"""MCP Tool — Web search via Firecrawl."""
from __future__ import annotations

import httpx
from mcp.types import TextContent, Tool

from app.config import settings


SEARCH_TOOL = Tool(
    name="web_search",
    description="Search the web using Firecrawl and return scraped content from top results.",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Max results", "default": 5},
        },
        "required": ["query"],
    },
)


async def handle_web_search(args: dict) -> list[TextContent]:
    query = args["query"]
    max_results = args.get("max_results", 5)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.firecrawl_base_url}/v1/search",
            headers={"Authorization": f"Bearer {settings.firecrawl_api_key}"},
            json={"query": query, "limit": max_results, "scrapeOptions": {"formats": ["markdown"]}},
        )
        if resp.status_code != 200:
            return [TextContent(type="text", text=f"Search failed: {resp.status_code}")]

        data = resp.json()
        parts = []
        for item in data.get("data", []):
            title = item.get("title", "No title")
            url = item.get("url", "")
            content = (item.get("markdown") or item.get("description", ""))[:1000]
            parts.append(f"## {title}\nURL: {url}\n\n{content}")

    if not parts:
        return [TextContent(type="text", text="No results found.")]

    return [TextContent(type="text", text="\n\n---\n\n".join(parts))]
