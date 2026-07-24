from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.postgres.base import get_session
from app.db.postgres.models import Note


class NoteRepository:
    async def list_by_user(self, user_id: str) -> list[Note]:
        async with get_session() as s:
            result = await s.execute(
                select(Note)
                .where(Note.user_id == uuid.UUID(user_id))
                .order_by(Note.updated_at.desc())
            )
            return list(result.scalars().all())

    async def get(self, note_id: str, user_id: str) -> Note | None:
        async with get_session() as s:
            result = await s.execute(
                select(Note).where(Note.id == uuid.UUID(note_id), Note.user_id == uuid.UUID(user_id))
            )
            return result.scalar_one_or_none()

    async def create(self, user_id: str, title: str, content: str = "") -> Note:
        async with get_session() as s:
            note = Note(user_id=uuid.UUID(user_id), title=title, content=content)
            s.add(note)
            await s.flush()
            await s.refresh(note)
            return note

    async def update(self, note_id: str, user_id: str, title: str | None, content: str | None) -> Note | None:
        async with get_session() as s:
            note = await s.get(Note, uuid.UUID(note_id))
            if not note or str(note.user_id) != user_id:
                return None
            if title is not None:
                note.title = title
            if content is not None:
                note.content = content
            await s.flush()
            await s.refresh(note)
            return note

    async def delete(self, note_id: str, user_id: str) -> bool:
        async with get_session() as s:
            note = await s.get(Note, uuid.UUID(note_id))
            if not note or str(note.user_id) != user_id:
                return False
            await s.delete(note)
            return True
