#!/usr/bin/env python3
"""Replace the knowledge bases' Markdown documents with their .docx versions.

Run INSIDE the app container (it uses the app's own pipelines and session):

    python scripts/replace_md_with_docx.py --dry-run
    python scripts/replace_md_with_docx.py --apply

Order matters: every .docx is ingested and verified BEFORE any .md is
deleted, so the knowledge base is never missing the content in between. The
new document is created with the SAME user_id as the .md it replaces —
document deletion is ownership-scoped, so attributing it to whoever ran this
script would leave the owner unable to delete their own document from the UI.

Region is only supplied where it is genuinely known (the Hồ Chí Minh price
annexes). A knowledge/standards document has no prices and no province, so
it goes through the standard pipeline rather than being given an invented
region — `material_prices.region` is what every price lookup filters on, and
a wrong value there produces wrong answers rather than missing ones.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

KB_KNOWLEDGE = "00000000-0000-0000-0000-000000000101"
KB_PRICING = "00000000-0000-0000-0000-000000000102"
KB_VENDOR = "00000000-0000-0000-0000-000000000103"
KB_STANDARDS = "00000000-0000-0000-0000-000000000104"

DOCX_ROOT = Path("/app/kb_docx")

# (markdown filename already in the KB, path of the .docx, kb, region or None)
# region None => standard pipeline (chunks only), no price extraction.
REPLACEMENTS: list[tuple[str, str, str, str | None]] = [
    (
        "KienThucNen-VatLieuXayDung.md",
        "Kiến thức nền VLXD - Tham khảo/KienThucNen-VatLieuXayDung.docx",
        KB_KNOWLEDGE,
        None,
    ),
    (
        "HuongDan-ChonVatLieu-UocTinhChiPhiXayNha.md",
        "Kiến thức nền VLXD - Tham khảo/HuongDan-ChonVatLieu-UocTinhChiPhiXayNha.docx",
        KB_KNOWLEDGE,
        None,
    ),
    (
        "HoChiMinh-BangGiaVLXD-TongHop-T7-2026.md",
        "Báo giá VLXD  HaNoi-DaNang-HoChiMinh/HoChiMinh-BangGiaVLXD-TongHop-T7-2026.docx",
        KB_PRICING,
        "HCM",
    ),
    (
        "HoChiMinh-PhuLuc1-GiaKhoangSan-T7-2026.md",
        "Báo giá VLXD  HaNoi-DaNang-HoChiMinh/HoChiMinh-PhuLuc1-GiaKhoangSan-T7-2026.docx",
        KB_PRICING,
        "HCM",
    ),
    (
        "HoChiMinh-PhuLuc2-GiaThamKhaoThiTruong-T7-2026.md",
        "Báo giá VLXD  HaNoi-DaNang-HoChiMinh/HoChiMinh-PhuLuc2-GiaThamKhaoThiTruong-T7-2026.docx",
        KB_PRICING,
        "HCM",
    ),
    (
        "BaoGia-DoanhNghiepVLXD-ToanQuoc-2026.md",
        "Doanh Nghiệp - Sản phẩm VLXD/BaoGia-DoanhNghiepVLXD-ToanQuoc-2026.docx",
        KB_VENDOR,
        None,
    ),
    (
        "TongHop-QCVN-TCVN-VatLieuXayDung.md",
        "QCVN - TCVN/TongHop-QCVN-TCVN-VatLieuXayDung.docx",
        KB_STANDARDS,
        None,
    ),
]

# "Báo giá doanh nghiệp" covers the whole country, so no single province is
# right for its rows; price extraction is turned off rather than filing them
# under an arbitrary region.
DISABLE_PRICE_EXTRACTION = [KB_VENDOR]


async def _find_doc(session, kb_id: str, filename: str):
    """Newest match. A previous interrupted run can leave an errored document
    with the same name behind, and picking that one would make the script
    report failure for an ingest that actually just succeeded."""
    from sqlalchemy import select

    from app.db.postgres.models import Document

    res = await session.execute(
        select(Document)
        .where(Document.kb_id == uuid.UUID(kb_id), Document.filename == filename)
        .order_by(Document.created_at.desc())
    )
    return res.scalars().first()


async def _purge_docs(session, qdrant, kb_id: str, filename: str) -> int:
    """Remove every existing document with this filename from the KB, along
    with its vectors and price rows. Makes the script re-runnable: without it
    a second run leaves two copies of each .docx in the KB, which then both
    surface as retrieval hits for the same content."""
    from sqlalchemy import delete as sa_delete
    from sqlalchemy import select

    from app.db.postgres.models import Document, KnowledgeBase, MaterialPrice

    res = await session.execute(
        select(Document).where(Document.kb_id == uuid.UUID(kb_id), Document.filename == filename)
    )
    docs = list(res.scalars().all())
    for doc in docs:
        await qdrant.delete_by_document(str(doc.id))
        await session.execute(sa_delete(MaterialPrice).where(MaterialPrice.document_id == doc.id))
        kb = await session.get(KnowledgeBase, doc.kb_id)
        if kb and kb.document_count > 0:
            kb.document_count -= 1
        await session.delete(doc)
    return len(docs)


async def main(apply: bool) -> int:
    from sqlalchemy import delete as sa_delete
    from sqlalchemy import select

    from app.core.ingestion.pipeline import IngestionPipeline
    from app.core.ingestion.price_pipeline import PriceExtractionPipeline
    from app.db.postgres.base import get_session
    from app.db.postgres.models import Document, KnowledgeBase, MaterialPrice
    from app.db.qdrant.client import QdrantStore

    plan: list[tuple] = []
    async with get_session() as s:
        for md_name, docx_rel, kb_id, region in REPLACEMENTS:
            docx = DOCX_ROOT / docx_rel
            old = await _find_doc(s, kb_id, md_name)
            status = []
            if not docx.exists():
                status.append("THIẾU FILE DOCX")
            if old is None:
                status.append("không thấy .md trong KB")
            plan.append((md_name, docx, kb_id, region, old, status))

    print(f"{'Tài liệu':52} {'KB':6} {'vùng':5} {'trạng thái'}")
    for md_name, docx, kb_id, region, old, status in plan:
        print(
            f"{md_name[:50]:52} …{kb_id[-3:]:5} {region or '-':5} "
            f"{'; '.join(status) if status else 'sẵn sàng'}"
        )
    if any(st for *_, st in plan):
        print("\nCó mục chưa sẵn sàng — dừng lại.")
        return 1
    if not apply:
        print("\n--dry-run: chưa thay đổi gì.")
        return 0

    # 1) Knowledge bases whose content has no province.
    async with get_session() as s:
        for kb_id in DISABLE_PRICE_EXTRACTION:
            kb = await s.get(KnowledgeBase, uuid.UUID(kb_id))
            if kb and kb.price_extraction:
                kb.price_extraction = False
                print(f"Đã tắt trích giá cho KB {kb.name}")

    std, price = IngestionPipeline(), PriceExtractionPipeline()
    qdrant = QdrantStore()
    new_doc_ids: list[str] = []

    # Clear any .docx left by an earlier run of this script before re-ingesting.
    async with get_session() as s:
        for _, docx, kb_id, *_ in plan:
            n = await _purge_docs(s, qdrant, kb_id, docx.name)
            if n:
                print(f"dọn {n} bản {docx.name} còn sót từ lần chạy trước")

    # 2) Ingest every .docx first — nothing is deleted until all of these
    #    finish, so the KB is never left without the content.
    for md_name, docx, kb_id, region, old, _ in plan:
        content = docx.read_bytes()
        pipeline = price if region else std
        config = {"region": region, "price_period": ""} if region else {}
        print(f"\n>>> nạp {docx.name} (KB …{kb_id[-3:]}, vùng={region or '-'})")
        async for ev in pipeline.ingest_stream(
            job_id=str(uuid.uuid4()),
            kb_id=kb_id,
            user_id=str(old.user_id),
            filename=docx.name,
            content=content,
            config=config,
        ):
            if ev.get("stage") == "error":
                print(f"    LỖI: {ev.get('error')}")
                return 2
            if ev.get("done"):
                print(
                    f"    xong: chunks={ev.get('chunks_total') or ev.get('chunks_done')} "
                    f"price_rows={ev.get('price_rows', '-')}"
                )

    async with get_session() as s:
        for _, docx, kb_id, *_ in plan:
            d = await _find_doc(s, kb_id, docx.name)
            if d is None or d.status != "done":
                print(
                    f"\n{docx.name}: trạng thái {d.status if d else 'không thấy'} — DỪNG, "
                    "không xoá .md nào cả."
                )
                return 3
            new_doc_ids.append(str(d.id))

    # 3) Only now remove the Markdown originals.
    async with get_session() as s:
        for md_name, _, kb_id, _, old, _ in plan:
            doc = await s.get(Document, old.id)
            if doc is None:
                continue
            await qdrant.delete_by_document(str(doc.id))
            await s.execute(sa_delete(MaterialPrice).where(MaterialPrice.document_id == doc.id))
            kb = await s.get(KnowledgeBase, doc.kb_id)
            if kb and kb.document_count > 0:
                kb.document_count -= 1
            await s.delete(doc)
            print(f"đã xoá {md_name}")

    async with get_session() as s:
        res = await s.execute(select(Document.filename).where(Document.filename.like("%.md")))
        left = [r[0] for r in res.fetchall()]
    print(f"\nCòn lại .md trong hệ thống: {left or 'không còn'}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(apply=a.apply)))
