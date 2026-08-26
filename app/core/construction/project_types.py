"""Vật liệu THÔ cho ước lượng chi phí xây nhà ở dân dụng (nhà phố).

Lịch sử: bản đầu của module này hỗ trợ 10 loại hình công trình (nhà xưởng,
sân bê tông, san nền, tường rào, vỉa hè, cải tạo...) cộng cả phần hoàn thiện
(sơn, gạch ốp lát, 3 mức hoàn thiện). Phạm vi đã được thu hẹp chủ đích chỉ còn
lại đúng "nhà ở dân dụng — phần vật liệu thô", mức hoàn thiện luôn là "thô":
mọi loại hình/công trình khác và phần hoàn thiện đã bị XOÁ khỏi code, không
phải chỉ ẩn trên UI — muốn khôi phục thì lấy lại từ lịch sử git.

What these numbers are — and are not
------------------------------------
Norm/WF là hệ số THAM KHẢO cho ước lượng ý tưởng (mục 4.1 domain guide): dùng
khi chưa có bản vẽ/bảng thống kê thép/chỉ dẫn kỹ thuật, KHÔNG thay thế một
bản bóc tách khối lượng thật khi đã có các tài liệu đó.

Materials are referenced by slug; `MATERIAL_SPECS` maps each slug to how it
must be looked up in `material_prices` (name query, unit, and a description
precise enough for the LLM disambiguator to reject near-miss products such
as "xi măng chuyên dụng giếng khoan" when the estimate wants ordinary xi
măng xây trát).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MaterialSpec:
    """How one material slug is priced out of `material_prices`."""

    label: str
    name_query: str  # ILIKE fragment for MaterialPriceRepository.lookup
    unit: str  # unit the quantity is expressed in, and the unit filter
    target_desc: str  # sent to the LLM disambiguator — must exclude near-misses
    exclude_keywords: list[str] = field(default_factory=list)
    # Sanity bounds for ONE unit of `unit`, in VNĐ. Any candidate outside the
    # range is dropped before it can reach the estimate.
    #
    # This is not fussiness. The web-price fallback once returned ~1,8 tỷ
    # đ/kg for structural steel (a per-project figure scraped as a unit
    # price), which multiplied out to a 31.500 tỷ đ line item in a 500 m²
    # estimate — a number wrong by six orders of magnitude, printed with the
    # same confidence as every other line. Bounds are wide on purpose: they
    # exist to catch decimal/unit catastrophes, not to second-guess a real
    # market price.
    price_min: float = 0.0
    price_max: float = float("inf")
    # Other units the same material is published in, with the factor that
    # converts a price in THAT unit into a price in `unit`. Xi măng is listed
    # 31× per kg but 27× per tấn in Hà Nội alone; without this the tonne rows
    # are invisible and the material reports "no price data".
    alt_units: list[tuple[str, float]] = field(default_factory=list)


_PER_TONNE = [("tấn", 1 / 1000)]  # price per tonne -> price per kg


# 5 vật liệu thô của nhà phố (Phần I của công thức dự toán mới). Các slug
# khác từng tồn tại ở đây (bê tông thương phẩm, thép hình, tôn lợp, gạch ốp
# lát, sơn, cát san lấp) đã bị xoá cùng với các loại hình công trình và mức
# hoàn thiện dùng chúng — không còn ProjectType nào tham chiếu tới nữa.
MATERIAL_SPECS: dict[str, MaterialSpec] = {
    "thep": MaterialSpec(
        label="Thép xây dựng (cốt thép)",
        name_query="thép",
        unit="kg",
        target_desc=(
            "thép thanh/thép cây/thép cuộn dùng làm cốt thép bê tông (thép xây dựng) — "
            "KHÔNG phải ống thép, tôn thép, thép mạ kẽm, khung móng thép đúc sẵn"
        ),
        exclude_keywords=["ống thép", "mạ kẽm", "tôn thép", "thép mạ", "dày mạ"],
        price_min=8_000,
        price_max=60_000,
        alt_units=_PER_TONNE,
    ),
    "gach": MaterialSpec(
        label="Gạch xây",
        name_query="gạch",
        unit="viên",
        target_desc=(
            "gạch xây tường (gạch đặc, gạch rỗng, gạch block bê tông) dùng xây tường — "
            "KHÔNG phải gạch ốp lát/gạch trang trí bề mặt"
        ),
        price_min=500,
        price_max=30_000,
    ),
    "xi_mang": MaterialSpec(
        label="Xi măng",
        name_query="xi măng",
        unit="kg",
        target_desc=(
            "xi măng poóc lăng hỗn hợp PCB30/PCB40 dùng xây trát và trộn vữa — "
            "KHÔNG phải xi măng chuyên dụng giếng khoan/bền sunfat"
        ),
        price_min=1_000,
        price_max=6_000,
        alt_units=_PER_TONNE,
    ),
    "cat": MaterialSpec(
        label="Cát xây dựng",
        name_query="cát",
        unit="m3",
        target_desc=(
            "cát xây dựng (cát vàng/cát xây tô/cát bê tông) — KHÔNG phải cát san lấp "
            "nếu câu hỏi là cát xây, và ngược lại"
        ),
        price_min=100_000,
        price_max=1_500_000,
    ),
    "da": MaterialSpec(
        label="Đá dăm",
        name_query="đá",
        unit="m3",
        target_desc=(
            "đá dăm/đá 1x2/đá 4x6 dùng làm lớp móng đường, lót nền, trộn bê tông — "
            "KHÔNG phải đá ốp lát trang trí"
        ),
        price_min=100_000,
        price_max=1_500_000,
    ),
}


# ─── "Nhà ở" floor-area geometry (công thức dự toán mới — Phần I) ──────────
#
# S_build = S_foundation × H_foundation + Σ S_floor + S_roof × H_roof.
# H_foundation is a fixed reference coefficient per loại móng — NOT a real
# height in metres, it is how much more material a deep/heavy foundation
# costs relative to floor area (móng bè/cọc cao hơn móng đơn nhiều).
FOUNDATION_HEIGHT_FACTOR: dict[str, float] = {
    "mong_don": 0.25,
    "mong_coc": 0.35,
    "mong_bang": 0.50,
    "mong_be": 0.70,
}


def compute_house_floor_area(
    foundation_area_m2: float,
    foundation_type: str,
    floor_areas_m2: list[float],
    roof_area_m2: float,
    roof_height_factor: float = 1.0,
) -> float:
    """S_build cho nhà ở, từ móng + từng tầng + mái, thay cho việc người dùng
    phải tự cộng sẵn một con số floor_area_m2 duy nhất.

    `roof_height_factor` mặc định 1.0 (mái tính đúng 1 lần diện tích, không
    nhân thêm). Bản gốc của công thức gọi tham số này là "chiều cao mái"
    (H_roof) nhưng không nêu đơn vị — hiểu là mét thật thì S_roof(m²) ×
    H_roof(m) ra m³, phá vỡ tính nhất quán cộng-dồn-diện-tích của cả công
    thức. Đã xác nhận: đây là một HỆ SỐ không thứ nguyên (giống
    H_foundation) bù diện tích BỀ MẶT mái dốc so với diện tích HÌNH CHIẾU
    mặt bằng (roof_area_m2), không phải chiều cao đo bằng mét. Trường này
    giờ có mặt trong FORM_SCHEMAS (intent.py) và COST_TOOL.inputSchema
    (cost_tool.py) — trước đây bị bỏ sót ở cả hai nơi nên luôn nhận đúng
    giá trị mặc định 1.0 dù người dùng có nhà mái dốc hay không.
    """
    if foundation_area_m2 <= 0:
        raise ValueError("foundation_area_m2 phải > 0")
    if roof_area_m2 <= 0:
        raise ValueError("roof_area_m2 phải > 0")
    if not floor_areas_m2 or any(a <= 0 for a in floor_areas_m2):
        raise ValueError("floor_areas_m2 phải có ít nhất 1 giá trị > 0")

    h_foundation = FOUNDATION_HEIGHT_FACTOR.get(foundation_type)
    if h_foundation is None:
        raise ValueError(
            f"foundation_type không hợp lệ: {foundation_type!r} "
            f"(phải là một trong {sorted(FOUNDATION_HEIGHT_FACTOR)})"
        )

    return (
        foundation_area_m2 * h_foundation
        + sum(floor_areas_m2)
        + roof_area_m2 * roof_height_factor
    )


@dataclass(frozen=True)
class ProjectType:
    key: str
    label: str
    area_label: str  # what the input area measures, shown in the answer
    # slug -> quantity consumed per 1 unit of reference area
    coefficients: dict[str, float]
    note: str
    # Hệ số hao hụt (WF) áp thêm cho từng vật liệu, theo Phụ lục VIII –
    # TT 12/2021/TT-BXD. slug -> WF; vật liệu không khai ở đây giữ WF = 1.0.
    rough_wf: dict[str, float] = field(default_factory=dict)
    # "Vật tư phụ & hệ thống âm tường thô" — phụ phí tính bằng % trên TỔNG
    # THÀNH TIỀN của rough_surcharge_base_slugs, KHÔNG tra material_prices
    # (không phải một sản phẩm thật, chỉ là hệ số bóc tách BOQ kinh nghiệm).
    rough_surcharge_pct: float = 0.0
    rough_surcharge_base_slugs: tuple[str, ...] = ()
    rough_surcharge_label: str = "Vật tư phụ & hệ thống âm tường thô"


# Chỉ còn đúng 1 loại hình: nhà phố / nhà ở dân dụng, phần vật liệu thô.
PROJECT_TYPES: dict[str, ProjectType] = {
    "nha_pho": ProjectType(
        key="nha_pho",
        label="Nhà phố / nhà ở dân dụng (khung BTCT) — phần thô",
        area_label="m² sàn",
        coefficients={
            # Norm tham khảo nhóm cung cấp, CHƯA đối chiếu được với một định
            # mức chính thức cụ thể — xem rough_wf/note bên dưới trước khi
            # trích dẫn số này vào báo cáo. Không có dòng "bê tông thương
            # phẩm" riêng: xi_mang/cat/da ở đây đã gộp cả nhu cầu trộn bê
            # tông lẫn vữa xây/trát.
            "thep": 42.0,
            "xi_mang": 100.0,  # ≈ 2 bao/m² × 50kg — TRA GIÁ vẫn theo kg/tấn (không theo "bao", xem cost_tool.py)
            "cat": 0.45,
            "da": 0.25,
            "gach": 90.0,
        },
        rough_wf={"thep": 1.05, "xi_mang": 1.0, "cat": 1.05, "da": 1.03, "gach": 1.05},
        rough_surcharge_pct=0.35,
        rough_surcharge_base_slugs=("thep", "xi_mang", "cat", "da", "gach"),
        note=(
            "Nhà 1–4 tầng, khung bê tông cốt thép, tường xây gạch — CHỈ phần vật liệu "
            "THÔ (không tính sơn, gạch ốp lát, hay bất kỳ hạng mục hoàn thiện nào). "
            "Diện tích tính từ móng/tầng/mái (xem compute_house_floor_area), hệ số hao "
            "hụt riêng từng vật liệu (Phụ lục VIII – TT 12/2021/TT-BXD), cộng 35% vật "
            "tư phụ & hệ thống âm tường trên tổng 5 vật liệu thô chính."
        ),
    ),
}

DEFAULT_PROJECT_TYPE = "nha_pho"


def get_project_type(key: str | None) -> ProjectType:
    return PROJECT_TYPES.get(key or DEFAULT_PROJECT_TYPE, PROJECT_TYPES[DEFAULT_PROJECT_TYPE])
