"""OpenRouter client — streaming chat + embeddings.

OpenRouter is OpenAI-API compatible, so we use the openai SDK pointed at
the OpenRouter base URL. HTTP chunks from /chat/completions SSE are
re-yielded as async generator tokens — the gRPC servicer then wraps those
into gRPC server-stream messages.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

import httpx
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.monitoring.metrics import LLM_REQUEST_LATENCY, LLM_TOKEN_COUNT

logger = logging.getLogger(__name__)

_HEADERS = {
    "HTTP-Referer": "https://agentic-rag.local",
    "X-Title": "Agentic RAG",
}


class OpenRouterClient:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers=_HEADERS,
        )

    # ─── Streaming chat ───────────────────────────────────────────────────────

    async def stream_chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Yield token strings from OpenRouter SSE stream."""
        import time

        model = model or settings.openrouter_chat_model
        t0 = time.perf_counter()
        total_tokens = 0

        stream = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                total_tokens += 1
                yield delta

        LLM_TOKEN_COUNT.labels(model=model, direction="output").inc(total_tokens)
        LLM_REQUEST_LATENCY.labels(model=model).observe(time.perf_counter() - t0)

    # ─── Non-streaming chat (for research nodes) ─────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        model = model or settings.openrouter_research_model
        resp = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    # ─── Tool-calling chat (agent mode) ──────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        """OpenAI-style tool calling. Returns the raw response message so the
        caller can inspect `.tool_calls` (list of {id, function.name,
        function.arguments}) vs `.content` — kept separate from `chat()`
        (which always returns plain text) so existing callers are untouched.
        """
        model = model or settings.openrouter_research_model
        resp = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice="auto",
        )
        return resp.choices[0].message

    # ─── Embeddings ──────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return list of embedding vectors (one per input text).

        Falls back to zero-vectors if the configured model does not support
        the /embeddings endpoint (e.g. chat-only models on OpenRouter).
        """
        try:
            resp = await self._client.embeddings.create(
                model=settings.openrouter_embed_model,
                input=texts,
            )
            return [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]
        except Exception as exc:
            logger.error(
                "Embedding failed (model=%s): %s — check OPENROUTER_EMBED_MODEL in .env. "
                "Supported models: openai/text-embedding-3-small, openai/text-embedding-3-large",
                settings.openrouter_embed_model,
                exc,
            )
            raise ValueError(
                f"Embedding model '{settings.openrouter_embed_model}' not supported. "
                "Set OPENROUTER_EMBED_MODEL=openai/text-embedding-3-small in .env"
            ) from exc

    async def embed_batch(
        self, texts: list[str], batch_size: int | None = None
    ) -> list[list[float]]:
        batch_size = batch_size or settings.embed_batch_size
        result: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            result.extend(await self.embed(batch))
        return result

    # ─── Vision OCR (scanned/image-only PDF pages) ───────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def vision_ocr(self, image_b64: str, model: str | None = None) -> str:
        """Transcribe a page image to plain text via an OpenRouter vision model.

        Used as a fallback when PyMuPDF/pdfplumber extract no text/tables from
        a PDF page (scanned image with no text layer)."""
        model = model or settings.openrouter_vision_model
        resp = await self._client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Transcribe all readable text from this document page "
                                "image exactly as it appears, preserving table structure "
                                "as plain rows/columns where present. Output only the "
                                "transcribed text, no commentary. If the page has no "
                                "readable text, output nothing."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        },
                    ],
                }
            ],
            temperature=0.0,
            max_tokens=4096,
        )
        return (resp.choices[0].message.content or "").strip()

    # ─── TTS via OpenRouter ───────────────────────────────────────────────────
    #
    # OpenRouter has no plain /audio/speech TTS endpoint (that returns 400
    # "Model ... does not exist" for every model tried) — audio output is
    # only available through /chat/completions with modalities=["text",
    # "audio"], and only when stream=true, and only in raw PCM16 (mp3/wav
    # output formats are rejected with "does not support 'mp3' when
    # stream=true. Supported values are: 'pcm16'"). So: stream chat deltas,
    # collect the base64 PCM16 chunks from delta.audio.data, and wrap the
    # concatenated PCM in a WAV header ourselves — the OpenAI audio models
    # (gpt-audio / gpt-audio-mini) render at 24kHz mono 16-bit.
    _PCM_SAMPLE_RATE = 24000
    _PCM_CHANNELS = 1
    _PCM_BITS = 16

    def _wav_header(self, pcm_byte_len: int) -> bytes:
        import struct

        byte_rate = self._PCM_SAMPLE_RATE * self._PCM_CHANNELS * self._PCM_BITS // 8
        block_align = self._PCM_CHANNELS * self._PCM_BITS // 8
        return (
            b"RIFF"
            + struct.pack("<I", 36 + pcm_byte_len)
            + b"WAVE"
            + b"fmt "
            + struct.pack(
                "<IHHIIHH",
                16,
                1,
                self._PCM_CHANNELS,
                self._PCM_SAMPLE_RATE,
                byte_rate,
                block_align,
                self._PCM_BITS,
            )
            + b"data"
            + struct.pack("<I", pcm_byte_len)
        )

    async def tts_stream(self, text: str, voice: str = "alloy") -> AsyncGenerator[bytes, None]:
        """Yield one complete WAV file's bytes (not per-chunk audio — the
        underlying PCM stream must be fully collected before a valid WAV
        header, which needs the total byte length, can be written)."""
        import base64
        import json

        pcm_chunks: list[bytes] = []
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{settings.openrouter_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                    **_HEADERS,
                },
                json={
                    "model": settings.openrouter_tts_model,
                    "modalities": ["text", "audio"],
                    "audio": {"voice": voice, "format": "pcm16"},
                    "stream": True,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Đọc chính xác nguyên văn nội dung người dùng gửi bằng giọng đọc "
                                "tự nhiên tiếng Việt. Không thêm bớt, không bình luận, không trả "
                                "lời như một cuộc hội thoại — chỉ đọc lại đúng nguyên văn."
                            ),
                        },
                        {"role": "user", "content": text},
                    ],
                },
                timeout=60,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[len("data: ") :]
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        audio = chunk["choices"][0]["delta"].get("audio")
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue
                    if audio and audio.get("data"):
                        pcm_chunks.append(base64.b64decode(audio["data"]))

        pcm = b"".join(pcm_chunks)
        if not pcm:
            logger.warning("OpenRouter TTS returned no audio data for text=%r", text[:80])
            return
        yield self._wav_header(len(pcm)) + pcm
