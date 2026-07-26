# Kiến trúc hệ thống Agentic RAG — Tài liệu chi tiết

Tài liệu này giải thích **toàn bộ hệ thống hoạt động thế nào**, ở mức chi tiết đủ để một
người mới hoàn toàn có thể hiểu và tiếp tục phát triển. Với các phần đã có tài liệu riêng
sâu hơn, có link tới file tương ứng.

> Tài liệu ngắn gọn hơn, hướng "chạy nhanh": [README.md](../README.md).
> Hướng dẫn cài đặt từ đầu: [getting-started.md](getting-started.md).
> Chi tiết riêng pipeline giá vật liệu: [construction-pricing-pipeline.md](construction-pricing-pipeline.md).

---

## Mục lục

1. [Hệ thống này làm gì, cho ai](#1-hệ-thống-này-làm-gì-cho-ai)
2. [Sơ đồ kiến trúc tổng thể](#2-sơ-đồ-kiến-trúc-tổng-thể)
3. [Tech stack và tác dụng từng công nghệ](#3-tech-stack-và-tác-dụng-từng-công-nghệ)
4. [Cơ sở dữ liệu Postgres](#4-cơ-sở-dữ-liệu-postgres)
5. [Vector DB — Qdrant](#5-vector-db--qdrant)
6. [Luồng chat đầy đủ, từng bước](#6-luồng-chat-đầy-đủ-từng-bước)
7. [Small talk — bỏ qua LLM để tiết kiệm chi phí](#7-small-talk--bỏ-qua-llm-để-tiết-kiệm-chi-phí)
8. [Validate câu hỏi người dùng — off-topic guard](#8-validate-câu-hỏi-người-dùng--off-topic-guard)
9. [Luồng tool-calling (agent mode) — dự toán chi phí xây dựng](#9-luồng-tool-calling-agent-mode--dự-toán-chi-phí-xây-dựng)
10. [Luồng ingest tài liệu](#10-luồng-ingest-tài-liệu)
11. [Luồng giọng nói (voice)](#11-luồng-giọng-nói-voice)
12. [Frontend — các màn hình](#12-frontend--các-màn-hình)
13. [Xác thực (Auth)](#13-xác-thực-auth)
14. [Giám sát (Monitoring)](#14-giám-sát-monitoring)
15. [Quy trình triển khai (Deployment)](#15-quy-trình-triển-khai-deployment)
16. [Những điểm chưa hoàn hảo, biết trước](#16-những-điểm-chưa-hoàn-hảo-biết-trước)

---

## 1. Hệ thống này làm gì, cho ai

Đây là **trợ lý AI chuyên về vật liệu xây dựng và dự toán chi phí xây nhà tại Việt Nam**.
Người dùng chat bằng tiếng Việt, có thể:

- Hỏi kiến thức xây dựng chung (quy chuẩn QCVN, cách đo bóc khối lượng...)
- Tra giá vật liệu cụ thể theo vùng (Hà Nội / Đà Nẵng / TPHCM)
- Yêu cầu dự toán chi phí xây nhà (nhập diện tích, số tầng, vùng, mức hoàn thiện → ra bảng giá)
- Tìm kiếm/nghiên cứu thông tin trên web (khi câu hỏi cần dữ liệu mới hơn KB nội bộ)
- Nói chuyện bằng giọng nói (ghi âm → chuyển văn bản → trả lời → đọc lại bằng giọng nói)
- Quản lý tài liệu riêng (tạo Cơ sở tri thức riêng, gộp nhiều KB vào 1 Dự án)

Hệ thống có sẵn **2 cơ sở tri thức hệ thống** (seed từ lúc deploy, chỉ đọc, không xoá/sửa được):
"Kiến thức xây dựng" (playbook đo bóc, QCVN) và "Dự toán giá nhà" (giá công bố Sở Xây dựng +
báo giá nhà cung cấp cho 3 vùng).

---

## 2. Sơ đồ kiến trúc tổng thể

```
┌─────────────┐      REST + SSE       ┌──────────────────────────────────────┐
│  Frontend   │ ───────────────────▶  │              Backend (app)           │
│  Next.js 16 │ ◀───────────────────  │              FastAPI                 │
│  (port 3210)│    /api/v1/*          │              (port 8000)             │
└─────────────┘                       └───┬─────────┬─────────┬─────────────┘
                                           │         │         │
                    ┌──────────────────────┘         │         └───────────────┐
                    ▼                                ▼                        ▼
            ┌───────────────┐              ┌──────────────────┐    ┌────────────────────┐
            │  PostgreSQL   │              │      Qdrant       │    │      RabbitMQ       │
            │  (dữ liệu có  │              │  (vector search    │    │  (hàng đợi ingest    │
            │   cấu trúc)   │              │   cho RAG)         │    │   tài liệu người dùng│
            └───────────────┘              └──────────────────┘    │   upload, KHÔNG dùng  │
                                                                    │   cho seed hệ thống)  │
                                                                    └────────────────────┘
                    │
                    ▼ (ngoài hệ thống, qua HTTP)
            ┌───────────────────────────────┐
            │  OpenRouter (LLM chat, embed,  │
            │  vision OCR)                   │
            │  OpenAI trực tiếp (TTS thật)   │
            │  Firecrawl (web search)        │
            └───────────────────────────────┘

STT (giọng nói → text): chạy NGOÀI backend, trên máy có GPU riêng
(local-gpu-stt/server.py) hoặc RunPod Serverless, gọi qua HTTP tunnel (ngrok).
```

Backend là **monolithic** (1 process FastAPI duy nhất, không tách microservice) — đơn giản
hoá vận hành, phù hợp quy mô hiện tại. Không còn dùng gRPC (đã gỡ bỏ — xem §16).

---

## 3. Tech stack và tác dụng từng công nghệ

| Công nghệ | Vai trò | Tại sao chọn |
|---|---|---|
| **FastAPI** | Web framework backend, REST + SSE | Async native, tích hợp Pydantic validation, tự sinh OpenAPI docs |
| **SSE (Server-Sent Events)** | Stream từng token câu trả lời về frontend | Đơn giản hơn WebSocket cho luồng 1 chiều server→client, browser hỗ trợ sẵn qua `fetch()` |
| **PostgreSQL 16 + SQLAlchemy (async) + Alembic** | Lưu dữ liệu có cấu trúc: user, KB, hội thoại, giá vật liệu... | ACID, quan hệ rõ ràng giữa user/KB/document; Alembic quản lý version schema |
| **Qdrant** | Vector database cho RAG | Named-vector collection, filter theo metadata (kb_id, region...), API đơn giản qua Python client |
| **RabbitMQ (aio-pika)** | Hàng đợi xử lý upload tài liệu của người dùng (async) | Upload file có thể mất vài phút (PDF lớn) — không giữ HTTP request chờ, xử lý nền |
| **OpenRouter** | Cổng trung gian gọi nhiều LLM (chat, embedding, OCR ảnh) chỉ với 1 API key | Đổi model cho từng tác vụ chỉ bằng sửa `.env`, không sửa code |
| **OpenAI API (trực tiếp, không qua OpenRouter)** | TTS thật (`/v1/audio/speech`) | OpenRouter không có endpoint TTS thật — chỉ có model chat đa phương thức dễ "trả lời lại" thay vì đọc nguyên văn (xem §11) |
| **faster-whisper (CTranslate2)** | STT (giọng nói → văn bản), tự host | Không phụ thuộc API ngoài trả phí theo phút; chạy CPU hoặc GPU |
| **PhoWhisper (VinAI)** | Bản fine-tune tiếng Việt của Whisper, dùng qua faster-whisper | Chính xác hơn hẳn Whisper gốc cho tiếng Việt (theo benchmark WER chính thức) |
| **LangGraph** | Orchestrator cho luồng Deep Research (mở rộng câu hỏi → tìm web → tổng hợp → kiểm tra chất lượng → trả lời) | Đây là quy trình nhiều bước tuần tự có trạng thái — phù hợp graph hơn vòng lặp tool-calling đơn giản |
| **MCP (Model Context Protocol) `Tool` schema** | Định nghĩa chuẩn cho 3 tool: tra giá, tính khối lượng, tính chi phí | Chuẩn hoá schema tool để LLM gọi qua tool-calling, tái dùng được ở nhiều nơi |
| **Next.js 16 (App Router) + React 19** | Frontend | Server-side rewrite proxy `/api/*` → backend (giấu domain thật, gộp cùng origin), React Server/Client Component |
| **Zustand** | State management phía frontend (danh sách KB/Dự án, cài đặt model) | Nhẹ hơn Redux, đủ dùng cho state không quá phức tạp |
| **Tailwind CSS** | Styling | Utility-first, nhanh cho việc build UI nhất quán |
| **JWT (access + refresh) + OAuth2** | Xác thực | Access token ngắn hạn (15 phút) + refresh dài hạn (7 ngày), OAuth Google/GitHub tuỳ chọn |
| **Prometheus + Grafana** | Giám sát (tuỳ chọn, profile riêng) | Theo dõi latency/request count theo thời gian thực |
| **Firecrawl** | Web search cho chế độ Search/Research | API scrape nội dung web sạch hơn tự parse HTML |
| **ngrok** | Tunnel máy GPU cá nhân ra internet cho STT | Cách nhanh nhất expose 1 server local mà không cần domain/SSL riêng |

---

## 4. Cơ sở dữ liệu Postgres

13 bảng, chia theo nhóm chức năng:

### Người dùng & xác thực
- **`users`** — tài khoản (gồm 1 user hệ thống cố định `SYSTEM_USER_ID` sở hữu 2 KB hệ thống)
- **`refresh_tokens`** — refresh token JWT còn hiệu lực, để logout/revoke được

### Tri thức & tài liệu
- **`knowledge_bases`** — mỗi KB có `is_system` (true = 2 KB hệ thống, chỉ đọc) và `document_count`
- **`documents`** — file đã upload vào 1 KB, `status`: `pending → processing → done/error`
- **`material_prices`** — **dữ liệu giá có cấu trúc**, trích xuất từ PDF giá vật liệu. Đây là bảng
  quan trọng nhất cho tính năng dự toán — mỗi dòng là 1 vật liệu cụ thể (tên, đơn giá, đơn vị,
  vùng, kỳ công bố, nguồn). Tool `lookup_material_price`/`calculate_construction_cost` **query
  trực tiếp SQL vào bảng này** (ILIKE + filter unit), **không phải semantic/vector search** —
  vì sai vật liệu ở đây → sai cả con số chi phí đưa ra, nên bắt buộc exact-match hoặc báo
  "không tìm thấy" thay vì đoán bừa.

### Dự án & ghi chú
- **`projects`** — gộp nhiều KB để RAG tìm cùng lúc trên tất cả
- **`project_kbs`** — bảng nối nhiều-nhiều `projects` ↔ `knowledge_bases`
- **`notes`** — sổ tay cá nhân, độc lập hoàn toàn với chat

### Hội thoại & lịch sử
- **`conversations`** — 1 dòng / cuộc hội thoại, `conversation_id` do frontend sinh UUID
- **`messages`** — từng tin nhắn (`role`: user/assistant, `content`, `sources` nếu có RAG citation).
  **Đây chính là bộ nhớ ngữ cảnh** — mỗi lượt chat mới, backend lấy 10 tin gần nhất từ bảng này
  làm history đưa vào prompt, không cần frontend gửi lại toàn bộ lịch sử.
- **`research_records`** — kết quả các phiên Deep Research đã chạy

### Vận hành
- **`usage_records`** — mỗi lượt chat ghi lại: model dùng, số token prompt/completion, chi phí
  ước tính (theo bảng giá tĩnh, không phải số thật OpenRouter trả về), thời gian xử lý — phục vụ
  trang "Sử dụng" trên UI
- **`alembic_version`** — Alembic tự quản lý, đánh dấu migration hiện tại đã áp dụng

---

## 5. Vector DB — Qdrant

**1 collection duy nhất**: `agentic_rag_chunks`.

### Payload của mỗi point (chunk)

```json
{
  "document_id": "...",
  "kb_id": "...",
  "filename": "PhuLuc.pdf",
  "chunk_type": "table" | "text",
  "content": "<nội dung chunk — bảng HTML nếu là table>",
  "context_above": "...",     // đoạn text ngay trước, KHÔNG hiển thị khi cite
  "context_below": "...",     // đoạn text ngay sau, KHÔNG hiển thị khi cite
  "full_content": "context_above + content + context_below",  // cái THỰC SỰ được embed
  "page_num": 468,
  "token_count": 651,
  "metadata": { "region": "HN", "source_type": "official_annex", "price_period": "" }
}
```

Vì sao tách `content` khỏi `full_content`: chunk là 1 bảng đứng riêng lẻ dễ mất ngữ cảnh
(không biết STT/nhóm vật liệu ở dòng trước) — nên **embed cả đoạn trước/sau** để tìm kiếm chính
xác hơn, nhưng khi hiển thị citation cho người dùng chỉ show `content` (gọn, không lặp lại
đoạn context của chunk lân cận).

### Cách tìm kiếm hiện tại

Code hiện **chỉ tìm dense vector** (`query_points(..., using="dense", ...)`), dù collection
được tạo sẵn `sparse_vectors_config` cho BM25 và docstring module ghi "hybrid search (dense +
sparse BM25)". Sparse vector đã cấu hình nhưng **chưa thực sự được dùng trong truy vấn** — đây
là 1 khoảng cách giữa tài liệu/ý định ban đầu và code thật, xem thêm §16.

Filter khi tìm: theo `kb_id` (1 hoặc nhiều, khi chat theo Project), có thể filter thêm theo
`metadata.region`/`metadata.source_type` để giới hạn phạm vi (vd chỉ tìm giá HN).

---

## 6. Luồng chat đầy đủ, từng bước

Endpoint duy nhất: `POST /api/v1/chat/stream` (SSE). Request luôn gồm `conversation_id`
(UUID sinh ở frontend), `kb_id`/`project_id` (nếu có scope RAG), `mode` (frontend luôn gửi
`"agent"`), `form_submission` (khi submit form dự toán).

Thứ tự xử lý trong `app/api/v1/chat.py::stream_chat()`, **dừng lại ở bước đầu tiên khớp**:

```
1. form_submission có giá trị?
   → bỏ qua mọi bước dưới, chạy thẳng tool tính chi phí (§9), không detect gì thêm

2. detect_small_talk(message)  — §7
   → khớp (chào/tạm biệt/cảm ơn/hỏi thăm/hỏi danh tính bot...)?
   → trả lời cứng (canned), KHÔNG gọi LLM, lưu lịch sử, return

3. detect_intent(message)  — app/core/chat/intent.py
   → khớp từ khoá "nhà" + "xây..." + "giá/chi phí..."?
   → trả về SSE event `form_request` (frontend render form nhập diện tích/vùng/mức hoàn thiện)
   → LLM CHƯA được gọi ở bước này — chỉ khi user điền form xong, quay lại bước 1

4. Off-topic guard  — §8 (chỉ chạy khi KHÔNG có kb_id/project_id/skill_id — persona mặc định)
   → gọi model rẻ (gpt-4o-mini) phân loại: câu hỏi có khả năng liên quan xây dựng/kỹ thuật/
     khoa học công nghệ không?
   → nếu KHÔNG (vd hỏi về bóng đá, người nổi tiếng) → trả lời từ chối lịch sự, KHÔNG gọi model
     chính, lưu lịch sử, return

5. mode == "agent" (luôn đúng vì frontend luôn gửi agent)
   → lấy 10 tin nhắn gần nhất từ DB làm history
   → build messages = [system_prompt, ...history, tin nhắn hiện tại]
   → run_tool_loop() — LLM có quyền tự quyết định gọi 1 trong 3 tool (§9) hay trả lời thẳng
   → stream từng token về frontend qua SSE
   → lưu user message + assistant reply vào `messages`, ghi `usage_records`
```

**Điểm quan trọng đã sửa gần đây**: trước đây nhánh `mode=="agent"` KHÔNG lấy history và
KHÔNG lưu lịch sử — nghĩa là mọi câu hỏi tiếp nối kiểu "còn ở HCM thì sao?" sau câu hỏi Hà Nội
trước đó sẽ bị "mất trí nhớ" hoàn toàn, LLM không biết "như vậy" là gì. Đã fix để nhánh agent
dùng chung cơ chế history/persist với nhánh RAG thường.

**Badge hiển thị trên UI** (ưu tiên theo thứ tự): RAG (có citation tài liệu thật) → Web
(Search/Research) → Chat thường. Nếu KB đang active nhưng câu trả lời không có citation nào
(off-topic trong phạm vi KB đó), badge hạ về "Chat thường" — không gắn nhãn RAG sai.

---

## 7. Small talk — bỏ qua LLM để tiết kiệm chi phí

File: `app/core/chat/intent.py::detect_small_talk()`.

**Nguyên tắc**: match **CHÍNH XÁC toàn bộ câu** (sau khi chuẩn hoá bỏ dấu câu, viết thường),
không phải substring — để tránh chặn nhầm câu hỏi thật có lẫn từ chào (vd "Chào bạn, giá thép
hôm nay bao nhiêu" **không** bị coi là small talk, vì cả câu không khớp nguyên văn bất kỳ cụm
nào trong danh sách). Có giới hạn độ dài (`_SMALL_TALK_MAX_LEN = 40` ký tự) làm lớp bảo vệ thứ 2.

5 nhóm hiện có (dựa theo bộ intent chitchat chuẩn của Rasa, điều chỉnh cho domain):

| Nhóm | Ví dụ câu | Phản hồi |
|---|---|---|
| `greeting` | "chào", "hi", "hello" | Chào lại + gợi ý hỏi về xây dựng |
| `farewell` | "tạm biệt", "bye" | Chào tạm biệt |
| `thanks` | "cảm ơn", "thank you" | Đáp lại lời cảm ơn |
| `how_are_you` | "bạn khỏe không" | Trả lời thăm hỏi + gợi ý hỏi tiếp |
| `bot_identity` | "bạn là ai", "bạn tên gì" | Giới thiệu bản thân là trợ lý xây dựng |
| `bot_capability` | "bạn làm được gì" | Liệt kê khả năng: tra giá, kiến thức, dự toán |
| `apology` | "xin lỗi", "sorry" | Trấn an, không sao |

**Cố tình KHÔNG có** nhóm affirm/deny ("ok", "không") hay khen ngợi — vì các câu này thường là
**câu trả lời cho lượt trước** của assistant (vd assistant hỏi "bạn có muốn dự toán không?",
user đáp "không") — nếu match cứng sẽ cắt ngang mạch hội thoại thật bằng 1 câu trả lời chung
chung sai ngữ cảnh.

Kết quả đo thực tế: small talk phản hồi trong **~0.14 giây, 0 lệnh gọi LLM** — so với ~5-7 giây
và ít nhất 1 lệnh gọi LLM cho câu hỏi thường.

---

## 8. Validate câu hỏi người dùng — off-topic guard

File: `app/core/chat/topic_guard.py`.

**Mục đích**: chặn câu hỏi hoàn toàn ngoài domain (thể thao, người nổi tiếng, giải trí...)
**trước khi** chúng chạm tới model chính (có thể là model đắt tiền người dùng tự chọn ở Settings)
— dùng 1 model rẻ cố định (`openai/gpt-4o-mini`, **độc lập với model người dùng chọn**) để
phân loại trước.

**Chỉ chạy khi đang ở persona mặc định** — tức không có `kb_id`/`project_id`/`skill_id` nào
active. Lý do: nếu người dùng đã chọn 1 KB/Dự án riêng (có thể chứa nội dung hoàn toàn khác,
vd tài liệu về message queue, database...), "liên quan" phải hiểu theo nội dung KB đó, không
phải theo domain xây dựng cứng — nên guard này tắt hẳn trong trường hợp đó.

**Prompt phân loại cố tình nới lỏng** (sau khi test thực tế thấy quá chặt): chỉ trả lời NO khi
chủ đề **hoàn toàn không có khả năng liên quan** tới xây dựng/kỹ thuật/khoa học công nghệ. Câu
hỏi khoa học/công nghệ chung chung (vd "công nghệ nano là gì") **được cho qua** — vì kỹ sư xây
dựng hoàn toàn có thể quan tâm tới các chủ đề đó, dù không trực tiếp về vật liệu xây dựng.

Ví dụ đã verify thực tế:
- "Công nghệ nano là gì" → **qua**, trả lời đầy đủ
- "Messi sinh năm bao nhiêu" / "Cristiano Ronaldo là ai" → **chặn**, từ chối lịch sự trong ~1 giây

**Fail-open**: nếu lệnh gọi classifier lỗi/timeout, mặc định coi là "on-topic" và cho qua bình
thường — một lỗi hạ tầng không liên quan không được phép chặn câu hỏi hợp lệ của người dùng.

---

## 9. Luồng tool-calling (agent mode) — dự toán chi phí xây dựng

3 tool định nghĩa theo chuẩn MCP `Tool` schema (`app/core/mcp/tools/`), LLM tự quyết định gọi
tool nào qua `run_tool_loop()` (`app/core/llm/tool_loop.py` — vòng lặp gọi model → nếu có
tool_calls thì thực thi → gọi lại model với kết quả tool → trả lời cuối):

### `estimate_material_quantity`
Công thức đo bóc khối lượng **thuần Python, không LLM** (`app/core/construction/formulas.py`)
— lấy thẳng từ các chương trong playbook phương pháp luận (bê tông §16, cốt thép §17, xây tường
§19, trát §20, ốp lát §21, sơn §22).

### `lookup_material_price`
Query SQL trực tiếp vào bảng `material_prices` (`region=... AND material_name ILIKE ... AND
unit ILIKE ...`) — **không phải semantic search**. Trả "không tìm thấy" thay vì đoán nếu sai.

### `calculate_construction_cost` — tool chính cho luồng dự toán
1. Tính khối lượng cần cho 4 hạng mục (bê tông, thép, gạch, sơn) từ diện tích/số tầng qua công
   thức Python
2. Với mỗi hạng mục, tra giá song song (`asyncio.gather`) qua `lookup_material_price`
3. **Bước LLM disambiguation**: khi 1 truy vấn trả về nhiều ứng viên (vd tìm "thép" ra cả thép
   thanh vằn lẫn ống thép/thép mạ kẽm), dùng 1 lệnh gọi LLM nhỏ để **chọn đúng 1 dòng khớp mô tả**
   — LLM không tự bịa giá, chỉ chọn index trong danh sách thật hoặc trả lời "không dòng nào phù
   hợp" (map thành "thiếu dữ liệu", không phải đoán số)
4. Nếu không tìm thấy trong DB → fallback tìm giá qua web (Firecrawl), gắn cờ "giá tham khảo từ
   web, chưa xác thực" + trích dẫn nguồn `[n]`
5. Trả kết quả có 2 loại citation trộn lẫn được: chip RAG (`document_name` + score, từ DB) và
   trích dẫn web `[n]` (có link) — badge UI ưu tiên RAG nếu có ít nhất 1 giá từ DB thật

**Lỗi từng gặp và đã fix**: hàm tra giá lấy tối đa 15 ứng viên **sắp theo thời gian công bố mới
nhất**, không sắp theo độ liên quan — với truy vấn chung chung như "thép" (75+ dòng khớp ở 1
vùng), toàn bộ top-15 có thể bị các biến thể cần loại trừ (ống thép, thép mạ kẽm...) chiếm hết,
đẩy dòng đúng (thép thanh vằn/thép cuộn) ra ngoài tầm nhìn của LLM disambiguation — LLM đúng khi
nói "không dòng nào phù hợp" vì nó chưa từng thấy dòng đúng. Đã fix bằng cách filter loại trừ
ngay ở tầng SQL (`exclude_name_keywords`) trước khi cắt giới hạn 15 dòng.

**2 chế độ song song**:
- **Fixed pipeline** (`detect_intent` → `form_request`, không LLM) cho ý định biết trước, độ
  rủi ro cao (đảm bảo tham số đúng thay vì tin LLM tự parse từ câu tự do)
- **`mode="agent"`** (tự do) cho câu hỏi mở — LLM tự quyết có cần gọi tool không

---

## 10. Luồng ingest tài liệu

2 pipeline dùng chung phần chunk/embed, khác nhau ở bước cuối:

```
PDF/DOCX/TXT
  │
  ├─ ChunkDispatcher.chunk() — PyMuPDF (text theo thứ tự đọc) + pdfplumber (bảng → HTML)
  │
  ├─ 0 chunk? (PDF scan/ảnh, không có text layer)
  │   → OCR fallback: render từng trang thành ảnh, gọi model vision qua OpenRouter
  │     để transcribe, chunk lại text vừa transcribe — chỉ kích hoạt khi extract thường
  │     ra 0 kết quả, tránh gọi vision cho mọi trang của mọi PDF
  │
  ├─ split_oversized_table_chunk() — 1 bảng giá dài (vd phụ lục 699 trang) có thể vượt
  │   giới hạn cứng 8192 token của model embedding — cắt theo nhóm dòng, lặp lại dòng
  │   header ở mỗi mảnh để không mất ngữ cảnh cột
  │
  ├─ OpenRouterClient.embed() — text-embedding-3-small, 1536 chiều, theo batch
  │
  ├─► QdrantStore.upsert_chunks() — batch 200 điểm/request (PDF lớn dễ WriteTimeout
  │     nếu upsert 1 lần)
  │
  └─► [CHỈ pipeline giá] extract_price_rows() → MaterialPriceRepository.bulk_create()
        → bảng material_prices (Postgres) — song song với việc chunk vào Qdrant ở trên,
          không thay thế nhau: Qdrant giữ phần văn bản pháp lý/ngữ cảnh (điều kiện áp dụng
          giá), Postgres giữ số liệu giá chính xác dùng để tính toán
```

**2 điểm vào, cùng pipeline**:
- **User upload** (`POST /documents/upload/{kb_id}` hoặc `/upload-price/{kb_id}`) → đẩy job vào
  RabbitMQ → `app/queue/consumer.py` xử lý nền
- **Seed hệ thống** (`app/core/bootstrap/seed.py`, chạy nền lúc `on_startup`) → gọi thẳng pipeline,
  **bỏ qua RabbitMQ** (job 1 lần lúc khởi động, không cần vòng qua consumer). Idempotent theo
  **từng file** (không phải theo cả KB) — nếu container restart giữa chừng lúc đang ingest 1 file
  lớn, lần sau chỉ ingest lại đúng file dở dang, không ingest lại từ đầu cả KB.

---

## 11. Luồng giọng nói (voice)

### STT (giọng nói → văn bản)

3 lựa chọn qua `STT_BACKEND`, code dùng chung interface `transcribe(audio_bytes, language)`:

| Backend | Chạy ở đâu | Khi nào dùng |
|---|---|---|
| `local` | Trong process backend, CPU hoặc GPU | Backend tự có GPU, hoặc chấp nhận CPU chậm cho model nhỏ |
| `http` | Máy GPU riêng (`local-gpu-stt/server.py`) + tunnel ngrok | Backend deploy trên host không GPU (vd Railway) — **đang dùng thực tế** |
| ~~`runpod`~~ | RunPod Serverless | Đã thử, bỏ vì cold-start quá chậm (worker GPU khởi động ~vài phút) |

Model đang dùng: **PhoWhisper large** (fine-tune tiếng Việt của VinAI, convert sang CTranslate2)
— chọn qua thực tế test (medium vẫn sai nhiều hơn chấp nhận được, dù benchmark giấy tờ cho thấy
medium/large gần như ngang nhau).

### TTS (văn bản → giọng nói)

Gọi **thẳng OpenAI** `/v1/audio/speech` (model `tts-1`), **không qua OpenRouter** — vì OpenRouter
không có endpoint TTS thật, trước đây dùng tạm model chat đa phương thức (`gpt-audio-mini` qua
`/chat/completions`) nhưng phát hiện nó có thể **tự "trả lời lại" thay vì đọc nguyên văn** (vì
bản chất vẫn là model hội thoại, không phải TTS thuần) — đã thay hẳn bằng API TTS thật, đảm bảo
đọc đúng 100% văn bản được yêu cầu, cần `OPENAI_API_KEY` riêng.

### Luồng đầy đủ

```
Bấm mic → ghi âm (MediaRecorder, webm) → thả ra
  → POST /voice/stt → text
  → tự động gửi text đó như 1 tin nhắn chat bình thường (đi qua toàn bộ luồng §6)
  → LLM trả lời (stream hiển thị text như bình thường)
  → LẤY ĐÚNG đoạn text đã stream (không gọi LLM lần 2) → POST /voice/tts/stream
  → phát audio, khoá toàn bộ composer (không gõ/gửi được) tới khi phát xong hẳn
```

Composer bị khoá suốt: ghi âm → transcribe → chat trả lời → **phát giọng nói xong hẳn** — tránh
việc người dùng gõ tin nhắn mới chen ngang khi lượt voice trước chưa kết thúc.

Cả text người dùng nói (sau STT) và text AI trả lời (trước khi TTS đọc) đều được lưu vào bảng
`messages` **y hệt tin nhắn gõ tay** — không có cờ `via_voice` nào gửi lên backend, nên không có
sự khác biệt nào ở tầng lưu trữ/ngữ cảnh giữa 2 cách nhập liệu.

---

## 12. Frontend — các màn hình

Sidebar có 6 mục: **Trò chuyện**, **Ghi chú**, **Dự án**, **Cơ sở tri thức**, **Sử dụng**, **Cài đặt**.

- **Trò chuyện** — màn hình chính. Composer có 3 chế độ (Chat/Search/Research), nút mic, chọn
  phạm vi RAG (KB/Dự án) ở sidebar. Badge RAG/Web/Chat thường hiển thị trên mỗi câu trả lời.
- **Ghi chú** — sổ tay CRUD đơn giản, không liên quan chat
- **Dự án** — tạo dự án, gán nhiều KB vào 1 dự án để RAG tìm cùng lúc
- **Cơ sở tri thức** — danh sách KB (2 hệ thống + KB tự tạo), xem chi tiết tài liệu từng KB, upload
  (KB hệ thống không cho upload/xoá), theo dõi trạng thái ingest realtime (poll khi còn
  `pending`/`processing`)
- **Sử dụng** — thẻ thống kê tổng chi phí/token, biểu đồ chi phí theo ngày, bảng lịch sử từng lượt gọi model
- **Cài đặt** — chọn model (3 tier Budget/Standard/Premium), temperature, max tokens — áp dụng
  cho tin nhắn mới

Kiến trúc: Next.js server-side `rewrites()` proxy `/api/*` → backend, giữ nguyên header
`Authorization`, **không nén/buffer response SSE** (bắt buộc, nếu không token sẽ dồn cục về cuối
thay vì stream mượt).

---

## 13. Xác thực (Auth)

JWT access token (15 phút) + refresh token (7 ngày). Frontend tự động gọi `/auth/refresh` khi
gặp `401`, retry request gốc. OAuth2 Google/GitHub tuỳ chọn (cần cấu hình client id/secret).

---

## 14. Giám sát (Monitoring)

Prometheus + Grafana, chạy qua profile riêng (`docker compose --profile monitoring up -d`),
không bật mặc định. Theo dõi: số request HTTP theo endpoint/status code, độ trễ, số token
LLM, thời gian ingest tài liệu, độ sâu hàng đợi RabbitMQ.

---

## 15. Quy trình triển khai (Deployment)

**Local**: `docker compose up -d --build` — 5 service (`postgres`, `qdrant`, `rabbitmq`, `app`,
`ui`) + `migrate` (chạy 1 lần rồi thoát). Xem [getting-started.md](getting-started.md).

**Production (Railway)**: mỗi service tách riêng (không dùng chung `docker-compose.yml` như
local) — backend + frontend là 2 service GitHub riêng, Postgres dùng plugin quản lý sẵn, Qdrant/
RabbitMQ tự deploy bằng Docker image (hoặc dùng bản Cloud managed để đơn giản hơn). STT chạy
ngoài Railway hoàn toàn (máy GPU riêng + ngrok), vì Railway không có GPU. Chi tiết đầy đủ:
[railway-deploy.md](railway-deploy.md).

---

## 16. Những điểm chưa hoàn hảo, biết trước

Ghi lại minh bạch để không ai tưởng nhầm là bug chưa phát hiện:

- **Qdrant "hybrid search" chỉ mới là dense-only.** Collection đã cấu hình sẵn sparse vector
  (BM25) và docstring module ghi "hybrid (dense + sparse)", nhưng hàm `search()` hiện chỉ query
  `using="dense"` — sparse vector tồn tại nhưng chưa được dùng để fusion kết quả. Muốn hybrid
  thật cần thêm `Prefetch` + fusion query (RRF) kết hợp cả 2.
- **gRPC đã bị gỡ bỏ hoàn toàn** (từng có ý định dùng cho "non-browser client" trong tương lai,
  nhưng không có consumer thực tế nào, và các servicer gRPC đã lạc hậu hẳn so với REST — thiếu
  agent mode, history, off-topic guard, small talk). Nếu sau này cần hỗ trợ client không phải
  trình duyệt, cần xây lại từ đầu.
- **Chi phí trong trang Sử dụng là ước tính**, không phải số OpenRouter trả về thật (họ không trả
  billing info qua luồng SSE) — tính theo bảng giá tĩnh per-model.
- **STT qua tunnel ngrok free không ổn định lâu dài** — URL đổi mỗi lần restart ngrok, phải cập
  nhật lại `STT_HTTP_URL` trên backend mỗi lần. Cần ngrok trả phí (static domain) hoặc 1 máy GPU
  luôn bật + domain cố định mới ổn định cho production thật sự.
- **Dữ liệu giá không đồng đều theo vùng** — Đà Nẵng có đủ giá cho 4 hạng mục chính; Hà Nội/TPHCM
  thiếu 1 số hạng mục trong nguồn đã ingest, dẫn tới nhiều câu trả lời phải fallback web hoặc báo
  "thiếu dữ liệu" — đây là giới hạn dữ liệu nguồn, không phải lỗi code.
