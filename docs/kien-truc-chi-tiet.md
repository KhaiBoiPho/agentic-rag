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
văn mô tả phía trên/dưới (đây là cơ chế "collapse/thu ngữ cảnh" — xem §2.8).

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

**Bảng chạy trước text**, vì bbox của bảng là thứ dùng để lọc text:

1. **Bảng** bằng **pdfplumber** — qua `extract_tables_resolved()` (§2.6) chứ
   không phải `page.extract_tables()` thô. Lấy `y` và bbox từ
   `page.find_tables()`.
2. **Text blocks** bằng **PyMuPDF** (`page.get_text("blocks")`) — mỗi block có
   toạ độ `y`; bỏ block ảnh (`b[6] != 0`) và **bỏ block nào có tâm nằm trong
   bbox của bảng** (`_in_any_bbox`, biên 2pt).
3. **Trộn theo thứ tự đọc**: gộp text-block và table-block cùng trang rồi
   **sort theo `y`** (trên→dưới). Nhờ vậy bảng nằm đúng vị trí giữa các đoạn văn.
4. **Text được gộp bằng `naive_merge`; bảng giữ nguyên là 1 chunk độc lập**
   (không trộn bảng vào text).
5. Gắn ngữ cảnh cho bảng bằng `add_table_context` (§2.8).

**Vì sao phải lọc text theo bbox bảng.** PyMuPDF không biết vùng nào là bảng —
nó trả chữ **bên trong** bảng ra như text block rời, thứ tự khó đoán. Không lọc
thì nội dung bảng có mặt ở **cả hai** loại chunk, và các mảnh ô bị xáo trộn chui
vào chunk text lân cận lẫn `context_above/below` của chính chunk bảng. Ví dụ
thật (trang 69 file `BangGia-VatTuDien-DaNang`): PyMuPDF trả 12 block, 10 block
nằm trong bbox bảng — trong đó có
`'27 Cồn Dầu 2, Phường Hòa Xuân, TP Đà Nẵng 4.446.000'` (một địa chỉ dính liền
một cái giá). Sau khi lọc chỉ còn 2 block header/footer trang. Trên toàn bộ 10
PDF nguồn: **3.163 → 1.195 chunk** (−62%), số chunk bảng không đổi (795).

**`page_num` lấy theo section đầu tiên.** `flush_text()` dùng
`naive_merge_with_origins()` ([base.py](../app/core/chunking/base.py)) — trả về
`(text, origin_idx)` — nên mỗi chunk text mang trang của section **đầu tiên**
góp vào nó. Buffer text có thể trải vài trang trước khi gặp bảng; gán tất cả
theo trang cuối cùng nhìn thấy sẽ đẩy trích dẫn đi xa hàng chục trang.

**Bảng → HTML** (`_table_to_html`): hàng header là `<th>` (nếu xác định được —
xem §2.7), còn lại `<td>`:
```html
<table>
<tr><th>Tên vật liệu</th><th>Đơn vị</th><th>Giá</th></tr>
<tr><td>Xi măng PCB40</td><td>tấn</td><td>1.450.000</td></tr>
...
</table>
```
Giữ HTML (thay vì flatten) để bảo toàn quan hệ hàng–cột khi model đọc.

### 2.6. Ô gộp và ký hiệu lặp — `table_extract.py`

File: [table_extract.py](../app/core/chunking/table_extract.py). **Dùng chung
cho cả chunker RAG và extractor giá có cấu trúc (§5)** để hai đường nhìn thấy
cùng một lưới.

**Vấn đề.** `page.extract_tables()` chỉ đặt chữ của ô gộp theo chiều dọc vào
**hàng mà ô đó bắt đầu**, mọi hàng tiếp theo trả rỗng. Trong phụ lục vật tư điện
Đà Nẵng, ô "Tiêu chuẩn kỹ thuật" gộp suốt một họ sản phẩm → chỉ **1/12** mẫu đèn
dính với `"CE, ENEC, IEC60598-2-3, RoHS…"`. Câu hỏi *"tiêu chuẩn RoHS áp dụng
cho vật liệu nào"* truy hồi được đúng chunk, nhưng trong chunk chỉ thấy một sản
phẩm có tiêu chuẩn → model lấp chỗ trống bằng kiến thức chung, trả lời sai.

#### Ví dụ hình dung — một bảng thu nhỏ

Bảng như mắt người nhìn thấy trên trang PDF:

```
        cột0   cột1               cột2      cột3                   cột4        cột5
       ┌─────┬──────────────────┬─────────┬──────────────────────┬───────────┬───────────┐
hàng0  │ TT  │ TÊN VẬT LIỆU     │ ĐƠN VỊ  │ TIÊU CHUẨN KỸ THUẬT  │ GHI CHÚ   │ GIÁ BÁN   │
       ├─────┼──────────────────┼─────────┼──────────────────────┼───────────┼───────────┤
hàng1  │  1  │ DHP-STR02A 30W   │ đ/bộ    │                      │ Hàng đặt  │ 4.446.000 │
       ├─────┼──────────────────┼─────────┤                      ├───────────┼───────────┤
hàng2  │  2  │ DHP-STR02A 40W   │    -    │   CE, ENEC,          │           │ 5.087.250 │
       ├─────┼──────────────────┼─────────┤   IEC60598-2-3,      ├───────────┼───────────┤
hàng3  │  3  │ DHP-STR02A 50W   │    -    │   RoHS               │           │ 5.785.500 │
       ├─────┼──────────────────┼─────────┤                      ├───────────┼───────────┤
hàng4  │  4  │ DHP-STR02A 60W   │    -    │                      │           │ 6.184.500 │
       └─────┴──────────────────┴─────────┴──────────────────────┴───────────┴───────────┘
```

Hai cột dưới đây là mấu chốt, và chúng **ngược nhau** dù ở hàng 2 đều trông
"trống":

- **cột3 (TIÊU CHUẨN)** — giữa hàng 1→4 **không có đường kẻ ngang nào**. Đó là
  **một ô duy nhất cao bằng 4 hàng**; chữ căn giữa nên trông như thuộc hàng 2–3.
  Hàng 2 trống vì **tiêu chuẩn RoHS vẫn đang áp dụng cho nó**.
- **cột4 (GHI CHÚ)** — **có** đường kẻ ngang giữa mọi hàng: **4 ô riêng biệt**,
  3 ô dưới rỗng. Hàng 2 trống vì **nó thật sự không có ghi chú** ("Hàng đặt" chỉ
  áp cho hàng 1).

`grid = table.extract()` — **chỉ có chữ, mất thông tin đường kẻ**:

```python
['TT', 'TÊN VẬT LIỆU',   'ĐƠN VỊ', 'TIÊU CHUẨN KỸ THUẬT',          'GHI CHÚ',  'GIÁ BÁN'  ]
['1',  'DHP-STR02A 30W', 'đ/bộ',   'CE, ENEC, IEC60598-2-3, RoHS', 'Hàng đặt', '4.446.000']
['2',  'DHP-STR02A 40W', '-',      '',                             '',         '5.087.250']
['3',  'DHP-STR02A 50W', '-',      '',                             '',         '5.785.500']
['4',  'DHP-STR02A 60W', '-',      '',                             '',         '6.184.500']
```

`grid[2][3]` và `grid[2][4]` **đều là `''`** — nhìn vào lưới chữ không thể phân
biệt "trống vì bị ô gộp phủ" với "trống thật".

`rows = table.rows` — **thông tin đường kẻ, thứ vừa bị mất**:

```
rows[0].cells = [ ▭ ,  ▭ ,  ▭ ,   ▭    ,  ▭ ,  ▭ ]
rows[1].cells = [ ▭ ,  ▭ ,  ▭ ,  ▭▭▭▭  ,  ▭ ,  ▭ ]   ← ô cột3 CAO GẤP 4 HÀNG
rows[2].cells = [ ▭ ,  ▭ ,  ▭ ,  None  ,  ▭ ,  ▭ ]
rows[3].cells = [ ▭ ,  ▭ ,  ▭ ,  None  ,  ▭ ,  ▭ ]
rows[4].cells = [ ▭ ,  ▭ ,  ▭ ,  None  ,  ▭ ,  ▭ ]
                                   ▲       ▲
                                   │       └─ cột4: LUÔN có ô thật (chỉ là rỗng)
                                   └───────── cột3: không có ô nào bắt đầu ở đây,
                                              vì ô của hàng1 đã phủ xuống
```

`None` **không** có nghĩa "ô rỗng". Nó có nghĩa **"vị trí này không phải một ô —
nó là phần thân của ô phía trên"**. Đó chính là thứ phân biệt được hai cột mà
lưới chữ không phân biệt nổi.

**Cách giải — dựa vào hình học, không đoán chuỗi.** `_resolve()` duyệt từ trên
xuống, giữ mảng `last[cột]` = giá trị gần nhất từng thấy ở cột đó:

| ô | `extract()` | `rows[r].cells[c]` | `_resolve()` làm gì |
|---|---|---|---|
| thân của ô gộp | `''` | `None` | lấy `last[c]` (giá trị gần nhất ở cột đó) |
| ô rỗng thật (có viền) | `''` | bbox | **giữ rỗng**, và `last[c] = ''` |
| ô có chữ | chữ | bbox | giữ nguyên, cập nhật `last[c]` |

Áp vào ví dụ trên:

| hàng | cột | chữ trong `grid` | hình học | quyết định |
|---|---|---|---|---|
| 1 | 3 | `'CE, ENEC…'` | ô thật | giữ, `last[3] = 'CE, ENEC…'` |
| 2 | 3 | `''` | **`None`** | → **`'CE, ENEC…'`** |
| 3 | 3 | `''` | **`None`** | → **`'CE, ENEC…'`** |
| 4 | 3 | `''` | **`None`** | → **`'CE, ENEC…'`** |
| 1 | 4 | `'Hàng đặt'` | ô thật | giữ, `last[4] = 'Hàng đặt'` |
| 2 | 4 | `''` | **ô thật** | **giữ rỗng**, `last[4] = ''` |
| 3–4 | 4 | `''` | ô thật | giữ rỗng |

Kết quả — cột3 điền đủ, cột4 vẫn rỗng, đúng như bảng gốc:

```python
['1', 'DHP-STR02A 30W', 'đ/bộ', 'CE, ENEC, IEC60598-2-3, RoHS', 'Hàng đặt', '4.446.000']
['2', 'DHP-STR02A 40W', '-',    'CE, ENEC, IEC60598-2-3, RoHS', '',         '5.087.250']
['3', 'DHP-STR02A 50W', '-',    'CE, ENEC, IEC60598-2-3, RoHS', '',         '5.785.500']
['4', 'DHP-STR02A 60W', '-',    'CE, ENEC, IEC60598-2-3, RoHS', '',         '6.184.500']
```

Nếu chỉ làm *"ô nào rỗng thì copy dòng trên"* — không nhìn hình học — thì cột3
vẫn đúng, nhưng **cột4 cũng bị điền `'Hàng đặt'` cho cả 4 hàng**: tự bịa ra ghi
chú cho 3 sản phẩm không hề có. Với bảng giá vật liệu, các cột "Ghi chú",
"Điều kiện thương mại", "Vận chuyển" đều là loại thông tin chỉ áp cho **một**
dòng cụ thể, nên sai kiểu này là bịa dữ liệu không có trong tài liệu.

#### Ký hiệu lặp (ditto)

Dạng chữ của cùng ý "như trên": `-nt-`, `nt`, `-//-`, `"`, `''`, `như trên` →
bung ra thành giá trị phía trên. Dấu `-` trần **cố ý không** coi là ditto ở tầng
này (nó cũng có nghĩa "không áp dụng"); chỉ extractor giá resolve nó **trong cột
đơn vị**, nơi `-` không thể là đơn vị hợp lệ (`is_unit_ditto`).

#### Hai API

`extract_tables_resolved(page)` trả lưới đã điền; `extract_tables_with_raw(page)`
trả kèm lưới **chưa điền**. Bên gọi nào phân loại dòng theo *độ rỗng* thì bắt
buộc dùng bản raw — dòng tiêu đề nhóm vật liệu được nhận ra nhờ "gần như mọi ô
đều rỗng", mà sau khi điền nó thừa hưởng đơn vị, tiêu chuẩn và cả **tên vật
liệu** của họ phía trên, trông hệt một dòng dữ liệu bình thường (§5.4).

#### Giới hạn còn lại

Nếu ô gộp bắt đầu *dưới* dòng đầu của khối (chữ căn giữa, đường kẻ cắt ngay dưới
dòng đầu) thì dòng đầu có ô riêng rỗng thật và không được điền. Trên khối đèn
CDE: 12/13 dòng có tiêu chuẩn thay vì 1/13. Không điền ngược lên vì đó là suy
đoán, không phải hình học.

### 2.7. Header của bảng nối trang — `_resolve_header`

pdfplumber bóc **một bảng cho mỗi trang**. Phụ lục Hà Nội quý II/2026 cho đúng
**700 chunk bảng trên 699 trang** — tức 1 trang = 1 bảng, gần như tuyệt đối; một
bảng giá dài 699 trang về thành 699 bảng rời. Không xử lý thì dòng dữ liệu đầu
tiên của **mọi** trang tiếp theo bị gán `<th>` — nói với model rằng `12.883.415`
là tên một cột.

`_resolve_header(grid, prev_header, prev_ncol)` xét theo thứ tự:

1. Dòng đầu **trùng** header bảng trước → header lặp lại bình thường.
2. **Cùng số cột** nhưng dòng đầu rõ ràng là dữ liệu → trang nối tiếp: **mượn
   header trang trước**, toàn bộ dòng trang này là `<td>`.
3. Dòng đầu **trông như header** → header mới.
4. Không rơi vào nhánh nào → **không phát `<th>`**. Gán nhầm một dòng sản phẩm
   thành nhãn cột tệ hơn là không có nhãn.

Ví dụ thật, bảng trang 69 của `BangGia-VatTuDien-DaNang`:

```
dòng đầu bảng TRANG 1 : ['TT', 'TÊN VẬT LIỆU, LO…', 'ĐƠN VỊ', 'TIÊU CHUẨN KỸ TH…', …]
   _looks_like_header -> True                      → header mới

dòng đầu bảng TRANG 69: ['', 'Đèn Led thanh CDE-SL13…', '-', '', '', '12.883.415']
   _looks_like_header -> False  (không có nhãn cột nào)
   => cùng 6 cột với header đang giữ → MƯỢN header trang trước,
      dòng này thành <td>, không phải <th>
```

`_looks_like_header()` đòi: ≥2 ô có chữ, không ô nào dài quá 60 ký tự, không ô
nào là số tiền thuần, **và** có ít nhất một nhãn cột quen thuộc (`_HEADER_LABELS`:
`stt`, `tên`, `đơn vị`, `giá`, `tiêu chuẩn`, `nhà sản xuất`, `ghi chú`…). Điều
kiện cuối là thứ phân biệt header thật với **dòng tiêu đề nhóm vật liệu** — cả
hai đều ngắn, thuần chữ, không có giá, nên hình dạng không đủ để tách.

Kết quả trên `BangGia-VatTuDien-DaNang` (89 chunk bảng): 78 chunk có header
đúng, 11 chunk không header — thà không có nhãn cột còn hơn nhãn sai. Trong dữ
liệu nạp bằng bản cũ, phụ lục Hà Nội có 10/700 chunk mà `<th>` là một dòng dữ
liệu, ví dụ trang 498: `<th>11</th><th></th><th>Công ty cổ phần khoa học công
nghệ Việt Nam</th>…` — chunk đó mất hoàn toàn thông tin cột (không biết cột nào
là giá, cột nào là đơn vị).

### 2.8. Gắn ngữ cảnh cho chunk bảng — `add_table_context` (collapse context)

`base.py:add_table_context()`. Với mỗi chunk bảng, đi **ngược lên** thu các
chunk text liền trước tới khi đủ `table_context_size` (128) token → `context_above`;
đi **xuôi xuống** → `context_below`. Cắt theo ranh giới câu (regex
`[。!?？；！\n]`). Mục đích: một bảng giá trơ trọi (chỉ số liệu) sẽ mất ngữ cảnh
"đây là bảng gì, điều kiện giá ra sao" — đoạn văn bao quanh bù lại điều đó khi
embedding và khi model đọc chunk.

Cơ chế này **phụ thuộc vào việc lọc text theo bbox ở §2.5**: chỉ khi các mảnh ô
bảng đã bị loại khỏi luồng text thì `context_above/below` mới là văn bản thật.
Trước khi có bộ lọc, chunk bảng của phụ lục Hà Nội nhận `context_above` là
`"nối mặt bích / tiêu chuẩn / EN 1092-2… / Y lọc gang FAF 2500 DN50 / cái /
DN50 / FAF / Thổ Nhĩ Kỳ / 3.859.200 / …"` — các ô của **chính bảng đó** bị
PyMuPDF trả về rời rạc và xáo trộn. Nguy hiểm hơn nhiễu thuần tuý: con số
`3.859.200` (của DN50) nằm trong `context_above` trong khi hàng thật trong
`<table>` là DN65 với ô giá trống, rất dễ khiến model gán sai giá cho sản phẩm.
Với phụ lục gần như toàn bảng (không có đoạn văn xen kẽ), `context_above/below`
nay thường chỉ còn header/footer trang hoặc rỗng — đúng và vô hại, thay vì sai.

### 2.9. Chunk quá khổ (bảng rộng) — tách theo hàng

`base.py:split_oversized_table_chunk()`. API embedding
(`text-embedding-3-small`) trần 8191 token; **một chunk quá khổ làm hỏng cả
lô**. Nếu `token_count > MAX_EMBED_TOKENS (8000)` và là **TABLE**:
- Tách HTML thành nhiều chunk, **lặp lại hàng header (`<tr>` đầu)** trong mỗi
  chunk để không mất ngữ cảnh cột.
- Hàng nào tự nó đã > ngân sách (một ô chứa cả đoạn ghi chú dài) → **bỏ hàng đó**.
- Sau khi tách mà vẫn còn chunk quá khổ (không phải bảng) → **loại bỏ** khỏi
  Qdrant, ghi `logger.warning` (dữ liệu giá có cấu trúc **không bị ảnh hưởng** vì
  đi đường trích riêng — xem §5).

### 2.10. DOCX

[docx_chunker.py](../app/core/chunking/docx_chunker.py): duyệt body XML theo thứ
tự DOM, `p`→text, `tbl`→HTML; text gộp `naive_merge`, bảng độc lập + gắn context.

### 2.11. Text / Markdown

[text_chunker.py](../app/core/chunking/text_chunker.py):
- `.md`: **cắt tại mỗi heading** (`^#{1,6}`), forward-fill marker
  `<!-- chunk_id: ... -->` (nếu file có), gộp `naive_merge` **theo từng nhóm
  chunk_id** để trích dẫn bám đúng mục nguồn.
- `.txt`: cắt theo đoạn (dòng trống) rồi `naive_merge`.

### 2.12. OCR fallback cho PDF scan — hai lượt, hai model khác nhau

[ocr_fallback.py](../app/core/ingestion/ocr_fallback.py). Kích hoạt khi
PdfChunker trả **0 chunk cho toàn tài liệu** (PDF chỉ là ảnh scan, không có lớp
text). Chỉ chạy khi không có chunk nào — gọi vision model mỗi trang cho PDF đã
có text là vô ích và tốn tiền.

**Mỗi trang được render 200 DPI rồi gọi hai lượt:**

| lượt | thiết lập | vai trò |
|---|---|---|
| cấu trúc | `openrouter_vision_table_model` | xin **HTML `<table>`** |
| đối chiếu | `openrouter_vision_model` | text thuần, **chỉ để soi số** |

Đầu ra lượt cấu trúc đi qua **đúng lớp xử lý bảng** như PDF có text: thành
TABLE chunk (§2.5), rồi `_detect_header` / `_parse_data_rows` (§5.4) → vào
`material_prices`. Trước đây OCR chỉ ra text thuần, nên một phụ lục giá dạng
scan chỉ tìm kiếm được chứ **không đóng góp dòng giá nào**.

**Hai model phải khác nhà cung cấp.** Model được yêu cầu xuất bảng có thể bịa
một ô cho hàng "cân đối", và hỏi lại chính nó thì nó lặp lại đúng cái bịa đó.
Bất kỳ số tiền nào trong HTML mà **không xuất hiện** trong bản đọc độc lập sẽ
bị **làm trống ô** (`_verify`) — ô rỗng báo "không có dữ liệu", còn số bịa thì
thành một dự toán sai.

**Đo trên bản scan Vicem Hà Tiên** (bảng 19 cột, header 2 tầng, ô đơn vị gộp
suốt cột), chấm từng dòng so với trang in:

| model (lượt cấu trúc) | giá đúng | ghi chú | USD/trang |
|---|---:|---|---:|
| gemini-2.5-flash | **15/15** | — | 0,0068 |
| claude-opus-4.5 | 15/15 | không hơn được gì đo được | 0,0710 |
| gpt-4o | 14/15 | đọc `1.356.481` thành `1.436.481` — **giá sai** | 0,0293 |

Độ bắt số của lượt đối chiếu trên cùng trang: haiku-4.5 **16/16**, flash 16/16,
gpt-4o-mini 15/16. Model soi mà bỏ sót số thật sẽ **làm trống nhầm một giá
đúng**, nên 16/16 là ngưỡng. Cấu hình đang dùng: **flash** (cấu trúc) +
**haiku-4.5** (đối chiếu) ≈ **0,0145 USD/trang**.

**Ba việc lớp này phải tự làm vì OCR không có hình học:**

- `_normalise` — đệm hàng thiếu ô về bề rộng phổ biến, đệm **bên phải** để các
  cột đầu (STT, tên, đơn vị) không lệch.
- `_is_legend_row` nhận cả `[1] [2] [3]` — dạng có ngoặc. Không nhận thì dòng
  chỉ số cột thành một vật liệu tên `"[3]"` giá `12`, và tệ hơn là gieo đơn vị
  `"[4]"` cho mọi dòng sau nó.
- `_fill_table_wide_unit` — ô "Tấn" gộp suốt cột được model đặt **một lần ở
  giữa bảng**, 8 hàng trên nó không có gì để kế thừa. Chỉ áp cho **cột đơn
  vị**: cột "Ghi chú" / "Điều kiện thương mại" cũng có dạng "một giá trị,
  nhiều ô trống", nhưng ở đó ghi chú in cạnh một hàng chỉ thuộc hàng đó —
  điền vào là bịa dữ liệu, đúng thứ §2.6 tránh được nhờ hình học.

**Prompt phải nói rõ hai điều** mà model hay bỏ: ô gộp **theo cột** cũng phải
lặp giá trị, và header **nhiều tầng** phải giữ nguyên từng dòng. Thiếu vế sau,
model ép "Giá bán (chưa gồm VAT)" và 4 nhãn vùng con thành một dòng → mất hết
từ khoá giá → `_detect_header` trả `None` → 0 dòng giá.

**Kết quả trên tài liệu đó**: 0 chunk / 0 dòng giá → **13 chunk (6 bảng) / 38
dòng giá**, 0 ô bị làm trống.

**Giới hạn còn lại**: bảng có 4 cột giá song song (Hồ Chí Minh / Cần Giờ / Củ
Chi / Phú Hòa Đông) nhưng `_detect_header` chỉ map **một** `price_generic_col`
→ chỉ lấy cột đầu; dòng nào chỉ có giá ở vùng con khác sẽ bị bỏ.

---

## 3. Pipeline nạp thường (standard)

File: [app/core/ingestion/pipeline.py](../app/core/ingestion/pipeline.py). Là
async generator, phát event tiến độ (`parsing 0.1 → chunking 0.3 → embedding
0.3–0.8 → indexing 0.9 → done 1.0`):

1. Tạo record document (`status=processing`).
2. Chunk (dispatcher) → nếu 0 chunk và là PDF → **OCR fallback**.
3. Tách chunk quá khổ (§2.9).
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

Ngoài ra còn dò cột **tiêu chuẩn kỹ thuật** (`_SPEC_KEYWORDS` → `spec`) và **nhà
sản xuất** (`_MANUFACTURER_KEYWORDS` → `manufacturer`). Hai cột này hầu như luôn
là ô gộp trải cả họ sản phẩm nên chỉ đọc được **sau khi** §2.6 điền ô gộp; trước
đó hai trường trong `material_prices` luôn `NULL`.

### 5.4. Đọc dòng dữ liệu (`_parse_data_rows`)

Lưới đầu vào lấy từ `extract_tables_with_raw(page)` (§2.6) — **cả bản đã điền ô
gộp lẫn bản gốc**, vì mỗi bản trả lời một câu hỏi khác nhau.

- **Nhận diện hàng "group header"** (tên nhóm vật liệu như `"I | XI MĂNG | | |"`)
  → cập nhật `state.category` cho các dòng sau. Xét **trên lưới GỐC**: sau khi
  điền ô gộp, hàng này thừa hưởng đơn vị, tiêu chuẩn và cả **tên vật liệu** của
  họ phía trên, trông hệt một dòng dữ liệu bình thường → đọc nhầm sẽ đẻ ra một
  sản phẩm có giá **không tồn tại** trong tài liệu. Nhãn nhóm được lấy từ bất kỳ
  cột nào chứa nó — một số phụ lục đặt nó ở **cột TT**, không phải cột tên.
- **`-` và `-nt-` ở cột đơn vị** → resolve về đơn vị gần nhất (`is_unit_ditto`).
  Khối báo giá nhà cung cấp ghi đơn vị một lần rồi để `-` cho mọi dòng sau; lưu
  nguyên `unit='-'` khiến giá hiển thị thành `4.250.000 đ/-` và vô hiệu bộ lọc
  `unit` của `lookup_material_price` (§5.6). Ở KB hiện tại, **2.026/10.010 dòng**
  đang mang `unit='-'` do dữ liệu nạp bằng bản cũ.
- **Chặn nhãn nhóm tràn sang nhóm mới**: khi số thứ tự (STT) **về lại 1** mà chưa
  có hàng group-header nào cho nhóm đó → xoá `category`/`manufacturer` thay vì kế
  thừa của nhóm trước (`state.heading_unclaimed`). Trước khi có cơ chế này, 47
  mẫu đèn CDE VINA bị xếp vào nhóm `"Cáp vặn xoắn hạ thế"`, khiến
  `lookup_material_price(material_category="đèn led")` trả về rỗng.
- **`manufacturer` chỉ nhận giá trị trông như tên tổ chức** (`_looks_like_org`).
  Cột "NHÀ SẢN XUẤT/ GHI CHÚ" trộn tên công ty với địa chỉ, số điện thoại và ghi
  chú giao hàng ở các dòng bên dưới; chỉ dòng đầu là tên. Giá trị đang giữ được
  dùng tiếp cho các dòng sau cho tới khi gặp tên tổ chức mới.
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
header. Cơ chế: **giữ lại column-mapping và `_ParseState`** (nhóm vật liệu, đơn
vị, nhà sản xuất đang hiệu lực) từ trang cuối CÓ header; trang sau **không có
header nhưng cùng số cột** → coi là tiếp nối. Số cột khác → là bảng/section
khác, **không tái dùng** mapping (tránh đọc nhầm cột).

> **Đo trên 10 PDF nguồn** (`seed_data/prices/`), so bản trước và sau khi dùng
> chung `table_extract`: dòng giá trích được **10.010 → 10.748** (+738), cảnh báo
> **633 → 154** (−76%), tổng chunk **3.163 → 1.195** (−62%, do hết text trùng),
> số chunk bảng giữ nguyên 795.

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

## 5B. Từ PDF tới câu trả lời — luồng đầy đủ, kèm ví dụ

Mục này trả lời trọn vẹn hai câu hỏi hay bị đặt ra khi bảo vệ: **hệ thống bóc
giá từ PDF vào database bằng cách nào**, và **khi người dùng hỏi thì con số
được lấy ra bằng đường nào, tại sao không để RAG tự trả lời**.

### 5B.1. Vì sao không dùng RAG thuần cho con số giá

RAG trả lời bằng cách nhét vài đoạn văn bản gần nghĩa nhất vào prompt rồi để
model tự đọc. Với **văn xuôi** thì tốt. Với **một con số tiền** thì ba điểm
yếu sau là cố hữu, không phải do chỉnh tham số chưa khéo:

**1. Tương đồng ngữ nghĩa không phân biệt được sản phẩm gần giống nhau.**
"Xi măng PCB40" và "Xi măng PCB30" khác nhau đúng một ký tự và cách nhau
khoảng 200.000 đ/tấn. Vector của hai chuỗi đó gần như trùng nhau. Truy hồi
top-k không có cơ chế nào để nói "hai cái này khác nhau về giá".

**2. Con số và tên vật liệu có thể lệch hàng trong cùng một chunk.** Đây là
lỗi đã xảy ra thật trong hệ thống này. Chunk `01509092…` (phụ lục Hà Nội,
trang 275) có hàng **DN65** với ô giá **trống**, trong khi con số
`3.859.200` — giá của **DN50** ở trang trước — lại nằm trong `context_above`
của chính chunk đó. Model đọc chunk ấy rất dễ gán 3.859.200 cho DN65. §2.5
và §2.6 đã sửa nguyên nhân, nhưng rủi ro dạng này không bao giờ về 0 với
bảng dài, ô gộp, cắt trang.

**3. RAG không tổng hợp được.** "Giá xi măng thấp nhất ở Hà Nội là bao
nhiêu", "có bao nhiêu loại thép trong công bố quý này" — không có phép
`MIN()`, `COUNT()` nào trong tìm kiếm vector. Nó chỉ lấy về k đoạn rồi thôi.

Bằng chứng bằng số trên chính dữ liệu này (10.010 dòng giá):

| truy vấn | số dòng khớp | khoảng giá |
|---|---|---|
| `ILIKE '%xi măng%'` | 135 (HN 83, DN 52) | 1.400 → 4.766.000 |
| `ILIKE '%thép%'` | 512 | 3 → 210.000.000 |

Chênh 3.400 lần trong cùng một truy vấn, vì trộn đơn vị (`đ/tấn` với `đ/kg`)
và trộn mác/thương hiệu. Một câu "giá xi măng bao nhiêu" **không có một đáp
án duy nhất** — nó là 135 sản phẩm. RAG sẽ chọn đại một đoạn và trả lời như
thể đó là đáp án.

> **Nguyên tắc của hệ thống:** RAG lo phần **chữ** (điều kiện giá, phạm vi áp
> dụng, đã gồm VAT chưa, tiêu chuẩn kỹ thuật). SQL tất định lo phần **số**.
> Một match sai vật liệu → sai dự toán công trình, nên chỗ nào cần chính xác
> thì không giao cho tìm kiếm xấp xỉ.

### 5B.2. Nửa thứ nhất — PDF vào database (lúc nạp tài liệu)

```
người dùng bấm Upload trên trang KB
   │
   ├─ POST /api/v1/documents/upload/{kb_id}?region=HN&price_period=2026-06
   │     │
   │     └─ đọc knowledge_bases.price_extraction  ─── false ──→ pipeline thường
   │                     │                                       (chỉ chunk → Qdrant)
   │                   true
   │                     │  region rỗng?  ──→ 400, chặn ngay tại API
   │                     ▼
   ├─ RabbitMQ  {mode: "price_extraction", config: {region, price_period}}
   │
   └─ consumer → PriceExtractionPipeline.ingest_stream()
          │
          ├── NHÁNH A: chunk → embed → Qdrant          (phần chữ, cho RAG)
          │      §2.5–2.9; mỗi chunk gắn metadata {region, source_type, price_period}
          │
          └── NHÁNH B: extract_price_rows()             (phần số, cho SQL)
                 │
                 ├─ iter_price_tables(content, filename)   §5B.3
                 │     .pdf  → pdfplumber + giải ô gộp (§2.6)
                 │     .docx → python-docx
                 │     .md   → bảng markdown + dọn LaTeX
                 │
                 ├─ _detect_header()      → cột nào là tên / đơn vị / giá / tiêu chuẩn / NSX
                 ├─ _parse_data_rows()    → từng dòng thành MaterialPriceRow
                 └─ bulk_create()         → INSERT vào material_prices
                          │
                          └─ set_metadata(doc, {price_row_count, warning_count})
                                   └─→ UI hiện badge "27 dòng giá" / "0 dòng giá"
```

**Hai nhánh chạy trên cùng một file, độc lập nhau.** Một công văn không có
bảng giá vẫn ra 20 chunk RAG và 0 dòng giá — đó là kết quả đúng, không phải
lỗi nạp. Một phụ lục 699 trang ra 700 chunk bảng **và** 6.626 dòng giá.

### 5B.3. Bóc một dòng giá — ví dụ cụ thể

Nguồn: `HaNoi-PhuLuc-BangGiaVLXD-QuyII-2026.pdf`, trang 15.

**Bước 1 — lưới thô từ pdfplumber** (ô gộp chỉ có chữ ở dòng đầu):

```python
['1', 'Xi măng Bút Sơn PCB40', 'tấn', 'TCVN 6260:2020', 'Bút Sơn', '', '1.520.000']
['2', 'Xi măng Bút Sơn PCB30', '-',   '',                '-nt-',    '', '1.430.000']
```

**Bước 2 — sau `_resolve()`** (§2.6: ô gộp điền xuống theo hình học, `-nt-`
bung ra):

```python
['1', 'Xi măng Bút Sơn PCB40', 'tấn', 'TCVN 6260:2020', 'Bút Sơn', '', '1.520.000']
['2', 'Xi măng Bút Sơn PCB30', '-',   'TCVN 6260:2020', 'Bút Sơn', '', '1.430.000']
```

**Bước 3 — `_detect_header()` xác định cột:**

```
name_col=1  unit_col=2  spec_col=3  manufacturer_col=4  price_generic_col=6
```

**Bước 4 — `_parse_data_rows()` xử lý dòng 2:**

- `unit = '-'` → `is_unit_ditto()` → lấy đơn vị gần nhất → `'tấn'`
- `price = _parse_price('1.430.000')` → `1430000.0` (dấu `.` là phân cách nghìn)
- `manufacturer` giữ `'Bút Sơn'` (đã bung từ `-nt-`)

**Bước 5 — dòng nằm trong DB:**

```sql
INSERT INTO material_prices
  (region, material_category, material_name,          unit,  price_ex_vat,
   price_basis, source_type,      price_period, spec,             manufacturer, ...)
VALUES
  ('HN',   'Xi măng',         'Xi măng Bút Sơn PCB30','tấn', 1430000.00,
   'khong_ro',  'official_annex', '2026-06',    'TCVN 6260:2020', 'Bút Sơn', ...);
```

### 5B.4. Nửa thứ hai — từ câu hỏi tới con số

Ví dụ người dùng gõ, ở chế độ **Agentic**:

> **"Giá xi măng PCB40 ở Hà Nội bao nhiêu một tấn?"**

```
1. POST /api/v1/chat/stream
      body = { message: "...", mode: "agent", all_kbs: true, use_rag: true }

2. Guard chủ đề (sub-model rẻ) — đúng chủ đề VLXD → đi tiếp

3. _resolve_rag_scope(all_kbs=true)
      → [4 KB hệ thống + mọi KB người dùng]        (KB tạo 1 phút trước cũng có)

4. Truy hồi RAG trên toàn bộ KB đó
      → vài chunk văn bản: "giá công bố chưa gồm VAT", "áp dụng quý II/2026"…
      → nhét vào prompt dưới dạng Context

5. run_tool_loop()  — LLM nhìn thấy 2 công cụ:
      • lookup_material_price(region, material_category, material_name)
      • calculate_construction_cost(floor_area_m2, region, project_type, finish_level)

6. LLM tự quyết định gọi:
      lookup_material_price({region: "HN", material_name: "xi măng PCB40"})

7. handle_lookup_material_price → MaterialPriceRepository.lookup()
      SELECT * FROM material_prices
      WHERE region = 'HN'
        AND material_name ILIKE '%xi măng PCB40%'
      ORDER BY price_period DESC NULLS LAST, created_at DESC
      LIMIT 10;

8. Kết quả trả về cho LLM dưới dạng bảng markdown, role="tool":
      | Vật liệu | Đơn giá | Điều kiện giao | Kỳ | Nguồn |
      | Xi măng Bút Sơn PCB40 (TCVN 6260:2020) | **1.520.000 đ**/tấn | không rõ | 2026-06 |
        phụ lục công bố Sở Xây dựng — Bút Sơn |

9. LLM đọc kết quả tool + Context RAG rồi soạn câu trả lời cuối:
      "Xi măng Bút Sơn PCB40 ở Hà Nội quý II/2026: 1.520.000 đ/tấn (chưa VAT)…"

10. SSE trả về: sources = [chunk RAG…] + [tool_call_log…]
      → UI hiện badge "RAG · Toàn bộ kho tri thức" và chip nguồn
```

**Điểm mấu chốt ở bước 7:** không có tìm kiếm vector nào tham gia vào việc
lấy con số. `1.520.000` đi thẳng từ ô trong PDF → `material_prices` → `SELECT`
→ câu trả lời. Model **không tự sinh** con số đó, nó chỉ đọc lại và diễn giải.
Nếu không có dòng nào khớp, tool trả về nguyên văn *"Không tìm thấy giá cho
vùng=…, name=… — Không suy đoán giá"* và model buộc phải nói không có dữ
liệu, thay vì đoán.

### 5B.5. Khi nào KHÔNG dùng tool — RAG vẫn là đường đúng

| Câu hỏi | Đường xử lý | Vì sao |
|---|---|---|
| "Giá xi măng PCB40 ở HN?" | tool → SQL | cần con số chính xác |
| "Xây 100 m² ở HN hết bao nhiêu vật liệu?" | tool `calculate_construction_cost` → SQL nhiều lần | cần khối lượng × đơn giá |
| "PCB40 khác PCB30 chỗ nào?" | RAG | kiến thức, không phải số |
| "Tiêu chuẩn RoHS áp dụng cho vật liệu nào?" | RAG | quan hệ trong bảng, đọc từ chunk |
| "Giá công bố đã gồm VAT chưa?" | RAG | điều kiện áp dụng, nằm trong văn bản |

Chế độ **Agentic** chạy cả hai: truy hồi RAG trước, rồi để LLM tự quyết có
cần gọi tool hay không. Nhờ vậy một câu hỏi lai — *"xi măng PCB40 giá bao
nhiêu và nó khác PCB30 thế nào"* — được trả lời bằng con số từ DB **và** giải
thích từ tài liệu, trong cùng một lượt.

### 5B.6. Khớp tên vật liệu — vì sao `ILIKE` không đủ

Đây là chỗ nghẽn lớn nhất của đường tra giá, và đã được đo bằng một bộ 16 câu
tra thực tế ([eval_price_lookup.py](../scripts/eval_price_lookup.py)).

**Cách cũ** — một `material_name ILIKE '%<cả cụm>%'` — đòi các từ của người
dùng phải **liền nhau, đúng thứ tự**. Câu hỏi thật không như vậy:

```
người dùng gõ : "xi măng Bút Sơn PCB40"
tên trong DB   : "Xi măng bao Bút Sơn Xanh đa dụng PCB40"
                          ^^^         ^^^^^^^^^^^^
```
Cùng những từ đó, nhưng bị chen `bao` và `Xanh đa dụng` vào giữa → `ILIKE`
trả **0 dòng** trong khi dữ liệu nằm ngay đó. Gõ không dấu cũng 0 dòng.

**Cách mới** (migration `0009` + `MaterialPriceRepository.lookup`):

1. Tách câu tra thành **từng từ**, bỏ dấu, bỏ stopword (`giá`, `của`, `loại`…).
2. Ứng viên phải chứa **mọi từ** (`AND`, không phải `OR`) — nghiêm ngặt như cũ,
   nhưng cho phép từ khác chen vào giữa.
3. Xếp hạng phần còn lại bằng `similarity()` của `pg_trgm`.
4. Nếu **không dòng nào** chứa đủ mọi từ, **bỏ dần từ phổ biến nhất** rồi thử
   lại — vì tên trong DB cô đọng hơn câu hỏi (`"cáp điện CXV-150"` được lưu là
   `"CXV-150 - 0,6/1kV"`, `"xi măng Vicem Hà Tiên Xây tô"` là `"XM Vicem Hà
   Tiên Xây tô"`), nên các từ mô tả người dùng thêm vào đơn giản là không có
   trong tên.

| | CŨ | MỚI |
|---|---:|---:|
| tra đúng sản phẩm ở kết quả đầu | **5/16** | **15/16** |

Ca duy nhất còn trượt là `"ống nhựa uPVC"` — không có dòng uPVC nào ở Đà Nẵng,
tức trả 0 dòng là **đúng**.

#### Hai chốt an toàn, và vì sao chúng cần thiết

Cả hai đều ra đời sau khi phép đo bắt được lỗi thật, không phải phòng xa.

**Không bao giờ bỏ từ có chữ số.** Mã sản phẩm và kích thước (`D12`,
`CXV-150`, `PCB40`) **chính là danh tính** của vật liệu, nhưng tần suất không
nói lên điều đó: `d12` xuất hiện trong 49 dòng Hà Nội còn `nhat` chỉ 15. Xếp
theo tần suất thuần tuý thì `d12` bị bỏ trước, còn lại `[viet, nhat]`, và câu
`"thép Việt Nhật D12"` được trả lời bằng **một tấm vách kính** hiệu "kính Việt
Nhật".

**Không nới lỏng xuống dưới 2 từ.** Một từ không đủ làm danh tính:
`"xi măng Hoàng Thạch"` (loại xi măng không có trong bảng) nới xuống còn
`hoang` và trả về **trần nhôm Zinca Alu**. Dừng ở 2 từ khiến nó trả **0 dòng**
— đúng hợp đồng của công cụ này: *không tìm thấy* tốt hơn *sản phẩm sai*.

**Không dùng `word_similarity` làm cơ chế nới lỏng.** Đã thử và loại: với câu
hỏi về Hà Tiên, nó xếp `"Xi măng Vicem **Hạ Long** Xây tô"` (0,742) **trên**
`"XM Vicem **Hà Tiên** Xây tô"` (0,741) — sai thương hiệu, ở hạng nhất, kèm
điểm số trông rất tự tin. Giữ các từ hiếm làm **bộ lọc cứng** không thể mắc
lỗi đó: ứng viên vẫn buộc phải chứa từng từ một.

Ca đối kháng đã kiểm chứng: `"xi măng Vicem Hạ Long Xây tô"` → chỉ ra Hạ Long;
`"cáp điện CXV-240"` → chỉ ra CXV-240; `"xi măng Nghi Sơn PCB40"` (không có
trong bảng HN) → **0 dòng**, không lấy Bút Sơn ra thay.

### 5B.7. Giới hạn còn lại

- **Không có tổng hợp.** Chưa có min/max/trung vị theo đơn vị, nên "giá xi
  măng khoảng bao nhiêu" chưa trả lời gọn được.
- **`region` bắt buộc** trong schema tool, nên câu hỏi không nêu vùng sẽ bị
  model đoán vùng.
- **Không làm text2sql.** Schema chỉ có 1 bảng ~12 cột, không join: một tool
  có tham số kiểu bao phủ hết không gian truy vấn và **test được**, trong khi
  SQL do LLM sinh thì không, lại thêm bề mặt rủi ro trên cùng database chứa
  `users`/`messages`. Và như phép đo trên cho thấy, chỗ nghẽn thật là **chất
  lượng khớp tên** — thứ mà text2sql không hề chạm tới, vì LLM sinh SQL cũng
  sẽ viết ra đúng cái `ILIKE '%cả cụm%'` vừa được thay.

### 5B.8. Đã thử và BÁC BỎ: đổi văn bản đem embed của chunk bảng

Ghi lại ở đây vì kết quả âm cũng là kết quả, và để người sau khỏi thử lại.

**Giả thuyết**: chunk bảng đang được embed dưới dạng **HTML**, mà HTML vừa
nhiều nhiễu (`<td>` lặp hàng chục lần) vừa tách rời các cột — trong phụ lục Hà
Nội, ô tên đọc là `"Xi măng bao PCB40"` còn `"Bút Sơn"` nằm ở ô **nhà sản
xuất**, nên hai từ người dùng gõ bị 3 cột khác chen giữa. Nếu render mỗi hàng
thành câu `"Tên: …, Đơn vị: …, Nhà sản xuất: …"` thì hai từ đó về chung một
câu, vector sẽ khớp tốt hơn.

Đo trên **2.504 chunk thật** với 16 câu hỏi khó có đáp án khách quan (chunk
đúng = chunk chứa chuỗi mục tiêu) — [eval_table_embedding.py](../scripts/eval_table_embedding.py):

| văn bản đem embed | recall@1 | @3 | @5 | @10 | MRR |
|---|---:|---:|---:|---:|---:|
| **HTML (đang dùng)** | **5/16** | **8/16** | 9/16 | 10/16 | **0,433** |
| văn xuôi có nhãn cột | 4/16 | 7/16 | 9/16 | 10/16 | 0,386 |
| bỏ thẻ, không nhãn | 5/16 | 8/16 | 10/16 | 11/16 | 0,434 |

**Văn xuôi KÉM HƠN** (MRR −0,047), và còn dài hơn HTML **+10% token** khiến 17
chunk vượt trần 8.000 token (HTML: 0 chunk). Bỏ thẻ mà không thêm nhãn thì
ngang bằng (MRR +0,001) — nằm trong nhiễu của một bộ 16 câu.

Vì sao giả thuyết sai: phép đo ban đầu chỉ so **một hàng** dạng văn xuôi với
**cả chunk** dạng HTML (0,666 vs 0,576) — nó trộn lẫn hai thay đổi *cắt nhỏ*
và *đổi định dạng*. Khi giữ nguyên ranh giới chunk và chỉ đổi định dạng, lợi
ích biến mất.

Cũng đã đo việc **cắt nhỏ chunk bảng**: cắt 5 hàng/chunk chỉ nâng similarity
từ 0,576 lên 0,614, trong khi đối thủ gần nhất là 0,611 — thắng 0,003, quá
mong manh, mà số chunk tăng ~3 lần (chi phí embedding và lưu trữ tăng theo).
Cắt xuống 1 hàng cũng chỉ đạt 0,614, tức **trần của tìm kiếm vector cho câu
hỏi này là ~0,61 bất kể chia chunk thế nào**.

Kết luận: câu hỏi tra giá **không sửa được bằng cách chia hay định dạng
chunk**. Đường đúng là SQL tất định (§5B.6), và số liệu ủng hộ: cùng những
câu hỏi đó, khớp theo từ đưa tỉ lệ đúng từ 5/16 lên 15/16.

### 5B.9. Đã sửa: truy hồi RAG từng chặn công cụ

Ở chế độ Agentic, đoạn văn bản truy hồi được **gắn thẳng vào câu hỏi** dạng
`"Context: …\n\nQuestion: …"`. Có khối context lớn trước mặt, model trả lời từ
đó và **không bao giờ gọi công cụ**. Thí nghiệm đối chứng trên cùng một câu:

| | công cụ được gọi? |
|---|---|
| `use_rag=true` | **không** — 0 lần |
| `use_rag=false` | **có** — `lookup_material_price(...)` ngay lập tức |

Tức là truy hồi đang **vô hiệu hoá** chính đường tra chính xác mà nó lẽ ra bổ
trợ. Đã sửa: context chuyển sang một **system message riêng**, kèm chỉ dẫn nói
rõ tư liệu **không thay thế** công cụ và chỉ được kết luận "không có dữ liệu"
sau khi công cụ đã trả về không tìm thấy.

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

## 8B. Các loại hình xây dựng và công thức tính theo m²

File: [project_types.py](../app/core/construction/project_types.py)

### 8B.1. Mức chính xác của những con số này

Toàn bộ mục này thuộc mức **"ước lượng ý tưởng"** (mục 4.1 của cẩm nang
nghiệp vụ): dùng khi **chưa có bản vẽ**, chưa có bảng thống kê thép, chưa có
chỉ dẫn kỹ thuật. Nó **không thay** bóc tách khối lượng khi đã có hồ sơ thiết
kế, và **không phải** giá trọn gói — chỉ là chi phí **vật liệu chính**, chưa
gồm nhân công, thiết bị, lợi nhuận nhà thầu, VAT, chi phí gián tiếp.

Hệ số là số tròn có chủ đích. Ghi ba chữ số có nghĩa sẽ ngụ ý một độ chính
xác mà cấp độ ước lượng này không có. Tiêu hao thật thay đổi theo khẩu độ,
số tầng, địa chất, hệ kết cấu và yêu cầu kỹ thuật — một khung 5 tầng trên nền
đất yếu có thể vượt hệ số thép của hồ sơ nhà phố tới 50%.

### 8B.2. Công thức chung

Với mọi loại hình, mỗi vật liệu được tính như nhau:

```
khối lượng vật liệu i  =  A  ×  k_i  ×  f
chi phí vật liệu i     =  khối lượng vật liệu i  ×  đơn giá tra từ material_prices
tổng chi phí vật liệu  =  Σ chi phí vật liệu i
```

| ký hiệu | ý nghĩa |
|---|---|
| `A` | diện tích tham chiếu — **tuỳ loại hình**, xem cột "Đơn vị diện tích" ở 8B.3 |
| `k_i` | hệ số tiêu hao vật liệu `i` trên 1 đơn vị diện tích |
| `f` | hệ số hoàn thiện, **chỉ áp cho vật liệu hoàn thiện** (sơn, gạch lát) và chỉ ở loại hình có hoàn thiện |

`f` = 1,00 (thô) · 1,00 (hoàn thiện cơ bản) · 1,15 (hoàn thiện cao cấp).

> **Cẩn thận với `A`.** Nhà thì `A` là **diện tích sàn** (cộng mọi tầng). Sân,
> nhà xưởng, san nền thì `A` là **diện tích mặt bằng**. Tường rào thì `A` là
> **diện tích mặt tường** = dài × cao — tường rào dài 30 m cao 2 m thì nhập
> **60**, không phải 30.

### 8B.3. Bảng hệ số tiêu hao theo loại hình

Đơn vị của mỗi ô: lượng vật liệu trên **1 đơn vị diện tích tham chiếu**.

| Loại hình (`project_type`) | Đơn vị diện tích | Bê tông m³ | Thép kg | Thép hình kg | Tôn m² | Gạch xây viên | Xi măng kg | Cát m³ | Đá m³ | Cát san lấp m³ | Sơn lít | Gạch lát m² | Hoàn thiện? |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:--:|
| `nha_pho` — nhà phố/nhà ở khung BTCT | m² sàn | 0,35 | 25 | — | — | 55 | 60 | 0,20 | — | — | 0,44 | 0,85 | ✔ |
| `nha_cap_4` — nhà cấp 4, mái tôn/ngói | m² sàn | 0,18 | 12 | — | 1,15 | 60 | 55 | 0,18 | — | — | 0,40 | 0,90 | ✔ |
| `biet_thu` — biệt thự/nhà vườn | m² sàn | 0,40 | 30 | — | — | 65 | 75 | 0,25 | — | — | 0,60 | 1,00 | ✔ |
| `nha_xuong` — nhà xưởng thép tiền chế | m² mặt bằng | 0,22 | 8 | 35 | 1,45 | — | 20 | 0,10 | 0,12 | — | — | — | ✘ |
| `nha_kho` — nhà kho/kho bãi có mái | m² mặt bằng | 0,18 | 6 | 25 | 1,35 | — | 15 | 0,08 | 0,10 | — | — | — | ✘ |
| `san_be_tong` — sân/đường nội bộ/bãi xe | m² mặt bằng | 0,16 | 4,5 | — | — | — | — | — | 0,18 | 0,12 | — | — | ✘ |
| `san_nen` — san nền/tôn nền | m² mặt bằng | — | — | — | — | — | — | — | 0,05 | 0,55 | — | — | ✘ |
| `tuong_rao` — tường rào | **m² mặt tường** | 0,05 | 4 | — | — | 60 | 35 | 0,12 | — | — | 0,45 | — | ✔ |
| `via_he_lat_gach` — vỉa hè/sân lát gạch | m² mặt bằng | 0,08 | — | — | — | — | 25 | 0,10 | 0,08 | — | — | 1,05 | ✘ |
| `cai_tao` — cải tạo/sửa chữa | m² sàn cải tạo | — | — | — | — | 25 | 35 | 0,12 | — | — | 0,50 | 0,70 | ✔ |

Ghi chú từng loại hình:

- **`nha_pho`** — nhà 1–4 tầng, khung BTCT, tường xây gạch. Đây là hồ sơ mặc
  định và cũng là hồ sơ được hiệu chuẩn kỹ nhất.
- **`nha_cap_4`** — một tầng, không có sàn tầng trên nên bê tông và thép thấp
  hơn hẳn nhà phố; phần bao che chuyển sang tường xây và mái lợp. Hệ số tôn
  1,15 vì mái dốc có diện tích lớn hơn diện tích sàn.
- **`biet_thu`** — nhịp lớn hơn và nhiều chi tiết kiến trúc hơn nên tiêu hao
  cao hơn nhà phố khoảng 15–25%.
- **`nha_xuong`** — thép hình và tôn **chi phối giá thành**, gần như không
  dùng gạch xây hay sơn nước. Hệ số thay đổi mạnh theo khẩu độ và tải cầu
  trục — đây là loại hình có sai số lớn nhất.
- **`san_be_tong`** — áo cứng dày 12–18 cm trên lớp móng đá dăm. Thép chỉ là
  lưới chống nứt, không phải cốt thép chịu lực.
- **`san_nen`** — giả định chiều dày tôn nền trung bình ~50 cm. Chiều dày
  thật do cao độ thiết kế quyết định; đây là biến đổi mạnh nhất trong toàn
  bộ bảng.
- **`tuong_rao`** — bê tông và thép là phần móng và giằng, không phải khung.
- **`cai_tao`** — giả định **giữ nguyên khung kết cấu**: chỉ xây/đập tường
  ngăn, trát, lát, sơn lại. Vì vậy không có bê tông và cốt thép.

### 8B.4. Nhà ở: thô và hoàn thiện gồm những gì

Câu hỏi "xây thô cần gì, full hoàn thiện cần gì" hay gặp nhất, nên tách riêng.

**Phần thô (`finish_level = "tho"`)** — vật liệu tạo nên kết cấu và bao che:

| Hạng mục | Vật liệu | Hệ số (nhà phố) |
|---|---|---|
| Móng, cột, dầm, sàn | bê tông thương phẩm | 0,35 m³/m² sàn |
| Cốt thép | thép thanh/cuộn | 25 kg/m² sàn |
| Tường bao, tường ngăn | gạch xây | 55 viên/m² sàn |
| Vữa xây, vữa trát | xi măng + cát | 60 kg + 0,20 m³ /m² sàn |

**Hoàn thiện cơ bản (`hoan_thien_co_ban`)** — thêm lớp phủ bề mặt:

| Hạng mục | Vật liệu | Hệ số |
|---|---|---|
| Sơn tường trong + ngoài | sơn nước | 0,44 lít/m² sàn |
| Lát nền | gạch lát | 0,85 m²/m² sàn |

Cách ra 0,44 lít: diện tích sơn ≈ 2,2 m² trên mỗi m² sàn (tường hai mặt +
trần), sơn 2 nước, độ phủ ~10 m²/lít ⇒ `2,2 ÷ 10 × 2 = 0,44`.

**Hoàn thiện cao cấp (`hoan_thien_cao_cap`)** — cùng danh mục vật liệu, nhân
hệ số `f = 1,15` cho **sơn và gạch lát**. Kết cấu không đổi vì cấp hoàn thiện
không làm thay đổi khung.

> Những thứ **không** nằm trong ước lượng này: thiết bị vệ sinh, hệ điện
> nước, cửa, lan can, trần thạch cao, chống thấm, nhân công, máy thi công,
> lợi nhuận nhà thầu, VAT. Với nhà ở, các khoản đó thường lớn hơn phần vật
> liệu chính — nên con số tool đưa ra **không phải** "giá xây nhà".

### 8B.5. Ví dụ tính tay — đối chiếu với kết quả tool

Sân bê tông 200 m², vùng HN, giá lấy từ `material_prices` tại thời điểm chạy:

```
A = 200 m² mặt bằng, loại hình san_be_tong, f không áp dụng

Bê tông:      200 × 0,16  = 32,0 m³  × 1.320.000 đ/m³ =  42.240.000 đ
Thép (lưới):  200 × 4,5   = 900  kg  ×    15.620 đ/kg =  14.058.000 đ
Đá dăm:       200 × 0,18  = 36,0 m³  ×   500.000 đ/m³ =  18.000.000 đ
Cát san lấp:  200 × 0,12  = 24,0 m³  ×   210.000 đ/m³ =   5.040.000 đ
                                                        ─────────────
                                          TỔNG VẬT LIỆU = 79.338.000 đ
                                               ≈ 397.000 đ/m²
```

Kết quả tool chạy thật trùng khớp từng dòng — công thức trong tài liệu này
đúng là công thức đang chạy trong code, không phải mô tả gần đúng.

### 8B.6. Hai chốt an toàn trên đơn giá

**Biên giá hợp lý (`price_min` / `price_max`).** Mỗi vật liệu khai báo khoảng
đơn giá chấp nhận được. Ứng viên nằm ngoài khoảng bị loại, **từ cả DB lẫn
web**. Chốt này ra đời sau một sự cố thật: nguồn giá web trả về ~1,8 tỷ đ/kg
cho thép hình (một con số tổng dự án bị bóc nhầm thành đơn giá), nhân với
17.500 kg thành **31.500 tỷ đ** cho một hạng mục — sai sáu bậc độ lớn nhưng
in ra với vẻ chắc chắn y hệt các dòng khác. Biên đặt rộng có chủ đích: nó bắt
thảm hoạ về đơn vị/dấu thập phân, không phải để phán xét giá thị trường.

**Quy đổi đơn vị (`alt_units`).** Xi măng ở Hà Nội có 31 dòng theo `kg` và 27
dòng theo `tấn`. Không quy đổi thì một nửa dữ liệu vô hình và vật liệu báo
"không có giá". Tra theo đơn vị chính trước, không thấy thì tra đơn vị thay
thế rồi nhân hệ số (`tấn → kg` là `× 1/1000`).

Ngoài ra vẫn giữ cơ chế cũ: `exclude_keywords` lọc ngay ở tầng SQL, và một
sub-model chọn đúng dòng trong số ứng viên thật — model **không bao giờ tự
sinh giá**, nó chỉ chọn giữa các dòng có thật hoặc nói không dòng nào phù
hợp, và câu đó thành một dòng "không có dữ liệu" trung thực.

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
