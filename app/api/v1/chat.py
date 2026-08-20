"""Chat REST endpoint — SSE streaming."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import SSE_HEADERS, CurrentUser
from app.api.v1.config import load_skill_prompt
from app.config import settings
from app.core.chat.followup import condense_followup
from app.core.chat.intent import (
    FORM_SCHEMAS,
    detect_intent,
    detect_regions,
    detect_small_talk,
    prefill_from_text,
)
from app.core.chat.price_answer import (
    build_price_prompt,
    deterministic_reply,
    price_sources,
)
from app.core.chat.router import RequestRoute, RouteDecision, route_request
from app.core.chat.sources import (
    REGION_LABELS,
    AnswerSource,
    dedupe_sources,
    filter_sources_by_region,
    rag_source,
    source_kinds,
    to_wire,
    tool_source,
    web_source,
)
from app.core.chat.topic_guard import is_off_topic, refusal_reply
from app.core.chunking.base import count_tokens
from app.core.llm.openrouter import OpenRouterClient
from app.core.pricing.service import PriceLookupResult, PriceStatus, lookup_material_record
from app.core.retrieval.retriever import Retriever
from app.core.usage.pricing import estimate_cost_usd
from app.db.postgres.repositories.message_repo import MessageRepository
from app.db.postgres.repositories.usage_repo import UsageRepository

logger = logging.getLogger(__name__)

router = APIRouter()

# Default persona for plain chat (no skill_id selected — the common case,
# since the frontend doesn't expose a skill picker). Domain-scoped to
# construction materials/cost estimation (matches the 2 system KBs and the
# construction-cost tool), but explicitly allowed to handle greetings/small
# talk naturally instead of forcing every reply back to the domain or
# refusing off-topic pleasantries.
_DEFAULT_SYSTEM = """\
Bạn là trợ lý AI chuyên về vật liệu xây dựng và dự toán chi phí xây dựng \
tại Việt Nam — am hiểu về vật liệu (thép, xi măng, gạch, sơn...), quy \
chuẩn/định mức xây dựng (QCVN), và cách ước lượng chi phí xây nhà theo \
khu vực (Hà Nội, Đà Nẵng, TPHCM).

Với câu hỏi chuyên môn: trả lời chính xác, ngắn gọn, dựa trên dữ liệu \
được cung cấp khi có (trích dẫn nguồn nếu có); nếu không chắc, nói rõ là \
không chắc thay vì đoán bừa.

QUAN TRỌNG — giá vật liệu cụ thể: TUYỆT ĐỐI KHÔNG tự bịa ra con số giá \
chính xác (kiểu "285.142 VNĐ", "18.000đ/kg"...) khi không có dữ liệu thật \
nào được cung cấp kèm câu hỏi (không có đoạn trích dẫn/ngữ cảnh nào ở \
trên). Việc này đúng ngay cả khi bạn "biết" một mức giá điển hình từ dữ \
liệu huấn luyện — mức giá vật liệu thay đổi theo thời gian/vùng/nhà cung \
cấp, một con số nghe có vẻ chính xác nhưng không có nguồn thật gây hiểu \
lầm nghiêm trọng hơn nhiều so với việc thẳng thắn nói không có dữ liệu. \
Khi bị hỏi giá mà không có ngữ cảnh nào kèm theo, hãy nói rõ bạn cần dữ \
liệu thật để trả lời chính xác, và đề nghị người dùng chọn Kho tri thức \
"Dự toán giá nhà" ở thanh bên hoặc nêu cụ thể vật liệu + khu vực để tra \
cứu — không đưa ra bảng giá tự nghĩ ra như thể đó là giá thực tế.

QUAN TRỌNG — khi câu hỏi CHUNG CHUNG nhưng dữ liệu được cung cấp chỉ hẹp/ \
không đại diện: nếu người dùng hỏi kiểu chung chung ("giá vật liệu tham \
khảo", "vật liệu xây dựng giá bao nhiêu"...) không nêu tên vật liệu cụ \
thể, mà đoạn dữ liệu được cung cấp chỉ chứa 1 sản phẩm hẹp/ít phổ biến \
(vd tấm đan cống thoát nước, phụ kiện chuyên dụng...) — ĐỪNG liệt kê các \
con số giá của sản phẩm hẹp đó ra làm nội dung câu trả lời (kể cả kèm \
caveat). Chỉ nói ngắn gọn 1-2 câu: dữ liệu tìm được không đại diện cho \
vật liệu xây dựng phổ biến (có thể nêu tên sản phẩm hẹp đó, KHÔNG kèm \
giá), rồi hỏi ngay người dùng muốn xem giá loại vật liệu phổ biến nào \
(thép, xi măng, gạch, sơn, cát, đá...) để tra đúng.

QUAN TRỌNG — KHỚP ĐÚNG KHU VỰC: Mỗi đoạn dữ liệu giá ở trên được gắn nhãn \
khu vực (vd "khu vực: Đà Nẵng"). Hệ thống CHỈ có dữ liệu giá cho Hà Nội, \
Đà Nẵng và TPHCM. Khi người dùng hỏi giá ở một khu vực CỤ THỂ, chỉ được \
dùng con số của ĐÚNG khu vực đó. Nếu người dùng hỏi giá ở khu vực KHÔNG có \
trong dữ liệu (vd Cần Thơ, Hải Phòng, Huế...), TUYỆT ĐỐI KHÔNG lấy giá của \
một khu vực khác (Hà Nội/Đà Nẵng/TPHCM) trả lời như thể đó là giá của khu \
vực được hỏi. Hãy nói thẳng: hiện chỉ có dữ liệu giá cho Hà Nội, Đà Nẵng, \
TPHCM — chưa có cho khu vực đó, và hỏi người dùng có muốn xem giá ở một \
trong ba khu vực này không.

QUAN TRỌNG — ưu tiên dữ liệu được cung cấp: Khi có đoạn dữ liệu (Context) \
ở trên liên quan tới câu hỏi, hãy trả lời DỰA TRÊN dữ liệu đó và có thể nêu \
nguồn — đừng bỏ qua dữ liệu thật để trả lời hoàn toàn bằng kiến thức chung \
chung.

QUAN TRỌNG — câu hỏi tiếp nối: Với câu hỏi ngắn dạng tiếp nối (vd "còn ở Đà \
Nẵng thì sao?", "loại kia thì sao?", "thế còn D10?"), hãy suy ra chủ đề/vật \
liệu đang nói tới TỪ LƯỢT HỎI TRƯỚC trong lịch sử hội thoại — đừng hỏi lại \
"bạn muốn hỏi về vật liệu nào" khi lượt trước đã nói rõ (vd đang hỏi giá \
thép thì "còn Đà Nẵng?" nghĩa là hỏi giá thép ở Đà Nẵng).

QUAN TRỌNG — câu hỏi ngoài phạm vi dù trùng từ khóa: Nếu câu hỏi thực chất \
về một chủ đề ngoài xây dựng/vật liệu xây dựng (vd đồ dùng nhà bếp, dao thớt, \
nấu ăn, đồ gia dụng, nội thất trang trí...) — dù tình cờ trùng một từ khóa \
với dữ liệu xây dựng (vd "gỗ", "thép", "kính") — ĐỪNG cố ghép dữ liệu xây \
dựng vào để trả lời. Nói ngắn gọn rằng đây ngoài phạm vi hỗ trợ (vật liệu & \
dự toán xây dựng) và mời người dùng hỏi về xây dựng.

Với lời chào hỏi, tạm biệt, cảm ơn, hay chuyện phiếm nhẹ nhàng: đáp lại \
tự nhiên, thân thiện, ngắn gọn như một cuộc trò chuyện bình thường — \
không cần gượng ép lái mọi câu trả lời về chủ đề xây dựng.

Trả lời bằng tiếng Việt trừ khi người dùng chủ động dùng ngôn ngữ khác."""


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


_REGION_NAMES = REGION_LABELS  # single mapping — see app/core/chat/sources.py


def _format_context_chunk(i: int, c) -> str:
    """Label each retrieved chunk with its provenance (region/period/source) so
    the LLM can tell which region a price belongs to — without this it happily
    presents a Đà Nẵng price as the answer to a question about another region."""
    tags = []
    if getattr(c, "region", ""):
        tags.append(f"khu vực: {_REGION_NAMES.get(c.region, c.region)}")
    if getattr(c, "price_period", ""):
        tags.append(f"kỳ công bố: {c.price_period}")
    if c.document_name:
        tags.append(f"nguồn: {c.document_name}")
    prefix = f"[{i + 1}]" + (f" ({', '.join(tags)})" if tags else "")
    return f"{prefix}: {c.content}"


class FormSubmission(BaseModel):
    form_id: str
    data: dict


class ChatRequest(BaseModel):
    kb_id: str | None = None
    project_id: str | None = (
        None  # if set, retrieval searches every KB in the project instead of kb_id
    )
    message: str = ""
    conversation_id: str | None = None
    model: str | None = None
    skill_id: str | None = None  # e.g. "write", "code", "learn"
    temperature: float = 0.7
    max_tokens: int = 2048
    use_rag: bool = True
    # Stays at 5. Widening to 10 was measured on 16 hard questions against
    # 2.504 real chunks (scripts/eval_table_embedding.py) and recovered
    # exactly one of them, while doubling the context every RAG turn carries.
    # It does not rescue the price questions either — "xi măng Bút Sơn PCB40"
    # sits at rank 11 — those are answered by lookup_material_price, not by
    # retrieval.
    top_k: int = 5
    # 0.3 let obviously-irrelevant chunks through as "citations" (cosine
    # similarity ~0.3 is close to noise floor for text-embedding-3-small —
    # unrelated text pairs routinely score in the 0.2-0.35 range) — e.g. a
    # question about Hồ Chí Minh's birthday still surfaced construction
    # price PDFs at 31-33% and displayed them as if they backed the answer.
    # 0.5 is a much more honest "this chunk is actually about the query" bar.
    score_threshold: float = 0.5
    # "auto"  — the Request Router decides (production default, §4). A price
    #           question goes to the tool from the backend; a narrative one
    #           goes to RAG; a mixed one uses both, tool authoritative.
    # "rag"   — the user deliberately forces RAG-only. Kept, unchanged.
    # "agent" — the tool loop, kept for open-ended agentic turns; exact price
    #           questions are STILL forced through the tool first (§11).
    # Defaulting to "auto" rather than "rag" is what makes a request that omits
    # `mode` (and every new client) get the routed pipeline; old clients that
    # explicitly send "rag"/"agent" keep exactly the behaviour they had.
    mode: str = "auto"
    # Web price fallback is ON by default: real DB gaps exist for some
    # region/material combinations (e.g. gạch xây ở HCM has no "viên"-unit
    # rows at all), and reporting every such line as "missing" made the
    # estimate unusable for those regions. A missing DB price now falls back
    # to web search unless the caller explicitly opts out (allow_web_fallback
    # = False), and either way the figure is always labelled unverified,
    # never blended silently with a DB-backed price — see cost_tool.py.
    allow_web_fallback: bool = True
    # Agentic mode: retrieve across EVERY knowledge base the user can see
    # (the 4 system ones + their own) instead of a single kb_id/project_id.
    # Resolved server-side on each request rather than sent as a list by the
    # client, so a KB created a minute ago is included without the client
    # having to re-sync anything.
    all_kbs: bool = False
    form_submission: FormSubmission | None = None  # human-in-the-loop form result, see intent.py
    # True when this message's text came from STT rather than being typed.
    # Skips fixed-intent form detection (§6 README) — an inline form doesn't
    # make sense in a hands-free voice flow, and a misheard word triggering
    # or failing to trigger it unpredictably is exactly the kind of glitch
    # that's embarrassing in a live demo. Voice turns always go straight to
    # RAG/plain chat instead.
    via_voice: bool = False


async def _resolve_rag_scope(
    body: ChatRequest, user_id: str
) -> tuple[str | list[str] | None, str | None]:
    """Which knowledge bases this turn retrieves from, and what to call that
    scope in the "RAG · <name>" badge.

    `all_kbs` (Agentic mode) is resolved here on every request instead of the
    client sending a list, so a knowledge base created moments ago is searched
    without the client re-syncing anything."""
    from app.db.postgres.repositories.kb_repo import KnowledgeBaseRepository

    if body.all_kbs:
        repo = KnowledgeBaseRepository()
        kbs = await repo.list_system() + await repo.list_by_user(user_id)
        if kbs:
            return [str(kb.id) for kb in kbs], "Toàn bộ kho tri thức"
        return None, None

    if body.project_id:
        from app.db.postgres.repositories.project_repo import ProjectRepository

        project = await ProjectRepository().get(body.project_id, user_id)
        if project and project.knowledge_bases:
            return [str(kb.id) for kb in project.knowledge_bases], project.name
        return body.kb_id, None

    if body.kb_id:
        kb = await KnowledgeBaseRepository().get_by_id(body.kb_id)
        return body.kb_id, kb.name if kb else None

    return body.kb_id, None


async def _retrieval_query(llm, message: str, history: list[dict]) -> str:
    """Rewrite a follow-up into a standalone searchable question.

    "còn ở Đà Nẵng", "khu vực thành phố Hồ Chí Minh" carry almost no searchable
    terms on their own — embedding them retrieves noise and the model loses the
    thread, which showed up as "Plain chat — no RAG" on the very turns that
    should have continued a price lookup.

    The word-count-only gate this used to have ("short -> condense, long ->
    assume self-contained") was wrong for this domain: region is the single
    most commonly omitted piece of context, and a user drops it in a fully-
    formed 10+-word question just as often as in a 3-word one ("NISHU PRIMER
    có mấy loại, giá mỗi loại bao nhiêu?" is a complete sentence that still
    silently means "... ở Hà Nội, như câu trước"). Skipping condensing for it
    lost the region already established earlier in the SAME conversation, so
    every follow-up like that re-asked "which region?" even though the user
    had already answered once. The gate now only skips condensing when the
    message is BOTH long AND already names a region itself — the actual
    signal for "this doesn't need history to be answered", not length alone.
    Falls back to prepending the previous user turn when the rewrite is
    unavailable."""
    if not history:
        return message
    if len(message.split()) > 8 and detect_regions(message):
        return message
    condensed = await condense_followup(llm, message, history)
    if condensed:
        return condensed
    prev_user = next((m["content"] for m in reversed(history) if m.get("role") == "user"), None)
    return f"{prev_user} {message}" if prev_user else message


async def _retrieve(
    retriever: Retriever,
    *,
    query: str,
    kb_scope: str | list[str] | None,
    top_k: int,
    score_threshold: float,
    regions: list[str],
) -> tuple[list, list[AnswerSource], dict]:
    """Region-aware retrieval + normalized, region-filtered sources.

    This is the second half of the P0 fix. Region-scoped retrieval used to be
    gated on `body.kb_id == KB_PRICING_ID`, so it did nothing at all in
    Agentic mode (`all_kbs`) or Project mode — which is exactly where a
    question about TP. Hồ Chí Minh pulled Hà Nội and Đà Nẵng price chunks and
    showed them as sources. The scoping now follows the REQUEST's regions, not
    which knowledge base happens to be selected.

    Returns the surviving chunks (so the LLM context is built from the same set
    the user is shown), the normalized sources, and an audit dict for the
    structured log — a filter that silently drops citations is how this class
    of bug stays invisible.
    """
    if not kb_scope:
        return [], [], {}

    if len(regions) >= 2:
        # A comparison ("so sánh giá thép HN và ĐN") retrieves per region and
        # merges, so each region is guaranteed a seat — a single unfiltered
        # search lets the higher-scoring region take the whole top-k. The
        # looser threshold is because comparison phrasing dilutes the
        # embedding enough to push the right chunk just under the 0.5 bar.
        cmp_threshold = min(score_threshold, 0.4)
        chunks: list = []
        seen: set[str] = set()
        for rg in regions:
            for c in await retriever.search(
                query=query, kb_id=kb_scope, top_k=4, score_threshold=cmp_threshold, region=rg
            ):
                if c.chunk_id not in seen:
                    seen.add(c.chunk_id)
                    chunks.append(c)
    elif len(regions) == 1:
        # Region-filtered, looser threshold: price rows sit in big mixed table
        # chunks that embed weakly against a single-material query (HN cement
        # lands ~0.45-0.48). Contamination stays bounded by the region filter.
        chunks = await retriever.search(
            query=query,
            kb_id=kb_scope,
            top_k=top_k,
            score_threshold=min(score_threshold, 0.4),
            region=regions[0],
        )
    else:
        chunks = await retriever.search(
            query=query, kb_id=kb_scope, top_k=top_k, score_threshold=score_threshold
        )

    raw = [rag_source(c) for c in chunks]
    kept, dropped = filter_sources_by_region(raw, regions)
    kept = dedupe_sources(kept)
    kept_ids = {s.chunk_id for s in kept}
    audit = {
        "rag_source_count_before_filter": len(raw),
        "rag_source_count_after_filter": len(kept),
        "source_regions_before_filter": sorted({s.region or "none" for s in raw}),
        "source_regions_after_filter": sorted({s.region or "none" for s in kept}),
        "source_region_filtered": len(dropped),
    }
    return [c for c in chunks if c.chunk_id in kept_ids], kept, audit


def _log_turn(decision: RouteDecision | None, **extra) -> None:
    """One structured line per turn. No message text, no API keys (§13)."""
    payload = {
        "route": decision.route.value if decision else None,
        "intent": decision.intent if decision else None,
        "decided_by": decision.decided_by if decision else None,
        "requested_regions": decision.regions if decision else [],
        "production_model": settings.openrouter_chat_model,
        **extra,
    }
    logger.info("chat_turn %s", json.dumps(payload, ensure_ascii=False, default=str))


class HistoryMessage(BaseModel):
    id: str
    role: str  # "user" | "assistant"
    content: str
    sources: list[dict] | None = None
    created_at: int


class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    kb_id: str | None
    messages: list[HistoryMessage]


@router.post("/stream")
async def stream_chat(body: ChatRequest, current_user: CurrentUser):
    """SSE stream for the chat UI's token stream."""
    llm = OpenRouterClient()
    retriever = Retriever()
    msg_repo = MessageRepository()

    # Determine system prompt: skill > default
    system_prompt = _DEFAULT_SYSTEM
    if body.skill_id:
        loaded = load_skill_prompt(body.skill_id)
        if loaded:
            system_prompt = loaded

    async def generate() -> AsyncGenerator[str, None]:
        # ─── Human-in-the-loop form submission ─────────────────────────────
        # A prior turn returned a form_request (see below); the user filled
        # it in on the frontend and this turn carries the structured result.
        # The numbers are computed deterministically (the tool), but the
        # presentation is streamed through the LLM so the reply reads like a
        # normal chat/search answer (prose + inline [n] citations) instead of
        # a raw markdown table — while the prompt forbids changing any number.
        if body.form_submission is not None:
            if body.form_submission.form_id == "construction_cost":
                from app.core.mcp.tools.cost_tool import (
                    COST_PRESENT_PROMPT,
                    _compute_cost,
                    build_cost_facts,
                )

                data = body.form_submission.data
                # Công thức mới (Phần thô, mức hoàn thiện duy nhất là "thô" —
                # không còn finish_level): diện tích tính từ móng + từng tầng
                # (giả định đều nhau = area_per_floor_m2 × num_floors, form
                # chưa hỏi diện tích từng tầng riêng lẻ) + mái, thay vì nhận
                # thẳng một floor_area_m2 đã cộng sẵn.
                num_floors = int(float(data.get("num_floors", 1)))
                tool_args = {
                    "foundation_area_m2": float(data["foundation_area_m2"]),
                    "foundation_type": data["foundation_type"],
                    "floor_areas_m2": [float(data["area_per_floor_m2"])] * max(num_floors, 1),
                    "roof_area_m2": float(data["roof_area_m2"]),
                    "region": data["region"],
                }
                # Optional — see intent.py's FORM_SCHEMAS comment. Reverse-
                # derives an achievable area in build_cost_facts() instead of
                # only ever answering "what does the area you typed cost".
                target_budget = data.get("target_budget_vnd")
                # Defaults True (see ChatRequest.allow_web_fallback) — a
                # missing DB price falls back to web search unless the caller
                # explicitly opts out, always labelled unverified.
                tool_args["allow_web_fallback"] = body.allow_web_fallback
                cost = await _compute_cost(tool_args)
                if cost.get("error"):
                    yield _sse({"type": "text", "delta": cost["error"], "done": False})
                    yield _sse({"type": "text", "delta": "", "done": True, "sources": []})
                    return
                # Two kinds of citation coexist and are now normalized into one
                # shape: DB prices are TOOL sources (authoritative, carrying the
                # region the estimate was priced in), web-fallback prices are
                # WEB sources (unverified). Both still serialize with their
                # legacy keys so the existing renderers keep working.
                form_answer_sources = [
                    tool_source(
                        row_id=s["document_id"],
                        region=tool_args["region"],
                        document_id=s["document_id"],
                        filename=s["document_name"],
                        used_for="estimate",
                    )
                    for s in cost["rag_sources"]
                ] + [web_source(url=s["url"], title=s["title"]) for s in cost["web_sources"]]
                form_sources = to_wire(dedupe_sources(form_answer_sources))
                # If any price came from the KB documents, label the answer as
                # RAG against that KB — it's document-backed, not a plain chat.
                rag_ctx = (
                    {"kind": "kb", "name": cost["rag_kb_name"]} if cost.get("rag_kb_name") else None
                )
                prompt = COST_PRESENT_PROMPT.format(
                    facts=build_cost_facts(cost, target_budget=target_budget)
                )
                reply = ""
                async for token in llm.stream_chat(
                    messages=[{"role": "user", "content": prompt}],
                    model=body.model,
                    temperature=0.2,
                    max_tokens=1200,
                ):
                    reply += token
                    yield _sse({"type": "text", "delta": token, "done": False})
                yield _sse(
                    {
                        "type": "text",
                        "delta": "",
                        "done": True,
                        "sources": form_sources,
                        "source_kinds": sorted(source_kinds(form_answer_sources)),
                        "route": "estimate",
                        "rag_context": rag_ctx,
                    }
                )
                # Persist the estimate so it's part of the conversation memory
                # (a synthetic user line captures the request, since the form
                # data — not free text — is what actually came in this turn).
                if body.conversation_id:
                    try:
                        await msg_repo.ensure_conversation(
                            body.conversation_id,
                            str(current_user.id),
                            kb_id=body.kb_id,
                            title="Dự toán chi phí xây dựng",
                        )
                        req_line = (
                            f"[Dự toán chi phí xây dựng — phần thô] {cost['area']:.0f} m² sàn, "
                            f"vùng {tool_args['region']}"
                        )
                        if target_budget:
                            req_line += f", ngân sách mục tiêu {target_budget:,.0f} đ"
                        await msg_repo.add(body.conversation_id, "user", req_line)
                        await msg_repo.add(
                            body.conversation_id, "assistant", reply, sources=form_sources or None
                        )
                    except Exception:
                        pass
                return
            yield _sse(
                {
                    "type": "text",
                    "delta": f"Unknown form_id: {body.form_submission.form_id}",
                    "done": False,
                }
            )
            yield _sse({"type": "text", "delta": "", "done": True, "sources": []})
            return

        # ─── Small talk — skip the LLM entirely to save API cost/latency ────
        # Pure greetings/farewells/thanks ("chào", "cảm ơn"...) get a canned
        # reply with zero model calls — see app/core/chat/intent.py for why
        # this is an exact-match check, not substring, to avoid swallowing
        # real questions that happen to start with a greeting.
        small_talk_reply = detect_small_talk(body.message)
        if small_talk_reply is not None:
            if body.conversation_id:
                try:
                    await msg_repo.ensure_conversation(
                        body.conversation_id,
                        str(current_user.id),
                        kb_id=body.kb_id,
                        title=body.message[:512],
                    )
                    await msg_repo.add(body.conversation_id, "user", body.message)
                    await msg_repo.add(body.conversation_id, "assistant", small_talk_reply)
                except Exception:
                    pass
            yield _sse({"type": "text", "delta": small_talk_reply, "done": False})
            yield _sse({"type": "text", "delta": "", "done": True, "sources": []})
            return

        # ─── Fixed-pipeline intent detection ───────────────────────────────
        # Known intents (e.g. "giá xây nhà ...") skip the LLM entirely and
        # ask the frontend to render a structured form instead of letting
        # the model guess parameters or ask clarifying questions in free
        # text — see app/core/chat/intent.py. Skipped entirely for voice
        # turns (body.via_voice) — see ChatRequest.via_voice.
        intent = None if body.via_voice else detect_intent(body.message)
        if intent is not None and intent in FORM_SCHEMAS:
            schema = FORM_SCHEMAS[intent]
            event = {
                "type": "form_request",
                "form_id": schema["form_id"],
                "title": schema["title"],
                "fields": schema["fields"],
                "prefill": prefill_from_text(body.message),
                "done": True,
            }
            # Persist the user's message even though this turn only renders a
            # form (no assistant reply yet). Without this, anything the user
            # said in the same breath as the request — e.g. "tôi tên là Khải,
            # cho tôi dự toán..." — is lost from history, so a later "tôi tên
            # gì?" can't recall it.
            if body.conversation_id:
                try:
                    await msg_repo.ensure_conversation(
                        body.conversation_id,
                        str(current_user.id),
                        kb_id=body.kb_id,
                        title=body.message[:512],
                    )
                    await msg_repo.add(body.conversation_id, "user", body.message)
                except Exception:
                    pass
            yield _sse(event)
            return

        # ─── History as memory + slot normalization ─────────────────────────
        # Both the router and retrieval need the STANDALONE form of the turn:
        # "còn ở Đà Nẵng thì sao?" carries no material and no searchable terms
        # on its own, so routing it would find no price question and retrieving
        # it would embed noise. Condensing happens once, up front — before the
        # off-topic guard too (see below) — and every downstream step (guard,
        # router, region detection, retrieval) reads the same rewritten
        # question, which is also why a follow-up now routes and cites the
        # region it actually asks about (§12.14).
        history: list[dict] = []
        if body.conversation_id:
            try:
                history = await msg_repo.get_recent(body.conversation_id, limit=10)
            except Exception:
                history = []

        resolved_query = await _retrieval_query(llm, body.message, history)

        # ─── Off-topic guard — cheap classifier before the (usually pricier)
        # main model/agent loop ────────────────────────────────────────────
        # Only in the default persona: once a KB/project or skill is active,
        # "on topic" is whatever that KB/skill defines, not construction
        # specifically — see app/core/chat/topic_guard.py.
        # `all_kbs` is a knowledge-base scope just like kb_id/project_id, so the
        # same exemption applies: once documents are in scope, "on topic" is
        # whatever they cover.
        # Checked against `resolved_query`, NOT `body.message` — a bare
        # follow-up ("ở Hà Nội thì sao?", or the same thing mis-transcribed by
        # voice) reads as off-topic in complete isolation, and this guard used
        # to run before the condensing step above ever touched it. That was
        # masked whenever a KB/Agentic scope happened to be active (the
        # exemption below skipped the guard entirely), but the default
        # persona — the common case for a plain voice turn — had no such
        # protection and refused mid-conversation about steel/cable prices.
        if not body.kb_id and not body.project_id and not body.skill_id and not body.all_kbs:
            if await is_off_topic(resolved_query, llm):
                reply = refusal_reply()
                if body.conversation_id:
                    try:
                        await msg_repo.ensure_conversation(
                            body.conversation_id,
                            str(current_user.id),
                            kb_id=body.kb_id,
                            title=body.message[:512],
                        )
                        await msg_repo.add(body.conversation_id, "user", body.message)
                        await msg_repo.add(body.conversation_id, "assistant", reply)
                    except Exception:
                        pass
                yield _sse({"type": "text", "delta": reply, "done": False})
                yield _sse({"type": "text", "delta": "", "done": True, "sources": []})
                return

        kb_scope, scope_name = await _resolve_rag_scope(body, str(current_user.id))

        # ─── (6) Request Router — BEFORE retrieval, BEFORE the main LLM ────
        # Mode "rag" is the user explicitly forcing RAG-only, so it skips
        # routing; "auto" (default) and "agent" both route.
        decision: RouteDecision | None = None
        if body.mode in ("auto", "agent"):
            decision = await route_request(resolved_query, llm=llm)
        regions = decision.regions if decision else detect_regions(resolved_query)

        # ─── (8) EXACT_STRUCTURED / MIXED / price CLARIFY ──────────────────
        # The tool runs from the backend. Nothing here depends on the model
        # choosing to call it, and no RAG context is assembled before the
        # lookup — that ordering is what used to make the model answer a price
        # question out of a retrieved table chunk.
        price_routes = (RequestRoute.EXACT_STRUCTURED, RequestRoute.MIXED)
        if decision is not None and (
            decision.route in price_routes
            or (decision.route is RequestRoute.CLARIFY and decision.intent == "price_lookup")
        ):
            t0 = time.perf_counter()
            if decision.price_period:
                # A relative-past period was named ("năm ngoái") — the corpus
                # holds exactly one price_period per material (whatever the
                # source document last published), so there is no history to
                # check this against. Answering with the only period on file
                # as if it satisfied "last year" would present an unverified
                # number as confirmed; refuse instead (§6), same terminal
                # shape as MISSING_SLOTS/AMBIGUOUS/NOT_FOUND below — see
                # not_found_reply()'s use of query_period.
                lookups = [
                    PriceLookupResult(
                        status=PriceStatus.NOT_FOUND,
                        region=(decision.regions or [None])[0],
                        query_name=decision.material_name,
                        query_period=decision.price_period,
                    )
                ]
            else:
                lookups = [
                    await lookup_material_record(
                        region=rg,
                        material_name=decision.material_name,
                        material_category=decision.material_category,
                        manufacturer=decision.manufacturer,
                        requested_fields=decision.requested_fields or ["price"],
                    )
                    for rg in (decision.regions or [None])
                ]
            found_records = [rec for r in lookups if r.found for rec in r.records]

            # Supporting prose (VAT, scope, notes) only — never a number (§7).
            supporting_ctx = ""
            supporting_srcs: list[AnswerSource] = []
            audit: dict = {}
            if decision.route is RequestRoute.MIXED and body.use_rag:
                try:
                    sup_chunks, supporting_srcs, audit = await _retrieve(
                        retriever,
                        query=resolved_query,
                        kb_scope=kb_scope,
                        top_k=body.top_k,
                        score_threshold=body.score_threshold,
                        regions=regions,
                    )
                    supporting_ctx = "\n\n".join(
                        _format_context_chunk(i, c) for i, c in enumerate(sup_chunks)
                    )
                except Exception:
                    supporting_ctx = ""

            tool_srcs = await price_sources(found_records)
            answer_sources = dedupe_sources(tool_srcs + supporting_srcs)

            reply = ""
            if found_records:
                prompt = build_price_prompt(
                    body.message, found_records, supporting_ctx, results=lookups
                )
                async for token in llm.stream_chat(
                    messages=[{"role": "user", "content": prompt}],
                    model=body.model,
                    temperature=0.2,
                    max_tokens=body.max_tokens,
                ):
                    reply += token
                    yield _sse({"type": "text", "delta": token, "done": False})
            else:
                # Terminal: MISSING_SLOTS / AMBIGUOUS / NOT_FOUND / ERROR.
                # Emitted verbatim with no model call — the whole point is that
                # nothing gets a chance to be helpful with a number here (§6).
                blocked = lookups[0]
                reply = deterministic_reply(blocked, decision.material_name) or ""
                if decision.route is RequestRoute.MIXED and supporting_ctx:
                    # §7 — the explanatory half can still be answered, as long
                    # as the reply says plainly that no verified price was found.
                    reply += "\n\n"
                    yield _sse({"type": "text", "delta": reply, "done": False})
                    explain_prompt = (
                        "Trả lời phần GIẢI THÍCH của câu hỏi dưới đây CHỈ dựa trên tư liệu "
                        "kèm theo. TUYỆT ĐỐI không nêu bất kỳ con số giá nào, kể cả khi tư "
                        "liệu có chứa giá — hệ thống chưa xác minh được giá cho yêu cầu này "
                        "và người dùng đã được thông báo điều đó.\n\n"
                        f"Câu hỏi: {body.message}\n\nTư liệu:\n{supporting_ctx}\n\nTrả lời:"
                    )
                    async for token in llm.stream_chat(
                        messages=[{"role": "user", "content": explain_prompt}],
                        model=body.model,
                        temperature=0.2,
                        max_tokens=body.max_tokens,
                    ):
                        reply += token
                        yield _sse({"type": "text", "delta": token, "done": False})
                else:
                    # A blocked price answer cites nothing: there is no
                    # authoritative row, and shipping the RAG chips alongside
                    # would suggest the number came from somewhere after all.
                    answer_sources = []
                    yield _sse({"type": "text", "delta": reply, "done": False})

            wire_sources = to_wire(answer_sources)
            yield _sse(
                {
                    "type": "text",
                    "delta": "",
                    "done": True,
                    "sources": wire_sources,
                    "source_kinds": sorted(source_kinds(answer_sources)),
                    "route": decision.route.value,
                    "rag_context": (
                        {"kind": "kb", "name": scope_name or "Kho tri thức"}
                        if any(s.source_kind == "rag" for s in answer_sources)
                        else None
                    ),
                }
            )
            _log_turn(
                decision,
                tool_status=[r.status.value for r in lookups],
                alias_retry=any(r.alias_retry for r in lookups),
                resolved_region=[r.region for r in lookups],
                tool_source_count=len(tool_srcs),
                **audit,
            )
            await _persist(msg_repo, body, current_user, reply, wire_sources)
            await _record_usage(current_user, body, system_prompt, reply, t0)
            return

        # ─── (8) ESTIMATE / GENERAL agentic turns — the tool loop ──────────
        # ESTIMATE is forced into the tool loop even from "auto": every figure
        # in a cost answer must come out of the cost/quantity tool's arithmetic
        # (§3.0), never out of the model.
        is_estimate = decision is not None and decision.route is RequestRoute.ESTIMATE
        if body.mode == "agent" or is_estimate:
            from app.core.llm.tool_loop import run_tool_loop

            agent_history = history
            # Agentic mode answers from documents AND tools, not tools alone:
            # "xi măng PCB40 khác PCB30 chỗ nào" only exists in the narrative
            # chunks. Retrieval is region-scoped like everywhere else now, so
            # an agentic turn about TP.HCM can no longer surface a Hà Nội chunk.
            agent_srcs: list[AnswerSource] = []
            agent_ctx = ""
            agent_audit: dict = {}
            if body.use_rag and kb_scope:
                try:
                    agent_chunks, agent_srcs, agent_audit = await _retrieve(
                        retriever,
                        query=resolved_query,
                        kb_scope=kb_scope,
                        top_k=body.top_k,
                        score_threshold=body.score_threshold,
                        regions=regions,
                    )
                except Exception:
                    agent_chunks = []
                if agent_chunks:
                    agent_ctx = "\n\n".join(
                        _format_context_chunk(i, c) for i, c in enumerate(agent_chunks)
                    )

            messages: list[dict] = [{"role": "system", "content": system_prompt}]
            if agent_ctx:
                # The retrieved text goes in its OWN system message, not glued
                # onto the user's question. Prefixing the question with a
                # "Context:" block made the model answer from that block and
                # never reach for a tool: asked "giá xi măng Bút Sơn PCB40 ở Hà
                # Nội", it replied "không có dữ liệu" without a single tool
                # call, while the same question with retrieval off called
                # lookup_material_price immediately. Retrieval was disabling
                # the exact-lookup path it was supposed to complement.
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Tư liệu tham khảo lấy từ kho tri thức (có thể KHÔNG chứa câu "
                            f"trả lời):\n{agent_ctx}\n\n"
                            "Tư liệu này KHÔNG thay thế công cụ. Với câu hỏi về ĐƠN GIÁ vật "
                            "liệu hoặc dự toán chi phí, PHẢI gọi công cụ tương ứng — kể cả "
                            "khi tư liệu trên trông đã đủ, và NHẤT LÀ khi tư liệu không "
                            "nhắc tới vật liệu được hỏi. Chỉ được kết luận 'không có dữ "
                            "liệu' sau khi công cụ đã trả về không tìm thấy."
                        ),
                    }
                )
            messages += [*agent_history, {"role": "user", "content": body.message}]
            t0 = time.perf_counter()
            final_content, tool_call_log = await run_tool_loop(
                messages, llm=llm, model=body.model, allow_web_fallback=body.allow_web_fallback
            )
            yield _sse({"type": "text", "delta": final_content, "done": False})
            # The raw tool-call log stays in the payload for debugging (it is
            # what the old client rendered), but the citations the UI shows are
            # the normalized ones — a tool log entry is not a source, and
            # counting it as one is why a tool-only answer used to be badged
            # "RAG" (§8.10).
            wire_sources = to_wire(agent_srcs)
            yield _sse(
                {
                    "type": "text",
                    "delta": "",
                    "done": True,
                    "sources": wire_sources,
                    "tool_calls": tool_call_log,
                    "source_kinds": sorted(
                        source_kinds(agent_srcs) | ({"tool"} if tool_call_log else set())
                    ),
                    "route": decision.route.value if decision else "agent",
                    "rag_context": (
                        {"kind": "kb", "name": scope_name or "Kho tri thức"}
                        if agent_srcs
                        else None
                    ),
                }
            )
            _log_turn(
                decision,
                mode=body.mode,
                tool_status=[c["name"] for c in tool_call_log],
                **agent_audit,
            )
            await _persist(msg_repo, body, current_user, final_content, wire_sources)
            await _record_usage(current_user, body, system_prompt, final_content, t0)
            return

        # ─── (8) DOCUMENT_RAG / GENERAL_CHAT — and explicit mode="rag" ─────
        chunks: list = []
        sources: list[AnswerSource] = []
        audit = {}
        if body.use_rag and kb_scope:
            chunks, sources, audit = await _retrieve(
                retriever,
                query=resolved_query,
                kb_scope=kb_scope,
                top_k=body.top_k,
                score_threshold=body.score_threshold,
                regions=regions,
            )
            context = "\n\n".join(_format_context_chunk(i, c) for i, c in enumerate(chunks))
            user_msg = f"Context:\n{context}\n\nQuestion: {body.message}"
        else:
            user_msg = body.message

        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": user_msg},
        ]

        t0 = time.perf_counter()
        reply = ""
        async for token in llm.stream_chat(
            messages=messages,
            model=body.model,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        ):
            reply += token
            yield _sse({"type": "text", "delta": token, "done": False})

        # Badge only when retrieval actually returned something — an active
        # KB/project with zero matching chunks (off-topic question) must NOT
        # be credited as "RAG · <name>", same rule the form-submission path
        # already follows (see rag_ctx above).
        rag_ctx = (
            {
                "kind": "project" if body.project_id else "kb",
                "name": scope_name or "Kho tri thức",
            }
            if sources
            else None
        )
        wire_sources = to_wire(sources)
        yield _sse(
            {
                "type": "text",
                "delta": "",
                "done": True,
                "sources": wire_sources,
                "source_kinds": sorted(source_kinds(sources)),
                "route": decision.route.value if decision else body.mode,
                "rag_context": rag_ctx,
            }
        )
        _log_turn(decision, mode=body.mode, resolved_region=regions, **audit)

        # Persist this turn for future context (best-effort — the reply has
        # already been delivered in full above, so a write failure is
        # harmless). Store the RAW user message, not the RAG-context-wrapped
        # one, so history stays compact and re-usable as plain memory. The
        # sources are stored in NORMALIZED form, so reopening the conversation
        # renders the same regions it showed live (rule §8.9).
        await _persist(msg_repo, body, current_user, reply, wire_sources)
        await _record_usage(current_user, body, system_prompt, reply, t0, user_msg)

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)


async def _persist(msg_repo, body, current_user, reply: str, sources: list[dict]) -> None:
    """Best-effort write of the turn. The reply has already been delivered in
    full by the time this runs, so a failure here must never surface."""
    if not body.conversation_id:
        return
    try:
        await msg_repo.ensure_conversation(
            body.conversation_id,
            str(current_user.id),
            kb_id=body.kb_id,
            title=body.message[:512],
        )
        await msg_repo.add(body.conversation_id, "user", body.message)
        await msg_repo.add(body.conversation_id, "assistant", reply, sources=sources or None)
    except Exception:
        pass


async def _record_usage(current_user, body, system_prompt: str, reply: str, t0, prompt_text=None):
    """Usage tracking — token counts are real (tiktoken), cost is a static-table
    estimate since OpenRouter returns no billing info on the SSE path."""
    try:
        model_used = body.model or settings.openrouter_chat_model
        prompt_tokens = count_tokens(system_prompt) + count_tokens(prompt_text or body.message)
        completion_tokens = count_tokens(reply)
        await UsageRepository().record(
            user_id=str(current_user.id),
            model=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=estimate_cost_usd(model_used, prompt_tokens, completion_tokens),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
    except Exception:
        pass


@router.get("/history/{conversation_id}", response_model=ConversationHistoryResponse)
async def get_history(conversation_id: str, current_user: CurrentUser):
    """Full message history for a conversation, so the chat UI can restore
    a past conversation on load instead of always starting empty — the
    `messages` table already exists (written for LLM context injection),
    this just reads it back. Ownership-scoped: 404s rather than 403s for a
    conversation that isn't the caller's, to avoid confirming it exists."""
    msg_repo = MessageRepository()
    try:
        conv = await msg_repo.get_conversation(conversation_id, str(current_user.id))
        rows = await msg_repo.get_all(conversation_id, str(current_user.id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Conversation not found") from None
    if conv is None or rows is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationHistoryResponse(
        conversation_id=conversation_id,
        kb_id=str(conv.kb_id) if conv.kb_id else None,
        messages=[
            HistoryMessage(
                id=str(m.id),
                role=m.role,
                content=m.content,
                sources=json.loads(m.sources) if m.sources else None,
                created_at=int(m.created_at.timestamp()),
            )
            for m in rows
        ],
    )
