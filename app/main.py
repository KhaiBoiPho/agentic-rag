"""Application entry point — starts the FastAPI (HTTP/SSE) app."""

from __future__ import annotations

import asyncio
import logging

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.db.postgres.base import init_db
from app.db.qdrant.client import QdrantStore
from app.monitoring.metrics import init_metrics
from app.monitoring.middleware import PrometheusMiddleware
from app.queue.consumer import start_consumer

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(),
)

# Most modules use stdlib `logging.getLogger(__name__)` (not structlog) —
# without this, the root logger defaults to WARNING and every logger.info()
# call across the app (seed.py, local_whisper.py, etc.) is silently dropped,
# which cost real debugging time this session.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

logger = structlog.get_logger()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agentic RAG",
        version="0.1.0",
        description="Monolithic RAG service with deep research, voice & MCP",
        docs_url="/docs" if settings.app_debug else None,
        redoc_url="/redoc" if settings.app_debug else None,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Prometheus request metrics
    if settings.prometheus_enabled:
        app.add_middleware(PrometheusMiddleware)
        init_metrics(app)

    # Health + metrics at root level (for Prometheus scraping)
    from app.api.health import router as health_router

    app.include_router(health_router)

    # All other API routes under /api
    app.include_router(api_router, prefix="/api")

    # MCP server (SSE) — the six construction/RAG tools, exposed for external
    # MCP clients. Three of them (rag_query, web_search, deep_research) are
    # deliberately NOT given to the chat agent (see llm/tool_loop.py), so this
    # mount is the only way anything reaches them; without it they were
    # unreachable code.
    from app.core.mcp.server import get_mcp_app

    app.mount("/mcp", get_mcp_app())

    @app.on_event("startup")
    async def on_startup():
        logger.info("startup", env=settings.app_env)

        # PostgreSQL — required
        await init_db()

        # Qdrant — optional at startup, retried lazily on first use
        try:
            await QdrantStore().ensure_collection()
            logger.info("qdrant connected")
        except Exception as exc:
            logger.warning(f"Qdrant not available at startup: {exc} — will retry on first use")

        # RabbitMQ consumer — optional, reconnects automatically
        async def _start_consumer_safe():
            try:
                await start_consumer()
            except Exception as exc:
                logger.warning(f"RabbitMQ consumer not started: {exc}")

        asyncio.create_task(_start_consumer_safe())

        # The 4 system knowledge bases (rows created by migrations
        # 0003/0007) start empty — no more automatic seed_data/ ingestion at
        # startup. They're populated by manually uploading documents through
        # the normal UI upload flow, same as any user KB — see
        # app/core/bootstrap/constants.py.

        # Local Whisper STT model — load once now instead of paying the
        # cold-load cost on the first voice request. Backgrounded since
        # model load can take a couple seconds; failure (e.g. missing
        # faster-whisper install) shouldn't crash the app, only voice.
        # Skipped entirely when STT_BACKEND=http — no local model, no GPU
        # needed on this host, transcription happens on a remote GPU box
        # instead (see app/core/voice/http_whisper.py, local-gpu-stt/).
        if settings.stt_backend == "local":

            async def _load_whisper_safe():
                from app.core.voice.local_whisper import LocalWhisperService

                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None, LocalWhisperService.get().load
                    )
                    logger.info("local Whisper STT model ready")
                except Exception as exc:
                    logger.warning(
                        f"Local Whisper model failed to load: {exc} — voice STT unavailable"
                    )

            asyncio.create_task(_load_whisper_safe())
        else:
            logger.info(f"STT_BACKEND={settings.stt_backend} — skipping local Whisper model load")

        logger.info("startup complete")

    @app.on_event("shutdown")
    async def on_shutdown():
        logger.info("shutdown")

    return app


app = create_app()


if __name__ == "__main__":
    import os

    # Railway (and most PaaS hosts) inject PORT at deploy time and route the
    # public domain to it, independent of whatever APP_PORT is set to — a
    # container listening on APP_PORT while the platform proxies to PORT is
    # reachable inside the private network but 502s on the public domain.
    port = int(os.environ.get("PORT", settings.app_port))
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=port,
        reload=settings.app_debug,
        log_level="info",
    )
