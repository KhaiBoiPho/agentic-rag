"""MCP Tool — exact lookup against the structured material_prices table.

Deliberately NOT a semantic/vector search: a wrong material or region match
here produces a wrong construction cost downstream, so this tool queries
Postgres directly and reports "not found" rather than a fuzzy best guess.
"""
from __future__ import annotations

from mcp.types import TextContent, Tool

PRICE_LOOKUP_TOOL = Tool(
    name="lookup_material_price",
    description=(
        "Tra cứu đơn giá vật liệu xây dựng đã công bố hoặc báo giá nhà cung cấp, "
        "theo vùng (HN|DN|HCM) và tên/nhóm vật liệu. Trả về giá mới nhất kèm nguồn, "
        "kỳ công bố và cơ sở giá (tại mỏ / tại chân công trình). "
        "Trả 'không tìm thấy' thay vì suy đoán khi thiếu dữ liệu."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "region": {"type": "string", "enum": ["HN", "DN", "HCM"], "description": "Vùng giá: Hà Nội | Đà Nẵng | TPHCM"},
            "material_category": {"type": "string", "description": "Nhóm vật liệu, vd 'xi măng', 'thép', 'cát'"},
            "material_name": {"type": "string", "description": "Tên vật liệu cụ thể, vd 'xi măng PCB40'"},
        },
        "required": ["region"],
    },
)


async def handle_lookup_material_price(args: dict) -> list[TextContent]:
    from app.db.postgres.repositories.material_price_repo import MaterialPriceRepository

    repo = MaterialPriceRepository()
    rows = await repo.lookup(
        region=args["region"],
        material_category=args.get("material_category"),
        material_name=args.get("material_name"),
        limit=10,
    )

    if not rows:
        return [TextContent(
            type="text",
            text=(
                f"Không tìm thấy giá cho vùng={args['region']}, "
                f"category={args.get('material_category', '-')}, "
                f"name={args.get('material_name', '-')}. "
                "Không suy đoán giá — cần bổ sung dữ liệu nguồn hoặc mở rộng tiêu chí tìm kiếm."
            ),
        )]

    lines = [
        "| Vật liệu | Đơn giá | Điều kiện giao | Kỳ | Nguồn |",
        "|---|---:|---|---|---|",
    ]
    for r in rows:
        basis = {
            "tai_mo": "tại nơi sản xuất",
            "tai_chan_cong_trinh": "tại chân công trình",
            "dai_ly": "tại đại lý",
        }.get(r.price_basis, "không rõ")
        period = r.price_period or "không rõ"
        source = {
            "official_announcement": "công bố Sở Xây dựng",
            "official_annex": "phụ lục công bố Sở Xây dựng",
            "vendor_quote": "báo giá nhà cung cấp",
        }.get(r.source_type, r.source_type)
        name = r.material_name + (f" ({r.spec})" if r.spec else "")
        source_cell = source + (f" — {r.manufacturer}" if r.manufacturer else "")
        lines.append(f"| {name} | **{r.price_ex_vat:,.0f} đ**/{r.unit} | {basis} | {period} | {source_cell} |")

    return [TextContent(type="text", text="\n".join(lines))]
