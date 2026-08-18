"""The real orchestration harness: bounded retries, tools, timings, policies, and full trace."""
from __future__ import annotations

import copy
import json
import logging
import time
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from pydantic import ValidationError

from backend.core.config import Settings
from backend.models.schemas import (
    Candidate,
    GeneratedAnswer,
    GroundingResult,
    GuardrailResult,
    QueryRequest,
    QueryResponse,
    QueryTrace,
    StageTiming,
    ToolExecution,
)
from backend.rag.generation.providers import LLMProvider
from backend.rag.guardrails.engine import GuardrailEngine
from backend.rag.guardrails.grounding import GroundingValidator
from backend.rag.orchestration.context import ContextBuilder
from backend.rag.reranking.lightweight import LightweightReranker
from backend.rag.retrieval.hybrid import HybridRetriever
from backend.services.query_intelligence import QueryIntelligence

logger = logging.getLogger("signal.pipeline")
EventCallback = Callable[[dict[str, Any]], Awaitable[None]]
_STAGE_TO_TOOL = {
    "query_analysis": "analyze_query",
    "retrieval": "retrieve_candidates",
    "rerank": "rerank_candidates",
    "context": "build_context",
    "generation": "generate_answer",
    "grounding": "validate_grounding",
}


class PipelineError(RuntimeError):
    pass


class SignalOrchestrator:
    def __init__(self, settings: Settings, intelligence: QueryIntelligence, retriever: HybridRetriever,
                 reranker: LightweightReranker, context_builder: ContextBuilder, generator: LLMProvider,
                 grounding: GroundingValidator, guardrails: GuardrailEngine):
        self.settings = settings
        self.intelligence = intelligence
        self.retriever = retriever
        self.reranker = reranker
        self.context_builder = context_builder
        self.generator = generator
        self.grounding = grounding
        self.guardrails = guardrails
        try:
            manifest = json.loads(settings.manifest_path.read_text(encoding="utf-8"))
            self.dataset_label = manifest.get("dataset_source", "ai4bharat/MSMARCO-XI")
            self.chunk_strategy = manifest.get("chunk_strategy", "adaptive_hybrid")
        except (FileNotFoundError, json.JSONDecodeError):
            self.dataset_label = "not indexed"
            self.chunk_strategy = "unknown"
        self.cache: OrderedDict[str, QueryResponse] = OrderedDict()

    async def _emit(self, callback: EventCallback | None, request_id: str, stage: str, status: str, **data: Any) -> None:
        event = {"request_id": request_id, "stage": stage, "status": status, "timestamp": time.time(), **data}
        logger.info(json.dumps(event, ensure_ascii=False))
        if callback:
            await callback(event)

    @staticmethod
    def _refusal(reason: str, warning: str) -> GeneratedAnswer:
        if reason in {"UNSAFE_INPUT", "PROMPT_INJECTION"}:
            copy_text = "REQUEST REJECTED. SIGNAL cannot process this request under the active safety policy."
        else:
            copy_text = "INSUFFICIENT SIGNAL. I couldn't find reliable evidence for that question in the indexed knowledge base."
        return GeneratedAnswer(
            answer=copy_text, confidence=0, grounded=False, citations=[], warnings=[warning],
            refusal=True, refusal_reason=reason,
        )

    async def run(
        self, request: QueryRequest, callback: EventCallback | None = None, request_id: str | None = None,
    ) -> QueryResponse:
        request_id = request_id or f"req_{uuid.uuid4().hex[:16]}"
        pipeline_started = time.perf_counter()
        timings: list[StageTiming] = []
        tool_calls: list[ToolExecution] = []
        recovery_actions: list[str] = []
        retry_count = 0
        generation_attempts = 0

        async def measured(stage: str, operation: Callable[[], Awaitable[Any]], attempt: int = 0,
                           tool_status: str = "success") -> Any:
            await self._emit(callback, request_id, stage, "started", attempt=attempt)
            started = time.perf_counter()
            try:
                value = await operation()
            except Exception as exc:
                duration = (time.perf_counter() - started) * 1000
                timings.append(StageTiming(stage=stage, duration_ms=duration, status="error", attempt=attempt))
                tool_calls.append(ToolExecution(
                    tool=_STAGE_TO_TOOL[stage], stage=stage, status="error", duration_ms=duration,
                    attempt=attempt, error_type=type(exc).__name__,
                ))
                await self._emit(callback, request_id, stage, "error", duration_ms=duration, attempt=attempt, error=type(exc).__name__)
                raise
            duration = (time.perf_counter() - started) * 1000
            timings.append(StageTiming(stage=stage, duration_ms=duration, status="success", attempt=attempt))
            tool_calls.append(ToolExecution(
                tool=_STAGE_TO_TOOL[stage], stage=stage, status=tool_status, duration_ms=duration, attempt=attempt,
            ))
            await self._emit(callback, request_id, stage, "complete", duration_ms=duration, attempt=attempt)
            return value

        analysis = await measured(
            "query_analysis", lambda: self.intelligence.analyze(request.query, request.language, request.metadata_filter),
        )
        input_guardrail = self.guardrails.validate_input(analysis)
        if input_guardrail.status == "rejected":
            answer = self._refusal(input_guardrail.flags[0], input_guardrail.reason)
            grounding = GroundingResult(passed=True, score=1, reason="Policy refusal")
            response = self._finish(
                request, request_id, pipeline_started, analysis, [], [], "", answer, grounding,
                input_guardrail, timings, tool_calls, retry_count, generation_attempts, recovery_actions,
            )
            await self._emit(callback, request_id, "complete", "refused", duration_ms=response.total_ms)
            return response

        cache_key = f"{analysis.normalized_query}|{request.metadata_filter}|{request.top_k}"
        if not request.bypass_cache and cache_key in self.cache:
            cached = copy.deepcopy(self.cache[cache_key])
            cached.request_id = request_id
            cached.trace.request_id = request_id
            cached.trace.input_mode = request.input_mode
            cached.trace.cache_hit = True
            cached.trace.recovery_actions = ["RESPONSE_CACHE_HIT"]
            cached.total_ms = (time.perf_counter() - pipeline_started) * 1000
            cached.telemetry = timings + [StageTiming(stage="total", duration_ms=cached.total_ms, status="cached")]
            cached.trace.timings = cached.telemetry
            cached.trace.tool_calls = tool_calls
            await self._emit(callback, request_id, "complete", "cached", duration_ms=cached.total_ms)
            return cached

        top_k = request.top_k or self.settings.top_k_candidates
        try:
            candidates = await measured(
                "retrieval", lambda: self.retriever.retrieve(
                    analysis, top_k=top_k, metadata_filter=request.metadata_filter,
                ),
            )
        except Exception:
            retry_count += 1
            recovery_actions.append("VECTOR_RETRIEVAL_FAILED → BM25_FALLBACK")
            candidates = await measured(
                "retrieval", lambda: self.retriever.retrieve_lexical(
                    analysis, top_k=top_k, metadata_filter=request.metadata_filter,
                ), attempt=1, tool_status="fallback",
            )

        candidates, retrieval_flags = self.guardrails.filter_retrieved(candidates)
        if retrieval_flags:
            recovery_actions.append(f"REMOVED_{len(retrieval_flags)}_SUSPICIOUS_RETRIEVED_CHUNK(S)")
        reranked = await measured(
            "rerank", lambda: self.reranker.rerank(
                analysis.normalized_query, candidates, self.settings.rerank_top_k,
            ),
        )
        evidence_guardrail = self.guardrails.evidence_check(
            reranked, self.settings.min_retrieval_score, analysis.normalized_query,
            self.settings.min_query_coverage,
        )
        if retrieval_flags:
            evidence_guardrail.flags.extend(retrieval_flags)
            if evidence_guardrail.status == "passed":
                evidence_guardrail.status = "warning"
                evidence_guardrail.reason = "Evidence passed; suspicious retrieved instructions were removed"

        if evidence_guardrail.status == "rejected":
            answer = self._refusal(evidence_guardrail.flags[0], evidence_guardrail.reason)
            grounding = GroundingResult(passed=True, score=1, reason="Evidence-based refusal")
            response = self._finish(
                request, request_id, pipeline_started, analysis, candidates, [], "", answer, grounding,
                evidence_guardrail, timings, tool_calls, retry_count, generation_attempts, recovery_actions,
            )
            await self._emit(callback, request_id, "complete", "refused", duration_ms=response.total_ms)
            return response

        context, selected = await measured("context", lambda: self.context_builder.build(reranked))
        answer: GeneratedAnswer | None = None
        output_guardrail = GuardrailResult(status="passed", reason="Output policy checks passed")
        generation_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            generation_attempts += 1
            try:
                answer = await measured(
                    "generation", lambda attempt=attempt: self.generator.generate(
                        analysis.normalized_query, context, selected, strict=attempt > 0,
                    ), attempt=attempt,
                )
                output_guardrail = self.guardrails.validate_output(answer)
                if output_guardrail.status == "rejected":
                    tool_calls[-1].status = "error"
                    tool_calls[-1].error_type = "OutputGuardrailRejected"
                    raise ValueError(output_guardrail.reason)
                break
            except (ValidationError, ValueError, httpx.TimeoutException, httpx.HTTPError) as exc:
                generation_error = exc
                if attempt >= self.settings.max_retries:
                    break
                retry_count += 1
                recovery_actions.append(f"GENERATION_{type(exc).__name__.upper()} → STRICT_SCHEMA_RETRY")

        if answer is None or output_guardrail.status == "rejected":
            answer = self._refusal(
                "MALFORMED_MODEL_OUTPUT", f"Generator failed schema validation: {type(generation_error).__name__}",
            )
            grounding = GroundingResult(passed=True, score=1, reason="Generator failure refusal")
            guardrail = GuardrailResult(
                status="rejected", reason="Malformed model output after bounded retry", flags=["MALFORMED_OUTPUT"],
            )
            response = self._finish(
                request, request_id, pipeline_started, analysis, candidates, selected, context, answer, grounding,
                guardrail, timings, tool_calls, retry_count, generation_attempts, recovery_actions,
            )
            await self._emit(callback, request_id, "complete", "refused", duration_ms=response.total_ms)
            return response

        grounding = await measured("grounding", lambda: self.grounding.validate(answer, selected))
        if not grounding.passed and not answer.refusal:
            retry_count += 1
            generation_attempts += 1
            recovery_actions.append("GROUNDING_FAILED → STRICT_EVIDENCE_REGENERATION")
            try:
                regenerated = await measured(
                    "generation", lambda: self.generator.generate(
                        analysis.normalized_query, context, selected, strict=True,
                    ), attempt=1,
                )
                regrounding = await measured(
                    "grounding", lambda: self.grounding.validate(regenerated, selected), attempt=1,
                )
                if regrounding.passed:
                    answer, grounding = regenerated, regrounding
                else:
                    answer = self._refusal("GROUNDING_FAILURE", regrounding.reason)
                    grounding = regrounding
                    recovery_actions.append("GROUNDING_RETRY_FAILED → SAFE_REFUSAL")
            except Exception:
                answer = self._refusal("GROUNDING_FAILURE", "Strict grounding retry failed")
                recovery_actions.append("GROUNDING_RETRY_ERRORED → SAFE_REFUSAL")

        if not grounding.passed:
            final_guardrail = GuardrailResult(
                status="rejected", reason=grounding.reason, flags=["GROUNDING_FAILURE"],
            )
        elif evidence_guardrail.flags:
            final_guardrail = evidence_guardrail
        else:
            final_guardrail = output_guardrail
        response = self._finish(
            request, request_id, pipeline_started, analysis, candidates, selected, context, answer, grounding,
            final_guardrail, timings, tool_calls, retry_count, generation_attempts, recovery_actions,
        )
        if not request.bypass_cache and response.status == "complete":
            self.cache[cache_key] = copy.deepcopy(response)
            while len(self.cache) > 128:
                self.cache.popitem(last=False)
        await self._emit(callback, request_id, "complete", response.status, duration_ms=response.total_ms)
        return response

    def _finish(self, request: QueryRequest, request_id: str, started: float, analysis: Any,
                candidates: list[Candidate], selected: list[Candidate], context: str, answer: GeneratedAnswer,
                grounding: GroundingResult, guardrail: GuardrailResult, timings: list[StageTiming],
                tool_calls: list[ToolExecution], retry_count: int, generation_attempts: int,
                recovery_actions: list[str]) -> QueryResponse:
        total_ms = (time.perf_counter() - started) * 1000
        all_timings = timings + [StageTiming(stage="total", duration_ms=total_ms)]
        weights = self.retriever.effective_weights(analysis) if hasattr(self.retriever, "effective_weights") else {}
        trace = QueryTrace(
            request_id=request_id, input_mode=request.input_mode,
            transcript=request.query if request.input_mode == "voice" else None,
            analysis=analysis,
            query_plan={
                "intent": analysis.intent, "language": analysis.language,
                "safety_status": analysis.safety_status, "normalized": True,
            },
            retrieval_plan={
                "mode": analysis.retrieval_mode, "candidate_top_k": request.top_k or self.settings.top_k_candidates,
                "context_top_k": self.settings.rerank_top_k, "weights": weights,
                "metadata_filter": request.metadata_filter,
            },
            selected_chunk_strategy=self.chunk_strategy, retrieval_mode=analysis.retrieval_mode,
            candidate_count=len(candidates), top_k=len(selected), candidates=candidates,
            selected_evidence=selected, context=context, model_output=answer.model_dump(mode="json"),
            grounding=grounding, guardrail=guardrail, timings=all_timings, tool_calls=tool_calls,
            generation_attempts=generation_attempts, retry_count=retry_count,
            recovery_actions=recovery_actions,
        )
        status = "refused" if answer.refusal else "complete"
        return QueryResponse(
            request_id=request_id, status=status, answer=answer, evidence=selected, telemetry=all_timings,
            total_ms=total_ms, trace=trace,
            runtime_mode="live" if self.settings.production_ready else "development_fallback",
            dataset=self.dataset_label,
        )
