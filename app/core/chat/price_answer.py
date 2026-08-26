"""Turning a `PriceLookupResult` into an answer — and, just as importantly,
into a REFUSAL when there is no verified price to give.

Division of labour (§5, §6, §7):
  · The tool decides WHAT the numbers are. Every figure in the reply is a
    `material_prices` value copied verbatim.
  · The LLM decides only HOW to say it. It is a presenter over a fact sheet,
    the same pattern the cost form already uses (`COST_PRESENT_PROMPT`), and
    it is forbidden from adding, adjusting or rounding a number.
  · RAG may add prose — VAT, scope of application, publication notes — and may
    never contribute a price, a unit or a region.

The NOT_FOUND / MISSING_SLOTS / AMBIGUOUS replies here don't call a model at
all. They are fixed Vietnamese text built from the slots, because the one
thing a model must never do at that moment is be helpful with a number.
"""

from __future__ import annotations

import re

from app.core.chat.sources import AnswerSource, region_label, tool_source
from app.core.pricing.service import MaterialRecord, PriceLookupResult, PriceStatus

_BASIS_LABELS = {
    "tai_mo": "tại nơi sản xuất",
    "tai_chan_cong_trinh": "tại chân công trình",
    "dai_ly": "tại đại lý",
    "khong_ro": "không rõ",
}
_SOURCE_TYPE_LABELS = {
    "official_announcement": "công bố Sở Xây dựng",
    "official_annex": "phụ lục công bố Sở Xây dựng",
    "vendor_quote": "báo giá nhà cung cấp",
}

_SLOT_QUESTIONS = {
    "region": (
        "bạn muốn xem giá ở khu vực nào — Hà Nội, Đà Nẵng hay TP. Hồ Chí Minh?"
    ),
    "material_name": "bạn muốn tra giá vật liệu nào (ví dụ: xi măng PCB40, thép D12, cát xây tô)?",
    "price_period": "bạn cần giá của kỳ công bố nào?",
}

# `material_prices.unit` is raw, unnormalized text lifted straight from the
# source document — many rows already carry a currency prefix ("đ/thùng",
# "Đ/Bao", "đồng/tấn "), others don't ("ống", "kg", "m"). Blindly formatting
# every record as f"đ/{rec.unit}" produced "đ/đồng/ống", "đ/đ/m" — a real
# duplication bug seen in production, not just a cosmetic one, since it makes
# the unit unreadable. Strip a leading currency token before adding "đ/" back
# in a single, consistent place.
_CURRENCY_PREFIX_RE = re.compile(r"^\s*(đồng|đ)\s*/\s*", re.IGNORECASE)


def _price_unit_suffix(price: float, unit: str) -> str:
    """"{price:,.0f} đ/{unit}" with any currency prefix already baked into
    `unit` stripped first, so the result never doubles up ("đ/đồng/ống")."""
    clean_unit = _CURRENCY_PREFIX_RE.sub("", unit or "").strip()
    if not clean_unit:
        return f"{price:,.0f} đ"
    return f"{price:,.0f} đ/{clean_unit}"


# ─── Presenter ───────────────────────────────────────────────────────────────

PRICE_PRESENT_PROMPT = """\
Bạn là trợ lý tra cứu vật liệu xây dựng. Trình bày lại DỮ LIỆU TRA CỨU dưới đây
thành câu trả lời gọn gàng bằng tiếng Việt cho câu hỏi của người dùng.

QUY TẮC BẮT BUỘC:
- GIỮ NGUYÊN 100% mọi con số, đơn vị, tên sản phẩm, khu vực và kỳ công bố.
  TUYỆT ĐỐI không đổi số, không làm tròn khác đi, không quy đổi đơn vị,
  không thêm bất kỳ mức giá nào không có trong dữ liệu.
- CHỈ dùng dữ liệu dưới đây. Không bổ sung giá từ kiến thức chung của bạn.
- Nêu rõ khu vực và kỳ công bố của mức giá.
- Nếu có phần "TƯ LIỆU THAM KHẢO", chỉ dùng nó để giải thích (VAT, phạm vi áp
  dụng, ghi chú, tiêu chuẩn). TUYỆT ĐỐI không lấy con số giá từ phần đó, và
  không dùng nó để sửa giá/khu vực/đơn vị ở phần dữ liệu tra cứu.
- Nếu câu hỏi có phần mà dữ liệu không trả lời được, nói thẳng là chưa có dữ
  liệu cho phần đó thay vì suy đoán.
- Markdown gọn (in đậm số tiền). Không dùng emoji.

CÂU HỎI: {question}

DỮ LIỆU TRA CỨU (nguồn có thẩm quyền — bảng giá đã công bố / báo giá):
{facts}
{supporting}
Viết câu trả lời:
"""


def _record_line(rec: MaterialRecord) -> str:
    bits = [
        f"- {rec.display_name}",
        f"khu vực {region_label(rec.region)}",
        f"đơn giá {_price_unit_suffix(rec.price, rec.unit)}",
    ]
    if rec.price_basis:
        bits.append(f"điều kiện giao: {_BASIS_LABELS.get(rec.price_basis, rec.price_basis)}")
    if rec.price_period:
        bits.append(f"kỳ công bố {rec.price_period}")
    if rec.manufacturer:
        bits.append(f"nhà sản xuất {rec.manufacturer}")
    if rec.size_spec:
        bits.append(f"quy cách {rec.size_spec}")
    if rec.technical_standard:
        bits.append(f"tiêu chuẩn {rec.technical_standard}")
    if rec.source_type:
        bits.append(_SOURCE_TYPE_LABELS.get(rec.source_type, rec.source_type))
    return " | ".join(bits)


def build_price_facts(records: list[MaterialRecord]) -> str:
    """Number-exact fact sheet. What the model sees is what the user gets.

    Takes records rather than a single result so a multi-region comparison
    ("giá thép ở Hà Nội và Đà Nẵng") is one fact sheet with every region
    labelled — merging at the fact-sheet level is what keeps both regions in
    the answer instead of one of them winning.
    """
    lines = [_record_line(r) for r in records]
    lines.append("")
    lines.append(
        "Đây là giá CHƯA gồm VAT trừ khi dòng dữ liệu ghi khác. "
        "Không được suy ra mức giá cho khu vực hoặc sản phẩm không có ở trên."
    )
    return "\n".join(lines)


def missing_regions_note(results: list[PriceLookupResult]) -> str:
    """For a multi-region question where only some regions have data.

    Without this, a comparison of Hà Nội and TP.HCM in which only Hà Nội has a
    row comes back looking like a complete answer about Hà Nội — the region
    that has no verified price simply vanishes, which reads as "these are the
    prices" rather than "one of the two is missing".
    """
    absent = [
        region_label(r.region)
        for r in results
        if not r.found and r.status is PriceStatus.NOT_FOUND and r.region
    ]
    if not absent:
        return ""
    return (
        "\nKHÔNG có dữ liệu giá đã xác minh cho: "
        + ", ".join(absent)
        + ". Phải nói rõ điều này trong câu trả lời, và TUYỆT ĐỐI không dùng giá của "
        "khu vực khác để thay cho khu vực còn thiếu.\n"
    )


def build_price_prompt(
    question: str,
    records: list[MaterialRecord],
    supporting_context: str = "",
    results: list[PriceLookupResult] | None = None,
) -> str:
    supporting = ""
    if supporting_context.strip():
        supporting = (
            "\nTƯ LIỆU THAM KHẢO (chỉ dùng cho phần giải thích — KHÔNG lấy số từ đây):\n"
            f"{supporting_context}\n"
        )
    facts = build_price_facts(records) + missing_regions_note(results or [])
    return PRICE_PRESENT_PROMPT.format(
        question=question, facts=facts, supporting=supporting
    )


# ─── Deterministic replies (no model call) ───────────────────────────────────


def missing_slots_reply(result: PriceLookupResult) -> str:
    asks = [_SLOT_QUESTIONS[s] for s in result.missing_slots if s in _SLOT_QUESTIONS]
    if not asks:
        asks = ["bạn bổ sung thêm thông tin giúp mình nhé?"]
    if len(asks) == 1:
        return f"Để tra đúng giá, {asks[0]}"
    return "Để tra đúng giá, mình cần thêm:\n" + "\n".join(f"- {a.capitalize()}" for a in asks)


def ambiguous_reply(result: PriceLookupResult) -> str:
    """Several genuinely different products matched. Ask which — do not pick
    one, and do not average them (§6.2)."""
    lines = [
        "Có nhiều sản phẩm khớp với yêu cầu của bạn, giá chênh nhau đáng kể "
        "nên mình không tự chọn thay bạn. Bạn muốn xem loại nào?",
        "",
    ]
    for rec in result.records[:5]:
        lines.append(f"- {rec.display_name} — {_price_unit_suffix(rec.price, rec.unit)}")
    return "\n".join(lines)


def not_found_reply(result: PriceLookupResult, material: str | None = None) -> str:
    """The terminal state. Deliberately offers no number and no substitute —
    not another region's price, not a similar product, not a RAG figure (§6.4).
    """
    what = material or result.query_name or "sản phẩm này"
    where = region_label(result.region) if result.region else None
    scope = f" tại {where}" if where else ""
    period = f" kỳ {result.query_period}" if getattr(result, "query_period", None) else ""
    return (
        f"Không tìm thấy dữ liệu giá đã xác minh cho “{what}”{scope}{period} "
        "trong bảng giá đã công bố và báo giá nhà cung cấp hiện có.\n\n"
        "Mình không lấy giá của khu vực khác hay của sản phẩm gần giống để thay thế, "
        "vì như vậy sẽ đưa ra một con số không đúng nguồn. Bạn có thể thử nêu tên sản "
        "phẩm chính xác hơn (theo cách ghi trên bảng giá), hoặc chọn một khu vực khác "
        "để mình tra lại."
    )


def error_reply() -> str:
    """An outage is not the same claim as "this product has no price"."""
    return (
        "Mình chưa truy vấn được dữ liệu giá lúc này (lỗi hệ thống tra cứu). "
        "Bạn thử lại sau giúp mình nhé — mình không đưa ra con số ước chừng khi "
        "chưa đọc được dữ liệu gốc."
    )


def deterministic_reply(result: PriceLookupResult, material: str | None = None) -> str | None:
    """The non-FOUND replies, or None when the lookup succeeded."""
    if result.status is PriceStatus.MISSING_SLOTS:
        return missing_slots_reply(result)
    if result.status is PriceStatus.AMBIGUOUS:
        return ambiguous_reply(result)
    if result.status is PriceStatus.NOT_FOUND:
        return not_found_reply(result, material)
    if result.status is PriceStatus.ERROR:
        return error_reply()
    return None


# ─── Provenance ──────────────────────────────────────────────────────────────


async def price_sources(records: list[MaterialRecord]) -> list[AnswerSource]:
    """Authoritative provenance for the rows actually used in the answer.

    Region comes from `material_prices.region` — the row's own column, not the
    region the user asked about and not the document's filename (rule §8.2).
    """
    if not records:
        return []

    filenames = await _document_filenames({r.document_id for r in records})
    return [
        tool_source(
            row_id=rec.row_id,
            region=rec.region,
            document_id=rec.document_id,
            filename=filenames.get(rec.document_id),
            price_period=rec.price_period,
            page_num=rec.page_num,
            content=rec.raw_row_text,
            used_for="price",
        )
        for rec in records
    ]


async def _document_filenames(document_ids: set[str]) -> dict[str, str]:
    """document_id -> filename, for the citation chip label."""
    if not document_ids:
        return {}
    import uuid as _uuid

    from sqlalchemy import select

    from app.db.postgres.base import get_session
    from app.db.postgres.models import Document

    try:
        ids = [_uuid.UUID(d) for d in document_ids]
    except (ValueError, AttributeError):
        return {}
    async with get_session() as s:
        stmt = select(Document.id, Document.filename).where(Document.id.in_(ids))
        rows = (await s.execute(stmt)).all()
    return {str(doc_id): filename for doc_id, filename in rows}
