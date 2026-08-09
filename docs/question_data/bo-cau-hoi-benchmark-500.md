# Bộ 500 câu hỏi benchmark sinh từ `material_prices`

Sinh bởi [`scripts/gen_benchmark_from_db.py`](../scripts/gen_benchmark_from_db.py) với `--kind mixed --n 500 --seed 20260804`, nên chạy lại ra đúng bộ này.


> **Không thay** [bộ 30 câu viết tay](bo-cau-hoi-benchmark.md). Bộ đó dựng từ
> lỗi hệ thống đã THỰC SỰ mắc và là nơi **duy nhất** đo được việc từ chối và gọi
> công cụ. Bộ này là bộ **phủ**; bộ kia là bộ **khó**. Báo cáo cả hai.

> **Thay thế bộ 200 câu tiền nhiệm.** Các phép đo ở Phần V–VII của
> [bao-cao-benchmark.md](bao-cao-benchmark.md) chạy trên bộ đó — chỉ có câu tra
> giá, và bao gồm cả nguồn `.md`. Bộ này thêm **248 câu hỏi cấu trúc** và **chỉ
> lấy dữ liệu từ PDF**, nên số của hai bộ **không so trực tiếp** được.


## 1. Vì sao sinh máy

Bộ viết tay có hai giới hạn mà thêm câu viết tay không chữa được:

- **Chỉ ~11/30 câu mang thông tin** — 19 câu cho kết quả giống hệt nhau ở mọi
  cấu hình nên không phân biệt được gì.
- **Đáp án phải rà tay sau mỗi lần nạp lại corpus.** `bench_ground.py` chỉ IN RA,
  không tự sửa; một giá trị kỳ vọng sai sẽ âm thầm làm hỏng phép đo.

Sinh từ database giải cả hai: đáp án **chính là dòng được lấy ra**, và cỡ mẫu
muốn bao nhiêu cũng được. Ở n=500, sai số chuẩn là **±2,2 điểm** — đủ để
phát hiện chênh lệch 5 điểm, thay vì ±3,5 điểm của bộ 200 câu.


## 2. Hai loại câu hỏi, và vì sao cần cả hai

| loại | số câu | đòi hỏi gì |
|---|---:|---|
| **tra giá** | 252 | chỉ cần **con số** nằm trong cửa sổ |
| **cấu trúc** | 248 | **bắt buộc** đọc được quan hệ hàng–cột |

Đây là điểm mấu chốt: câu tra giá **không đòi hỏi hiểu cấu trúc bảng**. Model chỉ
cần con số đúng xuất hiện đâu đó — không cần biết cột nào là giá, hàng nào thuộc
sản phẩm nào. Một bộ đo chỉ có câu tra giá vì thế **không đo được** thứ mà bảo
toàn cấu trúc bảng tuyên bố mang lại.

Câu hỏi về đơn vị, tiêu chuẩn, nhà sản xuất thì buộc phải đọc đúng ô ở đúng cột
của đúng hàng. Đo được trên bộ trước: khoảng cách giữa hai chiến lược chunking là
**15 điểm** ở câu tra giá nhưng **9,5 điểm** ở câu cấu trúc — hai loại câu cho hai
bức tranh khác nhau.


## 3. Tám trục, và hạn ngạch đặt theo độ tin cậy của nhãn

| trục | loại | biến dạng / cột hỏi | số câu | độ tin cậy nhãn |
|---|---|---|---:|---|
| **G1** | tra giá | tên nguyên như lưu | 63 | cao nhất — giá đã kiểm |
| **G2** | tra giá | bỏ dấu tiếng Việt | 63 | cao nhất |
| **G3** | tra giá | gãy mã (CXV-150 → CXV150) | 63 | cao nhất |
| **G4** | tra giá | rút gọn ~40% từ | 63 | cao nhất |
| **S3** | cấu trúc | tiêu chuẩn kỹ thuật | 100 | cao — đã lọc chỉ giữ TCVN/QCVN/IEC |
| **S2** | cấu trúc | nhà sản xuất | 80 | khá — tên tổ chức đủ hiếm |
| **S4** | cấu trúc | cơ sở giá | 40 | trung bình — chỉ 2 giá trị, đoán bừa trúng 50% |
| **S1** | cấu trúc | đơn vị tính | 28 | thấp nhất — nhiễu do giải ký hiệu lặp sai |

**Mỗi biến thể chỉ lấy từ nhóm nó có tác dụng.** Gán vòng tròn là sai một cách
âm thầm: tên không dấu thì G2 trả lại chuỗi cũ, tên không mã thì G3 cũng vậy —
câu đó mang nhãn G2/G3 nhưng thực chất là G1, pha loãng đúng trục cần đo.


## 4. Chỉ lấy dữ liệu từ PDF

File `.md` đi qua `TextChunker` nên **mọi chunk là `ChunkType.TEXT`** — không có
`<table>` HTML, không `_resolve_header`, không `add_table_context`. Chúng không đi
qua tầng xử lý bảng nào, nên đưa vào một bộ đo về **chunking bảng** là thêm nhiễu
chứ không thêm thông tin. Đo được: **578/2.054 chunk** của corpus đến từ `.md`.

Hệ quả: nguồn giá TPHCM chủ yếu nằm trong markdown, nên sau khi lọc HCM chỉ còn
**38 dòng / 21 tên** — quá ít làm một tầng riêng. Bộ này phân tầng trên **Hà Nội**
và **Đà Nẵng**.


## 5. Cách chấm

| loại | trường chấm | ghi chú |
|---|---|---|
| tra giá | `expect_values` | trung bình **1.1** giá hợp lệ mỗi câu |
| cấu trúc | `expect_text` | đáp án là một **nhãn đọc ra từ bảng**, không phải số |

Câu tra giá mang **mọi** đơn giá của cặp (tên, vùng) đó. Chốt đúng một con số sẽ
chấm trượt một câu trả lời đúng chỉ vì nó chọn nhà cung cấp khác — một tên trong
một vùng thường có nhiều dòng giá hợp lệ.

Bộ chấm dùng chung với bộ viết tay (`bench_agentic.py:grade`), so số sau khi bỏ
mọi dấu phân cách, so chữ sau khi bỏ dấu tiếng Việt.


## 6. Bốn chốt chất lượng

1. **Tên dài quá bị loại** (>90 ký tự) — có dòng dài 300+ ký tự gồm
   quy cách, phụ kiện và điều kiện bảo hành dính liền.
2. **Tên chỉ có quy cách bị loại** — `Φ200 PN6`, `D710 x 27.2mm`; loại sản phẩm nằm
   ở hàng tiêu đề nhóm chứ không ở ô tên. Đòi ít nhất 2 từ thuần chữ.
3. **Giá < 1,000 bị loại** — bộ chấm bắt mọi số nguyên, nên đơn giá 70 hay
   700 sẽ khớp nhầm với số thứ tự.
4. **Đơn vị được dọn** — bỏ tiền tố `đ/`, loại ký hiệu lặp chưa giải (`-`, `- - - -`).


## 7. Hạn chế

- **Không có câu phải-từ-chối.** Mọi câu đều có đáp án trong dữ liệu, nên bộ này
  **không đo được việc bịa số** — kiểu lỗi mà §4.1 xác định là nguy hiểm nhất. Một
  hệ thống luôn trả lời tự tin sẽ ăn điểm ở đây.
- **Không có câu cần gọi tool**, không tiếp nối, không suy luận nhiều bước.
- **Cách hỏi theo mẫu cố định.**
- **Nhóm S thừa hưởng lỗi trích xuất của chính cột nó hỏi** — ví dụ thật:
  `Mặt 1 lỗ cỡ L…` có đơn vị `"cuộn"` trong DB, sai so với tài liệu gốc. Nhãn sai
  làm trượt **cả hai nhánh như nhau** nên thêm nhiễu chứ không thêm thiên lệch.
- **Đáp án đúng theo cấu tạo, nhưng chỉ với corpus hiện tại.** Nạp lại thì sinh lại.


## 8. Danh sách 500 câu


### G1 · tra giá — tên nguyên như lưu (63 câu)

| mã | câu hỏi | đáp án | tên lưu trong DB |
|---|---|---|---|
| Q015 | Giá Vonta - VT14D/220w - DIM - S - (VT33-PG33) ở Hà Nội là bao nhiêu một cái? | 15.100.000 | tên lưu: Vonta - VT14D/220w - DIM - S - (VT33-PG33) |
| Q022 | Giá Ống HDPE PE100 DN110 PN6 ở Hà Nội là bao nhiêu một m? | 158.000 | tên lưu: Ống HDPE PE100 DN110 PN6 |
| Q025 | Giá Cát san lấp ở TPHCM là bao nhiêu một m3? | 400.000, 450.000 | tên lưu: Cát san lấp |
| Q027 | Giá Tủ điện âm tường kim loại 4 đường ở Đà Nẵng là bao nhiêu một cái? | 116.000 | tên lưu: Tủ điện âm tường kim loại 4 đường |
| Q070 | Giá bộ sen cây nóng lạnh ba chức năng Prime mã PF2- SC205i ở Hà Nội là bao nhiêu một bộ? | 7.215.000 | tên lưu: bộ sen cây nóng lạnh ba chức năng Prime mã PF2- SC205i |
| Q098 | Giá Ống HDPE PE100 DN125 PN12.5 ở Hà Nội là bao nhiêu một m? | 377.700 | tên lưu: Ống HDPE PE100 DN125 PN12.5 |
| Q101 | Giá Vonta - VTL02/50w - DIM - S - (VT04-PG04) ở Hà Nội là bao nhiêu một cái? | 6.750.000 | tên lưu: Vonta - VTL02/50w - DIM - S - (VT04-PG04) |
| Q110 | Giá Băng cản nước PVC xử lý mạch ngừng bê tông - GPS ® Waterstop BO250(20m/ cuộn) ở Đà Nẵng là bao nhiêu một m? | 157.000 | tên lưu: Băng cản nước PVC xử lý mạch ngừng bê tông - GPS ® Waterstop BO250(20m/ cuộn) |
| Q115 | Giá DHP-STR15B 110W ở Đà Nẵng là bao nhiêu một bộ? | 10.605.000 | tên lưu: DHP-STR15B 110W |
| Q140 | Giá Ống HDPE PE100 DN140 PN8 ở Hà Nội là bao nhiêu một m? | 315.700 | tên lưu: Ống HDPE PE100 DN140 PN8 |
| Q141 | Giá Đèn đường Led KC-DL13B 100W, tiết giảm công suất 2-5 cấp ở Hà Nội là bao nhiêu một chiếc? | 5.950.000 | tên lưu: Đèn đường Led KC-DL13B 100W, tiết giảm công suất 2-5 cấp |
| Q147 | Giá Cát bê tông ở TPHCM là bao nhiêu một m3? | 450.000, 480.000 | tên lưu: Cát bê tông |
| Q148 | Giá Gạch rộng PT150R4(150x190x390)mm ở Đà Nẵng là bao nhiêu một viên? | 6.250, 6.640 | tên lưu: Gạch rộng PT150R4(150x190x390)mm |
| Q151 | Giá Tôn Seamlock G350, độ dày 0.50mm ở Hà Nội là bao nhiêu một m2? | 249.000, 267.000 | tên lưu: Tôn Seamlock G350, độ dày 0.50mm |
| Q164 | Giá Máng đèn batten Standardkit đuôi đèn oval 1 bóng 1.2m ở Đà Nẵng là bao nhiêu một bộ? | 131.000 | tên lưu: Máng đèn batten Standardkit đuôi đèn oval 1 bóng 1.2m |
| Q165 | Giá Khớp nối mềm cao su bích inox 304 Wonil - Hàn Quốc DN200 ở Hà Nội là bao nhiêu một cái? | 6.408.000 | tên lưu: Khớp nối mềm cao su bích inox 304 Wonil - Hàn Quốc DN200 |
| Q188 | Giá FL03C 201-300W I hiệu suất phát quang bộ đèn >120lm/W ở Đà Nẵng là bao nhiêu một bộ? | 12.223.000 | tên lưu: FL03C 201-300W I hiệu suất phát quang bộ đèn >120lm/W |
| Q191 | Giá Máng đèn gắn nổi chóa phản quang cao cấp -2*36 watt ở Đà Nẵng là bao nhiêu một bộ? | 786.000 | tên lưu: Máng đèn gắn nổi chóa phản quang cao cấp -2*36 watt |
| Q202 | Giá Đèn downlight gắn nổi 15 watt ở Đà Nẵng là bao nhiêu một bộ? | 177.000 | tên lưu: Đèn downlight gắn nổi 15 watt |
| Q218 | Giá Cầu dao tự động 15A SB-15 ở Hà Nội là bao nhiêu một cái? | 57.222 | tên lưu: Cầu dao tự động 15A SB-15 |
| Q221 | Giá Y lọc gang Wonil - Hàn Quốc DN250 ở Hà Nội là bao nhiêu một cái? | 22.225.600 | tên lưu: Y lọc gang Wonil - Hàn Quốc DN250 |
| Q234 | Giá MCB 1 cực 16A 6kA - Vonta ở Hà Nội là bao nhiêu một bộ? | 87.600 | tên lưu: MCB 1 cực 16A 6kA - Vonta |
| Q246 | Giá EPOGUARD PRIMER, PART A Sơn chống rỉ epoxy 02 thành phần (16L/thùng) ở Đà Nẵng là bao nhiêu một Thùng? | 4.575.000 | tên lưu: EPOGUARD PRIMER, PART A Sơn chống rỉ epoxy 02 thành phần (16L/thùng) |
| Q248 | Giá Ống HDPE PE100 DN1000 PN12.5 ở Hà Nội là bao nhiêu một m? | 25.546.400 | tên lưu: Ống HDPE PE100 DN1000 PN12.5 |
| Q249 | Giá Bóng đèn Compact xoắn lớn 7W ở Đà Nẵng là bao nhiêu một cái? | 75.500 | tên lưu: Bóng đèn Compact xoắn lớn 7W |
| Q256 | Giá Cột thép Bát giác, Tròn côn 10m D78-4mm ở Hà Nội là bao nhiêu một Cột? | 6.606.451 | tên lưu: Cột thép Bát giác, Tròn côn 10m D78-4mm |
| Q258 | Giá Cột thép Bát giác, Tròn côn 8m D78-3,5mm ở Hà Nội là bao nhiêu một Cột? | 4.797.419 | tên lưu: Cột thép Bát giác, Tròn côn 8m D78-3,5mm |
| Q264 | Giá SP FILLER bột bả tường nội thất ở Hà Nội là bao nhiêu một QCVN 4? | 13.725, 13.920 | tên lưu: SP FILLER bột bả tường nội thất |
| Q265 | Giá Trường hợp bơm cần nối ống ở Đà Nẵng là bao nhiêu một đợt? | 2.314.815 | tên lưu: Trường hợp bơm cần nối ống |
| Q267 | Giá Khớp nối ren phi 25 ở Đà Nẵng là bao nhiêu một cái? | 2.900 | tên lưu: Khớp nối ren phi 25 |
| Q278 | Giá Mặt viền cầu dao an tòan đơn trắng xi bạc ở Đà Nẵng là bao nhiêu một cái? | 17.200 | tên lưu: Mặt viền cầu dao an tòan đơn trắng xi bạc |
| Q288 | Giá Led pha 200W ánh sáng trắng (T)/ vàng (V) FLD5-200T/V ở Hà Nội là bao nhiêu một cái? | 2.639.630 | tên lưu: Led pha 200W ánh sáng trắng (T)/ vàng (V) FLD5-200T/V |
| Q289 | Giá măng sông ren trong HDPE DN20x3/4" ở Hà Nội là bao nhiêu một cái? | 12.200 | tên lưu: măng sông ren trong HDPE DN20x3/4" |
| Q303 | Giá Đèn LED HM SMD 121 Công suất 180W-250W - Hiệu suất phát quang ≥120Lm/W ở Hà Nội là bao nhiêu một bộ? | 6.250.000 | tên lưu: Đèn LED HM SMD 121 Công suất 180W-250W - Hiệu suất phát quang ≥120Lm/W |
| Q305 | Giá Cát xây tô ở TPHCM là bao nhiêu một m3? | 450.000, 480.000 | tên lưu: Cát xây tô |
| Q312 | Giá VCTF 3x0.7 ( bọc tròn ) ở Hà Nội là bao nhiêu một m? | 14.370 | tên lưu: VCTF 3x0.7 ( bọc tròn ) |
| Q313 | Giá Đèn chiếu sáng đường phố LED HERA, công suất 60W ở Hà Nội là bao nhiêu một bộ? | 6.450.000 | tên lưu: Đèn chiếu sáng đường phố LED HERA, công suất 60W |
| Q318 | Giá Sơn siêu chống thấm Lincoin 168 ở Đà Nẵng là bao nhiêu một thùng? | 1.800.000 | tên lưu: Sơn siêu chống thấm Lincoin 168 |
| Q319 | Giá Băng cản nước PVC xử lý mạch ngừng bê tông - GPS ® Waterstop V320,(20m/ cuộn) ở Đà Nẵng là bao nhiêu một m? | 204.000 | tên lưu: Băng cản nước PVC xử lý mạch ngừng bê tông - GPS ® Waterstop V320,(20m/ cuộn) |
| Q325 | Giá Máng đèn tán xạ lắp nổi 2 bóng 0.6m ở Đà Nẵng là bao nhiêu một bao gồm tăng? | 493.000 | tên lưu: Máng đèn tán xạ lắp nổi 2 bóng 0.6m |
| Q330 | Giá Sơn siêu bóng nội thất cao cấp (5 Lít/ lon) ở Đà Nẵng là bao nhiêu một lon? | 1.440.000 | tên lưu: Sơn siêu bóng nội thất cao cấp (5 Lít/ lon) |
| Q334 | Giá Chậu rửa treo tường Prime mã P05-006 WH 440x370x155 ở Hà Nội là bao nhiêu một chiếc? | 1.050.000 | tên lưu: Chậu rửa treo tường Prime mã P05-006 WH 440x370x155 |
| Q340 | Giá Van bướm tay gạt gang FAF 3500 DN50 ở Hà Nội là bao nhiêu một cái? | 1.680.000 | tên lưu: Van bướm tay gạt gang FAF 3500 DN50 |
| Q342 | Giá Ống nhựa PPR 1 lớp D25 PN20 ở Hà Nội là bao nhiêu một m? | 66.600 | tên lưu: Ống nhựa PPR 1 lớp D25 PN20 |
| Q349 | Giá Máng đèn huỳnh quang điện tử siêu mỏng đơn seri DT2 1x1.2m (Không bóng) ở Đà Nẵng là bao nhiêu một bộ? | 120.000 | tên lưu: Máng đèn huỳnh quang điện tử siêu mỏng đơn seri DT2 1x1.2m (Không bóng) |
| Q355 | Giá CXV/DSTA-4x25 - 0,6/1kV ở Đà Nẵng là bao nhiêu một XLPE, giáp? | 652.410 | tên lưu: CXV/DSTA-4x25 - 0,6/1kV |
| Q358 | Giá Thép CT3 hoặc C45, 4 Bulông M16, KT: (260x260x500)mm ở Đà Nẵng là bao nhiêu một cái? | 591.500 | tên lưu: Thép CT3 hoặc C45, 4 Bulông M16, KT: (260x260x500)mm |
| Q378 | Giá Đèn LED tube Điện Quang ĐQ LEDTU06I (1.2m 18W daylight/warmwhite thân thủy tinh) ở Đà Nẵng là bao nhiêu một cái? | 66.940 | tên lưu: Đèn LED tube Điện Quang ĐQ LEDTU06I (1.2m 18W daylight/warmwhite thân thủy tinh) |
| Q380 | Giá Cầu dao tự động MCB tép 1 pha 50A ở Đà Nẵng là bao nhiêu một cái? | 39.000 | tên lưu: Cầu dao tự động MCB tép 1 pha 50A |
| Q392 | Giá Máng đèn tán quang âm trần đôi 2x0.6m (Không bóng) ở Đà Nẵng là bao nhiêu một bộ? | 792.000 | tên lưu: Máng đèn tán quang âm trần đôi 2x0.6m (Không bóng) |
| Q405 | Giá Bộ mặt viền ổ đơn 2 chấu + 1 lỗ đơn trắng ở Đà Nẵng là bao nhiêu một cái? | 38.100 | tên lưu: Bộ mặt viền ổ đơn 2 chấu + 1 lỗ đơn trắng |
| Q409 | Giá Đèn led bulb công suất lớn Điện Quang ĐQ LEDBU09 (12W daylight/warmwhite) ở Đà Nẵng là bao nhiêu một cái? | 71.900 | tên lưu: Đèn led bulb công suất lớn Điện Quang ĐQ LEDBU09 (12W daylight/warmwhite) |
| Q422 | Giá Xi măng xây trát cao cấp (Thành Thắng, Thịnh Thành, Thịnh Vượng, Tiến Sơn) ở Hà Nội là bao nhiêu một tấn? | 1.150.000 | tên lưu: Xi măng xây trát cao cấp (Thành Thắng, Thịnh Thành, Thịnh Vượng, Tiến Sơn) |
| Q428 | Giá Avento 1 120W-192Led ở Đà Nẵng là bao nhiêu một bộ? | 14.815.000 | tên lưu: Avento 1 120W-192Led |
| Q430 | Giá bột bả ngoại thất cao cấp ở Hà Nội là bao nhiêu một kg? | 9.506, 13.264 | tên lưu: bột bả ngoại thất cao cấp |
| Q441 | Giá Van bướm gang cánh inox điều khiển điện dạng tuyến tính Kosaplus - Hàn Quốc DN150 ở Hà Nội là bao nhiêu một bộ? | 43.051.200 | tên lưu: Van bướm gang cánh inox điều khiển điện dạng tuyến tính Kosaplus - Hàn Quốc DN150 |
| Q446 | Giá Cút HDPE ren ngoài DN40x1" ở Hà Nội là bao nhiêu một cái? | 65.600 | tên lưu: Cút HDPE ren ngoài DN40x1" |
| Q458 | Giá Sơn nội thất bóng cao cấp trắng, màu TOGI T200 (Thùng18L:21Kg) ở Đà Nẵng là bao nhiêu một thùng? | 2.534.000 | tên lưu: Sơn nội thất bóng cao cấp trắng, màu TOGI T200 (Thùng18L:21Kg) |
| Q465 | Giá Tê thu HDPE DN315x225 ở Hà Nội là bao nhiêu một cái? | 8.342.700 | tên lưu: Tê thu HDPE DN315x225 |
| Q468 | Giá Vonta - VTFL02D/300w - DIM - S ở Hà Nội là bao nhiêu một cái? | 8.900.000 | tên lưu: Vonta - VTFL02D/300w - DIM - S |
| Q472 | Giá Máng táng quang ECO lắp nổi 2 bóng 0.6m ở Đà Nẵng là bao nhiêu một từ, con mồi)? | 395.000, 461.000 | tên lưu: Máng táng quang ECO lắp nổi 2 bóng 0.6m |
| Q489 | Giá Bộ nắp hố ga Composite nắp tròn, khung tròn, KT nắp 700mm, tải trọng 125KN ở Đà Nẵng là bao nhiêu một bộ? | 1.986.000 | tên lưu: Bộ nắp hố ga Composite nắp tròn, khung tròn, KT nắp 700mm, tải trọng 125KN |
| Q493 | Giá LIGHT GLOSS - Sơn nội thất bóng ngọc trai ở Hà Nội là bao nhiêu một kg? | 114.000 | tên lưu: LIGHT GLOSS - Sơn nội thất bóng ngọc trai |

### G2 · tra giá — bỏ dấu tiếng Việt (63 câu)

| mã | câu hỏi | đáp án | tên lưu trong DB |
|---|---|---|---|
| Q009 | Giá TOPGUARD, PART B Son phu Acrylic Polyurethane 02 thanh phan (4L/lon) ở Đà Nẵng là bao nhiêu một Lon? | 1.485.000 | tên lưu: TOPGUARD, PART B Sơn phủ Acrylic Polyurethane 02 thành phần (4L/lon) |
| Q014 | Giá Son sieu bong ngoai that kim cuong ( 1.2 kg/thung ) ở Đà Nẵng là bao nhiêu một lon? | 412.000 | tên lưu: Sơn siêu bóng ngoại thất kim cương ( 1.2 kg/thùng ) |
| Q023 | Giá Den duong Led KC-DL13C 150W, tiet giam cong suat 2-5 cap ở Hà Nội là bao nhiêu một chiếc? | 7.110.000 | tên lưu: Đèn đường Led KC-DL13C 150W, tiết giảm công suất 2-5 cấp |
| Q029 | Giá Son bong noi that cao cap DAHLIA-10 ở Hà Nội là bao nhiêu một lít? | 1.206.481, 3.864.815 | tên lưu: Sơn bóng nội thất cao cấp DAHLIA-10 |
| Q039 | Giá Nhua duong 60/70 ở Hà Nội là bao nhiêu một kg? | 18.600 | tên lưu: Nhựa đường 60/70 |
| Q048 | Giá Den Led pha CDE-SL1235FF-16, RGBW, Cree Chips, IP66 ở Đà Nẵng là bao nhiêu một bộ? | 18.015.365 | tên lưu: Đèn Led pha CDE-SL1235FF-16, RGBW, Cree Chips, IP66 |
| Q050 | Giá Den led pha CDE-FL250W, cong suat 250W ở Đà Nẵng là bao nhiêu một bộ? | 14.500.000 | tên lưu: Đèn led pha CDE-FL250W, công suất 250W |
| Q055 | Giá Den LED Sao La SL10(125w-160w) DIM. Chong set 10kA ở Hà Nội là bao nhiêu một bộ? | 7.450.000 | tên lưu: Đèn LED Sao La SL10(125w-160w) DIM. Chống sét 10kA |
| Q056 | Giá Vua xi mang kho tron san khong co - GPS® GROUT M90 ở Hà Nội là bao nhiêu một kg? | 23.000 | tên lưu: Vữa xi măng khô trộn sẵn không co - GPS® GROUT M90 |
| Q060 | Giá ton Austnam ADLOK420 - 3 song, day 0,45mm ở Hà Nội là bao nhiêu một m2? | 235.455 | tên lưu: tôn Austnam ADLOK420 - 3 sóng, dày 0,45mm |
| Q064 | Giá Van mot chieu mat bich canh lat co doi trong - FAF 2280 DN250 ở Hà Nội là bao nhiêu một cái? | 54.890.880 | tên lưu: Van một chiều mặt bích cánh lật có đối trọng - FAF 2280 DN250 |
| Q066 | Giá Son bong chong nong ngoai that Alex Pro ( 15L/thung) ở Đà Nẵng là bao nhiêu một thùng? | 5.030.909 | tên lưu: Sơn bóng chóng nóng ngoại thất Alex Pro ( 15L/thùng) |
| Q068 | Giá Son chong tham mau vuot troi Ultra Prevent (5L/lon) ở Đà Nẵng là bao nhiêu một lon? | 1.367.273 | tên lưu: Sơn chống thấm màu vượt trội Ultra Prevent (5L/lon) |
| Q087 | Giá Cap ngam 3x25+1x16 (7/2.14) +(7/1.70) ở Hà Nội là bao nhiêu một m? | 556.593 | tên lưu: Cáp ngầm 3x25+1x16 (7/2.14) +(7/1.70) |
| Q092 | Giá Ong luon tron PVC - H.SERIES phi 20 ở Đà Nẵng là bao nhiêu một cây? | 30.000 | tên lưu: Ống luồn tròn PVC - H.SERIES phi 20 |
| Q099 | Giá Cap Cu/XLPE/PVC-Fr 4x16mm2 ở Hà Nội là bao nhiêu một m? | 416.117 | tên lưu: Cáp Cu/XLPE/PVC-Fr 4x16mm2 |
| Q112 | Giá Ong uPVC C6 D90 ở Hà Nội là bao nhiêu một m? | 185.800 | tên lưu: Ống uPVC C6 D90 |
| Q114 | Giá Nhua duong Colflex® I (PMB-I) ở Hà Nội là bao nhiêu một kg? | 26.400 | tên lưu: Nhựa đường Colflex® I (PMB-I) |
| Q120 | Giá bo den duong ham Signify/Philips FlowBase G2 LED 100W (BWP352) ở Hà Nội là bao nhiêu một bộ? | 6.951.000 | tên lưu: bộ đèn đường hầm Signify/Philips FlowBase G2 LED 100W (BWP352) |
| Q121 | Giá Cua di 2 canh mo truot: Thanh profile Adamas/ Viet Phap Shal he Xingfa(XF) 93, day 2.0mm ở Đà Nẵng là bao nhiêu? | 3.433.000 | tên lưu: Cửa đi 2 cánh mở trượt: Thanh profile Adamas/ Việt Pháp Shal hệ Xingfa(XF) 93, dày 2.0mm |
| Q126 | Giá SON NOI THAT BONG mO CAO CAP (mang son bong nhe, chong phai mau, chui rua tot, do phu cao) ở Hà Nội là bao nhiêu một kg? | 97.489 | tên lưu: SƠN NỘI THẤT BÓNG mỜ CAO CẤP (màng sơn bóng nhẹ, chống phai màu, chùi rửa tốt, độ phủ cao) |
| Q128 | Giá San Deck H50W1000 do day 1.5 mm ở Hà Nội là bao nhiêu một kg? | 28.000 | tên lưu: Sàn Deck H50W1000 độ dày 1.5 mm |
| Q132 | Giá Ong luon day dien DN32 1250N ở Hà Nội là bao nhiêu một cây? | 120.500 | tên lưu: Ống luồn dây điện DN32 1250N |
| Q139 | Giá Ban cau mot khoi Prime ma P11-007 WH (Nap roi em, men Nano sieu khang khuan) 700x375x720 ở Hà Nội là bao nhiêu một bộ? | 5.800.000 | tên lưu: Bàn cầu một khối Prime mã P11-007 WH (Nắp rơi êm, men Nano siêu kháng khuẩn) 700x375x720 |
| Q146 | Giá TOA 2 TRONG 1 SON LOT VA PHU ACRYLIC KHO NHANH (Mau thuong) (17.5L/thung) ở Đà Nẵng là bao nhiêu một Thùng? | 2.880.556 | tên lưu: TOA 2 TRONG 1 SƠN LÓT VÀ PHỦ ACRYLIC KHÔ NHANH (Màu thường) (17.5L/thùng) |
| Q152 | Giá Bong bup Series C Led 12W ở Đà Nẵng là bao nhiêu một bóng? | 40.000 | tên lưu: Bóng búp Series C Led 12W |
| Q156 | Giá Class 2 Φ200 day 5.9 ở Hà Nội là bao nhiêu một m? | 362.300 | tên lưu: Class 2 Φ200 dầy 5.9 |
| Q180 | Giá Chong tham 2 thanh phan Vipri trust,10 lit ở Đà Nẵng là bao nhiêu một 10 lít? | 787.037 | tên lưu: Chống thấm 2 thành phần Vipri trust,10 lít |
| Q186 | Giá Con thu HDPE DN250x110 ở Hà Nội là bao nhiêu một cái? | 4.264.400 | tên lưu: Côn thu HDPE DN250x110 |
| Q194 | Giá Son CHONG THAM MAU Y18,04L/lon ở Đà Nẵng là bao nhiêu một Lon? | 1.290.000 | tên lưu: Sơn CHỐNG THẤM MÀU Y18,04L/lon |
| Q203 | Giá mang song ren trongi HDPE DN50x1 1/2" ở Hà Nội là bao nhiêu một cái? | 75.700 | tên lưu: măng sông ren trongi HDPE DN50x1 1/2" |
| Q207 | Giá Gach TH01 (4 vien goc va 1 vien giua) KT tong the (500x500x60)mm, M600 ở Đà Nẵng là bao nhiêu một m²? | 276.000, 295.000 | tên lưu: Gạch TH01 (4 viên góc và 1 viên giữa) KT tổng thể (500x500x60)mm, M600 |
| Q223 | Giá Co noi chu T co nap phi 20 ở Đà Nẵng là bao nhiêu một cái? | 7.500 | tên lưu: Co nối chữ T có nắp phi 20 |
| Q244 | Giá Gach dac (55x90x190)mm ở Đà Nẵng là bao nhiêu một viên? | 1.472 | tên lưu: Gạch đặc (55x90x190)mm |
| Q251 | Giá canDEN -VTK07 ở Hà Nội là bao nhiêu một cần? | 1.205.000 | tên lưu: cầnĐÈN -VTK07 |
| Q271 | Giá Den LED tube Dien Quang DQ LEDTU09 09765 (0.6m 9W daylight than nhom chup nhua mo) ở Đà Nẵng là bao nhiêu một cái? | 93.390 | tên lưu: Đèn LED tube Điện Quang ĐQ LEDTU09 09765 (0.6m 9W daylight thân nhôm chụp nhựa mờ) |
| Q279 | Giá Den LED dung cho chieu sang duong pho - Phu Thang: Den LED STAR 888 cong suat 100W-DIM ở Hà Nội là bao nhiêu một bộ? | 8.120.000 | tên lưu: Đèn LED dùng cho chiếu sáng đường phố - Phú Thắng: Đèn LED STAR 888 công suất 100W-DIM |
| Q280 | Giá Hoa chat chong tham 2 thanh phan goc Polyurethane Conmik PU Eco Cm21 ở Hà Nội là bao nhiêu một kg? | 260.000 | tên lưu: Hóa chất chống thấm 2 thành phần gốc Polyurethane Conmik PU Eco Cm21 |
| Q283 | Giá O cam sac USB A & USB C DC 5V-3.1A, 2 modul A6USB-A/C ở Hà Nội là bao nhiêu một cái? | 345.926 | tên lưu: Ổ cắm sạc USB A & USB C DC 5V-3.1A, 2 modul A6USB-A/C |
| Q287 | Giá Den san vuon 1 x 60/100W ở Đà Nẵng là bao nhiêu một cái? | 409.000 | tên lưu: Đèn sân vườn 1 x 60/100W |
| Q293 | Giá Cap Cu/XLPE/PVC-Fr 3x6mm2 ở Hà Nội là bao nhiêu một m? | 139.840 | tên lưu: Cáp Cu/XLPE/PVC-Fr 3x6mm2 |
| Q331 | Giá Ong HDPE D560 PN16 ở Hà Nội là bao nhiêu một m? | 9.803.200 | tên lưu: Ống HDPE D560 PN16 |
| Q335 | Giá MUI (Ket hop thanh nap mong va song duc sat san) rac be tong ở Hà Nội là bao nhiêu một bộ? | 8.832.000 | tên lưu: MÙI (Kết hợp thành nắp móng và song đúc sắt sẵn) rác bê tông |
| Q351 | Giá Son sieu bong noi that kim cuong ( 5.5kg/thung ) ở Đà Nẵng là bao nhiêu một lon? | 1.359.000 | tên lưu: Sơn siêu bóng nội thất kim cương ( 5.5kg/thùng ) |
| Q356 | Giá Son min ngoai that cao cap - BuildTex ở Hà Nội là bao nhiêu một kg? | 8.740 | tên lưu: Sơn mịn ngoại thất cao cấp - BuildTex |
| Q362 | Giá SUPERTECH PRO NGOAI THAT SON NUOC NGOAI THAT (5L/lon) ở Đà Nẵng là bao nhiêu một Lon? | 843.519 | tên lưu: SUPERTECH PRO NGOẠI THẤT SƠN NƯỚC NGOẠI THẤT (5L/lon) |
| Q377 | Giá Bang keo dien Nano 10 Yard ở Đà Nẵng là bao nhiêu một cuộn? | 4.500, 8.200 | tên lưu: Băng keo điện Nano 10 Yard |
| Q387 | Giá bot ba noi va ngoai that cao cap ở Hà Nội là bao nhiêu một kg? | 11.759 | tên lưu: bột bả nội và ngoại thất cao cấp |
| Q406 | Giá Cot thep Bat giac, Tron con 6m D78-3mm ở Hà Nội là bao nhiêu một Cột? | 3.580.632 | tên lưu: Cột thép Bát giác, Tròn côn 6m D78-3mm |
| Q407 | Giá SON NGOAI THAT: OPTEX- TITANIUM: Son sieu bong ngoai that cao cap 8 in 1 - P-09 ở Hà Nội là bao nhiêu một lít? | 329.156 | tên lưu: SƠN NGOẠI THẤT: OPTEX- TITANIUM: Sơn siêu bóng ngoại thất cao cấp 8 in 1 - P-09 |
| Q408 | Giá Van giam ap thuy luc FAF 7551 DN350 ở Hà Nội là bao nhiêu một cái? | 206.352.000 | tên lưu: Van giảm áp thủy lực FAF 7551 DN350 |
| Q414 | Giá Bot noi that METTON (40kg/bao) ở Đà Nẵng là bao nhiêu một bao? | 305.556 | tên lưu: Bột nội thất METTON (40kg/bao) |
| Q427 | Giá TOA NANOSHIELD SEALER SON LOT CHONG KIEM NGOAI THAT CAO CAP (15L/thung) ở Đà Nẵng là bao nhiêu một Thùng? | 4.097.222 | tên lưu: TOA NANOSHIELD SEALER SƠN LÓT CHỐNG KIỀM NGOẠI THẤT CAO CẤP (15L/thùng) |
| Q431 | Giá Den LED downlight D AT04L 110/9w.DA ở Đà Nẵng là bao nhiêu một cái? | 151.000 | tên lưu: Đèn LED downlight D AT04L 110/9w.DA |
| Q433 | Giá HOMECOTE WALL PUTTY INTERIOR BOT TRET HOMECOTE NOI THAT (40KG/bao) ở Đà Nẵng là bao nhiêu một Bao? | 452.778 | tên lưu: HOMECOTE WALL PUTTY INTERIOR BỘT TRÉT HOMECOTE NỘI THẤT (40KG/bao) |
| Q443 | Giá Son bong ngoai that cao cap ở Hà Nội là bao nhiêu một lít? | 3.946.000 | tên lưu: Sơn bóng ngoại thất cao cấp |
| Q450 | Giá Vua xay dung SCL-Mortar M7.5 (bao jumbo 1.500 kg/bao - loai xay) ở Hà Nội là bao nhiêu một tấn? | 910.000 | tên lưu: Vữa xây dựng SCL-Mortar M7.5 (bao jumbo 1.500 kg/bao - loại xây) |
| Q452 | Giá Son bong noi that cao cap NINOCLEAN trang, mau,01Kg/lon ở Đà Nẵng là bao nhiêu một Lon? | 420.000 | tên lưu: Sơn bóng nội thất cao cấp NINOCLEAN trắng, màu,01Kg/lon |
| Q461 | Giá Coc BTLT PHC-350 ở Đà Nẵng là bao nhiêu một m? | 365.000, 390.000, 450.000 | tên lưu: Cọc BTLT PHC-350 |
| Q480 | Giá Te thu HDPE DN315x280 ở Hà Nội là bao nhiêu một cái? | 8.943.800 | tên lưu: Tê thu HDPE DN315x280 |
| Q485 | Giá DenLEDchieusangduongphoDPC04B141-150W.hieu suat phat quang bo den >= 140Lm/W ở Đà Nẵng là bao nhiêu một bộ? | 8.701.000 | tên lưu: ĐènLEDchiếusángđườngphốDPC04B141-150W.hiệu suất phát quang bộ đèn >= 140Lm/W |
| Q490 | Giá Son ngoai that NINOGUARD trang, mau,01Kg/lon ở Đà Nẵng là bao nhiêu một Lon? | 400.000 | tên lưu: Sơn ngoại thất NINOGUARD trắng, màu,01Kg/lon |
| Q491 | Giá Son noi that bong cao cap SUMO Lavender (19.6kg/thung) ở Đà Nẵng là bao nhiêu một thùng? | 3.776.000 | tên lưu: Sơn nội thất bóng cao cấp SUMO Lavender (19.6kg/thùng) |

### G3 · tra giá — gãy mã (CXV-150 → CXV150) (63 câu)

| mã | câu hỏi | đáp án | tên lưu trong DB |
|---|---|---|---|
| Q002 | Giá Sơn ngoại thất SOLITE – SL62 trắng, màu,01Kglon ở Đà Nẵng là bao nhiêu một Lon? | 380.000 | tên lưu: Sơn ngoại thất SOLITE – SL62 trắng, màu,01Kg/lon |
| Q006 | Giá Vữa xây dựng SCLMortar M50 (đóng bao jumbo 1500 kgbao - loại trát) ở Hà Nội là bao nhiêu một tấn? | 900.000 | tên lưu: Vữa xây dựng SCL-Mortar M5.0 (đóng bao jumbo 1.500 kg/bao - loại trát) |
| Q032 | Giá Máng đèn batten Slimkit đuôi đèn oval 1 bóng 06m ở Đà Nẵng là bao nhiêu một bộ? | 114.500 | tên lưu: Máng đèn batten Slimkit đuôi đèn oval 1 bóng 0.6m |
| Q046 | Giá Sơn siêu trắng nội thất cao cấp SUPER WHITE02 ở Hà Nội là bao nhiêu một lít? | 701.852, 2.216.667 | tên lưu: Sơn siêu trắng nội thất cao cấp SUPER WHITE-02 |
| Q057 | Giá Thiết bị tách mỡ 8ls HS - TN8 ở Hà Nội là bao nhiêu một bộ? | 42.553.408 | tên lưu: Thiết bị tách mỡ 8l/s HS - TN8 |
| Q059 | Giá FRNCXV 2x10 ở Hà Nội là bao nhiêu một m? | 111.670 | tên lưu: FRN-CXV 2x10 |
| Q067 | Giá Cút HDPE ren trong DN75x2 12" ở Hà Nội là bao nhiêu một cái? | 333.100 | tên lưu: Cút HDPE ren trong DN75x2 1/2" |
| Q075 | Giá Sơn nhũ đồng cao cấp Rman -R94 (1kglon) ở Đà Nẵng là bao nhiêu một lon? | 490.509 | tên lưu: Sơn nhũ đồng cao cấp Rman -R94 (1kg/lon) |
| Q077 | Giá SUPERSHIELD DURACLEAN A+ BÓNG MỜ SƠN NƯỚC NỘI THẤT SIÊU CAO CẤP (15Lthùng) ở Đà Nẵng là bao nhiêu một Thùng? | 5.701.852 | tên lưu: SUPERSHIELD DURACLEAN A+ BÓNG MỜ SƠN NƯỚC NỘI THẤT SIÊU CAO CẤP (15L/thùng) |
| Q078 | Giá Đèn LED chiếu sáng đường phố DPC03A 6180W . hiệu suất phát quang bộ đèn >= 120LmW ở Đà Nẵng là bao nhiêu một bộ? | 5.771.000 | tên lưu: Đèn LED chiếu sáng đường phố DPC03A 61-80W . hiệu suất phát quang bộ đèn >= 120Lm/W |
| Q081 | Giá Đèn chiếu rọi LED 20W, ánh sáng trắng/ấm Roman, Mã: ELC103620W,A ở Hà Nội là bao nhiêu một chiếc? | 232.000 | tên lưu: Đèn chiếu rọi LED 20W, ánh sáng trắng/ấm Roman, Mã: ELC1036/20W,A |
| Q093 | Giá DATACTSW 1x30024kV ở Hà Nội là bao nhiêu một m? | 1.638.635 | tên lưu: DATA/CTS-W 1x300-24kV |
| Q103 | Giá Máng đèn tán quang âm trần 3x06m (Không bóng) ở Đà Nẵng là bao nhiêu một bộ? | 1.260.000 | tên lưu: Máng đèn tán quang âm trần 3x0.6m (Không bóng) |
| Q109 | Giá bộ đèn LED Panel chiếu đáy 3cm 600*600mm 40W, ánh sáng trắng -Roman, Mã:PLP102060640W ở Hà Nội là bao nhiêu một chiếc? | 735.000 | tên lưu: bộ đèn LED Panel chiếu đáy 3cm 600*600mm 40W, ánh sáng trắng -Roman, Mã:PLP102/060640W |
| Q117 | Giá Cáp ngầm 4x50 (19183) ở Hà Nội là bao nhiêu một m? | 1.135.666 | tên lưu: Cáp ngầm 4x50 (19/1.83) |
| Q127 | Giá FL05A 200W hiệu suất phát quang bộ đèn >120lmW ở Đà Nẵng là bao nhiêu một bộ? | 10.330.000 | tên lưu: FL05A 200W hiệu suất phát quang bộ đèn >120lm/W |
| Q162 | Giá bộ đèn đường SignifyPhilips LED Roadflair Pro 220W (BRP594) ở Hà Nội là bao nhiêu một bộ? | 14.350.000 | tên lưu: bộ đèn đường Signify/Philips LED Roadflair Pro 220W (BRP594) |
| Q168 | Giá Đai khởi thủy HDPE DN125x34" ở Hà Nội là bao nhiêu một cái? | 260.500 | tên lưu: Đai khởi thủy HDPE DN125x3/4" |
| Q170 | Giá Tôn PU (11 sóng) dày 040mm ở Hà Nội là bao nhiêu một m2? | 259.000, 269.000 | tên lưu: Tôn PU (11 sóng) dày 0.40mm |
| Q171 | Giá Class 0 Φ160 dầy 32 ở Hà Nội là bao nhiêu một m? | 171.600 | tên lưu: Class 0 Φ160 dầy 3.2 |
| Q183 | Giá CUXLPEPVC0,61kV 3x185+1x150mm2 ở Hà Nội là bao nhiêu một m? | 2.867.000 | tên lưu: CU/XLPE/PVC0,6/1kV 3x185+1x150mm2 |
| Q184 | Giá Đai khởi thủy HDPE DN200x114" ở Hà Nội là bao nhiêu một cái? | 644.000 | tên lưu: Đai khởi thủy HDPE DN200x1.1/4" |
| Q185 | Giá Sen tắm Orans OLS7621W ở Hà Nội là bao nhiêu một bộ? | 4.900.000 | tên lưu: Sen tắm Orans OLS-7621W |
| Q190 | Giá LVABC2x500,61 kV (ruột nhôm) ở Đà Nẵng là bao nhiêu một m? | 65.690 | tên lưu: LV-ABC-2x50-0,6/1 kV (ruột nhôm) |
| Q197 | Giá Cáp ngầm 3x16+1x10 (7170)+ (7135) ở Hà Nội là bao nhiêu một m? | 366.316 | tên lưu: Cáp ngầm 3x16+1x10 (7/1.70)+ (7/1.35) |
| Q220 | Giá bộ đèn đường SignifyPhilips LED GreenVision Xceed Pro 50W (BRP581) ở Hà Nội là bao nhiêu một bộ? | 7.662.000 | tên lưu: bộ đèn đường Signify/Philips LED GreenVision Xceed Pro 50W (BRP581) |
| Q236 | Giá Cút HDPE ren trong DN50x1 12" ở Hà Nội là bao nhiêu một cái? | 101.200 | tên lưu: Cút HDPE ren trong DN50x1 1/2" |
| Q240 | Giá Tôn Kazin 150 (5 sóng) dày 04mm ở Hà Nội là bao nhiêu một m2? | 192.000 | tên lưu: Tôn Kazin 150 (5 sóng) dày 0.4mm |
| Q242 | Giá Đèn LED Panel D P07 60x6035wDA ở Đà Nẵng là bao nhiêu một cái? | 1.155.000 | tên lưu: Đèn LED Panel D P07 60x60/35w.DA |
| Q250 | Giá bộ đèn đường SignifyPhilips LED GreenVision Xceed Pro 20W (BRP581) ở Hà Nội là bao nhiêu một bộ? | 7.519.000 | tên lưu: bộ đèn đường Signify/Philips LED GreenVision Xceed Pro 20W (BRP581) |
| Q252 | Giá Vữa xi măng trát M75 ở Hà Nội là bao nhiêu một tấn? | 1.190.000 | tên lưu: Vữa xi măng trát M7.5 |
| Q262 | Giá MángđènbattenStandardkitđuôiđèntruyền thống1 bóng 12m ở Đà Nẵng là bao nhiêu một bộ? | 118.000 | tên lưu: MángđènbattenStandardkitđuôiđèntruyền thống1 bóng 1.2m |
| Q270 | Giá Đèn led pha CDEFL450W, công suất 450W ở Đà Nẵng là bao nhiêu một bộ? | 18.500.000 | tên lưu: Đèn led pha CDE-FL450W, công suất 450W |
| Q275 | Giá DSTACTSW 3x5024kV ở Hà Nội là bao nhiêu một m? | 1.050.730 | tên lưu: DSTA/CTS-W 3x50-24kV |
| Q281 | Giá ADSTACTSW 3x150405kV ở Hà Nội là bao nhiêu một m? | 956.544 | tên lưu: ADSTA/CTS-W 3x150-40.5kV |
| Q285 | Giá CUXLPEPVC0,61kV 2x6mm2 ở Hà Nội là bao nhiêu một m? | 96.000 | tên lưu: CU/XLPE/PVC0,6/1kV 2x6mm2 |
| Q291 | Giá Lót kháng kiềm nội thất Nano/ PRIMENANOINT18 lít ở Đà Nẵng là bao nhiêu một Thùng? | 2.395.000 | tên lưu: Lót kháng kiềm nội thất Nano/ PRIME.NANO.INT18 lít |
| Q306 | Giá INPRO SUPER WHITE - Sơn siêu trắng trần cao cấp T13 ở Hà Nội là bao nhiêu một lít? | 120.685 | tên lưu: INPRO SUPER WHITE - Sơn siêu trắng trần cao cấp T1.3 |
| Q309 | Giá Máng táng quang ECO lắp âm 1 bóng 06m ở Đà Nẵng là bao nhiêu một từ, con mồi)? | 249.000, 305.000 | tên lưu: Máng táng quang ECO lắp âm 1 bóng 0.6m |
| Q311 | Giá Sơn nước nội thất, kinh tế, độ phủ cao TERRAMATT (05 kgThùng) ở Đà Nẵng là bao nhiêu một Thùng? | 302.000 | tên lưu: Sơn nước nội thất, kinh tế, độ phủ cao TERRAMATT (05 kg/Thùng) |
| Q316 | Giá Đèn pha LED HMFL 38 Công suất 200W250W. Hiệu suất phát quang ≥120LmW ở Hà Nội là bao nhiêu một bộ? | 8.010.000 | tên lưu: Đèn pha LED HMFL 38 Công suất 200W-250W. Hiệu suất phát quang ≥120Lm/W |
| Q357 | Giá Sơn lót kháng kiềm nội thất Nice Space (21kgthùng) ở Đà Nẵng là bao nhiêu một thùng? | 1.769.445 | tên lưu: Sơn lót kháng kiềm nội thất Nice Space (21kg/thùng) |
| Q368 | Giá Vonta - VTL02150w - DIM - S- (VT04PG04) ở Hà Nội là bao nhiêu một cái? | 8.900.000 | tên lưu: Vonta - VTL02/150w - DIM - S- (VT04-PG04) |
| Q379 | Giá Sơn phủ nội thất (18 litThùng) ở Đà Nẵng là bao nhiêu một thùng? | 1.009.800 | tên lưu: Sơn phủ nội thất (18 lit/Thùng) |
| Q386 | Giá Côn thu D7560 PN10 ở Hà Nội là bao nhiêu một chiếc? | 17.900 | tên lưu: Côn thu D75/60 PN10 |
| Q399 | Giá Sơn lót chống kiềm WE PRIMER 8300,45Llon ở Đà Nẵng là bao nhiêu một Lon? | 550.000 | tên lưu: Sơn lót chống kiềm WE PRIMER 8300,4.5L/lon |
| Q404 | Giá Sơn nội thất che phủ hiệu quả SUMO Orange (236kgthùng) ở Đà Nẵng là bao nhiêu một thùng? | 869.000 | tên lưu: Sơn nội thất che phủ hiệu quả SUMO Orange (23.6kg/thùng) |
| Q412 | Giá Bộ đèn LED BD M26L 6018wDA ở Đà Nẵng là bao nhiêu một cái? | 161.000 | tên lưu: Bộ đèn LED BD M26L 60/18w.DA |
| Q439 | Giá Bồn cầu một khối Bravat C21292UW3- VN ở Hà Nội là bao nhiêu? | 11.820.060 | tên lưu: Bồn cầu một khối Bravat C21292UW-3- VN |
| Q445 | Giá Máng đèn tán quang ECO lắp âm 4 bóng 06m ở Đà Nẵng là bao nhiêu? | 644.000 | tên lưu: Máng đèn tán quang ECO lắp âm 4 bóng 0.6m |
| Q447 | Giá bộ đèn đường SignifyPhilips LED RoadFlair G2 250W (BRP493) ở Hà Nội là bao nhiêu một bộ? | 11.736.000 | tên lưu: bộ đèn đường Signify/Philips LED RoadFlair G2 250W (BRP493) |
| Q449 | Giá Máng đèn batten Standardkit đuôi đèn oval 1 bóng 06m ở Đà Nẵng là bao nhiêu một bộ? | 125.000 | tên lưu: Máng đèn batten Standardkit đuôi đèn oval 1 bóng 0.6m |
| Q454 | Giá Đèn Led đường phố NUY100W DIM ở Hà Nội là bao nhiêu một cái? | 3.000.000 | tên lưu: Đèn Led đường phố NUY-100W DIM |
| Q466 | Giá TOA HYDRO QUICK PRIMER SƠN LÓT ĐA NĂNG CAO CẤP (18Lthùng) ở Đà Nẵng là bao nhiêu một Thùng? | 4.400.926 | tên lưu: TOA HYDRO QUICK PRIMER SƠN LÓT ĐA NĂNG CAO CẤP (18L/thùng) |
| Q471 | Giá DHPSTR15A 90W ở Đà Nẵng là bao nhiêu một bộ? | 8.925.000 | tên lưu: DHP-STR15A 90W |
| Q473 | Giá Ống luồn tròn PVC - HSERIES phi 16 ở Đà Nẵng là bao nhiêu một cây? | 22.700 | tên lưu: Ống luồn tròn PVC - H.SERIES phi 16 |
| Q474 | Giá Máng đèn âm trần chóa phản quang cao cấp2*36 watt ở Đà Nẵng là bao nhiêu một bộ? | 836.000 | tên lưu: Máng đèn âm trần chóa phản quang cao cấp-2*36 watt |
| Q476 | Giá Bột bả tường gốc xi măng poóc lăng Victory Skim Coat VTR5 (20kgbao) ở Đà Nẵng là bao nhiêu một bao? | 416.667 | tên lưu: Bột bả tường gốc xi măng poóc lăng Victory Skim Coat VTR5 (20kg/bao) |
| Q477 | Giá Sơn lót ngoại thất Jobee Sealer Ext (17lthùng) ở Đà Nẵng là bao nhiêu một thùng? | 2.629.630 | tên lưu: Sơn lót ngoại thất Jobee Sealer Ext (17l/thùng) |
| Q488 | Giá Sơn ngoại thất siêu bóng hợp kim, chống nóng tốt FUJISU Yamato (52kglon nhựa) ở Đà Nẵng là bao nhiêu một lon? | 1.622.000 | tên lưu: Sơn ngoại thất siêu bóng hợp kim, chống nóng tốt FUJISU Yamato (5.2kg/lon nhựa) |
| Q495 | Giá Đèn Led đường phố KAPPA120W ở Hà Nội là bao nhiêu một cái? | 1.836.000 | tên lưu: Đèn Led đường phố KAPPA-120W |
| Q499 | Giá bộ đèn đường SignifyPhilips LED RoadFlair G2 70W (BRP491) ở Hà Nội là bao nhiêu một bộ? | 6.700.000 | tên lưu: bộ đèn đường Signify/Philips LED RoadFlair G2 70W (BRP491) |
| Q500 | Giá Sơn Alkyd chống gỉ màu xám (20 litthùng) ở Đà Nẵng là bao nhiêu một thùng? | 2.131.800 | tên lưu: Sơn Alkyd chống gỉ màu xám (20 lit/thùng) |

### G4 · tra giá — rút gọn ~40% từ (63 câu)

| mã | câu hỏi | đáp án | tên lưu trong DB |
|---|---|---|---|
| Q001 | Giá Đèn LED Điện LEDSL18 60W ở Đà Nẵng là bao nhiêu một cái? | 8.614.050 | tên lưu: Đèn đường LED Điện Quang LEDSL18 60W |
| Q011 | Giá Granite quy (150x150x50) mm ở Đà Nẵng là bao nhiêu một m2? | 554.545 | tên lưu: Đá Granite quy cách (150x150x50) mm |
| Q021 | Giá Đèn Led KC-ZS15 120W-150W, tiết suất 2-5 cấp ở Hà Nội là bao nhiêu một chiếc? | 7.650.000 | tên lưu: Đèn đường Led KC-ZS15 120W-150W, tiết giảm công suất 2-5 cấp |
| Q026 | Giá Gạch Terazo ngoại đỏ vàng AP(400x400x30)mm ở Đà Nẵng là bao nhiêu một m²? | 91.000 | tên lưu: Gạch Terazo ngoại thất màu đỏ hoặc màu vàng AP(400x400x30)mm |
| Q045 | Giá khô trộn thấm Victory Acc VTR4 (25kg/bao) ở Đà Nẵng là bao nhiêu một bao? | 300.926 | tên lưu: Vữa khô trộn sẵn chống thấm Victory Acc VTR4 (25kg/bao) |
| Q053 | Giá bộ gang 160 kg ở Hà Nội là bao nhiêu một bộ? | 6.750.576 | tên lưu: bộ ghi gang 160 kg |
| Q065 | Giá LED Panel D P05 640x640/50W.DA ở Đà Nẵng là bao nhiêu một cái? | 1.650.000 | tên lưu: Đèn LED Panel D P05 640x640/50W.DA |
| Q100 | Giá L63x63x6, L= 1500mm, nối D10x1500mm ở Hà Nội là bao nhiêu một bộ? | 315.000 | tên lưu: L63x63x6, L= 1500mm, dây nối D10x1500mm |
| Q107 | Giá Ống uPVC D225 ở Hà Nội là bao nhiêu một m? | 255.400 | tên lưu: Ống uPVC Thoát D225 |
| Q113 | Giá đèn LED TUBE T8 60/10w.DA ở Đà Nẵng là bao nhiêu một cái? | 112.000 | tên lưu: Bóng đèn LED TUBE T8 60/10w.DA |
| Q116 | Giá Khung gang (107kg) ở Hà Nội là bao nhiêu một Khung? | 4.475.183 | tên lưu: Khung ga gang (107kg) |
| Q119 | Giá Sơn siêu ngoại thất cương ở Đà Nẵng là bao nhiêu một thùng? | 5.202.000 | tên lưu: Sơn siêu bóng ngoại thất kim cương (20kg/thùng ) |
| Q122 | Giá G98022, G98305 ;G98308, G98T15 ; G98T18, G98MXBL ;G98MXGA ; G98MXGR ở Đà Nẵng là bao nhiêu một m²? | 389.978 | tên lưu: G98022, G98305 ;G98308, G98T15 ; G98T18, G98MXBL ;G98MXGA ; G98MXGR |
| Q129 | Giá Ống gân xoắn 320/250 ở Hà Nội là bao nhiêu một m? | 593.600 | tên lưu: Ống nhựa gân xoắn HDPE 320/250 |
| Q137 | Giá Ống uPVC C0 D225 ở Hà Nội là bao nhiêu một m? | 316.000, 316.300 | tên lưu: Ống uPVC C0 D225 |
| Q138 | Giá chống kiềm Tomat 6000 (5L/lon) ở Đà Nẵng là bao nhiêu một lon? | 947.273 | tên lưu: Sơn chống kiềm Tomat CK 6000 (5L/lon) |
| Q142 | Giá Đầu nối HDPE DN110 ở Hà Nội là bao nhiêu một cái? | 450.800 | tên lưu: Đầu nối bích HDPE DN110 |
| Q144 | Giá Ống HDPE D140 PN10 ở Hà Nội là bao nhiêu một m? | 386.900 | tên lưu: Ống HDPE D140 PN10 |
| Q155 | Giá TCLCĐ, 7 m, vươn 1,5m, dày 3,5mm ở Hà Nội là bao nhiêu một cột? | 3.345.000 | tên lưu: TCLCĐ, BGLCD cao 7 m, vươn 1,5m, dày 3,5mm |
| Q160 | Giá SV320 - cuộn 20m ở Đà Nẵng là bao nhiêu một cuộn? | 4.160.000 | tên lưu: BestWaterbar SV320 - cuộn 20m |
| Q166 | Giá Diềm mái Onduline 1100x380x3) (xanh, nâu) ở Đà Nẵng là bao nhiêu một tấm? | 132.000 | tên lưu: Diềm mái Onduline (KT: 1100x380x3) (xanh, đỏ, nâu) |
| Q167 | Giá Ống uPVC C1 D60 ở Hà Nội là bao nhiêu một m? | 41.900 | tên lưu: Ống uPVC C1 D60 |
| Q174 | Giá Led phố AWINMAX -100W DIM DALI ở Hà Nội là bao nhiêu một cái? | 8.285.000 | tên lưu: Đèn Led đường phố AWINMAX -100W DIM DALI |
| Q177 | Giá Ống HDPE PE100 DN50 PN10 ở Hà Nội là bao nhiêu một m? | 50.100 | tên lưu: Ống HDPE PE100 DN50 PN10 |
| Q181 | Giá Sơn giả cương ở Hà Nội là bao nhiêu một 5L? | 1.314.815, 4.325.000 | tên lưu: Sơn giả đá Hoa cương |
| Q219 | Giá Tê ren HDPE DN32x3/4" ở Hà Nội là bao nhiêu một cái? | 51.000 | tên lưu: Tê ren ngoài HDPE DN32x3/4" |
| Q226 | Giá bộ đường hầm Signify/Philips FlowBase G2 40W (BWP352) ở Hà Nội là bao nhiêu một bộ? | 5.104.000, 5.576.500, 6.565.500 | tên lưu: bộ đèn đường hầm Signify/Philips FlowBase G2 LED 40W (BWP352) |
| Q231 | Giá Sơn nội thất siêu bóng cấp FUJISU (5.1kg/lon nhựa) ở Đà Nẵng là bao nhiêu một lon? | 1.493.000 | tên lưu: Sơn nội thất siêu bóng hợp kim cao cấp FUJISU Agano (5.1kg/lon nhựa) |
| Q261 | Giá gang lệch tay quay bích FAF 3800 DN150 ở Hà Nội là bao nhiêu một cái? | 22.147.840 | tên lưu: Van bướm gang lệch tâm tay quay mặt bích FAF 3800 DN150 |
| Q263 | Giá LED Bulb BU11 Điện ĐQ LEDBU11A50 ở Đà Nẵng là bao nhiêu một cái? | 28.930 | tên lưu: Đèn LED Bulb BU11 Điện Quang ĐQ LEDBU11A50 (3W daylight/ warmwhite chụp cầu mờ) |
| Q292 | Giá Led trang trí HE PS 4,5W ở Đà Nẵng là bao nhiêu? | 95.000 | tên lưu: Led Bulb trang trí HE LED PS 4,5W |
| Q296 | Giá điện 2 cửa 16 đường ở Đà Nẵng là bao nhiêu một cái? | 888.000 | tên lưu: Tủ điện 2 cửa 16 đường |
| Q298 | Giá Đèn LED Katrina SL15 (135w-150w). sét 10kA ở Hà Nội là bao nhiêu một bộ? | 8.150.000 | tên lưu: Đèn LED Katrina SL15 (135w-150w). DIM. Chống sét 10kA |
| Q302 | Giá Bộ máng đèn siêu mỏng-T8 1x1.2m ở Đà Nẵng là bao nhiêu một bộ? | 378.000 | tên lưu: Bộ máng đèn bóng Led siêu mỏng-T8 1x1.2m |
| Q310 | Giá Phụ gia hoá MEN PRO,0,5L ở Đà Nẵng là bao nhiêu một 0,5L? | 158.000 | tên lưu: Phụ gia hoá học CX MEN PRO,0,5L |
| Q314 | Giá Gạch rỗng 6 98*98*198 mm ở Đà Nẵng là bao nhiêu một 4? | 2.639 | tên lưu: Gạch rỗng 6 lỗ nhỏ 98*98*198 mm |
| Q321 | Giá Ống HDPE PE100 DN40 PN12.5 ở Hà Nội là bao nhiêu một m? | 39.500 | tên lưu: Ống HDPE PE100 DN40 PN12.5 |
| Q323 | Giá bả ngoại thất cao N303 ở Hà Nội là bao nhiêu một kg? | 7.000 | tên lưu: bột bả ngoại thất cao cấp N303 |
| Q337 | Giá LED downlight D AT12L 240x125/9wx2.DA ở Đà Nẵng là bao nhiêu một cái? | 1.276.000 | tên lưu: Đèn LED downlight D AT12L 240x125/9wx2.DA |
| Q346 | Giá Đai khởi thủy DN110x2" ở Hà Nội là bao nhiêu một cái? | 171.700 | tên lưu: Đai khởi thủy HDPE DN110x2" |
| Q353 | Giá Van mặt bích cánh lật có - FAF 2280 DN600 ở Hà Nội là bao nhiêu một cái? | 205.571.520 | tên lưu: Van một chiều mặt bích cánh lật có đối trọng - FAF 2280 DN600 |
| Q366 | Giá Bình VANREm-ITALY xuất: Loại 100L-10bar-đặt đứng ở Hà Nội là bao nhiêu một cái? | 9.000.000 | tên lưu: Bình áp lực VANREm-ITALY sản xuất: Loại 100L-10bar-đặt đứng |
| Q367 | Giá Sơn ngoại thất siêu (5L/thùng) ở Đà Nẵng là bao nhiêu một thùng? | 873.000 | tên lưu: Sơn ngoại thất siêu che phủ (5L/thùng) |
| Q373 | Giá CE200 - bao 20 kg ở Đà Nẵng là bao nhiêu một bao? | 340.000 | tên lưu: BestJoint CE200 - bao 20 kg |
| Q375 | Giá Đèn led đường CDE-CM200W ở Đà Nẵng là bao nhiêu một bộ? | 14.500.000 | tên lưu: Đèn led chiếu sáng đường CDE-CM200W |
| Q376 | Giá Đế đôi nhựa cháy ở Đà Nẵng là bao nhiêu một cái? | 13.200 | tên lưu: Đế âm đôi nhựa chống cháy |
| Q382 | Giá ty chìm Wonil - Hàn Quốc DN80 ở Hà Nội là bao nhiêu một cái? | 3.481.600 | tên lưu: Van cổng gang ty chìm Wonil - Hàn Quốc DN80 |
| Q388 | Giá Bộ LED Alley 3 - 120DL -V02 (120w, Daylight, B2B) ở Đà Nẵng là bao nhiêu một bộ? | 3.264.000 | tên lưu: Bộ đèn đường LED Alley 3 - 120DL -V02 (120w, Daylight, B2B) |
| Q394 | Giá Đèn cảnh LED LLF0112A góc chiếu 10° 30° công suất 28,3W COLOUR) ở Hà Nội là bao nhiêu một bộ? | 20.790.000 | tên lưu: Đèn cảnh quan LED STANLEY LLF0112A góc chiếu 10° - 30° công suất 28,3W ON/OFF (ALL COLOUR) |
| Q395 | Giá Vonta VTFL02D/450w DIM S ở Hà Nội là bao nhiêu một cái? | 14.600.000 | tên lưu: Vonta - VTFL02D/450w - DIM - S |
| Q411 | Giá PRO THẤT SƠN THẤT (18L/thùng) ở Đà Nẵng là bao nhiêu một Thùng? | 2.310.185 | tên lưu: SUPERTECH PRO NGOẠI THẤT SƠN NƯỚC NGOẠI THẤT (18L/thùng) |
| Q415 | Giá NỘI THẤT: OPTEX- SUPPER WHITE: trắng thất cấp- T-02 ở Hà Nội là bao nhiêu một lít? | 119.167 | tên lưu: SƠN NỘI THẤT: OPTEX- SUPPER WHITE: Sơn siêu trắng nội thất cao cấp- T-02 |
| Q416 | Giá Giấy Decal kính ở Đà Nẵng là bao nhiêu một m2? | 34.000 | tên lưu: Giấy Decal dán kính |
| Q420 | Giá Ống HDPE D280 PN10 ở Hà Nội là bao nhiêu một m? | 1.522.100 | tên lưu: Ống HDPE D280 PN10 |
| Q435 | Giá Kích thước 1000x300x150 ở Đà Nẵng là bao nhiêu một m²? | 87.963, 152.778 | tên lưu: Kích thước 1000x300x150 (mm) |
| Q438 | Giá dán gạch CX MOZART,25kg ở Đà Nẵng là bao nhiêu một 25kg? | 272.727 | tên lưu: Keo dán gạch CX MEN MOZART,25kg |
| Q442 | Giá LED HM SMD45-I Công 150W-200W. Hiệu quang ≥120Lm/W ở Hà Nội là bao nhiêu một bộ? | 9.950.000 | tên lưu: Đèn LED HM SMD45-I Công suất 150W-200W. Hiệu suất phát quang ≥120Lm/W |
| Q451 | Giá Bộ + điện thoại ở Đà Nẵng là bao nhiêu một bộ? | 144.500 | tên lưu: Bộ ổ cắm Tivi + ổ cắm điện thoại |
| Q455 | Giá Sơn kháng ngoại thất cấp ở Hà Nội là bao nhiêu một lít? | 948.148, 2.986.000, 3.083.333 | tên lưu: Sơn lót kháng kiềm ngoại thất cao cấp |
| Q456 | Giá Sơn thất ngọc trai N650 ở Hà Nội là bao nhiêu một lít? | 179.003 | tên lưu: Sơn ngoại thất bóng ngọc trai N650 |
| Q457 | Giá Ống HDPE PE100 DN90 PN20 ở Hà Nội là bao nhiêu một m? | 281.500 | tên lưu: Ống HDPE PE100 DN90 PN20 |
| Q467 | Giá luồn dây điện DN20 750N ở Hà Nội là bao nhiêu một cây? | 32.500, 34.200 | tên lưu: Ống luồn dây điện DN20 750N |
| Q494 | Giá Van tay gang FAF 3500 DN80 ở Hà Nội là bao nhiêu một cái? | 2.256.000 | tên lưu: Van bướm tay gạt gang FAF 3500 DN80 |

### S1 · cấu trúc — đơn vị tính (28 câu)

| mã | câu hỏi | đáp án | tên lưu trong DB |
|---|---|---|---|
| Q003 | Khớp nối cao su FAF 5000 DN125 ở Hà Nội được tính theo đơn vị nào? | cái | Khớp nối cao su FAF 5000 DN125 |
| Q005 | SUPERTECH PRO NỘI THẤT SƠN NƯỚC NỘI THẤT (5L/lon) ở Đà Nẵng được tính theo đơn vị nào? | Lon | SUPERTECH PRO NỘI THẤT SƠN NƯỚC NỘI THẤT (5L/lon) |
| Q038 | Tấm nóc Onduline (900x480x3) màu xanh, đỏ,nâu ở Đà Nẵng được tính theo đơn vị nào? | tấm | Tấm nóc Onduline (900x480x3) màu xanh, đỏ,nâu |
| Q041 | Bê tông Mac M400 ở Đà Nẵng được tính theo đơn vị nào? | m3 | Bê tông Mac M400 |
| Q063 | Sơn lót ngoại thất (Fly Primer) ở Hà Nội được tính theo đơn vị nào? | lít | Sơn lót ngoại thất (Fly Primer) |
| Q072 | Đen Emergency ở Đà Nẵng được tính theo đơn vị nào? | bộ | Đen Emergency |
| Q125 | Ống HDPE PE100 DN560 PN6 ở Hà Nội được tính theo đơn vị nào? | m | Ống HDPE PE100 DN560 PN6 |
| Q143 | Máng đèn tán quang lắp âm 4 bóng 1.2m ở Đà Nẵng được tính theo đơn vị nào? | con mồi và | Máng đèn tán quang lắp âm 4 bóng 1.2m |
| Q176 | Đèn quang pha bộ LED đèn >= Sapele 150Lm/W BL- FL14C 81W - 150W, hiệu suất ở Đà Nẵng được tính theo đơn vị nào? | bộ | Đèn quang pha bộ LED đèn >= Sapele 150Lm/W BL- FL14C 81W - 150W, hiệu suất |
| Q199 | TCLCĐ, BGLCD cao 6 m, vươn 1,5m, dày 3,5mm ở Hà Nội được tính theo đơn vị nào? | cột | TCLCĐ, BGLCD cao 6 m, vươn 1,5m, dày 3,5mm |
| Q206 | CU/XLPE/PVC0,6/1kV 4x70mm2 ở Hà Nội được tính theo đơn vị nào? | m | CU/XLPE/PVC0,6/1kV 4x70mm2 |
| Q210 | Sơn lót kháng kiềm Nội thất Cao cấp 18 lít ở Đà Nẵng được tính theo đơn vị nào? | Thùng | Sơn lót kháng kiềm Nội thất Cao cấp 18 lít |
| Q224 | DHP-STR 300W ở Đà Nẵng được tính theo đơn vị nào? | bộ | DHP-STR 300W |
| Q254 | Tê thu HDPE DN50x32 ở Hà Nội được tính theo đơn vị nào? | cái | Tê thu HDPE DN50x32 |
| Q255 | Tê ren trong HDPE DN20x1/2" ở Hà Nội được tính theo đơn vị nào? | cái | Tê ren trong HDPE DN20x1/2" |
| Q257 | Van bướm gang cánh inox điều khiển điện dạng ON /OFF Kosaplus - Hàn Quốc DN50 ở Hà Nội được tính theo đơn vị nào? | bộ | Van bướm gang cánh inox điều khiển điện dạng ON /OFF Kosaplus - Hàn Quốc DN50 |
| Q274 | Sơn lót nội thất Building Rman-R96 (21kg/thùng) ở Đà Nẵng được tính theo đơn vị nào? | thùng | Sơn lót nội thất Building Rman-R96 (21kg/thùng) |
| Q295 | Cáp ngầm hạ thế (3+1) lõi ,6V/1kV - Cu/XPLE/PVC/DSTA/PVC - Phú Thắng: DSTA 3x95+1x50mm2 ở Hà Nội được tính theo đơn vị nào? | m | Cáp ngầm hạ thế (3+1) lõi ,6V/1kV - Cu/XPLE/PVC/DSTA/PVC - Phú Thắng: DSTA 3x95+1x50mm2 |
| Q348 | Chậu rửa treo tường CI06-PI06, CL06-PL06 ở Đà Nẵng được tính theo đơn vị nào? | bộ | Chậu rửa treo tường CI06-PI06, CL06-PL06 |
| Q400 | Cáp ngầm 1x185 (37/2.52) ở Hà Nội được tính theo đơn vị nào? | m | Cáp ngầm 1x185 (37/2.52) |
| Q401 | Ống luồn dây điện DN50 750N ở Hà Nội được tính theo đơn vị nào? | cây | Ống luồn dây điện DN50 750N |
| Q418 | Ống HDPE PE100 DN450 PN20 ở Hà Nội được tính theo đơn vị nào? | m | Ống HDPE PE100 DN450 PN20 |
| Q424 | Đèn LED chiếu sáng đường phố DPC04A 71-80W . hiệu suất phát quang bộ đèn >= 140Lm/W ở Đà Nẵng được tính theo đơn vị nào? | bộ | Đèn LED chiếu sáng đường phố DPC04A 71-80W . hiệu suất phát quang bộ đèn >= 140Lm/W |
| Q453 | măng sông ren trong HDPE DN63x2" ở Hà Nội được tính theo đơn vị nào? | cái | măng sông ren trong HDPE DN63x2" |
| Q475 | DSTA/CTS-W 3x70-40.5kV ở Hà Nội được tính theo đơn vị nào? | m | DSTA/CTS-W 3x70-40.5kV |
| Q479 | Hóa chất chống thấm gốc xi măng 2 thành phần Conmik W112 ở Hà Nội được tính theo đơn vị nào? | kg | Hóa chất chống thấm gốc xi măng 2 thành phần Conmik W112 |
| Q487 | RSV đơn vân ở Hà Nội được tính theo đơn vị nào? | m2 | RSV đơn vân |
| Q492 | Ống HDPE PE100 DN90 PN10 ở Hà Nội được tính theo đơn vị nào? | m | Ống HDPE PE100 DN90 PN10 |

### S2 · cấu trúc — nhà sản xuất (80 câu)

| mã | câu hỏi | đáp án | tên lưu trong DB |
|---|---|---|---|
| Q012 | Ai là nhà sản xuất/cung cấp Class 4 Φ400 dầy 19.1 ở Hà Nội? | Composit Sao Đỏ | Class 4 Φ400 dầy 19.1 |
| Q013 | Ai là nhà sản xuất/cung cấp Tê ren trong HDPE DN90x3" ở Hà Nội? | Composit Sao Đỏ | Tê ren trong HDPE DN90x3" |
| Q016 | Ai là nhà sản xuất/cung cấp CU/XLPE/PVC0,6/1kV 4x70mm2 ở Hà Nội? | điện và chiếu sáng phương đông | CU/XLPE/PVC0,6/1kV 4x70mm2 |
| Q017 | Ai là nhà sản xuất/cung cấp Đèn LED gắn tường D GT07L/5w.DA ở Đà Nẵng? | ĐN - 169 Điện Biên Phủ ĐN | Đèn LED gắn tường D GT07L/5w.DA |
| Q018 | Ai là nhà sản xuất/cung cấp Clear phủ bóng ở Hà Nội? | Sơn JYMEC Việt Nam | Clear phủ bóng |
| Q031 | Ai là nhà sản xuất/cung cấp DHP-STR 400W ở Đà Nẵng? | thiết bị điện Đồng Hưng Phát | DHP-STR 400W |
| Q034 | Ai là nhà sản xuất/cung cấp Đèn led chiếu sáng đường CDE-CM100W ở Đà Nẵng? | CDE VINA | Đèn led chiếu sáng đường CDE-CM100W |
| Q035 | Ai là nhà sản xuất/cung cấp Sơn bóng chóng nóng ngoại thất Alex Pro ( 1L/lon) ở Đà Nẵng? | Tân Sơn - Lương Sơn Hòa Bình | Sơn bóng chóng nóng ngoại thất Alex Pro ( 1L/lon) |
| Q036 | Ai là nhà sản xuất/cung cấp Sơn bán bóng ngọai thất cao cấp DAISY-03 (5lít/lon) ở Đà Nẵng? | MAXKO VIỆT NAM | Sơn bán bóng ngọai thất cao cấp DAISY-03 (5lít/lon) |
| Q037 | Ai là nhà sản xuất/cung cấp Đèn Led đường phố AWINMINI-60W DIM ở Hà Nội? | Thiết bị điện và chiếu sáng Miền Bắc | Đèn Led đường phố AWINMINI-60W DIM |
| Q044 | Ai là nhà sản xuất/cung cấp tôn Austnam ADPU1- 6 sóng, dày 0,45mm ở Hà Nội? | Austnam | tôn Austnam ADPU1- 6 sóng, dày 0,45mm |
| Q047 | Ai là nhà sản xuất/cung cấp Đèn đường Led KC-RT11A 50W-60W, tiết giảm công suất 2-5 cấp ở Hà Nội? | Chiếu sáng Kim Cương | Đèn đường Led KC-RT11A 50W-60W, tiết giảm công suất 2-5 cấp |
| Q051 | Ai là nhà sản xuất/cung cấp Vonta - VT23D/250w - DIM - S ở Hà Nội? | VONTA VIỆT NAM | Vonta - VT23D/250w - DIM - S |
| Q054 | Ai là nhà sản xuất/cung cấp Đèn chiếu rọi LED 100W, ánh sáng trắng/ấm Roman, Mã: ELC1036/100W,A ở Hà Nội? | Điện ZHEJIANG KRIPAL | Đèn chiếu rọi LED 100W, ánh sáng trắng/ấm Roman, Mã: ELC1036/100W,A |
| Q069 | Ai là nhà sản xuất/cung cấp 1,64 x1,64 x0,15 (đan thu cổ ga 12A) ở Hà Nội? | VLXD Sông Đáy | 1,64 x1,64 x0,15 (đan thu cổ ga 12A) |
| Q071 | Ai là nhà sản xuất/cung cấp Sơn lót chống kiềm nội thất ( 5.7thùng ) ở Đà Nẵng? | SUZUMAX | Sơn lót chống kiềm nội thất ( 5.7thùng ) |
| Q083 | Ai là nhà sản xuất/cung cấp Ống uPVC C5 D140 ở Hà Nội? | PmT.Quang minh | Ống uPVC C5 D140 |
| Q085 | Ai là nhà sản xuất/cung cấp Sơn phủ nội thất Jotaplast ở Hà Nội? | Sơn Jotun Việt Nam | Sơn phủ nội thất Jotaplast |
| Q086 | Ai là nhà sản xuất/cung cấp Cáp ngầm 3x185+1x120 (37/2.52)+(19/2.83) ở Hà Nội? | Slighting Việt Nam | Cáp ngầm 3x185+1x120 (37/2.52)+(19/2.83) |
| Q089 | Ai là nhà sản xuất/cung cấp Bóng đèn tuýp led thủy tinh T8 09W 0.6m ánh sáng trắng ở Đà Nẵng? | Junsun Việt Nam | Bóng đèn tuýp led thủy tinh T8 09W 0.6m ánh sáng trắng |
| Q091 | Ai là nhà sản xuất/cung cấp Ống HDPE PE100 DN400 PN12.5 ở Hà Nội? | PmT.Quang minh | Ống HDPE PE100 DN400 PN12.5 |
| Q094 | Ai là nhà sản xuất/cung cấp Sơn nội thất lau chùi hiệu quả SMARTLITE trắng, màu,01Kg/lon ở Đà Nẵng? | SƠN SANQ TITO | Sơn nội thất lau chùi hiệu quả SMARTLITE trắng, màu,01Kg/lon |
| Q106 | Ai là nhà sản xuất/cung cấp Bộ đèn LED Downlight VIRGO 39 (39W, 3000K, Ra80, góc chiếu 60 độ, HPF, B2B) ở Đà Nẵng? | Bóng đèn Điện Quang | Bộ đèn LED Downlight VIRGO 39 (39W, 3000K, Ra80, góc chiếu 60 độ, HPF, B2B) |
| Q108 | Ai là nhà sản xuất/cung cấp Đèn Led pha CDE-SL1281UF-12, RGBW, Cree Chips ở Đà Nẵng? | CDE VINA | Đèn Led pha CDE-SL1281UF-12, RGBW, Cree Chips |
| Q111 | Ai là nhà sản xuất/cung cấp Đèn LED downlight D AT12L 240x125/9wx2.DA ở Đà Nẵng? | ĐN - 169 Điện Biên Phủ ĐN | Đèn LED downlight D AT12L 240x125/9wx2.DA |
| Q133 | Ai là nhà sản xuất/cung cấp Class 0 Φ21 dầy 1.2 ở Hà Nội? | Composit Sao Đỏ | Class 0 Φ21 dầy 1.2 |
| Q134 | Ai là nhà sản xuất/cung cấp Đèn LED Panel D P05 640x640/50W.DA ở Đà Nẵng? | ĐN - 169 Điện Biên Phủ ĐN | Đèn LED Panel D P05 640x640/50W.DA |
| Q136 | Ai là nhà sản xuất/cung cấp Đèn LED Highbay D HB02L 430/100w.DA ở Đà Nẵng? | ĐN - 169 Điện Biên Phủ ĐN | Đèn LED Highbay D HB02L 430/100w.DA |
| Q153 | Ai là nhà sản xuất/cung cấp Cáp Cu/Mica/XLPE/PVC-Fr 3x16+1x10 mm2 ở Hà Nội? | Slighting Việt Nam | Cáp Cu/Mica/XLPE/PVC-Fr 3x16+1x10 mm2 |
| Q157 | Ai là nhà sản xuất/cung cấp TCLCĐ, BGLCD cao 8 m, vươn 1,5m, dày 3,5mm ở Hà Nội? | VONTA VIỆT NAM | TCLCĐ, BGLCD cao 8 m, vươn 1,5m, dày 3,5mm |
| Q172 | Ai là nhà sản xuất/cung cấp Cáp Cu/XLPE/PVC-Fr 4x16mm2 ở Hà Nội? | Slighting Việt Nam | Cáp Cu/XLPE/PVC-Fr 4x16mm2 |
| Q175 | Ai là nhà sản xuất/cung cấp Sơn CHỐNG THẤM MÀU Y18,04L/lon ở Đà Nẵng? | SƠN SANQ TITO | Sơn CHỐNG THẤM MÀU Y18,04L/lon |
| Q179 | Ai là nhà sản xuất/cung cấp ống cống D1250 TTA ở Hà Nội? | VLXD Sông Đáy | ống cống D1250 TTA |
| Q187 | Ai là nhà sản xuất/cung cấp Bê tông Mac M300 ở Đà Nẵng? | BÊ TÔNG XANH ĐÀ NẴNG | Bê tông Mac M300 |
| Q192 | Ai là nhà sản xuất/cung cấp Cáp ngầm hạ thế (3+1) lõi ,6V/1kV - Cu/XPLE/PVC/DSTA/PVC - Phú Thắng: DSTA 3x185+1x95mm2 ở Hà Nội? | Điện và Chiếu sáng Phú Thắng | Cáp ngầm hạ thế (3+1) lõi ,6V/1kV - Cu/XPLE/PVC/DSTA/PVC - Phú Thắng: DSTA 3x185+1x95mm2 |
| Q201 | Ai là nhà sản xuất/cung cấp Cút HDPE ren ngoài DN110x3" ở Hà Nội? | Composit Sao Đỏ | Cút HDPE ren ngoài DN110x3" |
| Q204 | Ai là nhà sản xuất/cung cấp Đèn đường Led KC-Y02B 100W, tiết giảm công suất 2-5 cấp ở Hà Nội? | Chiếu sáng Kim Cương | Đèn đường Led KC-Y02B 100W, tiết giảm công suất 2-5 cấp |
| Q205 | Ai là nhà sản xuất/cung cấp Đèn led đường phố AT-Lighting 150W (220-240V) ở Đà Nẵng? | TM&XL An Thành Tài | Đèn led đường phố AT-Lighting 150W (220-240V) |
| Q214 | Ai là nhà sản xuất/cung cấp Sơn phủ bóng nội - ngoại cao cấp FUJISU Clear (1.05kg/lon nhựa) ở Đà Nẵng? | ty Cổ phần Liên Doanh Sơn Nhật | Sơn phủ bóng nội - ngoại cao cấp FUJISU Clear (1.05kg/lon nhựa) |
| Q217 | Ai là nhà sản xuất/cung cấp Sơn bóng nội thất cao cấp ở Hà Nội? | CN & Tm Diệp minh | Sơn bóng nội thất cao cấp |
| Q222 | Ai là nhà sản xuất/cung cấp Đèn Led pha CDE-SL1102UC-24, RGB, Cree Chips ở Đà Nẵng? | CDE VINA | Đèn Led pha CDE-SL1102UC-24, RGB, Cree Chips |
| Q229 | Ai là nhà sản xuất/cung cấp Gạch Ceramic men bóng 40x80cm ở Đà Nẵng? | HỢP TÁC XÃ GẠCH KHÔNG NUNG HIỆP HƯNG | Gạch Ceramic men bóng 40x80cm |
| Q233 | Ai là nhà sản xuất/cung cấp Bộ đèn LED chống nổ BD CN01L 120/18w.DA ở Đà Nẵng? | ĐN - 169 Điện Biên Phủ ĐN | Bộ đèn LED chống nổ BD CN01L 120/18w.DA |
| Q235 | Ai là nhà sản xuất/cung cấp Gạch Porcelain giả gỗ 20x80cm ở Đà Nẵng? | HỢP TÁC XÃ GẠCH KHÔNG NUNG HIỆP HƯNG | Gạch Porcelain giả gỗ 20x80cm |
| Q237 | Ai là nhà sản xuất/cung cấp Đèn đường LED Điện Quang LEDSL11 90W ở Đà Nẵng? | Bóng đèn Điện Quang | Đèn đường LED Điện Quang LEDSL11 90W |
| Q239 | Ai là nhà sản xuất/cung cấp Thẻ chìa khóa ở Đà Nẵng? | Junsun Việt Nam | Thẻ chìa khóa |
| Q243 | Ai là nhà sản xuất/cung cấp Kép nhựa 2 đầu ren ngoài HDPE DN3/4"x3/4" ở Hà Nội? | Composit Sao Đỏ | Kép nhựa 2 đầu ren ngoài HDPE DN3/4"x3/4" |
| Q259 | Ai là nhà sản xuất/cung cấp Vật liệu chống thấm gốc xi măng - Polymer - GPS COAT 12N ở Hà Nội? | GPS Việt Nam | Vật liệu chống thấm gốc xi măng - Polymer - GPS COAT 12N |
| Q260 | Ai là nhà sản xuất/cung cấp Sơn mịn ngoại thất cao cấp - BuildTex ở Hà Nội? | Đầu tư | Sơn mịn ngoại thất cao cấp - BuildTex |
| Q276 | Ai là nhà sản xuất/cung cấp Đèn LED chiếu gương D G02L/8w.DA ở Đà Nẵng? | ĐN - 169 Điện Biên Phủ ĐN | Đèn LED chiếu gương D G02L/8w.DA |
| Q282 | Ai là nhà sản xuất/cung cấp Tôn PU (5 sóng) dày 0.50mm ở Hà Nội? | Công đoàn ty Thép Cổ phần Poshaco Tập | Tôn PU (5 sóng) dày 0.50mm |
| Q284 | Ai là nhà sản xuất/cung cấp TCLCĐ, BGLCD cao 11 m, vươn 1,5m, dày 3,0mm ở Hà Nội? | VONTA VIỆT NAM | TCLCĐ, BGLCD cao 11 m, vươn 1,5m, dày 3,0mm |
| Q294 | Ai là nhà sản xuất/cung cấp Sơn mịn nội thất cao cấp KUTO RUBY ở Hà Nội? | Hoàn mỹ | Sơn mịn nội thất cao cấp KUTO RUBY |
| Q299 | Ai là nhà sản xuất/cung cấp bột bả nội thất Jotun Interior Putty ở Hà Nội? | Sơn Jotun Việt Nam | bột bả nội thất Jotun Interior Putty |
| Q304 | Ai là nhà sản xuất/cung cấp Cáp ngầm 4x10 (7/1.35) ở Hà Nội? | Slighting Việt Nam | Cáp ngầm 4x10 (7/1.35) |
| Q307 | Ai là nhà sản xuất/cung cấp Cáp Cu/Mica/XLPE/PVC-Fr 4x10mm2 ở Hà Nội? | Slighting Việt Nam | Cáp Cu/Mica/XLPE/PVC-Fr 4x10mm2 |
| Q324 | Ai là nhà sản xuất/cung cấp bộ đèn đường Signify/Philips LED Roadflair Pro 140W (BRP593) ở Hà Nội? | điện và chiếu sáng phương đông | bộ đèn đường Signify/Philips LED Roadflair Pro 140W (BRP593) |
| Q329 | Ai là nhà sản xuất/cung cấp Đèn pha LED chiếu điểm FLAR, công suất 300W, ánh sáng RGBW lập trình DMX ở Hà Nội? | Slighting Việt Nam | Đèn pha LED chiếu điểm FLAR, công suất 300W, ánh sáng RGBW lập trình DMX |
| Q332 | Ai là nhà sản xuất/cung cấp Sơn lót chống kiềm ngoài trời đặc biệt NaNo ( 21kg/thùng ) ở Đà Nẵng? | SUZUMAX | Sơn lót chống kiềm ngoài trời đặc biệt NaNo ( 21kg/thùng ) |
| Q333 | Ai là nhà sản xuất/cung cấp Sơn sàn tự san phẳng phủ màu (tùy chọn) (15 lít/thùng) ở Đà Nẵng? | Sơn Thế Hệ Mới | Sơn sàn tự san phẳng phủ màu (tùy chọn) (15 lít/thùng) |
| Q336 | Ai là nhà sản xuất/cung cấp Gạch lát chống trơn 30*30 cm ở Hà Nội? | Sơn và Hóa chất Việt Nam | Gạch lát chống trơn 30*30 cm |
| Q339 | Ai là nhà sản xuất/cung cấp Tấm chắn rác kích thước 960x300x80(mm). Tải trọng 250KN ở Đà Nẵng? | Sông Hàn Invest | Tấm chắn rác kích thước 960x300x80(mm). Tải trọng 250KN |
| Q343 | Ai là nhà sản xuất/cung cấp Bóng đèn tuýp led thủy tinh T8 18W 1,2 m ánh sáng trắng ở Đà Nẵng? | Junsun Việt Nam | Bóng đèn tuýp led thủy tinh T8 18W 1,2 m ánh sáng trắng |
| Q344 | Ai là nhà sản xuất/cung cấp (400x400x30)mm màu ghi ở Đà Nẵng? | CN Gốm Sứ Taicera | (400x400x30)mm màu ghi |
| Q354 | Ai là nhà sản xuất/cung cấp Vữa khô trộn sẵn chống thấm ngược Victory Gold VTR7 (25kg/bao) ở Đà Nẵng? | Kim Toàn Phát | Vữa khô trộn sẵn chống thấm ngược Victory Gold VTR7 (25kg/bao) |
| Q359 | Ai là nhà sản xuất/cung cấp cần đèn l dài 2m dày 3mm ở Hà Nội? | điện và chiếu sáng phương đông | cần đèn l dài 2m dày 3mm |
| Q370 | Ai là nhà sản xuất/cung cấp Nút bịt hố ga 110 nhựa ở Hà Nội? | Composit Sao Đỏ | Nút bịt hố ga 110 nhựa |
| Q372 | Ai là nhà sản xuất/cung cấp Led Tapy LED TC30 HE 30W ở Đà Nẵng? | Công nghệ Tin học Viễn thông 5M | Led Tapy LED TC30 HE 30W |
| Q384 | Ai là nhà sản xuất/cung cấp Đèn LED chiếu sáng đường phố DPC03A 30-50W. hiệu suất phát quang bộ đèn >= 120Lm/W ở Đà Nẵng? | CHIẾU SÁNG CÔNG CỘNG ĐÀ NẴNG | Đèn LED chiếu sáng đường phố DPC03A 30-50W. hiệu suất phát quang bộ đèn >= 120Lm/W |
| Q390 | Ai là nhà sản xuất/cung cấp Ống uPVC C4 D60 ở Hà Nội? | PmT.Quang minh | Ống uPVC C4 D60 |
| Q396 | Ai là nhà sản xuất/cung cấp Sơn nội thất bóng TOGI T250 (Thùng18L:21Kg) ở Đà Nẵng? | Sơn Nikko Việt Nam | Sơn nội thất bóng TOGI T250 (Thùng18L:21Kg) |
| Q398 | Ai là nhà sản xuất/cung cấp Ngói bò nóc phẳng ở Hà Nội? | Tập | Ngói bò nóc phẳng |
| Q421 | Ai là nhà sản xuất/cung cấp Vonta - VT08D/250w - DIM ở Hà Nội? | VONTA VIỆT NAM | Vonta - VT08D/250w - DIM |
| Q432 | Ai là nhà sản xuất/cung cấp Cáp vặn xoắn ABC 2x25 mm2 ở Hà Nội? | Slighting Việt Nam | Cáp vặn xoắn ABC 2x25 mm2 |
| Q434 | Ai là nhà sản xuất/cung cấp Đai khởi thủy HDPE DN180x2" ở Hà Nội? | Composit Sao Đỏ | Đai khởi thủy HDPE DN180x2" |
| Q448 | Ai là nhà sản xuất/cung cấp Đai khởi thủy HDPE DN225x1/2" ở Hà Nội? | Composit Sao Đỏ | Đai khởi thủy HDPE DN225x1/2" |
| Q463 | Ai là nhà sản xuất/cung cấp Vòi chậu 2 đường nước CT561D ở Hà Nội? | Thương mại và sản xuất minh Quang | Vòi chậu 2 đường nước CT561D |
| Q470 | Ai là nhà sản xuất/cung cấp Ống ruột gà lõi thép bọc nhựa PVC màu đen 3/4" (D20) ở Hà Nội? | Slighting Việt Nam | Ống ruột gà lõi thép bọc nhựa PVC màu đen 3/4" (D20) |
| Q481 | Ai là nhà sản xuất/cung cấp Cáp ngầm hạ thế (3+1) lõi ,6V/1kV - Cu/XPLE/PVC/DSTA/PVC - Phú Thắng: DSTA 3x150+1x95mm2 ở Hà Nội? | Điện và Chiếu sáng Phú Thắng | Cáp ngầm hạ thế (3+1) lõi ,6V/1kV - Cu/XPLE/PVC/DSTA/PVC - Phú Thắng: DSTA 3x150+1x95mm2 |
| Q483 | Ai là nhà sản xuất/cung cấp Co nối chữ L có nắp phi 32 ở Đà Nẵng? | Bảo Phước | Co nối chữ L có nắp phi 32 |

### S3 · cấu trúc — tiêu chuẩn kỹ thuật (100 câu)

| mã | câu hỏi | đáp án | tên lưu trong DB |
|---|---|---|---|
| Q004 | Sơn lót kháng kiềm nội thất cao cấp ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BXD QCVN 08:2020/BCT | Sơn lót kháng kiềm nội thất cao cấp |
| Q010 | Ống HDPE PE100 DN40 PN16 ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BX D | Ống HDPE PE100 DN40 PN16 |
| Q019 | Bột trét tường NINOSHIELD ngoại thất,40Kg/Bao ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 7239:2014 | Bột trét tường NINOSHIELD ngoại thất,40Kg/Bao |
| Q024 | Class 4 Φ34 dầy 3.8 ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | ( TCVN 8491- 2:2011) | Class 4 Φ34 dầy 3.8 |
| Q028 | Chống thấm đa năng/ CT11A18 lít ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BXD | Chống thấm đa năng/ CT11A18 lít |
| Q030 | Class 1 Φ48 dầy 1.9 ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | ( TCVN 8491- 2:2011) | Class 1 Φ48 dầy 1.9 |
| Q033 | TOA 4 SEASONS TROPIC SHIELD SƠN NƯỚC NGOẠI THẤT (15L/thùng) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16: 2019/ BXD; QCVN 08: 2020/ BCT | TOA 4 SEASONS TROPIC SHIELD SƠN NƯỚC NGOẠI THẤT (15L/thùng) |
| Q043 | Ống HDPE PE100 DN20 PN12.5 ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BX D | Ống HDPE PE100 DN20 PN12.5 |
| Q049 | VCmt 2x2.5-500V BLACK ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 6610 | VCmt 2x2.5-500V BLACK |
| Q052 | Đèn đường LED Điện Quang LEDSL11 180W ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 7722-2-3:2019 | Đèn đường LED Điện Quang LEDSL11 180W |
| Q062 | FRN-CXV 3x16 ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 5935-1, IEC 60502- 1/IEC 60331/IEC 60332 | FRN-CXV 3x16 |
| Q073 | cột thép bát giác hoặc tròn côn 7m d78 dày 3.5mm ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | tccs 01:2018/pđ iso 9001:2015, iso 14001:2015 | cột thép bát giác hoặc tròn côn 7m d78 dày 3.5mm |
| Q074 | Gạch rỗng 3 lổ(90x190x390)mm ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16: 2019/BXD | Gạch rỗng 3 lổ(90x190x390)mm |
| Q080 | Đèn đường Led KC-RZ01B 80W-100W, tiết giảm công suất 2-5 cấp ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 7722-2-3:2019 (IEC 60598-2-3:2011) | Đèn đường Led KC-RZ01B 80W-100W, tiết giảm công suất 2-5 cấp |
| Q082 | TOA WALL MASTIC EXTERIOR BỘT TRÉT TOA CAO CẤP NGOẠI THẤT (40KG/bao) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 7239: 2014 | TOA WALL MASTIC EXTERIOR BỘT TRÉT TOA CAO CẤP NGOẠI THẤT (40KG/bao) |
| Q084 | Sơn (21kg/thùng) lót siêu kháng kiềm ngoại thất Rman-R97 ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BXD | Sơn (21kg/thùng) lót siêu kháng kiềm ngoại thất Rman-R97 |
| Q090 | Chống thấm gốc nước JOTON® CT-J-555 (18lít/thùng) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023 | Chống thấm gốc nước JOTON® CT-J-555 (18lít/thùng) |
| Q095 | Cột thép Bát giác, Tròn côn liền cần đơn, H=10m, D56/165, tôn dày 3,5mm ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | ISO 9001: 2015 | Cột thép Bát giác, Tròn côn liền cần đơn, H=10m, D56/165, tôn dày 3,5mm |
| Q096 | Màu đen ) Sơn sơn tĩnh 10 năm điện (Nâu cà phê, ghi, trắng sữa ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2019 TCVN 12513-2:2018 | Màu đen ) Sơn sơn tĩnh 10 năm điện (Nâu cà phê, ghi, trắng sữa |
| Q102 | Sơn chống thấm bề mặt xi măng và đá (3.8L/thùng) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BXD | Sơn chống thấm bề mặt xi măng và đá (3.8L/thùng) |
| Q104 | Sơn chống thấm tường NINO - CT FLEX ,04L/lon ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 8652:2014 | Sơn chống thấm tường NINO - CT FLEX ,04L/lon |
| Q105 | Gạch chữ H (320x270x60)mm, M600 ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 6477:2016 | Gạch chữ H (320x270x60)mm, M600 |
| Q118 | DATA/CTS-W 1x50-40.5kV ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 5935-2/IEC 60502-2 | DATA/CTS-W 1x50-40.5kV |
| Q123 | Sơn không bóng ngoại thất cao cấp ( NEWTECOAT CLEAR-02 ) ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/ BXD | Sơn không bóng ngoại thất cao cấp ( NEWTECOAT CLEAR-02 ) |
| Q124 | Sơn Acrylic gốc nước (Sơn bê tông - màu Đen) ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 8652:2020 | Sơn Acrylic gốc nước (Sơn bê tông - màu Đen) |
| Q131 | DHP-STR15B 100W ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | CE, ENEC, IEC60598-2-3, RoHS… | DHP-STR15B 100W |
| Q135 | Đèn led pha CDE-FL150W, công suất 150W ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | IEC 62262:2002, IEC 61643-11:2011 | Đèn led pha CDE-FL150W, công suất 150W |
| Q150 | Gạch Porcelain in KTS, hiệu ứng Carving gold 800x800mm - Nhóm BIa xương 11mm ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BXD | Gạch Porcelain in KTS, hiệu ứng Carving gold 800x800mm - Nhóm BIa xương 11mm |
| Q154 | Y lọc gang Wonil - Hàn Quốc DN80 ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | Nối bích tiêu chuẩn BS/JIS10K | Y lọc gang Wonil - Hàn Quốc DN80 |
| Q158 | L63x63x6, L=2500mm, râu thép D10 kèm tai bắt ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCCS 01:2018/VIETHAI ISO 9001:2015 ISO 14001:2015 | L63x63x6, L=2500mm, râu thép D10 kèm tai bắt |
| Q159 | Vữa xây dựng SCL-Mortar M5.0 (đóng gói 50 kg/bao - loại trát) ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 4314:2022 | Vữa xây dựng SCL-Mortar M5.0 (đóng gói 50 kg/bao - loại trát) |
| Q163 | Bồn cầu một khối Bravat C21273W-3-VN ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | ISO9001 ISO14001 ISO45001 | Bồn cầu một khối Bravat C21273W-3-VN |
| Q173 | Sơn chống thấm màu Lotus- mCT ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | QCVN TCVN TCVN 08:2020/BCT 9014:2011 8652:2020 | Sơn chống thấm màu Lotus- mCT |
| Q182 | DATA/CTS-W 1x300-40.5kV ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 5935-2/IEC 60502-2 | DATA/CTS-W 1x300-40.5kV |
| Q189 | Xi măng bao MC25 ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 9202:2012 | Xi măng bao MC25 |
| Q195 | Sơn ngoại thất cao cấp (Onip RS) ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BXD | Sơn ngoại thất cao cấp (Onip RS) |
| Q196 | Sơn lót kháng kiềm nội thất 23kg/thùng ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 8652 - 2020 | Sơn lót kháng kiềm nội thất 23kg/thùng |
| Q198 | Hoda Natural Granite - HNG ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BXD QCVN 08:2020/BCT | Hoda Natural Granite - HNG |
| Q200 | FRN-CXV 3x120+1x95 ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | 1/IEC 60331/IEC 60332 | FRN-CXV 3x120+1x95 |
| Q209 | DSTA/CTS-W 3x300-40.5kV ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 5935-2/IEC 60502-2 | DSTA/CTS-W 3x300-40.5kV |
| Q213 | Vonta - VT23D/80w - DIM - S ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 7722-1:2017; TCVN 7722-2-3:2019 | Vonta - VT23D/80w - DIM - S |
| Q215 | Ống thép đen Hoa Sen ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN, ASTM | Ống thép đen Hoa Sen |
| Q227 | Đèn đường Led KC-DL37A 80W-100W, tiết giảm công suất 2-5 cấp ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 7722-2-3:2019 (IEC 60598-2-3:2011) | Đèn đường Led KC-DL37A 80W-100W, tiết giảm công suất 2-5 cấp |
| Q230 | Đèn đường Led KC-DL13A 50W, tiết giảm công suất 2-5 cấp ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 7722-2-3:2019 (IEC 60598-2-3:2011) | Đèn đường Led KC-DL13A 50W, tiết giảm công suất 2-5 cấp |
| Q238 | Xi măng bao Bút Sơn Xanh đa dụng PCB30 vỏ PP công trình ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 6260:2009 | Xi măng bao Bút Sơn Xanh đa dụng PCB30 vỏ PP công trình |
| Q241 | Kính dán an toàn nhiều lớp 25,52mm (12mm kính tôi nhiệt +1,52mm PVB 12mm kính tôi nhiệt) ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BXD | Kính dán an toàn nhiều lớp 25,52mm (12mm kính tôi nhiệt +1,52mm PVB 12mm kính tôi nhiệt) |
| Q245 | Gạch Porcelain bóng toàn phần 60x120cm ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BXD | Gạch Porcelain bóng toàn phần 60x120cm |
| Q266 | TOA HYDRO QUICK PRIMER SƠN LÓT ĐA NĂNG CAO CẤP (18L/thùng) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16: 2023/ BXD; QCVN 08: 2020/ BCT | TOA HYDRO QUICK PRIMER SƠN LÓT ĐA NĂNG CAO CẤP (18L/thùng) |
| Q268 | Gạch Porcelain in KTS men matt, hiệu ứng Structured 150x900mm - Nhóm BIa ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BXD | Gạch Porcelain in KTS men matt, hiệu ứng Structured 150x900mm - Nhóm BIa |
| Q269 | Ống ruột gà lõi thép bọc nhựa PVC màu đen 1 1/2" (D40) ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | BS 731 | Ống ruột gà lõi thép bọc nhựa PVC màu đen 1 1/2" (D40) |
| Q272 | Thép thanh vằn d22 CB400-V ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 1651-2:2018 | Thép thanh vằn d22 CB400-V |
| Q273 | Chất trám khe một thành phần gốc polyurethan cao cấp - GPS® Sealant 888 ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | ASTM D792-13 ASTM D2240 ASTM D412 ASTM D5893 | Chất trám khe một thành phần gốc polyurethan cao cấp - GPS® Sealant 888 |
| Q277 | TOA NANOSHIELD BÓNG MỜ SƠN NƯỚC NGOẠI THẤT CAO CẤP (5L/lon) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16: 2019/ BXD; QCVN 08: 2020/ BCT | TOA NANOSHIELD BÓNG MỜ SƠN NƯỚC NGOẠI THẤT CAO CẤP (5L/lon) |
| Q286 | Sơn phủ bóng Clear ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | QCVN16:2023/BXD QCVN 08:2020/BCT | Sơn phủ bóng Clear |
| Q290 | Sơn nội thất bóng cao cấp FUJISU Edo (5.1kg/lon nhựa) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2019 | Sơn nội thất bóng cao cấp FUJISU Edo (5.1kg/lon nhựa) |
| Q301 | DHP-STR15B 120W ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | CE, ENEC, IEC60598-2-3, RoHS… | DHP-STR15B 120W |
| Q308 | Đèn đường Led KC-P09B 100W, tiết giảm công suất 2-5 cấp ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 7722-2-3:2019 (IEC 60598-2-3:2011) | Đèn đường Led KC-P09B 100W, tiết giảm công suất 2-5 cấp |
| Q315 | Đèn đường Led KC-P2B 90W, tiết giảm công suất 2-5 cấp ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 7722-2-3:2019 (IEC 60598-2-3:2011) | Đèn đường Led KC-P2B 90W, tiết giảm công suất 2-5 cấp |
| Q320 | CHỐNG THẤM MÀU TOA WATERBLOCK COLOR (20KG/thùng) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16: 2019/ BXD; QCVN 08: 2020/ BCT | CHỐNG THẤM MÀU TOA WATERBLOCK COLOR (20KG/thùng) |
| Q322 | Nắp hố ga Composite, Gang 900x900 tải trọng 12.5 tấn ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | BS ISO ISO EN 14001-2015 9001:2015 124-2:2015 | Nắp hố ga Composite, Gang 900x900 tải trọng 12.5 tấn |
| Q326 | Gạch Porcelain in KTS, Anti-slip/Chống trơn 600x600mm - Nhóm BIa xương 10mm ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BXD | Gạch Porcelain in KTS, Anti-slip/Chống trơn 600x600mm - Nhóm BIa xương 10mm |
| Q327 | Class 0 Φ42 dầy 1.5 ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | ( TCVN 8491- 2:2011) | Class 0 Φ42 dầy 1.5 |
| Q338 | Băng cản nước PVC xử lý mạch ngừng bê tông - GPS ® Waterstop V150,(20m/ cuộn) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | BS EN 14891: 2017 | Băng cản nước PVC xử lý mạch ngừng bê tông - GPS ® Waterstop V150,(20m/ cuộn) |
| Q345 | Sơn mịn ngoại thất cao cấp SMOOTH-05 (5lít/lon) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 8652:2020 | Sơn mịn ngoại thất cao cấp SMOOTH-05 (5lít/lon) |
| Q347 | Sơn nội thất siêu bóng ánh ngọc FUJISU Tama (19kg/thùng) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2019 | Sơn nội thất siêu bóng ánh ngọc FUJISU Tama (19kg/thùng) |
| Q352 | Khung bulong neo PHL-RD300,Khung bulong neo móng trụ đèn 300x300x700 ø 22 mạ kẽm đầu ren ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | ISO ISO 14001:2015 9001:2015; EN40 BS5649 | Khung bulong neo PHL-RD300,Khung bulong neo móng trụ đèn 300x300x700 ø 22 mạ kẽm đầu ren |
| Q361 | Ống ruột gà lõi thép bọc nhựa PVC màu đen 1/2" (D15) ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | BS 731 | Ống ruột gà lõi thép bọc nhựa PVC màu đen 1/2" (D15) |
| Q363 | TOA NANOSHIELD SEALER SƠN LÓT CHỐNG KIỀM NGOẠI THẤT CAO CẤP (15L/thùng) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16: 2023/ BXD; QCVN 08: 2020/ BCT | TOA NANOSHIELD SEALER SƠN LÓT CHỐNG KIỀM NGOẠI THẤT CAO CẤP (15L/thùng) |
| Q364 | Ống HDPE PE100 DN63 PN6 ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BX D | Ống HDPE PE100 DN63 PN6 |
| Q365 | Vật liệu chống thấm CX MEN GOLD,25kg ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 8826:2011 | Vật liệu chống thấm CX MEN GOLD,25kg |
| Q369 | Sơn phủ chống nóng và chống thấm (15 lít/thùng) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BXD | Sơn phủ chống nóng và chống thấm (15 lít/thùng) |
| Q383 | POLYME CẤU KIỆN ĐÚC KÈ SẴN BÊ TÔNG M500 tính CỐT năng SỢI cao ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 1:2019; 22604- 3:2018 1239 | POLYME CẤU KIỆN ĐÚC KÈ SẴN BÊ TÔNG M500 tính CỐT năng SỢI cao |
| Q385 | Thép thanh vằn d14 CB300-V ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 1651-2:2018 | Thép thanh vằn d14 CB300-V |
| Q389 | DATA/CTS-W 1x120-40.5kV ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 5935-2/IEC 60502-2 | DATA/CTS-W 1x120-40.5kV |
| Q391 | Sơn men sứ ngoại thất đặc biệt 15kg/thùng ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BXD | Sơn men sứ ngoại thất đặc biệt 15kg/thùng |
| Q393 | tôn Suntek EC11 - 11sóng, dày 0,45mm ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | JIS G3322:2013 | tôn Suntek EC11 - 11sóng, dày 0,45mm |
| Q397 | Gạch rỗng 6 lổ(90x135x190)mm ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16: 2019/BXD | Gạch rỗng 6 lổ(90x135x190)mm |
| Q402 | ADSTA/CTS-W 3x300-24kV ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 5935-2/IEC 60502-2 | ADSTA/CTS-W 3x300-24kV |
| Q403 | Lót kháng kiềm ngoại thất Nano/ PRIME.NANO.EXT5 lít ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 8652:2020 | Lót kháng kiềm ngoại thất Nano/ PRIME.NANO.EXT5 lít |
| Q410 | Cột bát giác, tròn côn H=8m, dày 4mm, bích đế 400x400 ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | ISO ISO 14001-2015 9001:2015 | Cột bát giác, tròn côn H=8m, dày 4mm, bích đế 400x400 |
| Q417 | Gạch ngói gốm tráng men, Nhóm gạch BIII nhãn hiệu Viglacera, mã ngói uno: Ngói UN03,06 ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | QCVN16:2019/ BXD TCVN 13113:2020 | Gạch ngói gốm tráng men, Nhóm gạch BIII nhãn hiệu Viglacera, mã ngói uno: Ngói UN03,06 |
| Q419 | TOA NANOSHIELD SEALER SƠN LÓT CHỐNG KIỀM NGOẠI THẤT CAO CẤP (18L/thùng) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16: 2023/ BXD; QCVN 08: 2020/ BCT | TOA NANOSHIELD SEALER SƠN LÓT CHỐNG KIỀM NGOẠI THẤT CAO CẤP (18L/thùng) |
| Q423 | Hodapaint Zelos Opal for Exterior Sơn nước Zelos ngoại thất hoàn thiện ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BXD QCVN 08:2020/BCT | Hodapaint Zelos Opal for Exterior Sơn nước Zelos ngoại thất hoàn thiện |
| Q426 | Đèn đường Led KC-DL18D 200W, tiết giảm công suất 2-5 cấp ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 7722-2-3:2019 (IEC 60598-2-3:2011) | Đèn đường Led KC-DL18D 200W, tiết giảm công suất 2-5 cấp |
| Q429 | BỆ Màu XÍ Anode KÉT LIỀN vàng bóng ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 12651:2020 | BỆ Màu XÍ Anode KÉT LIỀN vàng bóng |
| Q436 | Sơn lót kháng kiềm nội thất Rman-R90 (21kg/thùng) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16:2023/BXD | Sơn lót kháng kiềm nội thất Rman-R90 (21kg/thùng) |
| Q437 | Khớp nối mềm cao su bích inox 304 Wonil - Hàn Quốc DN150 ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | Nối bích tiêu chuẩn BS/JIS10K | Khớp nối mềm cao su bích inox 304 Wonil - Hàn Quốc DN150 |
| Q440 | Vỏ tủ đựng thiết bị NLMT ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | ISO 9001-2015 ISO 14001:2015 TCVN 7994-1:2009 | Vỏ tủ đựng thiết bị NLMT |
| Q444 | Vữa dán gạch gốc xi măng -C1 ( Keo dán gạch C1) ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN7899- 1:2008/ISO13007 - 1:2004 | Vữa dán gạch gốc xi măng -C1 ( Keo dán gạch C1) |
| Q459 | Cầu dao 1 pha 25A MP6-C125 ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 6434-1: 2018 IEC 60898-1: 2015 | Cầu dao 1 pha 25A MP6-C125 |
| Q460 | Vữa xây dựng SCL-Mortar M7.5 (bao jumbo 1.500 kg/bao - loại xây) ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 4314:2022 | Vữa xây dựng SCL-Mortar M7.5 (bao jumbo 1.500 kg/bao - loại xây) |
| Q462 | Gạch terazo màu ghi 400x400x30 ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 7744:2013 | Gạch terazo màu ghi 400x400x30 |
| Q464 | SUPERTECH PRO NỘI THẤT SIÊU TRẮNG SƠN NƯỚC NỘI THẤT (5L/lon) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 16: 2023/ BXD; QCVN 08: 2020/ BCT | SUPERTECH PRO NỘI THẤT SIÊU TRẮNG SƠN NƯỚC NỘI THẤT (5L/lon) |
| Q469 | Đèn LED thanh BARART, công suất 12W, ánh sáng RGBW lập trình DMX ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | 1:2017 TCVN (IEC 7722-2-3:2019 60598-1 :2014) | Đèn LED thanh BARART, công suất 12W, ánh sáng RGBW lập trình DMX |
| Q482 | Sơn sàn Epoxy lót (5 lít/Thùng) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | QCVN 08:2020/BCT | Sơn sàn Epoxy lót (5 lít/Thùng) |
| Q484 | Xi măng trây cát chống thấm Victory G20 VTR3 (40kg/bao) ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | TCVN9202:2012 TCVN4314:2022 TCVN7239:2014 TCVN4314:2022 | Xi măng trây cát chống thấm Victory G20 VTR3 (40kg/bao) |
| Q486 | Đèn đường Led KC-HR15 120W, tiết giảm công suất 2-5 cấp ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 7722-2-3:2019 (IEC 60598-2-3:2011) | Đèn đường Led KC-HR15 120W, tiết giảm công suất 2-5 cấp |
| Q496 | Đèn chiếu sáng đường phố LED NIKA, công suất 100W có tích hợp bộ điều khiển thông minh LCU ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | ISO 9001: 2015, ISO | Đèn chiếu sáng đường phố LED NIKA, công suất 100W có tích hợp bộ điều khiển thông minh LCU |
| Q497 | Đèn Led đường phố CHI-150W, DIM ở Hà Nội áp dụng tiêu chuẩn kỹ thuật nào? | (ISO 9001:2015) | Đèn Led đường phố CHI-150W, DIM |
| Q498 | Gạch rỗng 4 lỗ 190*190*390 mm ở Đà Nẵng áp dụng tiêu chuẩn kỹ thuật nào? | TCVN 6477:2016 | Gạch rỗng 4 lỗ 190*190*390 mm |

### S4 · cấu trúc — cơ sở giá (40 câu)

| mã | câu hỏi | đáp án | tên lưu trong DB |
|---|---|---|---|
| Q007 | Giá SUPERTECH PRO SEALER SƠN LÓT CHỐNG KIỀM NGOẠI THẤT (15L/thùng) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | SUPERTECH PRO SEALER SƠN LÓT CHỐNG KIỀM NGOẠI THẤT (15L/thùng) |
| Q008 | Giá Sơn lót kháng kiềm Ngoại thất cao cấp 18 Lít ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Sơn lót kháng kiềm Ngoại thất cao cấp 18 Lít |
| Q020 | Giá SƠN LÓT CHỐNG RỈ ĐỎ HOMECOTE KHÔ NHANH (17.5L/thùng) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | SƠN LÓT CHỐNG RỈ ĐỎ HOMECOTE KHÔ NHANH (17.5L/thùng) |
| Q040 | Giá Vữa xi măng khô trộn sẵn không co - GPS® GROUT M80,(25kg/bao) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Vữa xi măng khô trộn sẵn không co - GPS® GROUT M80,(25kg/bao) |
| Q042 | Giá Bóng mờ ngoại thất MATTE GLOSS.EXT18 lít ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Bóng mờ ngoại thất MATTE GLOSS.EXT18 lít |
| Q058 | Giá Sơn chống thấm màu vượt trội Ultra Prevent (17L/thùng) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Sơn chống thấm màu vượt trội Ultra Prevent (17L/thùng) |
| Q061 | Giá TOA HYDRO QUICK PRIMER SƠN LÓT ĐA NĂNG CAO CẤP (5L/lon) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | TOA HYDRO QUICK PRIMER SƠN LÓT ĐA NĂNG CAO CẤP (5L/lon) |
| Q076 | Giá BestLatex R126 - thùng 25 lít ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | BestLatex R126 - thùng 25 lít |
| Q079 | Giá SƠN LÓT CHỐNG RỈ ĐỎ CON VỊT KHÔ NHANH (17.5L/thùng) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | SƠN LÓT CHỐNG RỈ ĐỎ CON VỊT KHÔ NHANH (17.5L/thùng) |
| Q088 | Giá Hào kỹ thuật 3 ngăn – Vỉa hè, Kt: B400x300x300- H500mm ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Hào kỹ thuật 3 ngăn – Vỉa hè, Kt: B400x300x300- H500mm |
| Q097 | Giá Bột bả ngoại thất cao cấp Gildden ( 40Kg) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Bột bả ngoại thất cao cấp Gildden ( 40Kg) |
| Q130 | Giá Thép vằn f 10 CB400 V, CB500 V ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Thép vằn f 10 CB400 V, CB500 V |
| Q145 | Giá Băng cản nước PVC xử lý mạch ngừng bê tông - GPS ® Waterstop O300,(20m/ cuộn) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Băng cản nước PVC xử lý mạch ngừng bê tông - GPS ® Waterstop O300,(20m/ cuộn) |
| Q149 | Giá Sơn bóng mờ nội thất cao cấp (5 Lít/ lon) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Sơn bóng mờ nội thất cao cấp (5 Lít/ lon) |
| Q161 | Giá Màu Anode vàng bóng ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Màu Anode vàng bóng |
| Q169 | Giá Sơn ngoại thất siêu bóng hợp kim, chống nóng tốt KATA Platin (5.2kg/lon nhựa) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Sơn ngoại thất siêu bóng hợp kim, chống nóng tốt KATA Platin (5.2kg/lon nhựa) |
| Q178 | Giá Vữa xi măng khô trộn sẵn không co - GPS® GROUT M50,(25kg/bao) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Vữa xi măng khô trộn sẵn không co - GPS® GROUT M50,(25kg/bao) |
| Q193 | Giá Sơn nội thất siêu bóng ánh ngọc SUMO Rose (19kg/thùng) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Sơn nội thất siêu bóng ánh ngọc SUMO Rose (19kg/thùng) |
| Q208 | Giá Băng cản nước PVC xử lý mạch ngừng bê tông - GPS ® Waterstop O250,(20m/ cuộn) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Băng cản nước PVC xử lý mạch ngừng bê tông - GPS ® Waterstop O250,(20m/ cuộn) |
| Q211 | Giá Super R7 - thùng 25 lít ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Super R7 - thùng 25 lít |
| Q212 | Giá Chậu rửa lắp bàn CI11, CL11 ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Chậu rửa lắp bàn CI11, CL11 |
| Q216 | Giá Sơn lót ngoại thất (15lit/thùng) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Sơn lót ngoại thất (15lit/thùng) |
| Q225 | Giá Dùng phụ gia phát triển cường độ sớm R4>90% cường độ yêu cầu ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Dùng phụ gia phát triển cường độ sớm R4>90% cường độ yêu cầu |
| Q228 | Giá Thép vằn f 10 Gr40 ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Thép vằn f 10 Gr40 |
| Q232 | Giá Sơn nội thất lau chùi hiệu quả SMARTLITE trắng, màu,01Kg/lon ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Sơn nội thất lau chùi hiệu quả SMARTLITE trắng, màu,01Kg/lon |
| Q247 | Giá Vữa xi măng khô trộn sẵn không co - GPS® GROUT M40,(25kg/bao) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Vữa xi măng khô trộn sẵn không co - GPS® GROUT M40,(25kg/bao) |
| Q253 | Giá Sơn mịn ngoại thất cao cấp/ GOLD.EXT1 lít ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Sơn mịn ngoại thất cao cấp/ GOLD.EXT1 lít |
| Q297 | Giá BestSeal AC404 - thùng 25 lít ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | BestSeal AC404 - thùng 25 lít |
| Q300 | Giá 850x850 tải trọng 25 tấn ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | 850x850 tải trọng 25 tấn |
| Q317 | Giá Cửa đi 1 cánh mở quay: Thanh profile Adamas/ Việt Pháp Shal hệ Xingfa(XF) 55, dày 1.6mm ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Cửa đi 1 cánh mở quay: Thanh profile Adamas/ Việt Pháp Shal hệ Xingfa(XF) 55, dày 1.6mm |
| Q328 | Giá TOA 4 SEASONS TOP SILK SƠN NƯỚC NỘI THẤT (15L/thùng) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | TOA 4 SEASONS TOP SILK SƠN NƯỚC NỘI THẤT (15L/thùng) |
| Q341 | Giá Chống thấm 2 thành phần Vipri trust,10 lít ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Chống thấm 2 thành phần Vipri trust,10 lít |
| Q350 | Giá Chất chống thấm 2 thành phần (40kg/ bộ) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Chất chống thấm 2 thành phần (40kg/ bộ) |
| Q360 | Giá Cửa sổ mở quay nhôm Xingfa hệ 55 Namsung ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Cửa sổ mở quay nhôm Xingfa hệ 55 Namsung |
| Q371 | Giá Sơn Epoxy lót sàn tự san phẳng (18lit/thùng) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Sơn Epoxy lót sàn tự san phẳng (18lit/thùng) |
| Q374 | Giá Cửa đi 2 cánh mở trượt: Thanh profile Adamas/ Việt Pháp Shal hệ Xingfa(XF) 93, dày 2.0mm ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Cửa đi 2 cánh mở trượt: Thanh profile Adamas/ Việt Pháp Shal hệ Xingfa(XF) 93, dày 2.0mm |
| Q381 | Giá Sơn ngoại thất che phủ hiệu quả KATA Green (5.8kg/lon nhựa) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Sơn ngoại thất che phủ hiệu quả KATA Green (5.8kg/lon nhựa) |
| Q413 | Giá TOA NANOSHIELD SEALER SƠN LÓT CHỐNG KIỀM NGOẠI THẤT CAO CẤP (18L/thùng) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | TOA NANOSHIELD SEALER SƠN LÓT CHỐNG KIỀM NGOẠI THẤT CAO CẤP (18L/thùng) |
| Q425 | Giá Xi măng Sông Gianh PCB30 (đóng bao) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Xi măng Sông Gianh PCB30 (đóng bao) |
| Q478 | Giá Sơn nước ngoại thất cao cấp, bền màu TERRASHIELD (Màu trắng) (05 lít/Thùng) ở Đà Nẵng là giá tại nơi sản xuất hay tại chân công trình? | chân công trình | Sơn nước ngoại thất cao cấp, bền màu TERRASHIELD (Màu trắng) (05 lít/Thùng) |
