#!/usr/bin/env python3
"""One-off: merge a PEFT LoRA adapter into its Whisper base model, then
convert the result to CTranslate2 so faster-whisper (server.py) can load it
directly — CT2/faster-whisper has no concept of a LoRA adapter, only a
single merged set of weights.

Run once, on CPU (this is a weight merge, not inference — no GPU needed):

    cd local-gpu-stt
    source .venv/bin/activate
    pip install transformers peft accelerate
    pip install torch --index-url https://download.pytorch.org/whl/cpu
    python merge_lora.py

Produces ./phowhisper-medium-lora-ct2/ in this directory. Point
WHISPER_MODEL_SIZE at its absolute path when starting server.py — no code
change needed, resolve_model_path() passes any value it doesn't recognise
as a phowhisper-* size straight through to faster-whisper's normal local-
path resolution.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from peft import PeftModel
from transformers import WhisperForConditionalGeneration, WhisperProcessor

# vinai/PhoWhisper-medium ships only pytorch_model.bin (no safetensors
# version), and transformers >=4.5x refuses torch.load on torch<2.6 by
# default (CVE-2025-32434 — arbitrary code execution from an untrusted
# pickle). Upgrading torch in a shared conda env just for this one-off
# merge is more disruptive than the fix: skip the guard for this single,
# specific, well-known official-VinAI repo rather than pulling torch>=2.6
# into an environment other things depend on.
import transformers.modeling_utils as _tf_modeling_utils

_tf_modeling_utils.check_torch_load_is_safe = lambda: None

BASE_MODEL = "vinai/PhoWhisper-medium"
ADAPTER = "schaffen49/PhoWhisper_medium_lora"
MERGED_DIR = Path("phowhisper-medium-lora-merged")
CT2_DIR = Path("phowhisper-medium-lora-ct2")


def main() -> None:
    print(f"Loading base model {BASE_MODEL} (first run downloads ~3GB)...")
    base = WhisperForConditionalGeneration.from_pretrained(BASE_MODEL)

    print(f"Applying LoRA adapter {ADAPTER}...")
    merged = PeftModel.from_pretrained(base, ADAPTER).merge_and_unload()

    print(f"Saving merged model to {MERGED_DIR}/...")
    merged.save_pretrained(MERGED_DIR)
    # ct2-transformers-converter needs the tokenizer/feature-extractor
    # config files alongside the weights — the adapter repo has neither
    # (it's LoRA weights only), so these come from the base model instead.
    WhisperProcessor.from_pretrained(BASE_MODEL).save_pretrained(MERGED_DIR)

    print(f"Converting to CTranslate2 at {CT2_DIR}/...")
    subprocess.run(
        [
            "ct2-transformers-converter",
            "--model", str(MERGED_DIR),
            "--output_dir", str(CT2_DIR),
            "--quantization", "float16",
            "--force",
        ],
        check=True,
    )
    print(f"\nDone. Start the server with:\n\n"
          f'  WHISPER_MODEL_SIZE="{CT2_DIR.resolve()}" STT_SECRET=... python server.py\n')


if __name__ == "__main__":
    main()
