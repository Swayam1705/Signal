"""Public and internal contracts. Malformed provider output never crosses these schemas."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    record_id: str
    source: str
    strategy: Literal["semantic", "sentence", "sliding_window", "metadata_aware", "adaptive_hybrid"]
    chunk_index: int
    token_count: int
    character_count: int
    overlap: int = 0
    text: str
    embedding_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    input_mode: Literal["text", "voice"] = "text"
    language: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=30)
    metadata_filter: dict[str, str] | None = None
    bypass_cache: bool = False

    @field_validator("query")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class QueryAnalysis(BaseModel):
    normalized_query: str
    intent: Literal["factoid", "description", "definition", "comparison", "unknown"]
    language: str
    safety_status: Literal["safe", "unsafe", "prompt_injection"]
    retrieval_mode: Literal["balanced", "lexical_boost", "broad", "filtered"]
    relevant_to_dataset: bool = True


class Candidate(BaseModel):
    chunk: Chunk
    semantic_score: float = 0
    lexical_score: float = 0
    metadata_score: float = 0
    hybrid_score: float = 0
    rerank_score: float = 0
    rank_before: int = 0
    rank_after: int = 0


class Citation(BaseModel):
    document_id: str
    chunk_id: str
    quote: str


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    confidence: float = Field(ge=0, le=1)
    grounded: bool
    citations: list[Citation]
    warnings: list[str] = Field(default_factory=list)
    refusal: bool = False
    refusal_reason: str | None = None


class ClaimSupport(BaseModel):
    claim: str
    score: float = Field(ge=0, le=1)
    supported: bool
    supporting_chunk_ids: list[str] = Field(default_factory=list)


class GroundingResult(BaseModel):
    passed: bool
    score: float = Field(ge=0, le=1)
    supported_citations: int = 0
    total_citations: int = 0
    claims: list[ClaimSupport] = Field(default_factory=list)
    reason: str


class StageTiming(BaseModel):
    stage: Literal["stt", "query_analysis", "retrieval", "rerank", "context", "generation", "grounding", "total"]
    duration_ms: float = Field(ge=0)
    status: Literal["success", "error", "skipped", "cached"] = "success"
    attempt: int = 0


class ToolExecution(BaseModel):
    tool: Literal["analyze_query", "retrieve_candidates", "rerank_candidates", "build_context", "generate_answer", "validate_grounding"]
    stage: str
    status: Literal["success", "error", "fallback", "cached"]
    duration_ms: float = Field(ge=0)
    attempt: int = 0
    error_type: str | None = None


class GuardrailResult(BaseModel):
    status: Literal["passed", "rejected", "warning"]
    reason: str
    flags: list[str] = Field(default_factory=list)


class QueryTrace(BaseModel):
    request_id: str
    timestamp: str = Field(default_factory=utc_now)
    input_mode: Literal["text", "voice"] = "text"
    transcript: str | None = None
    analysis: QueryAnalysis
    query_plan: dict[str, Any] = Field(default_factory=dict)
    retrieval_plan: dict[str, Any] = Field(default_factory=dict)
    selected_chunk_strategy: str = "adaptive_hybrid"
    retrieval_mode: str
    candidate_count: int
    top_k: int
    candidates: list[Candidate]
    selected_evidence: list[Candidate]
    context: str
    model_output: dict[str, Any]
    grounding: GroundingResult
    guardrail: GuardrailResult
    timings: list[StageTiming]
    tool_calls: list[ToolExecution] = Field(default_factory=list)
    generation_attempts: int = 0
    retry_count: int = 0
    recovery_actions: list[str] = Field(default_factory=list)
    cache_hit: bool = False


class QueryResponse(BaseModel):
    request_id: str
    status: Literal["complete", "refused", "error"]
    answer: GeneratedAnswer
    evidence: list[Candidate]
    telemetry: list[StageTiming]
    total_ms: float
    trace: QueryTrace
    runtime_mode: Literal["live", "development_fallback"]
    dataset: str


class TranscriptionResult(BaseModel):
    text: str
    language: str
    confidence: float | None = None
    duration_ms: float


class HealthService(BaseModel):
    name: str
    status: Literal["online", "degraded", "offline"]
    detail: str


class HealthResponse(BaseModel):
    status: Literal["online", "degraded", "offline"]
    mode: Literal["live", "development_fallback"]
    runtime_profile: Literal["local-development", "neural-retrieval", "full-production"]
    services: list[HealthService]
    dataset: str
    dataset_mode: Literal["development_fixture", "official_subset", "full_dataset", "unknown"]
    indexed_documents: int
    indexed_chunks: int
    manifest: dict[str, Any] | None = None


class BenchmarkSummary(BaseModel):
    benchmark_id: str
    timestamp: str
    profile: Literal["local-development", "neural-retrieval", "full-production", "full-voice"]
    query_count: int
    warmup_count: int
    indexed_documents: int
    indexed_chunks: int
    environment: dict[str, Any]
    latency_scope: str
    cache_policy: str
    cold_cache: bool
    p50_ms: float
    p70_ms: float
    p95_ms: float
    p100_ms: float
    mean_ms: float
    min_ms: float
    max_ms: float
    failure_rate: float
    refusal_rate: float
    grounding_pass_rate: float
    retry_rate: float
    avg_retrieval_ms: float
    avg_generation_ms: float
    avg_score: float
    results: list[dict[str, Any]] = Field(default_factory=list)
