"""Chat REST endpoint — SSE fallback (gRPC preferred for production)."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import SSE_HEADERS, CurrentUser
from app.api.v1.config import load_skill_prompt
from app.core.chat.intent import FORM_SCHEMAS, detect_intent, prefill_from_text
from app.core.chunking.base import count_tokens
from app.core.llm.openrouter import OpenRouterClient
from app.core.retrieval.retriever import Retriever
from app.core.usage.pricing import estimate_cost_usd
from app.db.postgres.repositories.usage_repo import UsageRepository

router = APIRouter()

_DEFAULT_SYSTEM = "You are a helpful AI assistant."


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


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


@router.post("/stream")
async def stream_chat(body: ChatRequest, current_user: CurrentUser):
    """SSE stream — use gRPC endpoint for lower latency in production."""
    llm = OpenRouterClient()
    retriever = Retriever()
    from app.db.postgres.repositories.message_repo import MessageRepository

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
                prompt = COST_PRESENT_PROMPT.format(facts=build_cost_facts(cost))
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

        # ─── Fixed-pipeline intent detection ───────────────────────────────
        # Known intents (e.g. "giá xây nhà ...") skip the LLM entirely and
        # ask the frontend to render a structured form instead of letting
        # the model guess parameters or ask clarifying questions in free
        # text — see app/core/chat/intent.py.
        intent = detect_intent(body.message)
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

        if body.mode == "agent":
            from app.core.llm.tool_loop import run_tool_loop

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": body.message},
            ]
            final_content, tool_call_log = await run_tool_loop(messages, llm=llm, model=body.model)
            yield _sse({"type": "text", "delta": final_content, "done": False})
            yield _sse({"type": "text", "delta": "", "done": True, "sources": tool_call_log})
            return

        search_kb_id: str | list[str] | None = body.kb_id
        if body.project_id:
            from app.db.postgres.repositories.project_repo import ProjectRepository

            project = await ProjectRepository().get(body.project_id, str(current_user.id))
            if project and project.knowledge_bases:
                search_kb_id = [str(kb.id) for kb in project.knowledge_bases]

        if body.use_rag and search_kb_id:
            chunks = await retriever.search(
                query=body.message,
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
            context = "\n\n".join(f"[{i + 1}]: {c.content}" for i, c in enumerate(chunks))
            user_msg = f"Context:\n{context}\n\nQuestion: {body.message}"
        else:
            user_msg = body.message

        # Prior turns (last N) as conversation memory. Persisted server-side
        # (messages table) so multi-turn context survives without the client
        # resending its whole history; fetched via the composite index added
        # in migration 0006. Best-effort — a history failure must not break
        # the reply, so it degrades to a single-turn (historyless) prompt.
        history: list[dict] = []
        if body.conversation_id:
            try:
                history = await msg_repo.get_recent(body.conversation_id, limit=10)
            except Exception:
                history = []

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

        yield _sse({"type": "text", "delta": "", "done": True, "sources": sources})

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
