#!/usr/bin/env python3
"""Compare what TABLE chunks are embedded as: HTML markup vs a prose rendering.

Run INSIDE the app container, after scripts/dump chunks to /tmp/chunks.json:

    python scripts/eval_table_embedding.py

Why: a table chunk is currently embedded as its HTML, and a question naming a
brand scored 0.576 against the chunk that actually holds the answer — below
three unrelated chunks. Two things drag it down. The markup itself is noise
(24 `<td>` pairs per row carry no meaning), and, worse, the values a question
combines often live in different columns: in the Hà Nội annex the name cell
reads "Xi măng bao PCB40" while "Bút Sơn" sits in the manufacturer cell, so
the two words the user typed are separated by three unrelated columns.

Rendering each row as "Tên: …, Đơn vị: …, Nhà sản xuất: …, Giá: …" removes
the markup and puts every column of one product in one continuous sentence.
Nothing is invented — it is the same cells, joined to their column labels.

The evaluation is retrieval-only and offline: it embeds every chunk both
ways, embeds the queries, and reports where the chunk that provably contains
the answer lands. Ground truth is objective — a chunk is correct iff its text
contains the target string — so this measures ranking, not answer wording.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import sys

CHUNKS = "/tmp/chunks.json"
EMBED_MODEL = "openai/text-embedding-3-small"

# (câu hỏi, chuỗi phải có trong chunk đúng). Chosen so the answer is
# unambiguous: each target appears in a handful of chunks at most.
QUERIES: list[tuple[str, str]] = [
    # thương hiệu nằm ở cột NHÀ SẢN XUẤT, không nằm trong tên vật liệu
    ("Giá xi măng Bút Sơn PCB40 ở Hà Nội bao nhiêu?", "Bút Sơn"),
    ("Xi măng Vicem Bút Sơn bao 50kg giá bao nhiêu một tấn?", "Bút Sơn"),
    # mã sản phẩm kỹ thuật
    ("Cáp điện CXV-150 0,6/1kV giá bao nhiêu một mét?", "CXV-150"),
    ("Cáp vặn xoắn LV-ABC-4x95 giá bao nhiêu?", "LV-ABC-4x95"),
    ("Đèn led DHP-STR02A 30W giá bao nhiêu một bộ?", "DHP-STR02A"),
    # tên dài, nhiều thuộc tính
    ("Cửa sổ nhôm Topal XFAD dày 1.4mm kính Việt Nhật giá bao nhiêu m2?", "Topal XFAD"),
    ("Y lọc gang FAF 2500 DN65 giá bao nhiêu?", "FAF 2500"),
    # thương hiệu phổ biến, dễ lẫn giữa nhiều nhà cung cấp
    ("Xi măng Sông Gianh PCB40 đóng bao giá bao nhiêu?", "Sông Gianh"),
    ("Xi măng Nghi Sơn giá bao nhiêu một tấn?", "Nghi Sơn"),
    ("Tôn Hoa Sen mạ kẽm giá bao nhiêu?", "Hoa Sen"),
    ("Xi măng Vicem Hà Tiên Xây tô giá bao nhiêu?", "Vicem Hà Tiên Xây tô"),
    # bẫy: "xi măng" khớp cả vật liệu chống thấm gốc xi măng
    ("Vật liệu chống thấm gốc xi măng polymer giá bao nhiêu?", "chống thấm gốc xi măng"),
    # vật liệu rời, đơn vị m3
    ("Giá cát san lấp ở TPHCM là bao nhiêu một khối?", "cát san lấp"),
    ("Đá 1x2 giá bao nhiêu một m3?", "đá 1x2"),
    # KHÔNG DẤU — thứ làm thứ hạng đảo ngược ở phép đo riêng
    ("gia xi mang But Son PCB40 o Ha Noi", "Bút Sơn"),
    ("cap dien CXV-150 gia bao nhieu", "CXV-150"),
]

_ROW_RE = re.compile(r"<tr>.*?</tr>", re.DOTALL)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _cells(row_html: str) -> list[str]:
    return [re.sub(r"\s+", " ", _TAG_RE.sub("", c)).strip() for c in _CELL_RE.findall(row_html)]


def table_to_prose(html: str) -> str:
    """Each data row becomes "<nhãn cột>: <giá trị>, …" on its own line.

    The header row supplies the labels. Cells that are empty are dropped —
    "Ghi chú: " with nothing after it is noise, and dropping it costs no
    information. If the table has no usable header the rows are joined
    plainly, which is still better than markup."""
    rows = _ROW_RE.findall(html)
    if not rows:
        return _TAG_RE.sub(" ", html)
    head = _cells(rows[0])
    out: list[str] = []
    for row in rows[1:]:
        cells = _cells(row)
        if not any(c for c in cells):
            continue
        parts = []
        for i, c in enumerate(cells):
            if not c:
                continue
            label = head[i].strip() if i < len(head) and head[i].strip() else ""
            parts.append(f"{label}: {c}" if label else c)
        if parts:
            out.append(", ".join(parts))
    return "\n".join(out) if out else _TAG_RE.sub(" ", html)


def table_to_plain(html: str) -> str:
    """Same rows, tags stripped, cells joined by " | " — no column labels.

    Isolates the two halves of the prose idea: this removes the markup noise
    without paying the label repetition that makes prose 10% longer."""
    rows = _ROW_RE.findall(html)
    if not rows:
        return _TAG_RE.sub(" ", html)
    out = []
    for row in rows:
        cells = [c for c in _cells(row) if c]
        if cells:
            out.append(" | ".join(cells))
    return "\n".join(out)


def cos(a, b) -> float:
    return sum(x * y for x, y in zip(a, b)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    )


def clip(text: str, max_tokens: int = 8000) -> str:
    """Trim to the embeddings API's input cap, counting real tokens.

    Needed because the prose rendering is LONGER than the HTML for a
    multi-row table: `<td>` is 4 characters, while repeating a label like
    "Tên vật liệu/loại vật liệu xây dựng: " costs 36 per cell. In production
    that is handled by split_oversized_table_chunk; here the chunk is simply
    clipped, which affects both variants the same way."""
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    ids = enc.encode(text, disallowed_special=())
    return enc.decode(ids[:max_tokens]) if len(ids) > max_tokens else text


async def embed_all(client, texts: list[str], batch: int = 64) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        chunk = [clip(t) or " " for t in texts[i : i + batch]]
        r = await client.embeddings.create(model=EMBED_MODEL, input=chunk)
        out.extend(d.embedding for d in r.data)
        print(f"   ...{min(i + batch, len(texts))}/{len(texts)}", end="\r", flush=True)
    print(" " * 40, end="\r")
    return out


def report(name: str, ranks: list[int | None]) -> dict:
    found = [r for r in ranks if r is not None]
    at = lambda k: sum(1 for r in found if r <= k)  # noqa: E731
    mrr = sum(1 / r for r in found) / len(ranks)
    print(
        f"{name:22} recall@1={at(1):2}/{len(ranks)}  @3={at(3):2}/{len(ranks)}  "
        f"@5={at(5):2}/{len(ranks)}  @10={at(10):2}/{len(ranks)}  MRR={mrr:.3f}"
    )
    return {"r1": at(1), "r3": at(3), "r5": at(5), "r10": at(10), "mrr": mrr}


async def main() -> int:
    from openai import AsyncOpenAI

    chunks = json.load(open(CHUNKS))
    print(f"{len(chunks)} chunk ({sum(1 for c in chunks if c['type'] == 'table')} bảng)\n")

    # What each variant actually sends to the embeddings API. `full_content`
    # is context_above + content + context_below (models.py), so both variants
    # keep the context — only the table body differs.
    def full(c: dict, body: str) -> str:
        return "\n".join(p for p in (c["above"], body, c["below"]) if p)

    html_texts = [full(c, c["content"]) for c in chunks]
    prose_texts = [
        full(c, table_to_prose(c["content"]) if c["type"] == "table" else c["content"])
        for c in chunks
    ]

    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    tb = [i for i, c in enumerate(chunks) if c["type"] == "table"]
    th = sum(len(enc.encode(html_texts[i], disallowed_special=())) for i in tb)
    tp = sum(len(enc.encode(prose_texts[i], disallowed_special=())) for i in tb)
    over_h = sum(1 for i in tb if len(enc.encode(html_texts[i], disallowed_special=())) > 8000)
    over_p = sum(1 for i in tb if len(enc.encode(prose_texts[i], disallowed_special=())) > 8000)
    print(
        f"token chunk bảng: HTML {th:,} | văn xuôi {tp:,} "
        f"({(tp / th - 1) * 100:+.0f}%) — vượt 8000 tok: {over_h} vs {over_p}\n"
    )

    plain_texts = [
        full(c, table_to_plain(c["content"]) if c["type"] == "table" else c["content"])
        for c in chunks
    ]

    client = AsyncOpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    )
    print("embed bản HTML..."), sys.stdout.flush()
    html_vecs = await embed_all(client, html_texts)
    print("embed bản văn xuôi..."), sys.stdout.flush()
    prose_vecs = await embed_all(client, prose_texts)
    print("embed bản bỏ thẻ (không nhãn)..."), sys.stdout.flush()
    plain_vecs = await embed_all(client, plain_texts)
    print("embed câu hỏi..."), sys.stdout.flush()
    q_vecs = await embed_all(client, [q for q, _ in QUERIES])

    truth = [
        {i for i, c in enumerate(chunks) if t.lower() in c["content"].lower()} for _, t in QUERIES
    ]

    rows = []
    ranks = {"html": [], "prose": [], "plain": []}
    for qi, ((q, t), gold) in enumerate(zip(QUERIES, truth)):
        line = {"q": q, "target": t, "gold": len(gold)}
        for key, vecs in (("html", html_vecs), ("prose", prose_vecs), ("plain", plain_vecs)):
            scored = sorted(((cos(q_vecs[qi], v), i) for i, v in enumerate(vecs)), reverse=True)
            rank = next((r for r, (_, i) in enumerate(scored, 1) if i in gold), None)
            ranks[key].append(rank)
            line[key] = rank
            line[key + "_top"] = scored[0][0]
        rows.append(line)

    print(f"\n{'câu hỏi':50} {'HTML':>6} {'VĂNXUÔI':>8} {'BỎTHẺ':>7}")
    for r in rows:
        print(
            f"{r['q'][:48]:50} {str(r['html'] or '—'):>6} "
            f"{str(r['prose'] or '—'):>8} {str(r['plain'] or '—'):>7}"
        )

    print()
    h = report("HTML (hiện tại)", ranks["html"])
    pr = report("VĂN XUÔI (có nhãn)", ranks["prose"])
    pl = report("BỎ THẺ (không nhãn)", ranks["plain"])
    print()
    for name, v in (("văn xuôi", pr), ("bỏ thẻ", pl)):
        print(
            f"{name:10} so với HTML: recall@1 {v['r1'] - h['r1']:+d}, "
            f"recall@5 {v['r5'] - h['r5']:+d}, MRR {v['mrr'] - h['mrr']:+.3f}"
        )
    json.dump(rows, open("/tmp/eval_result.json", "w"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
