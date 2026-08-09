"""Document upload — publishes ingestion job to RabbitMQ, returns job_id."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.core.bootstrap.constants import is_system_kb
from app.core.chunking.profiles import ChunkProfile, profile_for
from app.queue.publisher import publish_ingest_job

router = APIRouter()

MAX_FILE_MB = 50


class IngestJobResponse(BaseModel):
    job_id: str
    filename: str
    status: str = "queued"


async def _kb_ingest_settings(kb_id: str) -> tuple[bool, ChunkProfile]:
    """(runs price extraction?, which chunking profile) for this KB.

    One lookup for both, because every upload needs both and they used to be
    fetched — or in the price path's case, not fetched at all — separately.
    """
    from app.db.postgres.repositories.kb_repo import KnowledgeBaseRepository

    kb = await KnowledgeBaseRepository().get_by_id(kb_id)
    if kb is None:
        return False, profile_for(False)
    return bool(kb.price_extraction), profile_for(bool(kb.table_heavy_chunking))


@router.post("/upload/{kb_id}", response_model=IngestJobResponse, status_code=202)
async def upload_document(
    kb_id: str,
    file: UploadFile,
    current_user: CurrentUser,
    region: str = Query(default="", description="HN | DN | HCM | KH — bắt buộc nếu KB bật trích giá"),
    price_period: str = Query(default="", description='Kỳ công bố, vd "2026-06"'),
    # Per-upload overrides on top of the KB's profile. Left unset by the UI —
    # they exist for one-off tuning and for the eval scripts.
    chunk_token_num: int = Query(default=None),
    chunk_overlap_pct: int = Query(default=None),
    table_context_size: int = Query(default=None),
    table_cap_tokens: int = Query(default=None),
):
    """Normal upload. If the target KB has `price_extraction` on, this runs the
    price pipeline instead — the caller doesn't have to know which endpoint to
    pick, the KB's own setting decides."""
    if file.size and file.size > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds {MAX_FILE_MB}MB limit")

    price_extraction, profile = await _kb_ingest_settings(kb_id)
    profile = profile.with_overrides(
        text_token_num=chunk_token_num,
        overlap_percent=chunk_overlap_pct,
        table_context_size=table_context_size,
        table_cap_tokens=table_cap_tokens,
    )

    if price_extraction:
        return await _publish_price_job(
            kb_id, file, current_user, region, price_period, profile
        )

    content = await file.read()
    job_id = await publish_ingest_job(
        kb_id=kb_id,
        user_id=str(current_user.id),
        filename=file.filename or "unknown",
        content=content,
        config=profile.to_config(),
    )
    return IngestJobResponse(job_id=job_id, filename=file.filename or "unknown")


VALID_REGIONS = {"HN", "DN", "HCM", "KH", "AG"}


async def _publish_price_job(
    kb_id: str,
    file: UploadFile,
    current_user: CurrentUser,
    region: str,
    price_period: str,
    profile: ChunkProfile | None = None,
) -> IngestJobResponse:
    """Region is mandatory for every price extraction, not just the published-
    price KB: `material_prices.region` is what both `lookup_material_price` and
    region-scoped RAG retrieval filter on, so a row stored without one can
    never be found again. Rejecting the upload is better than silently
    ingesting price data that no query will ever reach.
    """
    if region not in VALID_REGIONS:
        raise HTTPException(
            400,
            "Kho tri thức này bật trích xuất giá vật liệu — cần chọn vùng giá "
            "(HN | DN | HCM | KH) khi tải tài liệu lên.",
        )
    content = await file.read()
    job_id = await publish_ingest_job(
        kb_id=kb_id,
        user_id=str(current_user.id),
        filename=file.filename or "unknown",
        content=content,
        # The chunk settings used to be omitted here, so a price KB always got
        # the defaults no matter what — which meant the one corpus that most
        # needed the table-heavy profile was the one corpus that could not be
        # given it.
        config={
            "region": region,
            "price_period": price_period,
            **(profile or profile_for(False)).to_config(),
        },
        mode="price_extraction",
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
                "id": str(d.id),
                "filename": d.filename,
                "status": d.status,
                "chunk_count": d.chunk_count,
                # Present (possibly 0) only for documents that went through the
                # price pipeline. 0 is meaningful — it tells the user the file
                # was scanned for price tables and none were readable — so it
                # must stay distinguishable from null ("not a price document").
                "price_row_count": (d.doc_metadata or {}).get("price_row_count"),
                "price_warning_count": (d.doc_metadata or {}).get("warning_count"),
                "created_at": int(d.created_at.timestamp()),
            }
            for d in docs
        ],
    }


@router.post("/upload-price/{kb_id}", response_model=IngestJobResponse, status_code=202)
async def upload_price_document(
    kb_id: str,
    file: UploadFile,
    current_user: CurrentUser,
    region: str = Query(..., description="HN | DN | HCM | KH"),
    price_period: str = Query(default="", description='Kỳ công bố, vd "2026-06"'),
):
    """Upload a price-announcement công văn/phụ lục or vendor-quote PDF: runs
    both the normal RAG chunking and structured price-row extraction into
    material_prices (see PriceExtractionPipeline).

    Kept as an explicit endpoint for callers that want price extraction for a
    single upload without changing the KB's setting. The KB-driven path
    (`/upload/{kb_id}` + `knowledge_bases.price_extraction`) is what the UI
    uses; there is no longer a fixed list of KBs allowed to feed
    material_prices."""
    if file.size and file.size > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds {MAX_FILE_MB}MB limit")
    # Still honours the KB's chunking profile — this endpoint bypasses the
    # `price_extraction` flag, not the chunking one.
    _, profile = await _kb_ingest_settings(kb_id)
    return await _publish_price_job(
        kb_id, file, current_user, region, price_period, profile
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str, current_user: CurrentUser):
    from app.db.postgres.repositories.document_repo import DocumentRepository
    from app.db.qdrant.client import QdrantStore

    repo = DocumentRepository()
    qdrant = QdrantStore()
    doc = await repo.get_by_id(document_id, str(current_user.id))
    if not doc:
        raise HTTPException(404, "Document not found")
    # Ownership scopes deletion to whichever user uploaded it (including for
    # documents inside a system KB — see is_system_kb's docstring). Deleting
    # a pricing-KB document also removes the material_prices rows extracted
    # from it — see DocumentRepository.delete().
    await qdrant.delete_by_document(document_id)
    await repo.delete(document_id, str(current_user.id))
