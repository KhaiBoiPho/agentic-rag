#!/usr/bin/env python3
"""Does capping table-chunk size help retrieval? Measured, not assumed.

Run INSIDE the app container (needs /tmp/chunks.json — see the dump step in
scripts/eval_table_embedding.py's docstring):

    python scripts/eval_chunk_cap.py

The earlier experiment (eval_table_embedding.py) asked whether splitting
improves RANKING, and the answer was barely (+0.038 similarity). This asks a
different question that the first one did not cover: with a token cap, does a
fixed top-k window end up carrying MORE of the answer?

Two effects pull in opposite directions and only measurement settles it:

  + smaller chunks waste fewer of the k slots on tables that merely score well
  − smaller chunks each carry fewer rows, so k of them hold less data

Metrics reported per variant:
  · recall@5 over the 16 hard questions (same set as eval_table_embedding)
  · coverage — of the 244 CADIVI prices in material_prices, how many appear
    in the retrieved window, split by region
  · tokens the window costs
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re

CHUNKS = "/tmp/chunks.json"
EMBED_MODEL = "openai/text-embedding-3-small"
CAPS = [None, 3000, 1500, 800]

CADIVI_Q = "dây cáp điện lực của công ty cổ phần vn cadivi giá bao nhiêu tiền"

QUERIES: list[tuple[str, str]] = [
    ("Giá xi măng Bút Sơn PCB40 ở Hà Nội bao nhiêu?", "Bút Sơn"),
    ("Xi măng Vicem Bút Sơn bao 50kg giá bao nhiêu một tấn?", "Bút Sơn"),
    ("Cáp điện CXV-150 0,6/1kV giá bao nhiêu một mét?", "CXV-150"),
    ("Cáp vặn xoắn LV-ABC-4x95 giá bao nhiêu?", "LV-ABC-4x95"),
    ("Đèn led DHP-STR02A 30W giá bao nhiêu một bộ?", "DHP-STR02A"),
    ("Cửa sổ nhôm Topal XFAD dày 1.4mm kính Việt Nhật giá bao nhiêu m2?", "Topal XFAD"),
    ("Y lọc gang FAF 2500 DN65 giá bao nhiêu?", "FAF 2500"),
    ("Xi măng Sông Gianh PCB40 đóng bao giá bao nhiêu?", "Sông Gianh"),
    ("Xi măng Nghi Sơn giá bao nhiêu một tấn?", "Nghi Sơn"),
    ("Tôn Hoa Sen mạ kẽm giá bao nhiêu?", "Hoa Sen"),
    ("Xi măng Vicem Hà Tiên Xây tô giá bao nhiêu?", "Vicem Hà Tiên Xây tô"),
    ("Vật liệu chống thấm gốc xi măng polymer giá bao nhiêu?", "chống thấm gốc xi măng"),
    ("Giá cát san lấp ở TPHCM là bao nhiêu một khối?", "cát san lấp"),
    ("Đá 1x2 giá bao nhiêu một m3?", "đá 1x2"),
    ("gia xi mang But Son PCB40 o Ha Noi", "Bút Sơn"),
    ("cap dien CXV-150 gia bao nhieu", "CXV-150"),
]

_ROW_RE = re.compile(r"<tr>.*?</tr>", re.DOTALL)
_MONEY_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})+")


def cos(a, b) -> float:
    return sum(x * y for x, y in zip(a, b)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    )


def split_to_cap(chunk: dict, cap: int, count_tokens) -> list[dict]:
    """Row-wise split with the header repeated in every piece — the same shape
    split_oversized_table_chunk produces, just at a smaller budget."""
    if chunk["type"] != "table" or cap is None:
        return [chunk]
    if count_tokens(chunk["content"]) <= cap:
        return [chunk]
    rows = _ROW_RE.findall(chunk["content"])
    if len(rows) < 3:
        return [chunk]
    head, body = rows[0], rows[1:]
    head_tok = count_tokens(head) + 12
    out, cur, cur_tok = [], [head], head_tok
    for r in body:
        t = count_tokens(r)
        if cur_tok + t > cap and len(cur) > 1:
            out.append(cur)
            cur, cur_tok = [head], head_tok
        cur.append(r)
        cur_tok += t
    if len(cur) > 1:
        out.append(cur)
    return [{**chunk, "content": "<table>\n" + "\n".join(g) + "\n</table>"} for g in out] or [chunk]


async def embed_all(client, texts: list[str], clip, batch: int = 64) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        r = await client.embeddings.create(
            model=EMBED_MODEL, input=[clip(t) or " " for t in texts[i : i + batch]]
        )
        out.extend(d.embedding for d in r.data)
    return out


async def main() -> int:
    import tiktoken
    from openai import AsyncOpenAI
    from sqlalchemy import text as sql

    from app.db.postgres.base import get_session

    enc = tiktoken.get_encoding("cl100k_base")
    count_tokens = lambda t: len(enc.encode(t, disallowed_special=()))  # noqa: E731

    def clip(t: str) -> str:
        ids = enc.encode(t, disallowed_special=())
        return enc.decode(ids[:8000]) if len(ids) > 8000 else t

    base = json.load(open(CHUNKS))

    async with get_session() as s:
        rows = (
            await s.execute(
                sql(
                    "select region, price_ex_vat from material_prices "
                    "where manufacturer ilike '%cadivi%'"
                )
            )
        ).fetchall()
    gold: dict[str, set[str]] = {}
    for r, p in rows:
        gold.setdefault(r, set()).add(f"{p:.0f}")
    total_gold = sum(len(v) for v in gold.values())
    print(f"đối chứng: {total_gold} giá CADIVI ({ {k: len(v) for k, v in gold.items()} })\n")

    client = AsyncOpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    )

    print(
        f"{'trần token':>11} {'#chunk':>7} {'recall@5':>9} {'phủ CADIVI top5':>17} "
        f"{'top10':>8} {'token/5chunk':>13} {'suất hữu ích':>13}"
    )
    for cap in CAPS:
        pieces: list[dict] = []
        for c in base:
            pieces.extend(split_to_cap(c, cap, count_tokens))
        texts = ["\n".join(p for p in (c["above"], c["content"], c["below"]) if p) for c in pieces]
        vecs = await embed_all(client, texts, clip)
        qvecs = await embed_all(client, [q for q, _ in QUERIES] + [CADIVI_Q], clip)

        hits = 0
        for qi, (_, target) in enumerate(QUERIES):
            gold_idx = {i for i, c in enumerate(pieces) if target.lower() in c["content"].lower()}
            top = sorted(range(len(vecs)), key=lambda i: cos(qvecs[qi], vecs[i]), reverse=True)[:5]
            if gold_idx & set(top):
                hits += 1

        cq = qvecs[-1]
        ranked = sorted(range(len(vecs)), key=lambda i: cos(cq, vecs[i]), reverse=True)

        def coverage(k: int) -> tuple[int, int, int]:
            blob = "\n".join(pieces[i]["content"] for i in ranked[:k])
            nums = {n.replace(",", "").replace(".", "") for n in _MONEY_RE.findall(blob)}
            got = sum(len(v & nums) for v in gold.values())
            toks = sum(count_tokens(pieces[i]["content"]) for i in ranked[:k])
            useful = sum(1 for i in ranked[:k] if "cadivi" in pieces[i]["content"].lower())
            return got, toks, useful

        g5, t5, u5 = coverage(5)
        g10, _, _ = coverage(10)
        print(
            f"{str(cap or 'không'):>11} {len(pieces):>7} {hits:>7}/16 "
            f"{g5:>9}/{total_gold:<6} {g10:>4}/{total_gold:<3} {t5:>13,} {u5:>10}/5"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
