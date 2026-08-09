# Whisper STT — run on your own GPU, tunnel it out

No serverless cold start, but your machine has to be on and reachable.
Good for testing/demo; a real always-on GPU host is the better fit once
this needs to be available 24/7 without your own PC being on.

## 1. Install

```bash
cd local-gpu-stt
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12   # CTranslate2's GPU backend needs these
```

## 2. Point at the CUDA libs and run

The pip-installed `nvidia-cublas-cu12`/`nvidia-cudnn-cu12` wheels aren't on
the loader path by default — export it first (same approach the main
backend's Dockerfile uses):

```bash
export LD_LIBRARY_PATH="$(python3 -c 'import nvidia.cublas, nvidia.cudnn, os; print(os.path.dirname(nvidia.cublas.__file__)+"/lib:"+os.path.dirname(nvidia.cudnn.__file__)+"/lib")'):$LD_LIBRARY_PATH"

STT_SECRET=pick-something-only-you-know python server.py
```

Default model is plain Whisper "medium". For Vietnamese, PhoWhisper
(VinAI's Vietnamese fine-tune) is usually more accurate — set
`WHISPER_MODEL_SIZE` to `phowhisper-tiny` / `phowhisper-base` /
`phowhisper-small` / `phowhisper-medium` / `phowhisper-large` to use it
instead (downloads a community CTranslate2 conversion automatically, see
`resolve_model_path()` in `server.py`). **`phowhisper-large` is the
current default here** — VinAI's published benchmark
([arXiv:2406.02555](https://arxiv.org/pdf/2406.02555)) shows medium and
large very close on paper, but real-world testing on this project found
medium still making more errors than acceptable, so large is used
despite the extra weight (1.55B params, ~3GB download, somewhat slower
inference than medium).

```bash
WHISPER_MODEL_SIZE=phowhisper-large STT_SECRET=pick-something-only-you-know python server.py
```

First run downloads+converts the model (~3GB for large) into
`~/.cache/huggingface` — subsequent runs are instant. Server listens on
`:8001`. Sanity check: `curl http://localhost:8001/health`.

### Using a LoRA fine-tune instead

A LoRA adapter (e.g. a Hugging Face repo with `adapter_config.json` +
`adapter_model.safetensors`, no full model weights) can't be loaded by
faster-whisper/CTranslate2 directly — it has no concept of an adapter, only
one merged set of weights. Merge it into its base model and convert to CT2
once with `merge_lora.py` (edit `BASE_MODEL`/`ADAPTER` at the top for a
different adapter):

```bash
pip install transformers peft accelerate
pip install torch --index-url https://download.pytorch.org/whl/cpu  # CPU is enough, this is a weight merge, not inference
python merge_lora.py
```

Produces `./phowhisper-medium-lora-ct2/`. Point `WHISPER_MODEL_SIZE` at its
absolute path — no code change needed, `resolve_model_path()` passes any
value it doesn't recognise as a `phowhisper-*` size straight through to
faster-whisper's normal local-directory resolution:

```bash
WHISPER_MODEL_SIZE="$(pwd)/phowhisper-medium-lora-ct2" STT_SECRET=... python server.py
```

## 3. Tunnel it out

```bash
ngrok http 8001
```

Copy the `https://xxxx.ngrok-free.app` URL it prints.

> Free ngrok URLs change every time you restart it — you'll need to update
> `STT_HTTP_URL` on the backend each time, or use a paid ngrok static
> domain / your own reverse-proxy setup if this needs to stay stable.

## 4. Point the deployed backend at it

On the backend's environment (Railway → `agentic-rag` → Variables):

```
STT_BACKEND=http
STT_HTTP_URL=https://xxxx.ngrok-free.app
STT_HTTP_SECRET=pick-something-only-you-know   # same value as STT_SECRET above
```

Save → backend redeploys → voice STT in the UI now round-trips to your
machine. If your machine/tunnel goes down, STT requests fail fast with a
clear "could not reach STT_HTTP_URL" error (see
`app/core/voice/http_whisper.py`) instead of hanging.
