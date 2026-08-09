#!/usr/bin/env python3
"""Delete Qdrant points whose document no longer exists in Postgres.

Run INSIDE the app container:

    python scripts/purge_orphaned_vectors.py --dry-run
    python scripts/purge_orphaned_vectors.py --apply

Why these exist: deleting a *knowledge base* used to drop the KB and cascade
its documents in Postgres while leaving every vector behind — one production
deletion left 4.060 orphaned points that way. Earlier re-ingests under
different filenames left the same residue.

THE LEAK IS CLOSED. `delete_kb` now calls `QdrantStore.delete_by_kb` before
the Postgres delete, and `tests/test_deletion_integration.py` fails if either
deletion path stops removing vectors. This script remains for the residue
already in the collection, and for anything a future crash leaves half-done —
it is a cleanup tool, no longer a workaround.

These are not harmless. Retrieval filters on `kb_id`, which the orphaned
payloads still carry, so stale copies of superseded documents keep surfacing
as citations for questions they should no longer answer — with the old,
pre-fix table text in them.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter


async def main(apply: bool) -> int:
    from qdrant_client.models import Filter, HasIdCondition
    from sqlalchemy import select

    from app.config import settings
    from app.db.postgres.base import get_session
    from app.db.postgres.models import Document
    from app.db.qdrant.client import QdrantStore

    async with get_session() as s:
        res = await s.execute(select(Document.id))
        alive = {str(r[0]) for r in res.fetchall()}
    print(f"documents còn sống trong Postgres: {len(alive)}")

    store = QdrantStore()
    client = store._client
    collection = settings.qdrant_collection_name

    orphan_ids: list[str] = []
    by_file: Counter[str] = Counter()
    offset = None
    total = 0
    while True:
        points, offset = await client.scroll(
            collection_name=collection,
            limit=1000,
            offset=offset,
            with_payload=["document_id", "filename"],
            with_vectors=False,
        )
        for p in points:
            total += 1
            if (p.payload or {}).get("document_id") not in alive:
                orphan_ids.append(p.id)
                by_file[(p.payload or {}).get("filename", "?")] += 1
        if offset is None:
            break

    print(f"tổng points: {total} | mồ côi: {len(orphan_ids)}")
    for name, n in by_file.most_common():
        print(f"   {n:6}  {name}")

    if not orphan_ids:
        print("Không có gì để dọn.")
        return 0
    if not apply:
        print("\n--dry-run: chưa xoá gì.")
        return 0

    # Delete in batches: one request carrying thousands of ids risks a
    # timeout, and a partial failure is easier to reason about per batch.
    BATCH = 500
    for i in range(0, len(orphan_ids), BATCH):
        await client.delete(
            collection_name=collection,
            points_selector=Filter(must=[HasIdCondition(has_id=orphan_ids[i : i + BATCH])]),
            wait=True,
        )
        print(f"   đã xoá {min(i + BATCH, len(orphan_ids))}/{len(orphan_ids)}")

    info = await client.get_collection(collection)
    print(f"\nCòn lại trong collection: {info.points_count} points")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(apply=a.apply)))
