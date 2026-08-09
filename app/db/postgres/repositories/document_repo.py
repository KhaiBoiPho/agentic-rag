from __future__ import annotations

import uuid

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from app.db.postgres.base import get_session
from app.db.postgres.models import Document, KnowledgeBase, MaterialPrice


class DocumentRepository:
    async def create(self, kb_id: str, user_id: str, filename: str) -> Document:
        async with get_session() as s:
            doc = Document(
                kb_id=uuid.UUID(kb_id),
                user_id=uuid.UUID(user_id),
                filename=filename,
                status="pending",
            )
            s.add(doc)
            await s.flush()
            await s.refresh(doc)
            # increment KB document count
            kb = await s.get(KnowledgeBase, uuid.UUID(kb_id))
            if kb:
                kb.document_count = (kb.document_count or 0) + 1
            return doc

    async def get_by_id(self, doc_id: str, user_id: str) -> Document | None:
        async with get_session() as s:
            result = await s.execute(
                select(Document).where(
                    Document.id == uuid.UUID(doc_id),
                    Document.user_id == uuid.UUID(user_id),
                )
            )
            return result.scalar_one_or_none()

    async def list_status_by_filename(self, kb_id: str) -> dict[str, tuple[str, str]]:
        """filename -> (document_id, status) for every document already
        recorded in a KB, regardless of status — used by seed.py to decide,
        per file, whether to skip (status == "done"), retry after cleaning
        up a stale row (status stuck at "processing"/"pending"/"error" from
        a run that got interrupted mid-file, e.g. by an app restart), or
        ingest fresh (no row yet)."""
        async with get_session() as s:
            result = await s.execute(
                select(Document.filename, Document.id, Document.status).where(
                    Document.kb_id == uuid.UUID(kb_id)
                )
            )
            return {filename: (str(doc_id), status) for filename, doc_id, status in result.all()}

    async def list_by_kb(
        self, kb_id: str, user_id: str | None, limit: int = 20, offset: int = 0
    ) -> tuple[list[Document], int]:
        async with get_session() as s:
            base_filter = [Document.kb_id == uuid.UUID(kb_id)]
            if user_id is not None:
                base_filter.append(Document.user_id == uuid.UUID(user_id))
            q = select(Document).where(*base_filter)
            total_result = await s.execute(select(func.count()).select_from(q.subquery()))
            total = total_result.scalar() or 0
            result = await s.execute(
                q.order_by(Document.created_at.desc()).limit(limit).offset(offset)
            )
            return list(result.scalars().all()), total

    async def update_status(
        self, doc_id: str, status: str, chunk_count: int = 0, error: str = ""
    ) -> None:
        async with get_session() as s:
            doc = await s.get(Document, uuid.UUID(doc_id))
            if doc:
                doc.status = status
                if chunk_count:
                    doc.chunk_count = chunk_count
                if error:
                    doc.error_message = error

    async def set_metadata(self, doc_id: str, metadata: dict) -> None:
        async with get_session() as s:
            doc = await s.get(Document, uuid.UUID(doc_id))
            if doc:
                doc.doc_metadata = {**(doc.doc_metadata or {}), **metadata}

    async def delete(self, doc_id: str, user_id: str) -> None:
        async with get_session() as s:
            doc = await s.get(Document, uuid.UUID(doc_id))
            if doc and str(doc.user_id) == user_id:
                # material_prices.document_id has no ON DELETE CASCADE — clear
                # rows extracted from this document first, or the FK blocks
                # deleting the document itself.
                await s.execute(sa_delete(MaterialPrice).where(MaterialPrice.document_id == doc.id))
                kb = await s.get(KnowledgeBase, doc.kb_id)
                if kb and kb.document_count > 0:
                    kb.document_count -= 1
                await s.delete(doc)
