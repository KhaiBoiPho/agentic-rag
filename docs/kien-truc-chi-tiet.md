# Kiến trúc chi tiết hệ thống Agentic RAG (VLXD)

Tài liệu này mô tả **toàn bộ** luồng vận hành thực tế của hệ thống: từ lúc nạp
tài liệu (chunking, xử lý bảng, trích giá), qua lưu trữ vector, đến luồng chat
(small-talk, phát hiện ý định, guard kiểm chủ đề, RAG, dự toán chi phí), các
sub-model phụ trợ, giọng nói, và danh sách API. Mọi con số/tham số nêu ra đều
lấy trực tiếp từ mã nguồn (đường dẫn file kèm theo để tra cứu).

> Quy ước đọc: `app/...py:NN` = file:dòng. Các hằng số cấu hình mặc định nằm ở
> [app/config.py](../app/config.py), giá trị chạy thật lấy từ `.env`.
>
> **Tài liệu liên quan:** [kien-truc-he-thong.md](kien-truc-he-thong.md) (tổng
> quan kiến trúc), [construction-pricing-pipeline.md](construction-pricing-pipeline.md)
> (đặc tả sâu luồng giá — bổ trợ §5 & §8), [getting-started.md](getting-started.md)
> (chạy thử), [railway-deploy.md](railway-deploy.md) (triển khai).

---

## 0. Bản đồ công nghệ

| Thành phần | Công nghệ | Vai trò |
|---|---|---|
| API / SSE | **FastAPI** + Uvicorn (`app/main.py`) | HTTP + streaming token qua Server-Sent Events |
| CSDL quan hệ | **PostgreSQL** (SQLAlchemy async + asyncpg) | user, KB, document, message, **material_prices**, notes, projects, usage |
| Vector DB | **Qdrant** (dense + sparse) | lưu embedding của chunk, tìm kiếm ngữ nghĩa có lọc metadata |
| Hàng đợi | **RabbitMQ** (aio-pika) | nạp tài liệu bất đồng bộ (không chặn request upload) |
| LLM/Embedding | **OpenRouter** (OpenAI-compatible SDK) | chat streaming, embedding, vision-OCR, các sub-model |
| STT (giọng → text) | **PhoWhisper** (faster-whisper/CTranslate2) | nhận dạng tiếng Việt, chạy in-process hoặc HTTP GPU |
| TTS (text → giọng) | **OpenAI** `/v1/audio/speech` trực tiếp | đọc câu trả lời |
| Deep Research | **LangGraph** (`app/core/research/graph.py`) | vòng lặp tìm kiếm web nhiều bước |
| Web search/scrape | **Firecrawl** | tìm giá fallback + search/research |
| Đo lường | **Prometheus** middleware | latency, token, ingestion metrics |
| Tokenizer | **tiktoken** `cl100k_base` | đếm token khi chunk + ước tính usage |

Các model OpenRouter (mặc định trong `.env` của bản deploy hiện tại đều là
`openai/gpt-4o-mini`; mặc định code ở `app/config.py`):

| Thiết lập | Biến `.env` | Dùng ở đâu |
|---|---|---|
| Chat chính | `OPENROUTER_CHAT_MODEL` | câu trả lời chat/RAG (thường frontend truyền `model` cụ thể) |
| Embedding | `OPENROUTER_EMBED_MODEL` = `openai/text-embedding-3-small` | vector hoá chunk + query, **dim 1536** |
| Classifier (rẻ/nhanh) | `OPENROUTER_CLASSIFIER_MODEL` = `openai/gpt-4o-mini` | topic-guard, condense follow-up, disambiguation… |
| Research | `OPENROUTER_RESEARCH_MODEL` | các node deep-research |
| Vision | `OPENROUTER_VISION_MODEL` | OCR trang PDF scan |

---

## 1. Vòng đời tài liệu: Upload → Queue → Ingest

### 1.1. Hai đường upload (đều trả `202 Accepted` + `job_id`)

File: [app/api/v1/documents.py](../app/api/v1/documents.py)

1. **Upload thường** — `POST /api/v1/documents/upload/{kb_id}`
   - Nhận file (`.pdf/.docx/.doc/.txt/.md`), đẩy job vào RabbitMQ với `mode="standard"`.
   - Chỉ chunk → embed → Qdrant (RAG thuần).

2. **Upload trích giá** — `POST /api/v1/documents/upload-price/{kb_id}?region=HN&price_period=2026-06`
   - Chỉ chấp nhận cho **KB "Dự toán giá nhà"** (`is_system_kb(kb_id) and kb_id != KB_PRICING_ID` → 403).
   - `region` **bắt buộc** (HN/DN/HCM); `price_period` tuỳ chọn.
   - Đẩy job với `mode="price_extraction"` → chạy **cả** chunk→Qdrant **và** trích bảng giá có cấu trúc vào `material_prices`.

> Vì sao dùng queue: request upload chỉ enqueue rồi trả về ngay. Một PDF phụ lục
> giá dài 128 trang có thể mất hàng chục giây để chunk+embed+trích bảng — làm
> nền trong worker, không chặn HTTP. Tải tài liệu dài **không gây quá tải** vì
> mỗi job xử lý tuần tự theo lô (batch), và `prefetch_count=4` giới hạn số job
> đồng thời.

### 1.2. Hàng đợi RabbitMQ

- Publisher: [app/queue/publisher.py](../app/queue/publisher.py) — queue `ingest_jobs`, `durable=True`, message `PERSISTENT`. File được **base64** nhét vào message body cùng `kb_id/user_id/filename/config/mode`.
- Consumer: [app/queue/consumer.py](../app/queue/consumer.py) — chạy **trong chính process app** (task nền khởi động ở `main.py`), `set_qos(prefetch_count=4)`, `message.process(requeue=True)` (job lỗi được requeue). Chọn pipeline theo `mode`.

### 1.3. Cập nhật trạng thái document

Bảng `documents.status`: `pending → processing → done | error` (`app/db/postgres/models.py:101`). Frontend trang KB **poll mỗi 2.5s** khi còn document `pending/processing`.

---

## 2. Chunking — chi tiết đầy đủ

File nền: [app/core/chunking/base.py](../app/core/chunking/base.py),
[models.py](../app/core/chunking/models.py),
dispatcher: [dispatcher.py](../app/core/chunking/dispatcher.py)

### 2.1. Cấu trúc một Chunk (`models.py`)

```python
Chunk(
  content: str,            # nội dung (bảng = HTML, text = plain)
  chunk_type: TEXT|TABLE,
  document_id, kb_id, filename, page_num,
  context_above: str,      # text bao quanh (chỉ cho chunk bảng)
  context_below: str,
  token_count: int,
  metadata: dict,          # region/source_type/price_period/chunk_id/source=ocr...
)
```

**Giá trị đưa đi embedding = `full_content`** = `context_above` + `\n` +
`content` + `\n` + `context_below`. Tức chunk bảng được embedding **kèm** đoạn
văn mô tả phía trên/dưới (đây là cơ chế "collapse/thu ngữ cảnh" — xem 2.4).

### 2.2. Dispatcher theo đuôi file

`.pdf → PdfChunker`, `.docx/.doc → DocxChunker`, `.txt/.md/.markdown → TextChunker`.
Đuôi khác → `ValueError: Unsupported file type`.

### 2.3. Các tham số chunk (mặc định)

| Tham số | Mặc định | Biến `.env` | Ý nghĩa |
|---|---|---|---|
| `chunk_token_num` | **512** | `CHUNK_TOKEN_NUM` | ngân sách token/chunk text |
| `chunk_overlap_percent` | **15** | `CHUNK_OVERLAP_PERCENT` | % overlap giữa 2 chunk liền kề |
| `table_context_size` | **128** | `TABLE_CONTEXT_SIZE` | token ngữ cảnh gắn quanh chunk bảng |
| `delimiter` | `\n!?。；！？` | `CHUNK_DELIMITER` | ký tự ranh giới câu |
| `MAX_EMBED_TOKENS` | **8000** | (hằng số) | trần token/chunk cho API embedding |
| `embed_batch_size` | **32** | `EMBED_BATCH_SIZE` | số chunk/lô embedding |
| `embed_dim` | **1536** | `EMBED_DIM` | chiều vector |

### 2.4. `naive_merge` — gộp text theo token (RAGFlow-inspired)

`base.py:naive_merge()`. Duyệt tuần tự các "section" text, cộng dồn cho tới khi
vượt `chunk_token_num * (1 - overlap%)` thì **mở chunk mới**, đồng thời **kéo
phần đuôi** của chunk trước làm phần overlap đầu chunk mới (`overlap_ratio =
(100-15)/100 = 0.85`). Kết quả: các chunk ~512 token, chồng lấn ~15% để không
cắt ngang ý.

### 2.5. Xử lý PDF: text + bảng đan xen theo thứ tự đọc

File: [pdf_chunker.py](../app/core/chunking/pdf_chunker.py)

1. **Text blocks** bằng **PyMuPDF** (`page.get_text("blocks")`) — mỗi block có
   toạ độ `y`; bỏ qua block ảnh (`b[6] != 0`).
2. **Bảng** bằng **pdfplumber** (`page.extract_tables()`), lấy `y` từ bbox của
   `page.find_tables()`.
3. **Trộn theo thứ tự đọc**: gộp text-block và table-block cùng trang rồi
   **sort theo `y`** (trên→dưới). Nhờ vậy bảng nằm đúng vị trí giữa các đoạn văn.
4. **Text được gộp bằng `naive_merge`; bảng giữ nguyên là 1 chunk độc lập**
   (không trộn bảng vào text).
5. Gắn ngữ cảnh cho bảng bằng `add_table_context`.

**Bảng → HTML** (`_table_to_html`): hàng đầu là `<th>`, còn lại `<td>`:
```html
<table>
<tr><th>Tên vật liệu</th><th>Đơn vị</th><th>Giá</th></tr>
<tr><td>Xi măng PCB40</td><td>tấn</td><td>1.450.000</td></tr>
...
</table>
```
Giữ HTML (thay vì flatten) để bảo toàn quan hệ hàng–cột khi model đọc.

### 2.6. Gắn ngữ cảnh cho chunk bảng — `add_table_context` (collapse context)

`base.py:add_table_context()`. Với mỗi chunk bảng, đi **ngược lên** thu các
chunk text liền trước tới khi đủ `table_context_size` (128) token → `context_above`;
đi **xuôi xuống** → `context_below`. Cắt theo ranh giới câu (regex
`[。!?？；！\n]`). Mục đích: một bảng giá trơ trọi (chỉ số liệu) sẽ mất ngữ cảnh
"đây là bảng gì, điều kiện giá ra sao" — đoạn văn bao quanh bù lại điều đó khi
embedding và khi model đọc chunk.

### 2.7. Chunk quá khổ (bảng rộng) — tách theo hàng

`base.py:split_oversized_table_chunk()`. API embedding
(`text-embedding-3-small`) trần 8191 token; **một chunk quá khổ làm hỏng cả
lô**. Nếu `token_count > MAX_EMBED_TOKENS (8000)` và là **TABLE**:
- Tách HTML thành nhiều chunk, **lặp lại hàng header (`<tr>` đầu)** trong mỗi
  chunk để không mất ngữ cảnh cột.
- Hàng nào tự nó đã > ngân sách (một ô chứa cả đoạn ghi chú dài) → **bỏ hàng đó**.
- Sau khi tách mà vẫn còn chunk quá khổ (không phải bảng) → **loại bỏ** khỏi
  Qdrant, ghi `logger.warning` (dữ liệu giá có cấu trúc **không bị ảnh hưởng** vì
  đi đường trích riêng — xem §5).

### 2.8. DOCX

[docx_chunker.py](../app/core/chunking/docx_chunker.py): duyệt body XML theo thứ
tự DOM, `p`→text, `tbl`→HTML; text gộp `naive_merge`, bảng độc lập + gắn context.

### 2.9. Text / Markdown

[text_chunker.py](../app/core/chunking/text_chunker.py):
- `.md`: **cắt tại mỗi heading** (`^#{1,6}`), forward-fill marker
  `<!-- chunk_id: ... -->` (nếu file có), gộp `naive_merge` **theo từng nhóm
  chunk_id** để trích dẫn bám đúng mục nguồn.
- `.txt`: cắt theo đoạn (dòng trống) rồi `naive_merge`.

### 2.10. OCR fallback cho PDF scan

[ocr_fallback.py](../app/core/ingestion/ocr_fallback.py). Nếu PdfChunker trả **0
chunk** (PDF chỉ là ảnh scan, không có lớp text) → render **mỗi trang** thành ảnh
(`_RENDER_DPI=150`) và gọi **vision model** OCR (`llm.vision_ocr`), rồi chunk văn
bản thu được như bình thường. Chỉ chạy khi không có chunk nào (tránh gọi
vision-LLM mỗi trang cho PDF đã có text).

---

## 3. Pipeline nạp thường (standard)

File: [app/core/ingestion/pipeline.py](../app/core/ingestion/pipeline.py). Là
async generator, phát event tiến độ (`parsing 0.1 → chunking 0.3 → embedding
0.3–0.8 → indexing 0.9 → done 1.0`):

1. Tạo record document (`status=processing`).
2. Chunk (dispatcher) → nếu 0 chunk và là PDF → **OCR fallback**.
3. Tách chunk quá khổ (§2.7).
4. **Embedding theo lô** `embed_batch_size=32`: mỗi lô gọi `llm.embed([full_content...])`.
5. **Upsert Qdrant** (§4).
6. `status=done`, `chunk_count=total`. Đo `INGESTION_CHUNK_COUNT`, `INGESTION_DURATION`.

Lỗi ở bất kỳ bước nào → `status=error` + event `stage=error`.

---

## 4. Embedding & lưu trữ vector (Qdrant)

File: [app/db/qdrant/client.py](../app/db/qdrant/client.py),
[app/core/retrieval/retriever.py](../app/core/retrieval/retriever.py)

### 4.1. Payload mỗi point

```python
{
  "document_id", "kb_id", "filename", "chunk_type",
  "content", "context_above", "context_below", "full_content",
  "page_num", "token_count",
  "metadata": { region?, source_type?, price_period?, chunk_id?, source? }
}
```

- Collection có **dense vector** (COSINE, size = `embed_dim` 1536) **và sparse
  vector** (khai báo sẵn để mở rộng hybrid).
- Upsert theo lô `batch_size=200` (một phụ lục 699 trang sinh hàng nghìn point,
  upsert một phát dễ `WriteTimeout`).

### 4.2. Truy hồi (retriever)

`retriever.search()` → embed query → `qdrant.search()`. Bộ lọc dựng bằng
`must`:
- `kb_id` (một KB, hoặc **danh sách** KB khi chat theo Project).
- `metadata.{key}` nếu có `metadata_filters`.
- **`region`** (đặc biệt cho KB giá): điều kiện **"đúng vùng HOẶC không gắn
  vùng"** — `Filter(should=[region==X, IsEmpty(region)])`. Nhờ vậy chunk
  region-agnostic (file .md không gắn vùng, chunk kiến thức) **không bị loại**,
  đồng thời chunk giá **sai vùng** vẫn bị loại. (Đây là fix cho lỗi badge "Plain
  chat" và recall — xem §7.6.)

`RetrievedChunk` mang thêm `region`, `price_period` lấy từ `payload.metadata` để
tầng chat gắn nhãn nguồn cho model.

---

## 5. Trích xuất giá có cấu trúc (bảng → `material_prices`)

Đây là điểm mấu chốt: **file định dạng PDF có bảng giá**, upload qua
`/upload-price`, sẽ vừa được chunk cho RAG **vừa** được bóc thành các dòng giá có
cấu trúc trong bảng `material_prices` — nguồn dữ liệu **chính xác, tất định** cho
tính năng dự toán (khác với tìm kiếm ngữ nghĩa).

File: [price_pipeline.py](../app/core/ingestion/price_pipeline.py) (điều phối),
[price_extractor.py](../app/core/ingestion/price_extractor.py) (bóc bảng).

### 5.1. Pipeline giá (`price_pipeline.py`) chạy song song 2 việc

1. **Chunk narrative → Qdrant** (giống pipeline thường) — nhưng **mỗi chunk được
   gắn metadata** `{region, source_type, price_period}` để retrieval lọc đúng
   vùng/kỳ. Giữ được phần "điều kiện giá, phạm vi áp dụng" cho RAG.
2. **Bóc bảng → Postgres** (`extract_price_rows`) vào `material_prices`.

### 5.2. Phân loại file nguồn (`classify_source_file`)

Theo tên file → `official_announcement` (công văn), `official_annex` (phụ lục),
hay `vendor_quote` (báo giá doanh nghiệp). Ảnh hưởng thứ tự ưu tiên nguồn.

### 5.3. Nhận diện header bảng (`_detect_header`)

- Dò trong **6 hàng đầu**, khớp **từ khoá** cho từng cột: tên vật liệu
  (`_NAME_KEYWORDS`), đơn vị (`_UNIT_KEYWORDS`), nhóm (`_CATEGORY_KEYWORDS`), và
  các loại giá (tại mỏ/tại chân công trình/giá bán chung — `_PRICE_*`).
- **Header có thể trải ≥2 dòng vật lý** ("GIÁ BÁN…" ở dòng trên, "Tại nơi sản
  xuất/Tại chân công trình" ở dòng dưới) → gộp qua cửa sổ, dòng đầu tiên không
  khớp gì (sau khi cửa sổ bắt đầu) đánh dấu kết thúc header.
- Bỏ qua **hàng chú thích chỉ số cột** ("1","2","3"…) hay gặp lặp đầu mỗi trang.
- Yêu cầu tối thiểu: có cột **tên** và **đơn vị** và **ít nhất 1 cột giá**, nếu
  không → bỏ bảng (ghi warning).

### 5.4. Đọc dòng dữ liệu (`_parse_data_rows`)

- **Forward-fill nhóm vật liệu**: hàng "group header" (ô đơn vị trống, ≤2 ô có
  chữ, ô category/name mang tên nhóm như "I | XI MĂNG | | |") → cập nhật
  `current_category` cho các dòng sau (mô phỏng merged-cell).
- Collapse xuống dòng trong tên/nhóm (`"Đá xây\ndựng"` → `"Đá xây dựng"`) để
  ILIKE lookup khớp.
- Một dòng có thể sinh **nhiều** `MaterialPriceRow` nếu có nhiều cột giá (giá tại
  mỏ `tai_mo`, tại chân công trình `tai_chan_cong_trinh`, giá chung `khong_ro`).
- **Số VN**: `.` = phân cách nghìn, `,` = thập phân; xử lý cả ô bị dính khoảng
  trắng lỗi font ("1 8.000" → "18.000"). Giá ≤ 0 bị loại.
- **An toàn hơn im lặng đoán**: dòng có tên+đơn vị nhưng **không đọc được giá** →
  KHÔNG tạo row, đẩy vào `warnings` (một match sai giá → dự toán sai).

### 5.5. Bảng trải nhiều trang (continuation)

`extract_price_rows`. Một phụ lục có thể là **1 bảng dài 128 trang** không lặp
header. Cơ chế: **giữ lại column-mapping và `current_category`** từ trang cuối
CÓ header; trang sau **không có header nhưng cùng số cột** → coi là tiếp nối. Số
cột khác → là bảng/section khác, **không tái dùng** mapping (tránh đọc nhầm cột).

### 5.6. Bảng `material_prices` (Postgres)

`app/db/postgres/models.py:MaterialPrice`. Cột chính: `region`,
`material_category`, `material_name`, `spec`, `unit`, `price_ex_vat` (Numeric
18,2), `price_basis`, `source_type`, `price_period`, `manufacturer`,
`raw_row_text` (dòng gốc để đối soát). FK `document_id` → xoá document sẽ xoá
kèm các row giá (`cascade="all, delete-orphan"`).

> **Tóm tắt "file nào ra được giá":** chỉ **PDF thật có bảng giá bóc được** (bằng
> pdfplumber), upload qua `/upload-price` với `region` đúng. File `.md`/`.txt`
> hay PDF scan không bảng **không** sinh row giá (nhưng vẫn thành chunk RAG nếu
> upload thường).

---

## 6. Luồng chat — thứ tự xử lý (rất quan trọng)

File: [app/api/v1/chat.py](../app/api/v1/chat.py), endpoint
`POST /api/v1/chat/stream` (SSE). Bên trong `generate()` chạy **theo thứ tự**,
trả sớm ngay khi một nhánh xử lý xong:

```
0. form_submission != null  → CÔNG CỤ DỰ TOÁN (không gọi LLM để tính, chỉ để trình bày)
1. small talk (khớp CHÍNH XÁC)     → câu chào/cảm ơn có sẵn, KHÔNG gọi LLM
2. intent detection (bỏ qua nếu via_voice) → phát 'form_request' để FE render form
3. off-topic guard (chỉ khi KHÔNG có kb_id/project_id/skill_id) → sub-model phân loại
4. mode == "agent"                 → tool-loop (LLM tự gọi công cụ MCP)
5. mặc định: RAG / plain chat      → truy hồi + stream LLM
```

### 6.1. Small talk (không tốn API)

`intent.py:detect_small_talk()`. **Khớp chính xác** (chuẩn hoá bỏ dấu câu, cắt
độ dài ≤40 ký tự) với các cụm: chào/tạm biệt/cảm ơn/hỏi thăm/bạn-là-ai/bạn-làm-
được-gì/xin-lỗi. Trả câu có sẵn (random trong list), **0 lần gọi model**. Cố ý
**không** khớp substring (để "chào bạn, giá thép bao nhiêu" không bị nuốt thành
câu chào), và **không** đưa "ok"/"không" vào (thường là trả lời cho câu hỏi
trước, không đứng độc lập được).

### 6.2. Phát hiện ý định (fixed-intent) → form

`intent.py:detect_intent()` + `FORM_SCHEMAS`. Dùng **khớp tổ hợp nhóm từ khoá**
(mỗi nhóm cần ≥1 từ xuất hiện): với `construction_cost` cần cả 3 nhóm
`["nhà"]` + `["xây"/"xây dựng"/"thi công"/"làm nhà"/"dự toán"]` +
`["giá"/"chi phí"/"bao nhiêu tiền"/…/"dự toán"]`. Khớp → **không gọi LLM**, phát
event `form_request` (schema field: diện tích/tầng/khu vực/mức hoàn thiện/ngân
sách tuỳ chọn) kèm `prefill` (bóc sẵn diện tích, khu vực, ngân sách từ câu hỏi
bằng regex `_AREA_RE`, `_REGION_KEYWORDS`, `_BUDGET_RE`). **Bỏ qua hoàn toàn khi
`via_voice=true`** (câu thoại đi thẳng RAG để không hiện form thất thường lúc
demo).

### 6.3. Off-topic guard — **sub-model kiểm chủ đề VLXD**

File: [app/core/chat/topic_guard.py](../app/core/chat/topic_guard.py). **Chỉ chạy
khi không có KB/project/skill** (khi đã chọn KB thì "đúng chủ đề" là do KB định
nghĩa). Gọi **classifier model** (`openai/gpt-4o-mini`, `temperature=0`,
`max_tokens=5`) trả **YES/NO**: câu có liên quan xây dựng/vật liệu/kỹ thuật (hiểu
RỘNG) không. NO → trả câu từ chối lịch sự (`refusal_reply()`), không chạy model
chính. **Fail-open**: lỗi classifier → cho câu đi tiếp (không chặn oan).

### 6.4. Agent mode (tool-loop) — LLM tự gọi công cụ

File: [app/core/llm/tool_loop.py](../app/core/llm/tool_loop.py). Khi
`mode=="agent"`: nạp history + để model **tự quyết** gọi công cụ MCP
(`lookup_material_price`, `estimate_material_quantity`,
`calculate_construction_cost`) qua function-calling, vòng lặp bounded
`max_rounds=4` (call → execute tool → call lại với kết quả → trả lời).
`tool_call_log` được trả về client như `sources` để phân biệt câu trả lời có
dùng công cụ.

### 6.5. Đường RAG / plain chat (mặc định)

Đây là đường phổ biến nhất. Trình tự trong `chat.py`:

1. **Nạp history** (`msg_repo.get_recent(conversation_id, limit=10)`) — TRƯỚC khi
   truy hồi, vì câu tiếp nối cần history để viết lại.
2. **Condense follow-up** (§7.1) — nếu câu ngắn (≤8 từ) và có history → viết lại
   thành câu độc lập bằng sub-model.
3. **Phát hiện & lọc vùng** (chỉ KB giá) (§7.2):
   - 0 vùng → không lọc.
   - 1 vùng → lọc `region=X` (OR không-gắn-vùng), **ngưỡng nới 0.4** (chunk bảng
     giá embed yếu, ~0.45–0.48, dưới ngưỡng 0.5 mặc định).
   - ≥2 vùng (so sánh) → **truy hồi riêng từng vùng** (top_k=4 mỗi vùng, ngưỡng
     0.4) rồi gộp, đảm bảo mỗi vùng có mặt.
4. **Dựng context có nhãn**: mỗi đoạn ghi rõ `[i] (khu vực: …, kỳ công bố: …,
   nguồn: file.pdf): <nội dung>` (`_format_context_chunk`). Nhờ nhãn vùng, model
   **không lấy giá vùng khác** trả cho vùng được hỏi.
5. **Ghép prompt**: `system_prompt` + `history` + `user_msg` (context + câu hỏi).
6. **Stream LLM** (`llm.stream_chat`), đẩy từng token qua SSE.
7. **Badge/`rag_context`**: chỉ đặt `rag_context` khi **có `sources`** (truy hồi
   ra chunk). Frontend hiện "RAG · <tên KB>" khi có `rag_context` + có citation;
   ngược lại "Chat thường — không dùng RAG".
8. **Lưu lượt** vào `messages` (user + assistant + sources), ghi `usage_records`.

### 6.6. System prompt & các quy tắc chống bịa (VLXD)

`_DEFAULT_SYSTEM` trong `chat.py` chứa các quy tắc cứng:
- **Không bịa số giá** khi không có dữ liệu thật kèm theo.
- **Khớp đúng khu vực**: chỉ có HN/DN/HCM; hỏi vùng khác (Cần Thơ…) → nói thẳng
  chưa có, **tuyệt đối không** lấy giá vùng khác thay thế.
- **Ưu tiên dữ liệu Context** hơn kiến thức chung.
- **Từ chối câu ngoài phạm vi dù trùng từ khoá** ("thớt gỗ" dù có "gỗ").
- **Câu tiếp nối**: suy chủ đề từ lượt trước (không hỏi lại "bạn hỏi vật liệu gì").
- Câu chung chung mà dữ liệu chỉ có sản phẩm hẹp → không liệt kê số, hỏi lại.

---

## 7. Các sub-model phụ trợ (tổng hợp)

| Sub-model | File | Model | Temp / Max tok | Mục đích |
|---|---|---|---|---|
| **Topic guard** (validate VLXD) | `chat/topic_guard.py` | classifier (gpt-4o-mini) | 0 / 5 | YES/NO câu có thuộc chủ đề xây dựng, chặn lạc đề trước model chính |
| **Condense follow-up** (nối RAG) | `chat/followup.py` | classifier | 0 / 64 | viết lại câu tiếp nối ngắn thành câu độc lập để truy hồi đúng |
| **Query contextualize** (search/research) | `chat/query_context.py` | gpt-4o-mini | 0 / 60 | viết lại câu hỏi thành truy vấn web độc lập, đủ ngữ cảnh |
| **Disambiguation giá** | `mcp/tools/cost_tool.py` | gpt-4o-mini | 0 / 10 | chọn ĐÚNG dòng vật liệu trong danh sách ứng viên DB (hoặc -1 nếu không có) |
| **Vision OCR** | `ingestion/ocr_fallback.py` | vision model | — | OCR trang PDF scan thành text |
| **Embedding** | `llm/openrouter.py` | text-embedding-3-small | — | vector hoá chunk + query (dim 1536) |
| **Research nodes** | `research/nodes/*` | research model | — | mở rộng prompt, đánh giá chất lượng, tổng hợp (deep research) |

### 7.1. Condense follow-up (chi tiết) — cho luồng chat RAG nối tiếp

File: [app/core/chat/followup.py](../app/core/chat/followup.py). Câu tiếp nối
kiểu "còn ở Đà Nẵng thì sao?" tự nó không có từ khoá tra cứu → embedding ra
nhiễu. Sub-model nhận **history gần nhất (4 lượt)** + câu tiếp nối → xuất **một
câu hỏi độc lập** ("Giá thép ở Đà Nẵng là bao nhiêu?"). **Fail-open**: lỗi hoặc
xuất ra đoạn dài (>200 ký tự, tức model trả lời thay vì viết lại) → trả None,
`chat.py` fallback sang việc ghép câu hỏi lượt trước vào query.

### 7.2. Phát hiện vùng (`intent.detect_regions` / `detect_region`)

`_REGION_KEYWORDS`: HN (`hà nội/ha noi/ hn `), DN (`đà nẵng/da nang/ dn `), HCM
(`tphcm/hồ chí minh/sài gòn/ hcm `…). `detect_regions` trả **danh sách** vùng
được nêu → phân nhánh 0/1/≥2 vùng như §6.5. Phát hiện trên **câu đã condense** để
follow-up ("còn Đà Nẵng?") vẫn ra đúng vùng.

---

## 8. Công cụ dự toán chi phí xây dựng (cost tool)

File: [app/core/mcp/tools/cost_tool.py](../app/core/mcp/tools/cost_tool.py),
[app/core/construction/formulas.py](../app/core/construction/formulas.py),
[web_price_fallback.py](../app/core/mcp/tools/web_price_fallback.py)

**Nguyên tắc**: chỉ **ước lượng ý tưởng** chi phí **vật liệu chính** từ diện tích
sàn (chưa có bản vẽ), **KHÔNG** phải giá xây trọn gói. Số liệu **tất định** (công
cụ tính), LLM chỉ **trình bày lại** (không đổi số).

### 8.1. Từ diện tích → khối lượng (hệ số tham khảo/m² sàn)

`_PER_M2_COEFFICIENTS`: bê tông `0.35 m³/m²`, thép `25 kg/m²`, tường `1.0 m²/m²`,
sơn `2.2 m²/m²` × hệ số hoàn thiện (`hoan_thien_cao_cap = 1.15`). Rồi qua
`formulas.concrete/rebar/masonry_wall/paint` ra khối lượng từng vật liệu (số
viên gạch, lít sơn…).

### 8.2. Từ khối lượng → giá (DB → web fallback → "không có dữ liệu")

Với **4 hạng mục** (bê tông, thép, gạch, sơn) chạy **song song** (`asyncio.gather`):
1. `MaterialPriceRepository.lookup()` — truy vấn `material_prices` theo
   `region` + `material_name ILIKE` + **`unit ILIKE`** (đơn vị lọc bớt match sai)
   + `exclude_name_keywords` (vd loại "ống thép/mạ kẽm" khỏi query "thép"), lấy
   tối đa 15 ứng viên, mới nhất theo `price_period` trước.
2. **Sub-model disambiguation** chọn đúng 1 dòng (hoặc -1). Có giá DB → citation
   là **document nguồn** (RAG chip, score 1.0 vì là dòng chính xác, không phải
   fuzzy).
3. Không có trong DB → **`search_web_price`** (Firecrawl) → giá gắn nhãn `[n]`
   "giá từ web, chưa xác thực".
4. Cả hai đều không có → dòng "KHÔNG có dữ liệu giá".

### 8.3. Tổng & tính ngược ngân sách

- Có đủ giá 4 hạng mục → **tổng = subtotal**, hiển thị khoảng **±15%/+20%** (cấp
  độ ý tưởng). Thiếu ≥1 hạng mục lớn → **không đưa tổng** (nêu rõ thiếu gì).
- **Tính ngược ngân sách**: chi phí tuyến tính theo diện tích →
  `đơn_giá/m² = subtotal / diện_tích` (chính xác) → `diện_tích_khả_thi =
  ngân_sách / đơn_giá/m²`. Chỉ kích hoạt khi form có `target_budget_vnd`.

### 8.4. Trình bày (`COST_PRESENT_PROMPT`)

Prompt buộc: **giữ nguyên 100% mọi số**, giữ ký hiệu `[n]` cho giá web, nhắc "chỉ
là vật liệu chính chưa gồm nhân công/VAT", và **nếu không có dòng "NGÂN SÁCH MỤC
TIÊU" thì tuyệt đối không nhắc chữ "ngân sách"** (tránh bịa ngân sách). Stream ở
`temperature=0.2`.

---

## 9. Giọng nói (Voice)

File API: [app/api/v1/voice.py](../app/api/v1/voice.py)

### 9.1. STT (giọng → text) — PhoWhisper

- Dispatcher [stt.py](../app/core/voice/stt.py): `STT_BACKEND=local` →
  [local_whisper.py](../app/core/voice/local_whisper.py) (faster-whisper
  in-process); `=http` → [http_whisper.py](../app/core/voice/http_whisper.py)
  (GPU box riêng + tunnel).
- **PhoWhisper** (VinAI, fine-tune tiếng Việt) resolve qua
  [phowhisper.py](../app/core/voice/phowhisper.py): `WHISPER_MODEL_SIZE=
  phowhisper-{tiny|base|small|medium|large}` → tải subfolder tương ứng từ HF repo
  `quocphu/PhoWhisper-ct2-FasterWhisper`. Mặc định deploy: **phowhisper-medium**,
  `WHISPER_DEVICE=cpu`, `compute_type=int8`. Model **nạp sẵn lúc khởi động**
  (task nền `_load_whisper_safe` ở `main.py`) để không trả cold-load lần đầu.
- Endpoint `POST /api/v1/voice/stt` (multipart `audio`, `language=vi`).
- **Câu thoại đặt `via_voice=true`** → chat bỏ qua form/intent (§6.2). Trên UI,
  tin nhắn thoại hiển thị **Mic động** (không hiện text transcript, tránh lộ lỗi
  nhận dạng khi demo); text nhận dạng vẫn được gửi làm nội dung + lưu history.

### 9.2. TTS (text → giọng) — OpenAI trực tiếp

[tts.py](../app/core/voice/tts.py) → [openai_tts.py](../app/core/voice/openai_tts.py):
gọi **OpenAI thật** `POST /v1/audio/speech` (OpenRouter không có endpoint này),
`OPENAI_TTS_MODEL=tts-1`. Endpoint `POST /api/v1/voice/tts/stream` (body
`{text, voice}`) trả **audio stream** (WAV). Text đọc = **chính câu trả lời của
LLM** (không phải nội dung riêng).

---

## 10. Deep Research & Web Search

- **Search** (`/api/v1/search`) và **Research** (`/api/v1/research`) đều
  `contextualize_query` trước (viết lại câu hỏi tiếp nối thành truy vấn web độc
  lập — `query_context.py`).
- **Deep Research** dùng **LangGraph** (`app/core/research/graph.py`) với các
  node: mở rộng prompt → tìm web (Firecrawl) → tổng hợp nội dung → kiểm chất
  lượng (lặp tối đa `RESEARCH_MAX_ITERATIONS=3`, ngưỡng
  `RESEARCH_QUALITY_THRESHOLD=0.75`) → sinh câu trả lời có trích dẫn.

---

## 11. Danh sách API

Router: [app/api/router.py](../app/api/router.py). Tất cả dưới prefix `/api`,
cần Bearer JWT trừ auth/health.

| Nhóm | Prefix | Endpoint tiêu biểu |
|---|---|---|
| Health | `/` | `GET /health`, `/metrics` (Prometheus) |
| Auth | `/api/v1/auth` | `POST /register`, `/login`, `/refresh`, `/logout`; OAuth Google/GitHub |
| Knowledge Base | `/api/v1/kb` | `GET /kb`, `POST /kb`, … (4 KB hệ thống hardcode) |
| Documents | `/api/v1/documents` | `POST /upload/{kb_id}`, `POST /upload-price/{kb_id}`, `GET /{kb_id}`, `DELETE /{document_id}` |
| Chat | `/api/v1/chat` | `POST /stream` (SSE), `GET /history/{conversation_id}` |
| Research | `/api/v1/research` | deep research (LangGraph) |
| Search | `/api/v1/search` | web search (Firecrawl) |
| Voice | `/api/v1/voice` | `POST /stt`, `POST /tts/stream` |
| Config | `/api/v1/config` | model list, thiết lập |
| Notes | `/api/v1/notes` | CRUD ghi chú cá nhân |
| Projects | `/api/v1/projects` | bó nhiều KB để chat truy hồi đa-KB |
| Usage | `/api/v1/usage` | tổng hợp token/chi phí/độ trễ |

### 11.1. Sự kiện SSE của `/chat/stream`

- `{type:"text", delta:"...", done:false}` — từng token.
- `{type:"text", delta:"", done:true, sources:[...], rag_context:{kind,name}}` —
  kết thúc, kèm citation + badge.
- `{type:"form_request", form_id, title, fields, prefill, done:true}` — yêu cầu
  render form (intent).

---

## 12. Cơ sở dữ liệu & Migrations

### 12.1. PostgreSQL (bảng chính — `app/db/postgres/models.py`)

`users`, `refresh_tokens`, `knowledge_bases`, `documents` (+`doc_metadata`
JSONB), `conversations`, `messages` (+`sources` JSON), `research_records`,
**`material_prices`**, `notes`, `projects` + `project_kbs` (M-N),
`usage_records`.

### 12.2. Migrations (Alembic — `migrations/versions/`)

| Rev | Nội dung |
|---|---|
| 0001 | schema gốc |
| 0002 | bảng `material_prices` (rỗng) |
| 0003 | user hệ thống + 2 KB đầu |
| 0004 | notes + projects |
| 0005 | usage_records |
| 0006 | index `(conversation_id, created_at)` cho history |
| 0007 | đổi tên 2 KB + thêm 2 KB (thành 4 KB hệ thống) |

**4 KB hệ thống** (id cố định, `app/core/bootstrap/constants.py`): Kiến thức về
VLXD cho kỹ sư · Dự toán giá nhà · Báo giá doanh nghiệp · Quy chuẩn & tiêu chuẩn
VN. Chỉ **"Dự toán giá nhà"** dùng `/upload-price`; sau migrate các KB **rỗng**,
nạp dữ liệu bằng upload thủ công (không còn auto-seed).

### 12.3. Qdrant

Collection `agentic_rag_chunks` (mặc định), dense COSINE 1536 + sparse. Xoá
document → xoá vector theo `document_id` (`delete_by_document`).

---

## 13. Khởi động & vận hành (`main.py`)

Thứ tự startup: `init_db()` (tạo bảng nếu thiếu — dev) → `ensure_collection()`
Qdrant (optional, retry lazy) → task nền **RabbitMQ consumer** → (nếu
`STT_BACKEND=local`) task nền **nạp PhoWhisper**. CORS theo `CORS_ORIGINS`.
Prometheus middleware nếu bật. `uvicorn --reload` khi `APP_DEBUG=true` (đổi code
Python có hiệu lực ngay).

### Docker Compose (dev)

`app` (bind-mount `.:/app` → sửa code Python live), `ui` (Next.js, build image —
đổi frontend phải rebuild), `postgres`, `qdrant`, `rabbitmq`, `migrate`
(chạy `alembic upgrade head` rồi thoát), `prometheus`, `grafana`.

---

## 14. Tóm tắt luồng end-to-end (một câu hỏi giá điển hình)

```
User (thoại/gõ): "giá xi măng ở Hà Nội bao nhiêu?"  (KB "Dự toán giá nhà")
  → chat/stream
  → không phải form_submission, không small-talk
  → intent: nếu là "dự toán nhà 100m2" → form; ở đây là hỏi giá → đi tiếp
  → có kb_id nên KHÔNG chạy topic-guard
  → mode mặc định: RAG
      • nạp history (10 lượt)
      • câu đủ dài → không condense
      • detect_regions → [HN] → lọc region=HN (OR không-gắn-vùng), ngưỡng 0.4
      • truy hồi Qdrant → chunk bảng giá HN + nhãn "(khu vực: Hà Nội, nguồn: …)"
      • prompt: system + history + context + câu hỏi
      • stream LLM → "Xi măng bao PCB40: 1.450.000đ/tấn …"
      • có sources → rag_context = {kb, "Dự toán giá nhà"} → badge "RAG"
      • lưu message + usage
  → (nếu thoại) TTS OpenAI đọc lại câu trả lời
```

Với câu **"xây nhà 100m² 2 tầng ở Hà Nội hết bao nhiêu?"**: intent khớp →
`form_request` → user điền form → `form_submission` → **cost tool** (hệ số →
khối lượng → tra `material_prices` + disambiguation + web fallback) →
`COST_PRESENT_PROMPT` trình bày (giữ nguyên số) → badge RAG nếu có giá từ DB.
