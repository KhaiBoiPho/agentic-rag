FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    WHISPER_MODEL_SIZE=medium \
    WHISPER_COMPUTE_TYPE=float16 \
    HF_HOME=/models

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Bake the model weights into the image so cold starts don't pay a
# multi-hundred-MB download on every scale-from-zero — this is the single
# biggest cold-start latency win for serverless GPU inference. Runs on CPU
# at build time (no GPU available in the build environment); the CT2 weight
# files it downloads are compute-device-agnostic, so runtime device=cuda
# reuses this same cache.
RUN python3 -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL_SIZE}', device='cpu', compute_type='int8')"

COPY handler.py .

CMD ["python3", "-u", "handler.py"]
