#!/usr/bin/env python3
"""Offline MSMARCO-XI ingestion: load → validate → normalize → chunk → embed → index → manifest."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import heapq
import json
import os
import sys
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.core.config import get_settings  # noqa: E402
from backend.models.schemas import Chunk  # noqa: E402
from backend.rag.chunking.strategies import STRATEGIES, ChunkConfig  # noqa: E402
from backend.rag.embeddings.providers import create_embedding_provider  # noqa: E402
from backend.rag.vector.qdrant_store import QdrantVectorStore  # noqa: E402

DATASET_ID = "ai4bharat/MSMARCO-XI"
LANG_FILES = {"as": "asm", "bn": "ben", "gu": "guj", "hi": "hin", "kn": "kan", "ml": "mal", "mr": "mar", "ne": "nep", "or": "ori", "pa": "pan", "sa": "san", "ta": "tam", "te": "tel", "ur": "urd"}
EXPECTED_SCHEMA = [
    "source_lang", "target_lang", "meta", "query", "Answer", "query_id", "query_type",
    "passages.is_selected", "passages.English_passages", "passages.Translated_passages",
    "Eng_Query", "Eng_Answer",
]


def official_parquet_url(language: str, split: str) -> str:
    code = LANG_FILES[language]
    filename = f"{code}{'train' if split == 'train' else 'val'}.parquet"
    return f"https://huggingface.co/datasets/{DATASET_ID}/resolve/main/{split}/{filename}"


def fixture_records(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON at {path}:{number}") from exc


def huggingface_records(language: str, split: str) -> Iterable[dict[str, Any]]:
    """Stream official Parquet. Its first row group is large; substantial download is expected."""
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("Install requirements-ml.txt to ingest from Hugging Face") from exc
    url = official_parquet_url(language, split)
    return load_dataset(
        "parquet", data_files={split: url}, split=split, streaming=True, token=os.getenv("HF_TOKEN"),
    )


def deterministic_records(records: Iterable[dict[str, Any]], *, selection: str, max_records: int,
                          scan_limit: int, seed: int) -> Iterable[dict[str, Any]]:
    """Select a reproducible subset without pretending it is random over unscanned rows."""
    if selection == "first" or max_records == 0:
        return records
    limit = max(scan_limit, max_records)
    heap: list[tuple[int, int, dict[str, Any]]] = []
    for position, record in enumerate(records):
        if position >= limit:
            break
        record_id = str(record.get("query_id", position))
        score = int.from_bytes(hashlib.sha256(f"{seed}:{record_id}".encode()).digest()[:8], "big")
        item = (-score, position, record)
        if len(heap) < max_records:
            heapq.heappush(heap, item)
        elif item > heap[0]:
            heapq.heapreplace(heap, item)
    return [item[2] for item in sorted(heap, key=lambda row: (-row[0], row[1]))]


def validate_record(record: dict[str, Any]) -> None:
    required = ("query_id", "passages")
    missing = [field for field in required if field not in record]
    if missing:
        raise ValueError(f"Record missing required fields: {missing}")
    passages = record["passages"]
    if not isinstance(passages, dict):
        raise TypeError("passages must be an object")
    for field in ("is_selected", "English_passages", "Translated_passages"):
        if field not in passages or not isinstance(passages[field], (list, tuple)):
            raise ValueError(f"passages.{field} must be a list")


def clean_text(text: Any) -> str:
    return " ".join(str(text or "").replace("\x00", " ").split())


def record_chunks(record: dict[str, Any], source: str, strategy_name: str, config: ChunkConfig) -> list[Chunk]:
    validate_record(record)
    strategy = STRATEGIES[strategy_name](config)
    record_id = str(record["query_id"])
    passages = record["passages"]
    selected = list(passages.get("is_selected", []))
    output: list[Chunk] = []
    groups = (
        ("en", passages.get("English_passages", []), clean_text(record.get("Eng_Query"))),
        (str(record.get("target_lang") or "translated"), passages.get("Translated_passages", []), clean_text(record.get("query"))),
    )
    for language, texts, query in groups:
        for passage_index, raw_text in enumerate(texts):
            text = clean_text(raw_text)
            if not text:
                continue
            document_id = f"msxi_{record_id}_{language}_{passage_index}"
            metadata = {
                "language": language, "query": query, "query_type": clean_text(record.get("query_type")),
                "is_selected": bool(selected[passage_index]) if passage_index < len(selected) else False,
                "passage_index": passage_index, "target_lang": clean_text(record.get("target_lang")),
                "source_lang": clean_text(record.get("source_lang")),
                "translation_model": clean_text((record.get("meta") or {}).get("model_name")),
            }
            output.extend(strategy.chunk(
                text, document_id=document_id, record_id=record_id, source=source, metadata=metadata,
            ))
    return output


def load_existing_chunks(path: Path) -> tuple[set[str], set[str], int]:
    if not path.exists():
        return set(), set(), 0
    chunk_ids: set[str] = set()
    record_ids: set[str] = set()
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            chunk = Chunk.model_validate_json(line)
            chunk_ids.add(chunk.chunk_id)
            record_ids.add(chunk.record_id)
            count += 1
    return chunk_ids, record_ids, count


def validate_resume(manifest: dict[str, Any] | None, *, source_label: str, strategy: str,
                    provider: str, model: str) -> None:
    if not manifest:
        raise RuntimeError("--resume requires an existing manifest")
    expected = {
        "dataset_source": source_label, "chunk_strategy": strategy,
        "embedding_provider": provider, "embedding_model": model,
    }
    mismatches = [f"{key}: existing={manifest.get(key)!r}, requested={value!r}" for key, value in expected.items() if manifest.get(key) != value]
    if mismatches:
        raise RuntimeError("RESUME_CONFIGURATION_MISMATCH: " + "; ".join(mismatches))


async def ingest(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    config = ChunkConfig(settings.chunk_size, settings.chunk_overlap, settings.min_chunk_size, settings.max_chunk_size)
    embeddings = create_embedding_provider(settings)

    if args.source == "huggingface":
        dataset_mode = "full_dataset" if args.max_records == 0 else "official_subset"
        source_label = f"{DATASET_ID}:{args.language}:{args.split}:{'full' if dataset_mode == 'full_dataset' else 'subset'}"
        source_location = official_parquet_url(args.language, args.split)
        raw_records: Iterable[dict[str, Any]] = huggingface_records(args.language, args.split) if not args.dry_run else []
    else:
        fixture = Path(args.input) if args.input else settings.data_dir / "source" / "dev_fixture.jsonl"
        source_label = "development-fixture:MSMARCO-XI-schema"
        source_location = str(fixture.resolve())
        raw_records = fixture_records(fixture) if not args.dry_run else []
        dataset_mode = "development_fixture"

    subset_descriptor = {
        "dataset": DATASET_ID, "source": args.source, "language": args.language, "split": args.split,
        "selection": args.selection, "seed": args.seed, "scan_limit": args.scan_limit,
        "max_records": args.max_records, "source_location": source_location,
    }
    subset_id = "subset_" + hashlib.sha256(json.dumps(subset_descriptor, sort_keys=True).encode()).hexdigest()[:16]
    if args.dry_run:
        plan = {
            **subset_descriptor, "subset_id": subset_id, "dataset_mode": dataset_mode,
            "schema": EXPECTED_SCHEMA, "embedding_provider": settings.embedding_provider,
            "embedding_model": embeddings.model_name, "embedding_dimension": embeddings.dimension,
            "embedding_device": getattr(embeddings, "device", "cpu-local"),
            "note": "Dry run validates configuration and source mapping; no rows were downloaded or indexed.",
        }
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return plan

    records = deterministic_records(
        raw_records, selection=args.selection, max_records=args.max_records,
        scan_limit=args.scan_limit, seed=args.seed,
    )
    store = QdrantVectorStore(settings.qdrant_path, settings.qdrant_collection, embeddings.dimension)
    existing_manifest = None
    if settings.manifest_path.exists():
        existing_manifest = json.loads(settings.manifest_path.read_text(encoding="utf-8"))
    if args.resume:
        validate_resume(
            existing_manifest, source_label=source_label, strategy=args.strategy,
            provider=settings.embedding_provider, model=embeddings.model_name,
        )
        store.ensure_collection(recreate=False)
        seen_chunk_ids, seen_record_ids, chunk_count = load_existing_chunks(settings.chunks_path)
        file_mode = "a"
    else:
        store.ensure_collection(recreate=True)
        seen_chunk_ids, seen_record_ids, chunk_count = set(), set(), 0
        file_mode = "w"

    settings.chunks_path.parent.mkdir(parents=True, exist_ok=True)
    demo_queries = list((existing_manifest or {}).get("demo_queries", [])) if args.resume else []
    records_seen = len(seen_record_ids)
    records_scanned = 0
    duplicate_records = 0
    duplicate_chunks = 0
    invalid_records = 0
    strategy_counts: dict[str, int] = dict((existing_manifest or {}).get("selected_strategy_counts", {})) if args.resume else {}
    batch: list[Chunk] = []
    try:
        with settings.chunks_path.open(file_mode, encoding="utf-8") as chunks_file:
            for record in records:
                if args.max_records and records_seen >= args.max_records:
                    break
                records_scanned += 1
                record_id = str(record.get("query_id", ""))
                if record_id in seen_record_ids:
                    duplicate_records += 1
                    continue
                try:
                    generated = record_chunks(record, source_label, args.strategy, config)
                except (ValueError, TypeError, KeyError) as exc:
                    invalid_records += 1
                    print(f"WARN record skipped: {exc}", file=sys.stderr)
                    continue
                seen_record_ids.add(record_id)
                records_seen += 1
                query = clean_text(record.get("Eng_Query") or record.get("query"))
                if query and query not in demo_queries and len(demo_queries) < 12:
                    demo_queries.append(query)
                unique: list[Chunk] = []
                for chunk in generated:
                    if chunk.chunk_id in seen_chunk_ids:
                        duplicate_chunks += 1
                        continue
                    seen_chunk_ids.add(chunk.chunk_id)
                    unique.append(chunk)
                    chunks_file.write(chunk.model_dump_json() + "\n")
                    concrete = chunk.metadata.get("adaptive_selected_strategy", chunk.strategy)
                    strategy_counts[concrete] = strategy_counts.get(concrete, 0) + 1
                batch.extend(unique)
                chunk_count += len(unique)
                if len(batch) >= args.batch_size:
                    vectors = await embeddings.embed_documents([chunk.text for chunk in batch])
                    await store.upsert(batch, vectors)
                    print(f"Indexed {chunk_count} chunks from {records_seen} unique records", flush=True)
                    batch = []
            if batch:
                vectors = await embeddings.embed_documents([chunk.text for chunk in batch])
                await store.upsert(batch, vectors)
    finally:
        store.close()

    attempted = records_scanned or 1
    invalid_rate = invalid_records / attempted
    if invalid_rate > args.max_invalid_rate:
        raise RuntimeError(f"INVALID_RECORD_RATE {invalid_rate:.3f} exceeded limit {args.max_invalid_rate:.3f}")

    manifest = {
        "index_id": f"idx_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{subset_id[-6:]}",
        "dataset": DATASET_ID, "dataset_source": source_label, "dataset_mode": dataset_mode,
        "development_fixture": dataset_mode == "development_fixture", "official_subset": dataset_mode == "official_subset",
        "subset_id": subset_id, "subset": subset_descriptor, "deterministic_selection": True,
        "schema_inspected": EXPECTED_SCHEMA,
        "fields_indexed": ["passages.English_passages", "passages.Translated_passages"],
        "fields_metadata": ["query_id", "query", "Eng_Query", "query_type", "source_lang", "target_lang", "passages.is_selected", "meta.model_name"],
        "fields_ignored": ["Answer", "Eng_Answer", "meta.temperature", "meta.max_tokens", "meta.top_p", "meta.frequency_penalty", "meta.presence_penalty"],
        "language": args.language, "split": args.split, "records": records_seen,
        "records_scanned_this_run": records_scanned, "invalid_records_this_run": invalid_records,
        "duplicate_records_skipped": duplicate_records, "duplicate_chunks_skipped": duplicate_chunks,
        "chunks": chunk_count, "documents": len({chunk.document_id for chunk in load_chunks(settings.chunks_path)}),
        "chunk_strategy": args.strategy, "selected_strategy_counts": strategy_counts,
        "chunk_config": {"size": config.chunk_size, "overlap": config.overlap, "minimum": config.minimum_chunk_size, "maximum": config.maximum_chunk_size},
        "embedding_provider": settings.embedding_provider, "embedding_mode": embeddings.mode,
        "embedding_model": embeddings.model_name, "embedding_dimension": embeddings.dimension,
        "embedding_device": getattr(embeddings, "device", "cpu-local"),
        "vector_store": "Qdrant embedded", "resumed": args.resume,
        "created_at": datetime.now(UTC).isoformat(), "demo_queries": demo_queries,
    }
    settings.manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def load_chunks(path: Path) -> Iterator[Chunk]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield Chunk.model_validate_json(line)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("fixture", "huggingface"), default="fixture", help="fixture is small and explicitly labelled; huggingface streams official data")
    parser.add_argument("--input", help="MSMARCO-XI-schema JSONL path for fixture mode")
    parser.add_argument("--language", choices=tuple(LANG_FILES), default="hi")
    parser.add_argument("--split", choices=("train", "validation"), default="validation")
    parser.add_argument("--max-records", type=int, default=5000, help="0 means all records; never use 0 accidentally on the official 55.6 GB corpus")
    parser.add_argument("--selection", choices=("first", "hash"), default="first", help="deterministic subset policy")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--scan-limit", type=int, default=100000, help="hash selection considers only this deterministic prefix")
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--strategy", choices=tuple(STRATEGIES), default="adaptive_hybrid")
    parser.add_argument("--resume", action="store_true", help="resume only when source, chunking, and embedding settings match the manifest")
    parser.add_argument("--dry-run", action="store_true", help="print a reproducible plan without downloading or indexing records")
    parser.add_argument("--max-invalid-rate", type=float, default=0.05)
    args = parser.parse_args()
    if args.max_records < 0 or args.batch_size < 1 or args.scan_limit < 1:
        parser.error("record, batch, and scan limits must be non-negative/positive")
    if args.selection == "hash" and args.max_records == 0:
        parser.error("hash selection requires a positive --max-records")
    return args


if __name__ == "__main__":
    asyncio.run(ingest(parse_args()))
