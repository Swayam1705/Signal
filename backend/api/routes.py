"""Typed HTTP API, including real-time NDJSON pipeline events."""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from pathlib import Path
from statistics import mean
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from backend.core.container import Container
from backend.models.schemas import (
    HealthResponse,
    HealthService,
    QueryRequest,
    QueryResponse,
    StageTiming,
    TranscriptionResult,
)
from backend.speech.providers import SpeechProviderError

router = APIRouter()


def container(request: Request) -> Container:
    return request.app.state.container


def _percentile(values: list[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile_value / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    c = container(request)
    indexed = c.vector_store.count
    services = [
        HealthService(name="STT", status="online" if c.stt.available else "offline", detail=f"{c.stt.name} / {c.stt.model_name}" if c.stt.available else "OFFLINE — ELEVENLABS_API_KEY REQUIRED"),
        HealthService(name="EMBEDDING", status="degraded" if c.embeddings.mode == "development_fallback" else "online", detail=f"{c.embeddings.provider_name} / {c.embeddings.model_name} / {c.embeddings.dimension}d"),
        HealthService(name="QDRANT", status="online" if indexed else "offline", detail=f"persistent cosine index / {indexed} chunks"),
        HealthService(name="BM25", status="online" if c.retriever.chunks else "offline", detail=f"in-memory lexical index / {len(c.retriever.chunks)} chunks"),
        HealthService(name="RERANKER", status="online", detail=f"{c.reranker.model_name} — {c.reranker.implementation}"),
        HealthService(name="LLM", status="degraded" if c.generator.is_fallback else "online", detail=f"{c.generator.provider_name} / {c.generator.model_name}"),
        HealthService(name="GROUNDING", status="online", detail=f"claim + citation verification / threshold {c.settings.grounding_threshold:.2f}"),
        HealthService(name="GUARDRAILS", status="online", detail="input, evidence, injection, unsafe, refusal"),
    ]
    overall = "online" if all(item.status == "online" for item in services) else ("degraded" if indexed else "offline")
    manifest = c.manifest
    dataset = manifest.get("dataset_source", "not indexed") if manifest else "not indexed"
    dataset_mode = manifest.get("dataset_mode", "development_fixture" if manifest and manifest.get("development_fixture") else "unknown") if manifest else "unknown"
    return HealthResponse(
        status=overall, mode="live" if c.settings.production_ready else "development_fallback",
        runtime_profile=c.settings.runtime_profile, services=services, dataset=dataset,
        dataset_mode=dataset_mode, indexed_documents=c.document_count, indexed_chunks=indexed, manifest=manifest,
    )


@router.post("/query", response_model=QueryResponse)
async def query(payload: QueryRequest, request: Request) -> QueryResponse:
    c = container(request)
    if not c.vector_store.available or not c.retriever.chunks:
        raise HTTPException(status_code=503, detail="VECTOR_INDEX_UNAVAILABLE: run python scripts/ingest.py")
    try:
        response = await c.orchestrator.run(payload)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"SIGNAL_PIPELINE_UNAVAILABLE:{type(exc).__name__}") from exc
    c.record(response)
    return response


@router.post("/query/stream")
async def query_stream(payload: QueryRequest, request: Request) -> StreamingResponse:
    c = container(request)
    if not c.vector_store.available or not c.retriever.chunks:
        raise HTTPException(status_code=503, detail="VECTOR_INDEX_UNAVAILABLE: run ingestion")
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def callback(event: dict[str, Any]) -> None:
        await queue.put({"type": "stage", "data": event})

    async def execute() -> None:
        try:
            response = await c.orchestrator.run(payload, callback)
            c.record(response)
            await queue.put({"type": "result", "data": response.model_dump(mode="json")})
        except Exception as exc:
            await queue.put({"type": "error", "data": {"code": "PIPELINE_ERROR", "message": type(exc).__name__}})
        finally:
            await queue.put(None)

    async def stream():
        task = asyncio.create_task(execute())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield json.dumps(item, ensure_ascii=False) + "\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


def _has_audio_signature(content: bytes) -> bool:
    return bool(
        content.startswith(b"\x1a\x45\xdf\xa3")  # WebM / Matroska
        or content.startswith(b"OggS")
        or (content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WAVE")
        or content.startswith(b"ID3")
        or (len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0)  # MP3/AAC frame
        or (len(content) >= 12 and content[4:8] == b"ftyp")  # MP4/M4A
    )


async def _read_audio(c: Container, audio: UploadFile) -> tuple[bytes, str, str]:
    content = await audio.read(c.settings.max_audio_bytes + 1)
    if len(content) > c.settings.max_audio_bytes:
        raise HTTPException(status_code=413, detail="AUDIO_TOO_LARGE")
    if not content:
        raise HTTPException(status_code=422, detail="EMPTY_AUDIO")
    content_type = audio.content_type or "application/octet-stream"
    allowed = ("audio/", "video/webm", "application/ogg")
    if not any(content_type.startswith(prefix) for prefix in allowed):
        raise HTTPException(status_code=415, detail="INVALID_AUDIO_TYPE")
    if not _has_audio_signature(content):
        raise HTTPException(status_code=422, detail="MALFORMED_AUDIO")
    return content, audio.filename or "recording.webm", content_type


@router.post("/transcribe", response_model=TranscriptionResult)
async def transcribe(request: Request, audio: UploadFile = File(...)) -> TranscriptionResult:
    c = container(request)
    content, filename, content_type = await _read_audio(c, audio)
    try:
        return await c.stt.transcribe(content, filename, content_type)
    except SpeechProviderError as exc:
        status = 503 if "UNAVAILABLE" in str(exc) else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/query/voice", response_model=QueryResponse)
async def voice_query(
    request: Request, audio: UploadFile = File(...), language: str | None = Form(default=None),
    top_k: int | None = Form(default=None), bypass_cache: bool = Form(default=False),
) -> QueryResponse:
    c = container(request)
    if not c.vector_store.available or not c.retriever.chunks:
        raise HTTPException(status_code=503, detail="VECTOR_INDEX_UNAVAILABLE: run ingestion")
    content, filename, content_type = await _read_audio(c, audio)
    try:
        transcript = await c.stt.transcribe(content, filename, content_type)
    except SpeechProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        response = await c.orchestrator.run(QueryRequest(
            query=transcript.text, input_mode="voice", language=language or transcript.language,
            top_k=top_k, bypass_cache=bypass_cache,
        ))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"SIGNAL_PIPELINE_UNAVAILABLE:{type(exc).__name__}") from exc
    rag_total = response.total_ms
    full_total = rag_total + transcript.duration_ms
    response.telemetry = [StageTiming(stage="stt", duration_ms=transcript.duration_ms)] + [timing for timing in response.telemetry if timing.stage != "total"] + [StageTiming(stage="total", duration_ms=full_total)]
    response.total_ms = full_total
    response.trace.transcript = transcript.text
    response.trace.timings = response.telemetry
    response.trace.model_output["rag_only_total_ms"] = rag_total
    c.record(response)
    return response


@router.post("/query/voice/stream")
async def voice_query_stream(
    request: Request, audio: UploadFile = File(...), language: str | None = Form(default=None),
    top_k: int | None = Form(default=None), bypass_cache: bool = Form(default=False),
) -> StreamingResponse:
    """Voice and all downstream stages as measured NDJSON events—no timer simulation."""
    c = container(request)
    if not c.vector_store.available or not c.retriever.chunks:
        raise HTTPException(status_code=503, detail="VECTOR_INDEX_UNAVAILABLE: run ingestion")
    content, filename, content_type = await _read_audio(c, audio)
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def callback(event: dict[str, Any]) -> None:
        await queue.put({"type": "stage", "data": event})

    async def execute() -> None:
        request_id = f"req_{uuid.uuid4().hex[:16]}"
        await queue.put({"type": "stage", "data": {
            "request_id": request_id, "stage": "stt", "status": "started", "timestamp": time.time(),
        }})
        try:
            transcript = await c.stt.transcribe(content, filename, content_type)
            await queue.put({"type": "stage", "data": {
                "request_id": request_id, "stage": "stt", "status": "complete",
                "timestamp": time.time(), "duration_ms": transcript.duration_ms, "transcript": transcript.text,
            }})
            response = await c.orchestrator.run(
                QueryRequest(
                    query=transcript.text, input_mode="voice", language=language or transcript.language,
                    top_k=top_k, bypass_cache=bypass_cache,
                ),
                callback, request_id=request_id,
            )
            rag_total = response.total_ms
            response.total_ms = rag_total + transcript.duration_ms
            response.telemetry = [StageTiming(stage="stt", duration_ms=transcript.duration_ms)] + [item for item in response.telemetry if item.stage != "total"] + [StageTiming(stage="total", duration_ms=response.total_ms)]
            response.trace.transcript = transcript.text
            response.trace.timings = response.telemetry
            response.trace.model_output["rag_only_total_ms"] = rag_total
            c.record(response)
            await queue.put({"type": "result", "data": response.model_dump(mode="json")})
        except SpeechProviderError as exc:
            await queue.put({"type": "error", "data": {
                "request_id": request_id, "timestamp": time.time(),
                "code": str(exc), "message": "Speech transcription failed",
            }})
        except Exception as exc:
            await queue.put({"type": "error", "data": {
                "request_id": request_id, "timestamp": time.time(),
                "code": "PIPELINE_ERROR", "message": type(exc).__name__,
            }})
        finally:
            await queue.put(None)

    async def stream():
        task = asyncio.create_task(execute())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield json.dumps(item, ensure_ascii=False) + "\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.get("/inspect/{request_id}")
async def inspect_request(request_id: str, request: Request) -> Any:
    trace = container(request).traces.get(request_id)
    if not trace:
        raise HTTPException(status_code=404, detail="REQUEST_TRACE_NOT_FOUND")
    return trace


@router.get("/metrics")
async def metrics(request: Request) -> dict[str, Any]:
    c = container(request)
    responses = list(c.responses)
    totals = [response.total_ms for response in responses]
    stage_values: dict[str, list[float]] = {}
    for response in responses:
        for timing in response.telemetry:
            stage_values.setdefault(timing.stage, []).append(timing.duration_ms)
    return {
        "source": "live_process_measurements", "sample_count": len(responses),
        "mean_total_ms": mean(totals) if totals else None,
        "p50_ms": _percentile(totals, 50), "p70_ms": _percentile(totals, 70),
        "p95_ms": _percentile(totals, 95), "p100_ms": max(totals) if totals else None,
        "stage_means_ms": {stage: mean(values) for stage, values in stage_values.items()},
        "success_rate": sum(response.status == "complete" for response in responses) / len(responses) if responses else None,
        "refusal_rate": sum(response.status == "refused" for response in responses) / len(responses) if responses else None,
    }


@router.get("/benchmark")
async def benchmark(request: Request) -> dict[str, Any]:
    path = container(request).settings.benchmark_path
    if not path.exists():
        return {"available": False, "reason": "No measured benchmark exists. Run python scripts/benchmark.py"}
    return {"available": True, **json.loads(path.read_text(encoding="utf-8"))}


@router.get("/benchmarks")
async def benchmark_history(request: Request) -> dict[str, Any]:
    path = container(request).settings.benchmark_dir / "index.json"
    if not path.exists():
        return {"benchmarks": []}
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/benchmark/profiles")
async def benchmark_profiles(request: Request) -> dict[str, Any]:
    """Profile registry keeps incomparable latency scopes visibly separate."""
    c = container(request)
    index_path = c.settings.benchmark_dir / "index.json"
    history = json.loads(index_path.read_text(encoding="utf-8")).get("benchmarks", []) if index_path.exists() else []
    definitions = [
        ("local-development", "LOCAL DEVELOPMENT TEXT RAG", "in-process text; hashing + local extractive fallback"),
        ("neural-retrieval", "LOCAL NEURAL EMBEDDING RAG", "in-process text; production embeddings + local extractive fallback"),
        ("full-production", "FULL PRODUCTION TEXT RAG", "in-process text; production embeddings + remote generation"),
        ("full-voice", "FULL VOICE END-TO-END", "HTTP audio upload + ElevenLabs STT + full-production text RAG"),
    ]
    profiles = []
    for profile_id, label, scope in definitions:
        runs = [row for row in history if row.get("profile") == profile_id]
        profiles.append({
            "profile": profile_id, "label": label, "scope": scope, "available": bool(runs),
            "measurement_count": len(runs), "latest": runs[-1] if runs else None,
        })
    return {"profiles": profiles}


@router.get("/benchmark/{benchmark_id}")
async def benchmark_by_id(benchmark_id: str, request: Request) -> dict[str, Any]:
    if not re.fullmatch(r"bench_[0-9]{8}_[0-9]{6}_[a-f0-9]{6}", benchmark_id):
        raise HTTPException(status_code=400, detail="INVALID_BENCHMARK_ID")
    path = container(request).settings.benchmark_dir / f"{benchmark_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="BENCHMARK_NOT_FOUND")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/evaluation")
async def evaluation(request: Request) -> dict[str, Any]:
    path = container(request).settings.evaluation_path
    if not path.exists():
        return {"available": False, "reason": "No verified evaluation exists. Run python scripts/evaluate.py"}
    return {"available": True, **json.loads(path.read_text(encoding="utf-8"))}


@router.get("/evaluations")
async def evaluation_history() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "reports" / "evaluations" / "index.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"evaluations": []}


@router.get("/evaluation/{evaluation_id}")
async def evaluation_by_id(evaluation_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"eval_[0-9]{8}_[0-9]{6}_[a-f0-9]{6}", evaluation_id):
        raise HTTPException(status_code=400, detail="INVALID_EVALUATION_ID")
    path = Path(__file__).resolve().parents[2] / "reports" / "evaluations" / f"{evaluation_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="EVALUATION_NOT_FOUND")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/chunking/preview")
async def chunking_preview() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "reports" / "chunking_comparison.json"
    if not path.exists():
        return {"available": False, "reason": "Run python scripts/inspect_chunking.py"}
    return {"available": True, **json.loads(path.read_text(encoding="utf-8"))}


@router.get("/pipeline")
async def pipeline() -> dict[str, Any]:
    return {"stages": [
        {"id": "01", "name": "VOICE", "what": "Browser MediaRecorder captures real audio", "why": "Low-friction multilingual input", "implementation": "getUserMedia + Web Audio API", "failure_modes": ["permission denied", "unsupported browser", "empty audio"]},
        {"id": "02", "name": "TRANSCRIBE", "what": "Audio becomes structured text", "why": "Converges voice and text paths", "implementation": "ElevenLabs Scribe provider adapter", "failure_modes": ["timeout", "rate limit", "empty transcript"]},
        {"id": "03", "name": "UNDERSTAND", "what": "Normalize, classify, and plan retrieval", "why": "Adapts scoring to the query", "implementation": "QueryIntelligence", "failure_modes": ["invalid query", "unsafe input", "prompt injection"]},
        {"id": "04", "name": "CHUNK", "what": "Offline adaptive document segmentation", "why": "Preserves useful evidence boundaries", "implementation": "Five strategy framework", "failure_modes": ["empty record", "invalid schema"]},
        {"id": "05", "name": "RETRIEVE", "what": "Semantic and lexical candidate search", "why": "Recall across meaning and exact terms", "implementation": "Qdrant + BM25 hybrid", "failure_modes": ["index unavailable", "low score"]},
        {"id": "06", "name": "RERANK", "what": "Reorder candidates with query-document features", "why": "Improve top context precision", "implementation": "Signal feature reranker", "failure_modes": ["empty candidates"]},
        {"id": "07", "name": "CONTEXT", "what": "Deduplicate and fit token budget", "why": "Keep only high-signal evidence", "implementation": "ContextBuilder", "failure_modes": ["budget exhausted"]},
        {"id": "08", "name": "GENERATE", "what": "Create schema-validated answer", "why": "Produce concise synthesis", "implementation": "OpenAI-compatible adapter or labelled extractive fallback", "failure_modes": ["timeout", "malformed JSON"]},
        {"id": "09", "name": "VERIFY", "what": "Check quotes and claim support", "why": "Know when not to answer", "implementation": "GroundingValidator", "failure_modes": ["unsupported claim", "bad citation"]},
        {"id": "10", "name": "RESPOND", "what": "Return answer, evidence, and full trace", "why": "Make every decision inspectable", "implementation": "Pydantic response contract", "failure_modes": ["serialization"]},
    ]}
