"""Server-side chat history — persist messages and fetch the recent window.

The conversation list/UI still lives in the browser (localStorage); this
table exists so the chat endpoint can pull the last N turns as context
without trusting the client to send its whole history each request, and so
that retrieval is a single indexed lookup (see the composite index on
(conversation_id, created_at) added in migration 0006).

`conversation_id` is the client's own conversation id (a UUID generated in
the browser). ensure_conversation() upserts the parent row so the Message
FK holds even though the conversation was "created" client-side.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.postgres.base import get_session
from app.db.postgres.models import Conversation, Message


class MessageRepository:
    async def ensure_conversation(
        self,
        conversation_id: str,
        user_id: str,
        kb_id: str | None = None,
        title: str = "",
    ) -> None:
        """Create the conversation row if it doesn't exist yet (no-op if it
        does) — needed before inserting messages (FK), since conversations
        originate client-side."""
        async with get_session() as s:
            stmt = (
                pg_insert(Conversation)
                .values(
                    id=uuid.UUID(conversation_id),
                    user_id=uuid.UUID(user_id),
                    kb_id=uuid.UUID(kb_id) if kb_id else None,
                    title=title[:512],
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            await s.execute(stmt)

    async def add(
        self,
        conversation_id: str,
        role: str,
        content: str,
        sources: list | None = None,
    ) -> None:
        async with get_session() as s:
            s.add(
                Message(
                    conversation_id=uuid.UUID(conversation_id),
                    role=role,
                    content=content,
                    sources=json.dumps(sources, ensure_ascii=False) if sources else None,
                )
            )

    async def get_recent(self, conversation_id: str, limit: int = 10) -> list[dict]:
        """Last `limit` messages for the conversation, oldest-first (ready to
        splice straight into the LLM `messages` list). Returns plain
        {role, content} dicts."""
        async with get_session() as s:
            result = await s.execute(
                select(Message.role, Message.content)
                .where(Message.conversation_id == uuid.UUID(conversation_id))
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            rows = list(result.all())
        # Pulled newest-first for the LIMIT; flip to chronological for the prompt.
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    async def get_conversation(self, conversation_id: str, user_id: str) -> Conversation | None:
        """The conversation row if it exists and belongs to `user_id`, else None."""
        async with get_session() as s:
            conv = await s.get(Conversation, uuid.UUID(conversation_id))
            if conv is None or str(conv.user_id) != user_id:
                return None
            return conv

    async def get_all(self, conversation_id: str, user_id: str, limit: int = 200) -> list[Message] | None:
        """Full message history for a conversation, chronological — the read
        side of the write-only persistence `add()` was originally built for
        (LLM context injection). Ownership-scoped: returns None if the
        conversation doesn't exist or isn't this user's, so the API layer
        can 404 without leaking whether the id exists for someone else."""
        async with get_session() as s:
            conv = await s.get(Conversation, uuid.UUID(conversation_id))
            if conv is None or str(conv.user_id) != user_id:
                return None
            result = await s.execute(
                select(Message)
                .where(Message.conversation_id == uuid.UUID(conversation_id))
                .order_by(Message.created_at.asc())
                .limit(limit)
            )
            return list(result.scalars().all())
