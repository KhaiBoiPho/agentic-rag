from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select

from app.db.postgres.base import get_session
from app.db.postgres.models import UsageRecord


@dataclass
class UsageTotals:
    total_cost_usd: float
    total_duration_ms: int
    total_messages: int
    total_prompt_tokens: int
    total_completion_tokens: int


class UsageRepository:
    async def record(
        self, user_id: str, model: str, prompt_tokens: int, completion_tokens: int,
        cost_usd: float, duration_ms: int,
    ) -> None:
        async with get_session() as s:
            s.add(UsageRecord(
                user_id=uuid.UUID(user_id), model=model,
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                cost_usd=cost_usd, duration_ms=duration_ms,
            ))

    async def totals(self, user_id: str) -> UsageTotals:
        async with get_session() as s:
            result = await s.execute(
                select(
                    func.coalesce(func.sum(UsageRecord.cost_usd), 0),
                    func.coalesce(func.sum(UsageRecord.duration_ms), 0),
                    func.count(UsageRecord.id),
                    func.coalesce(func.sum(UsageRecord.prompt_tokens), 0),
                    func.coalesce(func.sum(UsageRecord.completion_tokens), 0),
                ).where(UsageRecord.user_id == uuid.UUID(user_id))
            )
            cost, duration, count, ptok, ctok = result.one()
            return UsageTotals(
                total_cost_usd=float(cost), total_duration_ms=int(duration), total_messages=int(count),
                total_prompt_tokens=int(ptok), total_completion_tokens=int(ctok),
            )

    async def recent(self, user_id: str, limit: int = 50) -> list[UsageRecord]:
        async with get_session() as s:
            result = await s.execute(
                select(UsageRecord)
                .where(UsageRecord.user_id == uuid.UUID(user_id))
                .order_by(UsageRecord.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def daily(self, user_id: str, days: int = 14) -> list[tuple[str, float, int]]:
        """Returns [(date_str, cost_usd, message_count), ...] for the last
        `days` days, oldest first — feeds the Usage page's simple bar chart."""
        async with get_session() as s:
            day_col = func.date_trunc("day", UsageRecord.created_at)
            result = await s.execute(
                select(day_col, func.sum(UsageRecord.cost_usd), func.count(UsageRecord.id))
                .where(UsageRecord.user_id == uuid.UUID(user_id))
                .group_by(day_col)
                .order_by(day_col.desc())
                .limit(days)
            )
            rows = list(result.all())
            return [(d.date().isoformat(), float(c), int(n)) for d, c, n in reversed(rows)]
