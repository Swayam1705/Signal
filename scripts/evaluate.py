#!/usr/bin/env python3
"""Deterministic retrieval, grounding, citation, and refusal evaluation from persisted ground truth."""
from __future__ import annotations

import asyncio
import json
import math
import re
import sys
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.core.container import Container  # noqa: E402
from backend.models.schemas import Chunk, QueryRequest  # noqa: E402


def query_variants(query: str) -> list[str]:
    stripped = re.sub(r"[?!.]+$", "", query.strip())
    return list(dict.fromkeys([
        query.strip(), stripped, stripped.lower(),
        f"Please answer from the indexed evidence: {stripped}",
        f"Find the most relevant evidence for: {stripped}",
        f"Question: {stripped}",
        f"Using only indexed passages, {stripped}",
        f"Evidence request — {stripped}",
    ]))


def dcg(relevances: list[int]) -> float:
    return sum(value / math.log2(index + 2) for index, value in enumerate(relevances))


def metric(name: str, values: list[bool]) -> dict[str, Any]:
    correct = sum(values)
    return {"name": name, "queries": len(values), "correct": correct, "incorrect": len(values) - correct, "rate": correct / len(values) if values else None}


def load_ground_truth(path: Path) -> tuple[list[dict[str, Any]], str]:
    chunks: list[Chunk] = []
    with path.open(encoding="utf-8") as handle:
        chunks = [Chunk.model_validate_json(line) for line in handle if line.strip()]
    relevant_by_record: dict[str, set[str]] = defaultdict(set)
    queries_by_record: dict[str, set[str]] = defaultdict(set)
    for chunk in chunks:
        query = str(chunk.metadata.get("query") or "").strip()
        if query:
            queries_by_record[chunk.record_id].add(query)
        if chunk.metadata.get("is_selected"):
            relevant_by_record[chunk.record_id].add(chunk.document_id)
    cases: list[dict[str, Any]] = []
    for record_id in sorted(queries_by_record):
        relevant = sorted(relevant_by_record.get(record_id, set()))
        if not relevant:
            continue
        for base_query in sorted(queries_by_record[record_id]):
            for variant_index, query in enumerate(query_variants(base_query)):
                cases.append({
                    "case_id": f"{record_id}_{variant_index}_{len(cases)}", "record_id": record_id,
                    "query": query, "base_query": base_query, "relevant_document_ids": relevant,
                })
    return cases, "passages.is_selected metadata persisted from the indexed MSMARCO-XI-schema records"


async def main() -> None:
    container = Container()
    try:
        if not container.manifest:
            raise SystemExit("Run ingestion first")
        cases, ground_truth_source = load_ground_truth(container.settings.chunks_path)
        retrieval_rows: list[dict[str, Any]] = []
        recall_1: list[bool] = []
        recall_3: list[bool] = []
        recall_5: list[bool] = []
        reciprocal_ranks: list[float] = []
        ndcg_values: list[float] = []
        grounding_values: list[bool] = []
        citation_values: list[bool] = []
        answerability_values: list[bool] = []

        for case in cases:
            response = await container.orchestrator.run(QueryRequest(query=case["query"], bypass_cache=True))
            ranked = [candidate.chunk.document_id for candidate in response.trace.candidates]
            relevant = set(case["relevant_document_ids"])
            ranks = [index + 1 for index, document_id in enumerate(ranked) if document_id in relevant]
            first_rank = min(ranks) if ranks else None
            hits = {k: any(document_id in relevant for document_id in ranked[:k]) for k in (1, 3, 5)}
            ideal = [1] * min(len(relevant), 5)
            actual = [1 if document_id in relevant else 0 for document_id in ranked[:5]]
            ndcg = dcg(actual) / dcg(ideal) if ideal else 0.0
            citation_valid = bool(response.answer.citations) and response.trace.grounding.supported_citations == response.trace.grounding.total_citations
            recall_1.append(hits[1])
            recall_3.append(hits[3])
            recall_5.append(hits[5])
            reciprocal_ranks.append(1 / first_rank if first_rank else 0.0)
            ndcg_values.append(ndcg)
            grounding_values.append(response.status == "complete" and response.trace.grounding.passed)
            citation_values.append(response.status == "complete" and citation_valid)
            answerability_values.append(response.status == "complete")
            retrieval_rows.append({
                **case, "status": response.status, "first_relevant_rank": first_rank,
                "recall_at_1": hits[1], "recall_at_3": hits[3], "recall_at_5": hits[5],
                "ndcg_at_5": ndcg, "grounding_passed": response.trace.grounding.passed,
                "citation_valid": citation_valid, "top_document_ids": ranked[:5],
            })

        adversarial_path = ROOT / "data" / "evaluation" / "adversarial_cases.json"
        adversarial_cases = json.loads(adversarial_path.read_text(encoding="utf-8"))
        adversarial_rows: list[dict[str, Any]] = []
        category_values: dict[str, list[bool]] = defaultdict(list)
        for case in adversarial_cases:
            response = await container.orchestrator.run(QueryRequest(query=case["query"], bypass_cache=True))
            reason = response.answer.refusal_reason
            passed = response.status == case["expected_status"] and reason in case["expected_reasons"]
            category_values[case["category"]].append(passed)
            adversarial_rows.append({
                **case, "actual_status": response.status, "actual_reason": reason, "passed": passed,
                "guardrail": response.trace.guardrail.model_dump(mode="json"),
            })

        now = datetime.now(UTC)
        evaluation_id = f"eval_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        retrieval_metrics = {
            "recall_at_1": metric("Recall@1", recall_1),
            "recall_at_3": metric("Recall@3", recall_3),
            "recall_at_5": metric("Recall@5", recall_5),
            "mrr": {"name": "MRR", "queries": len(cases), "value": sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else None},
            "ndcg_at_5": {"name": "nDCG@5", "queries": len(cases), "value": sum(ndcg_values) / len(ndcg_values) if ndcg_values else None},
        }
        report = {
            "evaluation_id": evaluation_id, "timestamp": now.isoformat(),
            "dataset": container.manifest.get("dataset"), "dataset_source": container.manifest.get("dataset_source"),
            "dataset_mode": container.manifest.get("dataset_mode"), "subset_id": container.manifest.get("subset_id"),
            "ground_truth_source": ground_truth_source,
            "ranking_ground_truth_isolation": (
                "passages.is_selected is read only by this evaluator; online hybrid retrieval and reranking never use it"
            ),
            "query_generation": "five deterministic surface variants per unique persisted query; no relevance labels were invented",
            "retrieval_query_count": len(cases), "unique_base_queries": len({case["base_query"] for case in cases}),
            "adversarial_query_count": len(adversarial_cases), "retrieval_metrics": retrieval_metrics,
            "grounding": metric("Grounding pass", grounding_values),
            "citation_validity": metric("Citation validity", citation_values),
            "answerability_accuracy": metric("In-domain answerability", answerability_values),
            "guardrails": {category: metric(category, values) for category, values in sorted(category_values.items())},
            "limitations": [
                "Surface variants increase robustness coverage but are not independent human-authored questions.",
                "The bundled fixture is small; rerun after official-subset ingestion for submission metrics.",
                "Relevance ground truth is passage-level is_selected metadata, not answer-quality annotation.",
            ],
            "retrieval_results": retrieval_rows, "adversarial_results": adversarial_rows,
        }
        evaluations_dir = ROOT / "reports" / "evaluations"
        evaluations_dir.mkdir(parents=True, exist_ok=True)
        immutable = evaluations_dir / f"{evaluation_id}.json"
        immutable.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        container.settings.evaluation_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        index_path = evaluations_dir / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"evaluations": []}
        for row in index["evaluations"]:
            row["latest"] = False
        index["evaluations"].append({
            "evaluation_id": evaluation_id, "timestamp": report["timestamp"], "latest": True,
            "status": "valid", "retrieval_query_count": len(cases),
            "recall_at_1": retrieval_metrics["recall_at_1"]["rate"],
            "recall_at_3": retrieval_metrics["recall_at_3"]["rate"],
            "recall_at_5": retrieval_metrics["recall_at_5"]["rate"],
            "mrr": retrieval_metrics["mrr"]["value"], "ndcg_at_5": retrieval_metrics["ndcg_at_5"]["value"],
            "grounding_rate": report["grounding"]["rate"],
            "note": "Ground-truth labels isolated from online ranking features",
        })
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"Saved immutable evaluation: {immutable}", file=sys.stderr)
    finally:
        await container.aclose()


if __name__ == "__main__":
    asyncio.run(main())
