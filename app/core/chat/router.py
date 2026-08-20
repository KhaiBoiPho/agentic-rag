"""Request Router — decides HOW a turn is answered, before any retrieval runs.

WHY THE ORDER MATTERS
---------------------
The previous pipeline retrieved first and then hoped the model would reach for
a tool. It doesn't. Asked "giá xi măng Bút Sơn PCB40 ở Hà Nội" with a fat
`Context:` block prefixed to the question, the model answered "không có dữ
liệu" without a single tool call — the very same question with retrieval
disabled called `lookup_material_price` immediately. A large RAG context
actively SUPPRESSES the exact-lookup path it was supposed to complement, and
worse, invites the model to read a number out of whatever table chunk landed
in the top-k regardless of which region it belongs to.

So: routing happens FIRST, and a price question goes to the tool from the
backend — not by asking the model nicely (§3, §11).

DETERMINISTIC RULES BEAT THE CLASSIFIER
---------------------------------------
Rules run before any model call and are the only thing allowed to decide a
clear price question. A classifier that turns "giá xi măng PCB40 ở TP.HCM"
into DOCUMENT_RAG re-creates the exact failure this module exists to prevent,
so the classifier is a fallback for genuinely ambiguous phrasing only, and its
answer is clamped: it can never downgrade a rule-detected price question.

Region detection reuses `intent.detect_regions` — there is deliberately no
second region detector in this codebase (§4).
"""

from __future__ import annotations

import logging
import re
from enum import StrEnum

from pydantic import BaseModel, Field

from app.core.chat.intent import _REGION_KEYWORDS, detect_regions

logger = logging.getLogger(__name__)


class RequestRoute(StrEnum):
    EXACT_STRUCTURED = "exact_structured"
    DOCUMENT_RAG = "document_rag"
    MIXED = "mixed"
    ESTIMATE = "estimate"
    CLARIFY = "clarify"
    GENERAL_CHAT = "general_chat"


class RouteDecision(BaseModel):
    route: RequestRoute
    intent: str
    regions: list[str] = Field(default_factory=list)
    price_period: str | None = None
    material_name: str | None = None
    material_category: str | None = None
    manufacturer: str | None = None
    requested_fields: list[str] = Field(default_factory=list)
    missing_slots: list[str] = Field(default_factory=list)
    confidence: float | None = None
    # "rule" | "classifier" | "fallback" — surfaced in the structured log so a
    # bad route can be traced to whichever layer produced it.
    decided_by: str = "rule"


# ─── Vocabulary ──────────────────────────────────────────────────────────────
#
# Matched against a space-padded, lower-cased message. Kept as plain word lists
# rather than one mega-regex so each phrase is greppable when a route comes out
# wrong in production.

_PRICE_WORDS = [
    "giá",
    "đơn giá",
    "bao nhiêu tiền",
    "bao nhiêu 1",
    "bao nhiêu một",
    "giá bán",
    "giá bao nhiêu",
    "báo giá",
    "mấy tiền",
    "giá thành",
]

# Structured columns that live in `material_prices` — asking for one of these
# about a named product is an exact lookup, not a document search (§4).
_STRUCTURED_FIELD_WORDS: dict[str, list[str]] = {
    "price": _PRICE_WORDS,
    "unit": ["đơn vị tính", "tính theo đơn vị", "đơn vị là gì", "bán theo"],
    "manufacturer": [
        "nhà sản xuất",
        "hãng nào",
        "thương hiệu",
        "do ai sản xuất",
        "sản xuất bởi",
        "thuộc công ty",
        "công ty nào",
        "của công ty nào",
        "của hãng nào",
    ],
    "spec": ["quy cách", "thông số", "kích thước", "chủng loại"],
    "technical_standard": ["tiêu chuẩn kỹ thuật của", "đạt tiêu chuẩn nào", "theo tcvn nào"],
    "price_basis": [
        "tại mỏ",
        "tại chân công trình",
        "điều kiện giao",
        "giao tại đâu",
        "cơ sở giá",
    ],
    "price_period": ["kỳ công bố", "công bố tháng", "giá tháng mấy", "cập nhật lúc nào"],
}

# Narrative content that only exists in the document chunks.
_DOCUMENT_WORDS = [
    "vat",
    "thuế",
    "đã gồm thuế",
    "phạm vi áp dụng",
    "áp dụng cho",
    "điều kiện áp dụng",
    "ghi chú",
    "quy định",
    "quy chuẩn",
    "tiêu chuẩn",
    "tcvn",
    "qcvn",
    "khác nhau",
    "khác gì",
    "so với",
    "phân biệt",
    "loại nào tốt",
    "là gì",
    "nghĩa là",
    "dùng để làm gì",
    "ưu nhược điểm",
    "hướng dẫn",
    "cách chọn",
    "vì sao",
    "tại sao",
]

# Whole-project estimation — the cost/quantity tools, arithmetic in code (§3.0).
_ESTIMATE_WORDS = [
    "dự toán",
    "ước tính chi phí",
    "khối lượng vật liệu",
    "cần bao nhiêu",
    "hết bao nhiêu",
    "tốn bao nhiêu",
    "chi phí xây",
    "xây nhà",
    "làm nhà",
    "thi công",
]
_ESTIMATE_SCALE_RE = re.compile(r"\d+(?:[.,]\d+)?\s*m\s*[²2]", re.IGNORECASE)

# Material vocabulary. A price question needs a SUBJECT — "giá bao nhiêu" with
# no product in it is a CLARIFY, not a lookup on nothing.
_MATERIAL_WORDS = [
    "xi măng",
    "thép",
    "sắt",
    "gạch",
    "cát",
    "đá",
    "sỏi",
    "bê tông",
    "vữa",
    "sơn",
    "cáp",
    "dây điện",
    "ống",
    "kính",
    "gỗ",
    "tôn",
    "nhựa đường",
    "vôi",
    "phụ gia",
    "ngói",
    "vật liệu",
    "vlxd",
    "vật tư",
]
# Product codes are as much an identity as a category word — "PCB40", "D12",
# "CXV-150" name a product even when no category word is present. A single
# optional space is allowed between the letters and digits too ("BT 01", not
# just "BT-01"/"BT01") — how a code is stored ("BT- 01", a space right after
# the hyphen) and how someone types it rarely match exactly, and without this
# "giá bt 01 của công ty" fell through as "names no material at all" even
# though "bt 01" IS the product code, just not glued to its digits.
_PRODUCT_CODE_RE = re.compile(r"\b[a-z]{2,}[-\s]?\d{1,4}\b", re.IGNORECASE)


# "PCB40 khác PCB30 thế nào?" — a product comparison, which lives in the
# narrative chunks. Deliberately NOT the bare word "khác" and NOT "so sánh":
# "so sánh giá thép Hà Nội và Đà Nẵng" is a comparison of two *prices*, which
# is a structured lookup per region, not a document question. Requiring the
# interrogative tail ("… thế nào / ra sao / chỗ nào") separates the two, and
# the price branch runs first anyway, so a price word always wins.
_COMPARISON_RE = re.compile(
    r"\bkhác\b.{0,40}?\b(thế nào|như thế nào|ra sao|chỗ nào|điểm nào|gì)\b", re.IGNORECASE
)


def _has(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


def _matched(text: str, words: list[str]) -> list[str]:
    return [w for w in words if w in text]


def _requested_fields(text: str) -> list[str]:
    return [field for field, words in _STRUCTURED_FIELD_WORDS.items() if _has(text, words)]


def _names_a_material(text: str, raw: str) -> bool:
    return _has(text, _MATERIAL_WORDS) or bool(_PRODUCT_CODE_RE.search(raw))


# ─── Slot extraction ─────────────────────────────────────────────────────────

# Phrases that belong to the QUESTION rather than the PRODUCT. They have to go
# before the name reaches the repository, because `material_name` is matched
# word-by-word with AND semantics: "Giá xi măng PCB40 ở Hồ Chí Minh?" passed
# through verbatim demands that the product name contain "hồ", "chí" and
# "minh", so a row that exists matches nothing. Sorted longest-first so
# "là bao nhiêu" is removed before "bao nhiêu" can leave a fragment behind.
_QUESTION_PHRASES = sorted(
    [
        # Everything that identifies the KIND of question is noise inside the
        # product name: a MIXED turn ("… đã gồm VAT chưa?") and a structured-
        # field turn ("… do nhà sản xuất nào cung cấp?") both carry their
        # question vocabulary into the phrase, and every one of those words
        # would then be demanded of the product name.
        *[w for words in _STRUCTURED_FIELD_WORDS.values() for w in words],
        *_DOCUMENT_WORDS,
        "so sánh",
        "bao gồm",
        "đã gồm",
        "cung cấp",
        "sản xuất",
        "chưa",
        "đã",
        "gồm",
        "nào",
        "do",
        "gì",
        "cho mình hỏi",
        "cho tôi hỏi",
        "cho tôi biết",
        "mình muốn hỏi",
        "tôi muốn hỏi",
        # Generic nouns for "the thing being asked about" — not part of any
        # product's actual name, so left in they get demanded of the
        # material_name column just like the question words above. "Vật liệu
        # bt-01 của công ty Nishu..." (a condensed follow-up) was searching
        # for a product literally named "vật liệu bt-01", which matches
        # nothing.
        "loại vật liệu",
        "vật liệu",
        "sản phẩm",
        "có sẵn",
        "hiện nay",
        "hiện tại",
        "bây giờ",
        "là bao nhiêu",
        "bao nhiêu tiền",
        "bao nhiêu một",
        "bao nhiêu 1",
        "bao nhiêu",
        "giá bao nhiêu",
        "mấy tiền",
        "giá bán",
        "đơn giá",
        "bảng giá",
        "báo giá",
        "giá thành",
        "giá cả",
        "giá",
        "thế nào",
        "như thế nào",
        "ra sao",
        "tra cứu",
        "kiểm tra",
        "khu vực",
        "tại khu vực",
        "vùng",
        "ở đâu",
        "vậy",
        "nhé",
        "ạ",
        "ah",
        "à",
        "thì sao",
        "hả",
        "không",
    ],
    key=len,
    reverse=True,
)

# Leftover connectives once the phrases above are gone.
_DANGLING = {"ở", "tại", "của", "cho", "về", "và", "với", "là", "the", "có", "hỏi", "một", "1"}

# A quarry/company phrase inside a price question ("mỏ đá Thanh Tâm", "công ty
# Cadivi"). MaterialPriceRepository.lookup() matches `manufacturer` word by
# word against exactly this kind of phrase — but only if it is ever passed
# one. Left inside material_name instead, none of "mỏ"/"thanh"/"tâm" occur in
# the actual product name column, so the all-words-must-match rule there
# returns nothing even though the manufacturer alone would have found the
# rows. Cut at the first connective/punctuation that plausibly ends the
# phrase, same boundary style as _QUESTION_PHRASES below.
_MANUFACTURER_LEAD_KEYWORDS = r"mỏ\s+đá|mỏ\s+cát|công\s*ty|cty|nhà\s*máy|doanh\s*nghiệp|hãng"
_MANUFACTURER_LEAD_RE = re.compile(
    rf"\b(?:{_MANUFACTURER_LEAD_KEYWORDS})\b"
    r"(?:(?!\s+(?:ở|tại|của|cho|và|với|là|giá|bao\s+nhiêu|nào|gì|có|còn|sẵn|không)\b)"
    r"[^?!.,;:\"'()])*",
    re.IGNORECASE,
)
# Just the lead keyword itself (+ any separating whitespace/punctuation right
# after it, e.g. "Cty." or "Công ty:") — stripped from extract_manufacturer_
# query's result so the searchable name is "Nishu", not "công ty Nishu". The
# DB abbreviates this boilerplate inconsistently ("C.ty", "Cty", "CTY CP",
# "Công ty CP"...) and MaterialPriceRepository.lookup() requires every word
# of `manufacturer` to match literally — demanding "công" AND "ty" as their
# own words never matches a row spelled "C.ty", so the real distinguishing
# word ("Nishu") never got a chance to run alone.
_MANUFACTURER_LEAD_KEYWORD_ONLY_RE = re.compile(
    rf"^\s*(?:{_MANUFACTURER_LEAD_KEYWORDS})\b[\s.:-]*", re.IGNORECASE
)

# Bare lead phrases with nothing after them once _MANUFACTURER_LEAD_RE's
# negative lookahead has trimmed the match — "công ty nào bán..." stops right
# after "công ty" because "nào" is a stop word, leaving a match that names no
# company at all.
_MANUFACTURER_LEAD_BARE = {
    "mỏ đá", "mỏ cát", "công ty", "cty", "nhà máy", "doanh nghiệp", "hãng",
}


def extract_manufacturer_query(message: str) -> str | None:
    """The manufacturer/quarry phrase inside a price question, or None.

    Returns just the name ("Nishu"), not the generic company-type word in
    front of it ("công ty Nishu") — see _MANUFACTURER_LEAD_KEYWORD_ONLY_RE.

    Returns None rather than the lead phrase alone when nothing follows it —
    "của công ty nào" is a question ABOUT the manufacturer (already covered
    by _REQUEST_FIELD_KEYWORDS), not one naming a specific one, and treating
    "công ty" as itself the manufacturer name filtered every real result out
    of the lookup."""
    m = _MANUFACTURER_LEAD_RE.search(message)
    if not m:
        return None
    out = re.sub(r"\s+", " ", m.group(0)).strip()
    if not out or out.lower() in _MANUFACTURER_LEAD_BARE:
        return None
    name_only = _MANUFACTURER_LEAD_KEYWORD_ONLY_RE.sub("", out).strip()
    return name_only or None


def extract_material_query(message: str, regions: list[str] | None = None) -> str | None:
    """The product phrase inside a price question, or None if there isn't one.

    Strips the region (already captured as its own slot — reusing
    `intent._REGION_KEYWORDS`, not a second table) and the interrogative
    scaffolding, and hands whatever is left to the repository's own word
    matcher, which is tuned for exactly this shape of input.
    """
    text = f" {message.strip()} "
    for code, keywords in _REGION_KEYWORDS:
        if regions is not None and code not in regions:
            continue
        for kw in sorted(keywords, key=len, reverse=True):
            pattern = rf"(?<![\w]){re.escape(kw.strip())}(?![\w])"
            text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    for phrase in _QUESTION_PHRASES:
        text = re.sub(rf"(?<![\w]){re.escape(phrase)}(?![\w])", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[?!.,;:\"'()]+", " ", text)
    tokens = [t for t in text.split() if t.lower() not in _DANGLING]
    out = " ".join(tokens).strip()
    return out or None


# ─── Rule layer ──────────────────────────────────────────────────────────────


def _build_price_decision(
    raw: str, regions: list[str], wants_document: bool, fields: list[str]
) -> RouteDecision:
    """Slot extraction shared by the rule layer AND the classifier fallback.

    Was previously inlined in `route_by_rules` only — `route_by_classifier`
    returned `material_name=None`/`manufacturer=None` even after correctly
    labelling a turn EXACT_STRUCTURED, so any price-shaped question the rule
    layer's word lists didn't happen to cover (a follow-up like "nó thuộc
    công ty nào?" once condensed to "Bột bả nội thất BT-01 thuộc công ty
    nào?") fell through the classifier with an empty product name, and the
    lookup downstream asked for material+region all over again — the
    conversation's context silently vanished. Both layers now build the same
    RouteDecision shape once a message is recognized as a price/attribute
    question, regardless of which layer recognized it."""
    manufacturer = extract_manufacturer_query(raw)
    # Pulled out BEFORE material_name is computed, not after — left in,
    # "mỏ"/"công ty"/etc. and the org name that follows would also count
    # as material_name words, and the repository's all-words-must-match
    # rule then demands them in the PRODUCT name column too, which they
    # are never in. Stripped whenever the LEAD regex matched at all — even a
    # BARE mention ("của công ty" naming no one, manufacturer=None) is still
    # not part of the product's name, so "giá bt 01 của công ty" no longer
    # searches for a product literally named "bt 01 công ty".
    material_source = _MANUFACTURER_LEAD_RE.sub(" ", raw, count=1)
    material = extract_material_query(material_source, regions)

    if not material:
        # "giá bao nhiêu?" with no subject — ask, don't guess (§6.1).
        return RouteDecision(
            route=RequestRoute.CLARIFY,
            intent="price_lookup",
            regions=regions,
            requested_fields=fields,
            missing_slots=["material_name", *([] if regions else ["region"])],
            confidence=0.9,
        )

    # A price question that ALSO asks about VAT/scope/standards needs both
    # lanes: the tool owns the number, RAG owns the prose (§7).
    route = RequestRoute.MIXED if wants_document else RequestRoute.EXACT_STRUCTURED
    if not regions and route is RequestRoute.EXACT_STRUCTURED:
        # No region on a price question. Guessing one is how a Hà Nội
        # number ends up answering a TP.HCM question, so ask instead (§12.5).
        return RouteDecision(
            route=RequestRoute.CLARIFY,
            intent="price_lookup",
            regions=[],
            material_name=material,
            manufacturer=manufacturer,
            requested_fields=fields,
            missing_slots=["region"],
            confidence=0.9,
        )
    return RouteDecision(
        route=route,
        intent="price_lookup",
        regions=regions,
        material_name=material,
        manufacturer=manufacturer,
        requested_fields=fields,
        missing_slots=[] if regions else ["region"],
        confidence=0.95,
    )


def route_by_rules(message: str) -> RouteDecision | None:
    """Deterministic routing. Returns None when nothing fires — only then is
    the classifier consulted."""
    raw = message.strip()
    if not raw:
        return None
    text = f" {raw.lower()} "
    regions = detect_regions(raw)
    fields = _requested_fields(text)
    wants_price = "price" in fields
    wants_document = _has(text, _DOCUMENT_WORDS) or bool(_COMPARISON_RE.search(text))
    names_material = _names_a_material(text, raw)

    # ESTIMATE first: "xây nhà 100 m² ở Hà Nội hết bao nhiêu" contains a price
    # word AND a material-ish word, but it is a whole-project estimate, not a
    # row lookup — the cost tool owns it and every figure is computed in code.
    estimate_signal = _has(text, _ESTIMATE_WORDS) or bool(_ESTIMATE_SCALE_RE.search(raw))
    asks_cost = wants_price or _has(text, ["bao nhiêu", "chi phí", "dự toán"])
    if estimate_signal and asks_cost and not _looks_like_unit_price_question(text):
        missing = [] if regions else ["region"]
        return RouteDecision(
            route=RequestRoute.ESTIMATE,
            intent="construction_cost_estimate",
            regions=regions,
            missing_slots=missing,
            requested_fields=["estimate"],
            confidence=0.95,
        )

    if wants_price or fields:
        if not names_material:
            # "giá bao nhiêu?" with no subject — ask, don't guess (§6.1).
            return RouteDecision(
                route=RequestRoute.CLARIFY,
                intent="price_lookup",
                regions=regions,
                requested_fields=fields,
                missing_slots=["material_name", *([] if regions else ["region"])],
                confidence=0.9,
            )
        return _build_price_decision(raw, regions, wants_document, fields)

    if wants_document and names_material:
        return RouteDecision(
            route=RequestRoute.DOCUMENT_RAG,
            intent="document_question",
            regions=regions,
            requested_fields=_matched(text, _DOCUMENT_WORDS)[:3],
            confidence=0.9,
        )

    return None


def _looks_like_unit_price_question(text: str) -> bool:
    """Distinguish "đơn giá xi măng ở HN" (a row lookup that happens to mention
    a construction word) from "xây nhà 100m2 ở HN hết bao nhiêu" (an estimate).
    The giveaway is an explicit per-unit phrasing."""
    return _has(text, ["đơn giá", "giá 1 ", "giá một ", "/kg", "/tấn", "/m3", "/viên", "một bao"])


# ─── Classifier layer ────────────────────────────────────────────────────────

_CLASSIFIER_SYSTEM = """\
Bạn phân loại câu hỏi của người dùng trong hệ thống tra cứu vật liệu xây dựng.
Chỉ trả lời đúng MỘT nhãn, viết hoa, không giải thích:

EXACT_STRUCTURED — hỏi giá/đơn vị/nhà sản xuất/quy cách/kỳ công bố của một sản
  phẩm cụ thể (dữ liệu này nằm trong bảng có cấu trúc).
DOCUMENT_RAG — hỏi giải thích, so sánh, tiêu chuẩn, VAT, phạm vi áp dụng, ghi
  chú (nội dung nằm trong văn bản).
MIXED — vừa hỏi giá vừa hỏi điều kiện/tiêu chuẩn/VAT.
ESTIMATE — dự toán chi phí/khối lượng cho cả công trình.
CLARIFY — thiếu thông tin bắt buộc (không rõ vật liệu hoặc không rõ khu vực).
GENERAL_CHAT — trò chuyện chung, không thuộc các loại trên.
"""

_LABELS = {r.name: r for r in RequestRoute}


async def route_by_classifier(message: str, llm) -> RouteDecision | None:
    """Model fallback for phrasing the rules don't cover. Fails open (None) —
    an unavailable classifier must not block a legitimate question."""
    from app.config import settings

    try:
        verdict = await llm.chat(
            messages=[
                {"role": "system", "content": _CLASSIFIER_SYSTEM},
                {"role": "user", "content": message},
            ],
            model=settings.openrouter_classifier_model,
            temperature=0.0,
            max_tokens=8,
        )
    except Exception as exc:  # pragma: no cover — network path
        logger.warning("route classifier failed, falling back: %s", exc)
        return None

    label = (verdict or "").strip().upper().split()[0] if verdict and verdict.strip() else ""
    route = _LABELS.get(label)
    if route is None:
        return None

    regions = detect_regions(message)
    if route in (RequestRoute.EXACT_STRUCTURED, RequestRoute.MIXED, RequestRoute.CLARIFY):
        # The classifier only ever sees phrasing route_by_rules' word lists
        # don't cover — but a price/attribute question is still a price/
        # attribute question, and it still needs material_name/manufacturer
        # extracted, or the lookup downstream gets an empty product name and
        # asks for material+region all over again (this used to silently
        # drop conversation context on any follow-up worded outside the rule
        # layer's vocabulary — see _build_price_decision's docstring).
        #
        # CLARIFY is included too: the classifier's own system prompt defines
        # CLARIFY strictly as "thiếu vật liệu hoặc khu vực" (a price question
        # short a slot), so a bare RouteDecision(route=CLARIFY, intent=
        # "classifier") used to reach app/api/v1/chat.py's
        # `decision.route is CLARIFY and decision.intent == "price_lookup"`
        # gate, FAIL it (intent was "classifier", not "price_lookup"), and
        # fall through to a free-form LLM reply instead of the fixed,
        # deterministic missing_slots_reply() — the vague "please describe
        # the material" answer this was built to prevent. Running slot
        # extraction here fixes both problems at once: intent becomes
        # "price_lookup" (all of _build_price_decision's return paths set
        # it), and any slot the classifier's CLARIFY verdict didn't need to
        # ask about (because it's already in the text) gets filled instead
        # of re-asked.
        decision = _build_price_decision(
            message.strip(), regions, wants_document=route is RequestRoute.MIXED, fields=[]
        )
        decision.decided_by = "classifier"
        decision.confidence = 0.6
        return decision

    return RouteDecision(
        route=route,
        intent="classifier",
        regions=regions,
        confidence=0.6,
        decided_by="classifier",
    )


async def route_request(message: str, llm=None) -> RouteDecision:
    """Rules first, classifier only when they abstain, GENERAL_CHAT last.

    The classifier is never allowed to overrule a rule — in particular it can
    never turn a rule-detected price question into a RAG-only answer, which is
    the failure mode §4 calls out by name.
    """
    decision = route_by_rules(message)
    if decision is not None:
        return decision

    if llm is not None:
        classified = await route_by_classifier(message, llm)
        if classified is not None:
            return classified

    return RouteDecision(
        route=RequestRoute.GENERAL_CHAT,
        intent="general_chat",
        regions=detect_regions(message),
        confidence=0.5,
        decided_by="fallback",
    )
