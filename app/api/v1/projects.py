"""Project CRUD endpoints — a saved bundle of Knowledge Bases. Chatting
"in" a project retrieves RAG context across every attached KB at once
(app/core/retrieval/retriever.py, app/api/v1/chat.py::project_id) instead
of being limited to a single KB per conversation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.db.postgres.repositories.project_repo import ProjectRepository

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str
    description: str | None = ""


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ProjectKBsUpdate(BaseModel):
    kb_ids: list[str]


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    kb_ids: list[str]
    kb_names: list[str]
    created_at: int
    updated_at: int


def _to_response(project) -> ProjectResponse:
    return ProjectResponse(
        id=str(project.id),
        name=project.name,
        description=project.description or "",
        kb_ids=[str(kb.id) for kb in project.knowledge_bases],
        kb_names=[kb.name for kb in project.knowledge_bases],
        created_at=int(project.created_at.timestamp()),
        updated_at=int(project.updated_at.timestamp()),
    )


@router.get("", response_model=list[ProjectResponse])
async def list_projects(current_user: CurrentUser):
    repo = ProjectRepository()
    projects = await repo.list_by_user(str(current_user.id))
    return [_to_response(p) for p in projects]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, current_user: CurrentUser):
    repo = ProjectRepository()
    project = await repo.create(
        user_id=str(current_user.id), name=body.name, description=body.description or ""
    )
    return _to_response(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, body: ProjectUpdate, current_user: CurrentUser):
    repo = ProjectRepository()
    project = await repo.rename(project_id, str(current_user.id), body.name, body.description)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project = await repo.get(project_id, str(current_user.id))
    return _to_response(project)


@router.put("/{project_id}/knowledge-bases", response_model=ProjectResponse)
async def set_project_kbs(project_id: str, body: ProjectKBsUpdate, current_user: CurrentUser):
    repo = ProjectRepository()
    project = await repo.set_kbs(project_id, str(current_user.id), body.kb_ids)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return _to_response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str, current_user: CurrentUser):
    repo = ProjectRepository()
    deleted = await repo.delete(project_id, str(current_user.id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
