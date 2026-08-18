#!/usr/bin/env python3
"""Compare real chunk boundaries from every SIGNAL strategy on the same document."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings  # noqa: E402
from backend.rag.chunking.strategies import STRATEGIES, ChunkConfig  # noqa: E402


def default_text() -> str:
    fixture = ROOT / "data" / "source" / "dev_fixture.jsonl"
    passages: list[str] = []
    with fixture.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            passages.extend(record["passages"]["English_passages"])
            if len(" ".join(passages).split()) >= 650:
                break
    return "\n\n".join(passages)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-file", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "chunking_comparison.json")
    args = parser.parse_args()
    text = args.text_file.read_text(encoding="utf-8") if args.text_file else default_text()
    settings = get_settings()
    config = ChunkConfig(settings.chunk_size, settings.chunk_overlap, settings.min_chunk_size, settings.max_chunk_size)
    metadata = {"title": "Shared inspection document", "section": "RAG evaluation", "language": "en"}
    strategies: dict[str, object] = {}
    for name, strategy_type in STRATEGIES.items():
        chunks = strategy_type(config).chunk(
            text, document_id="chunking_inspection", record_id="inspection", source="judge-inspection",
            metadata=metadata,
        )
        strategies[name] = {
            "chunk_count": len(chunks),
            "selected_algorithm": chunks[0].metadata.get("adaptive_selected_strategy") if chunks else None,
            "chunks": [
                {
                    "index": chunk.chunk_index, "tokens": chunk.token_count, "characters": chunk.character_count,
                    "overlap": chunk.overlap, "start": chunk.text[:100], "end": chunk.text[-100:],
                    "chunk_id": chunk.chunk_id,
                }
                for chunk in chunks
            ],
        }
    report = {
        "generated_at": datetime.now(UTC).isoformat(), "source": "bundled fixture passages",
        "same_document_sha256": __import__("hashlib").sha256(text.encode()).hexdigest(),
        "document_tokens": len(text.split()), "config": asdict(config), "strategies": strategies,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
