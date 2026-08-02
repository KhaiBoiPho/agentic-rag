"""Application settings — loaded from environment / .env file."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── App ─────────────────────────────────────────────────────────────────
    app_env: Literal["development", "production", "test"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False
    secret_key: str = "change-me"

    # ─── PostgreSQL ──────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://agentic:agentic_secret@localhost:5432/agentic_rag"

    # ─── Qdrant ──────────────────────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str = ""
    qdrant_https: bool = False  # True for Qdrant Cloud (requires TLS)
    qdrant_collection_name: str = "agentic_rag_chunks"

    # ─── RabbitMQ ────────────────────────────────────────────────────────────
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # ─── Auth ────────────────────────────────────────────────────────────────
    jwt_secret_key: str = "change-me-jwt"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/oauth/google/callback"

    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/api/v1/auth/oauth/github/callback"

    # ─── OpenRouter ──────────────────────────────────────────────────────────
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_chat_model: str = "anthropic/claude-3.5-sonnet"
    openrouter_embed_model: str = "openai/text-embedding-3-small"
    openrouter_research_model: str = "google/gemini-2.0-flash-exp:free"
    # Cheap/fast model for the off-topic classifier (app/core/chat/topic_guard.py)
    # — deliberately independent of openrouter_chat_model / the user's selected
    # model, so an off-topic question gets intercepted before ever reaching
    # whatever (possibly premium-tier) model the user picked for real answers.
    openrouter_classifier_model: str = "openai/gpt-4o-mini"
    # Vision-capable model for OCR fallback on scanned/image-only PDF pages
    # (normal text/table extraction yields nothing for these).
    # Two vision passes per scanned page (see ocr_fallback):
    #
    #   *_vision_table_model — asks for HTML table markup.
    #   *_vision_model       — plain-text pass, used ONLY to corroborate the
    #                          numbers in the structured output.
    #
    # They must stay DIFFERENT vendors: a model can invent a cell to make a
    # row come out even, and a second opinion from the same model repeats the
    # same invention.
    #
    # Measured on the Vicem Hà Tiên scan (19-column, multi-level header,
    # column-wide merged unit), scoring extracted rows against the printed
    # page: gemini-2.5-flash 15/15 prices correct, claude-opus-4.5 15/15,
    # gpt-4o 14/15 (misread 1.356.481 as 1.436.481 — a wrong price, the worst
    # failure mode). Flash matches Opus here at 1/10 the cost, so Opus buys
    # nothing measurable on this corpus.
    #
    # Cross-check recall on the same page: haiku-4.5 16/16 numbers, flash
    # 16/16, gpt-4o-mini 15/16 — a checker that misses a real number blanks a
    # valid price, so 16/16 is the bar.
    openrouter_vision_model: str = "anthropic/claude-haiku-4.5"
    openrouter_vision_table_model: str = "google/gemini-2.5-flash"

    # ─── OpenAI (TTS only — direct, not via OpenRouter) ───────────────────────
    # OpenRouter has no genuine /audio/speech endpoint (see
    # app/core/voice/openai_tts.py) — real TTS needs an actual OpenAI key.
    # STT stays on PhoWhisper (below), not OpenAI — a different model choice
    # for a different reason (Vietnamese-tuned accuracy, no per-request cost).
    openai_api_key: str = ""
    openai_tts_base_url: str = "https://api.openai.com/v1"
    openai_tts_model: str = "tts-1"

    # ─── STT ─────────────────────────────────────────────────────────────────
    # "local" loads faster-whisper in-process, running PhoWhisper (VinAI's
    # Vietnamese Whisper fine-tune, see app/core/voice/phowhisper.py) —
    # needs a CUDA host for anything bigger than "base"/"small" at usable
    # latency, but has no external dependency to keep alive. "http" calls a
    # plain HTTP server you run yourself on a GPU box (see local-gpu-stt/),
    # tunneled in via ngrok or similar — the way to get GPU PhoWhisper on a
    # host with no GPU of its own (e.g. Railway), no cold start, but the box
    # and the tunnel both have to stay up (a real failure mode mid-demo if
    # either drops).
    stt_backend: Literal["local", "http"] = "local"

    whisper_model_size: str = "base"
    whisper_device: Literal["cpu", "cuda"] = "cpu"
    whisper_compute_type: str = "int8"  # int8 for CPU; float16 recommended on GPU

    stt_http_url: str = ""  # e.g. https://xxxx.ngrok-free.app
    stt_http_secret: str = ""  # sent as X-STT-Secret, checked by local-gpu-stt/server.py

    # ─── Firecrawl ───────────────────────────────────────────────────────────
    firecrawl_api_key: str = ""
    firecrawl_base_url: str = "https://api.firecrawl.dev"

    # ─── Deep Research ───────────────────────────────────────────────────────
    research_max_iterations: int = 3
    research_max_search_results: int = 10
    research_quality_threshold: float = 0.75

    # ─── Chunking ────────────────────────────────────────────────────────────
    chunk_token_num: int = 512
    chunk_overlap_percent: int = 15
    table_context_size: int = 128
    chunk_delimiter: str = "\n!?。；！？"

    # ─── Embedding ───────────────────────────────────────────────────────────
    embed_batch_size: int = 32
    embed_dim: int = 1536

    # ─── Monitoring ──────────────────────────────────────────────────────────
    prometheus_enabled: bool = True
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    # ─── CORS ────────────────────────────────────────────────────────────────
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173", "http://localhost:3210"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
