"""Node 3 — Aggregate all scraped content into a single text corpus."""
from __future__ import annotations

from app.core.research.state import ResearchState

_MAX_CHARS_PER_SOURCE = 3000
_MAX_TOTAL_CHARS = 20000


async def content_aggregator_node(state: ResearchState) -> dict:
    results = state.get("search_results", [])
    parts: list[str] = []
    total_chars = 0

    for r in results:
        content = (r.get("content") or r.get("snippet") or "").strip()
        if not content:
            continue
        # Trim per-source to avoid one source dominating
        trimmed = content[:_MAX_CHARS_PER_SOURCE]
        header = f"### {r.get('title', r.get('url', 'Source'))}\nURL: {r.get('url', '')}\n\n"
        block = header + trimmed
        if total_chars + len(block) > _MAX_TOTAL_CHARS:
            remaining = _MAX_TOTAL_CHARS - total_chars
            if remaining > 200:
                parts.append(block[:remaining])
            break
        parts.append(block)
        total_chars += len(block)

    aggregated = "\n\n---\n\n".join(parts)

    return {
        "aggregated_text": aggregated,
        "events": [
            {
                "node": "content_aggregator",
                "status": "completed",
                "content": f"Aggregated {len(parts)} sources ({total_chars} chars)",
                "progress": 0.5,
                "iteration": state.get("iteration", 0),
            }
        ],
    }
