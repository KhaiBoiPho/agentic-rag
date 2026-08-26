"""MCP Tool — construction cost orchestrator for nhà ở dân dụng, phần THÔ.

Scope note (important): without a detailed design (bản vẽ, bảng thống kê
thép, chỉ dẫn kỹ thuật), the domain guide's own classification (mục 4.1
"Ước lượng ý tưởng") says only floor-area-based parametric estimation is
valid — not a detailed take-off. This tool therefore:
  1. Derives floor area from móng/tầng/mái geometry (or accepts it directly).
  2. Derives PHẦN THÔ material QUANTITIES from that area using reference
     consumption coefficients + hệ số hao hụt (WF) — rough parametric
     coefficients for a low-rise residential house, not a substitute for
     actual geometric take-off.
  3. Prices those quantities via the structured material_prices table
     (region-scoped), falling back to web search when the DB has a gap.
  4. Sums to a MATERIAL cost estimate only — explicitly NOT a turnkey
     "giá xây nhà" figure, since labor, equipment, contractor margin, VAT
     and indirect costs are outside this corpus's price data entirely.

Scope was narrowed deliberately (and the removed code deleted, not just
hidden): only nhà phố/nhà ở dân dụng is supported — nhà xưởng, nhà kho, sân
bê tông, san nền, tường rào, vỉa hè, cải tạo are gone. Only "phần thô" is
priced — sơn, gạch ốp lát, and the 3-tier finish level (thô/cơ bản/cao cấp)
are gone; there is exactly one, implicit level: thô.

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
    FOUNDATION_HEIGHT_FACTOR,
    MATERIAL_SPECS,
    compute_house_floor_area,
    get_project_type,
)

COST_TOOL = Tool(
    name="calculate_construction_cost",
    description=(
        "Ước lượng Ý TƯỞNG chi phí VẬT LIỆU THÔ (thép, xi măng, cát, đá, gạch xây + vật tư "
        "phụ) cho nhà phố / nhà ở dân dụng, từ diện tích móng/tầng/mái (chưa có bản vẽ chi "
        "tiết). KHÔNG tính phần hoàn thiện (sơn, gạch ốp lát...), KHÔNG hỗ trợ loại công "
        "trình khác ngoài nhà ở. Trả về khoảng giá kèm giả định — KHÔNG bao gồm nhân công, "
        "thiết bị, lợi nhuận nhà thầu, VAT, chi phí gián tiếp. Không dùng thay dự toán/hợp đồng."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "floor_area_m2": {
                "type": "number",
                "description": (
                    "Tổng diện tích sàn xây dựng (m2), đã gồm các tầng. Chỉ dùng khi KHÔNG đủ "
                    "dữ liệu hình học — BỎ QUA trường này nếu đã cung cấp đủ "
                    "foundation_area_m2 + foundation_type + floor_areas_m2 + roof_area_m2, hệ "
                    "thống sẽ tự tính diện tích từ 4 trường đó và ưu tiên kết quả tính được."
                ),
            },
            "foundation_area_m2": {
                "type": "number",
                "description": "Diện tích móng (m2) — dùng cùng foundation_type/floor_areas_m2/roof_area_m2 (+ roof_height_factor tuỳ chọn) để TỰ TÍNH diện tích sàn theo công thức S_build = S_móng×H_móng + ΣS_tầng + S_mái×hệ_số_mái.",
            },
            "foundation_type": {
                "type": "string",
                "enum": list(FOUNDATION_HEIGHT_FACTOR.keys()),
                "description": "Loại móng — quyết định hệ số H_móng: mong_don (0,25) | mong_coc (0,35) | mong_bang (0,50) | mong_be (0,70).",
            },
            "floor_areas_m2": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Diện tích từng tầng (m2), theo thứ tự — ví dụ [80, 75, 75] cho nhà 3 tầng.",
            },
            "roof_area_m2": {
                "type": "number",
                "description": "Diện tích mái (m2), đo theo hình chiếu mặt bằng.",
            },
            "roof_height_factor": {
                "type": "number",
                "description": (
                    "Hệ số mái, KHÔNG THỨ NGUYÊN (không phải chiều cao thật đo bằng mét — "
                    "roof_area_m2 x mét sẽ ra m3, phá vỡ phép cộng diện tích của S_build). Bù "
                    "diện tích bề mặt mái dốc so với roof_area_m2 (diện tích hình chiếu). Mặc "
                    "định 1.0 (mái bằng); mái tôn/ngói dốc dùng khoảng 1,15-1,3. Bỏ qua trường "
                    "này nếu không rõ — sẽ dùng mặc định 1.0."
                ),
            },
            "region": {"type": "string", "enum": ["HN", "DN", "HCM"]},
        },
        # floor_area_m2 is NOT required at the schema level any more — it can
        # come either directly, or be derived from the 4 geometry fields (see
        # their descriptions above). _compute_cost enforces "at least one of
        # the two" at runtime and returns a clear error otherwise.
        "required": ["region"],
    },
)

# Hệ số tiêu hao KHÔNG khai báo ở đây — nằm trong
# `PROJECT_TYPES["nha_pho"].coefficients` (project_types.py). `_compute_cost`
# đọc thẳng từ đó qua vòng lặp `for slug, per_m2 in project.coefficients.items()`.


def _display_name(row) -> str:
    """The specific product a price came from, for showing "which cement did
    the system actually price this with" instead of only the generic
    category label (§ user request: matched_name in each line item).
    `row` is a MaterialPrice ORM row (has material_name/spec/manufacturer)."""
    name = row.material_name
    # getattr, not row.spec/row.manufacturer directly — test stubs (and any
    # future lightweight row shape) don't always carry every optional column,
    # and neither is essential to identify which product this is.
    spec = getattr(row, "spec", None)
    if spec:
        name += f" ({spec})"
    manufacturer = getattr(row, "manufacturer", None)
    if manufacturer:
        name += f" — {manufacturer}"
    return name


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
- NẾU có dòng "Cách tính diện tích: S_build = ..." trong dữ liệu: BẮT BUỘC phải nêu
  lại dòng này (có thể diễn đạt gọn hơn nhưng phải giữ đủ các số hạng móng/tầng/mái và
  kết quả cuối) NGAY ĐẦU câu trả lời, trước khi liệt kê từng vật liệu — đây là cách
  DUY NHẤT người dùng biết diện tích tổng đã cộng cả phần móng, từng tầng và mái vào
  hay chưa. TUYỆT ĐỐI không được bỏ qua dòng này chỉ vì muốn câu trả lời gọn hơn.
- Với hạng mục có giá lấy từ web (đánh dấu [n]), giữ NGUYÊN ký hiệu [n] ngay sau
  số tiền của hạng mục đó, và nói rõ đó là giá tham khảo từ web, chưa xác thực.
- Nêu rõ hạng mục không có dữ liệu giá; nếu thiếu thì giải thích vì sao không đưa tổng.
- Với MỖI hạng mục có dòng "Sản phẩm dùng để định giá: ...": PHẢI nêu ĐÚNG TÊN SẢN PHẨM
  cụ thể đó trong câu trả lời (VD "Xi măng PCB40 Hà Tiên"), không được chỉ nói chung chung
  "xi măng" — người dùng cần biết giá đang tính dựa trên sản phẩm nào để đối chiếu lại.
- Với MỖI hạng mục có dòng "Công thức khối lượng: ...": nêu ngắn gọn cách tính ra khối
  lượng đó (diện tích × định mức × hao hụt) ngay trước hoặc trong ngoặc, để người dùng
  thấy được luồng tính từ công thức ra số liệu, không chỉ đưa thẳng kết quả cuối.
- Nhắc ngắn gọn: đây chỉ là chi phí vật liệu THÔ chính, chưa gồm nhân công/thiết bị/lợi
  nhuận/VAT, và chưa gồm phần hoàn thiện (sơn, gạch ốp lát...).
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
        f"Loại hình: {data.get('project_label', 'Nhà phố / nhà ở dân dụng — phần thô')}. "
        f"Quy mô: {data['area']:.0f} {data.get('area_label', 'm² sàn')}. "
        f"Vùng: {data['region']}.",
    ]
    if data.get("area_formula_note"):
        lines.append(f"Cách tính diện tích: {data['area_formula_note']}.")
    lines += [
        "Chi phí VẬT LIỆU THÔ (chưa gồm nhân công/thiết bị/lợi nhuận/VAT/gián tiếp, "
        "chưa gồm phần hoàn thiện).",
        "",
        "Các hạng mục:",
    ]
    for li in data["line_items"]:
        if li.get("derived"):
            # "Vật tư phụ" — phụ phí % trên thành tiền các dòng khác, không
            # có khối lượng/đơn giá riêng để in.
            lines.append(f"- {li['item']}: {li.get('derived_note', '')} = {li['subtotal']:,.0f} đ")
            continue
        # Full formula-to-number trail per material — user-requested: don't
        # just show the final qty×price, show HOW qty was derived (§ Norm ×
        # S_build × WF), and WHICH exact product's price was used (not just
        # the generic category label "item").
        if li.get("formula_note"):
            lines.append(f"- {li['item']} — công thức khối lượng: {li['formula_note']}")
        else:
            lines.append(f"- {li['item']}:")
        if li["subtotal"] is not None:
            tag = (
                f" [{li['source_index']}] (giá từ web, chưa xác thực)" if li.get("via_web") else ""
            )
            source_kind = "giá tham khảo web" if li.get("via_web") else "giá công bố"
            if li.get("matched_name"):
                lines.append(
                    f"  Sản phẩm dùng để định giá ({source_kind}): \"{li['matched_name']}\""
                )
            lines.append(
                f"  Thành tiền: {li['qty']:g} {li['unit']} × {li['unit_price']:,.0f} đ "
                f"= {li['subtotal']:,.0f} đ{tag}"
            )
        else:
            lines.append(
                f"  {li['qty']:g} {li['unit']} — KHÔNG có dữ liệu giá (kể cả tìm trên web)"
            )
    lines.append("")
    if data["has_full_pricing"]:
        low, high = data["priced_subtotal"] * 0.85, data["priced_subtotal"] * 1.20
        lines.append(
            f"Tổng ước lượng chi phí vật liệu thô: {low:,.0f} – {high:,.0f} đ "
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
            lines.append(f"Đơn giá vật liệu thô ước tính: {cost_per_m2:,.0f} đ/m² sàn.")
            lines.append(
                f"→ Với ngân sách này, diện tích sàn khả thi ước tính khoảng "
                f"{suggested_area:.0f} m² (cùng vùng, chỉ tính vật liệu thô chính — "
                f"không gồm nhân công/thiết bị/lợi nhuận/VAT/hoàn thiện)."
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

    region = args["region"]
    # Default changed to ON: the DB has real gaps for some region/material
    # combinations (notably gạch xây ở HCM — no "viên"-unit rows at all), and
    # the decision was to fill those from web search rather than always
    # reporting "no data" for a common, everyday material. A web price is
    # still never blended silently — see search_web_price's docstring and
    # build_cost_facts/_format_cost_text, which always tag it [n]/⚠️ and cite
    # the source, distinct from a DB-backed (authoritative) price.
    allow_web_fallback = bool(args.get("allow_web_fallback", True))

    # Diện tích: ưu tiên tính từ hình học (móng + từng tầng + mái) nếu đủ dữ
    # liệu — công thức mới. floor_area_m2 trực tiếp là fallback khi thiếu
    # dữ liệu hình học.
    geometry_keys = ("foundation_area_m2", "foundation_type", "floor_areas_m2", "roof_area_m2")
    area_formula_note: str | None = None
    if all(args.get(k) is not None for k in geometry_keys):
        try:
            area = compute_house_floor_area(
                foundation_area_m2=args["foundation_area_m2"],
                foundation_type=args["foundation_type"],
                floor_areas_m2=args["floor_areas_m2"],
                roof_area_m2=args["roof_area_m2"],
                roof_height_factor=args.get("roof_height_factor", 1.0),
            )
        except ValueError as exc:
            return {"error": str(exc)}
        h = FOUNDATION_HEIGHT_FACTOR[args["foundation_type"]]
        floors_txt = " + ".join(f"{a:g}" for a in args["floor_areas_m2"])
        area_formula_note = (
            f"S_build = {args['foundation_area_m2']:g}×{h:g} (móng) + {floors_txt} (tầng) + "
            f"{args['roof_area_m2']:g}×{args.get('roof_height_factor', 1.0):g} (mái) = {area:.1f} m²"
        )
    else:
        area = args.get("floor_area_m2")
        if area is None:
            return {
                "error": (
                    "Thiếu diện tích: truyền floor_area_m2, HOẶC đủ 4 trường "
                    "foundation_area_m2/foundation_type/floor_areas_m2/roof_area_m2."
                )
            }
    if area <= 0:
        return {"error": "Diện tích tính được phải > 0"}

    # Chỉ còn một loại hình (nhà phố — phần thô); get_project_type() luôn trả
    # về nó bất kể args.get("project_type") là gì.
    project = get_project_type(None)

    # (slug, qty, formula_note) — formula_note is the Norm/S_build/WF trail
    # for THIS quantity, carried all the way to the output text so "how did
    # you get this number" is answerable from the reply itself, not just the
    # final qty×price line.
    demands: list[tuple[str, float, str]] = []
    for slug, per_m2 in project.coefficients.items():
        wf = project.rough_wf.get(slug, 1.0)  # hệ số hao hụt — 1.0 nếu không khai báo
        qty = area * per_m2 * wf
        if qty > 0:
            wf_txt = f" × hao hụt {wf:g}" if wf != 1.0 else ""
            unit = MATERIAL_SPECS[slug].unit
            formula_note = f"{area:.0f} m² × {per_m2:g} {unit}/m²{wf_txt} = {qty:.2f} {unit}"
            demands.append((slug, qty, formula_note))

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
        formula_note: str,
        exclude_keywords: list[str] | None = None,
    ) -> dict:
        """Pure — returns a line dict, no shared-state mutation, so the five
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
                "matched_name": _display_name(candidates[idx]),
                "formula_note": formula_note,
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

        # Not in the vetted price DB for this region. Default is now to fall
        # back to web search (allow_web_fallback defaults True — see above)
        # rather than always reporting "missing", because some region/material
        # combinations have real DB gaps (e.g. gạch xây ở HCM). The figure is
        # still always cited as unverified [n]/⚠️, never blended silently
        # with DB-backed prices. Passing allow_web_fallback=False explicitly
        # restores the old fail-closed behaviour (report missing, withhold
        # the total) for a caller that wants it.
        if not allow_web_fallback:
            return {
                "item": label,
                "formula_note": formula_note,
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
                "formula_note": formula_note,
                "qty": qty,
                "unit": unit,
                "unit_price": None,
                "subtotal": None,
                "via_web": False,
                "_missing": True,
            }

        return {
            "item": label,
            # No DB row here — the web result's own title is the closest
            # thing to "which product" the price came from.
            "matched_name": title,
            "formula_note": formula_note,
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
    # searches back-to-back, ~15s+ each). gather overlaps them.
    results = await asyncio.gather(
        *(
            price_line(
                slug,
                MATERIAL_SPECS[slug].label,
                MATERIAL_SPECS[slug].name_query,
                qty,
                MATERIAL_SPECS[slug].unit,
                MATERIAL_SPECS[slug].target_desc,
                formula_note,
                exclude_keywords=MATERIAL_SPECS[slug].exclude_keywords or None,
            )
            for slug, qty, formula_note in demands
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

    # "Vật tư phụ & hệ thống âm tường thô" — % trên TỔNG THÀNH TIỀN của các
    # vật liệu thô chính, KHÔNG tra material_prices (không phải một sản phẩm
    # thật). Thiếu giá bất kỳ vật liệu nền nào thì phụ phí cũng phải báo
    # thiếu — nó là % trên chính các dòng đó, không có ý nghĩa nếu tính thiếu.
    if project.rough_surcharge_pct > 0:
        base_labels = {MATERIAL_SPECS[s].label for s in project.rough_surcharge_base_slugs}
        base_items = [li for li in line_items if li["item"] in base_labels]
        base_missing = [li["item"] for li in base_items if li["subtotal"] is None]
        if base_missing:
            missing.append(project.rough_surcharge_label)
        else:
            base_subtotal = sum(li["subtotal"] for li in base_items)
            surcharge = round(base_subtotal * project.rough_surcharge_pct, 0)
            line_items.append(
                {
                    "item": project.rough_surcharge_label,
                    "qty": None,
                    "unit": None,
                    "unit_price": None,
                    "subtotal": surcharge,
                    "via_web": False,
                    "derived": True,
                    "derived_note": (
                        f"{project.rough_surcharge_pct:.0%} × "
                        f"({' + '.join(sorted(base_labels))})"
                    ),
                }
            )

    priced_subtotal = sum(li["subtotal"] for li in line_items if li["subtotal"] is not None)
    has_full_pricing = not missing

    return {
        "error": None,
        "area": area,
        "area_formula_note": area_formula_note,
        "region": region,
        "project_type": project.key,
        "project_label": project.label,
        "area_label": project.area_label,
        "project_note": project.note,
        "coef": dict(project.coefficients),
        "rough_wf": dict(project.rough_wf),
        "rough_surcharge_pct": project.rough_surcharge_pct,
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
    area, region = data["area"], data["region"]
    line_items, missing, web_sources = data["line_items"], data["missing"], data["web_sources"]
    coef = data["coef"]
    area_label = data.get("area_label", "m² sàn")

    lines = [
        "### Ước lượng ý tưởng chi phí vật liệu thô",
        f"**{data.get('project_label', 'Nhà phố / nhà ở dân dụng — phần thô')}** — "
        f"**{area:.0f} {area_label}** · vùng **{region}**",
        "",
        "*(Chưa gồm nhân công, thiết bị, lợi nhuận nhà thầu, VAT, chi phí gián tiếp, và "
        "chưa gồm phần hoàn thiện — sơn, gạch ốp lát...)*",
        "",
    ]
    if data.get("area_formula_note"):
        lines.append(f"*Cách tính diện tích: {data['area_formula_note']}*")
        lines.append("")
    lines += [
        "| Hạng mục | Sản phẩm dùng để định giá | Khối lượng | Đơn giá | Thành tiền |",
        "|---|---|---:|---:|---:|",
    ]
    for li in line_items:
        # Khối lượng shows the formula trail ("240 m² × 2 bao/m² = 480 bao"),
        # not just the final number, when one was computed for this line —
        # user-requested: the reply must show HOW a number was derived, not
        # only the result. Derived rows (phụ phí) keep their own % note.
        qty_cell = f"{li['formula_note']}" if li.get("formula_note") else f"{li.get('qty', '—')}"
        if li.get("derived"):
            lines.append(
                f"| {li['item']} | — | _{li.get('derived_note', '')}_ | — "
                f"| **{li['subtotal']:,.0f} đ** |"
            )
        elif li["subtotal"] is not None:
            tag = f" `[${li['source_index']}]`" if li.get("via_web") else ""
            unit_price_cell = f"{li['unit_price']:,.0f} đ{tag}"
            if li.get("via_web"):
                unit_price_cell += " ⚠️"
            product_cell = li.get("matched_name") or "—"
            lines.append(
                f"| {li['item']} | {product_cell} | {qty_cell} | {unit_price_cell} "
                f"| **{li['subtotal']:,.0f} đ** |"
            )
        else:
            lines.append(f"| {li['item']} | — | {qty_cell} | _không có dữ liệu_ | — |")

    lines.append("")

    if data["has_full_pricing"]:
        priced_subtotal = data["priced_subtotal"]
        low, high = priced_subtotal * 0.85, priced_subtotal * 1.20
        lines.append(f"### Tổng chi phí vật liệu thô: **{low:,.0f} – {high:,.0f} đ**")
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
    rough_wf = data.get("rough_wf") or {}
    for key, value in coef.items():
        spec = MATERIAL_SPECS.get(key)
        label = spec.label if spec else key
        unit = spec.unit if spec else ""
        wf = rough_wf.get(key)
        wf_txt = f" × hao hụt {wf:g}" if wf and wf != 1.0 else ""
        lines.append(f"- {label}: {value:g} {unit}/{area_label}{wf_txt}")
    if data.get("rough_surcharge_pct"):
        lines.append(
            f"- {data.get('rough_surcharge_pct', 0):.0%} phụ phí vật tư phụ & hệ thống âm "
            "tường thô, tính trên tổng thành tiền các vật liệu thô chính "
            "(theo Phụ lục VIII – TT 12/2021/TT-BXD cho phần hao hụt)."
        )
    if data.get("project_note"):
        lines.append("")
        lines.append(f"- *{data['project_note']}*")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    lines.append(
        f"*Đây chỉ là chi phí vật liệu THÔ chính của {len(coef)} hạng mục, không phải giá xây "
        "trọn gói, không gồm phần hoàn thiện, và không thay thế dự toán từ hồ sơ thiết kế đã "
        "duyệt, định mức hiện hành hoặc báo giá hợp lệ.*"
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
