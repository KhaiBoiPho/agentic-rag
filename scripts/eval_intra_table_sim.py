#!/usr/bin/env python3
"""How alike are two pieces of the SAME table, at different token caps?

Run INSIDE the app container (needs /tmp/chunks.json):

    python scripts/eval_intra_table_sim.py

Why this matters, beyond the token arithmetic. Every piece of a split table
repeats the same header, and the header is a fixed cost: at a 3.000-token cap
it is 4-6% of a piece, at 800 it is 16-18%. The worry is not only wasted
tokens — it is that the shared text pushes the pieces' vectors together. Two
pieces that embed nearly identically are indistinguishable to retrieval: it
cannot prefer the one holding the answer, so a top-k window either swallows
several near-duplicates or misses the right one for no reason a score can
explain.

This measures that directly: split every table, embed the pieces, and report
the cosine between every pair of pieces that came from the same table.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import statistics
from collections import defaultdict

CHUNKS = "/tmp/chunks.json"
EMBED_MODEL = "openai/text-embedding-3-small"
CAPS = [3000, 800]


def cos(a, b) -> float:
    return sum(x * y for x, y in zip(a, b)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    )


def histogram(values: list[float]) -> str:
    edges = [0.90, 0.95, 0.97, 0.98, 0.99, 1.01]
    labels = ["<0.90", "0.90–0.95", "0.95–0.97", "0.97–0.98", "0.98–0.99", "≥0.99"]
    counts = [0] * len(labels)
    for v in values:
        for i, e in enumerate(edges):
            if v < e:
                counts[i] += 1
                break
        else:
            counts[-1] += 1
    n = max(len(values), 1)
    return "\n".join(
        f"      {lab:>10}  {c:5}  {c / n * 100:5.1f}%  {'█' * round(c / n * 40)}"
        for lab, c in zip(labels, counts)
    )


async def main() -> int:
    import tiktoken
    from openai import AsyncOpenAI

    from scripts.eval_chunk_cap import split_to_cap

    enc = tiktoken.get_encoding("cl100k_base")
    tok = lambda t: len(enc.encode(t, disallowed_special=()))  # noqa: E731

    def clip(t: str) -> str:
        ids = enc.encode(t, disallowed_special=())
        return enc.decode(ids[:8000]) if len(ids) > 8000 else t

    base = [c for c in json.load(open(CHUNKS)) if c["type"] == "table"]
    client = AsyncOpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    )

    for cap in CAPS:
        groups: dict[str, list[str]] = defaultdict(list)
        for idx, c in enumerate(base):
            pieces = split_to_cap(c, cap, tok)
            if len(pieces) < 2:
                continue  # nothing to compare it against
            for p in pieces:
                groups[f"{idx}"].append(p["content"])

        texts, owner = [], []
        for gid, ps in groups.items():
            for p in ps:
                texts.append(p)
                owner.append(gid)
        if not texts:
            print(f"trần {cap}: không bảng nào bị cắt")
            continue

        vecs: list[list[float]] = []
        for i in range(0, len(texts), 64):
            r = await client.embeddings.create(
                model=EMBED_MODEL, input=[clip(t) or " " for t in texts[i : i + 64]]
            )
            vecs.extend(d.embedding for d in r.data)

        by_group: dict[str, list[list[float]]] = defaultdict(list)
        for g, v in zip(owner, vecs):
            by_group[g].append(v)

        sims: list[float] = []
        for vs in by_group.values():
            for i in range(len(vs)):
                for j in range(i + 1, len(vs)):
                    sims.append(cos(vs[i], vs[j]))

        pieces_total = len(texts)
        print(
            f"── trần {cap}: {len(by_group)} bảng bị cắt → {pieces_total} mảnh, "
            f"{len(sims):,} cặp cùng bảng ──"
        )
        print(
            f"      trung vị={statistics.median(sims):.4f}  "
            f"trung bình={statistics.fmean(sims):.4f}  "
            f"min={min(sims):.4f}  max={max(sims):.4f}"
        )
        print(
            f"      ≥0.95: {sum(1 for s in sims if s >= 0.95) / len(sims) * 100:.1f}%   "
            f"≥0.98: {sum(1 for s in sims if s >= 0.98) / len(sims) * 100:.1f}%"
        )
        print(histogram(sims))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
