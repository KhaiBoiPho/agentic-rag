"""Node 2 — Search the web using Firecrawl for each expanded query."""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import settings
from app.core.research.state import ResearchState

logger = logging.getLogger(__name__)


async def firecrawl_search(
    query: str, max_results: int, *, scrape: bool = True, timeout: float = 15
) -> list[dict]:
    """Call Firecrawl search API, optionally scraping the top results.

    `scrape=True` fetches each page's full markdown (higher quality context
    but much slower — the search+scrape round-trip for a handful of results
    routinely takes 15-30s). `scrape=False` returns just the search hits +
    their snippet/description, which is far faster; callers that only need a
    quick summary (the Search composer mode) use that. `timeout` is the
    whole-request budget — a scrape run needs a bigger one than the 15s
    research uses for its parallel per-query calls.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{settings.firecrawl_base_url}/v1/search",
            headers={
                "Authorization": f"Bearer {settings.firecrawl_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "limit": max_results,
                "scrapeOptions": {"formats": ["markdown"]} if scrape else {},
            },
        )
        if resp.status_code != 200:
            logger.warning("Firecrawl returned %d for query=%r", resp.status_code, query)
            return []

        data = resp.json()
        results = []
        for item in data.get("data", []):
            results.append(
                {
                    "url": item.get("url", ""),
                    "title": item.get("title", ""),
                    "content": item.get("markdown", "") or item.get("description", ""),
                    "snippet": item.get("description", "")[:300],
                }
            )
        return results


async def web_searcher_node(state: ResearchState) -> dict:
    queries = state.get("expanded_queries", [state["original_query"]])
    max_results = max(1, state["config"].get("max_search_results", 10) // len(queries))

    # Run all searches in parallel
    tasks = [firecrawl_search(q, max_results) for q in queries]
    all_results_nested = await asyncio.gather(*tasks, return_exceptions=True)

    # Pre-search results (see graph.py::stream — a quick single-query search
    # run before the graph starts, when the user used Search-then-Research)
    # go first so they win the URL-dedup below if the expanded-query search
    # turns up the same page again — no point re-aggregating it twice.
    search_results: list[dict] = list(state.get("pre_search_results") or [])
    for item in all_results_nested:
        if isinstance(item, list):
            search_results.extend(item)

    # Deduplicate by URL
    seen: set[str] = set()
    unique: list[dict] = []
    for r in search_results:
        if r["url"] and r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)

    return {
        "search_results": unique,
        "events": [
            {
                "node": "web_searcher",
                "status": "completed",
                "content": f"Found {len(unique)} sources",
                "progress": 0.3,
                "sources": [
                    {"url": r["url"], "title": r["title"], "snippet": r["snippet"]} for r in unique
                ],
                "iteration": state.get("iteration", 0),
            }
        ],
    }
