"""Off-topic guard — a cheap/fast classifier call that intercepts questions
unrelated to construction materials/cost estimation *before* the (usually
more expensive) main model or agent tool loop runs.

Only meaningful in the default persona (no skill_id, no active KB/project —
see app/api/v1/chat.py's call site): once a user has their own KB/project
active, "on topic" is defined by whatever THAT KB contains, not by
construction specifically, so the guard must not run there.

Fails open — a classifier error/timeout lets the message through to the
normal pipeline rather than blocking a legitimate question because of an
unrelated infra hiccup.
"""

from __future__ import annotations

import logging
import random

from app.config import settings
from app.core.llm.openrouter import OpenRouterClient

logger = logging.getLogger(__name__)

_CLASSIFIER_SYSTEM = (
    "Bạn phân loại xem tin nhắn của người dùng có khả năng liên quan tới xây "
    "dựng, vật liệu, kỹ thuật, khoa học công nghệ, hay các chủ đề mà một kỹ "
    "sư/người làm xây dựng có thể quan tâm hay không — hiểu theo nghĩa RỘNG, "
    "không chỉ giới hạn đúng nghĩa đen 'vật liệu xây dựng'. Lời chào hỏi/tạm "
    "biệt/cảm ơn không tính (đã được xử lý riêng).\n\n"
    "Chỉ trả lời NO khi chủ đề HOÀN TOÀN không liên quan và không có khả năng "
    "nào liên quan tới xây dựng/kỹ thuật/khoa học công nghệ — ví dụ: lịch sử, "
    "chính trị, giải trí, thể thao, người nổi tiếng, ẩm thực, v.v. Nếu còn "
    "mơ hồ hoặc có thể liên quan (kể cả gián tiếp), trả lời YES.\n\n"
    "Chỉ trả lời đúng một từ: YES hoặc NO."
)

REFUSAL_RESPONSES = [
    "Mình là trợ lý chuyên về vật liệu xây dựng và dự toán chi phí xây dựng, "
    "nên câu này ngoài phạm vi hỗ trợ của mình rồi. Bạn có câu hỏi nào về "
    "vật liệu hoặc chi phí xây dựng không?",
    "Câu hỏi này nằm ngoài chuyên môn của mình (vật liệu xây dựng, dự toán "
    "chi phí) nên mình không trả lời chính xác được. Mình có thể giúp gì về "
    "xây dựng không?",
]


async def is_off_topic(message: str, llm: OpenRouterClient) -> bool:
    try:
        verdict = await llm.chat(
            messages=[
                {"role": "system", "content": _CLASSIFIER_SYSTEM},
                {"role": "user", "content": message},
            ],
            model=settings.openrouter_classifier_model,
            temperature=0.0,
            max_tokens=5,
        )
        return verdict.strip().upper().startswith("NO")
    except Exception as exc:
        logger.warning("off-topic classifier failed, letting message through: %s", exc)
        return False


def refusal_reply() -> str:
    return random.choice(REFUSAL_RESPONSES)
