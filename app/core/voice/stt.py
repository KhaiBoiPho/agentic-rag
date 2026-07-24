"""STT — dispatches to a local Whisper model or a RunPod Serverless GPU
endpoint depending on `settings.stt_backend`. See:
  - app/core/voice/local_whisper.py (in-process, faster-whisper)
  - app/core/voice/runpod_whisper.py (out-of-process, GPU on RunPod)
"""

from __future__ import annotations

from app.config import settings


class STTProvider:
    async def transcribe(self, audio_bytes: bytes, language: str = "vi") -> str:
        if settings.stt_backend == "runpod":
            from app.core.voice.runpod_whisper import RunpodWhisperService

            return await RunpodWhisperService().transcribe(audio_bytes, language)

        from app.core.voice.local_whisper import LocalWhisperService

        return await LocalWhisperService.get().transcribe(audio_bytes, language)
