"""Normalized answer-source metadata — one shape for tool, RAG and web citations.

WHY THIS MODULE EXISTS (the P0 "wrong region on the UI" bug)
-----------------------------------------------------------
Region metadata was present at every stage of the pipeline except the one that
mattered:

    upload (region=HCM)
      -> documents.doc_metadata.region        ✅ stored
      -> chunk.metadata.region                ✅ stored (price_pipeline.py)
      -> Qdrant payload metadata.region       ✅ stored
      -> RetrievedChunk.region                ✅ read back (retriever.py)
      -> `sources` wire dict                  ❌ DROPPED — only
                                                 {chunk_id, document_name,
                                                  content, score} survived
      -> SSE done event                       ❌ no region
      -> message persistence                  ❌ no region
      -> frontend chip                        ❌ renders document_name

With nothing but the filename to render, a chip for
`BangGia-VLXD-DaNang-Thang06-2026.pdf` reads as "Đà Nẵng" to a user who asked
about TP. Hồ Chí Minh — and because the chunk really was a Đà Nẵng chunk, this
was not a labelling glitch: a wrong-region source was genuinely being retrieved
and displayed. Two things were missing, and this module supplies both: region
survives serialization, and a source carrying a region nobody asked about is
removed before the SSE `done` event.

RULES ENCODED HERE (see also docs/kien-truc-chi-tiet.md)
  1. Region is NEVER inferred — not from the filename, not from the KB name,
     not from the answer text, and above all not from the region the user asked
     about. It comes from `material_prices.region` (tool) or
     `payload.metadata.region` (Qdrant), or it stays None.
  2. A source whose region contradicts the request is DROPPED, never relabelled.
  3. `region=None` is kept only when the chunk is genuinely region-neutral —
     a legacy untagged chunk that quotes another region's price table is not.
  4. Dedupe uses a composite key that includes region, so a two-region
     comparison can't collapse into one chip.

Backward compatibility: `to_wire()` still emits the four legacy keys
(`chunk_id`, `document_name`, `content`, `score`) that the pre-fix frontend and
every persisted conversation rely on, and `from_wire()` reads a legacy dict
back without inventing a region for it.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel

SourceKind = Literal["tool", "rag", "web"]
SourceAuthority = Literal["authoritative", "supporting", "unverified"]
SourceUse = Literal["price", "structured_field", "explanation", "estimate"]

# THE single region -> display-name mapping (rule §8.3). Everything that shows
# a region to a user goes through `region_label`; there is no second table.
# HN/DN/HCM are the three published-price regions; KH/AG exist in the price
# corpus too (see app/api/v1/documents.py VALID_REGIONS) and must not be
# dropped just because the P0 report only named three.
REGION_LABELS: dict[str, str] = {
    "HN": "Hà Nội",
    "DN": "Đà Nẵng",
    "HCM": "TP. Hồ Chí Minh",
    "KH": "Khánh Hoà",
    "AG": "An Giang",
}
NO_REGION_LABEL = "Không gắn vùng"


def region_label(region: str | None) -> str:
    """Display name for a region code. `None` is a real, honest value — a
    legacy chunk with no region tag renders as "Không gắn vùng" and is never
    back-filled with the region of the request (rule §8.8)."""
    if not region:
        return NO_REGION_LABEL
    return REGION_LABELS.get(region, region)


class AnswerSource(BaseModel):
    """One citation, as it travels from DB/Qdrant to the SSE `done` event."""

    source_id: str
    source_kind: SourceKind
    authority: SourceAuthority
    used_for: SourceUse
    document_id: str | None = None
    kb_id: str | None = None
    filename: str | None = None
    page_num: int | None = None
    chunk_id: str | None = None
    row_id: str | None = None
    # Deliberately `str | None`, not Literal["HN","DN","HCM"] — the corpus also
    # holds KH/AG, and a validation error on a legitimate region would take the
    # whole answer down over a citation chip.
    region: str | None = None
    price_period: str | None = None
    score: float | None = None
    # What `score` means, so a renderer never turns an RRF score into a
    # percentage: "cosine" (dense-only), "rrf" (hybrid fusion — a sum of
    # reciprocal ranks, ~0,033 at the top), "exact" (a material_prices row,
    # which is not a similarity at all).
    score_kind: str = "cosine"
    used_in_answer: bool = True
    # Payload kept for rendering: RAG chips show the snippet, web citations the
    # link. Not part of the identity used for dedupe.
    content: str | None = None
    url: str | None = None
    title: str | None = None

    # ─── Wire format ─────────────────────────────────────────────────────────

    def to_wire(self) -> dict[str, Any]:
        """Serialize for SSE + message persistence.

        Emits the legacy keys alongside the normalized ones so a client built
        against the old contract keeps working unchanged:
          · `document_name` + `score` + `chunk_id` + `content` → RAG chip
          · `url` + `title`                                    → web citation
        New clients read `source_kind` / `region` / `authority` instead of
        guessing from which keys happen to be present.
        """
        wire: dict[str, Any] = {
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "authority": self.authority,
            "used_for": self.used_for,
            "document_id": self.document_id,
            "kb_id": self.kb_id,
            "filename": self.filename,
            "page_num": self.page_num,
            "chunk_id": self.chunk_id,
            "row_id": self.row_id,
            "region": self.region,
            "region_label": region_label(self.region),
            "price_period": self.price_period,
            "score": self.score,
            "score_kind": self.score_kind,
            "used_in_answer": self.used_in_answer,
        }
        if self.source_kind == "web":
            wire["url"] = self.url
            wire["title"] = self.title
        else:
            # legacy RAG-chip shape — `document_name` is what the pre-fix
            # frontend keys `isRagSource` off, so it must stay populated.
            wire["document_name"] = self.filename or self.title or ""
            wire["content"] = self.content
        return wire

    @classmethod
    def from_wire(cls, data: dict[str, Any]) -> AnswerSource:
        """Read a wire dict back — including one persisted before this schema
        existed. A legacy row has no region, and gets None rather than a
        back-filled guess (rule §8.8/§8.9)."""
        if "source_kind" in data:
            return cls.model_validate(data)
        # Legacy: infer only the SHAPE (which keys are present), never the region.
        if data.get("url"):
            return cls(
                source_id=str(data.get("url")),
                source_kind="web",
                authority="unverified",
                used_for="price",
                url=data.get("url"),
                title=data.get("title"),
            )
        return cls(
            source_id=str(data.get("chunk_id") or data.get("document_name") or ""),
            source_kind="rag",
            authority="supporting",
            used_for="explanation",
            chunk_id=data.get("chunk_id"),
            filename=data.get("document_name"),
            content=data.get("content"),
            score=data.get("score"),
        )


# ─── Constructors ────────────────────────────────────────────────────────────


def rag_source(chunk, *, used_for: SourceUse = "explanation", used_in_answer: bool = True):
    """From a `RetrievedChunk`. Region comes from the Qdrant payload metadata
    the retriever already read — the empty string Qdrant returns for an
    untagged chunk normalizes to None, not to ''."""
    return AnswerSource(
        source_id=f"rag:{chunk.chunk_id}",
        source_kind="rag",
        authority="supporting",
        used_for=used_for,
        document_id=chunk.document_id or None,
        filename=chunk.document_name or None,
        page_num=chunk.page_num or None,
        chunk_id=chunk.chunk_id,
        region=(getattr(chunk, "region", "") or None),
        price_period=(getattr(chunk, "price_period", "") or None),
        score=chunk.score,
        score_kind=getattr(chunk, "score_kind", "cosine"),
        content=chunk.content,
        used_in_answer=used_in_answer,
    )


def tool_source(
    *,
    row_id: str,
    region: str | None = None,
    document_id: str | None = None,
    filename: str | None = None,
    price_period: str | None = None,
    page_num: int | None = None,
    content: str | None = None,
    used_for: SourceUse = "price",
) -> AnswerSource:
    """From a `material_prices` row. `authoritative` because the number in the
    answer is this row's number verbatim — the tool is the source of truth for
    prices and structured fields (§5), RAG never overrides it."""
    return AnswerSource(
        source_id=f"tool:{row_id}",
        source_kind="tool",
        authority="authoritative",
        used_for=used_for,
        document_id=document_id,
        filename=filename,
        page_num=page_num,
        row_id=row_id,
        region=region,
        price_period=price_period,
        score=1.0,
        score_kind="exact",
        content=content,
    )


def web_source(*, url: str, title: str | None = None) -> AnswerSource:
    """From the Firecrawl price fallback. Always `unverified` — never blended
    silently with published prices (§10)."""
    return AnswerSource(
        source_id=f"web:{url}",
        source_kind="web",
        authority="unverified",
        used_for="price",
        url=url,
        title=title,
    )


# ─── Region filtering ────────────────────────────────────────────────────────

# A chunk that carries no region tag but visibly quotes another region's price
# table is not "region-neutral" — see `filter_sources_by_region`. Detecting the
# quote needs (a) another region named in the text and (b) something that looks
# like money; a knowledge chunk that merely mentions "Hà Nội" in passing has no
# price in it and stays.
_PRICE_SHAPED = re.compile(r"\d[\d.,]{4,}\s*(?:đ|vnđ|vnd|đồng)", re.IGNORECASE)


def _quotes_other_region_price(content: str | None, allowed: set[str]) -> bool:
    if not content:
        return False
    # Reuse the ONE region detector (§4: no second region detector) rather than
    # re-implementing the keyword table here.
    from app.core.chat.intent import detect_regions

    named = set(detect_regions(content))
    if not named or named <= allowed:
        return False
    return bool(_PRICE_SHAPED.search(content))


def filter_sources_by_region(
    sources: list[AnswerSource], requested_regions: list[str]
) -> tuple[list[AnswerSource], list[AnswerSource]]:
    """Split sources into (kept, dropped) for the regions this request is about.

    Returns the dropped list too so the caller can log
    `source_region_filtered_total` and the before/after region sets — silently
    discarding citations is exactly the kind of thing that made the original
    bug hard to see.

    · No requested region (a general/knowledge question) → keep everything.
    · Region tagged and not asked for → drop. Never relabel (rule §8.4).
    · Region None → keep, unless the text quotes another region's prices.
    """
    if not requested_regions:
        return list(sources), []
    allowed = set(requested_regions)
    kept: list[AnswerSource] = []
    dropped: list[AnswerSource] = []
    for s in sources:
        if s.region is not None:
            (kept if s.region in allowed else dropped).append(s)
        elif _quotes_other_region_price(s.content, allowed):
            dropped.append(s)
        else:
            kept.append(s)
    return kept, dropped


# ─── Dedupe ──────────────────────────────────────────────────────────────────


def _dedupe_key(s: AnswerSource) -> tuple:
    """Composite key from rule §8.7. Region and price_period are IN the key on
    purpose: the same annex PDF holds rows for several regions and periods, and
    keying on the filename alone merged them — which is how a two-region
    comparison answer came back showing a single region's chip."""
    return (
        s.source_kind,
        s.document_id,
        s.page_num,
        s.region,
        s.price_period,
        s.chunk_id or s.row_id or s.url,
    )


def dedupe_sources(sources: list[AnswerSource]) -> list[AnswerSource]:
    seen: set[tuple] = set()
    out: list[AnswerSource] = []
    for s in sources:
        key = _dedupe_key(s)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def source_kinds(sources: list[AnswerSource]) -> set[str]:
    """Which kinds actually back this answer — drives the UI badge (§8.10):
    tool-only → "Tra cứu dữ liệu", RAG-only → "RAG", both → "Tool + RAG"."""
    return {s.source_kind for s in sources if s.used_in_answer}


def to_wire(sources: list[AnswerSource]) -> list[dict[str, Any]]:
    return [s.to_wire() for s in sources]
