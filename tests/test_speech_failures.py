import httpx
import pytest

from backend.core.config import Settings
from backend.speech.providers import ElevenLabsSpeechProvider, SpeechProviderError


class TimeoutClient:
    def __init__(self):
        self.calls = 0

    async def post(self, *args, **kwargs):
        self.calls += 1
        raise httpx.ReadTimeout("provider timeout")


class MalformedResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        raise ValueError("not json")


class MalformedClient:
    async def post(self, *args, **kwargs):
        return MalformedResponse()


class ValidResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"text": "Recovered transcript", "language_code": "en", "words": []}


class TimeoutThenValidClient:
    def __init__(self):
        self.calls = 0

    async def post(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise httpx.ReadTimeout("transient timeout")
        return ValidResponse()


@pytest.mark.asyncio
async def test_empty_audio_fails_before_provider_call():
    provider = ElevenLabsSpeechProvider(Settings(elevenlabs_api_key="configured-for-test"))
    with pytest.raises(SpeechProviderError, match="EMPTY_AUDIO"):
        await provider.transcribe(b"", "empty.webm", "audio/webm")


@pytest.mark.asyncio
async def test_stt_timeout_has_stable_error():
    provider = ElevenLabsSpeechProvider(Settings(elevenlabs_api_key="configured-for-test"))
    await provider.client.aclose()
    client = TimeoutClient()
    provider.client = client  # type: ignore[assignment]
    with pytest.raises(SpeechProviderError, match="STT_TIMEOUT"):
        await provider.transcribe(b"audio", "recording.webm", "audio/webm")
    assert client.calls == 2


@pytest.mark.asyncio
async def test_stt_transient_timeout_recovers_within_retry_budget():
    provider = ElevenLabsSpeechProvider(Settings(elevenlabs_api_key="configured-for-test"))
    await provider.client.aclose()
    client = TimeoutThenValidClient()
    provider.client = client  # type: ignore[assignment]
    result = await provider.transcribe(b"audio", "recording.webm", "audio/webm")
    assert result.text == "Recovered transcript"
    assert client.calls == 2


@pytest.mark.asyncio
async def test_stt_malformed_provider_response_has_stable_error():
    provider = ElevenLabsSpeechProvider(Settings(elevenlabs_api_key="configured-for-test"))
    await provider.client.aclose()
    provider.client = MalformedClient()  # type: ignore[assignment]
    with pytest.raises(SpeechProviderError, match="STT_MALFORMED_RESPONSE"):
        await provider.transcribe(b"audio", "recording.webm", "audio/webm")
