"""Inspectable, deterministic chunking strategies used only during offline ingestion."""
from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from backend.models.schemas import Chunk
from backend.rag.text import word_tokens

_SENTENCE = re.compile(r"(?<=[.!?।؟])\s+|\n+")


def tokens(text: str) -> list[str]:
    return word_tokens(text)


def sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE.split(text.strip()) if part.strip()]


@dataclass(slots=True)
class ChunkConfig:
    chunk_size: int = 160
    overlap: int = 32
    minimum_chunk_size: int = 24
    maximum_chunk_size: int = 240


class ChunkingStrategy(ABC):
    name: str

    def __init__(self, config: ChunkConfig | None = None):
        self.config = config or ChunkConfig()

    @abstractmethod
    def split(self, text: str, metadata: dict[str, Any] | None = None) -> list[tuple[str, int]]:
        """Return (chunk_text, overlap_tokens) pairs."""

    def chunk(self, text: str, *, document_id: str, record_id: str, source: str, metadata: dict[str, Any] | None = None) -> list[Chunk]:
        metadata = metadata or {}
        output: list[Chunk] = []
        for index, (part, overlap) in enumerate(self.split(text, metadata)):
            digest = hashlib.sha1(f"{document_id}:{self.name}:{index}:{part}".encode()).hexdigest()[:16]
            output.append(Chunk(
                chunk_id=f"chk_{digest}", document_id=document_id, record_id=record_id,
                source=source, strategy=self.name, chunk_index=index,
                token_count=len(tokens(part)), character_count=len(part), overlap=overlap,
                text=part, embedding_id=f"emb_{digest}", metadata=metadata,
            ))
        return output


class SentenceChunker(ChunkingStrategy):
    name = "sentence"

    def split(self, text: str, metadata: dict[str, Any] | None = None) -> list[tuple[str, int]]:
        groups: list[tuple[str, int]] = []
        current: list[str] = []
        count = 0
        for sentence in sentences(text):
            size = len(tokens(sentence))
            if current and count + size > self.config.chunk_size:
                groups.append((" ".join(current), 0))
                current, count = [], 0
            if size > self.config.maximum_chunk_size:
                words = sentence.split()
                groups.extend((" ".join(words[i:i + self.config.maximum_chunk_size]), 0) for i in range(0, len(words), self.config.maximum_chunk_size))
            else:
                current.append(sentence)
                count += size
        if current:
            groups.append((" ".join(current), 0))
        return groups


class SlidingWindowChunker(ChunkingStrategy):
    name = "sliding_window"

    def split(self, text: str, metadata: dict[str, Any] | None = None) -> list[tuple[str, int]]:
        words = text.split()
        size = min(self.config.chunk_size, self.config.maximum_chunk_size)
        overlap = min(self.config.overlap, max(0, size - 1))
        step = max(1, size - overlap)
        output: list[tuple[str, int]] = []
        for start in range(0, len(words), step):
            part = words[start:start + size]
            if not part:
                break
            if len(part) < self.config.minimum_chunk_size and output:
                previous, previous_overlap = output[-1]
                output[-1] = (f"{previous} {' '.join(part)}", previous_overlap)
                break
            output.append((" ".join(part), overlap if start else 0))
            if start + size >= len(words):
                break
        return output


class FixedSemanticChunker(ChunkingStrategy):
    """Paragraph/sentence semantic boundaries with lexical cohesion as a cheap embedding proxy."""
    name = "semantic"

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        a, b = {x.lower() for x in tokens(left)}, {x.lower() for x in tokens(right)}
        return len(a & b) / max(1, len(a | b))

    def split(self, text: str, metadata: dict[str, Any] | None = None) -> list[tuple[str, int]]:
        units = sentences(text)
        if not units:
            return []
        chunks: list[str] = []
        current = units[0]
        for unit in units[1:]:
            projected = len(tokens(current)) + len(tokens(unit))
            semantic_break = self._similarity(current, unit) < 0.025 and len(tokens(current)) >= self.config.minimum_chunk_size
            if projected > self.config.chunk_size or semantic_break:
                chunks.append(current)
                current = unit
            else:
                current += " " + unit
        chunks.append(current)
        return [(chunk, 0) for chunk in chunks]


class MetadataAwareChunker(ChunkingStrategy):
    name = "metadata_aware"

    def split(self, text: str, metadata: dict[str, Any] | None = None) -> list[tuple[str, int]]:
        metadata = metadata or {}
        prefix_parts = [str(metadata.get(key, "")).strip() for key in ("title", "section", "language") if metadata.get(key)]
        prefix = " — ".join(prefix_parts)
        base = SentenceChunker(self.config).split(text, metadata)
        return [(f"{prefix}: {part}" if prefix else part, overlap) for part, overlap in base]


class AdaptiveHybridChunker(ChunkingStrategy):
    name = "adaptive_hybrid"

    def choose(self, text: str, metadata: dict[str, Any] | None = None) -> ChunkingStrategy:
        metadata = metadata or {}
        word_count = len(tokens(text))
        structured = bool(metadata.get("title") or metadata.get("section"))
        sentence_count = len(sentences(text))
        if structured:
            return MetadataAwareChunker(self.config)
        if word_count <= self.config.chunk_size or sentence_count <= 3:
            return SentenceChunker(self.config)
        if word_count > self.config.maximum_chunk_size * 3:
            return SlidingWindowChunker(self.config)
        return FixedSemanticChunker(self.config)

    def split(self, text: str, metadata: dict[str, Any] | None = None) -> list[tuple[str, int]]:
        return self.choose(text, metadata).split(text, metadata)

    def chunk(self, text: str, *, document_id: str, record_id: str, source: str, metadata: dict[str, Any] | None = None) -> list[Chunk]:
        metadata = dict(metadata or {})
        selected = self.choose(text, metadata)
        metadata["adaptive_selected_strategy"] = selected.name
        # Required storage label remains adaptive_hybrid while the selected algorithm is inspectable.
        return super().chunk(text, document_id=document_id, record_id=record_id, source=source, metadata=metadata)


STRATEGIES: dict[str, type[ChunkingStrategy]] = {
    "sentence": SentenceChunker,
    "sliding_window": SlidingWindowChunker,
    "semantic": FixedSemanticChunker,
    "metadata_aware": MetadataAwareChunker,
    "adaptive_hybrid": AdaptiveHybridChunker,
}
