"""Note CRUD endpoints — free-standing personal scratchpad, not linked to
any chat message or conversation."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.db.postgres.repositories.note_repo import NoteRepository

router = APIRouter()


class NoteCreate(BaseModel):
    title: str = ""
    content: str = ""


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class NoteResponse(BaseModel):
    id: str
    title: str
    content: str
    created_at: int
    updated_at: int


def _to_response(note) -> NoteResponse:
    return NoteResponse(
        id=str(note.id), title=note.title, content=note.content,
        created_at=int(note.created_at.timestamp()), updated_at=int(note.updated_at.timestamp()),
    )


@router.get("", response_model=list[NoteResponse])
async def list_notes(current_user: CurrentUser):
    repo = NoteRepository()
    notes = await repo.list_by_user(str(current_user.id))
    return [_to_response(n) for n in notes]


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(body: NoteCreate, current_user: CurrentUser):
    repo = NoteRepository()
    note = await repo.create(user_id=str(current_user.id), title=body.title, content=body.content)
    return _to_response(note)


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(note_id: str, body: NoteUpdate, current_user: CurrentUser):
    repo = NoteRepository()
    note = await repo.update(note_id, str(current_user.id), body.title, body.content)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return _to_response(note)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: str, current_user: CurrentUser):
    repo = NoteRepository()
    deleted = await repo.delete(note_id, str(current_user.id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Note not found")
