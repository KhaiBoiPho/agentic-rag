"""Usage endpoint — powers the Usage page (chat time/cost/history).

Token counts are real; cost is an estimate against a static per-model price
table (app/core/usage/pricing.py), not pulled live from OpenRouter — see
UsageRecord's docstring in app/db/postgres/models.py for why."""
from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.db.postgres.repositories.usage_repo import UsageRepository

router = APIRouter()


class UsageRecordResponse(BaseModel):
    id: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    duration_ms: int
    created_at: int


class DailyUsage(BaseModel):
    date: str
    cost_usd: float
    messages: int


class UsageResponse(BaseModel):
    total_cost_usd: float
    total_duration_ms: int
    total_messages: int
    total_prompt_tokens: int
    total_completion_tokens: int
    avg_duration_ms: float
    avg_cost_usd: float
    daily: list[DailyUsage]
    history: list[UsageRecordResponse]


@router.get("", response_model=UsageResponse)
async def get_usage(current_user: CurrentUser):
    repo = UsageRepository()
    user_id = str(current_user.id)
    totals = await repo.totals(user_id)
    daily = await repo.daily(user_id)
    history = await repo.recent(user_id)

    return UsageResponse(
        total_cost_usd=totals.total_cost_usd,
        total_duration_ms=totals.total_duration_ms,
        total_messages=totals.total_messages,
        total_prompt_tokens=totals.total_prompt_tokens,
        total_completion_tokens=totals.total_completion_tokens,
        avg_duration_ms=(totals.total_duration_ms / totals.total_messages) if totals.total_messages else 0.0,
        avg_cost_usd=(totals.total_cost_usd / totals.total_messages) if totals.total_messages else 0.0,
        daily=[DailyUsage(date=d, cost_usd=c, messages=n) for d, c, n in daily],
        history=[
            UsageRecordResponse(
                id=str(r.id), model=r.model, prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens, cost_usd=float(r.cost_usd),
                duration_ms=r.duration_ms, created_at=int(r.created_at.timestamp()),
            )
            for r in history
        ],
    )
