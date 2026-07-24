# Construction Materials & Cost-Estimation Pipeline

Tài liệu này mô tả toàn bộ luồng xử lý dữ liệu vật liệu xây dựng trong hệ
thống: từ ingest PDF, chunking, embedding, đến các MCP tool tính giá, vòng
lặp tool-calling của LLM, và luồng human-in-the-loop form trên chat UI.

Đây là phần domain-specific được thêm vào trên nền kiến trúc RAG chung của
project (ingestion pipeline, Qdrant, MCP server có sẵn) — xem `README.md`
cho kiến trúc tổng quan.

---

## 1. Tổng quan luồng dữ liệu

```
PDF công văn/phụ lục giá vật liệu (Sở Xây dựng) hoặc báo giá nhà cung cấp
│
├─ classify_source_file()             app/core/ingestion/price_extractor.py
│   → official_announcement | official_annex | vendor_quote
│
├─ ChunkDispatcher.chunk()            app/core/chunking/dispatcher.py
│   → PdfChunker: PyMuPDF (text) + pdfplumber (table → HTML)
│
├─ split_oversized_table_chunk()      app/core/chunking/base.py
│   → bảng HTML > MAX_EMBED_TOKENS (8000) bị tách thành nhiều chunk nhỏ,
│     mỗi chunk lặp lại header row để giữ ngữ cảnh cột
│
├─ OpenRouterClient.embed()           app/core/llm/openrouter.py
│   → text-embedding-3-small, 1536-dim
│
├─► QdrantStore.upsert_chunks()       app/db/qdrant/client.py
│     → ngữ cảnh pháp lý/điều kiện giá cho RAG (metadata: region,
│       source_type, price_period)
│
└─► extract_price_rows()              app/core/ingestion/price_extractor.py
      → MaterialPriceRepository.bulk_create()
      → bảng material_prices (Postgres) — dữ liệu giá CÓ CẤU TRÚC,
        dùng để tra cứu chính xác, KHÔNG qua semantic search
```

Hai đích lưu trữ này phục vụ hai việc khác nhau:

| Đích | Dùng để | Vì sao |
|---|---|---|
| Qdrant (chunk ngữ cảnh) | RAG trả lời câu hỏi kiến thức/điều kiện giá | Semantic search phù hợp cho văn bản tự do |
| `material_prices` (Postgres) | `lookup_material_price` tra giá chính xác | Semantic search có thể trả nhầm vật liệu/vùng/kỳ — sai một đơn giá là sai cả kết quả tính chi phí, nên tool tra cứu bắt buộc phải là truy vấn SQL chính xác, không phải similarity search |

Cả hai chạy trong cùng 1 pipeline (`PriceExtractionPipeline`,
`app/core/ingestion/price_pipeline.py`), kích hoạt qua endpoint
`POST /api/v1/documents/upload-price/{kb_id}?region=...&price_period=...`.

---

## 2. Chunking & embedding

### 2.1. Chunking

Dùng chung `PdfChunker`/`TextChunker`/`DocxChunker` của project (không có
chunking strategy riêng cho domain này). Điểm khác biệt duy nhất:

- **`TextChunker`** giữ marker `<!-- chunk_id: ... -->` trong file `.md`
  kiến thức nền làm metadata (`Chunk.metadata["chunk_id"]`), forward-fill
  cho các sub-heading không có marker riêng — giúp trích dẫn đúng mục khi
  trả lời.
- **`PdfChunker`** tách bảng giá thành HTML chunk riêng (không merge với
  text) — đúng hành vi gốc của project, không có gì đặc thù domain ở bước
  này.

### 2.2. Vì sao phải tách chunk quá khổ thay vì đổi model embedding

Đã kiểm chứng trực tiếp với OpenRouter: `text-embedding-3-small` **và**
`text-embedding-3-large` đều giới hạn cứng **8192 token/input** — bản
"large" chỉ khác số chiều vector đầu ra, không khác context. Một bảng giá
PDF thật (vd phụ lục 27 dòng × 8 cột) có thể tạo ra 1 chunk HTML ~39.000 ký
tự (~20.000 token), vượt xa giới hạn này. OpenRouter/OpenAI **từ chối cả
batch request** nếu có 1 item vượt giới hạn — không phải chỉ item đó, làm
hỏng toàn bộ lô ingest.

Giải pháp: `split_oversized_table_chunk()` (`app/core/chunking/base.py`)
tách chunk TABLE quá khổ theo nhóm dòng, **lặp lại header row** ở mỗi phần
để không mất ngữ cảnh cột:

```
Trước: 1 chunk 20.043 token (1 bảng 78 dòng) → vượt 8000 → cả batch lỗi
Sau:   4 chunk (7891, 7912, 4788, 743 token), mỗi chunk có header riêng
```

Áp dụng trong cả `IngestionPipeline` (upload thường) và
`PriceExtractionPipeline` (upload giá) — chunk vẫn vượt ngưỡng sau khi tách
(hiếm, ví dụ 1 ô ghi chú dài bất thường) mới bị bỏ qua, có log cảnh báo.

---

## 3. Trích xuất giá có cấu trúc (`price_extractor.py`)

Parser bảng theo hướng heuristic (không có schema cố định vì mỗi vùng/nhà
cung cấp trình bày bảng khác nhau):

1. **Nhận diện header** — quét tối đa 6 dòng đầu bảng, gộp keyword-hit qua
   nhiều dòng (header thường trải 2+ dòng vật lý, vd "GIÁ BÁN..." ở 1 dòng,
   "Tại nơi sản xuất"/"Tại chân công trình" ở dòng kế). Bỏ qua ô văn bản dài
   (>60 ký tự) khi tìm cột — tránh nhận nhầm dòng tiêu đề trang (vd "BẢNG
   CÔNG BỐ GIÁ MỘT SỐ VẬT LIỆU...") thành cột giá.
2. **Bảng nhiều trang không lặp header** — mapping cột + category được giữ
   xuyên suốt các trang tiếp theo, chỉ áp dụng nếu **số cột khớp** với bảng
   đã detect header gần nhất (tránh áp nhầm mapping cũ cho 1 bảng khác cấu
   trúc xen giữa).
3. **Dòng nhóm vật liệu thưa cột** (vd `["I", "XI MĂNG", "", "", ...]`)
   được forward-fill làm `material_category` cho các dòng sau.
4. **Chuẩn hoá whitespace** — category/name bị xuống dòng trong PDF gốc
   (vd `"Đá xây\ndựng"`) được gộp thành 1 dòng để `ILIKE` lookup hoạt động.
5. **Không đoán khi không chắc** — dòng có tên+đơn vị nhưng không đọc được
   giá bị ghi vào `warnings`, KHÔNG bị bỏ qua âm thầm và KHÔNG bị gán giá
   sai. Đây là nguyên tắc xuyên suốt: sai giá 1 vật liệu → sai cả kết quả
   tính chi phí, nên thà thiếu còn hơn sai.

Kết quả trên bộ dữ liệu thật (10 file, 3 vùng), sau khi sửa 2 bug phát hiện
qua kiểm chứng thủ công:

1. **Dòng tiêu đề trang bị nhận nhầm thành header cột giá** — vd
   `"BẢNG CÔNG BỐ GIÁ MỘT SỐ VẬT LIỆU XÂY DỰNG..."` vô tình chứa cụm
   `"công bố giá"` khớp `_PRICE_GENERIC_KEYWORDS`, khiến vòng lặp dò header
   dừng ở dòng tiêu đề (chỉ 1 ô có nội dung) thay vì dòng header thật (nhiều
   ô). Sửa: một dòng chỉ được tính là ứng viên header nếu có ≥2 ô không
   rỗng — dòng tiêu đề/phụ đề chỉ có 1 ô nội dung trải dài (do gộp cell khi
   pdfplumber flatten bảng) sẽ bị bỏ qua.
2. **pdfplumber tách rời số do lỗi kerning font** — vd `"18.000"` bị đọc
   thành `"1 8.000"` (khoảng trắng lạc giữa 1-2 chữ số đầu và phần còn lại),
   khiến `_parse_price()` chỉ lấy được `"1"` → sai giá gấp hàng chục nghìn
   lần (18.000đ đọc thành 1đ). Sửa: gộp lại khoảng trắng ở đúng vị trí này
   trước khi chạy regex trích số — chỉ áp dụng hẹp (1-2 chữ số đầu dòng),
   không gộp mọi khoảng trắng để tránh nhập nhằng 2 số riêng biệt trong
   cùng 1 ô (vd 1 khoảng giá `min - max`).

| File | Vùng | Chunks | Dòng giá |
|---|---|---:|---:|
| BangGia-VLXD-HaNoi-QuyII-2026.pdf (699 trang) | HN | 2.259 | 6.588 |
| BangGia-VLXD-BoSung-NhuaDuong-HaNoi-QuyII-2026.pdf | HN | 15 | 13 |
| CongVan-CongBoGia-VLXD-HaNoi-QuyII-2026.pdf | HN | 9 | 0 (công văn, không có bảng giá) |
| BangGia-VLXD-DaNang-Thang06-2026.pdf | DN | 470 | 1.588 |
| BangGia-VatTuDien-DaNang-Thang06-2026.pdf | DN | 332 | 1.639 |
| BangGia-VatTuNuoc-DaNang-Thang06-2026.pdf | DN | 15 | 144 |
| CongVan-CongBoGia-VLXD-DaNang-Thang06-2026.pdf | DN | 7 | 0 (công văn) |
| BangGia-VLXD-KhoangSan-HCM-Thang06-2026.pdf | HCM | 29 | 27 |
| BangGia-VLXD-ThamKhaoThiTruong-HCM-Thang06-2026.pdf | HCM | 8 | 11 |
| ThongBao-CongBoGia-VLXD-HCM-Thang06-2026.pdf | HCM | 20 | 0 (thông báo) |

**Tên file**: đổi từ tên gốc mơ hồ (`PhuLuc.pdf`, `PL1.pdf`, `02.01-2026_CBGVL-SXD.pdf`...)
sang tên mô tả nội dung + vùng + kỳ (`BangGia-VLXD-HaNoi-QuyII-2026.pdf`...)
— tên gốc không nói lên được file nào chứa gì khi liệt kê nhiều file cùng
lúc trong UI. Còn ~60 file báo giá scan của từng nhà cung cấp riêng lẻ ở
TPHCM (`01_Công ty...pdf`, `18_Công ty...pdf`...) đã bị loại khỏi
`seed_data/` — ảnh quét không có lớp text, ngay cả sau khi thêm OCR fallback
(mục 3.1) nhiều file vẫn cho kết quả không đáng tin để dùng làm dữ liệu giá.

### 3.1. OCR fallback cho PDF quét ảnh

Khi `PdfChunker` trả về 0 chunk (PDF không có lớp text, thường gặp ở báo giá
scan tay), `app/core/ingestion/ocr_fallback.py` render từng trang thành ảnh
(PyMuPDF `get_pixmap`) rồi gọi model vision qua OpenRouter
(`OPENROUTER_VISION_MODEL`) để phiên âm chữ, sau đó chunk văn bản thu được
như bình thường. Chỉ kích hoạt khi trích xuất thường ra 0 chunk (không chạy
vision model cho mọi trang của mọi PDF) — vẫn chỉ tạo chunk cho RAG, **không**
tự động trích ra `material_prices` có cấu trúc từ văn bản OCR (bảng dạng ảnh
quá rủi ro để tự tin gán số mà không có cấu trúc cột rõ ràng).

---

## 4. MCP tools

`app/core/mcp/tools/` — theo pattern `Tool` (schema) + `handle_*` (async
handler) có sẵn của project, đăng ký trong `app/core/mcp/server.py`.

### `lookup_material_price`
Query trực tiếp `material_prices` (SQL `WHERE region=... AND
material_category ILIKE ...`, không phải vector search). Trả "không tìm
thấy" thay vì đoán khi thiếu dữ liệu.

### `estimate_material_quantity`
Công thức đo bóc xác định (`app/core/construction/formulas.py`) — code
Python thuần, **không dùng LLM để tính toán**. Hỗ trợ: bê tông (§16), cốt
thép theo hình học hoặc bảng thống kê (§17), tường xây (§19), trát (§20),
ốp lát (§21), sơn (§22).

### `calculate_construction_cost`
Orchestrator cấp cao nhất: từ diện tích sàn → hệ số tiêu hao tham khảo/m2 →
gọi `estimate_material_quantity` cho 4 hạng mục chính (bê tông, thép, gạch,
sơn) → chọn đúng dòng giá cho từng hạng mục → tổng hợp. Luôn trả **khoảng
giá** (không phải 1 số duy nhất) kèm giả định đã dùng, và ghi rõ đây chỉ là
**chi phí vật liệu**, không phải giá xây nhà trọn gói (không gồm nhân
công/thiết bị/VAT).

**Chọn đúng dòng giá — LLM chỉ chọn, không tự tính giá.** `material_category`
trong dữ liệu bị điền không đồng nhất (có lúc là tên công ty thay vì loại vật
liệu — vd `"CÔNG TY CỔ PHẦN VIGLACERA TIÊN SƠN"` từng khớp nhầm truy vấn
"sơn"), nên bước lọc đầu tiên dùng `material_name` + **đơn vị tính** (m3/kg/
viên/lít — ràng buộc vật lý khách quan, không phải suy đoán) để lấy ra tối
đa 15 ứng viên từ `material_prices`. Nếu còn nhiều hơn 1 ứng viên,
`_disambiguate()` (`app/core/mcp/tools/cost_tool.py`) gửi danh sách kèm mô tả
mục tiêu (vd *"bê tông thương phẩm/bê tông tươi trộn sẵn — KHÔNG phải bê
tông đúc sẵn dạng tấm/panel/cấu kiện"*) cho LLM (`openai/gpt-4o-mini`, cố
định — không dùng `settings.openrouter_research_model`, xem ghi chú trong
code), yêu cầu trả về **index** của dòng đúng nhất hoặc `-1` nếu không dòng
nào phù hợp. LLM không bao giờ tự nghĩ ra giá — chỉ chọn giữa các dòng thật
trong DB, và nói "không dòng nào phù hợp" thay vì chọn đại một dòng gần
đúng khi không chắc.

Cách này thay cho danh sách từ khoá loại trừ thủ công ban đầu (vd
`exclude=["khí chưng áp","tấm panel","cấu kiện",...]`) — đúng nhưng quá
mong manh: mỗi vendor file mới có thể tạo ra 1 kiểu khớp nhầm chưa ai lường
trước, phải liệt kê tay từng trường hợp mới phát hiện được.

---

## 5. Vòng lặp tool-calling (chế độ `mode="agent"`)

`app/core/llm/tool_loop.py::run_tool_loop()` — vòng lặp OpenAI-style tool
calling đơn giản, **không dùng LangGraph** (LangGraph research graph giải
quyết bài toán khác: web search lặp lại nhiều vòng, không phù hợp cho
1-shot tool dispatch này):

```
gọi LLM với tools=[...] 
  → có tool_calls?  → thực thi tool → nối kết quả vào hội thoại → lặp lại
  → không có       → trả câu trả lời cuối
(tối đa 4 vòng, sau đó ép LLM trả lời không dùng tool)
```

Dùng khi client gửi `POST /api/v1/chat/stream` với `mode: "agent"` — LLM tự
quyết định có cần gọi `lookup_material_price`/`calculate_construction_cost`
hay không, và tự suy luận tham số từ câu hỏi tự do. Phù hợp cho câu hỏi mở,
nhưng **có rủi ro LLM đoán sai tham số** (diện tích, vùng) nếu người dùng
không nói rõ.

---

## 6. Human-in-the-loop form (fixed pipeline)

Với câu hỏi có dạng cố định và rủi ro cao nếu đoán sai tham số ("giá xây
nhà bao nhiêu m2"), hệ thống **không** để LLM tự suy luận — thay vào đó
route qua 1 pipeline cố định: nhận diện ý định → yêu cầu form → nhận kết
quả form → gọi tool trực tiếp, hoàn toàn không qua LLM.

### Sequence

```
User: "giá xây nhà 100m2 ở Hà Nội"
   │
   ▼
POST /chat/stream {message: "..."}                app/api/v1/chat.py
   │
   ├─ form_submission? không có
   ├─ detect_intent(message)                       app/core/chat/intent.py
   │     → khớp keyword "giá xây nhà" → "construction_cost"
   │
   ▼
SSE: {"type":"form_request", "form_id":"construction_cost",
      "fields":[...], "prefill":{"area_per_floor_m2":100,"region":"HN"}}
   │   (KHÔNG gọi LLM — kiểm chứng: không có log request tới OpenRouter)
   ▼
Frontend: setPendingForm() → render <ConstructionCostForm>
                                frontend/components/chat/ConstructionCostForm.tsx
   │  (form thủ công theo đúng schema server gửi, không dùng thư viện sinh
   │   form từ JSON schema)
   │
User điền/sửa field, bấm "Tính chi phí" — nếu câu hỏi gốc đến từ voice
(Speak), kết quả sau khi submit cũng được đọc lại bằng giọng nói
(ChatArea.tsx::handleSubmitForm, cờ `viaVoice` được giữ xuyên suốt từ lúc
tạo form)
   │
   ▼
POST /chat/stream {form_submission: {form_id, data}}
   │
   ├─ handle_calculate_construction_cost(floor_area_m2 = area_per_floor_m2
   │       * num_floors, region, finish_level)   — gọi TRỰC TIẾP tool,
   │       không qua tool_loop/LLM
   ▼
SSE: {"type":"text", "delta": "<kết quả text đã format sẵn>", "done":true}
   │
   ▼
Frontend: message assistant MỚI render kết quả (form cũ chuyển sang
disabled, không cho gửi lại)
```

### Vì sao không qua LLM ở cả 2 chiều

- **form_request**: nếu để LLM tự hỏi lại bằng text, user phải tự gõ đúng
  format (dễ sai, không được dẫn dắt). Regex nhận diện keyword rẻ và đủ tin
  cậy cho một tập câu hỏi có cấu trúc lặp lại cao.
- **form_submission**: dữ liệu đã có cấu trúc đầy đủ (đúng kiểu, đúng field
  bắt buộc) — để LLM "diễn giải" lại tham số hoặc tệ hơn là paraphrase con
  số kết quả chỉ thêm rủi ro sai số mà không thêm giá trị. Tool tính bằng
  code xác định, LLM không tham gia tính toán.

### Thêm intent/form mới

1. Viết tool mới trong `app/core/mcp/tools/` (nếu cần).
2. Thêm entry vào `FORM_SCHEMAS` và `_INTENT_KEYWORDS` trong
   `app/core/chat/intent.py`.
3. Thêm nhánh xử lý `form_submission.form_id == "..."` trong
   `app/api/v1/chat.py` (map field form → tham số tool).
4. Frontend: nếu field type mới ngoài `number`/`select`, mở rộng
   `ConstructionCostForm.tsx` (hoặc tách thành component chung theo
   `form_id` nếu có nhiều form).

**Giới hạn hiện tại**: chỉ có intent `construction_cost`. Các câu hỏi kiểu
"giá xây sân", "giá cải tạo"... chưa có tool tương ứng nên chưa được thêm
vào registry — đây là việc làm thêm khi có tool thật, không nên định nghĩa
form cho tool chưa tồn tại.

---

## 7. Nguồn tham khảo trong repo

- `DataRAG-uoc-luong-gia-vlxd.md` (KB "vlxd-knowledge") — playbook công thức
  đo bóc, quy tắc hao hụt, ETL — nguồn cho `formulas.py` và
  `price_extractor.py`, không chứa số liệu giá.
- `app/core/construction/formulas.py` — công thức Chương 16/17/19/20/21/22.
- `app/core/ingestion/price_extractor.py`, `price_pipeline.py` — ETL giá.
- `app/core/mcp/tools/{price_lookup,quantity,cost}_tool.py` — 3 MCP tool.
- `app/core/llm/tool_loop.py` — vòng lặp tool-calling cho `mode="agent"`.
- `app/core/chat/intent.py` — intent detection + form schema registry.
