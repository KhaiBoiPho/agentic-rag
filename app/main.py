"""Application entry point — starts FastAPI (HTTP) + gRPC concurrently."""

from __future__ import annotations

import asyncio
import logging

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.core.bootstrap.seed import seed_system_kb_documents
from app.db.postgres.base import init_db
from app.db.qdrant.client import QdrantStore
from app.grpc_server.server import serve as grpc_serve
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
        description="Monolithic RAG service with gRPC streaming, deep research, voice & MCP",
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

        # System knowledge bases (Kiến thức xây dựng / Dự toán giá nhà) —
        # ingests seed_data/ once (gated on document_count == 0), see
        # app/core/bootstrap/seed.py. Backgrounded since it can take minutes.
        async def _seed_system_kbs_safe():
            try:
                await seed_system_kb_documents()
            except Exception as exc:
                logger.warning(f"System KB seeding failed: {exc}")

        asyncio.create_task(_seed_system_kbs_safe())

        # Local Whisper STT model — load once now instead of paying the
        # cold-load cost on the first voice request. Backgrounded since
        # model load can take a couple seconds; failure (e.g. missing
        # faster-whisper install) shouldn't crash the app, only voice.
        async def _load_whisper_safe():
            from app.core.voice.local_whisper import LocalWhisperService

            try:
                await asyncio.get_event_loop().run_in_executor(None, LocalWhisperService.get().load)
                logger.info("local Whisper STT model ready")
            except Exception as exc:
                logger.warning(f"Local Whisper model failed to load: {exc} — voice STT unavailable")

        asyncio.create_task(_load_whisper_safe())

        # gRPC server
        async def _start_grpc_safe():
            try:
                await grpc_serve(settings.grpc_host, settings.grpc_port)
            except Exception as exc:
                logger.warning(f"gRPC server error: {exc}")

        asyncio.create_task(_start_grpc_safe())
        logger.info("startup complete")

    @app.on_event("shutdown")
    async def on_shutdown():
        logger.info("shutdown")

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
        log_level="info",
    )
