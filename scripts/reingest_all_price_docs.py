"""Re-ingest every price PDF under seed_data/prices/ with the fixed
price_extractor (header false-positive + stray-space price bug). Deletes
existing DB/Qdrant rows first so results aren't duplicated. Safe to run
alongside the app — doesn't restart anything."""
import asyncio
import logging
from pathlib import Path

from sqlalchemy import select

from app.core.bootstrap.constants import KB_PRICING_ID, SEED_DATA_DIR, SEED_PRICE_REGIONS, SYSTEM_USER_ID
from app.core.ingestion.price_pipeline import PriceExtractionPipeline
from app.db.postgres.base import get_session
from app.db.postgres.models import Document
from app.db.postgres.repositories.document_repo import DocumentRepository
from app.db.qdrant.client import QdrantStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("reingest_all")


async def main() -> None:
    doc_repo = DocumentRepository()
    qdrant = QdrantStore()
    pipeline = PriceExtractionPipeline()
    root = Path(SEED_DATA_DIR)

    async with get_session() as s:
        result = await s.execute(select(Document).where(Document.kb_id == KB_PRICING_ID))
        existing = {d.filename: d for d in result.scalars().all()}

    for region in SEED_PRICE_REGIONS:
        region_dir = root / "prices" / region
        if not region_dir.exists():
            continue
        for path in sorted(region_dir.glob("*.pdf")):
            old = existing.get(path.name)
            if old is not None:
                if old.chunk_count:
                    await qdrant.delete_by_document(str(old.id))
                await doc_repo.delete(str(old.id), SYSTEM_USER_ID)

            logger.info("ingesting %s (region=%s)", path.name, region)
            content = path.read_bytes()
            async for event in pipeline.ingest_stream(
                job_id=f"reextract-{path.name}",
                kb_id=KB_PRICING_ID,
                user_id=SYSTEM_USER_ID,
                filename=path.name,
                content=content,
                config={"region": region, "price_period": ""},
            ):
                if event.get("stage") == "error":
                    logger.warning("ingest failed file=%s error=%s", path.name, event.get("error"))
                elif event.get("stage") == "done":
                    logger.info(
                        "ingest done file=%s chunks=%s price_rows=%s warnings=%s",
                        path.name, event.get("chunks_done"), event.get("price_rows"), event.get("warnings"),
                    )

    logger.info("reingest_all complete")


if __name__ == "__main__":
    asyncio.run(main())
