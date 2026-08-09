"""MCP Tool — top-level construction cost orchestrator.

Scope note (important): without a detailed design (bản vẽ, bảng thống kê
thép, chỉ dẫn kỹ thuật), the domain guide's own classification (mục 4.1
"Ước lượng ý tưởng") says only floor-area-based parametric estimation is
valid — not a detailed take-off. This tool therefore:
  1. Derives material QUANTITIES from floor_area using reference
     consumption coefficients (m3 bê tông/m2, kg thép/m2, ...) — these are
     rough parametric coefficients for low-rise residential construction,
     not a substitute for actual geometric take-off.
  2. Prices those quantities via the structured material_prices table
     (lookup_material_price's underlying repository) for the given region.
  3. Sums to a MATERIAL cost estimate only — explicitly NOT a turnkey
     "giá xây nhà" figure, since labor, equipment, contractor margin, VAT
     and indirect costs are outside this corpus's price data entirely.

Per mục 55–56 of the domain guide, results are returned as a range with
assumptions listed, not a single confident number.

Product disambiguation: `material_category` in this dataset is
inconsistently populated (sometimes a real category, sometimes a vendor
company name — e.g. "CÔNG TY CỔ PHẦN VIGLACERA TIÊN SƠN" would substring-
match a "sơn" search), so picking "the first row" by category alone can
silently price a completely wrong product. Rather than a hand-maintained
keyword blocklist (brittle — every new vendor file can introduce a new
false match no one thought to exclude), an LLM call picks the correct row
from the actual unit-filtered candidates pulled from the DB. The LLM never
invents a price — it only selects among real rows, or says none fit, which
maps to an honest "no data" line instead of a guess.
"""

from __future__ import annotations

import asyncio

from mcp.types import TextContent, Tool

from app.core.construction.project_types import (
    DEFAULT_PROJECT_TYPE,
    MATERIAL_SPECS,
    PROJECT_TYPES,
    get_project_type,
)

COST_TOOL = Tool(
    name="calculate_construction_cost",
    description=(
        "Ước lượng Ý TƯỞNG chi phí VẬT LIỆU cho một công trình từ diện tích (chưa có bản vẽ "
        "chi tiết). Hỗ trợ nhiều loại hình: nhà phố, nhà cấp 4, biệt thự, nhà xưởng thép tiền "
        "chế, nhà kho, sân bê tông/đường nội bộ, san nền, tường rào, vỉa hè lát gạch, cải tạo. "
        "Trả về khoảng giá kèm giả định — KHÔNG bao gồm nhân công, thiết bị, lợi nhuận nhà "
        "thầu, VAT, chi phí gián tiếp. Không dùng thay dự toán/hợp đồng."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "floor_area_m2": {
                "type": "number",
                "description": "Tổng diện tích sàn xây dựng (m2), đã gồm các tầng",
            },
            "region": {"type": "string", "enum": ["HN", "DN", "HCM", "KH", "AG"]},
            "project_type": {
                "type": "string",
                "enum": list(PROJECT_TYPES.keys()),
                "default": DEFAULT_PROJECT_TYPE,
                "description": (
                    "Loại hình công trình. Quyết định bộ vật liệu và hệ số tiêu hao: "
                    "nha_pho (nhà phố/nhà ở khung BTCT), nha_cap_4, biet_thu, "
                    "nha_xuong (nhà thép tiền chế), nha_kho, san_be_tong (sân/đường nội bộ), "
                    "san_nen (san lấp), tuong_rao (tính theo m2 MẶT TƯỜNG), "
                    "via_he_lat_gach, cai_tao (sửa chữa không đụng kết cấu)."
                ),
            },
            "finish_level": {
                "type": "string",
                "enum": ["tho", "hoan_thien_co_ban", "hoan_thien_cao_cap"],
                "default": "hoan_thien_co_ban",
                "description": (
                    "Chỉ có ý nghĩa với loại hình có hoàn thiện (nhà ở, tường rào, cải tạo); "
                    "bị bỏ qua với sân bê tông, san nền, nhà xưởng."
                ),
            },
        },
        "required": ["floor_area_m2", "region"],
    },
)

# Hệ số tiêu hao KHÔNG khai báo ở đây. Chúng thuộc về từng loại hình công
# trình (`PROJECT_TYPES[...].coefficients` trong project_types.py), vì một bộ
# hệ số chung không phục vụ được cả nhà phố lẫn nhà xưởng thép tiền chế.
# `_compute_cost` đọc thẳng từ đó — xem vòng lặp `for slug, per_m2 in
# project.coefficients.items()`.

_FINISH_MULTIPLIER = {"tho": 1.0, "hoan_thien_co_ban": 1.0, "hoan_thien_cao_cap": 1.15}
_FINISH_LABELS = {
    "tho": "thô",
    "hoan_thien_co_ban": "hoàn thiện cơ bản",
    "hoan_thien_cao_cap": "hoàn thiện cao cấp",
}


async def _disambiguate(llm, target_desc: str, candidates: list) -> int | None:
    """Ask the LLM to pick the candidate row matching target_desc, or None
    if it says none fit (or its answer can't be parsed) — never guess."""
    if not candidates:
        return None
    if len(candidates) == 1:
        return 0

    listing = "\n".join(
        f"{i}. {c.material_name}"
        + (f" ({c.spec})" if c.spec else "")
        + f" — đơn vị: {c.unit} — giá: {c.price_ex_vat:,.0f} đ"
        for i, c in enumerate(candidates)
    )
    prompt = (
        f"Trong danh sách vật liệu xây dựng dưới đây, hãy chọn ĐÚNG MỘT dòng khớp với mô tả sau: "
        f'"{target_desc}".\n\nDanh sách:\n{listing}\n\n'
        "Chỉ trả lời bằng số thứ tự (index) của dòng đúng nhất. Nếu KHÔNG có dòng nào thực sự phù "
        "hợp với mô tả (đừng chọn đại một dòng chỉ gần giống tên), trả lời -1. Không giải thích gì "
        "thêm, chỉ một con số duy nhất."
    )
    try:
        # settings.openrouter_research_model (chat()'s default) points at a
        # model OpenRouter no longer serves, and openrouter_chat_model is a
        # content-safety classifier, not a general chat model — both are
        # stale leftover config nothing else relies on (the main chat flow
        # always passes model= explicitly from the frontend). Use the same
        # fixed model the rest of the app hardcodes.
        resp = await llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model="openai/gpt-4o-mini",
            temperature=0.0,
            max_tokens=10,
        )
        idx = int(resp.strip().split()[0])
    except Exception:
        return None
    return idx if 0 <= idx < len(candidates) else None


# Prompt used to turn the computed estimate into a streamed, conversational
# reply (the human-in-the-loop form path in app/api/v1/chat.py), so tool
# output reads like a normal chat/search answer instead of a raw table dump.
# Numbers are authoritative and must survive verbatim — hence the hard rules.
COST_PRESENT_PROMPT = """\
Bạn là trợ lý xây dựng. Trình bày lại BẢNG DỰ TOÁN dưới đây thành một câu trả lời
gọn gàng, dễ đọc, thân thiện bằng tiếng Việt — như một tin nhắn chat.

QUY TẮC BẮT BUỘC:
- GIỮ NGUYÊN 100% mọi con số (khối lượng, đơn giá, thành tiền, khoảng tổng).
  Tuyệt đối KHÔNG đổi số, KHÔNG làm tròn khác đi, KHÔNG bịa thêm.
- Với hạng mục có giá lấy từ web (đánh dấu [n]), giữ NGUYÊN ký hiệu [n] ngay sau
  số tiền của hạng mục đó, và nói rõ đó là giá tham khảo từ web, chưa xác thực.
- Nêu rõ hạng mục không có dữ liệu giá; nếu thiếu thì giải thích vì sao không đưa tổng.
- Nhắc ngắn gọn: đây chỉ là chi phí vật liệu chính, chưa gồm nhân công/thiết bị/lợi nhuận/VAT.
- NẾU VÀ CHỈ NẾU có dòng "NGÂN SÁCH MỤC TIÊU: ... đ" xuất hiện NGUYÊN VĂN
  trong dữ liệu bên dưới: đây là câu hỏi thực sự của người dùng ("với ngân
  sách này thì xây được bao nhiêu") — trả lời thẳng vào đó trước (diện tích
  khả thi ước tính), rồi mới nêu chi phí của diện tích họ gõ ở trên để đối
  chiếu. Nếu chi phí đó vượt xa ngân sách, nói THẲNG là vượt (không giảm
  nhẹ), và không tự bịa thêm phương án nào ngoài con số diện tích đã tính
  sẵn.
- NẾU KHÔNG có dòng "NGÂN SÁCH MỤC TIÊU" đó trong dữ liệu (trường hợp phổ
  biến nhất): TUYỆT ĐỐI KHÔNG nhắc tới từ "ngân sách" hay tự đặt ra một
  ngân sách nào cả — chỉ trình bày bảng chi phí trực tiếp cho diện tích đã
  cho, đúng như một dự toán thông thường. Không suy diễn "khoảng ngân sách"
  từ diện tích/chi phí đã tính.
- Dùng markdown gọn (in đậm số tiền, gạch đầu dòng). KHÔNG dùng bảng, KHÔNG dùng emoji.

DỮ LIỆU DỰ TOÁN:
{facts}

Viết câu trả lời:
"""


def build_cost_facts(data: dict, target_budget: float | None = None) -> str:
    """Compact, number-exact fact sheet fed to COST_PRESENT_PROMPT — the LLM
    only rephrases it, so every figure here is what the user ends up seeing.

    `target_budget` (VNĐ, optional): when the user stated a budget, the cost
    formulas are linear in floor area (each material's quantity is area ×
    a fixed per-m² coefficient, priced at a fixed unit price — no bulk
    discount is modeled), so cost-per-m² = priced_subtotal / area is exact,
    not an approximation, and target_budget / cost-per-m² gives the area
    that budget actually buys. This is arithmetic on the same numbers
    already computed for the direct estimate, not a second pricing pass —
    see cost_tool.py module docstring for why area-based estimation is the
    right precision level here in the first place.
    """
    lines = [
        f"Loại hình: {data.get('project_label', 'Nhà phố / nhà ở dân dụng')}. "
        f"Quy mô: {data['area']:.0f} {data.get('area_label', 'm² sàn')}. "
        f"Vùng: {data['region']}."
        + (
            f" Mức hoàn thiện: {_FINISH_LABELS.get(data['finish_level'], data['finish_level'])}."
            if data.get("finish_applies", True)
            else ""
        ),
        "Chi phí VẬT LIỆU (chưa gồm nhân công/thiết bị/lợi nhuận/VAT/gián tiếp).",
        "",
        "Các hạng mục:",
    ]
    for li in data["line_items"]:
        if li["subtotal"] is not None:
            tag = (
                f" [{li['source_index']}] (giá từ web, chưa xác thực)" if li.get("via_web") else ""
            )
            lines.append(
                f"- {li['item']}: {li['qty']:g} {li['unit']} × {li['unit_price']:,.0f} đ "
                f"= {li['subtotal']:,.0f} đ{tag}"
            )
        else:
            lines.append(
                f"- {li['item']}: {li['qty']:g} {li['unit']} — "
                "KHÔNG có dữ liệu giá (kể cả tìm trên web)"
            )
    lines.append("")
    if data["has_full_pricing"]:
        low, high = data["priced_subtotal"] * 0.85, data["priced_subtotal"] * 1.20
        lines.append(
            f"Tổng ước lượng chi phí vật liệu chính: {low:,.0f} – {high:,.0f} đ "
            "(sai số ±15%/+20% ở cấp độ ý tưởng)."
        )
    else:
        lines.append(
            f"KHÔNG đưa ra tổng vì thiếu giá của: {', '.join(data['missing'])} "
            "(là hạng mục lớn — không đưa một số duy nhất khi thiếu dữ liệu)."
        )
    if data["web_sources"]:
        lines.append("")
        lines.append("Nguồn web (khớp với số [n] ở trên):")
        for s in data["web_sources"]:
            lines.append(f"[{s['index']}] {s['title']} — {s['url']}")

    if target_budget and target_budget > 0:
        lines.append("")
        lines.append(f"NGÂN SÁCH MỤC TIÊU: {target_budget:,.0f} đ.")
        if data["has_full_pricing"] and data["area"] > 0:
            cost_per_m2 = data["priced_subtotal"] / data["area"]
            suggested_area = target_budget / cost_per_m2
            lines.append(
                f"Đơn giá vật liệu chính ước tính: {cost_per_m2:,.0f} đ/m² sàn "
                f"(ở mức hoàn thiện đã chọn)."
            )
            lines.append(
                f"→ Với ngân sách này, diện tích sàn khả thi ước tính khoảng "
                f"{suggested_area:.0f} m² (cùng vùng/mức hoàn thiện, chỉ tính vật liệu "
                f"4 hạng mục chính — không gồm nhân công/thiết bị/lợi nhuận/VAT)."
            )
        else:
            lines.append(
                "KHÔNG tính được diện tích khả thi từ ngân sách vì thiếu dữ liệu giá "
                f"cho: {', '.join(data['missing'])} — nêu rõ điều này thay vì đoán."
            )
    return "\n".join(lines)


async def _compute_cost(args: dict) -> dict:
    """Do the estimation and return structured data (or {'error': msg}).
    Shared by the MCP/agent text path (_format_cost_text) and the streamed
    human-in-the-loop form path (build_cost_facts)."""
    from app.core.llm.openrouter import OpenRouterClient
    from app.core.mcp.tools.web_price_fallback import search_web_price
    from app.db.postgres.repositories.material_price_repo import MaterialPriceRepository

    area = args["floor_area_m2"]
    region = args["region"]
    finish_level = args.get("finish_level", "hoan_thien_co_ban")
    # OFF in production (§10). The web fallback is an exploratory-estimate
    # feature, not a price source: when the vetted DB has no row, the honest
    # output is "no data for this line item", and the caller decides whether an
    # unverified web number is acceptable for their purpose. The code path is
    # kept intact and merely gated — see search_web_price's own docstring for
    # why a web price is never blended with published prices.
    allow_web_fallback = bool(args.get("allow_web_fallback", False))
    if area <= 0:
        return {"error": "floor_area_m2 phải > 0"}

    project = get_project_type(args.get("project_type"))
    # The finish multiplier only touches finishing materials, and only for the
    # types that actually have a finish stage — scaling a concrete yard's
    # aggregate by "hoàn thiện cao cấp" would be meaningless.
    finish_mult = _FINISH_MULTIPLIER.get(finish_level, 1.0) if project.finish_applies else 1.0
    _FINISHING_SLUGS = {"son", "gach_lat"}

    demands: list[tuple[str, float]] = []
    for slug, per_m2 in project.coefficients.items():
        qty = area * per_m2
        if slug in _FINISHING_SLUGS:
            qty *= finish_mult
        if qty > 0:
            demands.append((slug, qty))

    repo = MaterialPriceRepository()
    llm = OpenRouterClient()
    line_items: list[dict] = []
    missing: list[str] = []
    web_sources: list[dict] = []  # [{index, title, url}] — cited as [n] in the output text

    async def price_line(
        slug: str,
        label: str,
        name_query: str,
        qty: float,
        unit: str,
        target_desc: str,
        exclude_keywords: list[str] | None = None,
    ) -> dict:
        """Pure — returns a line dict, no shared-state mutation, so the four
        calls can run concurrently (see asyncio.gather below). web_sources
        indices/citation numbers are assigned afterwards in fixed order.

        `exclude_keywords` filters at the SQL level, before `limit` caps the
        candidate list — without this, a generic name_query like "thép" (75+
        rows in HN) can have every one of the top-15-by-recency slots taken
        by exactly the variants target_desc says to exclude (ống thép, thép
        mạ kẽm...), pushing the actually-correct rebar/coil rows out of the
        window the LLM disambiguator ever sees. Relying on the disambiguator
        alone to filter post-hoc doesn't help once the right row never made
        the cut."""
        spec = MATERIAL_SPECS[slug]

        # Try the material's own unit first, then any unit it is also
        # published in (tấn for kg-priced materials), converting the price so
        # every candidate is comparable in `unit`.
        candidates: list = []
        factors: list[float] = []
        for db_unit, factor in [(unit, 1.0), *spec.alt_units]:
            found = await repo.lookup(
                region=region,
                material_name=name_query,
                unit=db_unit,
                exclude_name_keywords=exclude_keywords,
                limit=15,
            )
            for c in found:
                converted = float(c.price_ex_vat) * factor
                # Bounds catch decimal/unit catastrophes from either source —
                # see MaterialSpec.price_min for the 1,8 tỷ đ/kg incident.
                if spec.price_min <= converted <= spec.price_max:
                    candidates.append(c)
                    factors.append(factor)
            if candidates:
                break

        idx = await _disambiguate(llm, target_desc, candidates)
        if idx is not None:
            unit_price = float(candidates[idx].price_ex_vat) * factors[idx]
            return {
                "item": label,
                "qty": round(qty, 2),
                "unit": unit,
                "unit_price": unit_price,
                "subtotal": round(qty * unit_price, 0),
                "via_web": False,
                # The price came straight from a document in the KB — carry
                # its source doc so the answer can cite it as RAG (this is
                # document-backed data, not a guess or a web hit).
                "_document_id": str(candidates[idx].document_id),
            }

        # Not in the vetted price DB for this region. In production this is
        # where the line item is reported as missing and the total is withheld
        # (fail-closed, §10) — the web search only runs when the caller has
        # explicitly opted in, and even then the figure is cited as unverified.
        if not allow_web_fallback:
            return {
                "item": label,
                "qty": qty,
                "unit": unit,
                "unit_price": None,
                "subtotal": None,
                "via_web": False,
                "_missing": True,
            }
        web_price, url, title = await search_web_price(target_desc, region)
        if web_price is not None and not (spec.price_min <= web_price <= spec.price_max):
            # A scraped number outside the plausible band is a unit mix-up,
            # not a bargain. Report "no data" rather than publish it.
            web_price = None
        if web_price is None:
            return {
                "item": label,
                "qty": qty,
                "unit": unit,
                "unit_price": None,
                "subtotal": None,
                "via_web": False,
                "_missing": True,
            }

        return {
            "item": label,
            "qty": round(qty, 2),
            "unit": unit,
            "unit_price": web_price,
            "subtotal": round(qty * web_price, 0),
            "via_web": True,
            "_url": url,
            "_title": title,
        }

    # Run every material lookup concurrently — each is an independent DB
    # query + LLM disambiguation (+ possibly a web-price search), and
    # serially they stacked up (a region missing 2-3 prices meant 2-3 web
    # searches back-to-back, ~15s+ each). gather overlaps them. The set of
    # materials now comes from the project profile, so a factory shed prices
    # structural steel and roof sheeting while a concrete yard prices neither.
    results = await asyncio.gather(
        *(
            price_line(
                slug,
                MATERIAL_SPECS[slug].label,
                MATERIAL_SPECS[slug].name_query,
                qty,
                MATERIAL_SPECS[slug].unit,
                MATERIAL_SPECS[slug].target_desc,
                exclude_keywords=MATERIAL_SPECS[slug].exclude_keywords or None,
            )
            for slug, qty in demands
        )
    )

    # Assemble in the fixed material order so citation numbers are stable.
    doc_ids: list[str] = []
    for r in results:
        if r.pop("_missing", False):
            missing.append(r["item"])
        if r.get("via_web"):
            web_sources.append(
                {"index": len(web_sources) + 1, "title": r.pop("_title"), "url": r.pop("_url")}
            )
            r["source_index"] = len(web_sources)
        did = r.pop("_document_id", None)
        if did:
            doc_ids.append(did)
        line_items.append(r)

    # Source documents behind the DB-priced lines → RAG citation chips + the
    # KB name for the "RAG · <kb>" badge (only present when DB prices were
    # actually used; an all-web estimate has none and stays web-cited).
    rag_sources, rag_kb_name = await _fetch_source_docs(doc_ids)

    priced_subtotal = sum(li["subtotal"] for li in line_items if li["subtotal"] is not None)
    has_full_pricing = not missing

    return {
        "error": None,
        "area": area,
        "region": region,
        "finish_level": finish_level,
        "project_type": project.key,
        "project_label": project.label,
        "area_label": project.area_label,
        "project_note": project.note,
        "finish_applies": project.finish_applies,
        "coef": dict(project.coefficients),
        "line_items": line_items,
        "missing": missing,
        "web_sources": web_sources,
        "rag_sources": rag_sources,
        "rag_kb_name": rag_kb_name,
        "priced_subtotal": priced_subtotal,
        "has_full_pricing": has_full_pricing,
    }


async def _fetch_source_docs(document_ids: list[str]) -> tuple[list[dict], str | None]:
    """Map DB-priced lines' source documents to citation chips
    ({chunk_id, document_name, score}) plus the KB they belong to (for the
    RAG badge). Deduped by filename. score is 1.0 — these are exact
    structured rows lifted straight from the document, not fuzzy retrieval
    matches, so full confidence in the source is honest."""
    if not document_ids:
        return [], None

    import uuid as _uuid

    from sqlalchemy import select

    from app.db.postgres.base import get_session
    from app.db.postgres.models import Document, KnowledgeBase

    uniq = list({d for d in document_ids})
    async with get_session() as s:
        rows = (
            await s.execute(
                select(Document.id, Document.filename, KnowledgeBase.name)
                .join(KnowledgeBase, Document.kb_id == KnowledgeBase.id)
                .where(Document.id.in_([_uuid.UUID(d) for d in uniq]))
            )
        ).all()

    seen: set[str] = set()
    sources: list[dict] = []
    kb_name: str | None = None
    for doc_id, filename, kbname in rows:
        kb_name = kb_name or kbname
        if filename not in seen:
            seen.add(filename)
            # `document_id` is additive — the caller needs it to build a
            # normalized AnswerSource (region comes from the priced rows, not
            # from this filename). The three legacy keys stay for old clients.
            sources.append(
                {
                    "chunk_id": filename,
                    "document_name": filename,
                    "score": 1.0,
                    "document_id": str(doc_id),
                }
            )
    return sources, kb_name


def _format_cost_text(data: dict) -> str:
    """Rich markdown table version — used by the MCP/agent tool-loop path,
    where the tool result is fed back to an LLM anyway. The human-in-the-loop
    form path uses build_cost_facts + COST_PRESENT_PROMPT to stream prose."""
    area, region, finish_level = data["area"], data["region"], data["finish_level"]
    line_items, missing, web_sources = data["line_items"], data["missing"], data["web_sources"]
    coef = data["coef"]
    area_label = data.get("area_label", "m² sàn")

    finish_txt = (
        f" · mức hoàn thiện **{_FINISH_LABELS.get(finish_level, finish_level)}**"
        if data.get("finish_applies", True)
        else ""
    )
    lines = [
        "### Ước lượng ý tưởng chi phí vật liệu",
        f"**{data.get('project_label', 'Nhà phố / nhà ở dân dụng')}** — "
        f"**{area:.0f} {area_label}** · vùng **{region}**{finish_txt}",
        "",
        "*(Chưa gồm nhân công, thiết bị, lợi nhuận nhà thầu, VAT, chi phí gián tiếp.)*",
        "",
        "| Hạng mục | Khối lượng | Đơn giá | Thành tiền |",
        "|---|---:|---:|---:|",
    ]
    for li in line_items:
        if li["subtotal"] is not None:
            tag = f" `[${li['source_index']}]`" if li.get("via_web") else ""
            unit_price_cell = f"{li['unit_price']:,.0f} đ{tag}"
            if li.get("via_web"):
                unit_price_cell += " ⚠️"
            lines.append(
                f"| {li['item']} | {li['qty']:g} {li['unit']} | {unit_price_cell} "
                f"| **{li['subtotal']:,.0f} đ** |"
            )
        else:
            lines.append(f"| {li['item']} | {li['qty']:g} {li['unit']} | _không có dữ liệu_ | — |")

    lines.append("")

    if data["has_full_pricing"]:
        priced_subtotal = data["priced_subtotal"]
        low, high = priced_subtotal * 0.85, priced_subtotal * 1.20
        lines.append(f"### Tổng chi phí vật liệu chính: **{low:,.0f} – {high:,.0f} đ**")
        lines.append("")
        lines.append(
            "*Khoảng ±15%/+20% phản ánh sai số ở cấp độ ý tưởng (mục 4.1), "
            "không phải dải dung sai định mức.*"
        )
        if web_sources:
            lines.append("")
            lines.append(
                f"> ⚠️ {len(web_sources)} hạng mục dùng giá tham khảo từ web "
                "(đánh dấu `[$n]` ở bảng trên, nguồn ở cuối) — độ tin cậy thấp hơn "
                "dữ liệu công bố chính thức, nên kiểm tra lại trước khi dùng cho quyết định thật."
            )
    else:
        lines.append(
            f"> **Không đủ dữ liệu giá cho:** {', '.join(missing)} — "
            "không đưa ra tổng để tránh thiếu "
            "sót một hạng mục lớn (mục 56: không đưa một số duy nhất khi thiếu dữ liệu)."
        )

    lines.append("")
    lines.append(
        f"<details><summary>Giả định đã dùng (hệ số tiêu hao tham khảo / {area_label})</summary>"
    )
    lines.append("")
    for key, value in coef.items():
        spec = MATERIAL_SPECS.get(key)
        label = spec.label if spec else key
        unit = spec.unit if spec else ""
        lines.append(f"- {label}: {value:g} {unit}/{area_label}")
    if data.get("project_note"):
        lines.append("")
        lines.append(f"- *{data['project_note']}*")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    lines.append(
        f"*Đây chỉ là chi phí vật liệu chính của {len(coef)} hạng mục, không phải giá xây "
        "trọn gói, và không thay thế dự toán từ hồ sơ thiết kế đã duyệt, "
        "định mức hiện hành hoặc báo giá hợp lệ.*"
    )

    if web_sources:
        lines.append("")
        lines.append("**Nguồn giá tham khảo từ web:**")
        for s in web_sources:
            lines.append(f"- `[${s['index']}]` [{s['title']}]({s['url']})")

    return "\n".join(lines)


async def handle_calculate_construction_cost(args: dict) -> list[TextContent]:
    """MCP/agent entry point — returns the rich markdown text. The chat form
    path calls _compute_cost + build_cost_facts directly to stream instead."""
    data = await _compute_cost(args)
    if data.get("error"):
        return [TextContent(type="text", text=data["error"])]
    return [TextContent(type="text", text=_format_cost_text(data))]
