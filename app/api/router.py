from fastapi import APIRouter

from app.api import health
from app.api.v1 import (
    auth,
    chat,
    config,
    documents,
    knowledge_base,
    notes,
    projects,
    research,
    search,
    usage,
    voice,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
api_router.include_router(knowledge_base.router, prefix="/v1/kb", tags=["knowledge-base"])
api_router.include_router(documents.router, prefix="/v1/documents", tags=["documents"])
api_router.include_router(chat.router, prefix="/v1/chat", tags=["chat"])
api_router.include_router(research.router, prefix="/v1/research", tags=["research"])
api_router.include_router(search.router, prefix="/v1/search", tags=["search"])
api_router.include_router(voice.router, prefix="/v1/voice", tags=["voice"])
api_router.include_router(config.router, prefix="/v1/config", tags=["config"])
api_router.include_router(notes.router, prefix="/v1/notes", tags=["notes"])
api_router.include_router(projects.router, prefix="/v1/projects", tags=["projects"])
api_router.include_router(usage.router, prefix="/v1/usage", tags=["usage"])
