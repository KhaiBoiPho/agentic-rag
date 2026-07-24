"""STT via a plain HTTP server you run yourself on a GPU machine (see
local-gpu-stt/), reachable through a tunnel (ngrok or similar). Same
interface as LocalWhisperService/RunpodWhisperService
(`transcribe(audio_bytes, language) -> str`) so STTProvider can switch
between backends via `settings.stt_backend` with no other code changes.

Avoids RunPod's serverless cold-start entirely — the tradeoff is the GPU
box has to be powered on and reachable for STT to work at all.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT_S = 60.0


class HttpWhisperError(RuntimeError):
    pass


class HttpWhisperService:
    def __init__(self) -> None:
        if not settings.stt_http_url:
            raise RuntimeError("STT_HTTP_URL must be set when STT_BACKEND=http")
        self._url = settings.stt_http_url.rstrip("/") + "/transcribe"
        self._headers = {}
        if settings.stt_http_secret:
            self._headers["X-STT-Secret"] = settings.stt_http_secret

    async def transcribe(self, audio_bytes: bytes, language: str = "vi") -> str:
        files = {"audio": ("audio.webm", audio_bytes, "application/octet-stream")}
        data = {"language": language or ""}
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            try:
                resp = await client.post(self._url, headers=self._headers, files=files, data=data)
            except httpx.TransportError as exc:
                raise HttpWhisperError(
                    f"Could not reach STT_HTTP_URL ({self._url}) — is the local GPU "
                    f"server + tunnel still up? {exc}"
                ) from exc
            resp.raise_for_status()
            payload = resp.json()

        text = payload.get("text", "")
        logger.info("http whisper transcribe: input_bytes=%d chars=%d", len(audio_bytes), len(text))
        return text.strip()
