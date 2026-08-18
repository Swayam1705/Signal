import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app


def test_all_deterministic_adversarial_cases_fail_safely():
    cases = json.loads((Path(__file__).parents[1] / "data" / "evaluation" / "adversarial_cases.json").read_text(encoding="utf-8"))
    assert len(cases) >= 24
    with TestClient(app) as client:
        for case in cases:
            response = client.post("/api/query", json={"query": case["query"], "bypass_cache": True})
            assert response.status_code == 200, case["id"]
            body = response.json()
            assert body["status"] == case["expected_status"], case["id"]
            assert body["answer"]["refusal"] is True, case["id"]
            assert body["answer"]["refusal_reason"] in case["expected_reasons"], case["id"]
            assert body["answer"]["confidence"] == 0, case["id"]
            assert body["answer"]["citations"] == [], case["id"]
