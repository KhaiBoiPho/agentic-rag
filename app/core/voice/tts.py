"""TTS Provider — streams audio bytes back to caller via OpenAI's real
/audio/speech endpoint (see OpenAITTSService)."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from app.core.voice.openai_tts import OpenAITTSService


class TTSProvider:
    async def stream(self, text: str, voice: str = "alloy") -> AsyncGenerator[bytes, None]:
        client = OpenAITTSService()
        async for chunk in client.stream(text, voice=voice):
            yield chunk
