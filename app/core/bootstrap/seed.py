"""Background ingestion of the system knowledge bases at app startup.

The two system KBs (rows created by migrations/versions/0003_seed_system_kb.py)
start empty. This module walks seed_data/ and ingests every file into them
directly (no RabbitMQ — IngestionPipeline/PriceExtractionPipeline don't need
the queue, see app/core/ingestion/{pipeline,price_pipeline}.py).

Idempotency is per-file (by filename already present in the KB), not a
single "document_count == 0" gate on the whole KB — some seed files are
large enough (e.g. a 699-page price annex) that ingesting one can take
minutes, and gating on the KB as a whole would mean a restart either
re-ingests everything from scratch or, once even one file has landed, skips
the rest forever.

Per-file status also matters, not just presence: an app restart (reload on
code change, container recreate, etc.) can kill a large file's ingestion
mid-stream, leaving its Document row stuck at "processing" forever with no
error recorded — this happened in practice with the 699-page Hà Nội annex.
Only "done" is treated as complete; anything else gets its stale row
deleted and the file re-ingested from scratch.

Called from app/main.py::on_startup() as a background task — must never
raise, since a seeding failure (e.g. missing OPENROUTER_API_KEY) shouldn't
crash the app.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.core.bootstrap.constants import (
    KB_KNOWLEDGE_ID,
    KB_PRICING_ID,
    SEED_DATA_DIR,
    SEED_PRICE_REGIONS,
    SYSTEM_USER_ID,
)
from app.core.ingestion.pipeline import IngestionPipeline
from app.core.ingestion.price_pipeline import PriceExtractionPipeline
from app.db.postgres.repositories.document_repo import DocumentRepository
from app.db.postgres.repositories.kb_repo import KnowledgeBaseRepository

logger = logging.getLogger(__name__)


async def _ingest_file(pipeline, kb_id: str, path: Path, config: dict) -> None:
    content = path.read_bytes()
    async for event in pipeline.ingest_stream(
        job_id=f"seed-{path.name}",
        kb_id=kb_id,
        user_id=SYSTEM_USER_ID,
        filename=path.name,
        content=content,
        config=config,
    ):
        if event.get("stage") == "error":
            logger.warning("seed ingest failed file=%s error=%s", path.name, event.get("error"))


async def _seed_kb(kb_id: str, kb_label: str, pipeline, files_with_config: list[tuple[Path, dict]]) -> None:
    kb_repo = KnowledgeBaseRepository()
    if await kb_repo.get(kb_id, SYSTEM_USER_ID) is None:
        logger.warning("system KB '%s' row missing — run `alembic upgrade head` first", kb_label)
        return

    doc_repo = DocumentRepository()
    existing = await doc_repo.list_status_by_filename(kb_id)

    pending: list[tuple[Path, dict]] = []
    for path, config in files_with_config:
        entry = existing.get(path.name)
        if entry is None:
            pending.append((path, config))
            continue
        doc_id, status = entry
        if status == "done":
            continue
        logger.warning(
            "seed: %s/%s stuck at status=%s from a prior run — deleting stale row and retrying",
            kb_label, path.name, status,
        )
        await doc_repo.delete(doc_id, SYSTEM_USER_ID)
        pending.append((path, config))

    if not pending:
        logger.info("KB '%s' already fully seeded (%d files) — skipping", kb_label, len(files_with_config))
        return

    logger.info("seeding KB '%s': %d/%d files remaining", kb_label, len(pending), len(files_with_config))
    for i, (path, config) in enumerate(pending, 1):
        logger.info("seed [%s %d/%d] %s", kb_label, i, len(pending), path.name)
        try:
            await _ingest_file(pipeline, kb_id, path, config=config)
        except Exception:
            logger.exception("seed file failed kb=%s file=%s", kb_label, path.name)
    logger.info("KB '%s' seeding pass done", kb_label)


async def seed_system_kb_documents() -> None:
    root = Path(SEED_DATA_DIR)
    if not root.exists():
        logger.info("seed_data/ not found — skipping system KB seeding")
        return

    try:
        files = sorted(p for p in (root / "knowledge").glob("*") if p.is_file())
        await _seed_kb(
            KB_KNOWLEDGE_ID, "Kiến thức xây dựng", IngestionPipeline(),
            [(p, {}) for p in files],
        )
    except Exception:
        logger.exception("seed_system_kb_documents: knowledge KB step failed")

    try:
        files_with_config: list[tuple[Path, dict]] = []
        for region in SEED_PRICE_REGIONS:
            region_dir = root / "prices" / region
            if not region_dir.exists():
                continue
            for path in sorted(region_dir.glob("*.pdf")):
                files_with_config.append((path, {"region": region, "price_period": ""}))
        await _seed_kb(KB_PRICING_ID, "Dự toán giá nhà", PriceExtractionPipeline(), files_with_config)
    except Exception:
        logger.exception("seed_system_kb_documents: pricing KB step failed")
