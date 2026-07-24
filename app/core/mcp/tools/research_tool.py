"""MCP Tool — Trigger deep research and return the final answer."""

from __future__ import annotations

from mcp.types import TextContent, Tool

RESEARCH_TOOL = Tool(
    name="deep_research",
    description=(
        "Run a deep research workflow (6-node LangGraph) and return a comprehensive answer."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Research question"},
            "max_iterations": {"type": "integer", "default": 2},
        },
        "required": ["query"],
    },
)


async def handle_deep_research(args: dict) -> list[TextContent]:
    from app.core.research.graph import DeepResearchGraph

    graph = DeepResearchGraph()

    final_response = ""
    async for event in graph.stream(
        query=args["query"],
        user_id="mcp-tool",
        config={
            "max_iterations": args.get("max_iterations", 2),
            "max_search_results": 8,
            "quality_threshold": 0.7,
        },
    ):
        if event.get("node") == "response_generator" and event.get("content"):
            final_response = event["content"]

    return [TextContent(type="text", text=final_response or "Research produced no result.")]
