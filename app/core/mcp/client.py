"""MCP Client — consumes external MCP servers (filesystem, browser, etc.)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from mcp import ClientSession
from mcp.client.sse import sse_client

logger = logging.getLogger(__name__)


class MCPClient:
    """Connects to an external MCP server over SSE and calls its tools."""

    def __init__(self, server_url: str) -> None:
        self._url = server_url

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[ClientSession, None]:
        async with sse_client(self._url) as (read, write):
            async with ClientSession(read, write) as sess:
                await sess.initialize()
                yield sess

    async def list_tools(self) -> list[dict]:
        async with self.session() as sess:
            result = await sess.list_tools()
            return [{"name": t.name, "description": t.description} for t in result.tools]

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        async with self.session() as sess:
            result = await sess.call_tool(tool_name, arguments)
            return [c.text for c in result.content if hasattr(c, "text")]
