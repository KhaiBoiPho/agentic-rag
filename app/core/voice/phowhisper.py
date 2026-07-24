"""Resolves WHISPER_MODEL_SIZE values like "phowhisper-base" to a local
CTranslate2 model directory, downloaded from the community CT2 mirror of
VinAI's PhoWhisper (Vietnamese Whisper fine-tune). vinai/PhoWhisper-* itself
ships in plain transformers format, not the CT2 format faster-whisper
needs, so this pre-converted mirror is used instead.
"""

from __future__ import annotations

import os

_PHOWHISPER_REPO = "quocphu/PhoWhisper-ct2-FasterWhisper"
_PHOWHISPER_SIZES = {
    "phowhisper-tiny": "PhoWhisper-tiny-ct2-fasterWhisper",
    "phowhisper-base": "PhoWhisper-base-ct2-fasterWhisper",
    "phowhisper-small": "PhoWhisper-small-ct2-fasterWhisper",
    "phowhisper-medium": "PhoWhisper-medium-ct2-fasterWhisper",
    "phowhisper-large": "PhoWhisper-large-ct2-fasterWhisper",
}


def resolve_model_path(model_size: str) -> str:
    """Values like "phowhisper-base" download just that subfolder (not the
    whole multi-GB repo) and return a local directory path; anything else
    (e.g. "medium", "large-v3") passes through unchanged for faster-whisper's
    normal Systran/faster-whisper-* resolution."""
    key = model_size.lower()
    if key not in _PHOWHISPER_SIZES:
        return model_size

    from huggingface_hub import snapshot_download

    subfolder = _PHOWHISPER_SIZES[key]
    local_dir = snapshot_download(repo_id=_PHOWHISPER_REPO, allow_patterns=[f"{subfolder}/*"])
    return os.path.join(local_dir, subfolder)
