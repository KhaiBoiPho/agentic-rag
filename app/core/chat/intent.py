"""Fixed-pipeline intent detection for the chat endpoint.

When a user message matches a known intent (currently just construction
cost estimation), the chat endpoint skips the LLM entirely and asks the
frontend to render a structured form instead of letting the model guess or
ask clarifying questions in free text — see docs/construction-pricing-pipeline.md.

Adding a new intent/form: add an entry to FORM_SCHEMAS, add matching
keywords to _INTENT_KEYWORDS, write the tool it submits to. No changes to
app/api/v1/chat.py are needed beyond that.
"""

from __future__ import annotations

import random
import re

FORM_SCHEMAS: dict[str, dict] = {
    "construction_cost": {
        "form_id": "construction_cost",
        "title": "Thông tin để tính chi phí xây dựng",
        "fields": [
            {
                "name": "area_per_floor_m2",
                "label": "Diện tích 1 tầng (m2)",
                "type": "number",
                "required": True,
            },
            {
                "name": "num_floors",
                "label": "Số tầng",
                "type": "number",
                "required": True,
                "default": 1,
            },
            {
                "name": "region",
                "label": "Khu vực",
                "type": "select",
                "required": True,
                "options": [
                    {"value": "HN", "label": "Hà Nội"},
                    {"value": "DN", "label": "Đà Nẵng"},
                    {"value": "HCM", "label": "TPHCM"},
                ],
            },
            {
                "name": "finish_level",
                "label": "Mức hoàn thiện",
                "type": "select",
                "default": "hoan_thien_co_ban",
                "options": [
                    {"value": "tho", "label": "Thô"},
                    {"value": "hoan_thien_co_ban", "label": "Hoàn thiện cơ bản"},
                    {"value": "hoan_thien_cao_cap", "label": "Hoàn thiện cao cấp"},
                ],
            },
        ],
    },
}

# Combinatorial match instead of fixed phrases: real questions vary word
# order a lot ("giá nhà 100m2 ở Hà Nội xây dựng hết bao nhiêu tiền?" has
# none of the old exact phrases like "giá xây nhà"). Require one keyword
# from EACH group anywhere in the message — cheap and much harder to miss
# than literal substrings, while still needing both "this is about a house"
# and "this is about cost" to avoid false positives (e.g. "xây nhà" alone,
# with no cost word, stays plain chat).
_INTENT_WORD_GROUPS: dict[str, list[list[str]]] = {
    "construction_cost": [
        ["nhà"],
        ["xây", "xây dựng", "thi công", "làm nhà"],
        ["giá", "chi phí", "bao nhiêu tiền", "tốn bao nhiêu", "hết bao nhiêu", "dự toán"],
    ],
}

# ─── Small talk — skip the LLM entirely to save API cost/latency ──────────
#
# Deliberately EXACT-match only (whole normalized message must equal one of
# these phrases), unlike the loose substring matching above — a substring
# match on "chào" would also fire on "chào bạn, giá thép hôm nay bao nhiêu"
# and silently eat a real question behind a canned greeting. The length cap
# in detect_small_talk() is a second guard against that.
_SMALL_TALK: dict[str, tuple[set[str], list[str]]] = {
    "greeting": (
        {
            "chào",
            "chào bạn",
            "chào shop",
            "xin chào",
            "alo",
            "hi",
            "hello",
            "hey",
            "helo",
            "hí",
        },
        [
            "Chào bạn! Mình có thể giúp gì về vật liệu xây dựng hay dự toán chi phí hôm nay?",
            "Xin chào! Bạn cần hỏi gì về vật liệu xây dựng hoặc dự toán chi phí không?",
        ],
    ),
    "farewell": (
        {
            "tạm biệt",
            "chào tạm biệt",
            "bye",
            "bye bye",
            "goodbye",
            "hẹn gặp lại",
            "byebye",
        },
        [
            "Tạm biệt bạn! Cần gì cứ quay lại hỏi mình nhé.",
            "Chào tạm biệt! Chúc bạn một ngày tốt lành.",
        ],
    ),
    "thanks": (
        {
            "cảm ơn",
            "cám ơn",
            "cảm ơn bạn",
            "cám ơn bạn",
            "cảm ơn nhé",
            "thanks",
            "thank you",
            "thank",
            "ok cảm ơn",
            "oke cảm ơn",
        },
        [
            "Không có gì! Rất vui được giúp bạn.",
            "Dạ không có gì, cần gì cứ hỏi mình tiếp nhé!",
        ],
    ),
    # Categories below follow the standard chitchat set from Rasa's demo
    # bot (ask_howdoing / ask_whoisit / ask_isbot / ask_whatspossible) —
    # https://github.com/RasaHQ/rasa/issues/4266 — adapted to this app's
    # domain. affirm/deny ("ok", "không") and compliments/insults are
    # deliberately NOT included: those are usually answers to whatever the
    # assistant asked in the previous turn, so a canned reply would cut
    # across real conversation flow instead of being safe standalone chat.
    "how_are_you": (
        {
            "bạn khỏe không",
            "bạn khoẻ không",
            "khỏe không",
            "khoẻ không",
            "bạn có khỏe không",
            "dạo này sao rồi",
            "how are you",
            "how are you doing",
        },
        [
            "Mình khỏe, cảm ơn bạn đã hỏi thăm! Bạn cần hỏi gì về vật liệu xây dựng không?",
            "Mình ổn, cảm ơn bạn! Có gì về xây dựng cần mình giúp không nè.",
        ],
    ),
    "bot_identity": (
        {
            "bạn là ai",
            "bạn là ai vậy",
            "bạn là ai thế",
            "bạn tên gì",
            "bạn tên là gì",
            "who are you",
            "what is your name",
            "bạn là người hay máy",
            "bạn là bot à",
            "bạn là ai à",
        },
        [
            "Mình là trợ lý AI chuyên về vật liệu xây dựng và dự toán chi phí "
            "xây dựng tại Việt Nam.",
            "Mình là AI hỗ trợ tra cứu vật liệu xây dựng và tính chi phí xây nhà.",
        ],
    ),
    "bot_capability": (
        {
            "bạn làm được gì",
            "bạn giúp được gì",
            "bạn có thể làm gì",
            "bạn hỗ trợ gì",
            "bạn có thể giúp gì",
            "what can you do",
        },
        [
            "Mình có thể tra cứu giá vật liệu xây dựng, giải đáp kiến thức xây dựng, và "
            "tính dự toán chi phí xây nhà theo khu vực. Bạn cứ hỏi thử nhé!",
            "Mình hỗ trợ tra giá vật liệu, kiến thức xây dựng, và dự toán chi phí xây nhà. "
            "Bạn cần hỗ trợ gì?",
        ],
    ),
    "apology": (
        {
            "xin lỗi",
            "sorry",
            "xin lỗi bạn",
            "xin lỗi nhé",
        },
        [
            "Không sao đâu bạn! Có gì mình giúp được không?",
            "Không sao cả, đừng ngại nhé. Bạn cần hỏi gì cứ hỏi mình.",
        ],
    ),
}

_SMALL_TALK_PUNCT_RE = re.compile(r"[!?.,;:~…]+")
_SMALL_TALK_MAX_LEN = 40  # chars — anything longer is never pure small talk


def detect_small_talk(message: str) -> str | None:
    """Returns a canned reply for pure greetings/farewells/thanks, or None
    if the message should go through the normal (LLM-backed) pipeline."""
    normalized = _SMALL_TALK_PUNCT_RE.sub("", message.strip().lower()).strip()
    if not normalized or len(normalized) > _SMALL_TALK_MAX_LEN:
        return None
    for phrases, responses in _SMALL_TALK.values():
        if normalized in phrases:
            return random.choice(responses)
    return None


_AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*m\s*2", re.IGNORECASE)

_REGION_KEYWORDS: list[tuple[str, list[str]]] = [
    ("HN", ["hà nội", "ha noi", " hn "]),
    ("DN", ["đà nẵng", "da nang", " dn "]),
    ("HCM", ["tphcm", "tp hcm", "hồ chí minh", "ho chi minh", "sài gòn", "sai gon", " hcm "]),
]


def detect_intent(message: str) -> str | None:
    text = f" {message.lower()} "
    for intent, groups in _INTENT_WORD_GROUPS.items():
        if all(any(kw in text for kw in group) for group in groups):
            return intent
    return None


def prefill_from_text(message: str) -> dict:
    """Best-effort extraction of area/region already present in the user's
    message, so the form isn't blank when they've already told us. Purely
    cosmetic — the form always requires explicit confirmation/submission."""
    prefill: dict = {}
    text = f" {message.lower()} "

    area_match = _AREA_RE.search(text)
    if area_match:
        prefill["area_per_floor_m2"] = float(area_match.group(1).replace(",", "."))

    for region, keywords in _REGION_KEYWORDS:
        if any(kw in text for kw in keywords):
            prefill["region"] = region
            break

    return prefill
