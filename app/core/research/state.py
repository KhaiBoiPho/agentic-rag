"""LangGraph state schema for deep research."""

from __future__ import annotations

import operator
from typing import Annotated, Any

from typing_extensions import TypedDict


class ResearchState(TypedDict):
    # Input
    original_query: str
    user_id: str
    config: dict[str, Any]
    iteration: int

    # Optional "Search first" head start (see graph.py::stream's
    # pre_search_results param) — a quick single-query search run before the
    # graph starts, merged into web_searcher_node's own results rather than
    # replacing them, so Research doesn't repeat work Search already did.
    pre_search_results: list[dict]

    # Node 1 output — expanded queries
    expanded_queries: list[str]

    # Node 2 output — raw search results
    search_results: list[dict]  # {url, title, content, snippet}

    # Node 3 output — aggregated text
    aggregated_text: str

    # Node 4 output — quality check
    quality_passed: bool
    quality_score: float
    quality_feedback: str

    # Node 5 output — summary
    summary: str

    # Node 6 output — final response
    final_response: str
    sources: list[dict]  # {url, title, snippet}

    # Streaming events for SSE — plain {node, status, content, progress,
    # iteration} dicts, not chat messages. `add_messages` (LangGraph's usual
    # reducer for a Annotated[list, ...] field) is specifically for
    # role/content chat messages and raises ValueError on anything else
    # ("Message dict must contain 'role' and 'content' keys") — that crash
    # is what made every Research run hang forever (the SSE stream died
    # mid-graph with no error/done event ever sent). operator.add just
    # concatenates the lists, which is all this field needs.
    events: Annotated[list[dict], operator.add]
