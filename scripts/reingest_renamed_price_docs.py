"""Ingest the price PDFs that were just renamed to clearer filenames.
Safe to run alongside the app (no restart) — only touches the specific
files listed here, not the whole seed_data tree."""
import asyncio
import logging
from pathlib import Path

from app.core.bootstrap.constants import KB_PRICING_ID, SEED_DATA_DIR, SYSTEM_USER_ID
from app.core.ingestion.price_pipeline import PriceExtractionPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("reingest_renamed")

FILES = [
    ("HN", "CongVan-CongBoGia-VLXD-HaNoi-QuyII-2026.pdf"),
    ("HN", "BangGia-VLXD-BoSung-NhuaDuong-HaNoi-QuyII-2026.pdf"),
    ("DN", "CongVan-CongBoGia-VLXD-DaNang-Thang06-2026.pdf"),
    ("DN", "BangGia-VLXD-DaNang-Thang06-2026.pdf"),
    ("DN", "BangGia-VatTuNuoc-DaNang-Thang06-2026.pdf"),
    ("DN", "BangGia-VatTuDien-DaNang-Thang06-2026.pdf"),
    ("HCM", "ThongBao-CongBoGia-VLXD-HCM-Thang06-2026.pdf"),
    ("HCM", "BangGia-VLXD-KhoangSan-HCM-Thang06-2026.pdf"),
    ("HCM", "BangGia-VLXD-ThamKhaoThiTruong-HCM-Thang06-2026.pdf"),
]


async def main() -> None:
    pipeline = PriceExtractionPipeline()
    root = Path(SEED_DATA_DIR)

    for region, filename in FILES:
        path = root / "prices" / region / filename
        if not path.exists():
            logger.warning("skip %s — not found at %s", filename, path)
            continue
        logger.info("ingesting %s (region=%s)", filename, region)
        content = path.read_bytes()
        async for event in pipeline.ingest_stream(
            job_id=f"rename-{filename}",
            kb_id=KB_PRICING_ID,
            user_id=SYSTEM_USER_ID,
            filename=filename,
            content=content,
            config={"region": region, "price_period": ""},
        ):
            if event.get("stage") == "error":
                logger.warning("ingest failed file=%s error=%s", filename, event.get("error"))
            elif event.get("stage") == "done":
                logger.info(
                    "ingest done file=%s chunks=%s price_rows=%s",
                    filename, event.get("chunks_done"), event.get("price_rows"),
                )

    logger.info("reingest complete")


if __name__ == "__main__":
    asyncio.run(main())
