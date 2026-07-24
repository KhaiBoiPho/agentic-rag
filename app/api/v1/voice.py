"""Voice endpoints — STT (local Whisper) + TTS (OpenRouter) streaming."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.core.voice.stt import STTProvider
from app.core.voice.tts import TTSProvider

router = APIRouter()
_tts = TTSProvider()


class TTSRequest(BaseModel):
    text: str
    voice: str = "alloy"


@router.post("/tts/stream")
async def tts_stream(body: TTSRequest, current_user: CurrentUser):
    """Stream TTS audio bytes (MP3) via OpenRouter."""
    async def audio_gen():
        async for chunk in _tts.stream(text=body.text, voice=body.voice):
            yield chunk

    return StreamingResponse(audio_gen(), media_type="audio/wav")


@router.post("/stt")
async def transcribe_audio(
    audio: UploadFile,
    current_user: CurrentUser,
    language: str = "vi",
):
    """Transcribe an uploaded audio file to text (WAV/MP3/WebM accepted)."""
    content = await audio.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio file")
    stt = STTProvider()
    text = await stt.transcribe(content, language)
    return {"text": text}
