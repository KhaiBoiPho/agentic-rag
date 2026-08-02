#!/usr/bin/env python3
"""Re-ingest the knowledge bases' PDFs so they use the current extraction code.

Run INSIDE the app container:

    python scripts/reingest_pdfs.py --dry-run
    python scripts/reingest_pdfs.py --apply

Why: the PDFs were ingested before merged-cell resolution (§2.6), table-bbox
text filtering (§2.5), continuation-page headers (§2.7) and the spec /
manufacturer / unit-ditto work in the price extractor. Their chunks still
carry duplicated, scrambled table text and their price rows still have
unit='-', spec=NULL, manufacturer=NULL. Nothing short of re-running the
pipeline fixes stored data.

The uploaded bytes are not retained anywhere, so the source files come from
seed_data/, which holds byte-identical copies under different names —
SOURCE_FILES maps one to the other (verified by md5 before being written
down here).

Per document: ingest first, verify the new document reached `done`, and only
then delete the old one. Region and price_period are read from the existing
document's metadata rather than guessed, and the new document keeps the
original uploader as owner (deletion is ownership-scoped).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from pathlib import Path

SEED = Path("/app/seed_data")

# KB filename -> byte-identical file in seed_data (md5-verified).
SOURCE_FILES: dict[str, Path] = {
    "HaNoi-PhuLuc-BangGiaVLXD-QuyII-2026.pdf": SEED / "prices/HN/BangGia-VLXD-HaNoi-QuyII-2026.pdf",
    "HaNoi-PhuLucBoSung-BangGiaVLXD-QuyII-2026.pdf": SEED
    / "prices/HN/BangGia-VLXD-BoSung-NhuaDuong-HaNoi-QuyII-2026.pdf",
    "CongVan-CongBoGiaVLXD-HaNoi-QuyII-2026.pdf": SEED
    / "prices/HN/CongVan-CongBoGia-VLXD-HaNoi-QuyII-2026.pdf",
    "DaNang-PhuLuc1-BangGiaVLXD-T6-2026.pdf": SEED
    / "prices/DN/BangGia-VLXD-DaNang-Thang06-2026.pdf",
    "DaNang-PhuLuc2-GiaVatTuNuoc-T6-2026.pdf": SEED
    / "prices/DN/BangGia-VatTuNuoc-DaNang-Thang06-2026.pdf",
    "DaNang-PhuLuc3-GiaVatTuDien-T6-2026.pdf": SEED
    / "prices/DN/BangGia-VatTuDien-DaNang-Thang06-2026.pdf",
    "CongVan-CongBoGiaVLXD-DaNang-T6-2026.pdf": SEED
    / "prices/DN/CongVan-CongBoGia-VLXD-DaNang-Thang06-2026.pdf",
    "HoChiMinh-PhuLuc1-GiaKhoangSan-T7-2026.pdf": SEED
    / "prices/HCM/BangGia-VLXD-KhoangSan-HCM-Thang06-2026.pdf",
    "HoChiMinh-PhuLuc2-GiaThamKhaoThiTruong-T7-2026.pdf": SEED
    / "prices/HCM/BangGia-VLXD-ThamKhaoThiTruong-HCM-Thang06-2026.pdf",
    "ThongBao-CongBoGiaVLXD-HoChiMinh-T7-2026.pdf": SEED
    / "prices/HCM/ThongBao-CongBoGia-VLXD-HCM-Thang06-2026.pdf",
    "QCVN-16-2023-BoXayDung.pdf": SEED / "knowledge/QCVN-16-2023.pdf",
}


async def _pdf_documents(session):
    from sqlalchemy import select

    from app.db.postgres.models import Document

    res = await session.execute(
        select(Document).where(Document.filename.like("%.pdf")).order_by(Document.filename)
    )
    return list(res.scalars().all())


async def _delete_document(session, qdrant, doc) -> None:
    from sqlalchemy import delete as sa_delete

    from app.db.postgres.models import KnowledgeBase, MaterialPrice

    await qdrant.delete_by_document(str(doc.id))
    await session.execute(sa_delete(MaterialPrice).where(MaterialPrice.document_id == doc.id))
    kb = await session.get(KnowledgeBase, doc.kb_id)
    if kb and kb.document_count > 0:
        kb.document_count -= 1
    await session.delete(doc)


async def main(apply: bool) -> int:
    from sqlalchemy import select

    from app.core.ingestion.pipeline import IngestionPipeline
    from app.core.ingestion.price_pipeline import PriceExtractionPipeline
    from app.db.postgres.base import get_session
    from app.db.postgres.models import Document
    from app.db.qdrant.client import QdrantStore

    async with get_session() as s:
        docs = await _pdf_documents(s)
        plan = []
        for d in docs:
            meta = d.doc_metadata or {}
            src = SOURCE_FILES.get(d.filename)
            problem = ""
            if src is None:
                problem = "KHÔNG CÓ FILE NGUỒN"
            elif not src.exists():
                problem = f"THIẾU {src}"
            plan.append(
                {
                    "id": str(d.id),
                    "kb_id": str(d.kb_id),
                    "user_id": str(d.user_id),
                    "filename": d.filename,
                    "src": src,
                    "region": meta.get("region", ""),
                    "price_period": meta.get("price_period", ""),
                    "chunks": d.chunk_count,
                    "rows": meta.get("price_row_count"),
                    "problem": problem,
                }
            )

    print(f"{'Tài liệu':52} {'vùng':5} {'chunk cũ':>9} {'giá cũ':>8}  {'trạng thái'}")
    for p in plan:
        print(
            f"{p['filename'][:50]:52} {p['region'] or '-':5} {p['chunks']:>9} "
            f"{'-' if p['rows'] is None else p['rows']:>8}  {p['problem'] or 'sẵn sàng'}"
        )
    if any(p["problem"] for p in plan):
        print("\nCó mục thiếu file nguồn — dừng lại.")
        return 1
    if not apply:
        print(f"\n--dry-run: {len(plan)} tài liệu sẽ được nạp lại. Chưa thay đổi gì.")
        return 0

    std, price = IngestionPipeline(), PriceExtractionPipeline()
    qdrant = QdrantStore()
    total_chunks = total_rows = 0

    for i, p in enumerate(plan, 1):
        t0 = time.perf_counter()
        content = p["src"].read_bytes()
        pipeline = price if p["region"] else std
        config = {"region": p["region"], "price_period": p["price_period"]} if p["region"] else {}
        print(f"\n[{i}/{len(plan)}] {p['filename']} (vùng={p['region'] or '-'})")

        async for ev in pipeline.ingest_stream(
            job_id=str(uuid.uuid4()),
            kb_id=p["kb_id"],
            user_id=p["user_id"],
            filename=p["filename"],
            content=content,
            config=config,
        ):
            if ev.get("stage") == "error":
                print(f"    LỖI: {ev.get('error')} — DỪNG, không xoá bản cũ.")
                return 2

        # The new document shares its filename with the old one, so identify
        # it by "not the id we recorded before ingesting".
        async with get_session() as s:
            res = await s.execute(
                select(Document).where(
                    Document.kb_id == uuid.UUID(p["kb_id"]),
                    Document.filename == p["filename"],
                    Document.id != uuid.UUID(p["id"]),
                )
            )
            fresh = [d for d in res.scalars().all() if d.status == "done"]
        if not fresh:
            print("    Không tìm thấy bản mới ở trạng thái done — DỪNG, không xoá bản cũ.")
            return 3

        new = max(fresh, key=lambda d: d.created_at)
        rows = (new.doc_metadata or {}).get("price_row_count")
        total_chunks += new.chunk_count
        total_rows += rows or 0
        print(
            f"    mới: chunks={new.chunk_count} (cũ {p['chunks']})  "
            f"giá={'-' if rows is None else rows} (cũ {'-' if p['rows'] is None else p['rows']})  "
            f"{time.perf_counter() - t0:.0f}s"
        )

        async with get_session() as s:
            old = await s.get(Document, uuid.UUID(p["id"]))
            if old is not None:
                await _delete_document(s, qdrant, old)
        print("    đã xoá bản cũ")

    print(f"\nXong {len(plan)} tài liệu — tổng chunk={total_chunks}, tổng dòng giá={total_rows}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(apply=a.apply)))
