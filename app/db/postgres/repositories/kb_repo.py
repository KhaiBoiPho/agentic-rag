from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.bootstrap.constants import SYSTEM_USER_ID
from app.db.postgres.base import get_session
from app.db.postgres.models import KnowledgeBase


class KnowledgeBaseRepository:
    async def list_all(self) -> list[KnowledgeBase]:
        """Return all knowledge bases across all users (used by plugin gateway)."""
        async with get_session() as s:
            result = await s.execute(
                select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc())
            )
            return list(result.scalars().all())

    async def list_system(self) -> list[KnowledgeBase]:
        """Knowledge bases owned by the fixed system user (see
        app/core/bootstrap/), visible to every authenticated user regardless
        of who created them — seeded once at deploy time."""
        return await self.list_by_user(SYSTEM_USER_ID)

    async def list_by_user(self, user_id: str) -> list[KnowledgeBase]:
        async with get_session() as s:
            result = await s.execute(
                select(KnowledgeBase)
                .where(KnowledgeBase.user_id == uuid.UUID(user_id))
                .order_by(KnowledgeBase.created_at.desc())
            )
            return list(result.scalars().all())

    async def create(self, user_id: str, name: str, description: str = "") -> KnowledgeBase:
        async with get_session() as s:
            kb = KnowledgeBase(user_id=uuid.UUID(user_id), name=name, description=description)
            s.add(kb)
            await s.flush()
            await s.refresh(kb)
            return kb

    async def get(self, kb_id: str, user_id: str) -> KnowledgeBase | None:
        async with get_session() as s:
            result = await s.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == uuid.UUID(kb_id),
                    KnowledgeBase.user_id == uuid.UUID(user_id),
                )
            )
            return result.scalar_one_or_none()

    async def delete(self, kb_id: str, user_id: str) -> bool:
        async with get_session() as s:
            kb = await s.get(KnowledgeBase, uuid.UUID(kb_id))
            if not kb or str(kb.user_id) != user_id:
                return False
            await s.delete(kb)
            return True
