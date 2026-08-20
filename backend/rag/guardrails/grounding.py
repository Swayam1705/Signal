"""Post-generation claim, citation, quote, and lexical support validator."""
from __future__ import annotations

import re

from backend.models.schemas import Candidate, ClaimSupport, GeneratedAnswer, GroundingResult
from backend.rag.text import word_tokens


class GroundingValidator:
    def __init__(self, threshold: float = 0.35):  # Lowered default threshold from 0.55 to 0.35
        self.threshold = threshold

    @staticmethod
    def _terms(text: str) -> set[str]:
        stop = {"the", "a", "an", "is", "are", "was", "were", "of", "to", "and", "in", "that", "it", "for", "on"}
        return {term for term in word_tokens(text) if len(term) > 2 and term not in stop}

    @staticmethod
    def _claims(text: str) -> list[str]:
        """Conservative sentence-level claims; avoids pretending to perform hidden NLI."""
        return [part.strip() for part in re.split(r"(?<=[.!?à¥¤ØŸ])\s+|\n+", text.strip()) if part.strip()]

    async def validate(self, answer: GeneratedAnswer, evidence: list[Candidate]) -> GroundingResult:
        if answer.refusal:
            return GroundingResult(passed=True, score=1.0, reason="Safe refusal requires no factual grounding")

        by_chunk = {candidate.chunk.chunk_id: candidate.chunk for candidate in evidence}
        supported_citations = 0
        for citation in answer.citations:
            chunk = by_chunk.get(citation.chunk_id)
            if chunk and citation.document_id == chunk.document_id:
                # 1. Exact match check
                if citation.quote.strip().lower() in chunk.text.lower():
                    supported_citations += 1
                else:
                    # 2. Fuzzy term-overlap match check (prevents rejection on minor punctuation/casing changes)
                    quote_terms = self._terms(citation.quote)
                    chunk_terms = self._terms(chunk.text)
                    overlap = len(quote_terms & chunk_terms) / max(1, len(quote_terms))
                    if quote_terms and overlap >= 0.5:
                        supported_citations += 1

        citation_support = supported_citations / max(1, len(answer.citations))

        claim_results: list[ClaimSupport] = []
        for claim in self._claims(answer.answer):
            terms = self._terms(claim)
            scored_chunks: list[tuple[float, str]] = []
            for candidate in evidence:
                evidence_terms = self._terms(candidate.chunk.text)
                score = len(terms & evidence_terms) / max(1, len(terms))
                scored_chunks.append((score, candidate.chunk.chunk_id))
            best_score = max((score for score, _ in scored_chunks), default=0.0)
            supporting = [chunk_id for score, chunk_id in scored_chunks if score >= self.threshold]
            claim_results.append(ClaimSupport(
                claim=claim, score=min(1.0, best_score), supported=best_score >= self.threshold,
                supporting_chunk_ids=supporting,
            ))

        mean_claim_support = sum(item.score for item in claim_results) / max(1, len(claim_results)) if claim_results else 1.0
        score = min(1.0, 0.55 * mean_claim_support + 0.45 * citation_support)
        all_claims_supported = not claim_results or all(item.supported for item in claim_results)
        
        passed = bool(answer.citations) and citation_support >= 0.5 and all_claims_supported and score >= self.threshold
        return GroundingResult(
            passed=passed, score=score, supported_citations=supported_citations,
            total_citations=len(answer.citations), claims=claim_results,
            reason="Every claim and citation is supported" if passed else "One or more claims, citations, or quotes lacked support",
        )