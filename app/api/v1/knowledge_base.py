"""Knowledge base CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.core.bootstrap.constants import is_system_kb
from app.db.postgres.repositories.kb_repo import KnowledgeBaseRepository

router = APIRouter()


class KBCreate(BaseModel):
    name: str
    description: str | None = ""
    # Opt-in at creation time; changeable later via PATCH.
    price_extraction: bool = False
    table_heavy_chunking: bool = False


class KBUpdate(BaseModel):
    """Both fields are optional so a client can PATCH one without echoing the
    other's current value back — sending a stale value would silently undo a
    change made in another tab. `price_extraction` stays accepted alone, which
    is the exact shape the existing frontend sends."""

    price_extraction: bool | None = None
    table_heavy_chunking: bool | None = None


class KBResponse(BaseModel):
    id: str
    name: str
    description: str
    document_count: int
    created_at: int
    is_system: bool = False
    price_extraction: bool = False
    table_heavy_chunking: bool = False


def _to_response(kb) -> KBResponse:
    return KBResponse(
        id=str(kb.id),
        name=kb.name,
        description=kb.description or "",
        document_count=kb.document_count,
        created_at=int(kb.created_at.timestamp()),
        is_system=is_system_kb(str(kb.id)),
        price_extraction=kb.price_extraction,
        table_heavy_chunking=kb.table_heavy_chunking,
    )


@router.get("", response_model=list[KBResponse])
async def list_kbs(current_user: CurrentUser):
    repo = KnowledgeBaseRepository()
    # System KBs (seeded at deploy time, see app/core/bootstrap/) are visible
    # to every user alongside their own — see plan for why no ownership
    # flag/model change was needed for this.
    kbs = await repo.list_system() + await repo.list_by_user(str(current_user.id))
    return [_to_response(kb) for kb in kbs]


@router.post("", response_model=KBResponse, status_code=status.HTTP_201_CREATED)
async def create_kb(body: KBCreate, current_user: CurrentUser):
    repo = KnowledgeBaseRepository()
    kb = await repo.create(
        user_id=str(current_user.id),
        name=body.name,
        description=body.description,
        price_extraction=body.price_extraction,
        table_heavy_chunking=body.table_heavy_chunking,
    )
    return _to_response(kb)


@router.patch("/{kb_id}", response_model=KBResponse)
async def update_kb(kb_id: str, body: KBUpdate, current_user: CurrentUser):
    """Toggle the per-KB ingestion settings for FUTURE uploads.

    · `price_extraction` — also parse price rows into material_prices.
    · `table_heavy_chunking` — chunk with the TABLE_HEAVY profile (cap 1.500,
      no table context) instead of STANDARD. See app/core/chunking/profiles.py.

    The two are independent: a long spec table wants the tighter cap but has no
    prices in it, and a short vendor quote has prices but no giant table.

    System KBs are editable here on purpose — unlike deletion, this is
    configuration, and the 4 system KBs are shared by every user so their
    settings have to be reachable from the UI. Already-ingested documents are
    untouched; the flags only decide how the NEXT upload is processed.
    """
    repo = KnowledgeBaseRepository()
    if not is_system_kb(kb_id) and not await repo.get(kb_id, str(current_user.id)):
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if body.price_extraction is None and body.table_heavy_chunking is None:
        raise HTTPException(status_code=400, detail="No settings to update")
    kb = await repo.set_ingest_flags(
        kb_id,
        price_extraction=body.price_extraction,
        table_heavy_chunking=body.table_heavy_chunking,
    )
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return _to_response(kb)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb(kb_id: str, current_user: CurrentUser):
    """Delete a knowledge base and everything derived from it.

    Postgres cascades handle their own side (`KnowledgeBase.documents` ->
    `Document.material_prices`). Qdrant is a SEPARATE store and gets no cascade
    — deleting a KB used to drop the rows and leave every vector behind, which
    in production meant 4.060 orphaned points still carrying the deleted KB's
    `kb_id`. Since retrieval filters on exactly that field, they stayed
    retrievable and kept appearing as citations for a knowledge base the user
    had deleted.

    Order matters. Ownership is verified FIRST, so nobody can wipe another
    user's vectors with a 404-shaped request. Then Qdrant, then Postgres —
    because the two failure modes are not equally bad: vectors gone but rows
    left is visible and fixable by re-uploading, whereas rows gone but vectors
    left is invisible and answers questions wrongly. Fail toward the
    recoverable one.
    """
    if is_system_kb(kb_id):
        raise HTTPException(403, "This knowledge base is system-managed and cannot be deleted")
    repo = KnowledgeBaseRepository()
    if not await repo.get(kb_id, str(current_user.id)):
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    from app.db.qdrant.client import QdrantStore

    await QdrantStore().delete_by_kb(kb_id)
    deleted = await repo.delete(kb_id, str(current_user.id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
