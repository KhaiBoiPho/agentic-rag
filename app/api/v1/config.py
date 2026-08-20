"""Config endpoint — exposes available skills and models to the frontend."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from app.config import settings

router = APIRouter()

_SKILLS_DIR = Path(__file__).parent.parent.parent / "core" / "skills"

_SKILL_META = {
    "write": {"label": "Write", "icon": "✏️", "description": "Writing & editing assistant"},
    "learn": {"label": "Learn", "icon": "📚", "description": "Patient tutor for any subject"},
    "code": {"label": "Code", "icon": "</> ", "description": "Senior engineer & code reviewer"},
    "chill": {"label": "Chill", "icon": "😎", "description": "Casual conversation & ideas"},
    "life": {"label": "Life stuff", "icon": "🌱", "description": "Life coach & practical advisor"},
}


def load_skill_prompt(skill_id: str) -> str | None:
    path = _SKILLS_DIR / f"{skill_id}.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return None


@router.get("/skills")
async def get_skills():
    skills = []
    for sid, meta in _SKILL_META.items():
        if (_SKILLS_DIR / f"{sid}.md").exists():
            skills.append({"id": sid, **meta})
    return {"skills": skills}


@router.get("/chat")
async def get_chat_config():
    """What the chat UI needs to agree with the backend about.

    `default_model` exists so the frontend stops shipping its own copy of the
    production model id: the two drifted, and the model shown in the picker was
    not the model a request without an explicit `model` actually used. The
    frontend reads this and falls back to its bundled constant only if the call
    fails (offline/first paint).

    Deliberately no API key, no base URL, no provider credentials.
    """
    return {
        "default_model": settings.openrouter_chat_model,
        "default_mode": "auto",
        "regions": [
            {"code": "HN", "label": "Hà Nội"},
            {"code": "DN", "label": "Đà Nẵng"},
            {"code": "HCM", "label": "TP. Hồ Chí Minh"},
        ],
        "allow_web_fallback_default": True,
    }
