"""LLM slot re-extraction — the fallback tier for when the regex/phrase-list
extraction in router.py got the wrong product name (or none at all).

WHY THIS EXISTS
----------------
`extract_material_query` (router.py) strips a fixed list of question phrases
("giá", "cho tôi biết", "hiện nay", ...) out of the raw message and hands
whatever survives to the repository's word matcher. Any phrasing the list
doesn't happen to cover leaves noise words glued to the real product name —
"tôi muốn biết giá thép xây dựng ở hà nội" (no "tôi muốn biết" entry in the
list at the time this was written) extracted as "tôi muốn biết thép xây
dựng", which matches no row even though "giá thép ở Hà Nội" is answerable.
A fixed phrase list can always be defeated by a phrasing nobody enumerated —
that is a structural property of the approach, not a bug in one list.

Product codes have the same problem from the other direction: "PCB-40" and
"PCB 40" are already normalized by the SQL layer (see
material_price_repo.py's `_has_word`) and by `canonicalize_material_name`'s
`_SPACED_CODE_RE`, but a stranger split like "PC B40" defeats both — the
tokenizer disagrees about where the code begins, and there's no way to
enumerate every possible OCR/typo split as a regex.

WHY THIS IS A FALLBACK, NOT THE PRIMARY PATH
---------------------------------------------
Called ONLY after the deterministic rule extraction *and* the deterministic
alias retry have both failed to find a row (see
`lookup_material_record` in app/core/pricing/service.py). This keeps the
common case — rule extraction already works for most phrasing — free of any
added latency or cost, and keeps the LLM off the critical path for the
questions that don't need it.

FAIL-CLOSED, LIKE EVERYTHING ELSE ON THE PRICE PATH
-----------------------------------------------------
This function only ever proposes ALTERNATE QUERY STRINGS to retry through
the exact same strict repository lookup (region filter, all-words-match,
ambiguity check) that every other query goes through. It never returns a
price, never bypasses the repository, and never gets a second chance to
"guess more" if its own proposal also finds nothing — the caller applies
this exactly once, same as the deterministic alias retry. A parse failure,
timeout, or malformed response all fail open to None, same posture as
`route_by_classifier`: an unavailable LLM must not block or corrupt the
answer, it just means one fewer retry attempt.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ExtractedSlots(BaseModel):
    material_name: str | None = None
    manufacturer: str | None = None
    material_category: str | None = None
    # Alternate spellings of a product code the model thinks are the same
    # product, typo/OCR-split included ("PC B40" -> "PCB40"). Capped at 2 by
    # the prompt — this is a retry budget, not an open-ended guess list.
    code_variants: list[str] = Field(default_factory=list)


_SYSTEM_PROMPT = """\
Bạn trích xuất thông tin sản phẩm từ câu hỏi giá vật liệu xây dựng tiếng Việt.

Chỉ trích xuất những gì CÓ THẬT trong câu hỏi. Không suy đoán, không bịa thêm
thông tin không có trong câu. Bỏ hết các từ hỏi/lịch sự không thuộc tên sản
phẩm (VD: "tôi muốn biết", "cho mình hỏi", "hiện nay giá", "ở đâu", "vậy",
"nhé"...) — chỉ giữ lại đúng tên sản phẩm/vật liệu.

Nếu câu hỏi có mã sản phẩm bị viết tách rời bất thường (lỗi gõ hoặc OCR,
ví dụ "PC B40" thay vì "PCB40"), đề xuất tối đa 2 cách viết lại hợp lý vào
"code_variants". Nếu không có mã sản phẩm nào đáng ngờ, để trống mảng đó.

Trả lời DUY NHẤT một JSON object, không kèm giải thích, đúng format:
{"material_name": "<tên sản phẩm hoặc null>", "manufacturer": "<tên nhà sản \
xuất/hãng nếu có, hoặc null>", "material_category": "<phân loại nếu câu hỏi \
nêu rõ, VD 'nội thất'/'ngoại thất', hoặc null>", "code_variants": ["..."]}
"""


async def extract_slots_llm(message: str, llm) -> ExtractedSlots | None:
    """Re-derive material_name/manufacturer/category/code variants straight
    from the raw message, or None on any failure (fail open)."""
    try:
        from app.config import settings

        raw = await llm.chat(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            model=settings.openrouter_classifier_model,
            temperature=0.0,
            max_tokens=200,
        )
    except Exception as exc:  # pragma: no cover — network path
        logger.warning("llm slot extraction failed, falling back: %s", exc)
        return None

    if not raw or not raw.strip():
        return None

    text = raw.strip()
    # Models sometimes wrap JSON in a ```json fence despite instructions not
    # to — strip it rather than fail the whole extraction over formatting.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("llm slot extraction returned non-JSON: %r", raw[:200])
        return None

    if not isinstance(data, dict):
        return None

    try:
        slots = ExtractedSlots.model_validate(data)
    except Exception:
        return None

    # An all-empty extraction is not useful as a retry candidate.
    if not slots.material_name and not slots.manufacturer and not slots.code_variants:
        return None
    return slots
