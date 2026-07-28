"""Chat REST endpoint — SSE streaming."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import SSE_HEADERS, CurrentUser
from app.api.v1.config import load_skill_prompt
from app.core.bootstrap.constants import KB_PRICING_ID
from app.core.chat.followup import condense_followup
from app.core.chat.intent import (
    FORM_SCHEMAS,
    detect_intent,
    detect_regions,
    detect_small_talk,
    prefill_from_text,
)
from app.core.chat.topic_guard import is_off_topic, refusal_reply
from app.core.chunking.base import count_tokens
from app.core.llm.openrouter import OpenRouterClient
from app.core.retrieval.retriever import Retriever
from app.core.usage.pricing import estimate_cost_usd
from app.db.postgres.repositories.message_repo import MessageRepository
from app.db.postgres.repositories.usage_repo import UsageRepository

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


_REGION_NAMES = {"HN": "Hà Nội", "DN": "Đà Nẵng", "HCM": "TPHCM"}


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
    top_k: int = 5
    # 0.3 let obviously-irrelevant chunks through as "citations" (cosine
    # similarity ~0.3 is close to noise floor for text-embedding-3-small —
    # unrelated text pairs routinely score in the 0.2-0.35 range) — e.g. a
    # question about Hồ Chí Minh's birthday still surfaced construction
    # price PDFs at 31-33% and displayed them as if they backed the answer.
    # 0.5 is a much more honest "this chunk is actually about the query" bar.
    score_threshold: float = 0.5
    mode: str = "rag"  # "rag" | "agent" — "agent" lets the LLM call construction-cost tools
    form_submission: FormSubmission | None = None  # human-in-the-loop form result, see intent.py
    # True when this message's text came from STT rather than being typed.
    # Skips fixed-intent form detection (§6 README) — an inline form doesn't
    # make sense in a hands-free voice flow, and a misheard word triggering
    # or failing to trigger it unpredictably is exactly the kind of glitch
    # that's embarrassing in a live demo. Voice turns always go straight to
    # RAG/plain chat instead.
    via_voice: bool = False


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
        sources = []

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
                tool_args = {
                    "floor_area_m2": float(data["area_per_floor_m2"])
                    * float(data.get("num_floors", 1)),
                    "region": data["region"],
                    "finish_level": data.get("finish_level", "hoan_thien_co_ban"),
                }
                # Optional — see intent.py's FORM_SCHEMAS comment. Reverse-
                # derives an achievable area in build_cost_facts() instead of
                # only ever answering "what does the area you typed cost".
                target_budget = data.get("target_budget_vnd")
                cost = await _compute_cost(tool_args)
                if cost.get("error"):
                    yield _sse({"type": "text", "delta": cost["error"], "done": False})
                    yield _sse({"type": "text", "delta": "", "done": True, "sources": []})
                    return
                # Two kinds of citation coexist: DB prices carry their source
                # document (RAG chips: document_name + score), web-fallback
                # prices carry url+title ([n] badges + "Nguồn" footer). The
                # frontend already renders each shape by which keys are set.
                form_sources = cost["rag_sources"] + [
                    {"url": s["url"], "title": s["title"]} for s in cost["web_sources"]
                ]
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
                            f"[Dự toán chi phí xây dựng] {tool_args['floor_area_m2']:.0f} m² sàn, "
                            f"vùng {tool_args['region']}, mức {tool_args['finish_level']}"
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

        # ─── Off-topic guard — cheap classifier before the (usually pricier)
        # main model/agent loop ────────────────────────────────────────────
        # Only in the default persona: once a KB/project or skill is active,
        # "on topic" is whatever that KB/skill defines, not construction
        # specifically — see app/core/chat/topic_guard.py.
        if not body.kb_id and not body.project_id and not body.skill_id:
            if await is_off_topic(body.message, llm):
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

        if body.mode == "agent":
            from app.core.llm.tool_loop import run_tool_loop

            # Same history-as-memory pattern as the plain RAG path below —
            # without this, every agent-mode turn (which is every turn, the
            # frontend always sends mode="agent") starts from zero context,
            # so a follow-up like "ở HCM thì sao" after "giá xây 100m2 ở Hà
            # Nội" has no idea what area/finish_level it's even talking
            # about and can't call the cost tool with inferred parameters.
            agent_history: list[dict] = []
            if body.conversation_id:
                try:
                    agent_history = await msg_repo.get_recent(body.conversation_id, limit=10)
                except Exception:
                    agent_history = []

            messages = [
                {"role": "system", "content": system_prompt},
                *agent_history,
                {"role": "user", "content": body.message},
            ]
            t0 = time.perf_counter()
            final_content, tool_call_log = await run_tool_loop(messages, llm=llm, model=body.model)
            yield _sse({"type": "text", "delta": final_content, "done": False})
            yield _sse({"type": "text", "delta": "", "done": True, "sources": tool_call_log})

            if body.conversation_id:
                try:
                    await msg_repo.ensure_conversation(
                        body.conversation_id,
                        str(current_user.id),
                        kb_id=body.kb_id,
                        title=body.message[:512],
                    )
                    await msg_repo.add(body.conversation_id, "user", body.message)
                    await msg_repo.add(body.conversation_id, "assistant", final_content)
                except Exception:
                    pass

            try:
                model_used = body.model or "openai/gpt-4o-mini"
                prompt_tokens = count_tokens(system_prompt) + count_tokens(body.message)
                completion_tokens = count_tokens(final_content)
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
            return

        search_kb_id: str | list[str] | None = body.kb_id
        rag_scope_name: str | None = None
        if body.project_id:
            from app.db.postgres.repositories.project_repo import ProjectRepository

            project = await ProjectRepository().get(body.project_id, str(current_user.id))
            if project and project.knowledge_bases:
                search_kb_id = [str(kb.id) for kb in project.knowledge_bases]
                rag_scope_name = project.name
        elif body.kb_id:
            from app.db.postgres.repositories.kb_repo import KnowledgeBaseRepository

            kb = await KnowledgeBaseRepository().get_by_id(body.kb_id)
            if kb:
                rag_scope_name = kb.name

        # Prior turns (last N) as conversation memory. Persisted server-side
        # (messages table) so multi-turn context survives without the client
        # resending its whole history; fetched via the composite index added
        # in migration 0006. Best-effort — a history failure must not break
        # the reply, so it degrades to a single-turn (historyless) prompt.
        # Fetched BEFORE retrieval because a deictic follow-up needs the prior
        # turn to build a searchable retrieval query (see below).
        history: list[dict] = []
        if body.conversation_id:
            try:
                history = await msg_repo.get_recent(body.conversation_id, limit=10)
            except Exception:
                history = []

        # A short follow-up ("còn ở Đà Nẵng thì sao?", "loại kia thì sao?")
        # carries almost no searchable terms on its own — embedding it retrieves
        # noise, so the model loses the thread. Rewrite it into a standalone
        # question with a cheap model (condense step). Falls back to prepending
        # the previous user turn if the rewrite is unavailable.
        retrieval_query = body.message
        if body.use_rag and history and len(body.message.split()) <= 8:
            condensed = await condense_followup(llm, body.message, history)
            if condensed:
                retrieval_query = condensed
            else:
                prev_user = next(
                    (m["content"] for m in reversed(history) if m.get("role") == "user"),
                    None,
                )
                if prev_user:
                    retrieval_query = f"{prev_user} {body.message}"

        # On the pricing KB, region-aware retrieval. Detect from the (possibly
        # condensed) retrieval query so a follow-up like "còn Đà Nẵng?" still
        # resolves its region. Only price chunks carry a region.
        #   • exactly 1 region → hard-filter to it, so the correct-region chunk
        #     can't be crowded out of the top-k by a wrong-region one.
        #   • 2+ regions (a comparison, "so sánh giá thép HN và ĐN") → retrieve
        #     SEPARATELY per region and merge, so each region is guaranteed a
        #     seat; a single unfiltered search lets the higher-scoring region
        #     dominate the top-k and starves the other, making comparison
        #     impossible.
        regions: list[str] = []
        if body.kb_id == KB_PRICING_ID:
            regions = detect_regions(retrieval_query)

        if body.use_rag and search_kb_id:
            if len(regions) >= 2:
                # Each search is already region-scoped (so off-topic
                # contamination is bounded), and a comparison-phrased query
                # ("so sánh ... nơi nào rẻ hơn") dilutes the embedding enough to
                # push the right chunk just under the normal 0.5 bar — so use a
                # looser threshold here to keep recall on both regions.
                cmp_threshold = min(body.score_threshold, 0.4)
                chunks = []
                seen: set[str] = set()
                for rg in regions:
                    for c in await retriever.search(
                        query=retrieval_query,
                        kb_id=search_kb_id,
                        top_k=4,
                        score_threshold=cmp_threshold,
                        region=rg,
                    ):
                        if c.chunk_id not in seen:
                            seen.add(c.chunk_id)
                            chunks.append(c)
            elif len(regions) == 1:
                # Region-filtered (so contamination is bounded to the right
                # region) — price rows sit in big mixed table chunks that embed
                # weakly against a single-material query, scoring just under the
                # 0.5 bar (e.g. HN cement chunks land ~0.45-0.48). A looser
                # threshold recovers them without risking cross-region bleed.
                chunks = await retriever.search(
                    query=retrieval_query,
                    kb_id=search_kb_id,
                    top_k=body.top_k,
                    score_threshold=min(body.score_threshold, 0.4),
                    region=regions[0],
                )
            else:
                chunks = await retriever.search(
                    query=retrieval_query,
                    kb_id=search_kb_id,
                    top_k=body.top_k,
                    score_threshold=body.score_threshold,
                )
            sources = [
                {
                    "chunk_id": c.chunk_id,
                    "document_name": c.document_name,
                    "content": c.content,
                    "score": c.score,
                }
                for c in chunks
            ]
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
            {"kind": "project" if body.project_id else "kb", "name": rag_scope_name or "Kho tri thức"}
            if sources
            else None
        )
        yield _sse({"type": "text", "delta": "", "done": True, "sources": sources, "rag_context": rag_ctx})

        # Persist this turn for future context (best-effort — the reply has
        # already been delivered in full above, so a write failure is
        # harmless). Store the RAW user message, not the RAG-context-wrapped
        # one, so history stays compact and re-usable as plain memory.
        if body.conversation_id:
            try:
                await msg_repo.ensure_conversation(
                    body.conversation_id,
                    str(current_user.id),
                    kb_id=body.kb_id,
                    title=body.message[:512],
                )
                await msg_repo.add(body.conversation_id, "user", body.message)
                await msg_repo.add(
                    body.conversation_id, "assistant", reply, sources=sources or None
                )
            except Exception:
                pass

        # Usage tracking (Usage page) — token counts are real (tiktoken),
        # cost is a static-table estimate since OpenRouter doesn't return
        # billing info on this SSE streaming path. Best-effort: never let a
        # tracking failure break the chat response, which has already been
        # sent in full by this point.
        try:
            model_used = body.model or "openai/gpt-4o-mini"
            prompt_tokens = count_tokens(system_prompt) + count_tokens(user_msg)
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

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)


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
