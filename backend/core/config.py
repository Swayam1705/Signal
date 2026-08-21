"""Typed configuration loaded exclusively from environment variables."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseModel):
    model_config = ConfigDict(validate_default=True)

    app_name: str = "SIGNAL — Voice Retrieval Intelligence"
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(default_factory=lambda: [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()])
    rate_limit_per_minute: int = Field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")), ge=1, le=10000)

    data_dir: Path = Field(default_factory=lambda: Path(os.getenv("DATA_DIR", str(ROOT / "data"))))
    vector_store: Literal["qdrant"] = "qdrant"
    qdrant_path: Path = Field(default_factory=lambda: Path(os.getenv("QDRANT_PATH", str(ROOT / "data" / "index" / "qdrant"))))
    qdrant_collection: str = Field(default_factory=lambda: os.getenv("QDRANT_COLLECTION", "signal_chunks"))

    embedding_provider: Literal["hashing", "sentence_transformers", "openai"] = Field(default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "hashing"))
    embedding_model: str = Field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small"))
    embedding_dimension: int = Field(default_factory=lambda: int(os.getenv("EMBEDDING_DIMENSION", "384")), ge=1, le=65536)
    embedding_device: str = Field(default_factory=lambda: os.getenv("EMBEDDING_DEVICE", "cpu"))
    embedding_mode: Literal["development_fallback", "production"] = Field(default_factory=lambda: os.getenv("EMBEDDING_MODE", "development_fallback"))
    embedding_api_key: str | None = Field(default_factory=lambda: os.getenv("EMBEDDING_API_KEY"))
    embedding_base_url: str = Field(default_factory=lambda: os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1"))

    llm_provider: Literal["extractive", "openai"] = Field(default_factory=lambda: os.getenv("LLM_PROVIDER", "extractive"))
    llm_model: str = Field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))
    llm_api_key: str | None = Field(default_factory=lambda: os.getenv("LLM_API_KEY"))
    llm_base_url: str = Field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"))
    llm_timeout_s: float = Field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_S", "12")), gt=0, le=300)
    llm_max_tokens: int = Field(default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "700")), ge=1, le=32768)

    stt_provider: Literal["elevenlabs"] = Field(default_factory=lambda: os.getenv("STT_PROVIDER", "elevenlabs"))
    elevenlabs_api_key: str | None = Field(default_factory=lambda: os.getenv("ELEVENLABS_API_KEY"))
    stt_model: str = Field(default_factory=lambda: os.getenv("STT_MODEL", "scribe_v1"))
    stt_timeout_s: float = Field(default_factory=lambda: float(os.getenv("STT_TIMEOUT_S", "30")), gt=0, le=300)
    stt_max_retries: int = Field(default_factory=lambda: int(os.getenv("STT_MAX_RETRIES", "1")), ge=0, le=3)
    max_audio_bytes: int = Field(default_factory=lambda: int(os.getenv("MAX_AUDIO_BYTES", "10485760")), ge=1024, le=104857600)

    top_k_candidates: int = Field(default_factory=lambda: int(os.getenv("TOP_K_CANDIDATES", "12")), ge=1, le=1000)
    rerank_top_k: int = Field(default_factory=lambda: int(os.getenv("RERANK_TOP_K", "4")), ge=1, le=100)
    semantic_weight: float = Field(default_factory=lambda: float(os.getenv("SEMANTIC_WEIGHT", "0.55")), ge=0, le=1)
    lexical_weight: float = Field(default_factory=lambda: float(os.getenv("LEXICAL_WEIGHT", "0.35")), ge=0, le=1)
    metadata_weight: float = Field(default_factory=lambda: float(os.getenv("METADATA_WEIGHT", "0.10")), ge=0, le=1)
    min_retrieval_score: float = Field(default_factory=lambda: float(os.getenv("MIN_RETRIEVAL_SCORE", "0.20")), ge=0, le=1)
    min_query_coverage: float = Field(default_factory=lambda: float(os.getenv("MIN_QUERY_COVERAGE", "0.30")), ge=0, le=1)
    grounding_threshold: float = Field(default_factory=lambda: float(os.getenv("GROUNDING_THRESHOLD", "0.55")), ge=0, le=1)
    context_token_budget: int = Field(default_factory=lambda: int(os.getenv("CONTEXT_TOKEN_BUDGET", "900")), ge=1, le=100000)
    max_retries: int = Field(default_factory=lambda: int(os.getenv("MAX_RETRIES", "1")), ge=0, le=3)

    chunk_size: int = Field(default_factory=lambda: int(os.getenv("CHUNK_SIZE", "160")), ge=1, le=100000)
    chunk_overlap: int = Field(default_factory=lambda: int(os.getenv("CHUNK_OVERLAP", "32")), ge=0, le=99999)
    min_chunk_size: int = Field(default_factory=lambda: int(os.getenv("MIN_CHUNK_SIZE", "24")), ge=1, le=100000)
    max_chunk_size: int = Field(default_factory=lambda: int(os.getenv("MAX_CHUNK_SIZE", "240")), ge=1, le=100000)

    @model_validator(mode="after")
    def validate_retrieval_and_chunking(self) -> "Settings":
        if abs(self.semantic_weight + self.lexical_weight + self.metadata_weight - 1.0) > 1e-6:
            raise ValueError("semantic, lexical, and metadata weights must sum to 1")
        if not self.min_chunk_size <= self.chunk_size <= self.max_chunk_size:
            raise ValueError("chunk sizes must satisfy MIN_CHUNK_SIZE <= CHUNK_SIZE <= MAX_CHUNK_SIZE")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return self

    @property
    def manifest_path(self) -> Path:
        return self.data_dir / "index" / "manifest.json"

    @property
    def chunks_path(self) -> Path:
        return self.data_dir / "index" / "chunks.jsonl"

    @property
    def benchmark_path(self) -> Path:
        return self.data_dir / "benchmarks" / "latest.json"

    @property
    def benchmark_dir(self) -> Path:
        return self.data_dir / "benchmarks"

    @property
    def evaluation_path(self) -> Path:
        return ROOT / "reports" / "evaluation.json"

    @property
    def runtime_profile(self) -> str:
        if self.embedding_provider == "hashing":
            return "local-development"
        if self.llm_provider == "extractive":
            return "neural-retrieval"
        return "full-production"

    @property
    def production_ready(self) -> bool:
        """Production text-RAG readiness; voice readiness is reported separately."""
        embedding_ready = (
            self.embedding_provider == "sentence_transformers"
            or bool(self.embedding_api_key)
            or self.embedding_mode == "production"
        )
        return bool(self.llm_provider == "openai" and self.llm_api_key and embedding_ready)

    @property
    def voice_ready(self) -> bool:
        return bool(self.production_ready and self.elevenlabs_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
