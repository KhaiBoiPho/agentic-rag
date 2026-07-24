from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.postgres.base import get_session
from app.db.postgres.models import KnowledgeBase, Project


class ProjectRepository:
    async def list_by_user(self, user_id: str) -> list[Project]:
        async with get_session() as s:
            result = await s.execute(
                select(Project)
                .where(Project.user_id == uuid.UUID(user_id))
                .options(selectinload(Project.knowledge_bases))
                .order_by(Project.updated_at.desc())
            )
            return list(result.scalars().all())

    async def get(self, project_id: str, user_id: str) -> Project | None:
        async with get_session() as s:
            result = await s.execute(
                select(Project)
                .where(Project.id == uuid.UUID(project_id), Project.user_id == uuid.UUID(user_id))
                .options(selectinload(Project.knowledge_bases))
            )
            return result.scalar_one_or_none()

    async def create(self, user_id: str, name: str, description: str = "") -> Project:
        async with get_session() as s:
            project = Project(user_id=uuid.UUID(user_id), name=name, description=description)
            # A brand-new project has no KBs yet — set this explicitly so the
            # relationship is considered "loaded" before the session closes.
            # Without it, the caller's first access to .knowledge_bases (e.g.
            # building the API response) tries an async lazy-load on a
            # detached instance and raises DetachedInstanceError (500).
            project.knowledge_bases = []
            s.add(project)
            await s.flush()
            # No s.refresh() here — it would re-expire (un-load) the
            # relationship we just set above, reintroducing the same crash.
            # id/created_at/updated_at are all populated client-side already
            # (see the Python-level `default=` on those columns), so nothing
            # is actually missing on `project` post-flush.
            return project

    async def rename(
        self, project_id: str, user_id: str, name: str | None, description: str | None
    ) -> Project | None:
        async with get_session() as s:
            project = await s.get(Project, uuid.UUID(project_id))
            if not project or str(project.user_id) != user_id:
                return None
            if name is not None:
                project.name = name
            if description is not None:
                project.description = description
            await s.flush()
            await s.refresh(project)
            return project

    async def delete(self, project_id: str, user_id: str) -> bool:
        async with get_session() as s:
            project = await s.get(Project, uuid.UUID(project_id))
            if not project or str(project.user_id) != user_id:
                return False
            await s.delete(project)
            return True

    async def set_kbs(self, project_id: str, user_id: str, kb_ids: list[str]) -> Project | None:
        """Replace the project's attached KB list wholesale — simpler and
        less error-prone from the frontend's multi-select than add/remove
        one at a time."""
        async with get_session() as s:
            result = await s.execute(
                select(Project)
                .where(Project.id == uuid.UUID(project_id), Project.user_id == uuid.UUID(user_id))
                .options(selectinload(Project.knowledge_bases))
            )
            project = result.scalar_one_or_none()
            if not project:
                return None
            kbs_result = await s.execute(
                select(KnowledgeBase).where(KnowledgeBase.id.in_([uuid.UUID(k) for k in kb_ids]))
            )
            project.knowledge_bases = list(kbs_result.scalars().all())
            await s.flush()
            await s.refresh(project)
            return project
