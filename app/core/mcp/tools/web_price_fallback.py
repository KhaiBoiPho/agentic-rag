"""Web search fallback for a material price missing from `material_prices`.

Used only by calculate_construction_cost (cost_tool.py) when the local,
vetted price DB has no matching row for a category/region — NOT a
replacement for that DB, which stays authoritative (per the domain guide's
source hierarchy: official công bố giá / vendor quote > informal web
sources). A price found this way is always labeled as an unverified web
source with a clickable citation, never presented as equal-confidence to a
DB-backed price — see cost_tool.py's price_line().

Requires a real FIRECRAWL_API_KEY (app/config.py) — with the placeholder
value shipped in .env.example this silently returns no result (Firecrawl
401s), same failure mode as the existing /api/v1/search endpoint.
"""

from __future__ import annotations

import logging
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_REGION_LABELS = {"HN": "Hà Nội", "DN": "Đà Nẵng", "HCM": "TP. Hồ Chí Minh"}


async def search_web_price(
    material_desc: str,
    region: str,
) -> tuple[float | None, str | None, str | None]:
    """Returns (price_vnd, source_url, source_title), or (None, None, None)
    if nothing usable was found (missing/invalid API key, no results, or
    the LLM couldn't confidently extract a number)."""
    region_label = _REGION_LABELS.get(region, region)
    query = f"giá {material_desc} xây dựng {region_label} 2026 đồng/m3 đồng/kg đồng/viên"

    try:
        # No scrapeOptions — a plain search returns each hit's snippet
        # (description) in ~2s, versus ~15s+ to also scrape every page's
        # full markdown. Construction-price listings put the number right in
        # the title/description, so the snippet is enough to extract from;
        # this alone took the tool from tens of seconds down to a few.
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.post(
                f"{settings.firecrawl_base_url}/v1/search",
                headers={"Authorization": f"Bearer {settings.firecrawl_api_key}"},
                json={"query": query, "limit": 3},
            )
        if resp.status_code != 200:
            logger.warning(
                "web price fallback: Firecrawl returned %s for %r", resp.status_code, query
            )
            return None, None, None
        results = resp.json().get("data", [])
    except Exception as exc:
        logger.warning("web price fallback: search request failed: %s", exc)
        return None, None, None

    if not results:
        return None, None, None

    top = results[0]
    url = top.get("url", "")
    title = top.get("title", url)
    # Combine the top few hits' title+description so a price shows up even if
    # the very first snippet omits it (no scraped body to fall back on now).
    content = "\n".join(f"{r.get('title', '')} — {r.get('description', '')}" for r in results[:3])[
        :3000
    ].strip()
    if not content:
        return None, None, None

    from app.core.llm.openrouter import OpenRouterClient

    prompt = (
        f'Trích xuất đơn giá (VNĐ) cho "{material_desc}" tại {region_label} '
        "từ đoạn văn bản web dưới đây.\n\n"
        f"{content}\n\n"
        "Chỉ trả lời bằng SỐ NGUYÊN (đơn vị đồng, không dấu phẩy/chấm phân cách, "
        "không kèm chữ), hoặc trả lời KHONG_TIM_THAY nếu đoạn văn bản "
        "không có giá rõ ràng cho đúng vật liệu này."
    )
    try:
        resp_text = await OpenRouterClient().chat(
            messages=[{"role": "user", "content": prompt}],
            model="openai/gpt-4o-mini",
            temperature=0.0,
            max_tokens=20,
        )
        digits = re.sub(r"[^\d]", "", resp_text.strip())
        price = float(digits) if digits and "KHONG_TIM_THAY" not in resp_text else None
    except Exception as exc:
        logger.warning("web price fallback: extraction failed: %s", exc)
        price = None

    if price is None or price <= 0:
        return None, None, None
    return price, url, title
