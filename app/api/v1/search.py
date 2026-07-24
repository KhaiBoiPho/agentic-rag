"""Web search endpoint — Firecrawl search + a streamed LLM summary.

Unlike Research (the multi-node graph in app/core/research/), this is a
single search pass: fetch results, hand them to the model as context, and
stream back a short synthesized answer with inline [n] citations — so the
user gets something readable instead of a raw list of links. The raw
sources are still sent (as one `sources` event) so the UI can render the
citation badges and a sources list.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import SSE_HEADERS, CurrentUser

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    max_results: int = 8
    scrape: bool = True  # also scrape full page content
    # Recent chat turns (plain text) when Search is used mid-conversation —
    # lets a follow-up like "còn ở HCM?" be resolved into a standalone
    # search query instead of being searched literally. Empty = standalone.
    context: str = ""


SEARCH_SUMMARY_PROMPT = """\
Bạn là trợ lý tìm kiếm. Dựa CHỈ trên các kết quả tìm kiếm web dưới đây, hãy
viết một câu trả lời ngắn gọn, rõ ràng, dễ đọc cho câu hỏi của người dùng —
tổng hợp thông tin lại thành đoạn văn mạch lạc, KHÔNG liệt kê lại từng link.

Trích dẫn nguồn bằng số trong ngoặc vuông ngay sau thông tin, ví dụ:
"Giá nhà Hà Nội khoảng 100 triệu/m² [1]." Số phải khớp với danh sách nguồn
bên dưới. KHÔNG viết link markdown, KHÔNG ghi chữ "nguồn"/"source" cạnh số,
KHÔNG bịa số không có nguồn. Trả lời bằng cùng ngôn ngữ với câu hỏi.

Câu hỏi: {query}

Kết quả tìm kiếm:
{context}

Danh sách nguồn (chỉ trích dẫn bằng số này):
{sources_list}

Viết câu trả lời:
"""


@router.post("/web")
async def web_search(body: SearchRequest, current_user: CurrentUser):
    """SSE stream — one `sources` event, then the summary answer token by token."""

    async def generate() -> AsyncGenerator[str, None]:
        # Resolve follow-up references against the chat so the *search* query
        # is self-contained ("còn ở HCM?" → "giá xây nhà ở HCM"). Only pays
        # the extra call when there's actually prior context.
        from app.core.chat.query_context import contextualize_query
        from app.core.llm.openrouter import OpenRouterClient
        from app.core.research.nodes.web_searcher import firecrawl_search

        search_query = await contextualize_query(body.query, body.context)

        try:
            # scrape=False — Search should feel snappy; the result snippets
            # are enough for a summary, and scraping every page would add
            # 15-30s. (Research is the mode that scrapes for depth.)
            results = await firecrawl_search(
                search_query,
                max_results=body.max_results,
                scrape=False,
                timeout=20,
            )
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc), 'done': True})}\n\n"
            return

        if not results:
            yield f"data: {json.dumps({'error': 'Không tìm thấy kết quả nào', 'done': True})}\n\n"
            return

        sources = [
            {"url": r["url"], "title": r.get("title", ""), "snippet": r.get("snippet", "")}
            for r in results
            if r.get("url")
        ]
        # Send sources up front so the UI can render the badges/list even
        # before (or if the LLM step somehow fails) the summary arrives.
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources, 'done': False})}\n\n"

        context = "\n\n".join(
            f"[{i}] {r.get('title', '')}\n{(r.get('content') or r.get('snippet') or '')[:1500]}"
            for i, r in enumerate(results, 1)
        )
        sources_list = "\n".join(
            f"{i}. {r.get('title', r.get('url', ''))}" for i, r in enumerate(results, 1)
        )
        prompt = SEARCH_SUMMARY_PROMPT.format(
            query=search_query, context=context, sources_list=sources_list
        )

        try:
            async for token in OpenRouterClient().stream_chat(
                messages=[{"role": "user", "content": prompt}],
                model="openai/gpt-4o-mini",
                temperature=0.4,
                max_tokens=1500,
            ):
                yield f"data: {json.dumps({'type': 'token', 'delta': token, 'done': False})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc), 'done': True})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'done', 'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)
