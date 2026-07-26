# Getting Started — Clone, chạy Docker, và test

Hướng dẫn này dành cho người mới clone repo, muốn chạy toàn bộ hệ thống
(backend + frontend + Postgres/Qdrant/RabbitMQ) bằng Docker và kiểm tra các
tính năng chính hoạt động đúng.

---

## 1. Yêu cầu

- Docker + Docker Compose v24+
- `openssl` (để `scripts/setup.sh` sinh secret ngẫu nhiên)
- 1 API key OpenRouter ([openrouter.ai/keys](https://openrouter.ai/keys)) — bắt buộc, dùng cho chat, embedding, OCR fallback (file scan) và TTS
- Ổ đĩa trống ≥ 500MB cho `seed_data/` (kiến thức xây dựng + giá vật liệu 3 vùng HN/DN/HCM)
- (Tuỳ chọn) GPU NVIDIA nếu muốn chạy Whisper `medium`/`large` cho STT nhanh hơn — xem mục 8

---

## 2. Clone và cấu hình `.env`

```bash
git clone git@github.com:KhaiBoiPho/agentic-rag.git
cd agentic-rag
bash scripts/setup.sh
```

`setup.sh` tự copy `.env.example` → `.env` và sinh `SECRET_KEY`/`JWT_SECRET_KEY` ngẫu nhiên. Sau đó **mở `.env`, điền `OPENROUTER_API_KEY`** (bắt buộc — thiếu key này thì chat và toàn bộ việc ingest dữ liệu có sẵn sẽ không chạy được, xem mục 5).

Các model mặc định trong `.env.example`:
```
OPENROUTER_CHAT_MODEL=openai/gpt-4o-mini
OPENROUTER_EMBED_MODEL=openai/text-embedding-3-small
OPENROUTER_RESEARCH_MODEL=openai/gpt-4o-mini
OPENROUTER_TTS_MODEL=openai/gpt-audio-mini
OPENROUTER_VISION_MODEL=google/gemini-2.0-flash-exp:free
```
OpenRouter thỉnh thoảng gỡ/đổi tên model (kể cả model trả phí, không chỉ `:free`) — nếu chat/OCR/TTS báo lỗi "model does not exist" hoặc 404, kiểm danh sách model hiện có tại [openrouter.ai/models](https://openrouter.ai/models) và sửa lại `.env`, rồi `docker compose up -d --force-recreate --no-deps app` (đổi `.env` **không** tự áp dụng qua `restart` thường — xem mục 7 bảng sự cố).

---

## 3. Chạy toàn bộ hệ thống

```bash
docker compose up -d --build
```

Thứ tự khởi động: `postgres` → `migrate` (chạy `alembic upgrade head`, tạo schema + 2 KB hệ thống rỗng) → `qdrant`/`rabbitmq` → `app` → `ui`.

| Service | URL |
|---|---|
| UI (Next.js) | http://localhost:3210 |
| API docs (Swagger) | http://localhost:8000/docs |
| Qdrant dashboard | http://localhost:6333/dashboard |
| RabbitMQ management | http://localhost:15672 (guest/guest) |

Kiểm nhanh backend đã lên chưa:
```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

**Docker Desktop vs Docker Engine gốc**: nếu máy có cả hai (`docker context ls` thấy `desktop-linux` và `default`), Docker Desktop chạy engine riêng trong VM, **không có GPU passthrough** dù host đã cài `nvidia-container-toolkit` — nếu định dùng GPU cho Whisper (mục 8), phải `docker context use default` trước khi `docker compose up`.

**Muốn xem container/log trực quan** (thay vì gõ lệnh): cài [lazydocker](https://github.com/jesseduffield/lazydocker) (không cần sudo, 1 binary):
```bash
curl https://raw.githubusercontent.com/jesseduffield/lazydocker/master/scripts/install_update_linux.sh | bash
```

---

## 4. Log không hiện realtime?

Nếu `docker compose logs app` không in gì dù container đã chạy được vài chục giây (nhưng `curl localhost:8000/health` vẫn trả `ok` bình thường) — đây là do Python buffer stdout khi không gắn TTY. `docker-compose.yml`'s `app` service đã có sẵn `PYTHONUNBUFFERED: "1"` để tránh việc này; nếu bạn thấy lại hiện tượng này sau khi tự sửa compose file, kiểm tra biến đó còn tồn tại không.

---

## 5. Dữ liệu có sẵn (seed) — tự động, chạy ngầm

Ngay khi container `app` khởi động lần đầu, nó tự ingest **2 knowledge base hệ thống** từ `seed_data/` (đã commit sẵn trong repo, không cần upload tay):

| KB | Nội dung | Nguồn | Số file |
|---|---|---|---|
| **Kiến thức xây dựng** | Playbook đo bóc/ước lượng, QCVN 16:2023, sách vật liệu xây dựng | `seed_data/knowledge/` | 3 |
| **Dự toán giá nhà** | Công văn/phụ lục công bố giá + báo giá nhà cung cấp cho 3 vùng HN, Đà Nẵng, TPHCM | `seed_data/prices/{HN,DN,HCM}/` | 10 |

(Số file ít hơn phiên bản đầu — ~60 file báo giá scan của từng nhà cung cấp riêng lẻ ở TPHCM đã bị loại bỏ vì không đọc được text/OCR không đáng tin; chỉ giữ lại các công văn/phụ lục chính thức và báo giá đọc được rõ ràng, đặt tên lại dễ hiểu thay vì "PL1"/"Phụ lục 1".)

Đây là quá trình **chunk + embed qua OpenRouter + trích xuất giá vào Postgres** — mất vài phút (file lớn nhất, phụ lục Hà Nội 699 trang, riêng nó đã mất ~10 phút để embed), chạy nền không chặn app (`/health` trả 200 ngay). Theo dõi tiến độ:

```bash
docker compose exec postgres psql -U agentic -d agentic_rag \
  -c "select name, document_count from knowledge_bases where user_id='00000000-0000-0000-0000-000000000001';"
```

`document_count` của "Kiến thức xây dựng" dừng ở 3 và "Dự toán giá nhà" dừng ở 10 là đã xong. Chi tiết hơn theo từng file:

```bash
docker compose exec postgres psql -U agentic -d agentic_rag \
  -c "select filename, status, chunk_count from documents where kb_id in ('00000000-0000-0000-0000-000000000101','00000000-0000-0000-0000-000000000102') order by created_at;"
```

Nếu thiếu `OPENROUTER_API_KEY` hoặc key sai, bước này sẽ log lỗi (xem `docker compose logs app`) nhưng **không làm crash app** — sửa `.env` rồi `docker compose up -d --force-recreate --no-deps app` để seed lại (idempotent theo từng file — chỉ file chưa `status=done` mới bị ingest lại, xem `app/core/bootstrap/seed.py`).

2 KB này **không thể xoá/sửa/upload thêm** qua API (chặn cứng ở `app/api/v1/documents.py` và `app/api/v1/knowledge_base.py`, trả về `403`) — đảm bảo mọi lần deploy đều có cùng bộ kiến thức nền.

**Chuyển máy/deploy lại mà không muốn embed lại từ đầu**: xem [README.md §9](../README.md#9-moving-to-another-machine-without-re-embedding) — backup 2 volume Postgres/Qdrant và restore ở máy mới thay vì để seed chạy lại.

---

## 6. Test end-to-end

### 6.1. Tạo tài khoản + đăng nhập

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test12345!","full_name":"Test"}'
```
Lấy `access_token` trong response, hoặc đăng nhập trực tiếp trên UI tại http://localhost:3210.

### 6.2. Test RAG chat với KB kiến thức

Trên UI: chọn KB **"Kiến thức xây dựng"**, hỏi ví dụ *"Quy tắc không cộng trùng hao hụt là gì?"* — câu trả lời phải trích đúng nội dung, kèm citation chip trỏ vào `DataRAG-uoc-luong-gia-vlxd.md`.

### 6.3. Test human-in-the-loop form tính giá xây dựng

Gõ câu có chứa cả 3 nhóm từ khoá "nhà" + "xây/xây dựng" + "giá/chi phí/bao nhiêu tiền" (xem `app/core/chat/intent.py`), ví dụ:

> "giá xây nhà 100m2 ở Hà Nội"

→ Phải hiện **form** (không phải câu trả lời text) với diện tích/vùng đã điền sẵn — xác nhận **không có request nào tới OpenRouter** ở bước này (kiểm `docker compose logs app | grep -i openrouter` — không có dòng nào mới):

```bash
curl -s -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"giá xây nhà 100m2 ở Hà Nội"}'
# data: {"type": "form_request", ...}
```

Điền form và submit (hoặc test trực tiếp bằng `form_submission`):

```bash
curl -s -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"form_submission":{"form_id":"construction_cost","data":{"area_per_floor_m2":100,"num_floors":1,"region":"DN","finish_level":"hoan_thien_co_ban"}}}'
```

**Lưu ý về dữ liệu theo vùng**: bộ `seed_data/` hiện có độ chi tiết khác nhau theo vùng — Đà Nẵng có đủ giá cho cả 4 hạng mục (bê tông/thép/gạch/sơn) nên ra tổng chi phí; Hà Nội và TPHCM thiếu giá bê tông tươi/thép cây trong nguồn đã ingest nên trả về **"không đủ dữ liệu"** cho đúng hạng mục đó thay vì đoán số — đây là hành vi đúng (mục 56 của playbook: không đưa 1 số khi thiếu dữ liệu), không phải lỗi.

### 6.4. Test tool-calling tự do (`mode="agent"`)

```bash
curl -s -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"Tra giá đá xây dựng ở TPHCM giúp tôi","mode":"agent"}'
```
LLM phải tự gọi tool `lookup_material_price` (xem trong `sources` của response là `tool_call_log`, không phải citation chunk).

### 6.5. Test upload tay 1 file mới (KB do user tự tạo)

```bash
curl -X POST http://localhost:8000/api/v1/kb \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"My KB"}'
# lấy id -> upload file
curl -X POST "http://localhost:8000/api/v1/documents/upload/<kb_id>" \
  -H "Authorization: Bearer $TOKEN" -F "file=@/path/to/file.pdf"
```

### 6.6. Test voice (Speak → nghe trả lời)

Trên UI, bấm nút **Speak** (mic) trong composer, nói, bấm dừng — hệ thống tự gửi transcript vào chat, chờ trả lời, rồi tự phát giọng đọc kèm chỉ báo "🔊 Speaking…" cạnh nút mic. Lưu ý: giọng đọc **không đảm bảo khớp nguyên văn** với chữ hiển thị (xem README §2.3) — đây là giới hạn của model audio OpenRouter đang dùng, không phải lỗi.

---

## 7. Sự cố thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| UI báo lỗi 500 khi gọi `/api/v1/...` qua `localhost:3210` | Container `ui` build từ code cũ (Next.js image không tự reload như `app`) | `docker compose up -d --build ui` |
| Login/API trả `Internal Server Error` không phải JSON | `app` container chưa khởi động xong (mới restart) | Đợi vài giây, kiểm `docker compose logs app | tail -20` thấy `Application startup complete` |
| Chat/OCR/TTS báo lỗi model không tồn tại (404) | Model trong `.env` đã bị OpenRouter gỡ hoặc đổi tên | Đổi `OPENROUTER_*_MODEL` trong `.env` sang model còn tồn tại (kiểm tại openrouter.ai/models), `docker compose up -d --force-recreate --no-deps app` (`.env` không tự áp dụng qua `restart` thường) |
| Câu hỏi giá xây nhà không hiện form | Câu hỏi thiếu 1 trong 3 nhóm từ khoá "nhà"/"xây"/"giá,chi phí,bao nhiêu tiền" | Xem `app/core/chat/intent.py::_INTENT_WORD_GROUPS`, hoặc diễn đạt lại câu hỏi |
| `calculate_construction_cost` báo "không đủ dữ liệu" cho 1 hạng mục | Vùng đó thật sự thiếu giá đúng loại/đơn vị trong `seed_data/` đã ingest (không phải bug — xem mục 7.3) | Nếu có file giá thật cho hạng mục/vùng đó, thêm vào `seed_data/prices/<region>/` rồi xoá dòng document cũ + để seed chạy lại, hoặc upload tay qua `/documents/upload-price/{kb_id}` vào 1 KB không phải hệ thống |
| Whisper GPU không load (`could not select device driver "nvidia"`) | Đang chạy Docker Desktop (VM engine), không phải Docker Engine gốc | `docker context use default` trước khi `docker compose up` — xem README §8 |
| Log `docker compose logs app` không hiện gì dù app chạy bình thường | Thiếu `PYTHONUNBUFFERED=1` (Python buffer stdout khi không có TTY) | Đã có sẵn trong `docker-compose.yml`; nếu vẫn gặp, kiểm biến này còn tồn tại trong service `app` không |

---

## 8. GPU cho Whisper (tuỳ chọn)

Xem chi tiết tại [README.md §8](../README.md#8-gpu-optional--local-whisper-stt) — tóm tắt: CPU dùng được ngay, không cần cấu hình gì; muốn dùng GPU cho model `medium`/`large` thì cần `nvidia-container-toolkit` trên host + chạy đúng Docker Engine gốc (không phải Docker Desktop VM) + đổi 3 biến `WHISPER_*` trong `.env`.

---

## 9. Tài liệu liên quan

- [docs/construction-pricing-pipeline.md](construction-pricing-pipeline.md) — chi tiết pipeline chunking/embedding/price-extraction/tool-calling/human-in-loop form.
- [README.md](../README.md) — kiến trúc tổng quan, tech stack, luồng hệ thống, Makefile, API reference.
