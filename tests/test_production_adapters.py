import sys
from types import SimpleNamespace

import numpy as np
import pytest

from backend.core.config import Settings
from backend.models.schemas import Candidate, Chunk
from backend.rag.embeddings.providers import SentenceTransformerEmbeddingProvider
from backend.rag.generation.providers import OpenAICompatibleGenerator
from backend.speech.providers import ElevenLabsSpeechProvider


class FakeSentenceModel:
    last_inputs: list[str] = []

    def __init__(self, model_name: str, device: str | None = None):
        self.model_name = model_name
        self.device = device

    def get_sentence_embedding_dimension(self):
        return 3

    def encode(self, inputs, normalize_embeddings, show_progress_bar):
        self.last_inputs = list(inputs)
        return np.array([[1.0, 0.0, 0.0] for _ in inputs], dtype=np.float32)


@pytest.mark.asyncio
async def test_multilingual_e5_uses_query_and_passage_semantics(monkeypatch):
    module = SimpleNamespace(SentenceTransformer=FakeSentenceModel)
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    provider = SentenceTransformerEmbeddingProvider("intfloat/multilingual-e5-small")
    assert provider.dimension == 3
    await provider.embed_documents(["document text"])
    assert provider._model.last_inputs == ["passage: document text"]
    await provider.embed_query("question text")
    assert provider._model.last_inputs == ["query: question text"]


class FakeLLMResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": '{"answer":"Supported fact.","confidence":0.9,"grounded":true,"citations":[{"document_id":"d1","chunk_id":"c1","quote":"Supported fact."}],"warnings":[],"refusal":false,"refusal_reason":null}'}}]}


class FakeLLMClient:
    def __init__(self):
        self.payload = None

    async def post(self, path, json):
        self.payload = json
        return FakeLLMResponse()


class MalformedLLMResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"unexpected": []}


class MalformedLLMClient:
    async def post(self, path, json):
        return MalformedLLMResponse()


@pytest.mark.asyncio
async def test_openai_compatible_provider_enforces_schema_and_token_limit():
    settings = Settings(llm_provider="openai", llm_api_key="test-only-secret", llm_max_tokens=123)
    provider = OpenAICompatibleGenerator(settings)
    await provider.client.aclose()
    fake = FakeLLMClient()
    provider.client = fake  # type: ignore[assignment]
    text = "Supported fact."
    chunk = Chunk(chunk_id="c1", document_id="d1", record_id="r1", source="test", strategy="sentence", chunk_index=0, token_count=2, character_count=len(text), text=text, embedding_id="e1")
    result = await provider.generate("What is supported?", text, [Candidate(chunk=chunk)])
    assert result.answer == text
    assert result.citations[0].chunk_id == "c1"
    assert fake.payload["max_tokens"] == 123
    assert "test-only-secret" not in str(fake.payload)


@pytest.mark.asyncio
async def test_openai_compatible_malformed_envelope_has_typed_error():
    provider = OpenAICompatibleGenerator(Settings(llm_provider="openai", llm_api_key="test-only-secret"))
    await provider.client.aclose()
    provider.client = MalformedLLMClient()  # type: ignore[assignment]
    with pytest.raises(ValueError, match="LLM_MALFORMED_RESPONSE"):
        await provider.generate("question", "context", [])


class FakeSTTResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"text": "  What causes tides?  ", "language_code": "en", "words": [{"logprob": -0.1}]}


class FakeSTTClient:
    async def post(self, *args, **kwargs):
        return FakeSTTResponse()


@pytest.mark.asyncio
async def test_elevenlabs_success_contract_without_fake_frontend_transcription():
    provider = ElevenLabsSpeechProvider(Settings(elevenlabs_api_key="test-only-key"))
    await provider.client.aclose()
    provider.client = FakeSTTClient()  # type: ignore[assignment]
    result = await provider.transcribe(b"audio bytes", "recording.webm", "audio/webm")
    assert result.text == "What causes tides?"
    assert result.language == "en"
    assert result.confidence is not None and 0 < result.confidence <= 1
    assert result.duration_ms >= 0
