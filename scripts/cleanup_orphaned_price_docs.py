"""Delete DB (Postgres + Qdrant) rows for seed_data price PDFs that no longer
exist on disk (user manually removed them, e.g. unreadable scanned vendor
quotes). Read-only w.r.t. files that ARE still on disk. Safe to run while
the app is up — does not touch the app process."""
import asyncio
import logging
from pathlib import Path

from sqlalchemy import select

from app.core.bootstrap.constants import KB_PRICING_ID, SEED_DATA_DIR, SYSTEM_USER_ID
from app.db.postgres.base import get_session
from app.db.postgres.models import Document
from app.db.postgres.repositories.document_repo import DocumentRepository
from app.db.qdrant.client import QdrantStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cleanup_orphaned")


async def main() -> None:
    doc_repo = DocumentRepository()
    qdrant = QdrantStore()
    root = Path(SEED_DATA_DIR)

    async with get_session() as s:
        result = await s.execute(select(Document).where(Document.kb_id == KB_PRICING_ID))
        docs = list(result.scalars().all())

    removed = 0
    for doc in docs:
        region = (doc.doc_metadata or {}).get("region", "")
        path = root / "prices" / region / doc.filename
        if path.exists():
            continue
        logger.info("orphaned (no longer on disk): %s [%s] chunk_count=%d", doc.filename, region, doc.chunk_count)
        if doc.chunk_count:
            await qdrant.delete_by_document(str(doc.id))
        await doc_repo.delete(str(doc.id), SYSTEM_USER_ID)
        removed += 1

    logger.info("cleanup complete — removed %d orphaned document rows", removed)


if __name__ == "__main__":
    asyncio.run(main())
