# Bộ câu hỏi benchmark cho chế độ Agentic

Bộ 30 câu hỏi dùng để đo chất lượng trả lời của chế độ **Agentic** (truy hồi
trên toàn bộ kho tri thức + gọi công cụ). Định nghĩa nằm ở
[`scripts/bench_questions.py`](../scripts/bench_questions.py); trình chạy ở
[`scripts/bench_agentic.py`](../scripts/bench_agentic.py); kết quả đo ở
[bao-cao-benchmark.md](bao-cao-benchmark.md).

---

## 1. Bộ câu hỏi này được thiết kế để làm gì

Không phải để cho ra điểm số đẹp. Nó được dựng từ **những câu hỏi hệ thống
đã thực sự trả lời sai**, cộng thêm các biến thể cùng dạng. Mục tiêu là mỗi
câu hỏi phải **phân biệt được** hai hệ thống khác nhau — một câu mà mọi cấu
hình đều đúng, hoặc mọi cấu hình đều sai, không mang thông tin gì.

Ba nguyên tắc:

**1. Đáp án phải kiểm chứng được bằng máy.**
Mọi giá trị kỳ vọng đều đọc trực tiếp từ bảng `material_prices` bằng
[`scripts/bench_ground.py`](../scripts/bench_ground.py), không viết theo trí
nhớ. Không dùng LLM chấm điểm, vì một model chấm điểm sẽ đưa phương sai của
chính nó vào phép đo vốn để so sánh các model.

**2. "Không biết" là một đáp án đúng, và phải được chấm điểm như vậy.**
Một phần bộ câu hỏi hỏi về thứ **không tồn tại** trong dữ liệu. Hệ thống bịa
ra một con số ở đó thì **tệ hơn** hệ thống nói không có — vì con giá bịa sẽ
đi thẳng vào một bản dự toán. Những câu đó chấm bằng `expect_refusal`.

**3. Sai kiểu "gần đúng" phải bị bắt.**
Trường `forbid` chứa **câu trả lời sai nhưng nghe hợp lý** — thương hiệu
hàng xóm (Hạ Long thay vì Hà Tiên), giá của vùng khác, mác xi măng kế bên
(PCB30 thay vì PCB40). Đây là kiểu sai nguy hiểm nhất vì nó không có dấu
hiệu bất thường nào.

## 2. Năm mức độ khó

| mức | tên | phép thử | số câu |
|---|---|---|---:|
| **T1** | nhiễu | thứ được hỏi không tồn tại, hoặc chỉ tồn tại dưới dạng hàng xóm gần giống | 6 |
| **T2** | suy luận | cần nhiều hơn một lượt tra, hoặc một phép quy đổi đơn vị/vùng | 6 |
| **T3** | tiếp nối | câu hỏi chỉ có nghĩa khi đọc cùng lượt trước | 5 |
| **T4** | tra cứu | một sản phẩm, một giá — nhưng tên gọi trong câu hỏi lệch với tên lưu | 7 |
| **T5** | trực tiếp | tên trong câu hỏi khớp sát tên lưu | 6 |

Thang này xếp theo **cái gì có thể hỏng**, chứ không theo độ dài câu hỏi:

- **T5** hỏng khi khớp tên hỏng.
- **T4** hỏng khi khớp tên không chịu được cách gọi khác (viết tắt, thiếu
  dấu, mã sản phẩm dính liền).
- **T3** hỏng khi bước cô đọng ngữ cảnh (condense follow-up) hỏng.
- **T2** hỏng khi model không chịu gọi công cụ nhiều lần, hoặc cộng trừ sai.
- **T1** hỏng khi model chọn "trả lời cho có" thay vì nói không có dữ liệu.

## 3. Cách chấm

Chấm hoàn toàn tất định, theo thứ tự — **sai số bị báo trước sai công cụ**,
vì một con số sai tệ hơn một quy trình sai:

| trường | ý nghĩa | chấm trượt khi |
|---|---|---|
| `expect_values` | tập số hợp lệ (một sản phẩm có thể có nhiều giá công bố hợp lệ: tại mỏ / tại chân công trình) | câu trả lời không nêu số nào trong tập |
| `forbid` | chuỗi **không được** xuất hiện | xuất hiện |
| `expect_text` | chuỗi phải xuất hiện đủ | thiếu bất kỳ chuỗi nào |
| `expect_tool` | công cụ phải được gọi | không gọi |
| `expect_refusal` | phải nói không có dữ liệu | trả lời như thể có |

So sánh số **bỏ mọi dấu phân cách**, nên `1.140.000`, `1,140,000` và
`1 140 000` được coi là một. So sánh chữ **bỏ dấu tiếng Việt và không phân
biệt hoa thường**, nên "Bút Sơn" và "But Son" đều được chấp nhận.

---

## 4. Danh sách 30 câu hỏi

### T1 · nhiễu — thứ được hỏi không tồn tại, hoặc chỉ có hàng xóm gần giống

**B01** — Mỏ đá Thanh Tâm ở Đà Nẵng báo giá đá 1x2 bao nhiêu một khối?

- *đạt khi:* **phải nói không có dữ liệu**
- *vì sao có câu này:* Không có nhà cung cấp nào tên Thanh Tâm trong corpus (0 dòng), trong khi đá 1x2 thì có rất nhiều — nên rất dễ trả lời giá của một mỏ khác rồi gán cho Thanh Tâm. Đây đúng là câu người dùng đã thấy hệ thống trả lời sai.

**B02** — Giá xi măng Bút Sơn PCB50 ở Hà Nội là bao nhiêu một tấn?

- *đạt khi:* **phải nói không có dữ liệu**; không được chứa `1.140.000`, `1.120.000`
- *vì sao có câu này:* Bút Sơn chỉ có PCB30 và PCB40. Bẫy kép: mác PCB50 CÓ THẬT trong corpus (Vicem Hạ Long, FICO — đều ở TPHCM), nên model dễ kết luận 'PCB50 có tồn tại' rồi lấy giá Bút Sơn PCB40 gán vào.

**B03** — Cáp điện CXV-500 0,6/1kV ở Đà Nẵng giá bao nhiêu một mét?

- *đạt khi:* **phải nói không có dữ liệu**; không được chứa `489.400`
- *vì sao có câu này:* CXV-150 có thật (489.400 đ/m), CXV-500 thì không. Khớp theo từ rất dễ trượt sang CXV-150 vì chung tiền tố.

**B04** — Ở Đà Nẵng, đá mi sàng giá bao nhiêu một m3?

- *đạt khi:* nêu được `381.818`
- *vì sao có câu này:* Ngược lại với B01–B03: thứ được hỏi CÓ THẬT ('Đá mi sàng (0,5-1)', 381.818 đ/m3) nhưng nằm lẫn giữa 20 dòng 'đá mi' khác giá. Từ chối ở đây cũng là sai.

**B05** — Giá thép thanh vằn Việt Nhật D12 ở Hà Nội bao nhiêu một kg?

- *đạt khi:* nêu được `15.360` hoặc `15.460` hoặc `15.620` hoặc `15.920` hoặc `16.020` hoặc `16.400`; không được chứa `vách kính`, `cửa sổ`, `cửa đi`
- *vì sao có câu này:* Trong corpus 'Việt Nhật' là thương hiệu KÍNH (kính 6.38mm Việt Nhật), không phải thép — nên câu này từng được trả lời bằng một tấm vách kính. Đáp án đúng: bỏ qua thương hiệu không khớp, trả giá thép thanh vằn D12 thật.

**B06** — Xi măng Vicem Hạ Long ở TPHCM giá bao nhiêu một tấn?

- *đạt khi:* nêu được `1.175.926` hoặc `1.259.259` hoặc `1.268.519` hoặc `1.314.815`; không được chứa `Hà Tiên`
- *vì sao có câu này:* Bẫy hàng xóm: TPHCM có 44 dòng Vicem *Hà Tiên* và chỉ 6 dòng *Hạ Long*. pg_trgm từng xếp 'Hạ Long' 0,742 trên 'Hà Tiên' 0,741 — đúng một phần nghìn, và trả về sai sản phẩm.

### T2 · suy luận — cần nhiều lượt tra, hoặc một phép quy đổi

**B07** — Ở Hà Nội, xi măng bao Bút Sơn Xanh đa dụng PCB40 đắt hơn PCB30 bao nhiêu tiền một tấn?

- *đạt khi:* nêu được `20.000`; gọi `lookup_material_price`
- *vì sao có câu này:* 1.140.000 − 1.120.000. Hai lượt tra rồi trừ; sai một trong hai giá là ra hiệu số sai, nên kết quả kiểm chứng được chính xác.

**B08** — Ở Đà Nẵng, đá cấp phối Dmax 25 và Dmax 37,5 của Công ty TNHH Xây dựng và Phát triển nông thôn Đại Lộc, loại nào rẻ hơn và giá bao nhiêu một m3?

- *đạt khi:* nêu được `283.636`; gọi `lookup_material_price`
- *vì sao có câu này:* Chính là hai dòng từng mang giá bịa 7 đ/m3 do lưới bảng khuyết (nay là 298.182 và 283.636). Nêu rõ nhà cung cấp để câu hỏi có đúng một đáp án, vì mỗi mỏ báo một giá khác nhau. Câu hỏi phải đòi cả GIÁ chứ không chỉ 'loại nào rẻ hơn' — nếu không, một câu trả lời đúng nghĩa ('Dmax 37,5 rẻ hơn') vẫn bị bộ chấm dựa trên con số đánh trượt, tức thước đo khắt khe hơn câu chữ.

**B09** — Một tấn xi măng Bút Sơn Xanh đa dụng PCB40 ở Hà Nội giá bao nhiêu, và quy ra một bao 50kg thì bao nhiêu tiền?

- *đạt khi:* nêu được `57.000`; gọi `lookup_material_price`
- *vì sao có câu này:* 1.140.000 ÷ 20. Kiểm tra model có giữ đúng đơn vị khi quy đổi, hay chia bừa cho 50.

**B10** — Xi măng PCB40 ở Hà Nội hay ở TPHCM đắt hơn?

- *đạt khi:* gọi `lookup_material_price`
- *vì sao có câu này:* Hai vùng, hai lượt tra. Bẫy: lấy giá vùng này gán cho vùng kia. Không chốt giá trị vì mỗi vùng có hàng chục dòng PCB40.

**B11** — Đổ 12 m3 bê tông mác 250 thì cần bao nhiêu xi măng, cát và đá?

- *đạt khi:* gọi `estimate_material_quantity`
- *vì sao có câu này:* Phải chọn công cụ khối lượng, không phải công cụ giá — câu hỏi không hề nhắc tới tiền.

**B12** — Xây nhà phố 100 m2 sàn ở Hà Nội, hoàn thiện cơ bản thì hết khoảng bao nhiêu tiền vật liệu?

- *đạt khi:* gọi `calculate_construction_cost`
- *vì sao có câu này:* Phải chọn công cụ dự toán và suy ra project_type='nha_pho', finish_level='hoan_thien_co_ban' từ câu chữ.

### T3 · tiếp nối — câu hỏi chỉ có nghĩa cùng lượt trước

**B13** — còn ở TPHCM thì sao?

> *lượt trước:* Giá xi măng Bút Sơn Xanh đa dụng PCB40 ở Hà Nội bao nhiêu một tấn?

- *đạt khi:* **phải nói không có dữ liệu**; không được chứa `1.140.000`
- *vì sao có câu này:* Bút Sơn chỉ có ở bảng giá Hà Nội (8 dòng, 0 dòng ở TPHCM). Câu này đòi hai việc cùng lúc: hiểu 'còn ở ... thì sao' đang nói về vật liệu nào, RỒI thừa nhận không có dữ liệu — thay vì nhắc lại giá Hà Nội như thể là giá TPHCM.

**B14** — loại PCB30 thì bao nhiêu?

> *lượt trước:* Giá xi măng Bút Sơn Xanh đa dụng PCB40 ở Hà Nội bao nhiêu một tấn?

- *đạt khi:* nêu được `1.100.000` hoặc `1.120.000`; gọi `lookup_material_price`
- *vì sao có câu này:* Giữ nguyên vùng và thương hiệu từ lượt trước, chỉ đổi mác.

**B15** — vậy mua 5 tấn hết bao nhiêu tiền?

> *lượt trước:* Giá xi măng Bút Sơn Xanh đa dụng PCB40 ở Hà Nội bao nhiêu một tấn?

- *đạt khi:* nêu được `5.700.000`
- *vì sao có câu này:* 1.140.000 × 5. Phép nhân thuần tuý từ ngữ cảnh — không cần tra lại, nên đo được model có giữ được con số vừa nói hay không.

**B16** — còn ở Đà Nẵng có bán loại đó không?

> *lượt trước:* Giá xi măng Bút Sơn Xanh đa dụng PCB40 ở Hà Nội bao nhiêu một tấn?

- *đạt khi:* **phải nói không có dữ liệu**
- *vì sao có câu này:* Bút Sơn là xi măng miền Bắc; bảng giá Đà Nẵng không có dòng nào.

**B17** — cái nào rẻ nhất trong mấy loại vừa kể?

> *lượt trước:* Ở Đà Nẵng có những loại đá cấp phối Dmax nào?

- *đạt khi:* gọi `lookup_material_price`
- *vì sao có câu này:* Phải tra lại giá của cả hai rồi so sánh, không được đoán từ chính câu trả lời trước (vốn không hề nêu giá).

### T4 · tra cứu — một giá, nhưng tên hỏi lệch với tên lưu

**B18** — Cáp vặn xoắn LV-ABC-4x95 ở Đà Nẵng giá bao nhiêu một mét?

- *đạt khi:* nêu được `121.000`; gọi `lookup_material_price`
- *vì sao có câu này:* Mã sản phẩm có gạch nối và chữ số dính nhau; tên lưu là 'LV-ABC-4x95 - 0,6/1kV'.

**B19** — Cửa sổ nhôm hệ Topal XFAD ở Hà Nội giá bao nhiêu m2?

- *đạt khi:* nêu được `1.809.338` hoặc `2.515.002` hoặc `2.698.310` hoặc `2.954.238` hoặc `3.358.761` hoặc `3.526.629` hoặc `3.837.928` hoặc `3.945.900`; gọi `lookup_material_price`
- *vì sao có câu này:* Tên lưu dài hơn 150 ký tự (kèm kích thước, loại kính, phụ kiện); câu hỏi chỉ nêu 3 từ khoá.

**B20** — Ống luồn tròn PVC H.SERIES phi 25 ở Đà Nẵng giá bao nhiêu một cây?

- *đạt khi:* nêu được `43.200`; gọi `lookup_material_price`
- *vì sao có câu này:* Tên có dấu chấm giữa từ ('H.SERIES') — dễ bị bộ tách từ cắt sai.

**B21** — Nối trơn phi 16 ở Đà Nẵng giá bao nhiêu một cái?

- *đạt khi:* nêu được `700`; gọi `lookup_material_price`
- *vì sao có câu này:* Giá thật chỉ 700 đ. Đây là ca kiểm tra ngược cho bộ lọc 'giá phi lý': một ngưỡng chặn dưới đặt ngây thơ sẽ cắt nhầm dòng đúng này.

**B22** — Cấp phối A Dmax25 ở Đà Nẵng giá bao nhiêu một m3?

- *đạt khi:* nêu được `298.182`; gọi `lookup_material_price`
- *vì sao có câu này:* Dòng từng bị lưới bảng khuyết làm hỏng thành 7 đ/m3 — giữ trong bộ đo để lỗi đó không quay lại mà không ai biết.

**B23** — Ống thoát uPVC D21 ở Đà Nẵng giá bao nhiêu một mét?

- *đạt khi:* **phải nói không có dữ liệu**
- *vì sao có câu này:* uPVC có 478 dòng nhưng TOÀN BỘ ở Hà Nội. Bẫy vùng: sản phẩm có thật, chỉ là không có ở vùng được hỏi.

**B24** — Nhựa đường 60/70 ở Hà Nội giá bao nhiêu một kg?

- *đạt khi:* nêu được `18.600`; gọi `lookup_material_price`
- *vì sao có câu này:* '60/70' là quy cách chứ không phải phân số; cạnh nó còn có '40/50' và '60/70 PG64' để trượt sang.

### T5 · trực tiếp — tên hỏi khớp sát tên lưu

**B25** — Giá xi măng bao Bút Sơn Xanh đa dụng PCB40 ở Hà Nội?

- *đạt khi:* nêu được `1.140.000`; gọi `lookup_material_price`

**B26** — Giá cát san lấp ở TPHCM là bao nhiêu một khối?

- *đạt khi:* nêu được `400.000` hoặc `450.000`; gọi `lookup_material_price`

**B27** — Giá đá 1x2 ở TPHCM bao nhiêu một m3?

- *đạt khi:* nêu được `730.000` hoặc `780.000`; gọi `lookup_material_price`

**B28** — Giá thép thanh vằn D10 ở Hà Nội bao nhiêu một kg?

- *đạt khi:* nêu được `15.560` hoặc `15.660` hoặc `15.820` hoặc `16.220` hoặc `16.550`; gọi `lookup_material_price`

**B29** — Giá XM Vicem Hà Tiên PCB40 ở TPHCM bao nhiêu một tấn?

- *đạt khi:* nêu được `1.268.519` hoặc `1.388.889` hoặc `1.407.407` hoặc `1.407.408` hoặc `1.444.444` hoặc `1.462.963` hoặc `1.495.370` hoặc `1.509.259` hoặc `1.527.778` hoặc `1.578.704` hoặc `1.583.333` hoặc `1.606.481` hoặc `1.615.741` hoặc `1.620.370` hoặc `1.629.630` hoặc `1.638.889` hoặc `1.648.148` hoặc `1.657.407` hoặc `1.703.704` hoặc `1.717.593` hoặc `1.726.852` hoặc `1.740.741`; gọi `lookup_material_price`

**B30** — Cáp điện CXV-150 0,6/1kV ở Đà Nẵng giá bao nhiêu một mét?

- *đạt khi:* nêu được `489.400`; gọi `lookup_material_price`
