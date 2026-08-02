from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select

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


# Words too short or too common to narrow anything down. "loại"/"loai" and
# "giá" show up in questions, never usefully in a product name.
_STOPWORDS = {
    "gia",
    "cua",
    "loai",
    "vat",
    "lieu",
    "bao",
    "nhieu",
    "mot",
    "va",
    "co",
    "cho",
    "tai",
    "o",
    "la",
    "voi",
    "theo",
}
_MIN_WORD_LEN = 2


def _norm_name():
    """material_name lower-cased and stripped of diacritics, matching the
    expression the GIN index in migration 0009 is built on."""
    return func.lower(func.immutable_unaccent(MaterialPrice.material_name))


def _strip_accents(text: str) -> str:
    return (
        "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
        .replace("đ", "d")
        .replace("Đ", "D")
    )


def _match_words(name: str) -> list[str]:
    """Accent-stripped, lower-cased words a candidate must all contain.

    Stopwords are dropped so "giá xi măng Bút Sơn" does not demand the literal
    word "giá" in the product name. Short fragments are dropped too — a
    one-character token matches nearly every row and would only slow the
    query down without narrowing it."""
    words = re.findall(r"[0-9a-z]+", _strip_accents(name).lower())
    return [w for w in words if len(w) >= _MIN_WORD_LEN and w not in _STOPWORDS]


def _trunc(value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    return value if len(value) <= max_len else value[:max_len]


class MaterialPriceRepository:
    async def bulk_create(self, document_id: str, kb_id: str, rows: list[MaterialPriceRow]) -> int:
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
        most such false matches even when the name/category text lines up.

        `material_name` is matched WORD BY WORD, not as one substring, and
        without diacritics (migration 0009). A single `ILIKE '%…%'` needs the
        user's words contiguous and in order, which real questions are not:
        "xi măng Bút Sơn PCB40" found nothing while the answer sat in a row
        named "Xi măng bao Bút Sơn Xanh đa dụng PCB40" — same words, with
        "bao" and "Xanh đa dụng" interleaved. Requiring every word to appear
        keeps the match strict (all of them, not any) while tolerating extra
        words between them, and the survivors are ranked by trigram
        similarity so the closest name comes first."""
        async with get_session() as s:
            q = select(MaterialPrice).where(MaterialPrice.region == region)
            if material_category:
                q = q.where(MaterialPrice.material_category.ilike(f"%{material_category}%"))

            def finish(base, words: list[str]):
                stmt = base
                for w in words:
                    stmt = stmt.where(_norm_name().like(f"%{w}%"))
                if unit:
                    stmt = stmt.where(MaterialPrice.unit.ilike(f"%{unit}%"))
                for kw in exclude_name_keywords or []:
                    stmt = stmt.where(~MaterialPrice.material_name.ilike(f"%{kw}%"))
                order = (
                    [
                        func.similarity(
                            _norm_name(), _strip_accents(material_name or "").lower()
                        ).desc()
                    ]
                    if words
                    else []
                )
                return stmt.order_by(
                    *order,
                    MaterialPrice.price_period.desc().nulls_last(),
                    MaterialPrice.created_at.desc(),
                ).limit(limit)

            words = _match_words(material_name) if material_name else []
            if material_name and not words:
                q = q.where(MaterialPrice.material_name.ilike(f"%{material_name}%"))
                words = []

            rows = list((await s.execute(finish(q, words))).scalars().all())
            if rows or len(words) < 2:
                return rows

            # Nothing matched every word. Real product names are terser than
            # the question — "cáp điện CXV-150" is stored as "CXV-150 -
            # 0,6/1kV", "xi măng Vicem Hà Tiên Xây tô" as "XM Vicem Hà Tiên
            # Xây tô" — so the generic words the user added are simply not in
            # the name. Drop them, most common first, and keep the rare ones:
            # those are the model codes and brands that identify the product.
            #
            # Relaxing this way rather than by fuzzy similarity is deliberate.
            # pg_trgm's word_similarity ranks "Vicem Hạ Long Xây tô" (0.742)
            # ABOVE "Vicem Hà Tiên Xây tô" (0.741) for a Hà Tiên question —
            # the wrong brand, first, with a confident score. Keeping the
            # rarest words as hard filters cannot do that: a candidate must
            # still contain every one of them.
            # Tokens carrying a digit are never dropped: a model code or size
            # ("D12", "CXV-150", "PCB40") IS the product's identity, and
            # frequency does not say so — "d12" occurs in 49 Hà Nội rows while
            # "nhat" occurs in 15, so a purely frequency-ordered drop threw
            # away "d12" first and answered "thép Việt Nhật D12" with a glass
            # partition whose brand happens to be "kính Việt Nhật".
            pinned = [w for w in words if any(c.isdigit() for c in w)]
            droppable = [w for w in words if w not in pinned]
            freq = await self._word_frequencies(s, region, droppable) if droppable else {}
            ordered = sorted(droppable, key=lambda w: (-freq.get(w, 0), -len(w)))

            # Never relax below two required words. One word is not a product
            # identity: "xi măng Hoàng Thạch" (a cement absent from this
            # table) relaxed down to "hoang" and returned an aluminium
            # ceiling. Stopping at two leaves it with no answer, which is the
            # honest outcome — the price tool's whole contract is that "not
            # found" beats a confident wrong product.
            for drop in range(1, len(ordered) + 1):
                kept = pinned + ordered[drop:]
                if len(kept) < 2:
                    break
                rows = list((await s.execute(finish(q, kept))).scalars().all())
                if rows:
                    return rows
            return []

    async def _word_frequencies(self, session, region: str, words: list[str]) -> dict[str, int]:
        """How many rows in this region contain each word — one round trip."""
        cols = [
            func.count().filter(_norm_name().like(f"%{w}%")).label(f"w{i}")
            for i, w in enumerate(words)
        ]
        row = (await session.execute(select(*cols).where(MaterialPrice.region == region))).one()
        return dict(zip(words, row, strict=True))
