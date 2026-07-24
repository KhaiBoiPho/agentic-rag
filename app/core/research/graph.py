"""Deep Research LangGraph — 5-node workflow with quality-gate loop.

Flow:
  prompt_expander → web_searcher → content_aggregator
       → quality_checker → [PASS] → response_generator
                        ↘ [FAIL, iter < max] → prompt_expander (loop)

There used to be a separate `summarizer` node between quality_checker and
response_generator (an LLM call that rewrote aggregated_text into a
structured summary, which response_generator's LLM call then rewrote AGAIN
into the final answer). Two blocking LLM round-trips back to back was the
main reason Research felt like it hung — cut it: response_generator now
writes straight from `aggregated_text` (graph.py::stream falls back to it
whenever `summary` is empty), which is one LLM call fewer per run/iteration.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from langgraph.graph import END, START, StateGraph

from app.core.research.nodes.content_aggregator import content_aggregator_node
from app.core.research.nodes.prompt_expander import prompt_expander_node
from app.core.research.nodes.quality_checker import quality_checker_node
from app.core.research.nodes.response_generator import response_generator_node
from app.core.research.nodes.web_searcher import web_searcher_node
from app.core.research.state import ResearchState

logger = logging.getLogger(__name__)


def _should_continue(state: ResearchState) -> str:
    """Routing: after quality check, go to the final response or loop back."""
    if state.get("quality_passed"):
        return "response_generator"
    return "prompt_expander"


def _build_graph() -> StateGraph:
    builder = StateGraph(ResearchState)

    builder.add_node("prompt_expander", prompt_expander_node)
    builder.add_node("web_searcher", web_searcher_node)
    builder.add_node("content_aggregator", content_aggregator_node)
    builder.add_node("quality_checker", quality_checker_node)
    builder.add_node("response_generator", response_generator_node)

    builder.add_edge(START, "prompt_expander")
    builder.add_edge("prompt_expander", "web_searcher")
    builder.add_edge("web_searcher", "content_aggregator")
    builder.add_edge("content_aggregator", "quality_checker")
    builder.add_conditional_edges(
        "quality_checker",
        _should_continue,
        {"response_generator": "response_generator", "prompt_expander": "prompt_expander"},
    )
    builder.add_edge("response_generator", END)

    return builder


_GRAPH = _build_graph().compile()


class DeepResearchGraph:
    async def stream(
        self,
        query: str,
        user_id: str,
        config: dict,
        pre_search_results: list[dict] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """`pre_search_results` — pass results from a quick Search (the
        composer's Search mode) to seed the graph instead of starting cold;
        web_searcher_node merges these into its own results rather than
        discarding them (search.py::stream_search_then_research calls this
        after running that quick search itself)."""
        initial_state: ResearchState = {
            "original_query": query,
            "user_id": user_id,
            "config": config,
            "iteration": 0,
            "pre_search_results": pre_search_results or [],
            "expanded_queries": [],
            "search_results": [],
            "aggregated_text": "",
            "quality_passed": False,
            "quality_score": 0.0,
            "quality_feedback": "",
            "summary": "",
            "final_response": "",
            "sources": [],
            "events": [],
        }

        # Emit starting event
        yield {
            "node": "start",
            "status": "started",
            "content": query,
            "progress": 0.0,
            "done": False,
        }

        if pre_search_results:
            yield {
                "node": "pre_search",
                "status": "completed",
                "content": f"Đã dùng {len(pre_search_results)} kết quả Search làm context ban đầu",
                "progress": 0.02,
                "sources": [
                    {"url": r["url"], "title": r["title"], "snippet": r.get("snippet", "")}
                    for r in pre_search_results
                ],
                "iteration": 0,
            }

        # `stream_mode="updates"` only yields each node's own diff, not the
        # accumulated state — track summary/sources/query ourselves across
        # the loop so they're available for the final streaming call below.
        final_state: dict = {}
        async for chunk in _GRAPH.astream(initial_state, stream_mode="updates"):
            for node_name, node_output in chunk.items():
                final_state.update({k: v for k, v in node_output.items() if k != "events"})
                events = node_output.get("events", [])
                for event in events:
                    yield event

        # Graph is done through response_generator (which now only builds
        # `sources` — see that node's docstring). Stream the actual
        # conversational answer here, token by token, same as normal chat —
        # previously this was one `await llm.chat(...)` call inside the
        # node, arriving as a single non-streaming SSE event with no
        # token-by-token feedback for however many seconds it took.
        from app.core.llm.openrouter import OpenRouterClient
        from app.core.research.nodes.response_generator import RESPONSE_PROMPT

        summary = final_state.get("summary", "") or final_state.get("aggregated_text", "")
        sources = final_state.get("sources", [])
        # Numbered so the model can cite "[1]", "[2]" inline — the frontend
        # (MarkdownRenderer) turns those into small clickable badges keyed
        # to this same 1-based index, instead of the model writing its own
        # full-size "[source](url)" markdown links inline.
        sources_list = (
            "\n".join(f"{i}. {s.get('title', s.get('url', ''))}" for i, s in enumerate(sources, 1))
            or "(không có nguồn)"
        )
        prompt = RESPONSE_PROMPT.format(query=query, summary=summary, sources_list=sources_list)

        full_response = ""
        async for token in OpenRouterClient().stream_chat(
            messages=[{"role": "user", "content": prompt}],
            model="openai/gpt-4o-mini",
            temperature=0.5,
            max_tokens=3000,
        ):
            full_response += token
            yield {
                "node": "response_generator",
                "status": "streaming",
                "content": token,
                "progress": 0.95,
                "done": False,
                "iteration": final_state.get("iteration", 0),
            }

        yield {
            "node": "response_generator",
            "status": "completed",
            "content": full_response,
            "progress": 1.0,
            "sources": sources,
            "done": False,
            "iteration": final_state.get("iteration", 0),
        }

        # Emit final done event
        yield {"node": "done", "status": "completed", "content": "", "progress": 1.0, "done": True}
