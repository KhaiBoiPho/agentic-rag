"""Document upload — publishes ingestion job to RabbitMQ, returns job_id."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.config import settings
from app.core.bootstrap.constants import is_system_kb
from app.queue.publisher import publish_ingest_job

router = APIRouter()

MAX_FILE_MB = 50


class IngestJobResponse(BaseModel):
    job_id: str
    filename: str
    status: str = "queued"


@router.post("/upload/{kb_id}", response_model=IngestJobResponse, status_code=202)
async def upload_document(
    kb_id: str,
    file: UploadFile,
    current_user: CurrentUser,
    chunk_token_num: int = Query(default=None),
    chunk_overlap_pct: int = Query(default=None),
    table_context_size: int = Query(default=None),
):
    if is_system_kb(kb_id):
        raise HTTPException(403, "This knowledge base is system-managed (read-only) — uploads are not allowed")
    if file.size and file.size > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds {MAX_FILE_MB}MB limit")

    content = await file.read()
    job_id = await publish_ingest_job(
        kb_id=kb_id,
        user_id=str(current_user.id),
        filename=file.filename or "unknown",
        content=content,
        config={
            "chunk_token_num": chunk_token_num or settings.chunk_token_num,
            "chunk_overlap_pct": chunk_overlap_pct or settings.chunk_overlap_percent,
            "table_context_size": table_context_size or settings.table_context_size,
        },
    )
    return IngestJobResponse(job_id=job_id, filename=file.filename or "unknown")


@router.get("/{kb_id}")
async def list_documents(kb_id: str, current_user: CurrentUser, limit: int = 20, offset: int = 0):
    from app.db.postgres.repositories.document_repo import DocumentRepository
    repo = DocumentRepository()
    # System KB documents belong to the system user, not the requester —
    # skip the user filter for these so the Documents view isn't always
    # empty (document_count would say otherwise).
    owner_filter = None if is_system_kb(kb_id) else str(current_user.id)
    docs, total = await repo.list_by_kb(kb_id, owner_filter, limit, offset)
    return {
        "total": total,
        "documents": [
            {
                "id": str(d.id), "filename": d.filename, "status": d.status,
                "chunk_count": d.chunk_count, "created_at": int(d.created_at.timestamp()),
            }
            for d in docs
        ],
    }


@router.post("/upload-price/{kb_id}", response_model=IngestJobResponse, status_code=202)
async def upload_price_document(
    kb_id: str,
    file: UploadFile,
    current_user: CurrentUser,
    region: str = Query(..., description="HN | DN | HCM"),
    price_period: str = Query(default="", description='Kỳ công bố, vd "2026-06"'),
):
    """Upload a price-announcement công văn/phụ lục or vendor-quote PDF: runs
    both the normal RAG chunking and structured price-row extraction into
    material_prices (see PriceExtractionPipeline)."""
    if is_system_kb(kb_id):
        raise HTTPException(403, "This knowledge base is system-managed (read-only) — uploads are not allowed")
    if file.size and file.size > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds {MAX_FILE_MB}MB limit")

    content = await file.read()
    job_id = await publish_ingest_job(
        kb_id=kb_id,
        user_id=str(current_user.id),
        filename=file.filename or "unknown",
        content=content,
        config={"region": region, "price_period": price_period},
        mode="price_extraction",
    )
    return IngestJobResponse(job_id=job_id, filename=file.filename or "unknown")


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str, current_user: CurrentUser):
    from app.db.postgres.repositories.document_repo import DocumentRepository
    from app.db.qdrant.client import QdrantStore
    repo = DocumentRepository()
    qdrant = QdrantStore()
    doc = await repo.get_by_id(document_id, str(current_user.id))
    if not doc:
        raise HTTPException(404, "Document not found")
    if is_system_kb(str(doc.kb_id)):
        raise HTTPException(403, "This document belongs to a system-managed knowledge base and cannot be deleted")
    await qdrant.delete_by_document(document_id)
    await repo.delete(document_id, str(current_user.id))
