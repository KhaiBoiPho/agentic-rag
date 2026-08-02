"""Parametric material-consumption profiles per type of construction work.

Why this exists
---------------
`calculate_construction_cost` originally hard-coded one profile — a low-rise
reinforced-concrete house — and priced exactly four materials from it. A
construction business quoting work is asked about far more than houses: a
steel-frame factory shed uses almost no brick and is dominated by structural
steel and roof sheeting; a concrete yard has no walls, no paint and no
rebar-heavy frame; a boundary wall is priced per m² of *wall*, not per m² of
floor. Running all of those through the house profile produced numbers that
were not merely imprecise but structurally wrong (paint for a concrete yard,
25 kg/m² of rebar for a fence).

What these numbers are — and are not
------------------------------------
Each profile is a set of **reference consumption coefficients per m² of the
type's own reference area** (floor area, ground area or wall face area — see
`area_label`). They belong to the "ước lượng ý tưởng" precision level in the
domain guide (mục 4.1): valid when there is no drawing, no bar-bending
schedule and no specification, and explicitly NOT a substitute for a
quantity take-off once those exist.

They are planning figures for low-rise, conventional construction in
Vietnam. Real consumption moves with span, storey count, soil conditions,
structural system and specification — a 5-storey frame on weak soil can
exceed the house profile's rebar figure by half. Treat every output as a
range with the assumptions printed, which is what the tool does.

Materials are referenced by slug; `MATERIAL_SPECS` maps each slug to how it
must be looked up in `material_prices` (name query, unit, and a description
precise enough for the LLM disambiguator to reject near-miss products such
as "sơn kẻ vạch đường" when the estimate wants wall paint).
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
    # factory estimate — a number wrong by six orders of magnitude, printed
    # with the same confidence as every other line. Bounds are wide on
    # purpose: they exist to catch decimal/unit catastrophes, not to
    # second-guess a real market price.
    price_min: float = 0.0
    price_max: float = float("inf")
    # Other units the same material is published in, with the factor that
    # converts a price in THAT unit into a price in `unit`. Xi măng is listed
    # 31× per kg but 27× per tấn in Hà Nội alone; without this the tonne rows
    # are invisible and the material reports "no price data".
    alt_units: list[tuple[str, float]] = field(default_factory=list)


_PER_TONNE = [("tấn", 1 / 1000)]  # price per tonne -> price per kg


MATERIAL_SPECS: dict[str, MaterialSpec] = {
    "be_tong": MaterialSpec(
        label="Bê tông thương phẩm",
        name_query="bê tông",
        unit="m3",
        target_desc=(
            "bê tông thương phẩm/bê tông tươi trộn sẵn dùng đổ móng, cột, dầm, sàn — "
            "KHÔNG phải bê tông đúc sẵn dạng tấm/panel/cấu kiện/cống/kè, "
            "KHÔNG phải cát dùng để trộn bê tông"
        ),
        price_min=500_000,
        price_max=5_000_000,
    ),
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
    "thep_hinh": MaterialSpec(
        label="Thép hình (kết cấu khung)",
        name_query="thép",
        unit="kg",
        target_desc=(
            "thép hình dùng làm kết cấu khung nhà thép tiền chế: thép H, thép I, thép U, "
            "thép V/thép góc, thép hộp kết cấu — KHÔNG phải thép thanh vằn làm cốt bê tông, "
            "KHÔNG phải tôn lợp"
        ),
        exclude_keywords=["thép cuộn", "thép thanh vằn", "tôn"],
        price_min=8_000,
        price_max=80_000,
        alt_units=_PER_TONNE,
    ),
    "ton_lop": MaterialSpec(
        label="Tôn lợp mái",
        name_query="tôn",
        unit="m2",
        target_desc=(
            "tôn lợp mái/tôn mạ màu/tôn kẽm dùng lợp mái và bao che nhà xưởng — "
            "KHÔNG phải thép tấm, KHÔNG phải thép hình"
        ),
        price_min=50_000,
        price_max=800_000,
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
    "gach_lat": MaterialSpec(
        label="Gạch lát nền",
        name_query="gạch",
        unit="m2",
        target_desc=(
            "gạch ốp lát nền/gạch men/gạch ceramic/granite dùng lát sàn hoàn thiện — "
            "KHÔNG phải gạch xây tường"
        ),
        price_min=50_000,
        price_max=2_000_000,
    ),
    "son": MaterialSpec(
        label="Sơn nước",
        name_query="sơn",
        unit="lít",
        target_desc=(
            "sơn nước/sơn phủ tường dùng sơn hoàn thiện công trình dân dụng — "
            "KHÔNG phải sơn giao thông/sơn kẻ vạch đường"
        ),
        price_min=30_000,
        price_max=500_000,
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
    "cat_san_lap": MaterialSpec(
        label="Cát san lấp",
        name_query="cát",
        unit="m3",
        target_desc="cát san lấp/cát đắp nền dùng tôn nền, san lấp mặt bằng",
        price_min=50_000,
        price_max=1_000_000,
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


@dataclass(frozen=True)
class ProjectType:
    key: str
    label: str
    area_label: str  # what the input area measures, shown in the answer
    # slug -> quantity consumed per 1 unit of reference area
    coefficients: dict[str, float]
    # Does `finish_level` change anything? A concrete yard has no finish tiers.
    finish_applies: bool
    note: str


# Consumption per m² of the reference area named in `area_label`.
#
# Sources of shape (not of exact value): the low-rise RC-frame house profile
# is the one this tool already used (0.35 m³ concrete, 25 kg steel, 1 m²
# wall, 2.2 m² paint per m² of floor); the other profiles keep the same
# modelling style and scale the same materials to how that structure is
# actually built. They are deliberately round numbers — presenting three
# significant figures would imply a precision this level of estimation does
# not have.
PROJECT_TYPES: dict[str, ProjectType] = {
    "nha_pho": ProjectType(
        key="nha_pho",
        label="Nhà phố / nhà ở dân dụng (khung BTCT)",
        area_label="m² sàn",
        coefficients={
            "be_tong": 0.35,
            "thep": 25.0,
            "gach": 55.0,  # ~55 viên/m² sàn ≈ 1 m² tường/m² sàn ở tường 100mm
            "xi_mang": 60.0,
            "cat": 0.20,
            "son": 0.44,  # 2,2 m² sơn/m² sàn ÷ 10 m²/lít × 2 nước
            "gach_lat": 0.85,
        },
        finish_applies=True,
        note=(
            "Nhà 1–4 tầng, khung bê tông cốt thép, tường xây gạch. Đây là hồ sơ mặc "
            "định và cũng là hồ sơ được hiệu chuẩn kỹ nhất."
        ),
    ),
    "nha_cap_4": ProjectType(
        key="nha_cap_4",
        label="Nhà cấp 4 (1 tầng, mái tôn/ngói)",
        area_label="m² sàn",
        coefficients={
            "be_tong": 0.18,
            "thep": 12.0,
            "gach": 60.0,
            "xi_mang": 55.0,
            "cat": 0.18,
            "son": 0.40,
            "ton_lop": 1.15,  # mái dốc ⇒ diện tích mái > diện tích sàn
            "gach_lat": 0.90,
        },
        finish_applies=True,
        note=(
            "Một tầng, không có sàn tầng trên nên lượng bê tông và thép thấp hơn hẳn "
            "nhà phố; phần bao che chuyển sang tường xây và mái lợp."
        ),
    ),
    "biet_thu": ProjectType(
        key="biet_thu",
        label="Biệt thự / nhà vườn",
        area_label="m² sàn",
        coefficients={
            "be_tong": 0.40,
            "thep": 30.0,
            "gach": 65.0,
            "xi_mang": 75.0,
            "cat": 0.25,
            "son": 0.60,
            "gach_lat": 1.00,
        },
        finish_applies=True,
        note=(
            "Nhịp lớn hơn và nhiều chi tiết kiến trúc hơn nhà phố nên tiêu hao vật "
            "liệu cao hơn khoảng 15–25%."
        ),
    ),
    "nha_xuong": ProjectType(
        key="nha_xuong",
        label="Nhà xưởng / nhà thép tiền chế",
        area_label="m² mặt bằng",
        coefficients={
            "be_tong": 0.22,  # móng đơn + nền công nghiệp
            "thep": 8.0,  # cốt thép móng và nền
            "thep_hinh": 35.0,  # khung kèo, cột, xà gồ — chi phối giá thành
            "ton_lop": 1.45,  # mái + bao che tường tôn
            "xi_mang": 20.0,
            "cat": 0.10,
            "da": 0.12,
        },
        finish_applies=False,
        note=(
            "Khung thép tiền chế: thép hình và tôn chi phối giá, gần như không dùng "
            "gạch xây hay sơn nước. Hệ số thay đổi mạnh theo khẩu độ và tải cầu trục."
        ),
    ),
    "nha_kho": ProjectType(
        key="nha_kho",
        label="Nhà kho / kho bãi có mái che",
        area_label="m² mặt bằng",
        coefficients={
            "be_tong": 0.18,
            "thep": 6.0,
            "thep_hinh": 25.0,
            "ton_lop": 1.35,
            "xi_mang": 15.0,
            "cat": 0.08,
            "da": 0.10,
        },
        finish_applies=False,
        note="Như nhà xưởng nhưng tải trọng và khẩu độ nhỏ hơn, ít yêu cầu nền chịu lực nặng.",
    ),
    "san_be_tong": ProjectType(
        key="san_be_tong",
        label="Sân bê tông / đường nội bộ / bãi đỗ xe",
        area_label="m² mặt bằng",
        coefficients={
            "be_tong": 0.16,  # dày ~15 cm kể cả hao hụt
            "thep": 4.5,  # lưới thép chống nứt
            "da": 0.18,  # lớp móng đá dăm
            "cat_san_lap": 0.12,
        },
        finish_applies=False,
        note=(
            "Kết cấu áo cứng dày 12–18 cm trên lớp móng đá dăm. Không có tường, không "
            "sơn, không hoàn thiện — nên `finish_level` không ảnh hưởng."
        ),
    ),
    "san_nen": ProjectType(
        key="san_nen",
        label="San nền / tôn nền mặt bằng",
        area_label="m² mặt bằng",
        coefficients={"cat_san_lap": 0.55, "da": 0.05},
        finish_applies=False,
        note=(
            "Chỉ vật liệu đắp nền, giả định chiều dày tôn nền trung bình ~50 cm. Chiều "
            "dày thực tế do cao độ thiết kế quyết định — đây là biến đổi mạnh nhất."
        ),
    ),
    "tuong_rao": ProjectType(
        key="tuong_rao",
        label="Tường rào",
        area_label="m² mặt tường",
        coefficients={
            "gach": 60.0,
            "xi_mang": 35.0,
            "cat": 0.12,
            "be_tong": 0.05,  # móng và giằng
            "thep": 4.0,
            "son": 0.45,
        },
        finish_applies=True,
        note=(
            "Tính theo DIỆN TÍCH MẶT TƯỜNG (dài × cao), không phải diện tích sàn. "
            "Tường rào 30 m dài, cao 2 m ⇒ nhập 60."
        ),
    ),
    "via_he_lat_gach": ProjectType(
        key="via_he_lat_gach",
        label="Vỉa hè / sân lát gạch",
        area_label="m² mặt bằng",
        coefficients={
            "gach_lat": 1.05,
            "be_tong": 0.08,
            "xi_mang": 25.0,
            "cat": 0.10,
            "da": 0.08,
        },
        finish_applies=False,
        note="Lát gạch terrazzo/block trên lớp bê tông lót và lớp cát đệm.",
    ),
    "cai_tao": ProjectType(
        key="cai_tao",
        label="Cải tạo / sửa chữa (không đụng kết cấu chính)",
        area_label="m² sàn cải tạo",
        coefficients={
            "gach": 25.0,
            "xi_mang": 35.0,
            "cat": 0.12,
            "son": 0.50,
            "gach_lat": 0.70,
        },
        finish_applies=True,
        note=(
            "Giả định giữ nguyên khung kết cấu: chỉ xây/đập tường ngăn, trát, lát và "
            "sơn lại. Không tính bê tông/cốt thép vì không can thiệp kết cấu."
        ),
    ),
}

DEFAULT_PROJECT_TYPE = "nha_pho"


def get_project_type(key: str | None) -> ProjectType:
    return PROJECT_TYPES.get(key or DEFAULT_PROJECT_TYPE, PROJECT_TYPES[DEFAULT_PROJECT_TYPE])
