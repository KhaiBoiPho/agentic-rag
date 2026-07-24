"""STT — local Whisper only (no RunPod serverless, no external API).

See app/core/voice/local_whisper.py for the model loading/inference
details and why "base" on CPU is the right default for this project.
"""
from __future__ import annotations

from app.core.voice.local_whisper import LocalWhisperService


class STTProvider:
    async def transcribe(self, audio_bytes: bytes, language: str = "vi") -> str:
        return await LocalWhisperService.get().transcribe(audio_bytes, language)
