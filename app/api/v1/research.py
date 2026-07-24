"""Deep research REST endpoint — SSE stream of 6-node LangGraph progress."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import SSE_HEADERS, CurrentUser
from app.core.research.graph import DeepResearchGraph
from app.core.research.nodes.web_searcher import firecrawl_search

router = APIRouter()
_graph = DeepResearchGraph()


class ResearchRequest(BaseModel):
    query: str
    max_iterations: int = 3
    max_search_results: int = 10
    quality_threshold: float = 0.75
    # "Search + Research together": run one quick Search on the raw query
    # first, then hand its results to the graph as a head start instead of
    # Research starting cold and re-discovering the same top results itself.
    search_first: bool = False
    # Recent chat turns (plain text) when Research runs mid-conversation —
    # prompt_expander uses it to resolve follow-ups ("còn ở HCM?") into
    # self-contained sub-queries. Empty = standalone.
    context: str = ""


@router.post("/stream")
async def stream_research(body: ResearchRequest, current_user: CurrentUser):
    async def generate() -> AsyncGenerator[str, None]:
        from app.core.chat.query_context import contextualize_query

        # Resolve the query against the chat FIRST, then use the resolved
        # form for everything. Without this, a follow-up like "cao quá nhỉ,
        # ảnh hưởng người trẻ không?" got pre-searched literally — Firecrawl
        # read "cao" as physical height and returned height articles that
        # then dominated the whole report. The resolved query keeps both the
        # pre-search and the final answer on the actual topic.
        resolved_query = await contextualize_query(body.query, body.context)

        pre_search_results: list[dict] = []
        if body.search_first:
            try:
                pre_search_results = await firecrawl_search(resolved_query, max_results=5)
            except Exception:
                pre_search_results = []  # best-effort — Research still runs fine without it

        async for event in _graph.stream(
            query=resolved_query,
            user_id=str(current_user.id),
            config={
                "max_iterations": body.max_iterations,
                "max_search_results": body.max_search_results,
                "quality_threshold": body.quality_threshold,
                "context": body.context,
            },
            pre_search_results=pre_search_results,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)
