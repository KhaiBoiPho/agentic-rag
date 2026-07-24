"""MCP Tool — deterministic material-quantity estimation per work_type.

Thin dispatch wrapper over app/core/construction/formulas.py. The actual
arithmetic is plain Python (see that module's docstring for why) — this
tool file only validates input shape and formats the result.
"""

from __future__ import annotations

import json

from mcp.types import TextContent, Tool

QUANTITY_TOOL = Tool(
    name="estimate_material_quantity",
    description=(
        "Tính khối lượng vật liệu cần cho một công tác xây dựng cụ thể theo công thức "
        "đo bóc chuẩn (bê tông, cốt thép, tường xây, trát, ốp lát, sơn). "
        "Dùng khi đã biết kích thước hình học của công tác — KHÔNG dùng để ước lượng "
        "toàn bộ công trình (dùng calculate_construction_cost cho việc đó)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "work_type": {
                "type": "string",
                "enum": [
                    "concrete",
                    "rebar_geometry",
                    "rebar_bbs",
                    "masonry_wall",
                    "plaster",
                    "tiling",
                    "paint",
                ],
            },
            "params": {
                "type": "object",
                "description": (
                    "Tham số theo work_type. concrete: {volume_m3, mix_grade?, ready_mix?}. "
                    "rebar_geometry: {diameter_mm, total_length_m}. "
                    "rebar_bbs: {bar_schedule: [{diameter_mm, count, length_m}]}. "
                    "masonry_wall: {length_m, height_m, thickness_m, "
                    "openings_area_m2?, brick_type?}. "
                    "plaster: {area_m2, thickness_mm?}. "
                    "tiling: {area_m2, tile_size_m2?, waste_pct?}. "
                    "paint: {area_m2, coats?, coverage_m2_per_liter?}."
                ),
            },
        },
        "required": ["work_type", "params"],
    },
)


async def handle_estimate_material_quantity(args: dict) -> list[TextContent]:
    from app.core.construction import formulas

    work_type = args["work_type"]
    params = args.get("params", {})

    dispatch = {
        "concrete": lambda p: formulas.concrete(**p),
        "rebar_geometry": lambda p: formulas.rebar_from_geometry(**p),
        "rebar_bbs": lambda p: formulas.rebar_from_bbs(**p),
        "masonry_wall": lambda p: formulas.masonry_wall(**p),
        "plaster": lambda p: formulas.plaster(**p),
        "tiling": lambda p: formulas.tiling(**p),
        "paint": lambda p: formulas.paint(**p),
    }

    fn = dispatch.get(work_type)
    if fn is None:
        return [TextContent(type="text", text=f"work_type '{work_type}' không được hỗ trợ.")]

    try:
        result = fn(params)
    except (TypeError, ValueError) as exc:
        return [TextContent(type="text", text=f"Tham số không hợp lệ cho {work_type}: {exc}")]

    payload = {
        "work_type": result.work_type,
        "quantities": result.quantities,
        "units": result.units,
        "assumptions": result.assumptions,
    }
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]
