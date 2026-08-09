#!/usr/bin/env python3
"""Seed seed_data/ into the demo account's own knowledge bases.

Run INSIDE the app container (uses the app's own pipelines and session):

    python scripts/seed_demo_data.py --dry-run
    python scripts/seed_demo_data.py --apply

Replaces scripts/ingest_kb_docx.py for this purpose: that script ingests
kb_docx/ (mixed .md/.pdf, some documents with no region) under the fixed
SYSTEM_USER_ID into the 4 system KBs. This script ingests seed_data/ only
(PDFs only — no .md twins to choose between) under a dedicated demo account
(demo@example.com), into two KBs owned by that account rather than the
shared system ones.

Region is inferred from each filename's own prefix (HaNoi_ / DaNang_ /
HoChiMinh_) rather than hand-listed per file, since seed_data/ already
names files that way.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

ROOT = Path("/app/seed_data")

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "Demo1234!"
DEMO_FULL_NAME = "Demo"

KB_PRICING_NAME = "Báo giá VLXD Hà Nội - Đà Nẵng - TP.HCM"
KB_STANDARDS_NAME = "QCVN - TCVN"

PRICES_DIR = "Báo giá VLXD  HaNoi-DaNang-HoChiMinh"
STANDARDS_DIR = "QCVN - TCVN"

_REGION_PREFIXES = {
    "HaNoi_": "HN",
    "DaNang_": "DN",
    "HoChiMinh_": "HCM",
}


def _region_for(filename: str) -> str | None:
    for prefix, region in _REGION_PREFIXES.items():
        if filename.startswith(prefix):
            return region
    return None


def _discover() -> list[tuple[Path, str | None]]:
    """(path, region) for every file under seed_data/, region=None routes to
    the standard (non-price) pipeline — currently only the QCVN standard."""
    out: list[tuple[Path, str | None]] = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        out.append((p, _region_for(p.name)))
    return out


async def _get_or_create_demo_user():
    from app.core.auth.password import PasswordHandler
    from app.db.postgres.repositories.user_repo import UserRepository

    repo = UserRepository()
    user = await repo.get_by_email(DEMO_EMAIL)
    if user:
        return user
    hashed = PasswordHandler().hash(DEMO_PASSWORD)
    return await repo.create(email=DEMO_EMAIL, hashed_password=hashed, full_name=DEMO_FULL_NAME)


async def _get_or_create_kb(user_id: str, name: str, *, price_extraction: bool):
    from app.db.postgres.repositories.kb_repo import KnowledgeBaseRepository

    repo = KnowledgeBaseRepository()
    for kb in await repo.list_by_user(user_id):
        if kb.name == name:
            return kb
    return await repo.create(
        user_id=user_id,
        name=name,
        price_extraction=price_extraction,
        table_heavy_chunking=price_extraction,
    )


async def _purge(session, qdrant, kb_id: str, filename: str) -> int:
    """Drop any existing copy of this filename, with its vectors and price
    rows, so re-running the script does not leave two copies of the same
    document competing for the same retrieval slots."""
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
    files = _discover()
    print(f"{'Tài liệu':58} {'vùng':5} {'MB':>6}")
    for p, region in files:
        size = f"{p.stat().st_size / 1e6:.1f}"
        print(f"{p.name[:56]:58} {region or '-':5} {size:>6}")

    if not files:
        print(f"\nKhông tìm thấy file nào dưới {ROOT} — dừng.")
        return 1
    if not apply:
        print(f"\nDemo account: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print("--dry-run: chưa thay đổi gì.")
        return 0

    from app.core.ingestion.pipeline import IngestionPipeline
    from app.core.ingestion.price_pipeline import PriceExtractionPipeline
    from app.db.postgres.base import get_session
    from app.db.qdrant.client import QdrantStore

    qdrant = QdrantStore()
    await qdrant.ensure_collection()

    demo_user = await _get_or_create_demo_user()
    user_id = str(demo_user.id)
    price_kb = await _get_or_create_kb(user_id, KB_PRICING_NAME, price_extraction=True)
    standards_kb = await _get_or_create_kb(user_id, KB_STANDARDS_NAME, price_extraction=False)
    print(f"\nDemo user: {user_id} ({DEMO_EMAIL})")
    print(f"KB giá:     {price_kb.id}")
    print(f"KB QCVN:    {standards_kb.id}")

    async with get_session() as s:
        for p, region in files:
            kb_id = str(price_kb.id if region else standards_kb.id)
            n = await _purge(s, qdrant, kb_id, p.name)
            if n:
                print(f"dọn {n} bản {p.name} còn sót")

    std, price = IngestionPipeline(), PriceExtractionPipeline()
    totals = {"chunks": 0, "rows": 0}
    for i, (p, region) in enumerate(files, 1):
        kb = price_kb if region else standards_kb
        pipeline = price if region else std
        config = {"region": region, "price_period": ""} if region else {}
        print(f"\n[{i}/{len(files)}] {p.name} (KB={kb.name}, vùng={region or '-'})", flush=True)
        async for ev in pipeline.ingest_stream(
            job_id=str(uuid.uuid4()),
            kb_id=str(kb.id),
            user_id=user_id,
            filename=p.name,
            content=p.read_bytes(),
            config=config,
        ):
            if ev.get("stage") == "error":
                print(f"    LỖI: {ev.get('error')}", flush=True)
                return 2
            if ev.get("done"):
                chunks = ev.get("chunks_total") or ev.get("chunks_done") or 0
                rows = ev.get("price_rows", 0) or 0
                totals["chunks"] += chunks
                totals["rows"] += rows
                print(f"    xong: chunks={chunks} price_rows={rows}", flush=True)

    print(f"\nTổng: {totals['chunks']} chunk, {totals['rows']} dòng giá.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.apply and not a.dry_run:
        ap.error("cần --apply hoặc --dry-run")
    sys.exit(asyncio.run(main(apply=a.apply)))
