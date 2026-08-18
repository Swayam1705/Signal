"""Fast deterministic query normalization, language hints, intent, and retrieval planning."""
from __future__ import annotations

import re
import unicodedata

from backend.models.schemas import QueryAnalysis


class QueryIntelligence:
    injection_patterns = (
        "ignore previous", "ignore all instructions", "system prompt", "developer message",
        "reveal your instructions", "jailbreak", "do not retrieve", "assistant:",
        "execute this command", "override safety", "treat retrieved", "hidden configuration",
    )
    unsafe_patterns = (
        "build a bomb", "make a bomb", "manufacture meth", "how to kill myself",
        "suicide instructions", "create ransomware", "steal credentials",
    )

    @staticmethod
    def normalize(query: str) -> str:
        query = unicodedata.normalize("NFKC", query)
        query = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", query)
        return re.sub(r"\s+", " ", query).strip()

    @staticmethod
    def language(text: str, hint: str | None = None) -> str:
        if hint:
            return hint
        counts = {
            "hi": len(re.findall(r"[\u0900-\u097F]", text)),
            "bn": len(re.findall(r"[\u0980-\u09FF]", text)),
            "ta": len(re.findall(r"[\u0B80-\u0BFF]", text)),
            "te": len(re.findall(r"[\u0C00-\u0C7F]", text)),
        }
        language, count = max(counts.items(), key=lambda item: item[1])
        return language if count else "en"

    async def analyze(self, query: str, language_hint: str | None = None, metadata_filter: dict[str, str] | None = None) -> QueryAnalysis:
        normalized = self.normalize(query)
        lowered = normalized.lower()
        safety = "safe"
        if any(pattern in lowered for pattern in self.injection_patterns):
            safety = "prompt_injection"
        elif any(pattern in lowered for pattern in self.unsafe_patterns):
            safety = "unsafe"

        if re.search(r"\b(what is|define|meaning of)\b", lowered):
            intent = "definition"
        elif re.search(r"\b(compare|difference|versus| vs )\b", lowered):
            intent = "comparison"
        elif re.search(r"\b(why|how|describe|explain)\b", lowered):
            intent = "description"
        elif normalized.endswith("?") or re.search(r"\b(who|when|where|which|what)\b", lowered):
            intent = "factoid"
        else:
            intent = "unknown"

        terms = re.findall(r"\w+", normalized, re.UNICODE)
        if metadata_filter:
            mode = "filtered"
        elif len(terms) <= 3:
            mode = "broad"
        elif any(char in normalized for char in ('"', "'")) or any(any(c.isdigit() for c in term) for term in terms):
            mode = "lexical_boost"
        else:
            mode = "balanced"
        return QueryAnalysis(
            normalized_query=normalized, intent=intent, language=self.language(normalized, language_hint),
            safety_status=safety, retrieval_mode=mode, relevant_to_dataset=True,
        )
