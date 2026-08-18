"""Dependency-free Unicode tokenization shared by retrieval, reranking, and grounding."""
from __future__ import annotations

import unicodedata


def word_tokens(text: str) -> list[str]:
    """Keep Unicode letters/numbers and combining marks in one normalized token."""
    output: list[str] = []
    current: list[str] = []
    for character in unicodedata.normalize("NFKC", text):
        category = unicodedata.category(character)
        if category[0] in {"L", "N"} or category[0] == "M":
            current.append(character.lower())
        elif current:
            output.append("".join(current))
            current = []
    if current:
        output.append("".join(current))
    return output
