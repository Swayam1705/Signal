"""Application service graph; expensive clients and indexes are created once."""
from __future__ import annotations

import json
from collections import deque
from typing import Any

from backend.core.config import Settings, get_settings
from backend.rag.embeddings.providers import create_embedding_provider
from backend.rag.generation.providers import create_llm_provider
from backend.rag.guardrails.engine import GuardrailEngine
from backend.rag.guardrails.grounding import GroundingValidator
from backend.rag.orchestration.context import ContextBuilder
from backend.rag.orchestration.pipeline import SignalOrchestrator
from backend.rag.reranking.lightweight import LightweightReranker
from backend.rag.retrieval.hybrid import HybridRetriever
from backend.rag.vector.qdrant_store import QdrantVectorStore
from backend.services.query_intelligence import QueryIntelligence
from backend.speech.providers import ElevenLabsSpeechProvider


class Container:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._manifest = self._read_manifest()
        self.embeddings = create_embedding_provider(self.settings)
        self.vector_store = QdrantVectorStore(
            self.settings.qdrant_path, self.settings.qdrant_collection, self.embeddings.dimension,
        )
        self._validate_index_compatibility()
        self.retriever = HybridRetriever(self.settings, self.embeddings, self.vector_store)
        self.reranker = LightweightReranker()
        self.generator = create_llm_provider(self.settings)
        self.stt = ElevenLabsSpeechProvider(self.settings)
        self.orchestrator = SignalOrchestrator(
            self.settings, QueryIntelligence(), self.retriever, self.reranker,
            ContextBuilder(self.settings.context_token_budget), self.generator,
            GroundingValidator(self.settings.grounding_threshold), GuardrailEngine(),
        )
        self.traces: dict[str, Any] = {}
        self.responses: deque[Any] = deque(maxlen=500)

    def _read_manifest(self) -> dict[str, Any] | None:
        try:
            return json.loads(self.settings.manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _validate_index_compatibility(self) -> None:
        if not self.vector_store.available:
            return
        index_dimension = self.vector_store.configured_dimension
        if index_dimension != self.embeddings.dimension:
            raise RuntimeError(
                f"INDEX_DIMENSION_MISMATCH:index={index_dimension},runtime={self.embeddings.dimension}; rerun ingestion"
            )
        if not self._manifest:
            raise RuntimeError("INDEX_MANIFEST_MISSING: cannot verify embedding/index compatibility")
        manifest_provider = self._manifest.get("embedding_provider")
        manifest_model = self._manifest.get("embedding_model")
        if manifest_provider != self.settings.embedding_provider or manifest_model != self.embeddings.model_name:
            raise RuntimeError(
                "INDEX_EMBEDDING_MISMATCH: indexed vectors do not match the configured embedding provider/model; rerun ingestion"
            )

    @property
    def manifest(self) -> dict[str, Any] | None:
        return self._manifest

    @property
    def document_count(self) -> int:
        return len({chunk.document_id for chunk in self.retriever.chunks})

    def record(self, response: Any) -> None:
        self.traces[response.request_id] = response.trace
        self.responses.append(response)
        if len(self.traces) > 500:
            self.traces.pop(next(iter(self.traces)))

    async def aclose(self) -> None:
        self.vector_store.close()
        for service in (self.embeddings, self.generator, self.stt):
            client = getattr(service, "client", None)
            if client is not None and hasattr(client, "aclose"):
                await client.aclose()

    def close(self) -> None:
        """Close local storage for synchronous callers; async callers should use aclose()."""
        self.vector_store.close()
