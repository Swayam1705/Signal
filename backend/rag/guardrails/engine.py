"""Dedicated input, retrieved-content, evidence, and output guardrails."""
from __future__ import annotations

import re

from backend.models.schemas import Candidate, GeneratedAnswer, GuardrailResult, QueryAnalysis
from backend.rag.text import word_tokens


class GuardrailEngine:
    retrieved_injection = re.compile(
        r"(?i)(ignore (all|previous) instructions|system prompt|assistant:|developer message|execute this command)"
    )

    def validate_input(self, analysis: QueryAnalysis) -> GuardrailResult:
        if analysis.safety_status == "prompt_injection":
            return GuardrailResult(status="rejected", reason="Prompt injection pattern detected", flags=["PROMPT_INJECTION"])
        if analysis.safety_status == "unsafe":
            return GuardrailResult(status="rejected", reason="Unsafe instruction request detected", flags=["UNSAFE_INPUT"])
        return GuardrailResult(status="passed", reason="Input policy checks passed")

    def filter_retrieved(self, candidates: list[Candidate]) -> tuple[list[Candidate], list[str]]:
        clean: list[Candidate] = []
        flags: list[str] = []
        for candidate in candidates:
            if self.retrieved_injection.search(candidate.chunk.text):
                flags.append(f"RETRIEVED_INJECTION:{candidate.chunk.chunk_id}")
                continue
            clean.append(candidate)
        return clean, flags

    def evidence_check(self, candidates: list[Candidate], threshold: float, query: str = "",
                       min_query_coverage: float = 0.30) -> GuardrailResult:
        if not candidates:
            return GuardrailResult(status="rejected", reason="No evidence was retrieved", flags=["NO_EVIDENCE"])
        if candidates[0].rerank_score < threshold:
            return GuardrailResult(status="rejected", reason=f"Top evidence score {candidates[0].rerank_score:.3f} is below threshold {threshold:.3f}", flags=["LOW_EVIDENCE"])
        stop = {"a", "an", "the", "is", "are", "was", "were", "of", "to", "and", "or", "in", "on", "at", "for", "from", "by", "with", "as", "it", "this", "that", "what", "who", "when", "where", "why", "how", "does", "do", "did", "which", "give", "find", "please", "answer", "evidence", "indexed", "passages", "question", "request", "using", "only", "most", "relevant"}
        query_terms = {term for term in word_tokens(query) if len(term) > 1 and term not in stop}
        evidence_terms = set(word_tokens(candidates[0].chunk.text))
        coverage = len(query_terms & evidence_terms) / max(1, len(query_terms))
        # Inflected Indic queries often share fewer exact surface forms with a valid passage.
        # Keep the safeguard, but use a documented lower lexical floor outside ASCII scripts.
        effective_min_coverage = min(min_query_coverage, 0.20) if any(
            any(ord(character) > 127 for character in term) for term in query_terms
        ) else min_query_coverage
        if query_terms and coverage < effective_min_coverage:
            return GuardrailResult(
                status="rejected",
                reason=f"Top evidence covers only {coverage:.3f} of material query terms; minimum is {effective_min_coverage:.3f}",
                flags=["LOW_QUERY_COVERAGE"],
            )
        return GuardrailResult(status="passed", reason=f"Evidence thresholds passed; query coverage {coverage:.3f}")

    def validate_output(self, answer: GeneratedAnswer) -> GuardrailResult:
        if not answer.answer.strip():
            return GuardrailResult(status="rejected", reason="Generator returned an empty answer", flags=["MALFORMED_OUTPUT"])
        if not answer.refusal and not answer.citations:
            return GuardrailResult(status="rejected", reason="Answer has no citations", flags=["UNGROUNDED_OUTPUT"])
        return GuardrailResult(status="passed", reason="Structured output checks passed")
