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
        "Tra cứu vật liệu xây dựng trong dữ liệu giá đã công bố và báo giá nhà cung cấp, "
        "theo vùng (HN|DN|HCM). Trả về tên vật liệu, đơn giá, đơn vị, quy cách, "
        "nhà sản xuất, kỳ công bố và cơ sở giá (tại mỏ / tại chân công trình).\n"
        "DÙNG CÔNG CỤ NÀY CHO CẢ HAI LOẠI CÂU HỎI:\n"
        "  1. Hỏi GIÁ — 'giá xi măng PCB40 bao nhiêu' → truyền material_name.\n"
        "  2. Hỏi DANH MỤC — 'công ty X bán/sản xuất những loại vật liệu nào', "
        "'có những loại cát nào' → truyền manufacturer và/hoặc material_category. "
        "Kết quả trả về chính là danh sách sản phẩm cần liệt kê.\n"
        "Có thể truyền RIÊNG manufacturer mà không cần material_name. "
        "Trả 'không tìm thấy' thay vì suy đoán khi thiếu dữ liệu — TUYỆT ĐỐI không "
        "liệt kê sản phẩm từ kiến thức chung khi công cụ không trả về gì."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "region": {
                "type": "string",
                "enum": ["HN", "DN", "HCM"],
                "description": (
                    "Vùng giá: Hà Nội | Đà Nẵng | TPHCM. BỎ TRỐNG nếu câu hỏi không nêu "
                    "vùng — khi đó công cụ tra cả 3 vùng và ghi rõ vùng ở từng dòng. "
                    "ĐỪNG đoán vùng."
                ),
            },
            "material_category": {
                "type": "string",
                "description": "Nhóm vật liệu, vd 'xi măng', 'thép', 'cát'",
            },
            "material_name": {
                "type": "string",
                "description": "Tên vật liệu cụ thể, vd 'xi măng PCB40'",
            },
            "manufacturer": {
                "type": "string",
                "description": (
                    "Nhà sản xuất / thương hiệu, vd 'CADIVI', 'Hoà Phát', 'Vicem Hà Tiên'. "
                    "Dùng khi câu hỏi nêu tên công ty — nhiều bảng giá đặt thương hiệu ở "
                    "cột riêng chứ không nằm trong tên vật liệu."
                ),
            },
        },
        "required": [],
    },
)


async def handle_lookup_material_price(args: dict) -> list[TextContent]:
    from app.db.postgres.repositories.material_price_repo import MaterialPriceRepository

    repo = MaterialPriceRepository()
    rows = await repo.lookup(
        region=args.get("region") or None,
        material_category=args.get("material_category"),
        material_name=args.get("material_name"),
        manufacturer=args.get("manufacturer"),
        limit=10,
    )

    if not rows:
        return [
            TextContent(
                type="text",
                text=(
                    f"Không tìm thấy giá cho vùng={args.get('region') or 'tất cả'}, "
                    f"category={args.get('material_category', '-')}, "
                    f"name={args.get('material_name', '-')}, "
                    f"nhà sản xuất={args.get('manufacturer', '-')}. "
                    "Không suy đoán giá — cần bổ sung dữ liệu nguồn hoặc mở rộng tiêu chí tìm kiếm."
                ),
            )
        ]

    lines = [
        "| Vật liệu | Vùng | Đơn giá | Điều kiện giao | Kỳ | Nguồn |",
        "|---|---|---:|---|---|---|",
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
        lines.append(
            f"| {name} | {r.region} | **{r.price_ex_vat:,.0f} đ**/{r.unit} | {basis} "
            f"| {period} | {source_cell} |"
        )

    return [TextContent(type="text", text="\n".join(lines))]
