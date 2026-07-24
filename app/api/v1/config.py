"""Config endpoint — exposes available skills and models to the frontend."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

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
