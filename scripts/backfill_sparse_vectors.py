"""Backfill BM25 sparse vectors onto points indexed before hybrid retrieval.

Every point already stores `full_content` in its payload — the exact string
that was embedded — so the lexical half can be built from what is already in
Qdrant. No documents are re-parsed, no text is re-embedded, and the dense
vectors are never touched: this uses `update_vectors`, which adds a named
vector to an existing point and leaves the rest of it alone.

Without this, a collection populated before the change answers every hybrid
query from the dense branch only. It does not error — points with no sparse
vector simply never match the sparse prefetch — which makes the omission
invisible except as retrieval quality that quietly fails to improve.

Also reports the TRUE average document length over the corpus. `settings.
bm25_avg_doc_len` ships as an estimate (600), and BM25's length normalisation
is only correct if that constant matches reality; the number printed at the
end is what it should be set to.

Usage:
    python -m scripts.backfill_sparse_vectors            # dry run: report only
    python -m scripts.backfill_sparse_vectors --apply    # write the vectors

    # Two passes, if you want the constant to be exactly right:
    python -m scripts.backfill_sparse_vectors            # prints the average
    #   -> set BM25_AVG_DOC_LEN in .env to that value, then
    python -m scripts.backfill_sparse_vectors --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from qdrant_client.models import SparseVector

from app.config import settings
from app.core.retrieval.sparse import encode_document, tokenize
from app.db.qdrant.client import SPARSE_VECTOR, QdrantStore

BATCH = 256


async def _scroll_all(store: QdrantStore):
    """Every point in the collection, with payload, in id order."""
    offset = None
    while True:
        points, offset = await store._client.scroll(
            collection_name=store._collection,
            limit=BATCH,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            return
        yield points
        if offset is None:
            return


def _text_of(point) -> str:
    p = point.payload or {}
    return p.get("full_content") or p.get("content") or ""


async def main(apply: bool) -> int:
    store = QdrantStore()

    try:
        info = await store._client.get_collection(store._collection)
    except Exception as exc:
        print(f"cannot reach collection {store._collection!r}: {exc}", file=sys.stderr)
        return 2
    total = info.points_count or 0
    print(f"collection={store._collection}  points={total}  apply={apply}")

    seen = 0
    empty = 0
    token_total = 0
    written = 0

    async for batch in _scroll_all(store):
        ids: list = []
        vectors: list[dict] = []
        for point in batch:
            seen += 1
            text = _text_of(point)
            n_tokens = len(tokenize(text))
            if n_tokens == 0:
                empty += 1
                continue
            token_total += n_tokens
            if apply:
                indices, values = encode_document(text, settings.bm25_avg_doc_len)
                if indices:
                    ids.append(point.id)
                    vectors.append({SPARSE_VECTOR: SparseVector(indices=indices, values=values)})

        if apply and ids:
            # update_vectors ADDS the named vector; the dense vector and the
            # payload are untouched, so this is safe to re-run and safe to
            # interrupt — a partial run just leaves the rest for the next one.
            await store._client.update_vectors(
                collection_name=store._collection,
                points=[
                    {"id": pid, "vector": vec} for pid, vec in zip(ids, vectors, strict=True)
                ],
            )
            written += len(ids)
        print(f"  … {seen}/{total} scanned, {written} written", end="\r", flush=True)

    print()
    indexable = seen - empty
    avg = (token_total / indexable) if indexable else 0.0
    print(f"scanned      : {seen}")
    print(f"no tokens    : {empty}  (nothing for BM25 to index — skipped)")
    print(f"written      : {written}" if apply else "written      : 0 (dry run)")
    print()
    print(f"TRUE average document length : {avg:.1f} tokens")
    print(f"configured  BM25_AVG_DOC_LEN : {settings.bm25_avg_doc_len:.1f}")
    if indexable and abs(avg - settings.bm25_avg_doc_len) / max(avg, 1) > 0.20:
        print()
        print(
            "  ⚠  These differ by more than 20%. BM25's length normalisation is\n"
            f"     computed against the configured value, so set BM25_AVG_DOC_LEN={avg:.0f}\n"
            "     in .env and re-run with --apply for correctly weighted scores."
        )
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write vectors (default: dry run)")
    raise SystemExit(asyncio.run(main(ap.parse_args().apply)))
