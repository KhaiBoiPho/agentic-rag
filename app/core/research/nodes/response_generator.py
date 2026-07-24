"""Node 6 — Build the final source list from search results.

The actual conversational answer is NOT generated here anymore — it used to
call the LLM with `await _llm.chat(...)` (non-streaming), which meant the
whole multi-second final answer arrived as a single SSE event with no
token-by-token feedback (unlike normal chat). That's now done in
graph.py::stream(), after the graph itself finishes, via `stream_chat()` so
the UI can render it exactly like a normal streaming chat reply. This node
just prepares `sources` (and a `final_response` fallback equal to the
summary, in case a caller reads it directly without going through the
graph's stream()).
"""

from __future__ import annotations

from app.core.research.state import ResearchState

RESPONSE_PROMPT = """\
You are a helpful research assistant. Using the research summary provided,
give a clear, direct, and conversational answer to the user's question.
Be accurate but accessible.

Cite sources with a bare bracketed number right after the claim, e.g.
"Giá nhà đã tăng 20% [1]." — the number must match the numbered source list
below. Do NOT write markdown links, do NOT write words like "source"/"nguồn"
next to the citation, do NOT invent a number with no matching source. Skip
citing anything not covered by the list below.

Question: {query}

Research summary:
{summary}

Numbered sources (cite these by number, nothing else):
{sources_list}

Provide your answer:
"""


async def response_generator_node(state: ResearchState) -> dict:
    sources = [
        {
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "snippet": r.get("snippet", ""),
        }
        for r in state.get("search_results", [])[:10]
        if r.get("url")
    ]

    return {
        "final_response": state.get("summary", ""),
        "sources": sources,
        "events": [
            {
                "node": "response_generator",
                "status": "ready",
                "content": "",
                "progress": 0.9,
                "sources": sources,
                "done": False,
                "iteration": state.get("iteration", 0),
            }
        ],
    }
