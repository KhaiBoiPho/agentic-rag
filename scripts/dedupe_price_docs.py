"""Remove duplicate document rows (same filename+region, both status=done)
in the pricing KB, keeping the oldest one. Purges Qdrant vectors + material
price rows for the duplicates being removed."""
import asyncio
import logging
from collections import defaultdict

from sqlalchemy import select

from app.core.bootstrap.constants import KB_PRICING_ID, SYSTEM_USER_ID
from app.db.postgres.base import get_session
from app.db.postgres.models import Document
from app.db.postgres.repositories.document_repo import DocumentRepository
from app.db.qdrant.client import QdrantStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("dedupe")


async def main() -> None:
    doc_repo = DocumentRepository()
    qdrant = QdrantStore()

    async with get_session() as s:
        result = await s.execute(select(Document).where(Document.kb_id == KB_PRICING_ID))
        docs = list(result.scalars().all())

    groups: dict[str, list[Document]] = defaultdict(list)
    for doc in docs:
        groups[doc.filename].append(doc)

    removed = 0
    for filename, rows in groups.items():
        if len(rows) <= 1:
            continue
        rows.sort(key=lambda d: d.created_at)
        keep, dupes = rows[0], rows[1:]
        logger.info("dedupe %s: keeping %s, removing %d duplicate(s)", filename, keep.id, len(dupes))
        for dup in dupes:
            if dup.chunk_count:
                await qdrant.delete_by_document(str(dup.id))
            await doc_repo.delete(str(dup.id), SYSTEM_USER_ID)
            removed += 1

    logger.info("dedupe complete — removed %d duplicate rows", removed)


if __name__ == "__main__":
    asyncio.run(main())
