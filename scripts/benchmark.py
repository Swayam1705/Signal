#!/usr/bin/env python3
"""Measure a declared SIGNAL profile; bypass response cache and persist immutable artifacts."""
from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.core.container import Container  # noqa: E402
from backend.models.schemas import BenchmarkSummary, QueryRequest  # noqa: E402

PROFILES = {
    "local-development": "Hashing embeddings + local Qdrant/BM25 + extractive development fallback",
    "neural-retrieval": "Neural embeddings + local Qdrant/BM25 + extractive development fallback",
    "full-production": "Neural/API embeddings + local Qdrant/BM25 + configured real LLM",
}


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile_value / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def persist(summary: BenchmarkSummary, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    artifact = directory / f"{summary.benchmark_id}.json"
    if artifact.exists():
        raise RuntimeError(f"Refusing to overwrite benchmark artifact: {artifact}")
    artifact.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    # latest.json is a convenience snapshot; immutable ID artifacts are never overwritten.
    (directory / "latest.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    index_path = directory / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"benchmarks": []}
    index["benchmarks"].append({
        "benchmark_id": summary.benchmark_id, "timestamp": summary.timestamp, "profile": summary.profile,
        "query_count": summary.query_count, "p50_ms": summary.p50_ms, "p70_ms": summary.p70_ms,
        "p95_ms": summary.p95_ms, "p100_ms": summary.p100_ms, "failure_rate": summary.failure_rate,
    })
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return artifact


async def run(args: argparse.Namespace) -> BenchmarkSummary:
    container = Container()
    try:
        manifest = container.manifest
        if not manifest or not container.vector_store.count:
            raise SystemExit("No compatible index found. Run: python scripts/ingest.py")
        actual_profile = container.settings.runtime_profile
        profile = actual_profile if args.profile == "auto" else args.profile
        if profile != actual_profile:
            raise SystemExit(
                f"Requested profile {profile!r}, but runtime is {actual_profile!r}. "
                "Configure providers, re-ingest with matching embeddings, and rerun."
            )
        base_queries = manifest.get("demo_queries") or []
        query_source = "index manifest demo_queries"
        evaluation_path = container.settings.evaluation_path
        if evaluation_path.exists():
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
            if evaluation.get("subset_id") == manifest.get("subset_id"):
                evaluated = [row.get("query") for row in evaluation.get("retrieval_results", [])]
                evaluated = list(dict.fromkeys(query for query in evaluated if isinstance(query, str) and query.strip()))
                if evaluated:
                    base_queries = evaluated
                    query_source = f"{evaluation.get('evaluation_id')} valid-ground-truth retrieval queries"
        if not base_queries:
            raise SystemExit("Manifest and evaluation artifacts contain no benchmark queries")
        queries = [base_queries[index % len(base_queries)] for index in range(args.queries)]
        warmup_count = 0
        if args.warmup:
            for query in base_queries[: min(args.warmup_queries, len(base_queries))]:
                await container.orchestrator.run(QueryRequest(query=query, bypass_cache=True))
                warmup_count += 1

        results: list[dict[str, object]] = []
        total_values: list[float] = []
        retrieval_values: list[float] = []
        generation_values: list[float] = []
        scores: list[float] = []
        for index, query in enumerate(queries, 1):
            started = time.perf_counter()
            try:
                response = await container.orchestrator.run(QueryRequest(query=query, bypass_cache=True))
                wall_ms = (time.perf_counter() - started) * 1000
                stages: dict[str, float] = {}
                for timing in response.telemetry:
                    stages[timing.stage] = stages.get(timing.stage, 0) + timing.duration_ms
                top_score = response.evidence[0].rerank_score if response.evidence else 0
                row: dict[str, object] = {
                    "query": query, "status": response.status, "pipeline_ms": response.total_ms,
                    "wall_ms": wall_ms, "retrieval_ms": stages.get("retrieval", 0),
                    "generation_ms": stages.get("generation", 0), "grounded": response.trace.grounding.passed,
                    "retries": response.trace.retry_count, "top_score": top_score,
                }
                total_values.append(response.total_ms)
                retrieval_values.append(stages.get("retrieval", 0))
                generation_values.append(stages.get("generation", 0))
                scores.append(top_score)
            except Exception as exc:
                row = {"query": query, "status": "error", "error": type(exc).__name__}
            results.append(row)
            if args.progress and (index % 10 == 0 or index == len(queries)):
                print(f"Measured {index}/{len(queries)}", file=sys.stderr)

        successful = [row for row in results if row["status"] != "error"]
        now = datetime.now(UTC)
        benchmark_id = f"bench_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        summary = BenchmarkSummary(
            benchmark_id=benchmark_id, timestamp=now.isoformat(), profile=profile,
            query_count=len(results), warmup_count=warmup_count,
            indexed_documents=container.document_count, indexed_chunks=container.vector_store.count,
            environment={
                "profile_description": PROFILES[profile], "python": platform.python_version(),
                "platform": platform.platform(), "dataset": manifest.get("dataset"),
                "dataset_source": manifest.get("dataset_source"), "dataset_mode": manifest.get("dataset_mode"),
                "dataset_records": manifest.get("records"), "subset_id": manifest.get("subset_id"),
                "indexed_documents": container.document_count, "indexed_chunks": container.vector_store.count,
                "embedding_provider": container.embeddings.provider_name,
                "embedding_mode": container.embeddings.mode, "embedding_model": container.embeddings.model_name,
                "embedding_dimension": container.embeddings.dimension, "vector_store": "Qdrant embedded cosine",
                "lexical_retriever": "BM25", "reranker": container.reranker.model_name,
                "reranker_implementation": container.reranker.implementation,
                "generator_provider": container.generator.provider_name, "generator": container.generator.model_name,
                "query_source": query_source, "unique_query_count": len(set(queries)),
                "warmup_queries": warmup_count, "stt": "not included",
            },
            latency_scope=(
                "complete text RAG: validation → analysis → query embedding + retrieval → hybrid scoring → "
                "rerank → context → generation → grounding → structured response; excludes HTTP, voice capture, and STT"
            ),
            cache_policy="response cache bypassed for every measured query; model/index/client warmed before measurement",
            cold_cache=False,
            p50_ms=percentile(total_values, 50), p70_ms=percentile(total_values, 70),
            p95_ms=percentile(total_values, 95), p100_ms=max(total_values, default=0),
            mean_ms=mean(total_values) if total_values else 0, min_ms=min(total_values, default=0),
            max_ms=max(total_values, default=0),
            failure_rate=(len(results) - len(successful)) / max(1, len(results)),
            refusal_rate=sum(row.get("status") == "refused" for row in successful) / max(1, len(successful)),
            grounding_pass_rate=sum(bool(row.get("grounded")) for row in successful) / max(1, len(successful)),
            retry_rate=sum(bool(row.get("retries")) for row in successful) / max(1, len(successful)),
            avg_retrieval_ms=mean(retrieval_values) if retrieval_values else 0,
            avg_generation_ms=mean(generation_values) if generation_values else 0,
            avg_score=mean(scores) if scores else 0, results=results,
        )
        artifact = persist(summary, container.settings.benchmark_dir)
        print(summary.model_dump_json(indent=2))
        print(f"Saved immutable benchmark: {artifact}", file=sys.stderr)
        return summary
    finally:
        await container.aclose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("auto", *PROFILES), default="auto")
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--warmup-queries", type=int, default=5)
    parser.add_argument("--no-warmup", dest="warmup", action="store_false")
    parser.add_argument("--progress", action="store_true")
    parser.set_defaults(warmup=True)
    args = parser.parse_args()
    if args.queries < 1 or args.warmup_queries < 0:
        parser.error("query count must be positive and warmup count non-negative")
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
