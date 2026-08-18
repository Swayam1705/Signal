"""Persistent embedded Qdrant vector store."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from backend.models.schemas import Chunk


class QdrantVectorStore:
    def __init__(self, path: Path, collection: str, dimension: int):
        path.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.collection = collection
        self.dimension = dimension
        self.client = QdrantClient(path=str(path))

    def ensure_collection(self, recreate: bool = False) -> None:
        names = {item.name for item in self.client.get_collections().collections}
        if recreate and self.collection in names:
            self.client.delete_collection(self.collection)
            names.remove(self.collection)
        if self.collection not in names:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.dimension, distance=Distance.COSINE),
            )

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"signal:{chunk_id}"))

    def upsert_sync(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        self.ensure_collection()
        points = [PointStruct(id=self._point_id(chunk.chunk_id), vector=vector, payload={"chunk": chunk.model_dump(mode="json")}) for chunk, vector in zip(chunks, vectors, strict=True)]
        if points:
            self.client.upsert(collection_name=self.collection, points=points, wait=True)

    async def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        await asyncio.to_thread(self.upsert_sync, chunks, vectors)

    def search_sync(self, vector: list[float], limit: int, metadata_filter: dict[str, str] | None = None) -> list[tuple[Chunk, float]]:
        if not self.available:
            return []
        conditions = [FieldCondition(key=f"chunk.metadata.{key}", match=MatchValue(value=value)) for key, value in (metadata_filter or {}).items()]
        result = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            query_filter=Filter(must=conditions) if conditions else None,
            limit=limit,
            with_payload=True,
        ).points
        return [(Chunk.model_validate(point.payload["chunk"]), float(point.score)) for point in result]

    async def search(self, vector: list[float], limit: int, metadata_filter: dict[str, str] | None = None) -> list[tuple[Chunk, float]]:
        return await asyncio.to_thread(self.search_sync, vector, limit, metadata_filter)

    @property
    def available(self) -> bool:
        try:
            return self.collection in {item.name for item in self.client.get_collections().collections}
        except Exception:
            return False

    @property
    def count(self) -> int:
        if not self.available:
            return 0
        return int(self.client.count(self.collection, exact=True).count)

    @property
    def configured_dimension(self) -> int | None:
        if not self.available:
            return None
        vectors = self.client.get_collection(self.collection).config.params.vectors
        return int(vectors.size) if hasattr(vectors, "size") else None

    def close(self) -> None:
        self.client.close()
