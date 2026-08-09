#!/usr/bin/env python3
"""Chunking theo bảng so với recursive thông thường — đo, không phỏng đoán.

Run INSIDE the app container:

    PYTHONPATH=/app python scripts/eval_chunking_strategy.py

Phần I của báo cáo chứng minh trần 3.000 token là điểm tối ưu **trong số các
mức trần**, nhưng chưa bao giờ so đường chunking-theo-bảng với đường mà mọi hệ
RAG dùng khi không xử lý bảng riêng: trích text thô rồi cắt đệ quy. Script này
đóng lỗ hổng đó.

Bốn nhánh, để recursive không bị dựng thành bù nhìn
---------------------------------------------------
    bang        ChunkDispatcher hiện tại — pdfplumber -> <table> HTML, lọc
                text theo bbox bảng, _resolve_header, add_table_context,
                enforce_chunk_caps (trần 3.000)
    rec512      RecursiveCharacterTextSplitter, 512 token — mặc định của dự án
    rec1500     ..., 1.500 token
    rec3000     ..., 3.000 token — CÙNG kích thước với trần bảng

Nhánh rec3000 là nhánh đối chứng then chốt: cùng ngân sách token mỗi chunk,
chỉ khác **có hiểu cấu trúc bảng hay không**. So bảng 3.000 với recursive 512
là so kích thước, không phải so phương pháp.

Recursive nhận text thô từ PyMuPDF `get_text()` — đúng thứ một đường ống ngây
thơ nhìn thấy. Đây KHÔNG phải cách làm cho nó yếu đi một cách bất công: chính
§2.5 đã đo rằng PyMuPDF trả nội dung ô bảng ra thành các block rời, thứ tự khó
đoán (trang 69 của phụ lục điện Đà Nẵng: 10/12 block nằm trong bbox bảng, một
block là địa chỉ dính liền một cái giá). Đó là đầu vào thật của recursive.

Chỉ số Tầng 1 — toàn vẹn cấu trúc
----------------------------------
Không cần embedding, không cần model, không cần truy hồi. Đây là tầng mạnh
nhất cho một luận văn vì nó đo **trực tiếp điều mà chunking bảng tuyên bố làm
được**, và chạy trên toàn bộ 11.784 dòng `material_prices` chứ không phải trên
30 câu hỏi:

    toàn vẹn dòng   material_name và price_ex_vat có nằm CÙNG một chunk không.
                    Tách ra là dòng đó vĩnh viễn không trả lời đúng được —
                    không truy hồi nào cứu nổi, không model nào rút ra được.
    dính header     chunk chứa dòng dữ liệu có kèm nhãn cột không (§2.7).
    nhiễu chéo      một chunk chứa bao nhiêu đơn giá KHÁC nhau. Càng nhiều,
                    càng dễ lấy nhầm giá hàng xóm — kiểu lỗi ở §4.1.
    chi phí         số chunk và tổng token phải embed.

Tầng 2 (recall truy hồi) và Tầng 3 (điểm trả lời) chạy riêng, vì chúng cần
embedding và model sinh; Tầng 1 chạy miễn phí trong vài giây và đã đủ trả lời
câu hỏi cơ chế.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import unicodedata
from collections import Counter
from pathlib import Path

from scripts.ingest_kb_docx import DOCUMENTS, ROOT

logging.disable(logging.CRITICAL)
_log = logging.getLogger("eval")

OVERLAP_PCT = 15
RECURSIVE_SIZES = (512, 1500, 3000)

# Corpus chỉ-PDF. File .md đi qua TextChunker, nơi mọi chunk được gán
# ChunkType.TEXT — không <table> HTML, không _resolve_header, không
# add_table_context. Chúng không đi qua tầng xử lý bảng nào nên chỉ làm loãng
# phép so chunking bảng. Đo được: 578/2.054 chunk của corpus đầy đủ là từ .md,
# và cả 5 file .md cho ĐÚNG 0 chunk bảng.
PDF_DOCS = [d for d in DOCUMENTS if d[0].lower().endswith(".pdf")]

# Nhãn cột quen thuộc, để đo "chunk có kèm header không". Cùng tinh thần với
# _HEADER_LABELS của table_extract.py nhưng đã bỏ dấu.
_HEADER_WORDS = (
    "ten vat lieu",
    "don vi",
    "don gia",
    "gia ban",
    "quy cach",
    "nha san xuat",
    "tieu chuan",
    "ghi chu",
    "stt",
)

_MONEY_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})+|\d{4,}")
_WS_RE = re.compile(r"\s+")


def fold(s: str) -> str:
    """Bỏ dấu, thường hoá, gộp khoảng trắng.

    Gộp khoảng trắng là bắt buộc chứ không phải làm đẹp: price_extractor đã
    gộp xuống dòng trong tên khi lưu ("Đá xây\\ndựng" -> "Đá xây dựng", §5.4),
    nên muốn so tên trong DB với text của chunk thì hai bên phải cùng dạng.
    """
    out = "".join(
        c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn"
    ).replace("đ", "d")
    return _WS_RE.sub(" ", out).strip()


def digits(s: str) -> str:
    return re.sub(r"[^0-9]", "", s)


# ─── Dựng bốn tập chunk ─────────────────────────────────────────────────────


def chunks_table_aware() -> list[str]:
    """Đúng đường ống đang chạy thật, kể cả trần 3.000."""
    from app.core.chunking.base import enforce_chunk_caps
    from app.core.chunking.dispatcher import ChunkDispatcher

    out: list[str] = []
    for rel, _, _ in PDF_DOCS:
        path = ROOT / rel
        chunks = ChunkDispatcher(
            chunk_token_num=512, overlap_percent=OVERLAP_PCT, table_context_size=128
        ).chunk(
            filename=path.name,
            content=path.read_bytes(),
            document_id="d",
            kb_id="k",
        )
        # full_content là thứ thực sự đem đi embed (§2.1), nên nó mới là văn
        # bản phải đem so — không phải content.
        out += [c.full_content for c in enforce_chunk_caps(chunks, "d", _log)]
    return out


def raw_text(path: Path) -> str:
    """Text thô, không biết gì về bảng — đầu vào của một đường ống ngây thơ."""
    if path.suffix.lower() == ".pdf":
        import fitz

        with fitz.open(path) as doc:
            return "\n".join(page.get_text() for page in doc)
    return path.read_text("utf-8", errors="replace")


def chunks_recursive(size: int) -> list[str]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=size,
        chunk_overlap=int(size * OVERLAP_PCT / 100),
    )
    out: list[str] = []
    for rel, _, _ in PDF_DOCS:
        out += splitter.split_text(raw_text(ROOT / rel))
    return out


# ─── Tầng 1 ─────────────────────────────────────────────────────────────────


async def price_rows() -> list[tuple[str, str]]:
    """(tên đã bỏ dấu, chuỗi chữ số của đơn giá) cho mọi dòng giá."""
    from sqlalchemy import text as sql

    from app.db.postgres.base import get_session

    async with get_session() as s:
        # Lọc theo PDF cho khớp corpus: dòng giá trích từ .md không bao giờ
        # xuất hiện trong corpus chỉ-PDF, nên tính chúng là "mất hẳn" sẽ bôi
        # đen mọi nhánh như nhau và làm loãng chỉ số toàn vẹn.
        res = await s.execute(
            sql(
                "select mp.material_name, mp.price_ex_vat from material_prices mp "
                "join documents d on d.id = mp.document_id "
                "where d.filename ilike '%.pdf'"
            )
        )
        return [(fold(n), digits(f"{float(p):.0f}")) for n, p in res if n]


def integrity_breakdown(chunks: list[str], rows: list[tuple[str, str]]) -> dict:
    """Tách 'mất hẳn' khỏi 'bị tách rời' — hai hỏng hóc khác nhau về bản chất.

    Một dòng bị TÁCH RỜI vẫn còn trong corpus: truy hồi có thể mang về mảnh
    chứa giá, và một cửa sổ rộng hơn hoặc một cách chia khác sẽ cứu được nó.
    Một dòng MẤT HẲN thì không cách nào cứu — giá của nó không tồn tại trong
    bất kỳ chunk nào, nên không truy hồi hay model nào chạm tới được.

    Gộp hai thứ này vào một con số 'toàn vẹn' sẽ giấu mất điều đáng lo nhất.
    """
    folded = [fold(c) for c in chunks]
    by_price: dict[str, list[int]] = {}
    for i, f in enumerate(folded):
        for d in {digits(m) for m in _MONEY_RE.findall(f)}:
            by_price.setdefault(d, []).append(i)

    intact = split = missing = 0
    for nm, pr in rows:
        cand = by_price.get(pr)
        if not cand:
            missing += 1
        elif any(nm and nm in folded[i] for i in cand):
            intact += 1
        else:
            split += 1
    return {"nguyen_ven": intact, "tach_roi": split, "mat_han": missing}


def measure(name: str, chunks: list[str], rows: list[tuple[str, str]]) -> dict:
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    folded = [fold(c) for c in chunks]

    # Đảo chỉ mục theo GIÁ trước, rồi mới soi tên trong số ít chunk ứng viên.
    # Quét thẳng 11.784 dòng × ~n chunk là hàng chục triệu phép so chuỗi; đi
    # qua giá trước cắt nó xuống còn vài chục nghìn.
    by_price: dict[str, list[int]] = {}
    prices_per_chunk: list[int] = []
    for i, f in enumerate(folded):
        found = {digits(m) for m in _MONEY_RE.findall(f)}
        prices_per_chunk.append(len(found))
        for d in found:
            by_price.setdefault(d, []).append(i)

    intact = 0
    with_header = 0
    for nm, pr in rows:
        cand = by_price.get(pr)
        if not cand:
            continue
        hit = [i for i in cand if nm and nm in folded[i]]
        if hit:
            intact += 1
            if any(sum(w in folded[i] for w in _HEADER_WORDS) >= 2 for i in hit):
                with_header += 1

    toks = [len(enc.encode(c, disallowed_special=())) for c in chunks]
    return {
        "ten": name,
        "n_chunk": len(chunks),
        "tong_token": sum(toks),
        "tb_token": sum(toks) // max(len(toks), 1),
        "max_token": max(toks, default=0),
        "toan_ven": intact,
        "co_header": with_header,
        "nhieu_cheo": round(sum(prices_per_chunk) / max(len(chunks), 1), 1),
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/app/.bench_cache/chunking_tier1.json")
    ap.add_argument(
        "--tier2",
        action="store_true",
        help="đo thêm recall truy hồi (cần embedding — có cache nên chỉ tốn lần đầu)",
    )
    ap.add_argument(
        "--tier3",
        action="store_true",
        help="đo thêm điểm trả lời 30 câu (tốn chi phí sinh, KHÔNG cache được)",
    )
    ap.add_argument("--model", default="anthropic/claude-haiku-4.5")
    ap.add_argument(
        "--sizes",
        default="",
        help="cỡ chunk recursive cần so, vd '1500'; bỏ trống = 512,1500,3000",
    )
    ap.add_argument(
        "--modes",
        default="dense,hybrid",
        help="nhánh truy hồi cho Tầng 3",
    )
    ap.add_argument(
        "--questions",
        default="",
        help="JSON bộ câu hỏi cho Tầng 2; bỏ trống thì dùng 20 câu chốt giá của bộ viết tay",
    )
    a = ap.parse_args()

    rows = await price_rows()
    print(f"đối chứng: {len(rows)} dòng giá trong material_prices\n")

    sizes = [int(x) for x in a.sizes.split(",")] if a.sizes else list(RECURSIVE_SIZES)
    arms: list[tuple[str, list[str]]] = [("bảng (hiện tại)", chunks_table_aware())]
    for s in sizes:
        arms.append((f"recursive {s}", chunks_recursive(s)))

    results = [{**measure(n, c, rows), **integrity_breakdown(c, rows)} for n, c in arms]

    hdr = (
        f"{'nhánh':18}{'#chunk':>8}{'tb tok':>8}{'max tok':>9}"
        f"{'toàn vẹn dòng':>16}{'kèm header':>13}{'giá/chunk':>11}"
    )
    print(hdr)
    print("─" * len(hdr))
    for r in results:
        pct = 100 * r["toan_ven"] / max(len(rows), 1)
        hpct = 100 * r["co_header"] / max(r["toan_ven"], 1)
        print(
            f"{r['ten']:18}{r['n_chunk']:>8}{r['tb_token']:>8}{r['max_token']:>9}"
            f"{r['toan_ven']:>9} ({pct:4.1f}%){r['co_header']:>7} ({hpct:3.0f}%)"
            f"{r['nhieu_cheo']:>11}"
        )

    print(f"\n{'nhánh':18}{'nguyên vẹn':>13}{'tách rời':>12}{'MẤT HẲN':>12}")
    print("─" * 55)
    for r in results:
        n = max(len(rows), 1)
        print(
            f"{r['ten']:18}{r['nguyen_ven']:>7} ({100 * r['nguyen_ven'] / n:4.1f}%)"
            f"{r['tach_roi']:>6} ({100 * r['tach_roi'] / n:4.1f}%)"
            f"{r['mat_han']:>6} ({100 * r['mat_han'] / n:4.1f}%)"
        )

    if a.tier2:
        await tier2(arms, rows, a.questions)
    if a.tier3:
        await tier3(arms, a.model, a.questions, a.modes.split(","))

    import json

    json.dump(results, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"\nchi tiết: {a.out}")
    return 0


def load_questions(path: str):
    """Bộ câu hỏi cho Tầng 2: bộ 30 câu viết tay, hoặc bộ sinh từ database.

    Tầng 2 không gọi model sinh, nên nâng cỡ mẫu ở đây gần như miễn phí — chỉ
    tốn một lượt embed câu hỏi. Đó là lý do nó là chỗ đáng nâng nhất: Tầng 3
    trên 200 câu × 4 nhánh × 2 chế độ tốn ~1.600 lượt sinh, còn Tầng 2 tốn một
    lượt embed và giảm nhiễu 3,2 lần.
    """
    from scripts.bench_questions import QUESTIONS, Q

    if not path:
        return [q for q in QUESTIONS if q.expect_values]
    import json as _json

    fields = set(Q.__dataclass_fields__)
    raw = _json.load(open(path))
    # Bộ tra giá chấm bằng `expect_values`, bộ cấu trúc bằng `expect_text` —
    # lọc theo mỗi expect_values sẽ loại sạch bộ thứ hai và trả về 0/0 thay vì
    # báo lỗi, đúng kiểu hỏng im lặng khó thấy nhất.
    return [
        Q(**{k: v for k, v in r.items() if k in fields})
        for r in raw
        if r.get("expect_values") or r.get("expect_text") or r.get("expect_refusal")
    ]


async def tier2(arms: list[tuple[str, list[str]]], rows: list[tuple[str, str]], qpath: str = "") -> None:
    """Tầng 2 — chunk chứa giá đúng có lọt cửa sổ top-5 không.

    Nối cơ chế của Tầng 1 với hệ quả thực tế. Một nhánh giữ được nhiều dòng
    nguyên vẹn hơn vẫn có thể truy hồi tệ hơn, nếu những chunk đó không được
    xếp hạng lên. Chỉ đo cả hai mới biết.

    Dùng lại embed_texts của bench_agentic: khoá cache gồm băm nội dung, nên
    mỗi nhánh có mục cache riêng và chạy lại không tốn tiền.
    """
    from scripts.bench_agentic import PREFETCH, cos, embed_texts
    from scripts.bench_retrieval import BM25Index, rrf_fuse

    qs = load_questions(qpath)
    qtexts = [q.question for q in qs]
    want = [{digits(str(v)) for v in q.expect_values} for q in qs]

    print(f"\nTầng 2 — recall@5 trên {len(qs)} câu chốt giá trị số")
    print(f"{'nhánh':18}{'dense':>10}{'sparse':>10}{'hybrid':>10}")
    print("─" * 48)
    for name, chunks in arms:
        cvecs = await embed_texts("openai/text-embedding-3-small", chunks, f"chunkarm{len(chunks)}")
        qvecs = await embed_texts("openai/text-embedding-3-small", qtexts, f"cq{len(qtexts)}")
        bm = BM25Index.build(chunks)
        folded = [fold(c) for c in chunks]
        money = [{digits(m) for m in _MONEY_RE.findall(f)} for f in folded]

        hits = {"dense": 0, "sparse": 0, "hybrid": 0}
        for q, qv, w in zip(qs, qvecs, want):
            d = [i for _, i in sorted(((cos(qv, v), i) for i, v in enumerate(cvecs)), reverse=True)]
            s = bm.top(q.question, PREFETCH)
            for arm, ids in (
                ("dense", d[:5]),
                ("sparse", s[:5]),
                ("hybrid", rrf_fuse([d[:PREFETCH], s], 5)),
            ):
                if any(money[i] & w for i in ids):
                    hits[arm] += 1
        print(
            f"{name:18}" + "".join(f"{hits[a]:>7}/{len(qs):<3}" for a in ("dense", "sparse", "hybrid"))
        )


async def tier3(arms, model: str, qpath: str = "", modes: list[str] | None = None) -> None:
    """Tầng 3 — điểm trả lời trên 30 câu, RAG thuần, cho từng cách chunk.

    Chạy cả hai nhánh truy hồi vì chúng trả lời hai câu khác nhau: nhánh dense
    là nơi Tầng 2 đo được khoảng cách lớn nhất (4/20 so với 12/20), còn nhánh
    hybrid là cấu hình thực sự đáng ship. Một cách chunk có thể thắng ở nhánh
    này mà không thắng ở nhánh kia, và gộp lại sẽ giấu mất điều đó.

    Dùng lại `run_one` của bench_agentic nguyên vẹn — cùng system prompt, cùng
    `_format_context_chunk`, cùng cách đặt tư liệu vào system message riêng,
    cùng bộ chấm. Chỉ tập chunk là thay đổi.
    """
    modes = modes or ["dense", "hybrid"]

    from app.api.v1.chat import _DEFAULT_SYSTEM, _format_context_chunk

    from scripts.bench_agentic import BenchInfraError, embed_texts, run_one
    from scripts.bench_retrieval import BM25Index

    questions = load_questions(qpath) if qpath else __import__(
        "scripts.bench_questions", fromlist=["QUESTIONS"]
    ).QUESTIONS
    qvecs = await embed_texts(
        "openai/text-embedding-3-small",
        [q.question for q in questions],
        f"q{len(questions)}",
    )

    print(f"\nTầng 3 — điểm trả lời, RAG thuần, sinh bằng {model}")
    detail: list[dict] = []
    print(f"{'nhánh':18}" + "".join(f"{m:>10}" for m in modes))
    print("─" * (18 + 10 * len(modes)))
    for name, texts in arms:
        cvecs = await embed_texts("openai/text-embedding-3-small", texts, f"chunkarm{len(texts)}")
        bm = BM25Index.build(texts)
        # run_one đọc chunk theo khoá dict; nhãn vùng/kỳ để rỗng vì bốn nhánh
        # phải nhận cùng lượng metadata, nếu không là so thêm một biến nữa.
        chunks = [
            {
                "content": t,
                "document_name": "",
                "region": "",
                "price_period": "",
                "chunk_id": str(i),
            }
            for i, t in enumerate(texts)
        ]

        cells = ""
        for mode, use_bm25 in zip(modes, [None if m == "dense" else bm for m in modes]):
            ok = 0
            for q, qv in zip(questions, qvecs):
                try:
                    o = await run_one(
                        q,
                        chunks,
                        cvecs,
                        qv,
                        model,
                        _DEFAULT_SYSTEM,
                        _format_context_chunk,
                        no_tools=True,
                        bm25=use_bm25,
                    )
                except BenchInfraError as exc:
                    print(f"  ✖ {name} bỏ dở ở {q.qid}: {exc}")
                    ok = -1
                    break
                ok += o.passed
                detail.append(
                    {"arm": name, "mode": mode, "qid": o.qid, "tier": o.tier, "passed": o.passed}
                )
            cells += f"{(str(ok) + '/' + str(len(questions))) if ok >= 0 else 'BỎ DỞ':>10}"
        print(f"{name:18}{cells}")

    # Lưu kết quả TỪNG CÂU. Bản đầu chỉ in tổng, nên phân rã theo trục không
    # lấy được nếu không chạy lại toàn bộ — mất $1 cho một thứ đáng lẽ miễn
    # phí. Tổng số che mất khả năng một nhánh thắng ở đúng trục nó được thiết
    # kế để thắng mà thua ba trục còn lại.
    import json as _j

    _j.dump(detail, open("/app/.bench_cache/tier3_detail.json", "w"), ensure_ascii=False)
    print("\nchi tiết từng câu: /app/.bench_cache/tier3_detail.json")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))


# ─── Tầng 1B — đồng vị trí giữa các CỘT ─────────────────────────────────────


async def column_pairs(limit: int = 1500) -> dict[str, list[tuple[str, str]]]:
    """(tên sản phẩm, giá trị cột khác) — để đo hai cột có ở cùng chunk không.

    Tầng 1 đo tên ↔ đơn giá. Nhưng "bảo toàn cấu trúc bảng" còn nghĩa là giữ
    được các cột KHÁC bên cạnh sản phẩm: tiêu chuẩn kỹ thuật, nhà sản xuất.
    Đó chính là chỗ §2.6 (điền ô gộp) sinh ra để phục vụ — ô "tiêu chuẩn" gộp
    suốt một họ sản phẩm, chỉ 1/12 mẫu đèn dính với chuỗi tiêu chuẩn nếu không
    điền.

    Chỉ lấy cột có giá trị ĐỦ HIẾM. Đo bằng cách tìm chuỗi trong chunk, nên
    một đáp án phổ biến sẽ khớp nhờ may: 'cuộn' có mặt ở 20,2% chunk và 'kg' ở
    8,6%, nên cột `unit` không đo được kiểu này. `spec` (TCVN…) và
    `manufacturer` thì ở mức 0,1–1,3%.
    """
    from sqlalchemy import text as sql

    from app.db.postgres.base import get_session

    out: dict[str, list[tuple[str, str]]] = {}
    async with get_session() as s:
        res = await s.execute(
            sql(
                "select distinct material_name, spec from material_prices "
                "where spec is not null and length(spec) between 5 and 60 "
                "and spec ~* '(TCVN|QCVN|IEC|ASTM|JIS|ISO)' limit :lim"
            ),
            {"lim": limit},
        )
        out["tiêu chuẩn"] = [(fold(a), fold(b)) for a, b in res]

        res = await s.execute(
            sql(
                "select distinct material_name, manufacturer from material_prices "
                "where manufacturer is not null and length(manufacturer) between 8 and 60 "
                "limit :lim"
            ),
            {"lim": limit},
        )
        out["nhà sản xuất"] = [(fold(a), fold(b)) for a, b in res]
    return out


def colocation(chunks: list[str], pairs: list[tuple[str, str]]) -> tuple[int, int]:
    """Bao nhiêu cặp (tên, giá trị cột) nằm chung một chunk."""
    folded = [fold(c) for c in chunks]
    hit = 0
    for name, val in pairs:
        if not name or not val:
            continue
        if any(name in f and val in f for f in folded):
            hit += 1
    return hit, len(pairs)
