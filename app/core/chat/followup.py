"""Follow-up query condensing for multi-turn RAG.

A short deictic follow-up ("còn ở Đà Nẵng thì sao?", "loại kia thì sao?")
carries almost no searchable terms on its own, so embedding it retrieves
noise and the model loses the thread. Naively prepending the whole previous
turn helps a little but injects conflicting signal (the prior turn's own
region/subject), which can push the correct chunk below the score threshold.

Rewriting the follow-up into a standalone question with a cheap/fast model —
the standard RAG "condense question" step — gives retrieval a clean query
("Giá thép ở Đà Nẵng là bao nhiêu?"). Fails open: any error returns None so
the caller falls back to its own heuristic.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.core.llm.openrouter import OpenRouterClient

logger = logging.getLogger(__name__)

_CONDENSE_SYSTEM = (
    "Bạn viết lại câu hỏi tiếp nối của người dùng thành MỘT câu hỏi độc lập, "
    "đầy đủ ngữ cảnh, dựa vào lịch sử hội thoại — để dùng cho việc tra cứu. "
    "Chỉ bổ sung chủ đề/vật liệu/khu vực còn thiếu từ lượt trước; giữ nguyên ý "
    "định của người dùng. KHÔNG trả lời câu hỏi, KHÔNG thêm giải thích. Chỉ "
    "xuất đúng một câu hỏi đã viết lại.\n\n"
    "QUY TẮC VÙNG (khu vực) — BẮT BUỘC: mọi câu hỏi giá vật liệu trong hệ "
    "thống này CẦN có khu vực (Hà Nội / Đà Nẵng / TP.HCM) mới tra được, kể cả "
    "khi câu hỏi tiếp nối đã là một câu hoàn chỉnh, đầy đủ chủ ngữ, không có "
    "đại từ thay thế (\"nó\", \"cái đó\"...). Nếu lịch sử đã có khu vực và câu "
    "tiếp nối KHÔNG tự nêu khu vực khác, LUÔN LUÔN thêm nguyên khu vực đó vào "
    "câu viết lại — đừng bỏ qua chỉ vì câu tiếp nối nghe đã đủ ý về mặt ngữ "
    "pháp.\n\n"
    'Ví dụ 1 — Lịch sử: "Giá thép ở Hà Nội thế nào?" / Tiếp nối: "còn ở Đà Nẵng '
    'thì sao?" → "Giá thép ở Đà Nẵng là bao nhiêu?"\n'
    'Ví dụ 2 — Lịch sử: "Giá BT-01 của Nishu ở Hà Nội?" / Tiếp nối: "NISHU '
    'PRIMER có mấy loại, giá mỗi loại bao nhiêu?" → "NISHU PRIMER của Nishu ở '
    'Hà Nội có mấy loại, giá mỗi loại bao nhiêu?" (câu tiếp nối nghe đầy đủ '
    "nhưng KHÔNG tự nêu khu vực — vẫn phải thêm \"ở Hà Nội\" từ lịch sử)\n\n"
    "QUY TẮC CHỦ ĐỀ (đại từ thay thế \"nó\"/\"cái đó\"/\"sản phẩm đó\"...) — "
    "BẮT BUỘC: đại từ luôn thay cho ĐÚNG MỘT sản phẩm cụ thể — sản phẩm mà "
    "TRỢ LÝ vừa nhắc tên/trả lời ở LƯỢT NGAY TRƯỚC ĐÓ (không phải một sản "
    "phẩm khác được nhắc ở đâu đó xa hơn trong lịch sử, kể cả khi tên đó nghe "
    "\"khớp\" hơn với chủ đề). Chép lại CHÍNH XÁC nguyên văn tên sản phẩm đó "
    "từ câu trả lời gần nhất của trợ lý — không rút gọn, không đổi sang một "
    "sản phẩm khác, không tự suy diễn thêm chi tiết (mã hàng, hãng...) mà "
    "lịch sử không ghi. Nếu không chắc \"nó\" ám chỉ sản phẩm nào, GIỮ NGUYÊN "
    "đại từ trong câu viết lại thay vì đoán bừa một cái tên.\n\n"
    'Ví dụ 3 — Lịch sử: "Đèn điện chiếu sáng đường phố của công ty Phương Đông '
    'được bảo hành mấy năm?" / Trợ lý: "Đèn điện chiếu sáng đường phố của công '
    'ty Phương Đông được bảo hành 05 năm." / Tiếp nối: "Tiêu chuẩn kỹ thuật của '
    'nó là gì?" → "Tiêu chuẩn kỹ thuật của đèn điện chiếu sáng đường phố của '
    'công ty Phương Đông là gì?" (LẤY ĐÚNG sản phẩm trợ lý vừa nói, KHÔNG lấy '
    "một sản phẩm nào khác dù có vẻ liên quan)"
)


async def condense_followup(
    llm: OpenRouterClient, message: str, history: list[dict]
) -> str | None:
    """Return a standalone rewrite of `message` given recent `history`, or None
    on any failure (caller should fall back)."""
    recent = [m for m in history if m.get("role") in ("user", "assistant")][-4:]
    if not recent:
        return None
    convo = "\n".join(
        f"{'Người dùng' if m['role'] == 'user' else 'Trợ lý'}: {m['content']}"
        for m in recent
    )
    try:
        rewritten = await llm.chat(
            messages=[
                {"role": "system", "content": _CONDENSE_SYSTEM},
                {"role": "user", "content": f"Lịch sử:\n{convo}\n\nTiếp nối: {message}\n\nCâu hỏi độc lập:"},
            ],
            model=settings.openrouter_classifier_model,
            temperature=0.0,
            max_tokens=64,
        )
        rewritten = rewritten.strip().strip('"').strip()
        # Guard against a model that ignored instructions and answered instead
        # of rewriting (a paragraph, not a question) — fall back in that case.
        if rewritten and len(rewritten) <= 200:
            return rewritten
        return None
    except Exception as exc:
        logger.warning("follow-up condense failed, falling back: %s", exc)
        return None
