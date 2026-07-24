"""Resolve a follow-up question into a standalone search query.

Mid-conversation, a user types things like "còn ở HCM?" or "cao quá nhỉ, có
ảnh hưởng tới người trẻ không?" — meaningless to a web search on their own,
and actively misleading ("cao" searched bare returns articles about physical
height, not high prices). Both Search and Research call this to rewrite such
a query against the recent chat before searching. No context → returned
unchanged; any failure → falls back to the original query (never blocks).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_REWRITE_PROMPT = (
    "Dựa vào đoạn hội thoại, viết lại câu hỏi cuối thành MỘT truy vấn tìm kiếm web "
    "độc lập, đầy đủ ngữ cảnh (giữ nguyên ngôn ngữ, giữ đúng ý — ví dụ 'cao' đang nói "
    "về GIÁ cao thì phải rõ là giá, không phải chiều cao). Chỉ trả về truy vấn, không "
    "giải thích.\n\nHội thoại:\n{context}\n\nCâu hỏi cuối: {query}"
)


async def contextualize_query(query: str, context: str) -> str:
    if not context or not context.strip():
        return query
    try:
        from app.core.llm.openrouter import OpenRouterClient

        rewritten = await OpenRouterClient().chat(
            messages=[
                {"role": "user", "content": _REWRITE_PROMPT.format(context=context, query=query)}
            ],
            model="openai/gpt-4o-mini",
            temperature=0.0,
            max_tokens=60,
        )
        resolved = (rewritten or "").strip().strip('"')
        return resolved or query
    except Exception as exc:
        logger.warning("query contextualization failed, using raw query: %s", exc)
        return query
