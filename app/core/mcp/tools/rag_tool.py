"""MCP Tool — RAG query against a knowledge base."""
from __future__ import annotations

from mcp.types import TextContent, Tool


RAG_TOOL = Tool(
    name="rag_query",
    description="Search the knowledge base and return relevant document chunks for a query.",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
            "kb_id": {"type": "string", "description": "Knowledge base ID to search"},
            "top_k": {"type": "integer", "description": "Number of results to return", "default": 5},
        },
        "required": ["query", "kb_id"],
    },
)


async def handle_rag_query(args: dict) -> list[TextContent]:
    from app.core.retrieval.retriever import Retriever
    retriever = Retriever()
    chunks = await retriever.search(
        query=args["query"],
        kb_id=args["kb_id"],
        top_k=args.get("top_k", 5),
    )
    if not chunks:
        return [TextContent(type="text", text="No relevant documents found.")]

    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(f"[{i}] {c.document_name} (score={c.score:.2f})\n{c.content}")

    return [TextContent(type="text", text="\n\n".join(parts))]
