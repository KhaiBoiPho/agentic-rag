#!/usr/bin/env python3
"""Does BM25 change what retrieval brings back? Measured without a generator.

Run INSIDE the app container:

    PYTHONPATH=/app python scripts/eval_hybrid_recall.py
    PYTHONPATH=/app python scripts/eval_hybrid_recall.py --embed voyageai/voyage-4-large

Why this exists alongside bench_agentic.py
------------------------------------------
bench_agentic grades the ANSWER, so a BM25 gain arrives mixed with the
generation model's own variance — which §5.2 of the report measured at ±1
question on a 30-question set. A 2-question swing there is unreadable.

This script removes the generator entirely. It asks the only question BM25 can
actually be responsible for: does the chunk containing the answer end up
inside the top-k window? That is deterministic — same corpus, same vectors,
same result every run — so a difference here is real by construction.

Read the two together. Retrieval recall going up while answer score stays flat
means the generator is the bottleneck; both flat means BM25 did nothing for
this corpus; answers up while recall is flat is a warning that the answer
gain came from somewhere other than the change under test.

Queries are split by SHAPE, not by difficulty
---------------------------------------------
BM25 should help where the query names a rare token — a product code — and
should do close to nothing where the query is ordinary prose that dense
embeddings already handle. Reporting one blended number would hide that. If
the sparse arm turns out to help both groups equally, the correct reaction is
to distrust the measurement rather than to celebrate, because that is not how
lexical matching behaves.

Corpus vectors are read from the same .bench_cache/ entries bench_agentic.py
writes, keyed by model + SHA-256 of the chunk texts. Running this after a
benchmark run therefore costs nothing for the corpus; only the queries below
are newly embedded.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import unicodedata

from scripts.bench_agentic import PREFETCH, cos, dump_chunks, embed_texts
from scripts.bench_retrieval import BM25Index, rrf_fuse

TOP_KS = (5, 10)

# Queries whose distinguishing token is a product code — hyphens, embedded
# digits, dotted or slashed specs. This is the group BM25 exists for.
CODE_QUERIES: list[tuple[str, str]] = [
    ("Cáp điện CXV-150 0,6/1kV giá bao nhiêu một mét?", "CXV-150"),
    ("Cáp vặn xoắn LV-ABC-4x95 giá bao nhiêu một mét?", "LV-ABC-4x95"),
    ("Ống luồn tròn PVC H.SERIES phi 25 giá bao nhiêu một cây?", "H.SERIES phi 25"),
    ("Nhựa đường 60/70 ở Hà Nội giá bao nhiêu một kg?", "60/70"),
    ("Cấp phối A Dmax37,5 ở Đà Nẵng giá bao nhiêu?", "Dmax37,5"),
    ("Cấp phối A Dmax25 ở Đà Nẵng giá bao nhiêu một m3?", "Dmax25"),
    ("Cửa đi mở quay 2 cánh nhôm Topal XFAD dày 2mm giá bao nhiêu m2?", "Topal XFAD"),
    ("Xi măng Vicem Hạ Long PCB50 giá bao nhiêu một tấn?", "PCB50"),
    ("Thép thanh vằn D12 CB500-V ở Hà Nội giá bao nhiêu một kg?", "D12"),
    ("Xi măng bao Bút Sơn Xanh đa dụng PCB40 giá bao nhiêu?", "PCB40"),
]

# Ordinary prose naming a common material. Dense retrieval should already be
# good here; this group is the control.
NAME_QUERIES: list[tuple[str, str]] = [
    ("Giá cát san lấp ở TPHCM là bao nhiêu một khối?", "cát san lấp"),
    ("Giá đá 1x2 ở TPHCM bao nhiêu một m3?", "đá 1x2"),
    ("Ở Đà Nẵng, đá mi sàng giá bao nhiêu một m3?", "đá mi sàng"),
    ("Xi măng Sông Gianh đóng bao giá bao nhiêu một tấn?", "Sông Gianh"),
    ("Xi măng Vicem Hà Tiên Xây tô giá bao nhiêu?", "Hà Tiên Xây tô"),
    ("Tôn Hoa Sen Gold màu giá bao nhiêu?", "Hoa Sen"),
    ("Nối trơn phi 16 ở Đà Nẵng giá bao nhiêu một cái?", "Nối trơn phi 16"),
    ("Đèn led bulb Điện Quang giá bao nhiêu một cái?", "Điện Quang"),
    ("Vật liệu chống thấm gốc xi măng giá bao nhiêu?", "chống thấm"),
    ("Ống thoát uPVC D125 ở Hà Nội giá bao nhiêu một mét?", "uPVC D125"),
]

# Coverage probe. One question whose honest answer spans hundreds of rows, to
# measure how much of a large answer a fixed window can physically carry —
# the failure §1.1 of the report identified as coverage rather than ranking.
COVERAGE_Q = "dây cáp điện lực CADIVI giá bao nhiêu tiền một mét"
COVERAGE_SUPPLIER = "cadivi"


def _fold(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn"
    ).replace("đ", "d")


_MONEY_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})+")


def _digits(s: str) -> str:
    return re.sub(r"[^\d]", "", s)


async def gold_prices() -> set[str]:
    """The price values a complete CADIVI answer would have to contain."""
    from sqlalchemy import text as sql

    from app.db.postgres.base import get_session

    async with get_session() as s:
        rows = await s.execute(
            sql(
                "select price_ex_vat from material_prices "
                "where manufacturer ilike :p or material_name ilike :p"
            ),
            {"p": f"%{COVERAGE_SUPPLIER}%"},
        )
        return {_digits(f"{float(r[0]):.0f}") for r in rows}


def arms(qvec, cvecs, bm25, query: str, k: int) -> dict[str, list[int]]:
    """The three retrieval arms, each returning k chunk indices."""
    dense = sorted(((cos(qvec, v), i) for i, v in enumerate(cvecs)), key=lambda t: -t[0])
    dense_ids = [i for _, i in dense]
    sparse_ids = bm25.top(query, PREFETCH)
    return {
        "dense": dense_ids[:k],
        "sparse": sparse_ids[:k],
        "hybrid": rrf_fuse([dense_ids[:PREFETCH], sparse_ids], k),
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embed", default="openai/text-embedding-3-small")
    a = ap.parse_args()

    chunks = await dump_chunks()
    print(f"{len(chunks)} chunk · embedding={a.embed}\n")

    cvecs = await embed_texts(a.embed, [c["full_content"] for c in chunks], "corpus")
    bm25 = BM25Index.build([c["full_content"] for c in chunks])

    groups = {"mã sản phẩm": CODE_QUERIES, "tên thường": NAME_QUERIES}
    all_q = [q for g in groups.values() for q, _ in g] + [COVERAGE_Q]
    qvecs = await embed_texts(a.embed, all_q, f"evalq{len(all_q)}")
    qvec_of = dict(zip(all_q, qvecs))

    folded = [_fold(c["full_content"]) for c in chunks]

    print(f"{'nhóm':14}{'k':>3}  " + "".join(f"{n:>10}" for n in ("dense", "sparse", "hybrid")))
    for gname, queries in groups.items():
        for k in TOP_KS:
            hits = {"dense": 0, "sparse": 0, "hybrid": 0}
            for q, needle in queries:
                got = arms(qvec_of[q], cvecs, bm25, q, k)
                nf = _fold(needle)
                for arm, ids in got.items():
                    if any(nf in folded[i] for i in ids):
                        hits[arm] += 1
            row = "".join(f"{hits[n]:>7}/{len(queries):<3}" for n in ("dense", "sparse", "hybrid"))
            print(f"{gname:14}{k:>3}  {row}")

    gold = await gold_prices()
    print(f"\nđộ phủ — {len(gold)} đơn giá CADIVI riêng biệt trong material_prices")
    print(f"{'':14}{'k':>3}  " + "".join(f"{n:>10}" for n in ("dense", "sparse", "hybrid")))
    for k in TOP_KS:
        got = arms(qvec_of[COVERAGE_Q], cvecs, bm25, COVERAGE_Q, k)
        cells = ""
        for arm in ("dense", "sparse", "hybrid"):
            window = " ".join(chunks[i]["full_content"] for i in got[arm])
            found = {_digits(m) for m in _MONEY_RE.findall(window)} & gold
            cells += f"{len(found):>7}/{len(gold):<3}"
        print(f"{'phủ CADIVI':14}{k:>3}  {cells}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
