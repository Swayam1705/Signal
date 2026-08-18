"""Embedding provider abstraction with production and controlled local implementations."""
from __future__ import annotations

import asyncio
import hashlib
import math
import re
from abc import ABC, abstractmethod

import httpx
import numpy as np

from backend.core.config import Settings
from backend.rag.text import word_tokens


class EmbeddingProvider(ABC):
    model_name: str
    dimension: int
    mode: str = "production"
    provider_name: str = "unknown"

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]: ...


class HashingEmbeddingProvider(EmbeddingProvider):
    """Dependency-free multilingual feature hashing fallback; not presented as a neural model."""
    model_name = "signal-hashing-v1"
    provider_name = "feature-hashing"
    mode = "development_fallback"

    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def _embed(self, text: str) -> list[float]:
        normalized = re.sub(r"\s+", " ", text.lower()).strip()
        words = word_tokens(normalized)
        features = words + [normalized[i:i + 3] for i in range(max(0, len(normalized) - 2)) if " " not in normalized[i:i + 3]]
        vector = np.zeros(self.dimension, dtype=np.float32)
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign * (1.0 + math.log1p(len(feature)))
        norm = float(np.linalg.norm(vector))
        if norm:
            vector /= norm
        return vector.tolist()

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Lazy optional multilingual neural embedding provider."""
    provider_name = "sentence-transformers"
    mode = "production"

    def __init__(self, model_name: str, device: str = "cpu"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("Install the 'ml' dependency group for sentence-transformers embeddings") from exc
        self.model_name = model_name
        self.device = device
        self._model = SentenceTransformer(model_name, device=None if device == "auto" else device)
        self.dimension = int(self._model.get_sentence_embedding_dimension())

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        inputs = [f"passage: {text}" for text in texts] if "e5" in self.model_name.lower() else texts
        result = await asyncio.to_thread(self._model.encode, inputs, normalize_embeddings=True, show_progress_bar=False)
        return result.tolist()

    async def embed_query(self, text: str) -> list[float]:
        value = f"query: {text}" if "e5" in self.model_name.lower() else text
        result = await asyncio.to_thread(self._model.encode, [value], normalize_embeddings=True, show_progress_bar=False)
        return result[0].tolist()


class OpenAIEmbeddingProvider(EmbeddingProvider):
    provider_name = "openai-compatible"
    mode = "production"

    def __init__(self, settings: Settings):
        if not settings.embedding_api_key:
            raise RuntimeError("EMBEDDING_API_KEY is required")
        self.model_name = settings.embedding_model
        self.dimension = settings.embedding_dimension
        self.client = httpx.AsyncClient(
            base_url=settings.embedding_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.embedding_api_key}"}, timeout=20,
        )

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.post("/embeddings", json={"model": self.model_name, "input": texts})
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda row: row["index"])
        vectors = [row["embedding"] for row in data]
        if any(len(vector) != self.dimension for vector in vectors):
            raise RuntimeError(f"EMBEDDING_DIMENSION_MISMATCH: configured={self.dimension}")
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "sentence_transformers":
        return SentenceTransformerEmbeddingProvider(settings.embedding_model, settings.embedding_device)
    if settings.embedding_provider == "openai":
        return OpenAIEmbeddingProvider(settings)
    return HashingEmbeddingProvider(settings.embedding_dimension)
