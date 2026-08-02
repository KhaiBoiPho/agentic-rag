"""Tool-calling loop — lets the LLM decide whether to call one of the
construction-domain MCP tools (lookup_material_price, estimate_material_quantity,
calculate_construction_cost) instead of answering from plain RAG context.

No LangGraph here on purpose: this is a bounded, single-turn tool loop
(call model -> execute any tool_calls -> call model again with results ->
return), not a multi-node research graph. `app/core/research/graph.py`
solves a different problem (iterative web search) and isn't a fit.
"""

from __future__ import annotations

import json
import logging

from mcp.types import Tool

from app.core.llm.openrouter import OpenRouterClient
from app.core.mcp.tools.cost_tool import COST_TOOL, handle_calculate_construction_cost
from app.core.mcp.tools.price_lookup_tool import PRICE_LOOKUP_TOOL, handle_lookup_material_price
from app.core.mcp.tools.quantity_tool import QUANTITY_TOOL, handle_estimate_material_quantity

logger = logging.getLogger(__name__)

# Construction-domain tools only — rag_query/web_search/deep_research stay
# MCP-only for now since RAG context is already injected directly into the
# chat prompt by the caller (app/api/v1/chat.py) rather than via tool call.
_AGENT_TOOLS: dict[str, tuple[Tool, callable]] = {
    "lookup_material_price": (PRICE_LOOKUP_TOOL, handle_lookup_material_price),
    "estimate_material_quantity": (QUANTITY_TOOL, handle_estimate_material_quantity),
    "calculate_construction_cost": (COST_TOOL, handle_calculate_construction_cost),
}


def _tool_input_schema(tool: Tool) -> dict:
    """Read the tool's JSON schema across mcp versions.

    `mcp` is pinned as >=1.1.0, and a later release renamed `Tool.inputSchema`
    to `input_schema`. Construction still accepts the old spelling as an
    alias, so the tools built fine and only this read failed — at import time,
    inside the request handler, which took down agent mode on the deployed
    build while local (older mcp) kept working."""
    for attr in ("inputSchema", "input_schema"):
        schema = getattr(tool, attr, None)
        if schema:
            return schema
    raise AttributeError(f"Tool {tool.name!r} exposes no input schema")


def _to_openai_tool_schema(tool: Tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": _tool_input_schema(tool),
        },
    }


_TOOL_SCHEMAS = [_to_openai_tool_schema(t) for t, _ in _AGENT_TOOLS.values()]


async def run_tool_loop(
    messages: list[dict],
    llm: OpenRouterClient | None = None,
    model: str | None = None,
    max_rounds: int = 4,
) -> tuple[str, list[dict]]:
    """Returns (final_content, tool_call_log). tool_call_log entries are
    {name, arguments, result} — surfaced to the client as `sources`/debug
    info so a tool-driven answer is distinguishable from a plain-RAG one."""
    llm = llm or OpenRouterClient()
    conversation = list(messages)
    tool_call_log: list[dict] = []

    for _ in range(max_rounds):
        message = await llm.chat_with_tools(conversation, tools=_TOOL_SCHEMAS, model=model)

        if not message.tool_calls:
            return message.content or "", tool_call_log

        conversation.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in message.tool_calls
                ],
            }
        )

        for tc in message.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            entry = _AGENT_TOOLS.get(name)
            if entry is None:
                result_text = f"Unknown tool: {name}"
            else:
                _, handler = entry
                try:
                    content = await handler(args)
                    result_text = "\n".join(c.text for c in content if hasattr(c, "text"))
                except Exception as exc:
                    logger.exception("Tool %s failed", name)
                    result_text = f"Tool error: {exc}"

            tool_call_log.append({"name": name, "arguments": args, "result": result_text})
            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                }
            )

    # Ran out of rounds — ask once more without tools to force a final answer.
    final = await llm.chat(conversation, model=model)
    return final, tool_call_log
