"""Standalone Whisper STT server — run this on your own GPU machine and
tunnel it out (ngrok/cloudflared) so the deployed backend (e.g. on Railway,
which has no GPU) can reach it. Point the backend at it with:

    STT_BACKEND=http
    STT_HTTP_URL=https://<your-tunnel-domain>
    STT_HTTP_SECRET=<same value as STT_SECRET below, optional but recommended>

Run:
    pip install -r requirements.txt
    STT_SECRET=<pick something> python server.py
    # in another terminal:
    ngrok http 8001
"""

from __future__ import annotations

import io
import logging
import os

import uvicorn
from faster_whisper import WhisperModel
from fastapi import FastAPI, Form, Header, HTTPException, UploadFile
from huggingface_hub import snapshot_download

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("local-gpu-stt")

# Community CTranslate2 conversion of VinAI's PhoWhisper (Vietnamese
# fine-tune) — vinai/PhoWhisper-* itself ships in plain transformers
# format, not the CT2 format faster-whisper needs, so this pre-converted
# mirror is used instead. Repo bundles all 5 sizes as subfolders; we only
# download the one requested (not the whole multi-GB repo).
_PHOWHISPER_REPO = "quocphu/PhoWhisper-ct2-FasterWhisper"
_PHOWHISPER_SIZES = {
    "phowhisper-tiny": "PhoWhisper-tiny-ct2-fasterWhisper",
    "phowhisper-base": "PhoWhisper-base-ct2-fasterWhisper",
    "phowhisper-small": "PhoWhisper-small-ct2-fasterWhisper",
    "phowhisper-medium": "PhoWhisper-medium-ct2-fasterWhisper",
    "phowhisper-large": "PhoWhisper-large-ct2-fasterWhisper",
}


def resolve_model_path(model_size: str) -> str:
    """WHISPER_MODEL_SIZE values like "phowhisper-base" download just that
    subfolder from the CT2 mirror and return a local directory path;
    anything else (e.g. "medium", "large-v3") passes through unchanged for
    faster-whisper's normal Systran/faster-whisper-* resolution."""
    key = model_size.lower()
    if key not in _PHOWHISPER_SIZES:
        return model_size
    subfolder = _PHOWHISPER_SIZES[key]
    local_dir = snapshot_download(repo_id=_PHOWHISPER_REPO, allow_patterns=[f"{subfolder}/*"])
    return os.path.join(local_dir, subfolder)


MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "medium")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "float16")
DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
PORT = int(os.environ.get("PORT", "8001"))
SECRET = os.environ.get("STT_SECRET", "")

app = FastAPI(title="local-gpu-stt")

_model_path = resolve_model_path(MODEL_SIZE)
logger.info(
    "Loading faster-whisper model=%s (resolved=%s) device=%s compute_type=%s",
    MODEL_SIZE,
    _model_path,
    DEVICE,
    COMPUTE_TYPE,
)
_model = WhisperModel(_model_path, device=DEVICE, compute_type=COMPUTE_TYPE)
logger.info("Model loaded — ready")


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_SIZE, "device": DEVICE}


@app.post("/transcribe")
async def transcribe(
    audio: UploadFile,
    language: str = Form(""),
    x_stt_secret: str | None = Header(default=None),
):
    if SECRET and x_stt_secret != SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-STT-Secret")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    segments, info = _model.transcribe(
        io.BytesIO(audio_bytes),
        language=language or None,
        vad_filter=True,
    )
    segments = list(segments)
    text = "".join(seg.text for seg in segments).strip()
    logger.info(
        "transcribe: input_bytes=%d duration=%.1fs lang=%s(p=%.2f) chars=%d",
        len(audio_bytes),
        info.duration,
        info.language,
        info.language_probability,
        len(text),
    )
    return {"text": text}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
