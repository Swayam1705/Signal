"""Hybrid vector + BM25 lexical retrieval with query-dependent scoring."""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from backend.core.config import Settings
from backend.models.schemas import Candidate, Chunk, QueryAnalysis
from backend.rag.embeddings.providers import EmbeddingProvider
from backend.rag.text import word_tokens
from backend.rag.vector.qdrant_store import QdrantVectorStore

_STOPWORDS = {"a", "an", "the", "is", "are", "was", "were", "be", "been", "being", "of", "to", "and", "or", "in", "on", "at", "for", "from", "by", "with", "as", "it", "this", "that", "what", "who", "when", "where", "why", "how", "does", "do", "did", "which", "find", "most", "relevant", "evidence", "please", "answer", "indexed", "passages", "question", "request", "using", "only"}


def tokenize(text: str) -> list[str]:
    return [word for word in word_tokens(text) if len(word) > 1 and word not in _STOPWORDS]


class BM25Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.term_frequencies = [Counter(tokenize(chunk.text)) for chunk in chunks]
        self.lengths = [sum(freq.values()) for freq in self.term_frequencies]
        self.avgdl = sum(self.lengths) / max(1, len(self.lengths))
        document_frequency: Counter[str] = Counter()
        for freq in self.term_frequencies:
            document_frequency.update(freq.keys())
        total = len(chunks)
        self.idf = {term: math.log(1 + (total - count + 0.5) / (count + 0.5)) for term, count in document_frequency.items()}

    def search(self, query: str, limit: int) -> list[tuple[Chunk, float]]:
        terms = tokenize(query)
        scores: list[tuple[int, float]] = []
        k1, b = 1.5, 0.75
        for index, frequencies in enumerate(self.term_frequencies):
            score = 0.0
            for term in terms:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + k1 * (1 - b + b * self.lengths[index] / max(1, self.avgdl))
                score += self.idf.get(term, 0) * frequency * (k1 + 1) / denominator
            if score:
                scores.append((index, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        ceiling = scores[0][1] if scores else 1.0
        return [(self.chunks[index], score / ceiling) for index, score in scores[:limit]]


class HybridRetriever:
    def __init__(self, settings: Settings, embeddings: EmbeddingProvider, vector_store: QdrantVectorStore):
        self.settings = settings
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.chunks = self._load_chunks(settings.chunks_path)
        self.by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        self.lexical = BM25Index(self.chunks)

    @staticmethod
    def _load_chunks(path: Path) -> list[Chunk]:
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as handle:
            return [Chunk.model_validate(json.loads(line)) for line in handle if line.strip()]

    def reload(self) -> None:
        self.chunks = self._load_chunks(self.settings.chunks_path)
        self.by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        self.lexical = BM25Index(self.chunks)

    def effective_weights(self, analysis: QueryAnalysis) -> dict[str, float]:
        semantic_weight = self.settings.semantic_weight
        lexical_weight = self.settings.lexical_weight
        if analysis.retrieval_mode == "lexical_boost":
            semantic_weight, lexical_weight = 0.40, 0.50
        elif analysis.retrieval_mode == "broad":
            semantic_weight, lexical_weight = 0.65, 0.25
        return {"semantic": semantic_weight, "lexical": lexical_weight, "metadata": self.settings.metadata_weight}

    async def retrieve(self, analysis: QueryAnalysis, *, top_k: int, metadata_filter: dict[str, str] | None = None) -> list[Candidate]:
        query_vector = await self.embeddings.embed_query(analysis.normalized_query)
        pool = max(top_k * 2, self.settings.top_k_candidates)
        semantic = await self.vector_store.search(query_vector, pool, metadata_filter)
        lexical = self.lexical.search(analysis.normalized_query, pool)
        semantic_map = {chunk.chunk_id: max(0.0, min(1.0, score)) for chunk, score in semantic}
        lexical_map = {chunk.chunk_id: score for chunk, score in lexical}
        chunk_map = {chunk.chunk_id: chunk for chunk, _ in semantic + lexical}

        weights = self.effective_weights(analysis)
        semantic_weight = weights["semantic"]
        lexical_weight = weights["lexical"]
        metadata_weight = weights["metadata"]

        candidates: list[Candidate] = []
        query_language = analysis.language.split("_")[0].lower()
        for chunk_id, chunk in chunk_map.items():
            filter_match = bool(metadata_filter) and all(
                str(chunk.metadata.get(key)) == str(value) for key, value in metadata_filter.items()
            )
            chunk_language = str(chunk.metadata.get("language", "")).split("_")[0].lower()
            # is_selected is evaluation ground truth and must never influence online ranking.
            meta_score = 1.0 if filter_match else (0.5 if query_language and chunk_language == query_language else 0.0)
            semantic_score = semantic_map.get(chunk_id, 0.0)
            lexical_score = lexical_map.get(chunk_id, 0.0)
            hybrid = semantic_weight * semantic_score + lexical_weight * lexical_score + metadata_weight * meta_score
            candidates.append(Candidate(chunk=chunk, semantic_score=semantic_score, lexical_score=lexical_score, metadata_score=meta_score, hybrid_score=min(1.0, hybrid)))
        candidates.sort(key=lambda candidate: candidate.hybrid_score, reverse=True)
        for rank, candidate in enumerate(candidates[:top_k], 1):
            candidate.rank_before = rank
        return candidates[:top_k]

    async def retrieve_lexical(self, analysis: QueryAnalysis, *, top_k: int, metadata_filter: dict[str, str] | None = None) -> list[Candidate]:
        """Vector-store failure fallback; remains real retrieval and is marked by orchestration telemetry."""
        rows = self.lexical.search(analysis.normalized_query, top_k)
        output: list[Candidate] = []
        for rank, (chunk, score) in enumerate(rows, 1):
            if metadata_filter and not all(str(chunk.metadata.get(k)) == str(v) for k, v in metadata_filter.items()):
                continue
            query_language = analysis.language.split("_")[0].lower()
            chunk_language = str(chunk.metadata.get("language", "")).split("_")[0].lower()
            metadata_score = 1.0 if metadata_filter else (0.5 if query_language and chunk_language == query_language else 0.0)
            hybrid = min(1.0, 0.9 * score + 0.1 * metadata_score)
            output.append(Candidate(chunk=chunk, lexical_score=score, metadata_score=metadata_score, hybrid_score=hybrid, rank_before=rank))
        return output[:top_k]
