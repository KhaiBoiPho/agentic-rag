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

COST_TOOL = Tool(
    name="calculate_construction_cost",
    description=(
        "Ước lượng Ý TƯỞNG chi phí VẬT LIỆU thô cho một công trình dân dụng từ diện tích sàn "
        "(chưa có bản vẽ chi tiết). Trả về khoảng giá kèm giả định — KHÔNG bao gồm nhân công, "
        "thiết bị, lợi nhuận nhà thầu, VAT, chi phí gián tiếp. Không dùng thay dự toán/hợp đồng."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "floor_area_m2": {
                "type": "number",
                "description": "Tổng diện tích sàn xây dựng (m2), đã gồm các tầng",
            },
            "region": {"type": "string", "enum": ["HN", "DN", "HCM"]},
            "finish_level": {
                "type": "string",
                "enum": ["tho", "hoan_thien_co_ban", "hoan_thien_cao_cap"],
                "default": "hoan_thien_co_ban",
            },
        },
        "required": ["floor_area_m2", "region"],
    },
)

# Hệ số tiêu hao tham khảo trên 1 m2 sàn xây dựng — nhà thấp tầng, kết cấu
# BTCT thông thường. Đây là con số THAM KHẢO cho cấp độ "ý tưởng" (mục 4.1),
# không thay cho bóc tách theo bộ phận khi đã có mặt bằng/mặt cắt.
_PER_M2_COEFFICIENTS = {
    "be_tong_m3_per_m2": 0.35,
    "thep_kg_per_m2": 25.0,
    "tuong_m2_per_m2_san": 1.0,  # diện tích tường xây ước theo diện tích sàn
    "son_m2_per_m2_san": 2.2,
}
_COEFFICIENT_LABELS = {
    "be_tong_m3_per_m2": "Bê tông thương phẩm",
    "thep_kg_per_m2": "Thép xây dựng",
    "tuong_m2_per_m2_san": "Tường xây",
    "son_m2_per_m2_san": "Sơn (trước hệ số hoàn thiện)",
}
_COEFFICIENT_UNITS = {
    "be_tong_m3_per_m2": "m3/m2 sàn",
    "thep_kg_per_m2": "kg/m2 sàn",
    "tuong_m2_per_m2_san": "m2 tường/m2 sàn",
    "son_m2_per_m2_san": "m2/m2 sàn",
}

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
- Dùng markdown gọn (in đậm số tiền, gạch đầu dòng). KHÔNG dùng bảng, KHÔNG dùng emoji.

DỮ LIỆU DỰ TOÁN:
{facts}

Viết câu trả lời:
"""


def build_cost_facts(data: dict) -> str:
    """Compact, number-exact fact sheet fed to COST_PRESENT_PROMPT — the LLM
    only rephrases it, so every figure here is what the user ends up seeing."""
    lines = [
        f"Diện tích: {data['area']:.0f} m² sàn. Vùng: {data['region']}. "
        f"Mức hoàn thiện: {_FINISH_LABELS.get(data['finish_level'], data['finish_level'])}.",
        "Chi phí VẬT LIỆU thô (chưa gồm nhân công/thiết bị/lợi nhuận/VAT/gián tiếp).",
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
    return "\n".join(lines)


async def _compute_cost(args: dict) -> dict:
    """Do the estimation and return structured data (or {'error': msg}).
    Shared by the MCP/agent text path (_format_cost_text) and the streamed
    human-in-the-loop form path (build_cost_facts)."""
    from app.core.construction import formulas
    from app.core.llm.openrouter import OpenRouterClient
    from app.core.mcp.tools.web_price_fallback import search_web_price
    from app.db.postgres.repositories.material_price_repo import MaterialPriceRepository

    area = args["floor_area_m2"]
    region = args["region"]
    finish_level = args.get("finish_level", "hoan_thien_co_ban")
    if area <= 0:
        return {"error": "floor_area_m2 phải > 0"}

    coef = _PER_M2_COEFFICIENTS
    concrete_vol = area * coef["be_tong_m3_per_m2"]
    steel_kg = area * coef["thep_kg_per_m2"]
    wall_area = area * coef["tuong_m2_per_m2_san"]
    paint_area = area * coef["son_m2_per_m2_san"] * _FINISH_MULTIPLIER.get(finish_level, 1.0)

    concrete_q = formulas.concrete(concrete_vol, ready_mix=True)
    steel_q = formulas.rebar_from_geometry(
        diameter_mm=16, total_length_m=steel_kg / formulas.rebar_unit_weight_kg_per_m(16)
    )
    wall_q = formulas.masonry_wall(length_m=wall_area / 3.0, height_m=3.0, thickness_m=0.1)
    paint_q = formulas.paint(paint_area)

    repo = MaterialPriceRepository()
    llm = OpenRouterClient()
    line_items: list[dict] = []
    missing: list[str] = []
    web_sources: list[dict] = []  # [{index, title, url}] — cited as [n] in the output text

    async def price_line(
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
        candidates = await repo.lookup(
            region=region,
            material_name=name_query,
            unit=unit,
            exclude_name_keywords=exclude_keywords,
            limit=15,
        )
        idx = await _disambiguate(llm, target_desc, candidates)
        if idx is not None:
            unit_price = float(candidates[idx].price_ex_vat)
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

        # Not in the vetted price DB for this region — fall back to a web
        # search rather than immediately reporting "missing". Always cited
        # with a clickable [n] source and flagged as unverified in the
        # output text; never silently blended with DB-backed confidence.
        web_price, url, title = await search_web_price(target_desc, region)
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

    # Run all four material lookups concurrently — each is an independent
    # DB query + LLM disambiguation (+ possibly a web-price search), and
    # serially they stacked up (a region missing 2-3 prices meant 2-3 web
    # searches back-to-back, ~15s+ each). gather overlaps them.
    results = await asyncio.gather(
        price_line(
            "bê tông thương phẩm",
            "bê tông",
            concrete_q.quantities["be_tong_thuong_pham"],
            "m3",
            "bê tông thương phẩm/bê tông tươi trộn sẵn dùng đổ móng, cột, dầm, sàn nhà dân dụng — "
            "KHÔNG phải bê tông đúc sẵn dạng tấm/panel/cấu kiện/cống/kè, "
            "KHÔNG phải cát dùng để trộn bê tông",
        ),
        price_line(
            "thép xây dựng",
            "thép",
            sum(steel_q.quantities.values()),
            "kg",
            "thép thanh/thép cây/thép cuộn dùng làm cốt thép bê tông (thép xây dựng) — "
            "KHÔNG phải ống thép, tôn thép, thép mạ kẽm, khung móng thép đúc sẵn",
            exclude_keywords=["ống thép", "mạ kẽm", "tôn thép", "thép mạ", "dày mạ"],
        ),
        price_line(
            "gạch xây",
            "gạch",
            wall_q.quantities["so_vien_gach"],
            "viên",
            "gạch xây tường (gạch đặc, gạch rỗng, gạch block bê tông) dùng xây tường nhà — "
            "KHÔNG phải gạch ốp lát/gạch trang trí bề mặt",
        ),
        price_line(
            "sơn",
            "sơn",
            paint_q.quantities["son"],
            "lít",
            "sơn nước/sơn phủ tường dùng sơn hoàn thiện công trình dân dụng — "
            "KHÔNG phải sơn giao thông/sơn kẻ vạch đường",
        ),
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
        "coef": coef,
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
                select(Document.filename, KnowledgeBase.name)
                .join(KnowledgeBase, Document.kb_id == KnowledgeBase.id)
                .where(Document.id.in_([_uuid.UUID(d) for d in uniq]))
            )
        ).all()

    seen: set[str] = set()
    sources: list[dict] = []
    kb_name: str | None = None
    for filename, kbname in rows:
        kb_name = kb_name or kbname
        if filename not in seen:
            seen.add(filename)
            sources.append({"chunk_id": filename, "document_name": filename, "score": 1.0})
    return sources, kb_name


def _format_cost_text(data: dict) -> str:
    """Rich markdown table version — used by the MCP/agent tool-loop path,
    where the tool result is fed back to an LLM anyway. The human-in-the-loop
    form path uses build_cost_facts + COST_PRESENT_PROMPT to stream prose."""
    area, region, finish_level = data["area"], data["region"], data["finish_level"]
    line_items, missing, web_sources = data["line_items"], data["missing"], data["web_sources"]
    coef = data["coef"]

    lines = [
        "### Ước lượng ý tưởng chi phí vật liệu thô",
        f"**{area:.0f} m² sàn** · vùng **{region}** · "
        f"mức hoàn thiện **{_FINISH_LABELS.get(finish_level, finish_level)}**",
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
    lines.append("<details><summary>Giả định đã dùng (hệ số tiêu hao tham khảo / m² sàn)</summary>")
    lines.append("")
    for key, value in coef.items():
        lines.append(f"- {_COEFFICIENT_LABELS[key]}: {value:g} {_COEFFICIENT_UNITS[key]}")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    lines.append(
        "*Đây chỉ là chi phí vật liệu của 4 hạng mục chính, không phải giá xây nhà trọn gói, "
        "và không thay thế dự toán từ hồ sơ thiết kế đã duyệt, "
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
