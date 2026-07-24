"""STT via a RunPod Serverless GPU endpoint (see runpod/whisper-stt/) —
the GPU-backed replacement for LocalWhisperService when the app itself runs
on a host with no GPU (e.g. Railway). Same interface as LocalWhisperService
(`transcribe(audio_bytes, language) -> str`) so STTProvider can switch
between them via `settings.stt_backend` with no other code changes.
"""

from __future__ import annotations

import asyncio
import base64
import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)

# RunPod's /runsync blocks server-side for a limited window (policy default
# ~90s) before returning IN_QUEUE/IN_PROGRESS instead of the final result —
# a cold worker start (model load) plus a slow request can exceed that, so
# we fall back to polling /status for jobs that don't finish synchronously.
_RUNSYNC_TIMEOUT_S = 100.0
_POLL_INTERVAL_S = 2.0
_POLL_TIMEOUT_S = 180.0


class RunpodTranscriptionError(RuntimeError):
    pass


class RunpodWhisperService:
    def __init__(self) -> None:
        if not settings.runpod_api_key or not settings.runpod_stt_endpoint_id:
            raise RuntimeError(
                "RUNPOD_API_KEY / RUNPOD_STT_ENDPOINT_ID must be set when STT_BACKEND=runpod"
            )
        self._base_url = f"{settings.runpod_base_url}/{settings.runpod_stt_endpoint_id}"
        self._headers = {
            "Authorization": f"Bearer {settings.runpod_api_key}",
            "Content-Type": "application/json",
        }

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
    )
    async def _runsync(self, client: httpx.AsyncClient, payload: dict) -> dict:
        resp = await client.post(f"{self._base_url}/runsync", headers=self._headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def _poll_until_done(self, client: httpx.AsyncClient, job_id: str) -> dict:
        elapsed = 0.0
        while elapsed < _POLL_TIMEOUT_S:
            await asyncio.sleep(_POLL_INTERVAL_S)
            elapsed += _POLL_INTERVAL_S
            resp = await client.get(f"{self._base_url}/status/{job_id}", headers=self._headers)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") in ("COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"):
                return data
        raise RunpodTranscriptionError(
            f"RunPod job {job_id} did not finish within {_POLL_TIMEOUT_S}s"
        )

    async def transcribe(self, audio_bytes: bytes, language: str = "vi") -> str:
        payload = {
            "input": {
                "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
                "language": language or None,
            }
        }
        async with httpx.AsyncClient(timeout=_RUNSYNC_TIMEOUT_S) as client:
            data = await self._runsync(client, payload)
            if data.get("status") in ("IN_QUEUE", "IN_PROGRESS"):
                logger.info(
                    "RunPod STT job %s still running past runsync window — polling", data.get("id")
                )
                data = await self._poll_until_done(client, data["id"])

        if data.get("status") != "COMPLETED":
            raise RunpodTranscriptionError(
                f"RunPod STT job failed: status={data.get('status')} error={data.get('error')}"
            )

        output = data.get("output") or {}
        text = output.get("text", "")
        logger.info(
            "runpod whisper transcribe: input_bytes=%d chars=%d",
            len(audio_bytes),
            len(text),
        )
        return text.strip()
