"""Evidence-preserving context construction under a deterministic token budget."""
from __future__ import annotations

from backend.models.schemas import Candidate


class ContextBuilder:
    def __init__(self, token_budget: int):
        self.token_budget = token_budget

    async def build(self, candidates: list[Candidate]) -> tuple[str, list[Candidate]]:
        seen_text: set[str] = set()
        selected: list[Candidate] = []
        blocks: list[str] = []
        used = 0
        for candidate in candidates:
            normalized = " ".join(candidate.chunk.text.lower().split())
            if normalized in seen_text:
                continue
            words = candidate.chunk.text.split()
            if used + len(words) > self.token_budget:
                remaining = self.token_budget - used
                if remaining < 24:
                    break
                text = " ".join(words[:remaining])
            else:
                text = candidate.chunk.text
            # Retrieved material is delimited and explicitly represented as data.
            blocks.append(f"<evidence document_id=\"{candidate.chunk.document_id}\" chunk_id=\"{candidate.chunk.chunk_id}\">\n{text}\n</evidence>")
            selected.append(candidate)
            seen_text.add(normalized)
            used += len(text.split())
            if used >= self.token_budget:
                break
        return "\n\n".join(blocks), selected
