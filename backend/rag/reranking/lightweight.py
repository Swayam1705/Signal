"""Low-latency, separate relevance reranker with inspectable features."""
from __future__ import annotations

from backend.models.schemas import Candidate
from backend.rag.text import word_tokens


class LightweightReranker:
    model_name = "SIGNAL Lightweight Relevance Reranker"
    implementation = "deterministic feature-based reranker"

    @staticmethod
    def _terms(text: str) -> list[str]:
        stop = {"a", "an", "the", "is", "are", "was", "were", "of", "to", "and", "or", "in", "on", "at", "for", "from", "by", "with", "as", "it", "this", "that", "what", "who", "when", "where", "why", "how", "does", "do", "did", "which", "find", "most", "relevant", "evidence", "please", "answer", "indexed", "passages", "question", "request", "using", "only"}
        return [word for word in word_tokens(text) if len(word) > 1 and word not in stop]

    async def rerank(self, query: str, candidates: list[Candidate], top_k: int) -> list[Candidate]:
        query_terms = self._terms(query)
        query_set = set(query_terms)
        phrase = " ".join(query_terms)
        for candidate in candidates:
            text_terms = self._terms(candidate.chunk.text)
            text_set = set(text_terms)
            coverage = len(query_set & text_set) / max(1, len(query_set))
            phrase_bonus = 1.0 if phrase and phrase in " ".join(text_terms) else 0.0
            # Relevance labels such as MSMARCO is_selected are evaluation-only and never ranking features.
            candidate.rerank_score = min(
                1.0, 0.60 * candidate.hybrid_score + 0.30 * coverage + 0.10 * phrase_bonus,
            )
        candidates.sort(key=lambda item: item.rerank_score, reverse=True)
        selected = candidates[:top_k]
        for rank, candidate in enumerate(selected, 1):
            candidate.rank_after = rank
        return selected
