# Whisper STT — RunPod Serverless

GPU-backed speech-to-text (faster-whisper "medium", the same engine as the
former in-process `WHISPER_DEVICE=cuda` setup) packaged as a RunPod
Serverless endpoint. Use this when the main backend runs somewhere without a
GPU (e.g. Railway) — set `STT_BACKEND=runpod` on the backend and it calls out
here instead of loading a local model (see `app/core/voice/runpod_whisper.py`).

## Why serverless instead of an always-on GPU pod

Voice STT is bursty (record-then-send, not continuous streaming) — a
serverless GPU endpoint scales to zero between requests and you only pay for
the seconds actually spent transcribing, instead of renting a GPU pod
24/7. Cold starts are the tradeoff; the Dockerfile bakes the model weights
into the image to keep that as small as possible (see the Dockerfile's
comment).

## 1. Build & push the image

```bash
cd runpod/whisper-stt
docker build -t <your-registry>/agentic-rag-whisper-stt:latest .
docker push <your-registry>/agentic-rag-whisper-stt:latest
```

Any registry RunPod can pull from works — Docker Hub, GHCR, etc. If using
GHCR, make the package public or add registry credentials in the RunPod
endpoint settings.

## 2. Create the RunPod Serverless endpoint

In the [RunPod console](https://www.runpod.io/console/serverless):

1. **New Endpoint** → **Import from Docker Registry** → point it at the
   image pushed above.
2. **GPU**: pick a tier with ≥ 8GB VRAM (medium model + CUDA runtime fits
   comfortably on a 16GB card; smaller cards may work but leave less
   headroom for concurrent requests per worker). RunPod's cheapest available
   tier that satisfies this is usually fine for this workload.
3. **Workers**: min workers `0` (scale-to-zero, matches the bursty usage
   pattern above), max workers per your expected concurrent voice traffic.
4. **Container Disk**: ≥ 10GB (image + baked-in model weights).
5. No environment variables are required — `WHISPER_MODEL_SIZE` /
   `WHISPER_COMPUTE_TYPE` default to `medium` / `float16` in the Dockerfile;
   override them in the endpoint's env vars only if you want a different
   model size.
6. Deploy, then copy the **Endpoint ID** shown in the console.

## 3. Wire it into the backend

On the backend service (see `docs/railway-deploy.md` for the Railway case):

```
STT_BACKEND=runpod
RUNPOD_API_KEY=<RunPod API key, from Settings → API Keys>
RUNPOD_STT_ENDPOINT_ID=<the Endpoint ID from step 2>
```

With `STT_BACKEND=runpod`, the backend skips loading any local Whisper model
at startup entirely (no GPU/CUDA needed on that host) and
`app/core/voice/runpod_whisper.py` calls this endpoint's `/runsync` for each
`/api/v1/voice/stt` request, falling back to polling `/status` if a cold
start pushes the job past RunPod's synchronous-wait window.

## Local testing

```bash
cd runpod/whisper-stt
pip install -r requirements.txt
```

Replace `audio_base64` in `test_input.json` with a real sample, e.g.:

```bash
python3 -c "import base64; print(base64.b64encode(open('sample.wav','rb').read()).decode())"
```

then run (needs a local GPU + CUDA to actually execute `handler.py` as
written — device is hardcoded to `cuda`; for a CPU-only sanity check of the
handler logic, temporarily edit `device='cuda'` to `device='cpu'`):

```bash
python3 handler.py
```

The RunPod SDK detects `test_input.json` in the working directory and runs
the handler against it once instead of starting the serverless worker loop.
