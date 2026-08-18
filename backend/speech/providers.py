"""Speech-to-text provider interface and ElevenLabs Scribe implementation."""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod

import httpx

from backend.core.config import Settings
from backend.models.schemas import TranscriptionResult


class SpeechProviderError(RuntimeError):
    pass


class SpeechToTextProvider(ABC):
    name: str

    @abstractmethod
    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> TranscriptionResult: ...


class ElevenLabsSpeechProvider(SpeechToTextProvider):
    name = "ElevenLabs Scribe"
    model_name = "scribe_v1"

    def __init__(self, settings: Settings):
        self.api_key = settings.elevenlabs_api_key
        self.model = settings.stt_model
        self.model_name = settings.stt_model
        self.timeout = settings.stt_timeout_s
        self.max_retries = settings.stt_max_retries
        self.client = httpx.AsyncClient(base_url="https://api.elevenlabs.io", timeout=self.timeout)

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> TranscriptionResult:
        if not audio:
            raise SpeechProviderError("EMPTY_AUDIO")
        if not self.api_key:
            raise SpeechProviderError("STT_PROVIDER_UNAVAILABLE: ELEVENLABS_API_KEY is not configured")
        started = time.perf_counter()
        response: httpx.Response | object | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.post(
                    "/v1/speech-to-text",
                    headers={"xi-api-key": self.api_key},
                    data={"model_id": self.model, "tag_audio_events": "false", "diarize": "false"},
                    files={"file": (filename, audio, content_type)},
                )
            except httpx.TimeoutException as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                raise SpeechProviderError("STT_TIMEOUT") from exc
            status_code = getattr(response, "status_code", 0)
            if status_code == 429 or status_code >= 500:
                if attempt < self.max_retries:
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                code = "STT_RATE_LIMITED" if status_code == 429 else f"STT_PROVIDER_ERROR:{status_code}"
                raise SpeechProviderError(code)
            try:
                response.raise_for_status()  # type: ignore[union-attr]
            except httpx.HTTPStatusError as exc:
                raise SpeechProviderError(f"STT_PROVIDER_ERROR:{exc.response.status_code}") from exc
            break
        if response is None:  # defensive; loop always returns or raises
            raise SpeechProviderError("STT_PROVIDER_ERROR")
        try:
            payload = response.json()  # type: ignore[union-attr]
        except (ValueError, TypeError, AttributeError) as exc:
            raise SpeechProviderError("STT_MALFORMED_RESPONSE") from exc
        if not isinstance(payload, dict):
            raise SpeechProviderError("STT_MALFORMED_RESPONSE")
        text = str(payload.get("text", "")).strip()
        if not text:
            raise SpeechProviderError("EMPTY_TRANSCRIPT")
        words = payload.get("words", [])
        if not isinstance(words, list):
            raise SpeechProviderError("STT_MALFORMED_RESPONSE")
        confidence_values = [word.get("logprob") for word in words if isinstance(word, dict) and word.get("logprob") is not None]
        confidence = None
        if confidence_values:
            import math
            confidence = sum(math.exp(value) for value in confidence_values) / len(confidence_values)
        return TranscriptionResult(
            text=text, language=str(payload.get("language_code") or "unknown"), confidence=confidence,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
