#!/usr/bin/env python3
"""Benchmark the Agentic path across embedding × generation model.

Run INSIDE the app container:

    PYTHONPATH=/app python scripts/bench_agentic.py --configs all
    PYTHONPATH=/app python scripts/bench_agentic.py --configs base --limit 5

Why a harness instead of hitting /api/v1/chat: the four configurations differ
in EMBEDDING model, and Qdrant collections are created with a fixed vector
size (1536 for text-embedding-3-small, 1024 for voyage-4-large). Comparing
them through the live endpoint would mean rebuilding the collection between
runs — slow, and it leaves the app unusable for whichever config is not
currently loaded.

So retrieval is done in-memory here: chunks are pulled from Qdrant once,
embedded once per embedding model (cached on disk), and scored by cosine.
Everything downstream of retrieval is the REAL code path — the same system
prompt, the same context-chunk formatting, the same separate-system-message
placement, and the same run_tool_loop with the same three tool schemas
hitting the same Postgres. Only the vectors change.

Grading is deterministic (see bench_questions.py); no LLM judge, because a
judge introduces its own variance into a measurement meant to compare models.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field

from scripts.bench_retrieval import BM25Index, rrf_fuse

# Deliberately NOT /tmp. Embedding the 3.645-chunk corpus costs real money and
# ~25 minutes for voyage-4-large, and /tmp inside the container is wiped every
# time it restarts — which already threw that work away once. This path sits
# under the repo root, which is bind-mounted from the host, so the vectors
# survive container restarts and can be reused by later benchmark runs.
# Override with BENCH_CACHE_DIR when running outside the container.
CACHE_DIR = os.environ.get(
    "BENCH_CACHE_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".bench_cache"),
)
TOP_K = 5
SCORE_THRESHOLD = 0.5

# How many candidates each arm contributes before fusion. Deliberately far
# larger than TOP_K: the entire point of the sparse arm is to promote a chunk
# the dense arm ranked OUTSIDE the window, which cannot happen if both arms
# are cut to the window size before they are fused.
PREFETCH = 50

_SMALL = "openai/text-embedding-3-small"
_VOYAGE = "voyageai/voyage-4-large"

# `gemini-2.5-pro` used to be here and has been removed rather than merely
# left unused. It cost 4,8× the time of gpt-4o-mini to buy 1 question — inside
# the ±1 measurement noise of §5.2 — and with the unchanged embedding it
# actually scored WORSE (22/30 vs 26/30). Keeping it in the table invited
# re-running it out of habit.
#
# The generation models below are chosen for two properties this corpus
# demands: reading HTML price tables, and holding a ~15.000-token context
# (TOP_K=5 × the 3.000-token table cap) without losing the middle of it. Note
# the context WINDOW is not the constraint — every candidate is ≥128k. What is
# being measured is whether the middle of that context is actually used.
#
# (nhãn, model embedding, model sinh, hybrid dense+BM25)
CONFIGS: dict[str, tuple[str, str, str, bool]] = {
    # Mốc so sánh: model đang chạy thật.
    "base": ("small + 4o-mini", _SMALL, "openai/gpt-4o-mini", False),
    "voy": ("voyage + 4o-mini", _VOYAGE, "openai/gpt-4o-mini", False),
    # Đo BM25: cùng model sinh, cùng corpus, chỉ khác tầng truy hồi — nên
    # chênh lệch trong mỗi cặp dense/hybrid là đóng góp của riêng BM25.
    # gemini-2.5-flash vì §4.2 đo được họ Gemini đọc bảng HTML này hơn hẳn
    # 4o-mini, và flash giữ điểm mạnh đó ở 1/4 giá của pro.
    "fs": ("small + flash", _SMALL, "google/gemini-2.5-flash", False),
    "fsb": ("small+BM25 + flash", _SMALL, "google/gemini-2.5-flash", True),
    "fv": ("voyage + flash", _VOYAGE, "google/gemini-2.5-flash", False),
    "fvb": ("voyage+BM25 + flash", _VOYAGE, "google/gemini-2.5-flash", True),
    # ─── Lưới model × tầng truy hồi, trên CÙNG một corpus ───────────────────
    # Vì sao phải là một lưới chứ không phải vài cấu hình rời: phép đo cũ so
    # MODEL nhưng cố định tầng truy hồi ở dense; phép đo BM25 so TẦNG TRUY HỒI
    # nhưng cố định model ở flash. Hai bảng đó không chung một ô nào, nên
    # không bảng nào kết luận được "model nào tốt nhất" hay "tầng nào tốt
    # nhất" — mỗi bảng chỉ đúng trong điều kiện của riêng nó. Lưới đầy đủ tách
    # được ba câu: so theo HÀNG ra model, so theo CỘT ra tầng truy hồi, ô cao
    # nhất ra cặp nên dùng.
    #
    # Chỉ có model rẻ. gemini-2.5-pro bị loại hoàn toàn (§4.4: 4,8× thời gian
    # để mua 1 câu, nằm trong nhiễu ±1). Hệ quả phải nói rõ khi đọc kết quả:
    # kết luận rút ra được chỉ là "TRONG NHÓM MODEL RẺ, X tốt nhất", không
    # phải "X tốt bằng pro" — không đo pro thì mệnh đề đó không kiểm chứng
    # được. Trần trên để đối chiếu lấy từ phép đo tầng truy hồi
    # (eval_hybrid_recall.py), vốn tất định và chặn mọi model cùng lúc.
    #
    # voyage+BM25 was very nearly left out of the grid, on the grounds that
    # flash had already measured it at +0 over voyage+dense (§9.1) — so
    # multiplying it across models looked like paying for a known answer.
    # That reasoning rested on ONE model, and the grid then showed BM25's
    # effect is strongly model-dependent: it bought 4o-mini +7 where voyage
    # bought it only +2. Whether BM25 is redundant once the embedding is
    # strong is therefore unknown outside flash, and the cell stays in.
    "g4_sd": ("4o-mini · small+dense", _SMALL, "openai/gpt-4o-mini", False),
    "g4_sb": ("4o-mini · small+BM25", _SMALL, "openai/gpt-4o-mini", True),
    "g4_vd": ("4o-mini · voyage+dense", _VOYAGE, "openai/gpt-4o-mini", False),
    "g4_vb": ("4o-mini · voyage+BM25", _VOYAGE, "openai/gpt-4o-mini", True),
    "hk_sd": ("haiku4.5 · small+dense", _SMALL, "anthropic/claude-haiku-4.5", False),
    "hk_sb": ("haiku4.5 · small+BM25", _SMALL, "anthropic/claude-haiku-4.5", True),
    "hk_vd": ("haiku4.5 · voyage+dense", _VOYAGE, "anthropic/claude-haiku-4.5", False),
    "hk_vb": ("haiku4.5 · voyage+BM25", _VOYAGE, "anthropic/claude-haiku-4.5", True),
}

# Named sets, so the docs can name a run instead of a comma list someone has
# to retype correctly.
GROUPS: dict[str, list[str]] = {
    "all": list(CONFIGS),
    "bm25": ["fs", "fsb", "fv", "fvb"],
    "baseline": ["base", "voy"],
    # The 8 cells that complete the 3-model × 4-arm grid; flash already
    # supplies its own four (fs / fsb / fv / fvb).
    "grid": ["g4_sd", "g4_sb", "g4_vd", "hk_sd", "hk_sb", "hk_vd"],
    "grid2": ["g4_vb", "hk_vb"],
}


class BenchInfraError(RuntimeError):
    """The API failed us, as opposed to the model answering badly. Kept
    separate because the two must never end up in the same column."""


@dataclass
class Retrieved:
    """Duck-types the retriever's result so _format_context_chunk works."""

    content: str
    document_name: str = ""
    region: str = ""
    price_period: str = ""
    score: float = 0.0
    chunk_id: str = ""


@dataclass
class Outcome:
    qid: str
    tier: str
    passed: bool
    reason: str
    tools: list[str] = field(default_factory=list)
    answer: str = ""
    seconds: float = 0.0


def _fold(s: str) -> str:
    """Accent- and case-insensitive form, so grading does not hinge on
    whether the model wrote 'Bút Sơn' or 'But Son'."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn"
    )


_DIGITS_RE = re.compile(r"\d[\d.,\s]*\d|\d")


def _numbers_in(text: str) -> set[int]:
    """Every integer the answer states, separators removed, so 1.140.000 and
    1,140,000 and '1 140 000' all compare equal."""
    out: set[int] = set()
    for m in _DIGITS_RE.findall(text):
        digits = re.sub(r"[^\d]", "", m)
        if digits:
            out.add(int(digits))
    return out


def cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    )


async def dump_chunks() -> list[dict]:
    """Pull every chunk out of Qdrant once; cached so repeated runs are cheap."""
    path = f"{CACHE_DIR}/chunks.json"
    if os.path.exists(path):
        return json.load(open(path))

    from app.db.qdrant.client import QdrantStore

    # Reuse the app's own store rather than building a client from settings —
    # host/port/https/api_key handling lives there and has already diverged
    # once between local and Railway.
    store = QdrantStore()
    client = store._client
    out: list[dict] = []
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=store._collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in points:
            pl = p.payload or {}
            out.append(
                {
                    "chunk_id": str(p.id),
                    "content": pl.get("content", ""),
                    "full_content": pl.get("full_content") or pl.get("content", ""),
                    "document_name": pl.get("document_name", ""),
                    "region": pl.get("region", ""),
                    "price_period": pl.get("price_period", ""),
                }
            )
        if offset is None:
            break
    os.makedirs(CACHE_DIR, exist_ok=True)
    json.dump(out, open(path, "w"))
    return out


async def embed_texts(model: str, texts: list[str], tag: str, manifest: dict | None = None) -> list[list[float]]:
    """Embed once, keep the vectors on disk, never pay for them twice.

    Two levels of persistence, because the corpus pass is the expensive part
    of this whole benchmark (~25 minutes and real money for voyage-4-large):

    · a finished file, reused verbatim by every later run;
    · a `.partial` checkpoint written every few batches, so a crash, a 403,
      or a killed container resumes where it stopped instead of starting the
      corpus over.
    """
    safe = model.replace("/", "_")
    # The key includes a digest of the TEXTS, not just their count. Keying on
    # count alone silently reuses stale vectors the moment a question is
    # reworded or a document re-ingested — the benchmark would then score new
    # questions against old embeddings and look perfectly healthy doing it.
    digest = hashlib.sha256("\x00".join(texts).encode()).hexdigest()[:12]
    path = f"{CACHE_DIR}/emb_{safe}_{tag}_{digest}.json"
    manifest_path = path + ".manifest.json"
    expected_manifest = {
        "config_id": (manifest or {}).get("config_id", tag),
        "chunk_limit": (manifest or {}).get("chunk_limit"),
        "chunk_count": len(texts),
        "chunk_content_digest": digest,
        "embedding_model": model,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "code_commit": os.environ.get("BENCH_CODE_COMMIT", "working-tree"),
    }
    if os.path.exists(path):
        cached = json.load(open(path))
        if len(cached) != len(texts):
            raise ValueError(f"embedding cache length mismatch: {path}")
        if not os.path.exists(manifest_path):
            raise ValueError(f"embedding cache has no manifest: {path}")
        saved = json.load(open(manifest_path))
        for key in ("chunk_count", "chunk_content_digest", "embedding_model"):
            if saved.get(key) != expected_manifest.get(key):
                raise ValueError(f"embedding cache manifest mismatch ({key}): {path}")
        return cached

    import tiktoken
    from openai import AsyncOpenAI

    enc = tiktoken.get_encoding("cl100k_base")

    def clip(t: str) -> str:
        ids = enc.encode(t or " ", disallowed_special=())
        return enc.decode(ids[:7000]) if len(ids) > 7000 else (t or " ")

    client = AsyncOpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    )
    os.makedirs(CACHE_DIR, exist_ok=True)
    partial_path = path + ".partial"
    out: list[list[float]] = []
    if os.path.exists(partial_path):
        try:
            out = json.load(open(partial_path))
            print(f"    tiếp tục từ mốc đã lưu: {len(out)}/{len(texts)}")
        except Exception:
            out = []

    batch = 32
    for i in range(len(out), len(texts), batch):
        for attempt in range(4):
            try:
                r = await client.embeddings.create(
                    model=model, input=[clip(t) for t in texts[i : i + batch]]
                )
                out.extend(d.embedding for d in r.data)
                break
            except Exception as exc:
                if attempt == 3:
                    json.dump(out, open(partial_path, "w"))
                    print(f"    dừng ở {len(out)}/{len(texts)} — đã lưu mốc, chạy lại sẽ tiếp tục")
                    raise
                print(f"    lỗi embed lô {i} ({exc.__class__.__name__}), thử lại…")
                await asyncio.sleep(2 * (attempt + 1))
        if i and i % (batch * 20) == 0:
            json.dump(out, open(partial_path, "w"))
            print(f"    …đã embed {len(out)}/{len(texts)} (đã lưu mốc)")

    json.dump(out, open(path, "w"))
    json.dump(expected_manifest, open(manifest_path, "w"), ensure_ascii=False, indent=2)
    if os.path.exists(partial_path):
        os.remove(partial_path)
    print(f"    đã lưu {len(out)} vector: {path}")
    return out


def select_chunks(qvec, cvecs, bm25, query: str) -> list[tuple[int, float]]:
    """Pick the TOP_K chunk indices, dense-only or dense+BM25 fused.

    Returns (index, cosine) pairs; the cosine is carried through for display
    only. In hybrid mode it is NOT the ranking score — RRF ranks by position,
    not magnitude — so it must never be filtered on downstream.

    The threshold is applied INSIDE the dense arm rather than after fusion, on
    purpose. RRF scores are sums of 1/(60+rank), i.e. well under 0,1, so
    reusing SCORE_THRESHOLD=0,5 on the fused list would discard every result
    for every query and read as "found no sources" rather than as a bug.
    """
    dense = sorted(((cos(qvec, v), i) for i, v in enumerate(cvecs)), key=lambda t: -t[0])
    cosines = {i: s for s, i in dense}

    if bm25 is None:
        return [(i, s) for s, i in dense[:TOP_K] if s >= SCORE_THRESHOLD]

    dense_rank = [i for s, i in dense if s >= SCORE_THRESHOLD][:PREFETCH]
    sparse_rank = bm25.top(query, PREFETCH)
    return [(i, cosines.get(i, 0.0)) for i in rrf_fuse([dense_rank, sparse_rank], TOP_K)]


async def run_one(
    q, chunks, cvecs, qvec, gen_model, system_prompt, fmt, no_tools: bool = False, bm25=None
) -> Outcome:
    from app.core.llm.tool_loop import run_tool_loop

    # The sparse arm sees `q.question` alone, exactly as the dense arm does
    # (qvecs are embedded from the same field). For the T3 follow-ups that
    # means both arms retrieve on a fragment like "còn ở TPHCM thì sao?" —
    # weak, but weak identically, so the dense/hybrid comparison stays fair.
    hits = [
        Retrieved(
            content=chunks[i]["content"],
            document_name=chunks[i]["document_name"],
            region=chunks[i]["region"],
            price_period=chunks[i]["price_period"],
            score=s,
            chunk_id=chunks[i]["chunk_id"],
        )
        for i, s in select_chunks(qvec, cvecs, bm25, q.question)
    ]

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if hits:
        ctx = "\n\n".join(fmt(i, c) for i, c in enumerate(hits))
        if no_tools:
            # RAG-only has no tool to defer to, so the instruction that makes
            # the agentic path work ("PHẢI gọi công cụ") would be an order to
            # do something impossible. What replaces it has to preserve the
            # part that actually matters — that inventing a price is worse
            # than admitting the documents do not contain one.
            guidance = (
                f"Tư liệu tham khảo lấy từ kho tri thức:\n{ctx}\n\n"
                "CHỈ được trả lời dựa trên tư liệu trên. Không dùng kiến thức "
                "riêng để bổ sung con số. Nếu tư liệu không chứa thông tin "
                "được hỏi, phải nói rõ là không tìm thấy trong tài liệu — "
                "tuyệt đối không suy đoán giá."
            )
        else:
            guidance = (
                "Tư liệu tham khảo lấy từ kho tri thức (có thể KHÔNG chứa câu "
                f"trả lời):\n{ctx}\n\n"
                "Tư liệu này KHÔNG thay thế công cụ. Với câu hỏi về ĐƠN GIÁ vật "
                "liệu hoặc dự toán chi phí, PHẢI gọi công cụ tương ứng — kể cả "
                "khi tư liệu trên trông đã đủ, và NHẤT LÀ khi tư liệu không "
                "nhắc tới vật liệu được hỏi. Chỉ được kết luận 'không có dữ "
                "liệu' sau khi công cụ đã trả về không tìm thấy."
            )
        messages.append({"role": "system", "content": guidance})
    messages += [*q.history, {"role": "user", "content": q.question}]

    t0 = time.perf_counter()
    try:
        if no_tools:
            from app.core.llm.openrouter import OpenRouterClient

            answer, log = await OpenRouterClient().chat(messages, model=gen_model), []
        else:
            answer, log = await run_tool_loop(messages, model=gen_model)
    except Exception as exc:
        # An infrastructure failure is NOT a wrong answer, and must never be
        # scored as one: a 403 from an exhausted key would otherwise render as
        # "0/30 — this model is terrible". Raise so the caller can abandon the
        # configuration instead of publishing a fabricated score.
        raise BenchInfraError(f"{type(exc).__name__}: {exc}") from exc
    dt = time.perf_counter() - t0

    tools = [e.get("name", "") for e in log]
    passed, reason = grade(q, answer, tools, no_tools=no_tools)
    return Outcome(q.qid, q.tier, passed, reason, tools, answer, dt)


def grade(q, answer: str, tools: list[str], no_tools: bool = False) -> tuple[bool, str]:
    """Deterministic. Order matters: a wrong number is a worse failure than a
    missing tool call, so value checks are reported first.

    In RAG-only mode `expect_tool` is skipped rather than failed — there are
    no tools to call, so scoring their absence would measure the harness
    setting instead of the system."""
    folded = _fold(answer)

    if q.expect_refusal:
        # Deliberately broad. A model that says "không có thông tin cụ thể"
        # and then offers labelled alternatives HAS done the right thing —
        # scoring that as a failure would reward the terse phrasing rather
        # than the honesty, which is the opposite of what is being measured.
        said_no = any(
            k in folded
            for k in (
                "khong tim thay",
                "khong tim duoc",
                "khong co du lieu",
                "khong co thong tin",
                "khong co gia",
                "khong co ban",
                "khong san co",
                "khong ton tai",
                "khong xuat hien",
                "khong nam trong",
                "chua co du lieu",
                "chua co thong tin",
            )
        )
        if not said_no:
            return False, "phải nói không có dữ liệu nhưng lại trả lời"
        # …but the refusal must not be undone by quoting a forbidden number
        # as though it were the answer.
        for s in q.forbid:
            if _fold(s) in folded:
                return False, f"có từ chối, nhưng vẫn nêu {s!r}"
        return True, "từ chối đúng"

    if q.expect_values:
        got = _numbers_in(answer)
        if not (set(q.expect_values) & got):
            return False, f"thiếu giá đúng {q.expect_values} (nêu: {sorted(got)[:6]})"

    for s in q.forbid:
        if _fold(s) in folded:
            return False, f"chứa nội dung sai: {s!r}"

    missing = [s for s in q.expect_text if _fold(s) not in folded]
    if missing:
        return False, f"thiếu nội dung: {missing}"

    if not no_tools and q.expect_tool and q.expect_tool not in tools:
        return False, f"không gọi {q.expect_tool} (đã gọi: {tools or 'không gọi gì'})"

    return True, "đạt"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="base")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(CACHE_DIR, "bench_results.json"))
    ap.add_argument(
        "--questions",
        default="",
        help="JSON bộ câu hỏi sinh; bỏ trống thì dùng bộ 30 câu viết tay",
    )
    ap.add_argument(
        "--no-tools",
        action="store_true",
        help="RAG thuần: không đưa tool nào cho model, chỉ ngữ cảnh truy hồi",
    )
    a = ap.parse_args()

    from app.api.v1.chat import _DEFAULT_SYSTEM, _format_context_chunk
    from scripts.bench_questions import QUESTIONS, Q

    if a.questions:
        # Bộ sinh từ material_prices (gen_benchmark_from_db.py). Nó KHÔNG thay
        # bộ 30 câu viết tay: bộ viết tay dựng từ lỗi thật đã quan sát và đo
        # được cả từ chối lẫn gọi tool, còn bộ sinh chỉ đo tra cứu theo mẫu.
        # Chạy cả hai và báo cáo riêng.
        raw = json.load(open(a.questions))
        fields = set(Q.__dataclass_fields__)
        QUESTIONS = [Q(**{k: v for k, v in r.items() if k in fields}) for r in raw]
        print(f"bộ câu hỏi: {a.questions} ({len(QUESTIONS)} câu)")

    questions = QUESTIONS[: a.limit] if a.limit else QUESTIONS
    names = GROUPS.get(a.configs) or a.configs.split(",")
    unknown = [n for n in names if n not in CONFIGS]
    if unknown:
        print(f"cấu hình không có: {unknown}. Có: {list(CONFIGS)} hoặc nhóm {list(GROUPS)}")
        return 1

    print("nạp chunk từ Qdrant…")
    chunks = await dump_chunks()
    print(f"  {len(chunks)} chunk")

    # Built once, over the same `full_content` that gets embedded, so the two
    # arms are ranking the identical text and the only difference is how.
    bm25_index = None
    if any(CONFIGS[n][3] for n in names):
        bm25_index = BM25Index.build([c["full_content"] for c in chunks])
        print(f"  chỉ mục BM25: {len(bm25_index.idf)} từ khác nhau")
    print()

    all_results: dict[str, list[Outcome]] = {}
    abandoned: dict[str, str] = {}

    def save() -> None:
        """Written after EVERY configuration, not once at the end. The first
        run of this benchmark lost two completed configurations because the
        third hit a 403 and the process was killed before the single final
        write."""
        json.dump(
            {n: [vars(o) for o in v] for n, v in all_results.items()},
            open(a.out, "w"),
            ensure_ascii=False,
            indent=1,
        )

    for name in names:
        label, emb_model, gen_model, hybrid = CONFIGS[name]
        mode = " — RAG THUẦN, KHÔNG TOOL" if a.no_tools else ""
        arm = "dense+BM25 (RRF)" if hybrid else "dense"
        print(f"══ {label} ══  (embed={emb_model}, sinh={gen_model}, truy hồi={arm}{mode})")

        try:
            cvecs = await embed_texts(emb_model, [c["full_content"] for c in chunks], "corpus")
            qvecs = await embed_texts(
                emb_model, [q.question for q in questions], f"q{len(questions)}"
            )
        except Exception as exc:
            abandoned[name] = f"embedding hỏng — {type(exc).__name__}: {exc}"
            print(f"  ✖ BỎ DỞ: {abandoned[name]}\n")
            continue

        outcomes: list[Outcome] = []
        for q, qv in zip(questions, qvecs):
            try:
                o = await run_one(
                    q,
                    chunks,
                    cvecs,
                    qv,
                    gen_model,
                    _DEFAULT_SYSTEM,
                    _format_context_chunk,
                    no_tools=a.no_tools,
                    bm25=bm25_index if hybrid else None,
                )
            except BenchInfraError as exc:
                abandoned[name] = str(exc)
                print(f"  ✖ BỎ DỞ ở {q.qid}: {exc}")
                print("     (không chấm điểm cấu hình này — lỗi hạ tầng, "
                      "không phải model trả lời sai)\n")
                outcomes = []
                break
            outcomes.append(o)
            mark = "✔" if o.passed else "✘"
            print(f"  {mark} [{o.tier}] {q.qid:6} {o.reason[:78]}")

        if not outcomes:
            continue
        all_results[name] = outcomes
        save()
        ok = sum(o.passed for o in outcomes)
        print(f"  → {ok}/{len(outcomes)}\n")

    names = [n for n in names if n in all_results]
    if abandoned:
        print("\nCẤU HÌNH BỎ DỞ (không có điểm — đừng đọc là 0 điểm):")
        for n, why in abandoned.items():
            print(f"  · {CONFIGS[n][0]}: {why[:160]}")
    if not names:
        print("\nKhông cấu hình nào chạy trọn vẹn.")
        return 1

    print("\n" + "=" * 74)
    print(f"{'cấu hình':22} {'đạt':>9} {'tool':>7} {'giây/câu':>10}")
    for name in names:
        label = CONFIGS[name][0]
        os_ = all_results[name]
        ok = sum(o.passed for o in os_)
        tool_rate = sum(1 for o in os_ if o.tools) / max(len(os_), 1)
        avg = sum(o.seconds for o in os_) / max(len(os_), 1)
        print(f"{label:22} {ok:>4}/{len(os_):<4} {tool_rate:>6.0%} {avg:>10.1f}")

    tiers = sorted({q.tier for q in questions})
    print(f"\n{'cấu hình':22}" + "".join(f"{t:>12}" for t in tiers))
    for name in names:
        row = ""
        for t in tiers:
            sel = [o for o in all_results[name] if o.tier == t]
            row += f"{sum(o.passed for o in sel):>7}/{len(sel):<5}"
        print(f"{CONFIGS[name][0]:22}{row}")

    save()
    print(f"\nchi tiết: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
