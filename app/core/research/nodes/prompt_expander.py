"""Node 1 — Expand the user prompt into multiple search queries."""

from __future__ import annotations

import json

from app.core.llm.openrouter import OpenRouterClient
from app.core.research.state import ResearchState

_llm = OpenRouterClient()

EXPAND_PROMPT = """\
You are a research assistant. Given a user question, generate {n} diverse sub-questions
and search queries that together would help answer the original question comprehensively.
{context_block}
Resolve any references in the question against the conversation above so each
sub-query is self-contained (e.g. "còn ở HCM?" → "giá xây nhà ở HCM"). Keep the
question's original language.

Return ONLY a JSON array of strings. No explanation.

Example: ["What is X?", "History of X", "X vs Y comparison", "Latest developments in X"]

User question: {query}
"""


async def prompt_expander_node(state: ResearchState) -> dict:
    query = state["original_query"]
    # Capped at 4 (was 8) — each extra query is another parallel Firecrawl
    # search+scrape call; 8 made the web_searcher step the single biggest
    # contributor to Research feeling stuck with no feedback.
    n = min(state["config"].get("max_search_results", 10), 4)

    context = (state["config"].get("context") or "").strip()
    context_block = (
        f"\nConversation so far (for resolving references):\n{context}\n" if context else ""
    )
    prompt = EXPAND_PROMPT.format(query=query, n=n, context_block=context_block)
    response = await _llm.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    try:
        # Extract JSON array from response
        start = response.find("[")
        end = response.rfind("]") + 1
        expanded = json.loads(response[start:end]) if start >= 0 else [query]
    except Exception:
        expanded = [query]

    return {
        "expanded_queries": expanded,
        "events": [
            {
                "node": "prompt_expander",
                "status": "completed",
                "content": f"{len(expanded)} câu hỏi phụ: " + "; ".join(expanded),
                "progress": 0.1,
                "iteration": state.get("iteration", 0),
            }
        ],
    }
