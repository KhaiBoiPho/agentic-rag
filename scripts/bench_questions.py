"""The 30-question Agentic benchmark set.

Every expected value here was read out of `material_prices` on the project's
own data, not written from memory — see docs/bo-cau-hoi-benchmark.md for the
question-by-question rationale and the SQL each answer was checked against.

Grading fields, all optional except `question`:

  expect_values   ints; the answer must state at least one of them. Several
                  are allowed because one product legitimately has more than
                  one published price (tại mỏ vs tại chân công trình).
  expect_text     substrings that must ALL appear (accent/case-insensitive).
  forbid          substrings that must NOT appear — this is where the
                  wrong-but-plausible neighbour goes (Hạ Long for Hà Tiên,
                  a Đà Nẵng price for a Hà Nội question).
  expect_tool     tool that must have been called.
  expect_refusal  the answer must say it has no data. Used for questions
                  whose subject is genuinely absent from the corpus; a system
                  that invents a number here is worse than one that fails.
  history         prior turns, for follow-up questions that only make sense
                  in context.

Tiers run hard -> easy:
  T1 nhiễu     the asked-for thing does not exist, or exists only as a
               near-miss neighbour. Tests refusal and disambiguation.
  T2 suy luận  needs more than one lookup, or a unit/region conversion.
  T3 tiếp nối  meaning depends on the previous turn.
  T4 tra cứu   one product, one price, but awkwardly named.
  T5 trực tiếp the name in the question matches the stored name closely.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Q:
    qid: str
    tier: str
    question: str
    expect_values: list[int] = field(default_factory=list)
    expect_text: list[str] = field(default_factory=list)
    forbid: list[str] = field(default_factory=list)
    expect_tool: str = ""
    expect_refusal: bool = False
    history: list[dict] = field(default_factory=list)
    note: str = ""


QUESTIONS: list[Q] = []

# ── T1 · nhiễu — thứ được hỏi không tồn tại, hoặc chỉ có hàng xóm gần giống ──
# Mức khó nhất, vì phần thưởng cho việc "cứ trả lời đại" ở đây rất cao: một
# model chịu bịa sẽ trông giỏi ở mọi mức khác và chỉ lộ ra ở mức này.

QUESTIONS += [
    Q(
        "B01", "T1",
        "Mỏ đá Thanh Tâm ở Đà Nẵng báo giá đá 1x2 bao nhiêu một khối?",
        expect_refusal=True,
        note="Không có nhà cung cấp nào tên Thanh Tâm trong corpus (0 dòng), "
             "trong khi đá 1x2 thì có rất nhiều — nên rất dễ trả lời giá của "
             "một mỏ khác rồi gán cho Thanh Tâm. Đây đúng là câu người dùng "
             "đã thấy hệ thống trả lời sai.",
    ),
    Q(
        "B02", "T1",
        "Giá xi măng Bút Sơn PCB50 ở Hà Nội là bao nhiêu một tấn?",
        expect_refusal=True,
        forbid=["1.140.000", "1.120.000"],
        note="Bút Sơn chỉ có PCB30 và PCB40. Bẫy kép: mác PCB50 CÓ THẬT trong "
             "corpus (Vicem Hạ Long, FICO — đều ở TPHCM), nên model dễ kết "
             "luận 'PCB50 có tồn tại' rồi lấy giá Bút Sơn PCB40 gán vào.",
    ),
    Q(
        "B03", "T1",
        "Cáp điện CXV-500 0,6/1kV ở Đà Nẵng giá bao nhiêu một mét?",
        expect_refusal=True,
        forbid=["489.400"],
        note="CXV-150 có thật (489.400 đ/m), CXV-500 thì không. Khớp theo từ "
             "rất dễ trượt sang CXV-150 vì chung tiền tố.",
    ),
    Q(
        "B04", "T1",
        "Ở Đà Nẵng, đá mi sàng giá bao nhiêu một m3?",
        expect_values=[381818],
        note="Ngược lại với B01–B03: thứ được hỏi CÓ THẬT ('Đá mi sàng "
             "(0,5-1)', 381.818 đ/m3) nhưng nằm lẫn giữa 20 dòng 'đá mi' "
             "khác giá. Từ chối ở đây cũng là sai.",
    ),
    Q(
        "B05", "T1",
        "Giá thép thanh vằn Việt Nhật D12 ở Hà Nội bao nhiêu một kg?",
        expect_values=[15360, 15460, 15620, 15920, 16020, 16400],
        forbid=["vách kính", "cửa sổ", "cửa đi"],
        note="Trong corpus 'Việt Nhật' là thương hiệu KÍNH (kính 6.38mm Việt "
             "Nhật), không phải thép — nên câu này từng được trả lời bằng một "
             "tấm vách kính. Đáp án đúng: bỏ qua thương hiệu không khớp, trả "
             "giá thép thanh vằn D12 thật.",
    ),
    Q(
        "B06", "T1",
        "Xi măng Vicem Hạ Long ở TPHCM giá bao nhiêu một tấn?",
        expect_values=[1175926, 1259259, 1268519, 1314815],
        forbid=["Hà Tiên"],
        note="Bẫy hàng xóm: TPHCM có 44 dòng Vicem *Hà Tiên* và chỉ 6 dòng "
             "*Hạ Long*. pg_trgm từng xếp 'Hạ Long' 0,742 trên 'Hà Tiên' "
             "0,741 — đúng một phần nghìn, và trả về sai sản phẩm.",
    ),
]

# ── T2 · suy luận — cần nhiều lượt tra, hoặc một phép quy đổi ──

QUESTIONS += [
    Q(
        "B07", "T2",
        "Ở Hà Nội, xi măng bao Bút Sơn Xanh đa dụng PCB40 đắt hơn PCB30 bao "
        "nhiêu tiền một tấn?",
        expect_values=[20000],
        expect_tool="lookup_material_price",
        note="1.140.000 − 1.120.000. Hai lượt tra rồi trừ; sai một trong hai "
             "giá là ra hiệu số sai, nên kết quả kiểm chứng được chính xác.",
    ),
    Q(
        "B08", "T2",
        "Ở Đà Nẵng, đá cấp phối Dmax 25 và Dmax 37,5 của Công ty TNHH Xây "
        "dựng và Phát triển nông thôn Đại Lộc, loại nào rẻ hơn và giá bao "
        "nhiêu một m3?",
        expect_values=[283636],
        expect_tool="lookup_material_price",
        note="Chính là hai dòng từng mang giá bịa 7 đ/m3 do lưới bảng khuyết "
             "(nay là 298.182 và 283.636). Nêu rõ nhà cung cấp để câu hỏi có "
             "đúng một đáp án, vì mỗi mỏ báo một giá khác nhau. Câu hỏi phải "
             "đòi cả GIÁ chứ không chỉ 'loại nào rẻ hơn' — nếu không, một câu "
             "trả lời đúng nghĩa ('Dmax 37,5 rẻ hơn') vẫn bị bộ chấm dựa trên "
             "con số đánh trượt, tức thước đo khắt khe hơn câu chữ.",
    ),
    Q(
        "B09", "T2",
        "Một tấn xi măng Bút Sơn Xanh đa dụng PCB40 ở Hà Nội giá bao nhiêu, "
        "và quy ra một bao 50kg thì bao nhiêu tiền?",
        expect_values=[57000],
        expect_tool="lookup_material_price",
        note="1.140.000 ÷ 20. Kiểm tra model có giữ đúng đơn vị khi quy đổi, "
             "hay chia bừa cho 50.",
    ),
    Q(
        "B10", "T2",
        "Xi măng PCB40 ở Hà Nội hay ở TPHCM đắt hơn?",
        expect_tool="lookup_material_price",
        note="Hai vùng, hai lượt tra. Bẫy: lấy giá vùng này gán cho vùng kia. "
             "Không chốt giá trị vì mỗi vùng có hàng chục dòng PCB40.",
    ),
    Q(
        "B11", "T2",
        "Đổ 12 m3 bê tông mác 250 thì cần bao nhiêu xi măng, cát và đá?",
        expect_tool="estimate_material_quantity",
        note="Phải chọn công cụ khối lượng, không phải công cụ giá — câu hỏi "
             "không hề nhắc tới tiền.",
    ),
    Q(
        "B12", "T2",
        "Xây nhà phố 100 m2 sàn ở Hà Nội, hoàn thiện cơ bản thì hết khoảng "
        "bao nhiêu tiền vật liệu?",
        expect_tool="calculate_construction_cost",
        note="Phải chọn công cụ dự toán và suy ra project_type='nha_pho', "
             "finish_level='hoan_thien_co_ban' từ câu chữ.",
    ),
]

# ── T3 · tiếp nối — câu hỏi chỉ có nghĩa khi đọc cùng lượt trước ──

_H_XM_HN = [
    {
        "role": "user",
        "content": "Giá xi măng Bút Sơn Xanh đa dụng PCB40 ở Hà Nội bao nhiêu một tấn?",
    },
    {
        "role": "assistant",
        "content": (
            "Xi măng bao Bút Sơn Xanh đa dụng PCB40 ở Hà Nội có giá "
            "1.140.000 đ/tấn (chưa VAT)."
        ),
    },
]

QUESTIONS += [
    Q(
        "B13", "T3", "còn ở TPHCM thì sao?",
        history=_H_XM_HN,
        expect_refusal=True,
        forbid=["1.140.000"],
        note="Bút Sơn chỉ có ở bảng giá Hà Nội (8 dòng, 0 dòng ở TPHCM). Câu "
             "này đòi hai việc cùng lúc: hiểu 'còn ở ... thì sao' đang nói về "
             "vật liệu nào, RỒI thừa nhận không có dữ liệu — thay vì nhắc lại "
             "giá Hà Nội như thể là giá TPHCM.",
    ),
    Q(
        "B14", "T3", "loại PCB30 thì bao nhiêu?",
        history=_H_XM_HN,
        expect_values=[1100000, 1120000],
        expect_tool="lookup_material_price",
        note="Giữ nguyên vùng và thương hiệu từ lượt trước, chỉ đổi mác.",
    ),
    Q(
        "B15", "T3", "vậy mua 5 tấn hết bao nhiêu tiền?",
        history=_H_XM_HN,
        expect_values=[5700000],
        note="1.140.000 × 5. Phép nhân thuần tuý từ ngữ cảnh — không cần tra "
             "lại, nên đo được model có giữ được con số vừa nói hay không.",
    ),
    Q(
        "B16", "T3", "còn ở Đà Nẵng có bán loại đó không?",
        history=_H_XM_HN,
        expect_refusal=True,
        note="Bút Sơn là xi măng miền Bắc; bảng giá Đà Nẵng không có dòng nào.",
    ),
    Q(
        "B17", "T3", "cái nào rẻ nhất trong mấy loại vừa kể?",
        history=[
            {
                "role": "user",
                "content": "Ở Đà Nẵng có những loại đá cấp phối Dmax nào?",
            },
            {
                "role": "assistant",
                "content": "Có đá cấp phối Dmax 25 và đá cấp phối Dmax 37,5.",
            },
        ],
        expect_tool="lookup_material_price",
        note="Phải tra lại giá của cả hai rồi so sánh, không được đoán từ "
             "chính câu trả lời trước (vốn không hề nêu giá).",
    ),
]

# ── T4 · tra cứu — một giá, nhưng tên hỏi lệch với tên lưu ──

QUESTIONS += [
    Q("B18", "T4", "Cáp vặn xoắn LV-ABC-4x95 ở Đà Nẵng giá bao nhiêu một mét?",
      expect_values=[121000], expect_tool="lookup_material_price",
      note="Mã sản phẩm có gạch nối và chữ số dính nhau; tên lưu là "
           "'LV-ABC-4x95 - 0,6/1kV'."),
    Q("B19", "T4", "Cửa sổ nhôm hệ Topal XFAD ở Hà Nội giá bao nhiêu m2?",
      expect_values=[1809338, 2515002, 2698310, 2954238, 3358761, 3526629,
                     3837928, 3945900],
      expect_tool="lookup_material_price",
      note="Tên lưu dài hơn 150 ký tự (kèm kích thước, loại kính, phụ kiện); "
           "câu hỏi chỉ nêu 3 từ khoá."),
    Q("B20", "T4", "Ống luồn tròn PVC H.SERIES phi 25 ở Đà Nẵng giá bao "
                   "nhiêu một cây?",
      expect_values=[43200], expect_tool="lookup_material_price",
      note="Tên có dấu chấm giữa từ ('H.SERIES') — dễ bị bộ tách từ cắt sai."),
    Q("B21", "T4", "Nối trơn phi 16 ở Đà Nẵng giá bao nhiêu một cái?",
      expect_values=[700], expect_tool="lookup_material_price",
      note="Giá thật chỉ 700 đ. Đây là ca kiểm tra ngược cho bộ lọc 'giá phi "
           "lý': một ngưỡng chặn dưới đặt ngây thơ sẽ cắt nhầm dòng đúng này."),
    Q("B22", "T4", "Cấp phối A Dmax25 ở Đà Nẵng giá bao nhiêu một m3?",
      expect_values=[298182], expect_tool="lookup_material_price",
      note="Dòng từng bị lưới bảng khuyết làm hỏng thành 7 đ/m3 — giữ trong "
           "bộ đo để lỗi đó không quay lại mà không ai biết."),
    Q("B23", "T4", "Ống thoát uPVC D21 ở Đà Nẵng giá bao nhiêu một mét?",
      expect_refusal=True,
      note="uPVC có 478 dòng nhưng TOÀN BỘ ở Hà Nội. Bẫy vùng: sản phẩm có "
           "thật, chỉ là không có ở vùng được hỏi."),
    Q("B24", "T4", "Nhựa đường 60/70 ở Hà Nội giá bao nhiêu một kg?",
      expect_values=[18600], expect_tool="lookup_material_price",
      note="'60/70' là quy cách chứ không phải phân số; cạnh nó còn có "
           "'40/50' và '60/70 PG64' để trượt sang."),
]

# ── T5 · trực tiếp — tên hỏi khớp sát tên lưu ──

QUESTIONS += [
    Q("B25", "T5", "Giá xi măng bao Bút Sơn Xanh đa dụng PCB40 ở Hà Nội?",
      expect_values=[1140000], expect_tool="lookup_material_price"),
    Q("B26", "T5", "Giá cát san lấp ở TPHCM là bao nhiêu một khối?",
      expect_values=[400000, 450000], expect_tool="lookup_material_price"),
    Q("B27", "T5", "Giá đá 1x2 ở TPHCM bao nhiêu một m3?",
      expect_values=[730000, 780000], expect_tool="lookup_material_price"),
    Q("B28", "T5", "Giá thép thanh vằn D10 ở Hà Nội bao nhiêu một kg?",
      expect_values=[15560, 15660, 15820, 16220, 16550],
      expect_tool="lookup_material_price"),
    Q("B29", "T5", "Giá XM Vicem Hà Tiên PCB40 ở TPHCM bao nhiêu một tấn?",
      expect_values=[1268519, 1388889, 1407407, 1407408, 1444444, 1462963,
                     1495370, 1509259, 1527778, 1578704, 1583333, 1606481,
                     1615741, 1620370, 1629630, 1638889, 1648148, 1657407,
                     1703704, 1717593, 1726852, 1740741],
      expect_tool="lookup_material_price"),
    Q("B30", "T5", "Cáp điện CXV-150 0,6/1kV ở Đà Nẵng giá bao nhiêu một mét?",
      expect_values=[489400], expect_tool="lookup_material_price"),
]
