from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select

from app.db.postgres.base import get_session
from app.db.postgres.models import MaterialPrice


@dataclass
class MaterialPriceRow:
    """One parsed price row, ready to persist. Mirrors MaterialPrice columns
    minus the identifiers assigned at insert time."""
    region: str
    material_category: str
    material_name: str
    unit: str
    price_ex_vat: float
    price_basis: str
    source_type: str
    raw_row_text: str
    spec: str | None = None
    price_period: str | None = None
    manufacturer: str | None = None
    notes: str | None = None


def _trunc(value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    return value if len(value) <= max_len else value[:max_len]


class MaterialPriceRepository:
    async def bulk_create(
        self, document_id: str, kb_id: str, rows: list[MaterialPriceRow]
    ) -> int:
        if not rows:
            return 0
        async with get_session() as s:
            s.add_all(
                MaterialPrice(
                    document_id=uuid.UUID(document_id),
                    kb_id=uuid.UUID(kb_id),
                    region=_trunc(r.region, 8),
                    material_category=_trunc(r.material_category, 128),
                    material_name=_trunc(r.material_name, 512),
                    spec=_trunc(r.spec, 512),
                    unit=_trunc(r.unit, 32),
                    price_ex_vat=r.price_ex_vat,
                    price_basis=_trunc(r.price_basis, 32),
                    source_type=_trunc(r.source_type, 32),
                    price_period=_trunc(r.price_period, 16),
                    manufacturer=_trunc(r.manufacturer, 255),
                    notes=r.notes,
                    raw_row_text=r.raw_row_text,
                )
                for r in rows
            )
            return len(rows)

    async def lookup(
        self,
        region: str,
        material_category: str | None = None,
        material_name: str | None = None,
        unit: str | None = None,
        exclude_name_keywords: list[str] | None = None,
        limit: int = 10,
    ) -> list[MaterialPrice]:
        """Exact/prefix lookup for the tool layer — newest price_period first.
        Deliberately not a fuzzy/semantic search: a wrong material match here
        means a wrong construction cost, so callers must narrow with category
        or name filters rather than relying on ranking alone.

        `unit` matters as much as name: `material_category` in this dataset
        is inconsistently populated (sometimes a real category, sometimes a
        vendor company name, sometimes blank), so a name-only match can
        silently pick up a wrong product (e.g. "TIÊN SƠN" — a company name —
        matching a "sơn"/paint search). Filtering by expected unit rejects
        most such false matches even when the name/category text lines up."""
        async with get_session() as s:
            q = select(MaterialPrice).where(MaterialPrice.region == region)
            if material_category:
                q = q.where(MaterialPrice.material_category.ilike(f"%{material_category}%"))
            if material_name:
                q = q.where(MaterialPrice.material_name.ilike(f"%{material_name}%"))
            if unit:
                q = q.where(MaterialPrice.unit.ilike(f"%{unit}%"))
            for kw in exclude_name_keywords or []:
                q = q.where(~MaterialPrice.material_name.ilike(f"%{kw}%"))
            q = q.order_by(
                MaterialPrice.price_period.desc().nulls_last(),
                MaterialPrice.created_at.desc(),
            ).limit(limit)
            result = await s.execute(q)
            return list(result.scalars().all())
