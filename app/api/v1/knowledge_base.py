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


class KBUpdate(BaseModel):
    price_extraction: bool


class KBResponse(BaseModel):
    id: str
    name: str
    description: str
    document_count: int
    created_at: int
    is_system: bool = False
    price_extraction: bool = False


def _to_response(kb) -> KBResponse:
    return KBResponse(
        id=str(kb.id),
        name=kb.name,
        description=kb.description or "",
        document_count=kb.document_count,
        created_at=int(kb.created_at.timestamp()),
        is_system=is_system_kb(str(kb.id)),
        price_extraction=kb.price_extraction,
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
    )
    return _to_response(kb)


@router.patch("/{kb_id}", response_model=KBResponse)
async def update_kb(kb_id: str, body: KBUpdate, current_user: CurrentUser):
    """Toggle structured price extraction for future uploads.

    System KBs are editable here on purpose — unlike deletion, this is
    configuration, and the 4 system KBs are shared by every user so their
    settings have to be reachable from the UI. Already-ingested documents are
    untouched; the flag only decides which pipeline the NEXT upload runs.
    """
    repo = KnowledgeBaseRepository()
    if not is_system_kb(kb_id) and not await repo.get(kb_id, str(current_user.id)):
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    kb = await repo.set_price_extraction(kb_id, body.price_extraction)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return _to_response(kb)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb(kb_id: str, current_user: CurrentUser):
    if is_system_kb(kb_id):
        raise HTTPException(403, "This knowledge base is system-managed and cannot be deleted")
    repo = KnowledgeBaseRepository()
    deleted = await repo.delete(kb_id, str(current_user.id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
