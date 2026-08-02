#!/usr/bin/env python3
"""Regenerate section 4 of docs/bo-cau-hoi-benchmark.md from the code.

    python scripts/bench_docs_gen.py

The question list exists in exactly one place — bench_questions.py — and the
docs table is derived from it. Writing the table by hand guarantees the two
drift apart the first time a question is retuned, and a benchmark whose
documentation describes a different question set than the one that ran is
worse than no documentation.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from scripts.bench_questions import QUESTIONS  # noqa: E402

DOC = pathlib.Path(__file__).resolve().parent.parent / "docs" / "bo-cau-hoi-benchmark.md"
MARKER = "## 4. Danh sách 30 câu hỏi"

TIER_TITLES = {
    "T1": "T1 · nhiễu — thứ được hỏi không tồn tại, hoặc chỉ có hàng xóm gần giống",
    "T2": "T2 · suy luận — cần nhiều lượt tra, hoặc một phép quy đổi",
    "T3": "T3 · tiếp nối — câu hỏi chỉ có nghĩa cùng lượt trước",
    "T4": "T4 · tra cứu — một giá, nhưng tên hỏi lệch với tên lưu",
    "T5": "T5 · trực tiếp — tên hỏi khớp sát tên lưu",
}


def criteria(q) -> str:
    bits: list[str] = []
    if q.expect_refusal:
        bits.append("**phải nói không có dữ liệu**")
    if q.expect_values:
        vals = " hoặc ".join(f"`{v:,}`".replace(",", ".") for v in q.expect_values)
        bits.append("nêu được " + vals)
    if q.expect_text:
        bits.append("có " + ", ".join(f"`{t}`" for t in q.expect_text))
    if q.forbid:
        bits.append("không được chứa " + ", ".join(f"`{t}`" for t in q.forbid))
    if q.expect_tool:
        bits.append(f"gọi `{q.expect_tool}`")
    return "; ".join(bits) or "—"


def main() -> int:
    out = [MARKER, ""]
    for tier in ("T1", "T2", "T3", "T4", "T5"):
        qs = [q for q in QUESTIONS if q.tier == tier]
        out += [f"### {TIER_TITLES[tier]}", ""]
        for q in qs:
            out.append(f"**{q.qid}** — {q.question}")
            out.append("")
            if q.history:
                prev = q.history[0]["content"]
                out.append(f"> *lượt trước:* {prev}")
                out.append("")
            out.append(f"- *đạt khi:* {criteria(q)}")
            if q.note:
                out.append(f"- *vì sao có câu này:* {q.note}")
            out.append("")
    body = "\n".join(out)

    text = DOC.read_text()
    head, sep, _ = text.partition(MARKER)
    assert sep, f"không tìm thấy mốc {MARKER!r} trong {DOC}"
    DOC.write_text(head + body)
    print(f"đã ghi {len(QUESTIONS)} câu vào {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
