#!/usr/bin/env python3
"""Render sections 3.3 and 3.4 of docs/bao-cao-benchmark.md from the run files.

    python scripts/bench_report_gen.py [.bench_cache/results_tools.json]

Reads `results_tools.json` (the agentic run) and, if it exists,
`results_ragonly.json` (the same questions with no tools) to render the
tool-vs-RAG-only comparison as section 3.4.

Same reason as bench_docs_gen.py: a report whose numbers were retyped by hand
is a report nobody can re-verify. Everything here is derived from the runs'
own output files.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from scripts.bench_agentic import CACHE_DIR, CONFIGS  # noqa: E402
from scripts.bench_questions import QUESTIONS  # noqa: E402

DOC = pathlib.Path(__file__).resolve().parent.parent / "docs" / "bao-cao-benchmark.md"
MARKER = "### 3.3. Kết quả"
TIERS = ["T1", "T2", "T3", "T4", "T5"]
TIER_NAME = {
    "T1": "nhiễu",
    "T2": "suy luận",
    "T3": "tiếp nối",
    "T4": "tra cứu",
    "T5": "trực tiếp",
}


def rag_section(tools: dict, rag: dict) -> list[str]:
    """Section 3.4 — the same 30 questions with the tools taken away.

    Only meaningful next to the tool run, so it is rendered as a difference
    rather than a standalone table: the interesting quantity is how many
    questions stop working when the deterministic lookup is removed.
    """
    names = [n for n in CONFIGS if n in rag]
    out = [
        "### 3.4. Nếu bỏ hoàn toàn công cụ — chỉ còn RAG thuần",
        "",
        "Cùng 30 câu hỏi, cùng vector, cùng `top_k = 5`, nhưng model **không "
        "được cấp tool nào**: nó chỉ có 5 chunk truy hồi được và phải tự rút "
        "câu trả lời ra từ đó.",
        "",
        "Lời nhắc hệ thống cũng đổi theo — bản dùng cho chế độ Agentic ra lệnh "
        "*\"PHẢI gọi công cụ tương ứng\"*, giữ nguyên nó khi không có công cụ "
        "nào là bắt model làm việc bất khả thi, và sẽ đo sự bối rối thay vì đo "
        "năng lực. Bản RAG thuần giữ đúng phần cốt lõi: chỉ trả lời từ tư "
        "liệu, không bịa số, không có thì nói không có.",
        "",
        "Điều kiện chấm `expect_tool` được bỏ qua (chấm trượt vì \"không gọi "
        "tool\" khi không có tool là đo thiết lập của bộ đo). 20 câu chốt giá "
        "trị số và 6 câu phải-từ-chối vẫn chấm y như cũ — đó mới là phép thử "
        "thật cho RAG thuần.",
        "",
        "| cấu hình | có tool | RAG thuần | chênh lệch |",
        "|---|---:|---:|---:|",
    ]
    for n in names:
        t = sum(r["passed"] for r in tools.get(n, []))
        g = sum(r["passed"] for r in rag[n])
        nt = len(tools.get(n, [])) or len(rag[n])
        out.append(f"| {CONFIGS[n][0]} | {t}/{nt} | **{g}/{len(rag[n])}** | {g - t:+d} |")

    out += ["", "#### Điểm RAG thuần theo mức độ khó", "",
            "| cấu hình | " + " | ".join(f"{t} {TIER_NAME[t]}" for t in TIERS) + " |",
            "|---|" + "---:|" * len(TIERS)]
    for n in names:
        cells = []
        for t in TIERS:
            sel = [r for r in rag[n] if r["tier"] == t]
            cells.append(f"{sum(r['passed'] for r in sel)}/{len(sel)}")
        out.append(f"| {CONFIGS[n][0]} | " + " | ".join(cells) + " |")

    out += ["", "#### Câu nào mất đi khi bỏ công cụ", "",
            "Câu **đạt khi có tool** nhưng **trượt khi chỉ có RAG** — đây là "
            "phần công việc mà truy hồi vector không làm thay được.", "",
            "| câu | mức | " + " | ".join(CONFIGS[n][0] for n in names) + " |",
            "|---|---|" + "---|" * len(names)]
    lost_any = 0
    for q in QUESTIONS:
        marks = []
        for n in names:
            t = next((x for x in tools.get(n, []) if x["qid"] == q.qid), None)
            g = next((x for x in rag[n] if x["qid"] == q.qid), None)
            if t and g and t["passed"] and not g["passed"]:
                marks.append("**mất**")
            elif t and g and not t["passed"] and g["passed"]:
                marks.append("thêm")
            else:
                marks.append("—")
        if any(m != "—" for m in marks):
            lost_any += 1
            out.append(f"| {q.qid} | {q.tier} | " + " | ".join(marks) + " |")
    if not lost_any:
        out.append("| — | — | " + " | ".join("—" for _ in names) + " |")
    out.append("")
    return out


def main() -> int:
    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else str(pathlib.Path(CACHE_DIR) / "results_tools.json")
    )
    data = json.load(open(path))
    names = [n for n in CONFIGS if n in data]
    by_qid = {q.qid: q for q in QUESTIONS}

    out = [
        MARKER,
        "",
        "#### Điểm tổng",
        "",
        "| cấu hình | đạt | tỷ lệ | gọi tool | giây/câu |",
        "|---|---:|---:|---:|---:|",
    ]
    for n in names:
        rs = data[n]
        ok = sum(r["passed"] for r in rs)
        tool = sum(1 for r in rs if r["tools"]) / len(rs)
        sec = sum(r["seconds"] for r in rs) / len(rs)
        out.append(
            f"| {CONFIGS[n][0]} | **{ok}/{len(rs)}** | {ok / len(rs):.0%} "
            f"| {tool:.0%} | {sec:.1f} |"
        )

    out += ["", "#### Điểm theo mức độ khó", "", "| cấu hình | " + " | ".join(
        f"{t} {TIER_NAME[t]}" for t in TIERS) + " |", "|---|" + "---:|" * len(TIERS)]
    for n in names:
        cells = []
        for t in TIERS:
            sel = [r for r in data[n] if r["tier"] == t]
            cells.append(f"{sum(r['passed'] for r in sel)}/{len(sel)}")
        out.append(f"| {CONFIGS[n][0]} | " + " | ".join(cells) + " |")

    # Per-question matrix: which questions separate the configurations at all.
    out += ["", "#### Câu nào phân biệt được các cấu hình", "",
            "Câu mà **mọi** cấu hình cùng đạt hoặc cùng trượt không mang thông "
            "tin so sánh. Bảng dưới chỉ liệt kê những câu có kết quả khác nhau "
            "giữa các cấu hình.", "",
            "| câu | mức | " + " | ".join(CONFIGS[n][0] for n in names) + " |",
            "|---|---|" + "---|" * len(names)]
    split = 0
    for q in QUESTIONS:
        marks = []
        for n in names:
            r = next((x for x in data[n] if x["qid"] == q.qid), None)
            marks.append("✔" if r and r["passed"] else "✘")
        if len(set(marks)) > 1:
            split += 1
            out.append(f"| {q.qid} | {q.tier} | " + " | ".join(marks) + " |")
    if not split:
        out.append("| — | — | " + " | ".join("—" for _ in names) + " |")

    always_ok = sum(
        1
        for q in QUESTIONS
        if all(
            next((x for x in data[n] if x["qid"] == q.qid), {"passed": False})["passed"]
            for n in names
        )
    )
    always_bad = sum(
        1
        for q in QUESTIONS
        if all(
            not next((x for x in data[n] if x["qid"] == q.qid), {"passed": True})["passed"]
            for n in names
        )
    )
    out += ["", f"Trong {len(QUESTIONS)} câu: **{always_ok}** câu mọi cấu hình "
            f"đều đạt, **{always_bad}** câu mọi cấu hình đều trượt, "
            f"**{split}** câu phân biệt được.", ""]

    # Every remaining failure, spelled out — a benchmark that hides its
    # failures is a marketing document.
    out += ["#### Toàn bộ câu trượt, theo cấu hình", ""]
    for n in names:
        fails = [r for r in data[n] if not r["passed"]]
        out.append(f"**{CONFIGS[n][0]}** — {len(fails)} câu trượt")
        out.append("")
        if not fails:
            out += ["Không có.", ""]
            continue
        out += ["| câu | mức | vì sao trượt |", "|---|---|---|"]
        for r in sorted(fails, key=lambda r: r["qid"]):
            q = by_qid[r["qid"]]
            out.append(f"| {r['qid']} | {r['tier']} | {r['reason']} |")
        out.append("")

    rag_path = pathlib.Path(CACHE_DIR) / "results_ragonly.json"
    if rag_path.exists():
        out += rag_section(data, json.load(open(rag_path)))

    text = DOC.read_text()
    head, sep, rest = text.partition(MARKER)
    assert sep, f"không tìm thấy mốc {MARKER!r}"
    # Keep everything from the next top-level section onwards; 3.3 and 3.4 are
    # both regenerated here, so the cut has to land after them.
    idx = rest.find("\n## ")
    tail = rest[idx:] if idx != -1 else "\n"
    DOC.write_text(head + "\n".join(out) + tail)
    print(f"đã ghi kết quả {len(names)} cấu hình vào {DOC}")
    if rag_path.exists():
        print("  (kèm mục 3.4 — RAG thuần)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
