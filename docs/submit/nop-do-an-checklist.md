# Nộp đồ án — những gì repo này thực sự cung cấp được

Đối chiếu trực tiếp với yêu cầu nộp bài đã dán, dựa trên rà soát thật trong repo (không suy đoán). Đánh dấu rõ **có sẵn**, **có nhưng cần bổ sung**, và **chưa có / không áp dụng**.

---

## a. Module phần mềm

**Có sẵn — cài đặt được từ đầu bằng tài liệu hướng dẫn:**

| Module | Vị trí | Cài đặt |
|---|---|---|
| Backend (FastAPI, RAG + tool-calling + MCP) | `app/` | `docker-compose.yml` service `app` |
| Frontend (Next.js chat UI) | `web/` | service `ui` |
| PostgreSQL (users, KB, `material_prices`...) | — | service `postgres` (image chính thức, không tự build) |
| Qdrant (vector DB) | — | service `qdrant` |
| RabbitMQ (hàng đợi nạp tài liệu) | — | service `rabbitmq` |
| STT GPU rời (tuỳ chọn) | `local-gpu-stt/` | chạy riêng, không nằm trong `docker-compose.yml` — xem `local-gpu-stt/README.md` |

Toàn bộ cài bằng: `bash scripts/setup.sh && docker compose up -d --build` — hướng dẫn đầy đủ ở [README.md](../../README.md) §7.

---

## b. Thư viện / framework / công cụ bên thứ 3

**Backend** (`pyproject.toml`) — nhóm chính: FastAPI, SQLAlchemy(async)+asyncpg+Alembic, qdrant-client, aio-pika, python-jose+bcrypt+authlib, openai SDK (dùng cho OpenRouter), langgraph+langchain, pymupdf+pdfplumber+python-docx (parse tài liệu), faster-whisper (STT), mcp (Model Context Protocol), prometheus-client+opentelemetry.

**Frontend** (`web/package.json`): next, react/react-dom, zustand, react-markdown+remark-gfm+remark-math+rehype-katex, katex.

**Dịch vụ bên thứ 3 (API ngoài, cần API key):** OpenRouter (LLM chat/embedding/vision), OpenAI (TTS trực tiếp — không qua OpenRouter), Firecrawl (web search cho deep research).

Danh sách đầy đủ, có ghi chú lý do chọn từng thư viện: `pyproject.toml`, `web/package.json`.

---

## c. File mô tả cấu hình / API bên thứ 3 / tài khoản đăng nhập

**Có sẵn, đầy đủ:**

- **`.env.example`** (126 dòng) — mọi biến cấu hình đều có comment giải thích: connection string Postgres/Qdrant/RabbitMQ, cổng API, toàn bộ API key bên thứ 3 cần điền (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `FIRECRAWL_API_KEY`, OAuth Google/GitHub), và các token bí mật (`SECRET_KEY`, `JWT_SECRET_KEY`). File này **chính là** "file văn bản mô tả cấu hình" mà đề yêu cầu — có thể nộp trực tiếp hoặc đổi tên/copy sang `docs/submit/`.
- **Tài khoản đăng nhập demo:** `demo@example.com` / `Demo1234!` (tạo qua `scripts/seed_demo_data.py`, xác nhận còn dùng được trong phiên làm việc này).

**Cần lưu ý khi nộp:**
- Hệ thống **không có phân quyền theo Role** (admin/user...) — chỉ có 1 loại tài khoản người dùng thường qua JWT/OAuth. Nếu đề yêu cầu liệt kê "tất cả các Roles", câu trả lời trung thực là: **không có hệ thống role, mọi tài khoản đăng nhập có quyền như nhau** (trừ 4 knowledge base hệ thống được bảo vệ không cho xoá, không phải phân quyền theo user).
- `.env` thật (chứa key thật của bạn) **không được nộp** — chỉ nộp `.env.example`. Nếu người chấm cần chạy demo thật, cần bạn tự điền `.env` từ key thật của mình, không phải mình cung cấp.

---

## c. Source code

Toàn bộ mã nguồn nằm trong chính repo Git này — `app/` (backend), `web/` (frontend), `local-gpu-stt/` (module STT GPU rời), `migrations/` (Alembic), `scripts/` (script vận hành/sửa dữ liệu). Nộp bằng cách nén toàn bộ repo (trừ các mục trong `.gitignore`: `__pycache__`, `node_modules`, `.venv`, build artifact) hoặc nộp link Git.

---

## d. File dữ liệu / hình ảnh / video

| Yêu cầu | Có sẵn? | Vị trí |
|---|---|---|
| Dữ liệu training mô hình AI | ⚠️ **Không có trong repo** | Fine-tune PhoWhisper (ASR) dùng bộ Vietnamese Multi-Dialect từ HuggingFace, không tải kèm — chỉ có **model đã huấn luyện xong** ở `local-gpu-stt/phowhisper-medium-lora-ct2/` và `phowhisper-medium-lora-merged/` (~4.4GB, là *kết quả* huấn luyện chứ không phải *dữ liệu* huấn luyện) |
| Dữ liệu/hình ảnh demo tính năng | ✅ Có | `seed_data/` — PDF giá vật liệu xây dựng thật (Hà Nội/Đà Nẵng/TP.HCM) + QCVN 16:2023, dùng để nạp vào 4 knowledge base demo |
| Hình ảnh kiến trúc hệ thống | ✅ Có | `docs/images/aaa.png` (đã cập nhật sang tiếng Anh) |
| Video demo | ⚠️ **Chưa có trong repo** | Cần bạn tự quay màn hình demo — mình không tạo được file video |
| Dữ liệu/sản phẩm sinh ra từ chạy phần mềm | ✅ Có | `results/` — 3 bộ kết quả benchmark thật (retrieval, representation, chunking) dạng CSV/JSON/MD, là *sản phẩm* của việc chạy các script đánh giá trong `scripts/` |

---

## Cần bạn xác nhận / tự bổ sung trước khi nộp

1. **Video demo** — chưa tồn tại, cần bạn tự quay.
2. **Dữ liệu training ASR gốc** — nếu đề yêu cầu bắt buộc phải có, cần bạn tải lại từ nguồn HuggingFace gốc (không có trong repo do dung lượng).
3. **README.md có vài link tài liệu bị gãy (`docs/getting-started.md`, `docs/construction-pricing-pipeline.md`, `docs/kien-truc-he-thong.md` cũ) — đã sửa lại trỏ đúng vào `docs/submit/kien-truc-chi-tiet.md` và `docs/instruction/*.md` trong phiên làm việc này.** Không có tài liệu "getting-started" độc lập nữa — README §7 (Quick start) đã đủ để cài từ đầu.
4. ⚠️ **Trong lúc rà soát để viết file này, phát hiện `seed_data/`, `docs/images/im1.png`, và 2 file trong `docs/submit/` bị xoá khỏi ổ đĩa lần nữa** (đã khôi phục bằng `git checkout`) — đây là lần thứ 3 trong phiên làm việc này hiện tượng này xảy ra, không do lệnh nào của mình. Nên kiểm tra xem có tiến trình/phiên nào khác đang chạy song song và xoá file trong thư mục này trước khi nộp, để tránh mất dữ liệu thật ở phút chót.
