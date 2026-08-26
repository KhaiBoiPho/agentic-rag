"""Price lookup as a service with an explicit outcome — the authoritative
source for every number and every structured field (§5).

WHAT THIS ADDS OVER `MaterialPriceRepository.lookup`
----------------------------------------------------
The repository returns rows or an empty list. That is not enough to answer
safely, because "no rows" has at least three different correct responses:

  · the user never said which region  -> ask (MISSING_SLOTS)
  · several genuinely different products match -> ask which (AMBIGUOUS)
  · nothing matches                    -> say so, and STOP (NOT_FOUND)

The third is the one the old pipeline got wrong. When the tool found nothing,
the answer fell through to whatever RAG had retrieved, and a number from a
neighbouring region's table chunk got presented as the answer. Rule §6 forbids
that outright: NOT_FOUND is a terminal state. No RAG price, no other region's
price, no "close enough" product.

FAIL-CLOSED ALIAS RETRY
-----------------------
Exactly one retry is allowed, and only after canonicalizing the name (§6.3).
The resolver here is DETERMINISTIC — an abbreviation table plus generic-word
stripping — not a RAG lookup. §6 permits a RAG-backed alias resolver under
strict conditions but also says to prefer fail-closed if it raises risk, and a
retrieval step that reads price tables in order to "identify" a product is
precisely the coupling that caused the original bug. So the resolver never
touches the vector store, and by construction it cannot return a number: it
maps a name to another name and nothing else.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


class PriceStatus(StrEnum):
    FOUND = "FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING_SLOTS = "MISSING_SLOTS"
    NOT_FOUND = "NOT_FOUND"
    ERROR = "ERROR"


@dataclass
class MaterialRecord:
    """One `material_prices` row, flattened for the presenter and for source
    provenance. Every field is read from the row — nothing is derived from the
    question, and nothing is invented."""

    row_id: str
    region: str
    material_name: str
    material_category: str
    unit: str
    price: float
    price_basis: str
    source_type: str
    document_id: str
    raw_row_text: str
    spec: str | None = None
    manufacturer: str | None = None
    price_period: str | None = None
    notes: str | None = None
    # Extracted from the row's own text when a standard code is literally
    # printed there (TCVN/QCVN/ASTM/JIS). `material_prices` has no column for
    # it, so this is an extraction, never an inference.
    technical_standard: str | None = None
    # `material_prices` rows carry the source document but not the page they
    # were parsed from, so provenance stops at document_id. Kept in the shape
    # the spec asks for rather than faked with a plausible number.
    page_num: int | None = None

    @property
    def display_name(self) -> str:
        return self.material_name + (f" ({self.spec})" if self.spec else "")


@dataclass
class PriceLookupResult:
    status: PriceStatus
    records: list[MaterialRecord] = field(default_factory=list)
    missing_slots: list[str] = field(default_factory=list)
    # Region(s) and query terms actually used — echoed into the structured log
    # so a wrong answer can be traced to the query that produced it.
    region: str | None = None
    query_name: str | None = None
    query_period: str | None = None
    alias_retry: bool = False
    alias_applied: str | None = None
    # Set when the deterministic alias retry also found nothing and an LLM
    # re-extraction (see app/core/chat/llm_extractor.py) was tried as a last
    # resort — surfaced in the structured log so a route that only worked
    # because of this fallback is traceable, same purpose as alias_applied.
    llm_retry: bool = False
    llm_applied: str | None = None
    error: str | None = None

    @property
    def found(self) -> bool:
        return self.status is PriceStatus.FOUND


_STANDARD_RE = re.compile(
    r"\b(?:TCVN|QCVN|ASTM|JIS|BS\s?EN|EN)\s?[\d]+(?:[-:]\d+)*(?::\d{4})?\b", re.IGNORECASE
)


def _extract_standard(*texts: str | None) -> str | None:
    for t in texts:
        if not t:
            continue
        m = _STANDARD_RE.search(t)
        if m:
            return m.group(0).strip()
    return None


def _to_record(row) -> MaterialRecord:
    return MaterialRecord(
        row_id=str(row.id),
        region=row.region,
        material_name=row.material_name,
        material_category=row.material_category or "",
        unit=row.unit,
        price=float(row.price_ex_vat),
        price_basis=row.price_basis or "",
        source_type=row.source_type or "",
        document_id=str(row.document_id),
        raw_row_text=row.raw_row_text or "",
        spec=row.spec,
        manufacturer=row.manufacturer,
        price_period=row.price_period,
        notes=row.notes,
        technical_standard=_extract_standard(row.spec, row.notes, row.raw_row_text),
    )


# ─── Deterministic alias resolution (§6.3) ───────────────────────────────────

# Curated both-ways abbreviations that appear in this corpus. Kept short and
# hand-checked: a wrong alias silently answers with the wrong product, which is
# the one outcome the price path is built to avoid.
_ALIASES: list[tuple[str, str]] = [
    ("xm", "xi măng"),
    ("bt", "bê tông"),
    ("btct", "bê tông cốt thép"),
    ("vlxd", "vật liệu xây dựng"),
    ("cp", "cấp phối"),
]

# Words that describe the QUESTION, not the product. Stripping them is safe —
# the repository's own word matcher already drops most of them, but a name like
# "bảng giá xi măng PCB40" reaching the DB with "bảng" still attached narrows
# it to nothing.
_GENERIC_WORDS = {
    "giá",
    "bảng",
    "báo",
    "đơn",
    "loại",
    "vật",
    "liệu",
    "hiện",
    "nay",
    "bao",
    "nhiêu",
    "tiền",
    "mua",
    "bán",
    "của",
    "cho",
    "về",
    "tại",
    "ở",
    "là",
    "thế",
    "nào",
}

# "PCB 40" and "PCB-40" are the same code as "PCB40". The repository has a lane
# for separator differences already; this closes the *space* case, which that
# lane cannot see because the tokenizer splits on it first.
#
# UPPERCASE letters only, deliberately. Product codes are written in caps in
# this corpus (PCB40, CXV, D12), while lower-case letter+number pairs are
# ordinary Vietnamese ("gach 4 lo", "cat 3"), and joining those invents a
# product code that exists nowhere.
_SPACED_CODE_RE = re.compile(r"\b([A-Z]{1,6})[\s-]+(\d{1,4})\b")


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    ).replace("đ", "d")


def canonicalize_material_name(name: str) -> str | None:
    """Return a canonical spelling to retry with, or None when it would be the
    same query again (so the caller doesn't burn a pointless round trip).

    Never returns a price, a region, or a different product — only a different
    spelling of the same words. That is the whole contract (§6.3).
    """
    if not name:
        return None
    out = _SPACED_CODE_RE.sub(r"\1\2", name.strip())

    words = out.split()
    kept = [w for w in words if w.lower().strip(".,") not in _GENERIC_WORDS]
    out = " ".join(kept) if kept else out

    # Expand a known abbreviation (xm -> xi măng) or contract the long form,
    # whichever the input isn't already using.
    low = _strip_accents(out.lower())
    for short, long in _ALIASES:
        if re.search(rf"\b{re.escape(short)}\b", low):
            out = re.sub(rf"\b{re.escape(short)}\b", long, out, flags=re.IGNORECASE)
            break
        if _strip_accents(long) in low:
            break

    out = " ".join(out.split())
    if not out or out.strip().lower() == name.strip().lower():
        return None
    return out


# ─── Ambiguity ───────────────────────────────────────────────────────────────

# Two rows are "the same answer in different words" when they name the same
# product; they are genuinely different answers when the names differ AND the
# prices differ enough that picking one for the user would materially change
# what they are told. 25% is well outside the brand-to-brand spread seen within
# one cement/steel grade in this corpus, and well inside the gap between
# actually-different products.
_AMBIGUOUS_SPREAD = 0.25


def _is_ambiguous(records: list[MaterialRecord]) -> bool:
    if len(records) < 2:
        return False
    names = {r.material_name.strip().lower() for r in records}
    if len(names) < 2:
        return False
    prices = [r.price for r in records if r.price > 0]
    if len(prices) < 2:
        return False
    lo, hi = min(prices), max(prices)
    return (hi - lo) / lo > _AMBIGUOUS_SPREAD


# ─── The service ─────────────────────────────────────────────────────────────


async def lookup_material_record(
    *,
    region: str | None = None,
    material_name: str | None = None,
    material_category: str | None = None,
    manufacturer: str | None = None,
    requested_fields: list[str] | None = None,
    limit: int = 10,
    repo=None,
    llm=None,
    raw_message: str | None = None,
) -> PriceLookupResult:
    """Structured price lookup. `repo` is injectable so the decision logic is
    testable without a database.

    Slot rules: a PRICE question needs a region — answering "giá xi măng ở TP
    HCM" with a Hà Nội row is the bug, and the only way to be sure is to have
    been told. A CATALOGUE question ("công ty X bán những loại cát nào") does
    not: it names a company, has no province in it, and forcing one made the
    model guess (it picked HN for a supplier that only appears in HCM).

    `llm`/`raw_message` are optional and only used as a THIRD attempt, after
    the direct query and the deterministic alias retry both find nothing —
    see llm_extractor.py's docstring for why this exists and why it is a
    fallback rather than the primary extraction path. Omitting them (the
    default) reproduces the exact behaviour before this fallback existed.
    """
    fields = requested_fields or ["price"]
    wants_price = "price" in fields

    if repo is None:
        from app.db.postgres.repositories.material_price_repo import MaterialPriceRepository

        repo = MaterialPriceRepository()

    missing: list[str] = []
    if not (material_name or material_category or manufacturer):
        missing.append("material_name")
    if wants_price and not region:
        missing.append("region")
    if missing:
        return PriceLookupResult(
            status=PriceStatus.MISSING_SLOTS,
            missing_slots=missing,
            region=region,
            query_name=material_name,
        )

    async def _query(name: str | None) -> list[MaterialRecord]:
        rows = await repo.lookup(
            region=region,
            material_category=material_category,
            material_name=name,
            manufacturer=manufacturer,
            limit=limit,
        )
        return [_to_record(r) for r in rows]

    try:
        records = await _query(material_name)
        alias_retry = False
        alias_applied = None

        if not records and material_name:
            # ONE retry, canonical spelling only (§6.3).
            alias = canonicalize_material_name(material_name)
            if alias:
                alias_retry = True
                alias_applied = alias
                records = await _query(alias)

        llm_retry = False
        llm_applied: str | None = None
        if not records and llm is not None and raw_message:
            # Last resort: the deterministic paths (raw query + alias) both
            # found nothing. Re-derive slots from the ORIGINAL message — not
            # from `material_name`, which may itself be the garbled output of
            # a phrase-list miss — and try each candidate once, in order,
            # stopping at the first that finds a row. Still the exact same
            # strict repository lookup; this only supplies better query
            # strings to it (§6.3's contract, extended to an LLM-sourced
            # candidate instead of a fixed alias table).
            from app.core.chat.llm_extractor import extract_slots_llm

            slots = await extract_slots_llm(raw_message, llm)
            if slots is not None:
                candidates = [c for c in slots.code_variants if c]
                if slots.material_name and slots.material_name not in candidates:
                    candidates.append(slots.material_name)
                for candidate in candidates:
                    if candidate.strip().lower() == (material_name or "").strip().lower():
                        continue
                    records = await _query(candidate)
                    if records:
                        llm_retry = True
                        llm_applied = candidate
                        break
    except Exception as exc:
        logger.exception("price lookup failed")
        return PriceLookupResult(
            status=PriceStatus.ERROR,
            region=region,
            query_name=material_name,
            error=str(exc),
        )

    if not records:
        # Terminal. The caller must NOT substitute a RAG number, another
        # region's number, or a similar product (§6.4).
        return PriceLookupResult(
            status=PriceStatus.NOT_FOUND,
            region=region,
            query_name=material_name,
            alias_retry=alias_retry,
            alias_applied=alias_applied,
            llm_retry=llm_retry,
            llm_applied=llm_applied,
        )

    # Defence in depth: the repository already filters by region, but a row
    # that slipped through with the wrong region must never reach the answer.
    if region:
        records = [r for r in records if r.region == region]
        if not records:
            return PriceLookupResult(
                status=PriceStatus.NOT_FOUND,
                region=region,
                query_name=material_name,
                alias_retry=alias_retry,
                alias_applied=alias_applied,
                llm_retry=llm_retry,
                llm_applied=llm_applied,
            )

    status = (
        PriceStatus.AMBIGUOUS if (wants_price and _is_ambiguous(records)) else PriceStatus.FOUND
    )
    return PriceLookupResult(
        status=status,
        records=records,
        region=region,
        query_name=material_name,
        alias_retry=alias_retry,
        alias_applied=alias_applied,
        llm_retry=llm_retry,
        llm_applied=llm_applied,
    )
