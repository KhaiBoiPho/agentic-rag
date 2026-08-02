# Báo cáo kỹ thuật — chọn trần chunk và đánh giá chế độ Agentic

Tài liệu này trả lời ba câu hỏi bằng số đo trên chính dữ liệu của dự án:

1. **Vì sao trần chunk bảng là 3.000 token** — không phải 800, không phải
   1.500, không phải bỏ trần. → mục 2
2. **Cấu hình embedding × model sinh nào cho chất lượng trả lời tốt nhất**,
   đo trên bộ 30 câu hỏi ở
   [bo-cau-hoi-benchmark.md](bo-cau-hoi-benchmark.md). → mục 3.3
3. **Nếu bỏ hoàn toàn công cụ, chỉ dùng RAG thuần thì mất gì** — và model
   sinh mạnh hơn có bù lại được không. → mục 3.4

Kết quả tóm tắt trong một bảng:

| | có công cụ | RAG thuần |
|---|---:|---:|
| small + gpt-4o-mini *(đang chạy thật)* | 26/30 | 10/30 |
| voyage + gpt-4o-mini | 26/30 | 12/30 |
| small + gemini-2.5-pro | 22/30 | 10/30 |
| voyage + gemini-2.5-pro | **27/30** | **21/30** |

Ba điều đáng chú ý nhất, giải thích ở mục 4:

- Bỏ công cụ **không** làm hệ thống trả lời thiếu, nó làm hệ thống **trả lời
  sai** — nêu giá của sản phẩm khác, chắc nịch, không dấu hiệu nghi ngờ.
- Đổi riêng embedding được **+2**, đổi riêng model sinh được **+0**, đổi cả
  hai được **+11**. Hai thay đổi chỉ có tác dụng khi đi cùng nhau.
- Model sinh mạnh hơn mà giữ nguyên tầng truy hồi thì **kém đi** (22 < 26),
  và chậm hơn gần 5 lần.

Mọi con số dưới đây đều tái lập được bằng các script trong `scripts/`; mỗi
mục ghi rõ script nào sinh ra nó.

---

## 1. Bối cảnh — vì sao trần chunk lại là một câu hỏi

Kho tri thức của hệ thống chủ yếu là **phụ lục công bố giá vật liệu xây
dựng**: các bảng dài hàng nghìn dòng, mỗi dòng một sản phẩm. Bộ chunker biến
mỗi bảng trong PDF thành **một chunk HTML** (§2.5–2.7 của
[kien-truc-chi-tiet.md](kien-truc-chi-tiet.md)).

Điều đó tạo ra một chunk rất lớn. Ban đầu chỉ có một ràng buộc duy nhất:

> `MAX_EMBED_TOKENS = 8000` — giới hạn **kỹ thuật** của API embedding.
> Vượt quá thì cả lô request bị từ chối.

Ràng buộc này chỉ trả lời câu hỏi *"chunk lớn nhất mà API chịu nhận là bao
nhiêu"*. Nó **không** trả lời câu hỏi thực sự quan trọng:

> *Chunk lớn nhất mà việc truy hồi còn **có ích** là bao nhiêu?*

Hai câu hỏi này khác nhau, và sự khác nhau đó là nội dung của mục 2.

### 1.1. Chỗ nghẽn quan sát được

Với câu hỏi *"dây cáp điện lực CADIVI giá bao nhiêu"*, truy hồi **không hề
xếp hạng sai**: chunk đứng đầu đúng là bảng chứa giá CADIVI. Nhưng bảng đó
dài tới ~7.900 token và cửa sổ `top_k = 5` chỉ mang về được **51 trong số
242** đơn giá CADIVI có trong `material_prices`.

Nghĩa là vấn đề không nằm ở *xếp hạng* (ranking) mà ở **độ phủ** (coverage):
một ô trong năm ô của cửa sổ bị chiếm bởi một bảng khổng lồ, phần lớn nội
dung của nó không liên quan tới câu hỏi.

Đây là lý do trần truy hồi tồn tại **độc lập** với trần API.

---

## 2. Vì sao 3.000 token

### 2.1. Phép đo

Script: [`scripts/eval_chunk_cap.py`](../scripts/eval_chunk_cap.py)

Cách cắt giống hệt cách `split_oversized_table_chunk` đang làm — cắt **theo
hàng**, và **lặp lại hàng header trong mọi mảnh** để mảnh phía sau không mất
nhãn cột. Chỉ thay đổi hạn mức token.

Ba chỉ số được đo trên cùng một tập chunk:

| chỉ số | ý nghĩa |
|---|---|
| `recall@5` | trong 16 câu hỏi khó, bao nhiêu câu có chunk chứa đáp án lọt top-5 |
| `phủ CADIVI` | trong 242 đơn giá CADIVI, bao nhiêu giá thực sự nằm trong cửa sổ top-5 |
| `token/5chunk` | giá phải trả: tổng token của cửa sổ |

### 2.2. Kết quả

| trần token | số chunk | recall@5 | **phủ CADIVI @top-5** | @top-10 | token/5 chunk |
|---:|---:|---:|---:|---:|---:|
| không có | 1.333 | 14/16 | 51/242 | 63/242 | 19.842 |
| **3.000** | **1.652** | **14/16** | **78/242** | **112/242** | **12.410** |
| 1.500 | 2.411 | 13/16 | 41/242 | 76/242 | 6.980 |
| 800 | 4.769 | 12/16 | 18/242 | 39/242 | 3.744 |

Hình dạng của cột "phủ" là điều đáng chú ý nhất — **nó không đơn điệu**:

```
  phủ CADIVI @top-5
  80 │            ●  78          ← 3.000
     │
  60 │
     │  ●  51                    ← không trần
  40 │                  ●  41    ← 1.500
     │
  20 │                        ●  18   ← 800
     └──────────────────────────────────
       không   3000   1500    800
```

Trực giác "chunk càng nhỏ thì truy hồi càng chính xác" **sai** trên bài toán
này. Độ phủ đạt đỉnh ở 3.000 rồi **tụt xuống dưới cả mức không cắt gì**.

### 2.3. Vì sao cắt nhỏ hơn lại tệ đi — ba nguyên nhân đo được

**(a) Mỗi mảnh mang quá ít dòng.**
Cửa sổ chỉ có 5 ô. Ở trần 800, mỗi mảnh chỉ còn khoảng 8–12 dòng sản phẩm,
nên 5 ô cộng lại vẫn ít hơn một bảng 3.000 token duy nhất. Cắt nhỏ làm tăng
*số* chunk trúng, nhưng giảm *lượng dữ liệu* mỗi chunk mang theo — và ở đây
vế thứ hai thắng.

**(b) Header lặp lại ăn mất ngân sách.**
Mỗi mảnh phải chép lại hàng header. Chi phí cố định đó chiếm tỷ lệ ngày càng
lớn khi mảnh càng nhỏ:

| trần | header chiếm |
|---:|---:|
| 3.000 | **+3 %** |
| 1.500 | +11 % |
| 800 | **+22 %** |

Ở trần 800, hơn một phần năm số token được embed là **nhãn cột lặp đi lặp
lại**, không phải dữ liệu.

**(c) Các mảnh cùng một bảng embed gần trùng nhau.**
Script: [`scripts/eval_intra_table_sim.py`](../scripts/eval_intra_table_sim.py)

Đây là nguyên nhân tinh vi nhất, và là lý do (b) không chỉ là chuyện lãng phí
token. Header giống nhau kéo vector của các mảnh **xích lại gần nhau**. Đo
cosine giữa mọi cặp mảnh **cùng một bảng**:

| | trần 3.000 | trần 800 |
|---|---:|---:|
| số bảng bị cắt | 145 | 827 |
| số mảnh | 319 | 3.436 |
| số cặp cùng bảng | 205 | 7.954 |
| trung vị cosine | 0,9338 | 0,9507 |
| tỷ lệ cặp ≥ 0,95 | 40,0 % | 50,4 % |
| **tỷ lệ cặp ≥ 0,98** | **13,2 %** | **24,8 %** |

Ở trần 800, **một phần tư** số cặp mảnh cùng bảng có cosine ≥ 0,98 — tức là
gần như **không phân biệt được** bằng vector. Truy hồi không có cơ sở nào để
ưu tiên đúng mảnh chứa đáp án; nó hoặc nuốt vài mảnh gần trùng vào cửa sổ
(lãng phí ô), hoặc lấy nhầm mảnh bên cạnh. Tỷ lệ này ở trần 3.000 chỉ bằng
**một nửa**.

### 2.4. Vì sao không giữ nguyên không cắt

Bảng nguyên khối vẫn **được xếp hạng đúng** (recall@5 = 14/16, bằng mức
3.000), nhưng chỉ mang về 51/242 đơn giá trong khi tiêu tốn **19.842 token**
cho cửa sổ. Trần 3.000 cho độ phủ **cao hơn 53 %** với chi phí token **thấp
hơn 37 %**.

### 2.5. Số liệu này đo trên bản dữ liệu nào

Bảng ở §2.2 và §2.3 chạy trên bản corpus **trước** khi sửa hai lỗi trích giá
(§0B.7 của [kien-truc-chi-tiet.md](kien-truc-chi-tiet.md)): số bị khoảng trắng
cắt cụt, và lưới bảng khuyết bị coi là ô gộp. Sau khi sửa, corpus tăng từ
1.333 lên **2.294 chunk** và từ 11.508 lên **18.551 dòng giá**.

Điều đó **không** làm hỏng kết luận, vì cả bốn mức trần đều đo trên **cùng
một tập chunk** — phép so sánh là nội bộ. Nhưng **giá trị tuyệt đối** của cột
"phủ CADIVI" sẽ đổi trên corpus mới, nên nếu trích dẫn con số cụ thể thì phải
chạy lại `eval_chunk_cap.py` (mục 5) chứ đừng chép lại bảng này.

### 2.6. Kết luận

3.000 là điểm mà ba lực đối nghịch cân bằng: đủ lớn để mỗi mảnh mang được
lượng dòng có nghĩa và để header chỉ là chi phí biên (3 %), đủ nhỏ để một
bảng khổng lồ không chiếm trọn cửa sổ. Giá trị này được ghi vào
`MAX_TABLE_CHUNK_TOKENS` trong
[`app/core/chunking/base.py`](../app/core/chunking/base.py), tách bạch với
`MAX_EMBED_TOKENS = 8000` vốn là giới hạn kỹ thuật của API.

> **Lưu ý về tính tổng quát:** con số 3.000 gắn với **hình dạng dữ liệu này**
> (bảng giá nhiều cột, mỗi dòng một sản phẩm, `top_k = 5`). Nó không phải
> hằng số phổ quát. Nếu `top_k` tăng, hoặc corpus chuyển sang văn xuôi, phép
> đo phải chạy lại — `eval_chunk_cap.py` tồn tại chính để việc chạy lại đó
> chỉ tốn vài phút.

---

## 3. Đánh giá chế độ Agentic

### 3.1. Bốn cấu hình được so sánh

| # | trần chunk | embedding | model sinh | vai trò |
|---|---:|---|---|---|
| 1 | 3.000 | `openai/text-embedding-3-small` | `openai/gpt-4o-mini` | **mốc so sánh** (cấu hình đang chạy thật) |
| 2 | 3.000 | `voyageai/voyage-4-large` | `openai/gpt-4o-mini` | đổi **embedding** |
| 3 | 3.000 | `openai/text-embedding-3-small` | `google/gemini-2.5-pro` | đổi **model sinh** |
| 4 | 3.000 | `voyageai/voyage-4-large` | `google/gemini-2.5-pro` | đổi **cả hai** |

Thiết kế này tách được ảnh hưởng của hai tầng: so 1↔2 và 3↔4 cho biết embedding
đóng góp bao nhiêu; so 1↔3 và 2↔4 cho biết model sinh đóng góp bao nhiêu.

> `voyage-4-large` **có** phục vụ qua OpenRouter (1024 chiều) dù endpoint
> `/models` không liệt kê — endpoint đó không liệt kê **model embedding nào**,
> kể cả `text-embedding-3-small` đang chạy thật. Muốn biết một model embedding
> có dùng được không thì phải **gọi thử**, không tra danh sách.

### 3.2. Cách chạy — vì sao dùng harness thay vì gọi API thật

Script: [`scripts/bench_agentic.py`](../scripts/bench_agentic.py)

Bốn cấu hình khác nhau ở **embedding**, mà collection Qdrant bị cố định số
chiều khi tạo (1536 với `text-embedding-3-small`, 1024 với `voyage-4-large`).
Đo qua endpoint thật sẽ phải **dựng lại collection giữa mỗi lượt** — chậm, và
làm hệ thống không dùng được cho cấu hình chưa nạp.

Nên phần **truy hồi** được làm trong bộ nhớ: kéo chunk từ Qdrant một lần, embed
một lần cho mỗi model (có cache đĩa), rồi chấm điểm bằng cosine với đúng
`top_k = 5` và `score_threshold = 0,5` như cấu hình thật.

Mọi thứ **sau** truy hồi là code thật, không mô phỏng:

- cùng `_DEFAULT_SYSTEM`;
- cùng `_format_context_chunk()` (gắn nhãn vùng/kỳ/nguồn cho từng chunk);
- cùng cách đặt tư liệu vào **một system message riêng** thay vì dán vào câu
  hỏi (§5B.9 — chi tiết vì sao điều này quyết định việc model có gọi tool hay
  không);
- cùng `run_tool_loop()` với đúng 3 schema tool, chạy SQL trên đúng Postgres đó.

Chỉ có vector là thay đổi.

### 3.3. Kết quả

#### Điểm tổng

| cấu hình | đạt | tỷ lệ | gọi tool | giây/câu |
|---|---:|---:|---:|---:|
| small + 4o-mini | **26/30** | 87% | 97% | 3.4 |
| voyage + 4o-mini | **26/30** | 87% | 97% | 3.2 |
| small + gemini-pro | **22/30** | 73% | 90% | 14.7 |
| voyage + gemini-pro | **27/30** | 90% | 93% | 15.3 |

#### Điểm theo mức độ khó

| cấu hình | T1 nhiễu | T2 suy luận | T3 tiếp nối | T4 tra cứu | T5 trực tiếp |
|---|---:|---:|---:|---:|---:|
| small + 4o-mini | 5/6 | 5/6 | 4/5 | 6/7 | 6/6 |
| voyage + 4o-mini | 4/6 | 5/6 | 4/5 | 7/7 | 6/6 |
| small + gemini-pro | 3/6 | 6/6 | 5/5 | 2/7 | 6/6 |
| voyage + gemini-pro | 4/6 | 6/6 | 5/5 | 6/7 | 6/6 |

#### Câu nào phân biệt được các cấu hình

Câu mà **mọi** cấu hình cùng đạt hoặc cùng trượt không mang thông tin so sánh. Bảng dưới chỉ liệt kê những câu có kết quả khác nhau giữa các cấu hình.

| câu | mức | small + 4o-mini | voyage + 4o-mini | small + gemini-pro | voyage + gemini-pro |
|---|---|---|---|---|---|
| B01 | T1 | ✘ | ✘ | ✘ | ✔ |
| B05 | T1 | ✔ | ✘ | ✘ | ✘ |
| B06 | T1 | ✔ | ✔ | ✘ | ✘ |
| B08 | T2 | ✘ | ✘ | ✔ | ✔ |
| B14 | T3 | ✘ | ✘ | ✔ | ✔ |
| B18 | T4 | ✘ | ✔ | ✘ | ✔ |
| B19 | T4 | ✔ | ✔ | ✘ | ✔ |
| B20 | T4 | ✔ | ✔ | ✔ | ✘ |
| B21 | T4 | ✔ | ✔ | ✘ | ✔ |
| B22 | T4 | ✔ | ✔ | ✘ | ✔ |
| B24 | T4 | ✔ | ✔ | ✘ | ✔ |

Trong 30 câu: **19** câu mọi cấu hình đều đạt, **0** câu mọi cấu hình đều trượt, **11** câu phân biệt được.

#### Toàn bộ câu trượt, theo cấu hình

**small + 4o-mini** — 4 câu trượt

| câu | mức | vì sao trượt |
|---|---|---|
| B01 | T1 | phải nói không có dữ liệu nhưng lại trả lời |
| B08 | T2 | thiếu giá đúng [283636] (nêu: [25, 375, 362727]) |
| B14 | T3 | thiếu giá đúng [1100000, 1120000] (nêu: [30, 1300000]) |
| B18 | T4 | thiếu giá đúng [121000] (nêu: [2, 4, 95]) |

**voyage + 4o-mini** — 4 câu trượt

| câu | mức | vì sao trượt |
|---|---|---|
| B01 | T1 | phải nói không có dữ liệu nhưng lại trả lời |
| B05 | T1 | thiếu giá đúng [15360, 15460, 15620, 15920, 16020, 16400] (nêu: [12]) |
| B08 | T2 | thiếu giá đúng [283636] (nêu: [1, 2, 25, 375, 362727]) |
| B14 | T3 | thiếu giá đúng [1100000, 1120000] (nêu: [30, 1300000]) |

**small + gemini-pro** — 8 câu trượt

| câu | mức | vì sao trượt |
|---|---|---|
| B01 | T1 | phải nói không có dữ liệu nhưng lại trả lời |
| B05 | T1 | thiếu giá đúng [15360, 15460, 15620, 15920, 16020, 16400] (nêu: [1, 12, 104, 117, 20100, 209000]) |
| B06 | T1 | thiếu giá đúng [1175926, 1259259, 1268519, 1314815] (nêu: [1, 4, 40, 50, 1407407, 1416667]) |
| B18 | T4 | thiếu giá đúng [121000] (nêu: []) |
| B19 | T4 | thiếu giá đúng [1809338, 2515002, 2698310, 2954238, 3358761, 3526629, 3837928, 3945900] (nêu: []) |
| B21 | T4 | không gọi lookup_material_price (đã gọi: không gọi gì) |
| B22 | T4 | thiếu giá đúng [298182] (nêu: [25]) |
| B24 | T4 | thiếu giá đúng [18600] (nêu: [6, 60, 70, 2026, 18000, 19800]) |

**voyage + gemini-pro** — 3 câu trượt

| câu | mức | vì sao trượt |
|---|---|---|
| B05 | T1 | thiếu giá đúng [15360, 15460, 15620, 15920, 16020, 16400] (nêu: [1, 12, 117, 209000]) |
| B06 | T1 | thiếu giá đúng [1175926, 1259259, 1268519, 1314815] (nêu: [1, 30, 40, 50, 1407407, 1703704]) |
| B20 | T4 | thiếu giá đúng [43200] (nêu: [1, 2, 3, 4, 15, 18]) |

### 3.4. Nếu bỏ hoàn toàn công cụ — chỉ còn RAG thuần

Cùng 30 câu hỏi, cùng vector, cùng `top_k = 5`, nhưng model **không được cấp tool nào**: nó chỉ có 5 chunk truy hồi được và phải tự rút câu trả lời ra từ đó.

Lời nhắc hệ thống cũng đổi theo — bản dùng cho chế độ Agentic ra lệnh *"PHẢI gọi công cụ tương ứng"*, giữ nguyên nó khi không có công cụ nào là bắt model làm việc bất khả thi, và sẽ đo sự bối rối thay vì đo năng lực. Bản RAG thuần giữ đúng phần cốt lõi: chỉ trả lời từ tư liệu, không bịa số, không có thì nói không có.

Điều kiện chấm `expect_tool` được bỏ qua (chấm trượt vì "không gọi tool" khi không có tool là đo thiết lập của bộ đo). 20 câu chốt giá trị số và 6 câu phải-từ-chối vẫn chấm y như cũ — đó mới là phép thử thật cho RAG thuần.

| cấu hình | có tool | RAG thuần | chênh lệch |
|---|---:|---:|---:|
| small + 4o-mini | 26/30 | **10/30** | -16 |
| voyage + 4o-mini | 26/30 | **12/30** | -14 |
| small + gemini-pro | 22/30 | **10/30** | -12 |
| voyage + gemini-pro | 27/30 | **21/30** | -6 |

#### Điểm RAG thuần theo mức độ khó

| cấu hình | T1 nhiễu | T2 suy luận | T3 tiếp nối | T4 tra cứu | T5 trực tiếp |
|---|---:|---:|---:|---:|---:|
| small + 4o-mini | 3/6 | 3/6 | 2/5 | 1/7 | 1/6 |
| voyage + 4o-mini | 3/6 | 5/6 | 2/5 | 0/7 | 2/6 |
| small + gemini-pro | 2/6 | 3/6 | 2/5 | 1/7 | 2/6 |
| voyage + gemini-pro | 4/6 | 6/6 | 3/5 | 3/7 | 5/6 |

#### Câu nào mất đi khi bỏ công cụ

Câu **đạt khi có tool** nhưng **trượt khi chỉ có RAG** — đây là phần công việc mà truy hồi vector không làm thay được.

| câu | mức | small + 4o-mini | voyage + 4o-mini | small + gemini-pro | voyage + gemini-pro |
|---|---|---|---|---|---|
| B01 | T1 | thêm | thêm | — | — |
| B04 | T1 | **mất** | **mất** | **mất** | — |
| B05 | T1 | **mất** | — | — | — |
| B06 | T1 | **mất** | **mất** | — | — |
| B07 | T2 | **mất** | — | **mất** | — |
| B08 | T2 | — | — | **mất** | — |
| B09 | T2 | **mất** | — | **mất** | — |
| B13 | T3 | **mất** | **mất** | **mất** | — |
| B14 | T3 | — | — | **mất** | **mất** |
| B16 | T3 | **mất** | **mất** | **mất** | **mất** |
| B18 | T4 | — | **mất** | — | **mất** |
| B19 | T4 | **mất** | **mất** | — | **mất** |
| B20 | T4 | **mất** | **mất** | **mất** | — |
| B21 | T4 | — | **mất** | thêm | — |
| B22 | T4 | **mất** | **mất** | — | — |
| B23 | T4 | **mất** | **mất** | **mất** | **mất** |
| B24 | T4 | **mất** | **mất** | — | — |
| B25 | T5 | **mất** | **mất** | **mất** | — |
| B26 | T5 | **mất** | **mất** | **mất** | — |
| B27 | T5 | **mất** | **mất** | **mất** | — |
| B28 | T5 | **mất** | — | **mất** | — |
| B30 | T5 | **mất** | **mất** | — | **mất** |

## 4. Đọc kết quả — bốn kết luận

### 4.1. Bỏ công cụ không làm hệ thống "trả lời thiếu", nó làm hệ thống **trả lời sai**

Đây là kết luận quan trọng nhất, và nó không nhìn ra được từ cột điểm.

Đếm theo **kiểu** trượt của RAG thuần: phần lớn không phải "không tìm thấy"
mà là **nêu một con số khác**. Hai ví dụ nguyên văn (`small + 4o-mini`):

> **B26 — "Giá cát san lấp ở TPHCM là bao nhiêu một khối?"**
> *"Giá cát san lấp ở TPHCM dao động từ 220.000 đến 380.000 VNĐ/m³."*
> Giá thật: **400.000** và **450.000**. Câu trả lời chắc nịch, không rào đón,
> và hai con số kia có thật — chúng thuộc **dòng khác** lọt vào cửa sổ truy
> hồi. Người đọc không có bất kỳ dấu hiệu nào để nghi ngờ.

> **B06 — "Xi măng Vicem Hạ Long ở TPHCM giá bao nhiêu một tấn?"**
> `voyage + gemini-pro` nêu 1.287.037 và 1.495.370 — cũng là giá thật, nhưng
> của **Vicem Hà Tiên**. Đúng vùng, đúng loại sản phẩm, sai thương hiệu.

Cùng câu hỏi đó, đường có công cụ chạy SQL trên `material_prices` và hoặc trả
đúng dòng, hoặc trả nguyên văn *"Không tìm thấy… Không suy đoán giá"*. Nó
không có cách nào nêu một con số không nằm trong kết quả truy vấn.

Với dự toán xây dựng, một con giá **sai mà nghe hợp lý** đi thẳng vào bảng
tính và không ai phát hiện. Chênh lệch 26/30 so với 10/30 vì thế còn **nhẹ
hơn** mức độ nghiêm trọng thật.

### 4.2. Embedding và model sinh chỉ có tác dụng khi đi **cùng nhau**

Ở chế độ RAG thuần, tách riêng từng thay đổi:

| thay đổi | điểm | so với gốc |
|---|---:|---:|
| gốc: small + 4o-mini | 10/30 | — |
| **chỉ** đổi embedding → voyage | 12/30 | **+2** |
| **chỉ** đổi model sinh → gemini-2.5-pro | 10/30 | **+0** |
| đổi **cả hai** | **21/30** | **+11** |

Tổng hai phần riêng lẻ là **+2**, nhưng làm cùng lúc được **+11**. Đây không
phải cộng dồn mà là **tương tác**, và cơ chế thì hợp lý:

- Đổi **riêng embedding**: chunk đúng được đưa vào cửa sổ nhiều hơn, nhưng
  `gpt-4o-mini` không rút nổi đúng dòng ra khỏi một bảng HTML 3.000 token —
  tư liệu tốt hơn mà không đọc được thì vô ích.
- Đổi **riêng model sinh**: Gemini đọc bảng tốt hơn hẳn, nhưng nếu chunk chứa
  đáp án không lọt vào top-5 thì đọc giỏi cũng không cứu được — không thể rút
  ra thứ không có trong ngữ cảnh.
- Chỉ khi **truy hồi mang đúng bảng về** *và* **model đủ sức đọc bảng đó**,
  cả hai điều kiện mới cùng thoả.

Điều này cũng giải thích nghịch lý ở mục 3.3: `small + gemini-pro` chỉ được
**22/30** — **kém hơn** `small + 4o-mini` (26/30) dù model đắt hơn nhiều.
Model mạnh hơn mà tầng truy hồi không đổi thì không mua được gì; riêng ở mức
T4 nó rớt xuống **2/7**.

### 4.3. Ngay cấu hình RAG thuần tốt nhất vẫn thua đường có công cụ

`voyage + gemini-pro` là cấu hình RAG thuần tốt nhất: **21/30** — gấp đôi mốc
so sánh. Nhưng cùng cấu hình đó, khi được cấp công cụ, đạt **27/30**.

Chín câu nó vẫn trượt chia làm hai nhóm:

| nhóm | câu | bản chất |
|---|---|---|
| nêu sai số | B05, B06, B14, B18, B19, B20, B30 | lấy giá của sản phẩm/vùng khác trong cửa sổ |
| tự tin sai chỗ | B16, B23 | trả lời như thể có, cho thứ **không** có trong dữ liệu |

Cả hai nhóm đều là dạng lỗi mà **thêm ngữ cảnh không sửa được**: vấn đề không
phải model thiếu thông tin, mà là nó phải **chọn** giữa nhiều dòng gần giống
nhau bằng cách đọc chữ — trong khi mệnh đề `WHERE` làm đúng việc đó một cách
tất định.

### 4.4. Chi phí: cấu hình tốt nhất chậm gấp gần 5 lần

| cấu hình | điểm (có tool) | giây/câu |
|---|---:|---:|
| small + 4o-mini | 26/30 | **3,4** |
| voyage + 4o-mini | 26/30 | **3,2** |
| small + gemini-pro | 22/30 | 14,7 |
| voyage + gemini-pro | **27/30** | 15,3 |

Đổi sang `gemini-2.5-pro` mua thêm **1 câu** (26 → 27) với giá **gấp 4,8 lần
thời gian** và chi phí token cao hơn nhiều lần. Trong khi đó `voyage + 4o-mini`
giữ nguyên 26/30 mà vẫn nhanh 3,2 giây — và nó là cấu hình **duy nhất đạt
7/7 ở mức T4**.

**Khuyến nghị:** giữ `gpt-4o-mini` làm model sinh mặc định cho chế độ Agentic.
Chênh lệch 1 câu nằm trong khoảng dao động giữa hai lần chạy (xem §5.2 — chính
`voyage + 4o-mini` đã cho 27/30 ở lần chạy trước và 26/30 ở lần này), nên nó
**không** đủ cơ sở để trả gấp 5 lần thời gian đáp ứng.

Điều đáng cân nhắc hơn là **đổi embedding sang `voyage-4-large`**: cùng chi
phí sinh, cùng tốc độ, T4 đạt trọn 7/7, và nó là thay đổi mở khoá được +11
điểm ở chế độ RAG thuần nếu sau này cần chạy không công cụ.

## 5. Những hạn chế của phép đo này

Ghi ra để người đọc biết con số này **không** nói được điều gì.

### 5.1. Bộ 30 câu là mẫu nhỏ

Chênh lệch 1–2 câu giữa hai cấu hình **không** đủ để kết luận cấu hình này hơn
cấu hình kia. Chỉ những chênh lệch lớn mới đáng đọc — cụ thể trong báo cáo này
là 22 vs 26/27 ở mục 3.3, và 10/12 vs 21 ở mục 3.4. Mục 3.3 liệt kê rõ **câu
nào** khác nhau để người đọc tự đánh giá thay vì chỉ nhìn tổng điểm.

### 5.2. Model sinh không tất định — đã quan sát trực tiếp

`temperature` mặc định khác 0, nên chạy lại cùng cấu hình có thể ra điểm khác.
Đây **không** phải cảnh báo lý thuyết: cấu hình `voyage + 4o-mini` cho
**27/30** ở lần chạy trước và **26/30** ở lần chạy được báo cáo — cùng code,
cùng vector, cùng câu hỏi.

Nói cách khác, **biên độ dao động của phép đo này là ±1 câu**. Mọi kết luận
dựa trên chênh lệch 1 câu đều vô nghĩa; đó là lý do §4.4 khuyến nghị giữ
`gpt-4o-mini` thay vì đổi sang `gemini-2.5-pro` để lấy đúng 1 câu.

Phép đo này là **một lần chạy**, không phải trung bình nhiều lần.

### 5.3. Chấm bằng luật, không bằng người

 Cách chấm bắt được "nêu sai số" và
"không nói không biết", nhưng **không** đánh giá được văn phong, độ đầy đủ,
hay việc câu trả lời có dễ hiểu với người dùng thật hay không. Một câu trả lời
đúng số nhưng trình bày rối vẫn được tính là đạt.

### 5.4. Câu B08 khắt khe hơn câu chữ của chính nó

Ở lần chạy này, B08 hỏi
*"loại nào rẻ hơn?"* nhưng chấm bằng con số — nên một câu trả lời đúng nghĩa
mà không nêu giá vẫn bị tính trượt. Phép **so sánh** giữa 4 cấu hình vẫn hợp
lệ vì cùng một thước đo áp cho cả bốn, nhưng **điểm tuyệt đối** của riêng câu
đó không đáng tin. Câu chữ đã được sửa lại cho các lần chạy sau.

### 5.5. Truy hồi chạy trong bộ nhớ, không qua Qdrant

 Cùng công thức cosine và
cùng `top_k`/`score_threshold`, nhưng không đi qua bộ lọc payload theo `kb_id`
của Qdrant. Với chế độ Agentic (quét toàn bộ KB) thì khác biệt này bằng không;
với chế độ hỏi trong một KB thì phép đo này không đại diện.

### 5.6. Không đo chi phí tiền

 Cột "giây/câu" là thời gian, không phải tiền.
`gemini-2.5-pro` đắt hơn `gpt-4o-mini` nhiều lần, và nếu hai bên bằng điểm thì
lựa chọn phải dựa trên chi phí — xem §0B.5 của
[kien-truc-chi-tiet.md](kien-truc-chi-tiet.md).

## 6. Cách chạy lại

```bash
# 1. neo lại giá trị kỳ vọng vào dữ liệu hiện tại (bắt buộc sau mỗi lần nạp lại)
docker exec -e PYTHONPATH=/app -w /app agentic-rag-app \
    python scripts/bench_ground.py

# 2. chạy benchmark — chế độ Agentic (có công cụ)
docker exec -e PYTHONPATH=/app -w /app agentic-rag-app \
    python scripts/bench_agentic.py --configs all \
    --out /app/.bench_cache/results_tools.json

# 2b. chạy lại cùng bộ câu hỏi nhưng KHÔNG cấp công cụ nào
docker exec -e PYTHONPATH=/app -w /app agentic-rag-app \
    python scripts/bench_agentic.py --configs all --no-tools \
    --out /app/.bench_cache/results_ragonly.json

# 3. sinh lại mục 3.3 và mục 4 của bộ câu hỏi từ kết quả
python scripts/bench_report_gen.py
python scripts/bench_docs_gen.py
```

Phép đo trần chunk (mục 2) chạy riêng:

```bash
docker exec -e PYTHONPATH=/app -w /app agentic-rag-app \
    python scripts/eval_chunk_cap.py
docker exec -e PYTHONPATH=/app -w /app agentic-rag-app \
    python scripts/eval_intra_table_sim.py
```

> Vector embedding được lưu ở **`.bench_cache/`** trong thư mục repo (được
> bind-mount ra host, nên **sống sót qua mọi lần restart container** — `/tmp`
> trong container thì không, và đã làm mất một lượt embed 25 phút). Khoá cache
> gồm **model + băm SHA-256 của chính nội dung**: sửa câu hỏi hay nạp lại tài
> liệu thì khoá đổi và vector được tính lại, nên cache **không thể** trả vector
> cũ cho nội dung mới. Quá trình embed còn ghi mốc `.partial` định kỳ, nên lần
> chạy sau tiếp tục từ chỗ dừng thay vì làm lại từ đầu.
>
> Nhờ vậy, chạy lại benchmark **không tốn chi phí embedding** — chỉ tốn chi phí
> sinh văn bản.
