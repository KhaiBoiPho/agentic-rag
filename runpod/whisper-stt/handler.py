"""RunPod Serverless handler — Whisper "medium" STT on GPU (faster-whisper).

Mirrors app/core/voice/local_whisper.py's transcription logic (same VAD
filter, same output shape) so switching STT_BACKEND between "local" and
"runpod" in the main backend doesn't change behavior, just where inference
runs.

Input  (event["input"]):
    audio_base64: str   — required, raw audio bytes (webm/wav/mp3), base64-encoded
    language:     str   — optional, e.g. "vi"; omit/null for auto-detect

Output:
    {"text": "..."}                on success
    {"error": "<message>"}         on failure (RunPod surfaces this as job error)
"""

from __future__ import annotations

import base64
import io
import logging
import os

import runpod
from faster_whisper import WhisperModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whisper-stt-handler")

MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "medium")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "float16")

logger.info("Loading faster-whisper model=%s compute_type=%s device=cuda", MODEL_SIZE, COMPUTE_TYPE)
# Loaded once per worker process at cold start, reused across every
# invocation for the life of the worker (RunPod keeps workers warm between
# jobs up to the endpoint's idle timeout).
_model = WhisperModel(MODEL_SIZE, device="cuda", compute_type=COMPUTE_TYPE)
logger.info("Model loaded — worker ready")


def handler(event: dict) -> dict:
    job_input = event.get("input") or {}
    audio_b64 = job_input.get("audio_base64")
    if not audio_b64:
        return {"error": "Missing required field: input.audio_base64"}

    language = job_input.get("language") or None

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception as exc:
        return {"error": f"Invalid base64 audio: {exc}"}

    try:
        segments, info = _model.transcribe(
            io.BytesIO(audio_bytes),
            language=language,
            vad_filter=True,
        )
        segments = list(segments)
        text = "".join(seg.text for seg in segments).strip()
        logger.info(
            "transcribe: input_bytes=%d duration=%.1fs lang=%s(p=%.2f) segments=%d chars=%d",
            len(audio_bytes),
            info.duration,
            info.language,
            info.language_probability,
            len(segments),
            len(text),
        )
        return {"text": text}
    except Exception as exc:
        logger.exception("transcription failed")
        return {"error": str(exc)}


runpod.serverless.start({"handler": handler})
