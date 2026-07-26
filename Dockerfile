FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev curl bash \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (cached layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# faster-whisper on GPU (WHISPER_DEVICE=cuda) needs CUDA/cuDNN shared libs at
# runtime. Rather than switching to a full nvidia/cuda base image, point
# LD_LIBRARY_PATH at the pip-installed nvidia-cublas-cu12/nvidia-cudnn-cu12
# wheels (see pyproject.toml) — CPU-only deployments (WHISPER_DEVICE=cpu)
# ignore this, the libs just sit unused.
ENV LD_LIBRARY_PATH="/usr/local/lib/python3.11/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.11/site-packages/nvidia/cudnn/lib:${LD_LIBRARY_PATH}"

# Copy application source
COPY . .

EXPOSE 8000

CMD ["python", "-m", "app.main"]
