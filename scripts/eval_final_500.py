#!/usr/bin/env python3
"""Lượt đo cuối — corpus PDF-only, bộ 500 câu, 9 nhánh.

    PYTHONPATH=/app python scripts/eval_final_500.py

Thực hiện bước 2 và 3 của docs/ke-hoach-benchmark-chunking.md trong một lần
chạy: embed 9 biến thể (có cache trên đĩa), rồi đo Tầng 2 (phân bố cosine giữa
các chunk) và Tầng 3 (recall@5 tách theo 8 trục).

Quy ước tên nhánh
----------------
    T       chunking bảng THUẦN — lưới pdfplumber -> <table> HTML, _resolve_header
            cấp lại header cho trang tiếp nối, trần 3.000 token. Đây là phương
            pháp đang được đánh giá.
    T+ctx   T cộng thêm `add_table_context` (pdf_chunker.py:259) — một lớp HẬU
            XỬ LÝ kế thừa từ RAGFlow, gắn text liền kề vào chunk bảng. Đây là
            cấu hình đang chạy trong sản phẩm.

Phân biệt hai cái này là quan trọng: T+ctx thua baseline 11,6 điểm, còn T thì
không. Gộp chúng làm một sẽ quy tội cho phương pháp thay vì cho lớp hậu xử lý.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re

from scripts.eval_chunking_strategy import (
    OVERLAP_PCT,
    PDF_DOCS,
    ROOT,
    _MONEY_RE,
    chunks_recursive,
    digits,
    fold,
    raw_text,
)

logging.disable(logging.CRITICAL)
_log = logging.getLogger("f500")

EMB = "openai/text-embedding-3-small"
TOPK = 5
AXES = ("G1", "G2", "G3", "G4", "S1", "S2", "S3", "S4")

_ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
_CELL = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.S)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _clean(s: str) -> str:
    return _WS.sub(" ", _TAG.sub("", s)).strip()


# ─── Biểu diễn thay thế (dùng chung ranh giới chunk của T) ───────────────────


def _parse(html: str) -> tuple[list[str] | None, list[list[str]]]:
    rows = [[_clean(c) for c in _CELL.findall(r)] for r in _ROW.findall(html)]
    rows = [r for r in rows if r]
    return (rows[0], rows[1:]) if rows else (None, [])


def to_keyvalue(html: str) -> str:
    hdr, body = _parse(html)
    if not hdr or not body:
        return _clean(html)
    return "\n".join(
        " | ".join(f"{hdr[i]}: {c}" for i, c in enumerate(r) if i < len(hdr) and c)
        for r in body
    )


def to_verbalized(html: str) -> str:
    """Chủ ngữ là ô ĐẦU TIÊN KHÔNG RỖNG, không phải ô số 0.

    Cột STT thường rỗng ở các bảng này — hoặc là ô gộp bị pdfplumber trải
    phẳng, hoặc bảng vốn không đánh số. Lấy cứng `r[0]` làm chủ ngữ thì mọi
    hàng đều bị bỏ và cả bảng biến mất khỏi chunk.
    """
    hdr, body = _parse(html)
    if not hdr or not body:
        return _clean(html)
    out = []
    for r in body:
        subj = next((i for i, c in enumerate(r) if c.strip()), None)
        if subj is None:
            continue
        parts = [
            f"{hdr[i].lower()} là {c}"
            for i, c in enumerate(r)
            if i != subj and i < len(hdr) and c.strip()
        ]
        out.append(f"{r[subj]} có " + ", ".join(parts) + "." if parts else r[subj])
    return "\n".join(out)


def rewrite_tables(text: str, fn) -> str:
    """Chỉ viết lại phần <table>…</table>, giữ nguyên văn xuôi quanh nó."""
    return re.sub(r"<table.*?</table>", lambda m: fn(m.group(0)), text, flags=re.S)


# ─── Dựng 9 nhánh ───────────────────────────────────────────────────────────


def table_variants() -> dict[str, list[str]]:
    """Một lần chạy pdfplumber, sinh ra mọi biến thể của nhánh bảng."""
    from app.core.chunking.base import enforce_chunk_caps
    from app.core.chunking.dispatcher import ChunkDispatcher

    out: dict[str, list[str]] = {k: [] for k in ("T3000_CTX", "T3000", "P-kv", "P-verb")}
    for rel, _, _ in PDF_DOCS:
        p = ROOT / rel
        ch = ChunkDispatcher(
            chunk_token_num=512, overlap_percent=OVERLAP_PCT, table_context_size=128
        ).chunk(filename=p.name, content=p.read_bytes(), document_id="d", kb_id="k")
        for c in enforce_chunk_caps(ch, "d", _log):
            # full_content = context_above + content + context_below (base.py:53).
            # content thôi = chunking bảng thuần, KHÔNG có lớp RAGFlow.
            out["T3000_CTX"].append(c.full_content)
            out["T3000"].append(c.content)
            out["P-kv"].append(rewrite_tables(c.full_content, to_keyvalue))
            out["P-verb"].append(rewrite_tables(c.full_content, to_verbalized))
    return out


def table_chunks_at_cap(cap: int) -> list[str]:
    """Build the table-aware arm with an explicit retrieval cap."""
    from app.core.chunking.base import split_oversized_table_chunk
    from app.core.chunking.dispatcher import ChunkDispatcher

    out: list[str] = []
    for rel, _, _ in PDF_DOCS:
        p = ROOT / rel
        raw = ChunkDispatcher(
            chunk_token_num=512, overlap_percent=OVERLAP_PCT, table_context_size=128
        ).chunk(filename=p.name, content=p.read_bytes(), document_id="d", kb_id="k")
        for c in raw:
            out.extend(part.content for part in split_oversized_table_chunk(c, cap))
    return out


def build_arms() -> dict[str, list[str]]:
    tv = table_variants()
    return {
        "R512": chunks_recursive(512),
        "R1500": chunks_recursive(1500),
        "R3000": chunks_recursive(3000),
        "T1500": table_chunks_at_cap(1500),
        "T3000": tv["T3000"],
        "T3000_CTX": tv["T3000_CTX"],
        "P-kv": tv["P-kv"],
        "P-verb": tv["P-verb"],
    }


# ─── Tầng 2 ─────────────────────────────────────────────────────────────────


def tier2(vecs) -> dict:
    """Phân bố cosine giữa các cặp chunk — đo CÁI GIÁ của việc giữ bảng nguyên.

    Tính theo khối để ma trận n×n không bao giờ tồn tại đủ trong RAM cùng lúc.
    """
    import numpy as np

    V = np.asarray(vecs, dtype=np.float32)
    V /= np.linalg.norm(V, axis=1, keepdims=True) + 1e-9
    n = len(V)
    hi90 = hi95 = 0
    tot = 0
    samp: list[np.ndarray] = []
    for i in range(0, n, 512):
        S = V[i : i + 512] @ V.T
        for r in range(S.shape[0]):
            S[r, i + r] = -1.0  # bỏ đường chéo
        flat = S.ravel()
        flat = flat[flat > -0.5]
        hi90 += int((flat >= 0.90).sum())
        hi95 += int((flat >= 0.95).sum())
        tot += flat.size
        samp.append(flat[:: max(flat.size // 20000, 1)])
    s = np.concatenate(samp)
    return {
        "n": n,
        "median": round(float(np.median(s)), 4),
        "p90": round(float(np.percentile(s, 90)), 4),
        "pct90": round(100 * hi90 / max(tot, 1), 3),
        "pct95": round(100 * hi95 / max(tot, 1), 3),
    }


# ─── Tầng 3 ─────────────────────────────────────────────────────────────────


def build_index(chunks: list[str]):
    folded = [fold(c) for c in chunks]
    money = [{digits(m) for m in _MONEY_RE.findall(f)} for f in folded]
    return folded, money


def hit(q: dict, idx: int, folded, money) -> bool:
    if q.get("expect_values"):
        want = {digits(f"{float(v):.0f}") for v in q["expect_values"]}
        return bool(money[idx] & want)
    return any(fold(t) in folded[idx] for t in q.get("expect_text") or [])


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="/app/.bench_cache/gen500.json")
    ap.add_argument("--out", default="/app/.bench_cache/final500.json")
    ap.add_argument("--arms", default="")
    ap.add_argument("--cache-version", default="identity_v2")
    a = ap.parse_args()

    if a.arms and any(x in a.arms.split(",") for x in ("T", "T+ctx")):
        raise SystemExit("Tên arm mơ hồ: dùng T1500, T3000 hoặc T3000_CTX; không dùng T/T+ctx")

    import numpy as np

    from scripts.bench_agentic import embed_texts

    qs = json.load(open(a.questions))
    qv = np.asarray(
        await embed_texts(
            EMB, [q["question"] for q in qs], f"{a.cache_version}_q500_{len(qs)}",
            {"config_id": "queries_500"},
        ), dtype=np.float32
    )
    qv /= np.linalg.norm(qv, axis=1, keepdims=True) + 1e-9
    print(f"{len(qs)} câu hỏi đã embed\n")

    print("đang dựng chunk cho 9 nhánh…")
    arms = build_arms()
    if a.arms:
        keep = set(a.arms.split(","))
        arms = {k: v for k, v in arms.items() if k in keep}
    for k, v in arms.items():
        print(f"  {k:10} {len(v):>5} chunk  {sum(len(x) for x in v) // max(len(v), 1):>6} ký tự/chunk")
    print()

    res: dict[str, dict] = {}
    for name, chunks in arms.items():
        vecs = await embed_texts(
            EMB,
            chunks,
            f"{a.cache_version}_f500_{name.replace('+', 'p')}_{len(chunks)}",
            {"config_id": name, "chunk_limit": 1500 if name in ("T1500", "R1500") else 3000},
        )
        t2 = tier2(vecs)
        V = np.asarray(vecs, dtype=np.float32)
        V /= np.linalg.norm(V, axis=1, keepdims=True) + 1e-9
        folded, money = build_index(chunks)

        per = {ax: [0, 0] for ax in AXES}
        hits: list[int] = []
        for q, v in zip(qs, qv):
            top = np.argpartition(-(V @ v), TOPK)[:TOPK]
            ax = q["tier"]
            per[ax][1] += 1
            ok = any(hit(q, int(i), folded, money) for i in top)
            hits.append(int(ok))
            per[ax][0] += ok
        tot = sum(x[0] for x in per.values())
        # Giữ kết quả TỪNG CÂU để chạy được kiểm định ghép cặp (McNemar). So
        # hai tỷ lệ độc lập bỏ phí thông tin rằng cả hai nhánh trả lời CÙNG
        # một bộ câu hỏi, nên nó là kiểm định yếu hơn hẳn.
        res[name] = {"tier2": t2, "per_axis": per, "total": tot, "n": len(qs), "hits": hits}
        print(f"  ✓ {name:10} recall@5 = {tot}/{len(qs)} ({100 * tot / len(qs):.1f}%)")

    json.dump(res, open(a.out, "w"), ensure_ascii=False, indent=1)

    print("\n── Tầng 2: phân bố cosine giữa các chunk ──")
    print(f"{'nhánh':11}{'#chunk':>8}{'median':>9}{'P90':>8}{'≥0,90':>9}{'≥0,95':>9}")
    print("─" * 54)
    for k, r in res.items():
        t = r["tier2"]
        print(f"{k:11}{t['n']:>8}{t['median']:>9.3f}{t['p90']:>8.3f}{t['pct90']:>8.2f}%{t['pct95']:>8.2f}%")

    print("\n── Tầng 3: recall@5 tách trục ──")
    print(f"{'nhánh':11}{'tổng':>10}" + "".join(f"{ax:>6}" for ax in AXES) + f"{'giá':>7}{'cấu trúc':>10}")
    print("─" * 84)
    for k, r in res.items():
        p = r["per_axis"]
        g = sum(p[x][0] for x in AXES[:4]), sum(p[x][1] for x in AXES[:4])
        s = sum(p[x][0] for x in AXES[4:]), sum(p[x][1] for x in AXES[4:])
        cells = "".join(f"{100 * p[ax][0] / max(p[ax][1], 1):>5.0f}%" for ax in AXES)
        print(
            f"{k:11}{r['total']:>5}/{r['n']:<4}{cells}"
            f"{100 * g[0] / max(g[1], 1):>6.1f}%{100 * s[0] / max(s[1], 1):>9.1f}%"
        )
    print(f"\nchi tiết: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
