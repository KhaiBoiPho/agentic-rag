"""STT — dispatches to a local Whisper model or a self-hosted HTTP GPU
server, depending on `settings.stt_backend`. See:
  - app/core/voice/local_whisper.py (in-process, faster-whisper)
  - app/core/voice/http_whisper.py   (out-of-process, your own GPU box)
"""

from __future__ import annotations

from app.config import settings


class STTProvider:
    async def transcribe(self, audio_bytes: bytes, language: str = "vi") -> str:
        if settings.stt_backend == "http":
            from app.core.voice.http_whisper import HttpWhisperService

            return await HttpWhisperService().transcribe(audio_bytes, language)

        from app.core.voice.local_whisper import LocalWhisperService

        return await LocalWhisperService.get().transcribe(audio_bytes, language)
