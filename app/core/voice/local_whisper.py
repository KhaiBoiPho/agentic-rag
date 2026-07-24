"""Local Whisper STT — self-hosted (faster-whisper/CTranslate2), no
serverless/API dependency (replaces the former RunPod-based STTProvider).

Whisper "base" (~74M params) is deliberately used un-fine-tuned for now —
per project decision, the fine-tuned model isn't ready yet. On CPU with
int8 quantization it transcribes a few seconds of audio in roughly the same
order of magnitude of wall-clock time (a 10s clip: ~1-3s), which is fine for
a record-then-send flow (not live streaming). Switch to GPU later by
setting WHISPER_DEVICE=cuda + WHISPER_COMPUTE_TYPE=float16 — no code change
needed, only .env and running on a CUDA-capable host.
"""

from __future__ import annotations

import asyncio
import io
import logging

logger = logging.getLogger(__name__)


class LocalWhisperService:
    """Singleton — model is loaded once and reused across requests."""

    _instance: LocalWhisperService | None = None

    def __init__(self) -> None:
        self._model = None
        self._ready = False

    @classmethod
    def get(cls) -> LocalWhisperService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self) -> None:
        """Load the model synchronously — call once at startup in a thread."""
        from faster_whisper import WhisperModel

        from app.config import settings

        logger.info(
            "Loading local Whisper model=%s device=%s compute_type=%s",
            settings.whisper_model_size,
            settings.whisper_device,
            settings.whisper_compute_type,
        )
        self._model = WhisperModel(
            settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        self._ready = True
        logger.info("Local Whisper model loaded and ready")

    @property
    def is_ready(self) -> bool:
        return self._ready

    def _transcribe_sync(self, audio_bytes: bytes, language: str) -> str:
        segments, info = self._model.transcribe(
            io.BytesIO(audio_bytes),
            language=language or None,
            vad_filter=True,  # skip silence — fewer hallucinated segments on quiet audio
        )
        segments = list(segments)
        text = "".join(seg.text for seg in segments).strip()
        logger.info(
            "whisper transcribe: input_bytes=%d duration=%.1fs "
            "lang=%s(p=%.2f) segments=%d chars=%d",
            len(audio_bytes),
            info.duration,
            info.language,
            info.language_probability,
            len(segments),
            len(text),
        )
        return text

    async def transcribe(self, audio_bytes: bytes, language: str = "vi") -> str:
        if self._model is None:
            raise RuntimeError("Whisper model not loaded — call load() first")
        loop = asyncio.get_event_loop()
        # CPU-bound inference — run in the default executor so it doesn't
        # block the event loop for the several seconds a clip can take.
        return await loop.run_in_executor(None, self._transcribe_sync, audio_bytes, language)
