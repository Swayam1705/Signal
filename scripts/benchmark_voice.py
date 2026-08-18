#!/usr/bin/env python3
"""Measure the real HTTP audio → ElevenLabs STT → production text RAG path."""
from __future__ import annotations

import argparse
import asyncio
import mimetypes
import platform
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.models.schemas import BenchmarkSummary  # noqa: E402
from scripts.benchmark import percentile, persist  # noqa: E402

AUDIO_SUFFIXES = {".webm", ".ogg", ".wav", ".mp3", ".m4a", ".mp4", ".aac"}


async def run(args: argparse.Namespace) -> BenchmarkSummary:
    files = sorted(path for path in args.audio_dir.iterdir() if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES)
    if not files:
        raise SystemExit(f"No supported audio files found in {args.audio_dir}")

    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=args.timeout) as client:
        health_response = await client.get("/api/health")
        health_response.raise_for_status()
        health = health_response.json()
        services = {item["name"]: item for item in health.get("services", [])}
        if health.get("runtime_profile") != "full-production" or services.get("STT", {}).get("status") != "online":
            raise SystemExit(
                "Full-voice benchmark requires runtime_profile=full-production and STT=online. "
                "Configure production embeddings/LLM/ElevenLabs, re-index, start the API, and rerun."
            )

        async def execute(audio_path: Path) -> tuple[dict, float]:
            content_type = mimetypes.guess_type(audio_path.name)[0] or "audio/webm"
            started = time.perf_counter()
            response = await client.post(
                "/api/query/voice",
                data={"bypass_cache": "true"},
                files={"audio": (audio_path.name, audio_path.read_bytes(), content_type)},
            )
            wall_ms = (time.perf_counter() - started) * 1000
            response.raise_for_status()
            return response.json(), wall_ms

        warmup_count = 0
        for index in range(args.warmup_queries):
            await execute(files[index % len(files)])
            warmup_count += 1

        rows: list[dict[str, object]] = []
        wall_values: list[float] = []
        retrieval_values: list[float] = []
        generation_values: list[float] = []
        scores: list[float] = []
        for index in range(args.queries):
            audio_path = files[index % len(files)]
            try:
                body, wall_ms = await execute(audio_path)
                timings = body.get("telemetry", [])
                by_stage = {item["stage"]: item["duration_ms"] for item in timings}
                top_score = body.get("evidence", [{}])[0].get("rerank_score", 0) if body.get("evidence") else 0
                row: dict[str, object] = {
                    "audio": audio_path.name, "request_id": body.get("request_id"), "status": body.get("status"),
                    "http_wall_ms": wall_ms, "server_total_ms": body.get("total_ms"),
                    "stt_ms": by_stage.get("stt", 0), "retrieval_ms": by_stage.get("retrieval", 0),
                    "generation_ms": by_stage.get("generation", 0),
                    "grounded": body.get("trace", {}).get("grounding", {}).get("passed", False),
                    "retries": body.get("trace", {}).get("retry_count", 0), "top_score": top_score,
                }
                wall_values.append(wall_ms)
                retrieval_values.append(float(by_stage.get("retrieval", 0)))
                generation_values.append(float(by_stage.get("generation", 0)))
                scores.append(float(top_score))
            except Exception as exc:
                row = {"audio": audio_path.name, "status": "error", "error": type(exc).__name__}
            rows.append(row)
            if args.progress and ((index + 1) % 10 == 0 or index + 1 == args.queries):
                print(f"Measured {index + 1}/{args.queries}", file=sys.stderr)

    successful = [row for row in rows if row.get("status") != "error"]
    manifest = health.get("manifest") or {}
    now = datetime.now(UTC)
    summary = BenchmarkSummary(
        benchmark_id=f"bench_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
        timestamp=now.isoformat(), profile="full-voice", query_count=len(rows), warmup_count=warmup_count,
        indexed_documents=health.get("indexed_documents", 0), indexed_chunks=health.get("indexed_chunks", 0),
        environment={
            "profile_description": "HTTP upload + ElevenLabs STT + full-production text RAG",
            "python": platform.python_version(), "platform": platform.platform(),
            "dataset": manifest.get("dataset"), "dataset_source": health.get("dataset"),
            "dataset_mode": health.get("dataset_mode"), "dataset_records": manifest.get("records"),
            "subset_id": manifest.get("subset_id"), "indexed_documents": health.get("indexed_documents"),
            "indexed_chunks": health.get("indexed_chunks"), "embedding": services.get("EMBEDDING", {}).get("detail"),
            "vector_store": services.get("QDRANT", {}).get("detail"), "lexical_retriever": "BM25",
            "reranker": services.get("RERANKER", {}).get("detail"), "generator": services.get("LLM", {}).get("detail"),
            "stt": services.get("STT", {}).get("detail"), "audio_files": len(files),
            "unique_audio_files": len({row.get("audio") for row in rows}), "base_url": args.base_url,
        },
        latency_scope=(
            "client-observed HTTP multipart upload → audio validation → ElevenLabs STT → query analysis → "
            "embedding + Qdrant/BM25 retrieval → hybrid score → rerank → context → production generation → "
            "grounding → JSON response; excludes browser microphone capture"
        ),
        cache_policy="response cache bypassed for every measured request; providers/index/API warmed before measurement",
        cold_cache=False,
        p50_ms=percentile(wall_values, 50), p70_ms=percentile(wall_values, 70),
        p95_ms=percentile(wall_values, 95), p100_ms=max(wall_values, default=0),
        mean_ms=mean(wall_values) if wall_values else 0, min_ms=min(wall_values, default=0),
        max_ms=max(wall_values, default=0), failure_rate=(len(rows) - len(successful)) / max(1, len(rows)),
        refusal_rate=sum(row.get("status") == "refused" for row in successful) / max(1, len(successful)),
        grounding_pass_rate=sum(bool(row.get("grounded")) for row in successful) / max(1, len(successful)),
        retry_rate=sum(bool(row.get("retries")) for row in successful) / max(1, len(successful)),
        avg_retrieval_ms=mean(retrieval_values) if retrieval_values else 0,
        avg_generation_ms=mean(generation_values) if generation_values else 0,
        avg_score=mean(scores) if scores else 0, results=rows,
    )
    artifact = persist(summary, args.output_dir)
    print(summary.model_dump_json(indent=2))
    print(f"Saved immutable benchmark: {artifact}", file=sys.stderr)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--warmup-queries", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "benchmarks")
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args()
    if args.queries < 1 or args.warmup_queries < 0:
        parser.error("query count must be positive and warmup count non-negative")
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
