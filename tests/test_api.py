import json

from fastapi.testclient import TestClient

from backend.main import app, settings
from backend.models.schemas import TranscriptionResult

VALID_WEBM_HEADER = b"\x1a\x45\xdf\xa3" + b"\x00" * 32


class DeterministicSTT:
    available = True
    name = "Contract STT"
    model_name = "contract-stt"

    async def transcribe(self, audio, filename, content_type):
        return TranscriptionResult(text="What causes tides?", language="en", confidence=1, duration_ms=4.5)


def test_health_and_text_query_contract():
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        status = health.json()
        assert status["indexed_chunks"] > 0
        assert status["indexed_documents"] > 0
        assert status["dataset_mode"] == "development_fixture"
        by_name = {service["name"]: service for service in status["services"]}
        assert by_name["EMBEDDING"]["status"] == "degraded"
        assert "feature-hashing" in by_name["EMBEDDING"]["detail"]
        assert by_name["STT"]["status"] == "offline"
        assert "API_KEY REQUIRED" in by_name["STT"]["detail"]

        response = client.post("/api/query", json={"query": "What causes ocean tides?", "bypass_cache": True})
        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["content-security-policy"].startswith("default-src 'none'")
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert body["status"] == "complete"
        assert body["request_id"].startswith("req_")
        assert body["telemetry"][-1]["stage"] == "total"
        assert body["trace"]["candidate_count"] > 0
        assert body["trace"]["input_mode"] == "text"
        assert body["trace"]["tool_calls"]
        assert body["trace"]["retrieval_plan"]["weights"]
        assert body["trace"]["grounding"]["claims"][0]["supported"]


def test_validation_audio_and_voice_provider_failure():
    with TestClient(app) as client:
        assert client.post("/api/query", json={"query": "   "}).status_code == 422
        assert client.post("/api/query", json={"query": "x" * 1001}).status_code == 422
        empty = client.post("/api/transcribe", files={"audio": ("empty.webm", b"", "audio/webm")})
        assert empty.status_code == 422 and empty.json()["detail"] == "EMPTY_AUDIO"
        malformed = client.post("/api/transcribe", files={"audio": ("bad.webm", b"not-real-audio", "audio/webm")})
        assert malformed.status_code == 422 and malformed.json()["detail"] == "MALFORMED_AUDIO"
        unavailable = client.post("/api/transcribe", files={"audio": ("audio.webm", VALID_WEBM_HEADER, "audio/webm")})
        assert unavailable.status_code == 503
        assert "STT_PROVIDER_UNAVAILABLE" in unavailable.json()["detail"]
        voice = client.post("/api/query/voice", files={"audio": ("audio.webm", VALID_WEBM_HEADER, "audio/webm")})
        assert voice.status_code == 503


def test_stream_emits_actual_stages_and_result():
    with TestClient(app) as client:
        response = client.post("/api/query/stream", json={"query": "What is photosynthesis?", "bypass_cache": True})
        assert response.status_code == 200
        messages = [json.loads(line) for line in response.text.splitlines() if line]
        assert any(message["type"] == "stage" and message["data"]["stage"] == "retrieval" and message["data"]["status"] == "started" for message in messages)
        result = next(message["data"] for message in messages if message["type"] == "result")
        assert result["trace"]["tool_calls"]
        assert result["trace"]["grounding"]["passed"]


def test_voice_stream_uses_one_request_id_and_same_orchestrator():
    with TestClient(app) as client:
        original = app.state.container.stt
        app.state.container.stt = DeterministicSTT()
        try:
            response = client.post(
                "/api/query/voice/stream",
                data={"bypass_cache": "true"},
                files={"audio": ("audio.webm", VALID_WEBM_HEADER, "audio/webm")},
            )
        finally:
            app.state.container.stt = original
        assert response.status_code == 200
        messages = [json.loads(line) for line in response.text.splitlines() if line]
        stages = [message["data"] for message in messages if message["type"] == "stage"]
        result = next(message["data"] for message in messages if message["type"] == "result")
        assert stages[0]["stage"] == "stt"
        assert all(stage["request_id"] == result["request_id"] for stage in stages)
        assert result["trace"]["input_mode"] == "voice"
        assert result["trace"]["transcript"] == "What causes tides?"
        assert result["telemetry"][0]["stage"] == "stt"
        assert result["trace"]["cache_hit"] is False


def test_repeated_query_uses_explicit_cache_trace():
    with TestClient(app) as client:
        payload = {"query": "What is DNA?"}
        first = client.post("/api/query", json=payload).json()
        second = client.post("/api/query", json=payload).json()
        assert first["status"] == "complete"
        assert second["trace"]["cache_hit"] is True
        assert second["trace"]["recovery_actions"] == ["RESPONSE_CACHE_HIT"]
        assert second["telemetry"][-1]["status"] == "cached"


def test_benchmark_evaluation_and_chunking_artifacts_are_exposed():
    with TestClient(app) as client:
        benchmark = client.get("/api/benchmark").json()
        assert benchmark["available"] is True
        assert benchmark["profile"] == "local-development"
        assert benchmark["query_count"] == 100
        assert benchmark["p95_ms"] >= benchmark["p70_ms"]
        history = client.get("/api/benchmarks").json()
        assert any(row["benchmark_id"] == benchmark["benchmark_id"] for row in history["benchmarks"])
        profiles = client.get("/api/benchmark/profiles").json()["profiles"]
        assert [profile["profile"] for profile in profiles] == [
            "local-development", "neural-retrieval", "full-production", "full-voice",
        ]
        assert next(profile for profile in profiles if profile["profile"] == "full-voice")["available"] is False
        assert client.get(f"/api/benchmark/{benchmark['benchmark_id']}").status_code == 200
        assert client.get("/api/benchmark/../../etc/passwd").status_code in (404, 400)
        evaluation = client.get("/api/evaluation").json()
        assert evaluation["available"] is True
        assert evaluation["retrieval_query_count"] >= 100
        evaluation_history = client.get("/api/evaluations").json()
        if evaluation_history["evaluations"]:
            latest_evaluation_id = evaluation_history["evaluations"][-1]["evaluation_id"]
            assert client.get(f"/api/evaluation/{latest_evaluation_id}").status_code == 200
        assert client.get("/api/evaluation/../../etc/passwd").status_code in (400, 404)
        preview = client.get("/api/chunking/preview").json()
        assert preview["available"] is True
        assert len(preview["strategies"]) == 5


def test_rate_limit_has_semantic_error_and_retry_header():
    original = settings.rate_limit_per_minute
    settings.rate_limit_per_minute = 1
    try:
        with TestClient(app) as client:
            first = client.post("/api/query", json={"query": "What is DNA?"})
            second = client.post("/api/query", json={"query": "What is DNA?"})
            assert first.status_code == 200
            assert second.status_code == 429
            assert second.json()["detail"] == "RATE_LIMIT_EXCEEDED"
            assert second.headers["retry-after"] == "60"
    finally:
        settings.rate_limit_per_minute = original
