"""MCP Server — exposes RAG query, web search, and deep research as MCP tools.

Runs as an SSE MCP server alongside FastAPI on /mcp path.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import CallToolResult, ListToolsResult

from app.core.mcp.tools.cost_tool import COST_TOOL, handle_calculate_construction_cost
from app.core.mcp.tools.price_lookup_tool import PRICE_LOOKUP_TOOL, handle_lookup_material_price
from app.core.mcp.tools.quantity_tool import QUANTITY_TOOL, handle_estimate_material_quantity
from app.core.mcp.tools.rag_tool import RAG_TOOL, handle_rag_query
from app.core.mcp.tools.research_tool import RESEARCH_TOOL, handle_deep_research
from app.core.mcp.tools.search_tool import SEARCH_TOOL, handle_web_search

logger = logging.getLogger(__name__)

_server = Server("agentic-rag-mcp")

_TOOLS = {
    "rag_query": (RAG_TOOL, handle_rag_query),
    "web_search": (SEARCH_TOOL, handle_web_search),
    "deep_research": (RESEARCH_TOOL, handle_deep_research),
    "lookup_material_price": (PRICE_LOOKUP_TOOL, handle_lookup_material_price),
    "estimate_material_quantity": (QUANTITY_TOOL, handle_estimate_material_quantity),
    "calculate_construction_cost": (COST_TOOL, handle_calculate_construction_cost),
}


@_server.list_tools()
async def list_tools() -> ListToolsResult:
    return ListToolsResult(tools=[t for t, _ in _TOOLS.values()])


@_server.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    if name not in _TOOLS:
        return CallToolResult(content=[], isError=True)
    _, handler = _TOOLS[name]
    try:
        content = await handler(arguments)
        return CallToolResult(content=content, isError=False)
    except Exception as exc:
        logger.exception("MCP tool %s failed", name)
        from mcp.types import TextContent
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {exc}")],
            isError=True,
        )


def get_mcp_app():
    """Return an ASGI app for MCP SSE transport — mount at /mcp in FastAPI."""
    transport = SseServerTransport("/mcp/messages")

    async def handle_sse(scope, receive, send):
        async with transport.connect_sse(scope, receive, send) as streams:
            await _server.run(streams[0], streams[1], _server.create_initialization_options())

    return handle_sse
