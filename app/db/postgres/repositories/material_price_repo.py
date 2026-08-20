from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select

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

# Units of measure. These carry a digit, so the "never drop a token with a
# digit" rule below would pin them forever — but a unit is not a product's
# identity, and models append them freely out of their own knowledge. Asked
# for "cáp vặn xoắn LV-ABC-4x95", gpt-4o-mini looked up "LV-ABC-4x95 mm2";
# the row is stored as "LV-ABC-4x95 - 0,6/1kV" with no "mm2" anywhere, so
# every candidate was filtered out and a product that exists was reported as
# missing. Listing them explicitly keeps real codes ("D12", "4x95", "PCB40")
# pinned while letting a stray unit be relaxed away.
_UNIT_TOKENS = {
    "mm",
    "mm2",
    "mm3",
    "cm",
    "cm2",
    "cm3",
    "dm",
    "m2",
    "m3",
    "kg",
    "kn",
    "kw",
    "kva",
    "kv",
    "kwh",
    "mpa",
    "kpa",
    "lit",
    "ml",
    "inch",
    "ton",
    "tan",
}

# A hyphen/space-joined "letters-digits" pair in the QUERY ("BT-01", "D 12")
# is one product code, not two independent words — the letter half is pinned
# alongside the digit half so relaxation can never split them.
#
# Without this: "BT-01 Nishu" (words bt/01/nishu) failed its all-words match
# (Nishu is a manufacturer, never in material_name), and relaxation dropped
# "bt" before "nishu" — "bt" occurs in 122 Hà Nội material_name rows
# (coincidental substring collisions across unrelated products) versus 46 for
# "nishu", and higher raw frequency is read as "less identifying" — leaving
# "01"+"nishu" as the surviving filter. That combination matched a DIFFERENT
# real row ("NISHU KD -01") and returned ITS price with full confidence: not
# a missed lookup, a wrong one. Pinning "bt" because it is glued to "01" in
# the user's own text keeps "bt"+"01" together through relaxation, so only
# "nishu" (the genuinely droppable word here) is ever up for removal.
_CODE_LETTER_PART_RE = re.compile(r"\b([a-zA-Z]+)[-\s]\d", re.UNICODE)


def _has_word(col, word: str):
    """`word` must appear as a WHOLE word in `col`, not as a substring.

    `LIKE '%trung%'` matches "Miền Trung" inside a branch address, and
    `'%dong%'` matches "Thanh Khê Đông" — so a question about the sand supplier
    "Trung Đông" came back with waterproofing paint from Đà Nẵng, because both
    fragments happened to occur in that row's manufacturer string. A regex
    word boundary keeps the tolerance that matters (extra words between the
    user's words) without the accidental collisions.

    Tokens come from `_match_words`, which yields `[0-9a-z]+` only, so there is
    A SECOND lane matches the same word against the column with in-word
    separators removed, because `_match_words` splits on them and the two
    sides then disagree about where a product code begins and ends:

        người dùng gõ "PC30"   -> ['pc30']
        tên trong DB  "PC-30"  -> ['pc', '30']      -> \\mpc30\\M không khớp

    Measured on the live corpus before this lane existed: `cáp điện CXV-150`
    found the row, `cáp điện CXV150` found NOTHING — same product; and
    `xi măng PCB40` returned 14 rows while `xi măng PCB-40` returned 1. The
    generated benchmark put a number on it: queries with a broken code scored
    18 points below queries with the stored spelling, the worst of the four
    axes in every configuration.

    The lane only ADDS candidates — the AND across the user's other words
    still applies, and the "never drop a token with a digit" guard is
    untouched — so it cannot resurrect the wrong-product failures that guard
    exists to prevent."""
    plain = func.lower(func.immutable_unaccent(col))
    squashed = func.regexp_replace(plain, r"[-._/]", "", "g")
    return or_(plain.op("~")(rf"\m{word}\M"), squashed.op("~")(rf"\m{word}\M"))


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
        region: str | None = None,
        material_category: str | None = None,
        material_name: str | None = None,
        manufacturer: str | None = None,
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
        rows = await self._lookup(
            region,
            material_category,
            material_name,
            manufacturer,
            unit,
            exclude_name_keywords,
            limit,
        )
        if rows:
            return rows
        # `material_category` is inconsistently populated in this dataset —
        # sometimes a real category, sometimes a vendor name, sometimes a whole
        # descriptive phrase ("Cáp vặn xoắn hạ thế -0,6/1 kV- (2 lõi…)"). A
        # model passing a sensible category like "dây, cáp điện" then matches
        # nothing and takes the entire lookup down with it, even when name and
        # manufacturer alone would have found the rows. Treat it as a hint:
        # try with it, and if that yields nothing, drop it and try again.
        if material_category:
            rows = await self._lookup(
                region, None, material_name, manufacturer, unit, exclude_name_keywords, limit
            )
            if rows:
                return rows
        # Same reasoning as the material_category fallback above, for
        # material_name this time. A model asking about one manufacturer's
        # whole product line often names the CATEGORY, not a specific
        # product ("đá xây dựng ở mỏ đá Thanh Tâm") — that word never
        # occurs in material_name (it lives in material_category, already
        # dropped and retried above), so the strict all-words-match zeroes
        # out every row even though `manufacturer` alone narrows the search
        # plenty. Only safe to drop when a manufacturer is given — the two
        # together are effectively cataloguing that supplier's line, not a
        # random name-less trawl.
        if material_name and manufacturer:
            rows = await self._lookup(
                region, None, None, manufacturer, unit, exclude_name_keywords, limit
            )
            if rows:
                return rows
        return await self._lookup_raw(region, material_name, manufacturer, limit)

    async def _lookup_raw(
        self, region: str | None, material_name: str | None, manufacturer: str | None, limit: int
    ) -> list[MaterialPrice]:
        """Last resort: search `raw_row_text`, the whole original row.

        Some names a user asks by are in a column the extractor does not map to
        its own field. "Cửa hàng VLXD Trung Đông" is a point of sale recorded
        under commercial terms, while `manufacturer` on that row holds the
        quarry company — so the shop is unfindable through any mapped column,
        yet it is right there in the row. Every word must still appear, and
        this only runs after name and manufacturer have both produced nothing,
        so a match means the phrase genuinely occurs in that source row."""
        term = manufacturer or material_name
        words = _match_words(term) if term else []
        # Three words minimum, not two. `raw_row_text` is the entire source row
        # — technical standards, addresses, delivery notes — so short Vietnamese
        # syllables collide constantly: "Trung Đông" as two words also matched
        # rows containing "Trung Quốc" and "đồng", answering a question about a
        # sand supplier with waterproofing paint from another province. A full
        # name ("Cửa hàng VLXD Trung Đông") clears the bar; an ambiguous
        # fragment returns nothing, which is the honest result.
        if len(words) < 3:
            return []
        async with get_session() as s:
            q = select(MaterialPrice)
            if region:
                q = q.where(MaterialPrice.region == region)
            for w in words:
                q = q.where(_has_word(MaterialPrice.raw_row_text, w))
            q = q.order_by(
                MaterialPrice.price_period.desc().nulls_last(),
                MaterialPrice.created_at.desc(),
            ).limit(limit)
            return list((await s.execute(q)).scalars().all())

    async def _lookup(
        self,
        region: str | None,
        material_category: str | None,
        material_name: str | None,
        manufacturer: str | None,
        unit: str | None,
        exclude_name_keywords: list[str] | None,
        limit: int,
    ) -> list[MaterialPrice]:
        async with get_session() as s:
            # Region is optional: a question naming only a company ("công ty X
            # bán những loại cát nào") has no province in it, and forcing one
            # made the model guess — it picked HN for a supplier that only
            # appears in HCM and got nothing. Searching all regions and
            # labelling each row is honest; guessing is not.
            q = select(MaterialPrice)
            if region:
                q = q.where(MaterialPrice.region == region)
            if material_category:
                # Word-wise for the same reason as material_name. The stored
                # categories in this dataset are whole descriptive phrases
                # ("Cáp vặn xoắn hạ thế -0,6/1 kV- (2 lõi, ruột nhôm…)"), so a
                # model passing a natural category like "dây, cáp điện" matched
                # nothing and the whole lookup came back empty.
                for w in _match_words(material_category):
                    q = q.where(_has_word(MaterialPrice.material_category, w))

            if manufacturer:
                # Matched word-wise for the same reason material_name is: the
                # stored value is a full legal name ("Công ty Cổ Phần dây cáp
                # Điện Việt Nam - Cadivi") while users type the brand alone
                # ("CADIVI"). A whole-phrase ILIKE finds neither direction.
                for w in _match_words(manufacturer):
                    q = q.where(_has_word(MaterialPrice.manufacturer, w))

            def finish(base, words: list[str]):
                stmt = base
                for w in words:
                    stmt = stmt.where(_has_word(MaterialPrice.material_name, w))
                if unit:
                    stmt = stmt.where(MaterialPrice.unit.ilike(f"%{unit}%"))
                for kw in exclude_name_keywords or []:
                    stmt = stmt.where(~MaterialPrice.material_name.ilike(f"%{kw}%"))
                order = []
                if words:
                    order.append(
                        func.similarity(
                            _norm_name(), _strip_accents(material_name or "").lower()
                        ).desc()
                    )
                if manufacturer:
                    # Two common words can each occur as a whole word in an
                    # unrelated string — "Chi Nhánh Miền Trung … Thanh Khê
                    # Đông" satisfies a search for "Trung Đông". Nothing rules
                    # that out as a match, so rank instead: the row whose
                    # manufacturer reads most like what was asked comes first.
                    order.append(
                        func.similarity(
                            func.lower(func.immutable_unaccent(MaterialPrice.manufacturer)),
                            _strip_accents(manufacturer).lower(),
                        ).desc()
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
            # …but a unit of measure carries a digit without being an identity
            # (see _UNIT_TOKENS), so it stays droppable rather than pinned.
            code_letter_parts = {
                m.group(1).lower() for m in _CODE_LETTER_PART_RE.finditer(material_name or "")
            }
            pinned = [
                w
                for w in words
                if (any(c.isdigit() for c in w) or w in code_letter_parts) and w not in _UNIT_TOKENS
            ]
            droppable = [w for w in words if w not in pinned]
            freq = await self._word_frequencies(s, region, droppable) if droppable else {}

            # Units are dropped FIRST, then everything else most-common-first.
            #
            # Frequency alone cannot order these, and getting it wrong is
            # dangerous in BOTH directions. Two words, both matching zero rows:
            #
            #  · "mm2" — descending frequency puts a 0-count word LAST, so
            #    every relaxation still required it and "LV-ABC-4x95 mm2"
            #    reported a cable that exists as not found.
            #  · "hoang"/"thach" — but dropping absent words first leaves only
            #    "xi mang", which matches any cement at all: "xi măng Hoàng
            #    Thạch" (absent from this table) came back as "Xi măng Hà Tiên
            #    Xanh". A confident wrong brand is worse than no answer.
            #
            # What separates them is not how often they occur but WHAT they
            # are: one is a unit the model appended, the other IS the product's
            # identity. Absence of an identity word is itself the answer — the
            # product is not here — so only units get priority to be dropped.
            ordered = sorted(
                droppable, key=lambda w: (w not in _UNIT_TOKENS, -freq.get(w, 0), -len(w))
            )

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

    async def _word_frequencies(
        self, session, region: str | None, words: list[str]
    ) -> dict[str, int]:
        """How many rows contain each word — one round trip, region-scoped when
        a region was given."""
        cols = [
            func.count().filter(_has_word(MaterialPrice.material_name, w)).label(f"w{i}")
            for i, w in enumerate(words)
        ]
        stmt = select(*cols)
        if region:
            stmt = stmt.where(MaterialPrice.region == region)
        row = (await session.execute(stmt)).one()
        return dict(zip(words, row, strict=True))
