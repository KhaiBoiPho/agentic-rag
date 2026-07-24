"""TTS Provider — streams audio bytes back to caller via OpenRouter's
OpenAI-compatible /audio/speech endpoint (see OpenRouterClient.tts_stream)."""
from __future__ import annotations

from typing import AsyncGenerator

from app.core.llm.openrouter import OpenRouterClient


class TTSProvider:
    async def stream(self, text: str, voice: str = "alloy") -> AsyncGenerator[bytes, None]:
        client = OpenRouterClient()
        async for chunk in client.tts_stream(text, voice=voice):
            yield chunk
