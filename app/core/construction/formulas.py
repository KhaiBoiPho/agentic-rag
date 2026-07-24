"""Deterministic material-quantity formulas — implemented from Chương 16–22
of DataRAG-uoc-luong-gia-vlxd.md (bê tông, cốt thép, tường xây, trát, ốp lát,
sơn). These are plain-Python calculations, not LLM reasoning: the domain
guide explicitly warns that a result with many decimal digits is not the
same as an accurate one, and arithmetic here must be exact and auditable.

Coverage is deliberately limited to the chapters most relevant to a typical
"nhà ở dân dụng" estimate (masonry house, concrete frame). Chương 18, 23–29
(cốp pha, chống thấm, mái, trần, cửa, kết cấu thép, MEP, hạ tầng) are out of
scope for now and would follow the same pattern if needed later.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QuantityResult:
    work_type: str
    quantities: dict[str, float]  # material_name -> quantity
    units: dict[str, str]         # material_name -> unit
    assumptions: list[str] = field(default_factory=list)


# ─── Chương 16 — Bê tông ────────────────────────────────────────────────────

# Xi măng/cát/đá per m3, theo cấp phối tham khảo mác 250 — dùng cho ước lượng
# sơ bộ khi trộn tại chỗ; dự toán chính thức phải dùng cấp phối được duyệt
# hoặc định mức áp dụng (mục 16.2 trong file .md).
_CONCRETE_MIX_PER_M3 = {
    "M200": {"xi_mang_kg": 350, "cat_m3": 0.50, "da_m3": 0.90},
    "M250": {"xi_mang_kg": 400, "cat_m3": 0.48, "da_m3": 0.85},
    "M300": {"xi_mang_kg": 450, "cat_m3": 0.45, "da_m3": 0.82},
}


def concrete(volume_m3: float, mix_grade: str = "M250", ready_mix: bool = True) -> QuantityResult:
    if volume_m3 <= 0:
        raise ValueError("volume_m3 phải > 0")

    if ready_mix:
        return QuantityResult(
            work_type="concrete",
            quantities={"be_tong_thuong_pham": round(volume_m3, 3)},
            units={"be_tong_thuong_pham": "m3"},
            assumptions=[
                f"Bê tông thương phẩm mác {mix_grade}, không bóc riêng xi măng/cát/đá "
                "(mục 16.2) — cần chốt độ sụt, cỡ đá, yêu cầu bơm khi tra giá.",
            ],
        )

    mix = _CONCRETE_MIX_PER_M3.get(mix_grade, _CONCRETE_MIX_PER_M3["M250"])
    return QuantityResult(
        work_type="concrete",
        quantities={
            "xi_mang": round(volume_m3 * mix["xi_mang_kg"], 1),
            "cat": round(volume_m3 * mix["cat_m3"], 3),
            "da": round(volume_m3 * mix["da_m3"], 3),
        },
        units={"xi_mang": "kg", "cat": "m3", "da": "m3"},
        assumptions=[
            f"Cấp phối tham khảo cho mác {mix_grade}, trộn tại chỗ — KHÔNG dùng cho "
            "dự toán chính thức, phải thay bằng cấp phối được duyệt hoặc định mức áp dụng.",
        ],
    )


# ─── Chương 17 — Cốt thép ───────────────────────────────────────────────────

def rebar_unit_weight_kg_per_m(diameter_mm: float) -> float:
    """w ≈ d² / 162 (kg/m), d tính bằng milimét — công thức gần đúng chuẩn
    (mục 17.1), dùng kiểm tra/bóc sơ bộ. Mua hàng/nghiệm thu phải theo
    tiêu chuẩn sản phẩm và chứng từ lô thép."""
    return (diameter_mm ** 2) / 162.0


def rebar_from_geometry(diameter_mm: float, total_length_m: float) -> QuantityResult:
    """Ước lượng sơ bộ khi CHƯA có bảng thống kê thép. Ưu tiên rebar_from_bbs
    khi đã có bản vẽ thi công (mục 17.2)."""
    if total_length_m <= 0:
        raise ValueError("total_length_m phải > 0")
    weight = rebar_unit_weight_kg_per_m(diameter_mm) * total_length_m
    return QuantityResult(
        work_type="rebar",
        quantities={f"thep_D{int(diameter_mm)}": round(weight, 1)},
        units={f"thep_D{int(diameter_mm)}": "kg"},
        assumptions=[
            "Tính từ hình học/tổng chiều dài thanh, KHÔNG phải từ bảng thống kê thép — "
            "chỉ dùng cho ước lượng sơ bộ (mục 17.1). Có bản vẽ thi công thì dùng "
            "rebar_from_bbs để cộng đúng neo/nối/uốn.",
        ],
    )


def rebar_from_bbs(bar_schedule: list[dict]) -> QuantityResult:
    """Q = Σ N_i × L_i × w_i (mục 17.2). Mỗi item: {diameter_mm, count, length_m}
    với length_m đã bao gồm móc/neo/uốn/nối theo bản vẽ thống kê thép."""
    total_by_diameter: dict[float, float] = {}
    for item in bar_schedule:
        d = item["diameter_mm"]
        n = item["count"]
        length = item["length_m"]
        w = rebar_unit_weight_kg_per_m(d) * n * length
        total_by_diameter[d] = total_by_diameter.get(d, 0.0) + w

    quantities = {f"thep_D{int(d)}": round(w, 1) for d, w in total_by_diameter.items()}
    units = {k: "kg" for k in quantities}
    return QuantityResult(
        work_type="rebar",
        quantities=quantities,
        units=units,
        assumptions=[
            "Tính từ bảng thống kê thép (BBS) — phương pháp ưu tiên khi có bản vẽ thi công. "
            "Không cộng thêm neo nếu length_m đã bao gồm; không tính chồng nối cơ khí/nối chồng.",
        ],
    )


# ─── Chương 19 — Tường xây ──────────────────────────────────────────────────

# Kích thước gạch phổ biến (m): dài x cao, mạch vữa mặc định 10mm.
_BRICK_SIZES_M = {
    "gach_dat_nung": (0.19, 0.055),
    "gach_ong": (0.08, 0.08),
    "block_aac": (0.60, 0.20),
}


def masonry_wall(
    length_m: float,
    height_m: float,
    thickness_m: float,
    openings_area_m2: float = 0.0,
    brick_type: str = "gach_ong",
    mortar_joint_m: float = 0.01,
) -> QuantityResult:
    """A_net = L×H − A_openings (mục 19.1); số viên theo mô đun xây (mục 19.2);
    vữa xây từ chênh lệch thể tích khối xây và thể tích viên (mục 19.3)."""
    if length_m <= 0 or height_m <= 0 or thickness_m <= 0:
        raise ValueError("length_m/height_m/thickness_m phải > 0")

    area_net = length_m * height_m - openings_area_m2
    if area_net <= 0:
        raise ValueError("Diện tích tường thuần <= 0 — kiểm tra openings_area_m2")
    volume_wall = area_net * thickness_m

    brick_l, brick_h = _BRICK_SIZES_M.get(brick_type, _BRICK_SIZES_M["gach_ong"])
    n_per_m2 = 1.0 / ((brick_l + mortar_joint_m) * (brick_h + mortar_joint_m))
    n_net = area_net * n_per_m2
    n_buy = n_net * 1.05  # dự phòng cắt/vỡ tham khảo — không thay cho định mức áp dụng

    brick_volume_each = brick_l * brick_h * thickness_m
    mortar_volume = max(volume_wall - n_net * brick_volume_each, 0.0)

    return QuantityResult(
        work_type="masonry_wall",
        quantities={
            "so_vien_gach": round(n_buy),
            "vua_xay": round(mortar_volume, 3),
        },
        units={"so_vien_gach": "viên", "vua_xay": "m3"},
        assumptions=[
            f"A_net = {area_net:.2f} m2, loại gạch {brick_type}, mạch vữa {mortar_joint_m*1000:.0f}mm.",
            "Số viên mua gồm +5% dự phòng cắt/vỡ tham khảo, KHÔNG thay cho định mức áp dụng "
            "hoặc layout xây thực tế — hao hụt thực tế phụ thuộc độ giòn, số góc, lỗ mở (mục 19.2).",
            "Vữa xây tính theo hình học (mục 19.3) — dự toán chính thức nên ưu tiên định mức áp dụng.",
        ],
    )


# ─── Chương 20 — Trát ───────────────────────────────────────────────────────

def plaster(area_m2: float, thickness_mm: float = 15.0, dry_mortar_kg_per_m2_per_mm: float = 1.6) -> QuantityResult:
    """M_dry = A × c_manufacturer(t) (mục 20.2) — hệ số tiêu hao tham khảo,
    dự toán chính thức phải dùng định mức nhà sản xuất công bố."""
    if area_m2 <= 0:
        raise ValueError("area_m2 phải > 0")
    dry_mortar_kg = area_m2 * thickness_mm * dry_mortar_kg_per_m2_per_mm
    return QuantityResult(
        work_type="plaster",
        quantities={"vua_kho_tron_san": round(dry_mortar_kg, 1)},
        units={"vua_kho_tron_san": "kg"},
        assumptions=[
            f"Chiều dày trát {thickness_mm}mm, hệ số tiêu hao {dry_mortar_kg_per_m2_per_mm} kg/m2/mm — "
            "hệ số THAM KHẢO, phải thay bằng định mức nhà sản xuất công bố cho đúng loại vữa/nền (mục 20.2).",
        ],
    )


# ─── Chương 21 — Gạch ốp lát ────────────────────────────────────────────────

def tiling(area_m2: float, tile_size_m2: float = 0.36, waste_pct: float = 8.0) -> QuantityResult:
    """Diện tích thuần + làm tròn theo hộp (mục 21.1–21.2). waste_pct mặc định
    cao hơn so với vật liệu khác vì gạch ốp lát làm tròn theo thùng/hộp."""
    if area_m2 <= 0 or tile_size_m2 <= 0:
        raise ValueError("area_m2 và tile_size_m2 phải > 0")
    area_buy = area_m2 * (1 + waste_pct / 100)
    n_tiles = area_buy / tile_size_m2
    return QuantityResult(
        work_type="tiling",
        quantities={"so_vien_gach_lat": round(n_tiles) , "dien_tich_mua": round(area_buy, 2)},
        units={"so_vien_gach_lat": "viên", "dien_tich_mua": "m2"},
        assumptions=[
            f"Diện tích thuần {area_m2:.2f} m2 + {waste_pct:.0f}% hao hụt/cắt — cần làm tròn "
            "theo số hộp thực tế của nhà sản xuất (mục 21.2), số viên trên chỉ là tham khảo.",
        ],
    )


# ─── Chương 22 — Sơn ────────────────────────────────────────────────────────

def paint(area_m2: float, coats: int = 2, coverage_m2_per_liter: float = 10.0) -> QuantityResult:
    """Lượng sơn lý thuyết = diện tích × số lớp / định mức phủ (mục 22.2)."""
    if area_m2 <= 0 or coats <= 0 or coverage_m2_per_liter <= 0:
        raise ValueError("area_m2, coats, coverage_m2_per_liter phải > 0")
    liters = (area_m2 * coats) / coverage_m2_per_liter
    return QuantityResult(
        work_type="paint",
        quantities={"son": round(liters, 2)},
        units={"son": "lít"},
        assumptions=[
            f"{coats} lớp, định mức phủ {coverage_m2_per_liter} m2/lít — định mức THAM KHẢO theo "
            "nhà sản xuất, thực tế phụ thuộc độ hút bề mặt và phương pháp thi công (mục 22.2).",
            "Lượng mua thực tế cần làm tròn theo thùng sơn (mục 22.3), không dùng số lít lý thuyết trực tiếp.",
        ],
    )
