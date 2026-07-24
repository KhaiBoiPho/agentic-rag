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

import re

FORM_SCHEMAS: dict[str, dict] = {
    "construction_cost": {
        "form_id": "construction_cost",
        "title": "Thông tin để tính chi phí xây dựng",
        "fields": [
            {"name": "area_per_floor_m2", "label": "Diện tích 1 tầng (m2)", "type": "number", "required": True},
            {"name": "num_floors", "label": "Số tầng", "type": "number", "required": True, "default": 1},
            {
                "name": "region", "label": "Khu vực", "type": "select", "required": True,
                "options": [
                    {"value": "HN", "label": "Hà Nội"},
                    {"value": "DN", "label": "Đà Nẵng"},
                    {"value": "HCM", "label": "TPHCM"},
                ],
            },
            {
                "name": "finish_level", "label": "Mức hoàn thiện", "type": "select",
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
