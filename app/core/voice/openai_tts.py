"""TTS via OpenAI's real /v1/audio/speech endpoint (called directly, not
through OpenRouter — OpenRouter has no genuine TTS endpoint, see the
removed OpenRouterClient.tts_stream for why that approach was unreliable:
it used a conversational audio-chat model that could "reply" instead of
reading the given text verbatim).

This endpoint takes text and returns exactly that text as audio — no
chat framing, no risk of the model generating an unrelated response.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class OpenAITTSService:
    async def stream(self, text: str, voice: str = "alloy") -> AsyncGenerator[bytes, None]:
        if not settings.openai_api_key:
            logger.warning("OPENAI_API_KEY not set — cannot synthesize speech")
            return

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.openai_tts_base_url}/audio/speech",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_tts_model,
                    "input": text,
                    "voice": voice,
                    "response_format": "wav",
                },
            )
            resp.raise_for_status()
            yield resp.content
