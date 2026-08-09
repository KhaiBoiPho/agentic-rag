# Báo cáo đối chiếu `docs/submit/kien-truc-chi-tiet.md` với codebase

**Ngày kiểm tra:** 2026-08-09 · **Nhánh:** `feature/test` · **Commit:** `fb1ddd0`
**Phạm vi:** 2.520 dòng tài liệu vs. toàn bộ `app/`, `migrations/`, `scripts/`,
`tests/`, `pyproject.toml`, `docker-compose.yml`, `.env`.

> **Cập nhật cùng ngày:** toàn bộ 13 mục đề xuất ở §4 đã được áp dụng — 3 thay
> đổi code (`.env` → `gemini-2.5-flash`, xoá mã chết `_PER_M2_COEFFICIENTS` ở
> `cost_tool.py`, mount MCP server tại `/mcp` trong `main.py`) và các mục còn
> lại sửa trực tiếp trong `docs/submit/kien-truc-chi-tiet.md`. Nội dung bên
> dưới giữ nguyên như lúc kiểm tra ban đầu, làm hồ sơ đối chiếu — xem khung
> "✅ ĐÃ SỬA" cuối mỗi mục §3 để biết bản vá tương ứng.

---

## 1. Tổng quan

Đây là một tài liệu kiến trúc **chất lượng cao bất thường**. Phần lớn các khẳng
định kỹ thuật — kể cả những con số rất cụ thể như hệ số tiêu hao từng loại công
trình, hằng số BM25, thứ tự các bước trong luồng chat — đều **khớp chính xác**
với mã nguồn. Đặc biệt §4.2 (hybrid retrieval), §8B.3 (bảng hệ số 10 loại hình)
và §6 (thứ tự luồng chat) khớp tới từng giá trị.

Các sai lệch phát hiện được **không nằm ở phần lõi mới viết**, mà tập trung ở
**những mục cũ chưa được cập nhật theo các đợt refactor sau đó**. Nói cách khác:
tài liệu đúng ở chỗ nó vừa được viết, và lệch ở chỗ nó bị bỏ quên.

| Đánh giá | Tỉ lệ | Số mục |
|---|---:|---:|
| ✅ **Đúng** — khớp hoàn toàn với code | **~82%** | ~101 |
| ⚠️ **Sai / không khớp** | **~9%** | 11 |
| ❌ **Thiếu** — có thật trong code, không có trong tài liệu | **~5%** | 6 |
| ❓ **Không kiểm chứng được** — số đo từ script đã bị gỡ | **~4%** | 5 |

> **Lưu ý về nhóm ❓:** tài liệu **đã tự khai báo** điều này ở §2.3B ("đã bị gỡ
> khỏi cây mã… không chạy lại được từ trạng thái repo hiện tại"). Đây là cách
> xử lý trung thực, không tính là lỗi.

**Một vấn đề nghiêm trọng duy nhất** (P0): model production thực tế đang chạy
**không phải** model tài liệu khẳng định. Xem §3.1.

---

## 2. Bảng đối chiếu chi tiết

### 2.1. §0 — Bản đồ công nghệ

| Khẳng định trong tài liệu | KQ | Minh chứng |
|---|:--:|---|
| FastAPI + Uvicorn | ✅ | `pyproject.toml` — `fastapi>=0.115.0`, `uvicorn[standard]>=0.32.0` |
| PostgreSQL (SQLAlchemy async + asyncpg) | ✅ | `sqlalchemy[asyncio]>=2.0.36`, `asyncpg>=0.30.0` |
| Qdrant dense + sparse BM25 | ✅ | `app/db/qdrant/client.py:42-43` `DENSE_VECTOR`/`SPARSE_VECTOR` |
| RabbitMQ (aio-pika) | ✅ | `aio-pika>=9.4.0`; `app/queue/publisher.py:12` |
| OpenRouter (OpenAI-compatible SDK) | ✅ | `openai>=1.55.0`; `app/core/llm/openrouter.py` |
| PhoWhisper (faster-whisper/CTranslate2) | ✅ | `faster-whisper>=1.0.0`; `app/core/voice/phowhisper.py` |
| TTS = OpenAI `/v1/audio/speech` trực tiếp | ✅ | `app/config.py:116-117` |
| Deep Research = LangGraph | ✅ | `langgraph>=0.2.50`; `app/core/research/graph.py:44-59` |
| Firecrawl | ✅ | `firecrawl-py>=1.4.0` |
| Prometheus middleware | ✅ | `app/monitoring/metrics.py:55` mount `/metrics` |
| tiktoken `cl100k_base` | ✅ | `tiktoken>=0.8.0`; `app/core/chunking/base.py` |
| **"Không có NVIDIA NIM trong runtime"** | ✅ | `grep -ri "nvidia\|nim" app/*.py` → **0 kết quả**. Tham chiếu duy nhất ở `scripts/setup.sh:51-56`, đúng như tài liệu mô tả (dọn dẹp, không sử dụng) |
| Chat model `google/gemini-2.5-flash` | ⚠️ | Mặc định code đúng (`app/config.py:74`) nhưng **`.env` đang ghi đè** → xem §3.1 |
| Embed `openai/text-embedding-3-small`, dim 1536 | ✅ | `app/config.py:75`, `:155` |
| Classifier `openai/gpt-4o-mini` | ✅ | `app/config.py:84` |
| Vision table `google/gemini-2.5-flash` | ✅ | `app/config.py:108` |
| Vision đối chiếu `anthropic/claude-haiku-4.5` | ✅ | `app/config.py:107` |

### 2.2. §1 — Upload → Queue → Ingest

| Khẳng định | KQ | Minh chứng |
|---|:--:|---|
| `POST /upload/{kb_id}` trả `202` | ✅ | `app/api/v1/documents.py:38` `status_code=202` |
| Query params `region`, `price_period`, 4 tham số chunk override | ✅ | `documents.py:43-51` |
| Đường phụ `POST /upload-price/{kb_id}` | ✅ | `documents.py:156` |
| Tối đa 50 MB | ✅ | `documents.py:15` `MAX_FILE_MB = 50` |
| Đọc cả 2 cờ KB, dựng `ChunkProfile`, serialize vào payload | ✅ | `documents.py:57+` `_kb_ingest_settings()` → `profile.with_overrides()` |
| Queue `ingest_jobs`, `durable=True`, `PERSISTENT`, base64 | ✅ | `app/queue/publisher.py:12,29,36,40` |
| `prefetch_count=4`, `message.process(requeue=True)` | ✅ | `app/queue/consumer.py:25,30` |
| `documents.status` tại **`models.py:101`** | ⚠️ | Thực tế **`models.py:120`** — tham chiếu dòng đã lệch |

### 2.3. §2 — Chunking

| Khẳng định | KQ | Minh chứng |
|---|:--:|---|
| `chunk_token_num=512`, `overlap=15%`, `table_context_size=128` | ✅ | `app/config.py:148-150` |
| `MAX_EMBED_TOKENS = 8000` | ✅ | `app/core/chunking/base.py:22` |
| `MAX_TABLE_CHUNK_TOKENS = 3000` | ✅ | `base.py:53` |
| `embed_batch_size=32`, `embed_dim=1536` | ✅ | `app/config.py:154-155` |
| **§2.3B — profile `STANDARD`** 512/15/128/3000 | ✅ | `profiles.py:107-113` — khớp từng trường |
| **§2.3B — profile `TABLE_HEAVY`** 512/15/**0**/**1500** | ✅ | `profiles.py:118-124` — khớp từng trường |
| `profile_from_config()` fallback về `STANDARD` | ✅ | `profiles.py:141` |
| "Profile KHÔNG bao gồm model trả lời", có test chốt | ✅ | `tests/test_chunk_profiles.py:143` `test_a_profile_carries_no_model_setting`, `:151` `test_turning_it_on_does_not_change_the_chat_model` |
| §2.5 `_in_any_bbox`, `_table_to_html`, `naive_merge_with_origins` | ✅ | `pdf_chunker.py:264,197`; `base.py:201` |
| §2.6 `extract_tables_resolved` / `extract_tables_with_raw` | ✅ | `table_extract.py:67,76` |
| §2.6 `_resolve()`, `_recover_hole()`, `is_unit_ditto()` | ✅ | `table_extract.py:142,123,63` |
| §2.6 hai test khoá ranh giới lưới khuyết | ✅ | `tests/test_chunking.py:147,158` — đúng tên tài liệu nêu |
| §2.7 `_resolve_header`, `_looks_like_header`, `_HEADER_LABELS` | ✅ | `pdf_chunker.py:364,276,45` |
| §2.9 `split_oversized_table_chunk` | ✅ | `base.py:70` |
| §2.12 OCR render 200 DPI, hai lượt, `_verify` làm trống ô | ✅ | `ocr_fallback.py:48` `_RENDER_DPI = 200`, `:131` `_verify`, `:225-227` |
| §2.12 `_normalise` | ✅ | `ocr_fallback.py:117` |
| §2.12 `_is_legend_row`, `_fill_table_wide_unit` **thuộc lớp OCR** | ⚠️ | Hai hàm này nằm ở **`price_extractor.py:197,402`**, không phải `ocr_fallback.py` |

### 2.4. §4 — Embedding & Qdrant (mục chính xác nhất tài liệu)

| Khẳng định | KQ | Minh chứng |
|---|:--:|---|
| Payload 11 khoá + `metadata` lồng | ✅ | `client.py:127-139` — khớp từng khoá |
| Dense COSINE size=`embed_dim`, sparse có `Modifier.IDF` | ✅ | `client.py:57,105-116` |
| Upsert `batch_size=200` | ✅ | `client.py:122` |
| Prefetch **limit=50** mỗi nhánh | ✅ | `client.py:49` `PREFETCH_LIMIT = 50` |
| Fusion RRF | ✅ | `client.py:298,308` `FusionQuery(fusion=Fusion.RRF)` |
| `score_threshold=0.5` **chỉ gác nhánh dense** | ✅ | `client.py:258` (dense có), `:260-265` (sparse không có) |
| `HYBRID_REQUIRE_DENSE_SUPPORT` mặc định `true` | ✅ | `app/config.py:178` |
| Cơ chế: dense probe `limit=1` chạy song song, rỗng → trả `[]` | ✅ | `client.py:285-303` |
| Bộ lọc `must` áp cho **cả hai** nhánh | ✅ | `client.py:253-265` — cùng `query_filter` |
| Region = `should=[region==X, IsEmpty(region)]` | ✅ | `client.py:226-233` |
| Không có query text → dense-only | ✅ | `client.py:241-251` |
| BM25 `k1=1.5`, `b=0.75` | ✅ | `sparse.py:54-55` |
| Chia đôi Okapi: TF-saturation lúc index, IDF ở Qdrant | ✅ | `sparse.py:104-121` (index), `:124-134` (query values = 1.0) |
| Tokenizer `cxv-150` → `['cxv','150','cxv150']` | ✅ | `sparse.py:65-89` |
| `tests/test_sparse.py` so từng chuỗi với benchmark | ✅ | File tồn tại |
| `BM25_AVG_DOC_LEN` mặc định 600 (ước lượng) | ✅ | `app/config.py:173` + comment thừa nhận là ước lượng |
| §4.3 `delete_kb`: kiểm quyền → Qdrant → Postgres | ✅ | `knowledge_base.py:130-141` — **đúng thứ tự tài liệu mô tả** |
| §4.3 bảng "DELETE /kb → ✔ delete_by_kb" | ✅ | `client.py:322`; `knowledge_base.py:138` |
| §4.3 `test_deletion_integration.py` search lại đòi rỗng | ✅ | 13 test, gồm `test_no_orphan_survives_anywhere_in_the_collection` |
| §4.4 `scripts/backfill_sparse_vectors.py` | ✅ | File tồn tại |

### 2.5. §5 / §5B — Pipeline giá

| Khẳng định | KQ | Minh chứng |
|---|:--:|---|
| `classify_source_file` → 3 loại | ✅ | `price_extractor.py:31` |
| `_detect_header` dò 6 hàng đầu, các nhóm keyword | ✅ | `price_extractor.py:209,232-239` |
| `_NAME/_UNIT/_CATEGORY/_SPEC/_MANUFACTURER_KEYWORDS` | ✅ | `price_extractor.py:50,60,61,66,67` |
| Bỏ qua hàng chú thích chỉ số cột (`_is_legend_row`) | ✅ | `price_extractor.py:268` |
| `_parse_data_rows`, `state.heading_unclaimed`, `_looks_like_org` | ✅ | `price_extractor.py:437,399,380` |
| `iter_price_tables` — pdf/docx/md, dọn LaTeX | ✅ | `price_tables.py:42,57,70,121,132` |
| `MaterialPrice` các cột nêu ở §5.6 | ✅ | `app/db/postgres/models.py:183-222` |
| `cascade="all, delete-orphan"` trên `document.material_prices` | ✅ | `models.py:137` |
| §5B.6 khớp **từng từ**, bỏ dấu, `AND` | ✅ | `material_price_repo.py:118-145` |
| §5B.6 **không bao giờ bỏ từ có chữ số** | ✅ | `material_price_repo.py:371` `pinned = [w for w in words if any(c.isdigit()...)]` |
| §5B.6 **không nới xuống dưới 2 từ** | ✅ | `material_price_repo.py:404` `if len(kept) < 2: break` |
| §5B.6 loại `word_similarity`, dùng `similarity()` xếp hạng | ✅ | `material_price_repo.py:319,330` + comment `:357-362` |
| §5B.4 `_AMBIGUOUS_SPREAD` = 25% | ✅ | `app/core/pricing/service.py:236` |
| §6.4B 5 trạng thái `PriceStatus` | ✅ | `service.py:42-47` |
| §6.4B alias resolver tất định, `canonicalize_material_name` | ✅ | `service.py:197` |
| **`_infer_mapping_from_data`** — fallback thứ 3 khi cả header lẫn mượn đều thất bại | ❌ | `price_extractor.py:294-309` — **không được nhắc ở §5.3 hay §5.5** |

### 2.6. §6 / §6B — Luồng chat & công cụ

| Khẳng định | KQ | Minh chứng |
|---|:--:|---|
| Thứ tự 0→7 trong `generate()` | ✅ | `chat.py`: form `:383` → small-talk `:494` → intent `:518` → guard `:552` → history `:588` → scope `:593` → **router `:600`** |
| `RequestRoute` 6 giá trị | ✅ | `router.py:42-48` — khớp từng tên |
| `RouteDecision` 12 trường | ✅ | `router.py:51-66` — khớp từng trường kể cả `decided_by` |
| Luật tất định chạy trước classifier, fail-open `GENERAL_CHAT` | ✅ | `router.py:446,462` |
| `mode` mặc định `auto` | ✅ | `chat.py:191` |
| §6.5 1 vùng → ngưỡng nới **0.4** | ✅ | `chat.py:312` `min(score_threshold, 0.4)` |
| §6.5 ≥2 vùng → `top_k=4`/vùng, ngưỡng 0.4 | ✅ | `chat.py:294,299` |
| §6.4 `run_tool_loop` `max_rounds=4` | ✅ | `tool_loop.py:68` |
| §6.4 `allow_web_fallback` bị backend ghi đè | ✅ | `tool_loop.py:69`; `chat.py:405` |
| §6B.3 **6 tool trong MCP server** | ✅ | `mcp/server.py:25-32` — đúng 6, đúng tên |
| §6B.3 **3 tool cho chat agent** | ✅ | `tool_loop.py:28-32` — đúng 3, đúng tên |
| §6B.3 `lookup_material_record()` là service nội bộ | ✅ | `service.py:255` |
| §6B.3 `allow_web_fallback` không có trong JSON schema công khai | ✅ | `cost_tool.py:55-84` — không xuất hiện |
| §6B.3 `estimate_material_quantity` 7 `work_type` | ✅ | `quantity_tool.py:27-34` — khớp cả 7 |
| §6B.3 quantity tool là tool duy nhất không chạm DB | ✅ | `quantity_tool.py:63-67` chỉ gọi `formulas.*` |
| §6B.3 `calculate_construction_cost` bắt buộc `floor_area_m2` + `region` | ✅ | `cost_tool.py:84` `"required": ["floor_area_m2", "region"]` |
| §6B.3 `project_type` 10 giá trị, mặc định `nha_pho` | ✅ | `cost_tool.py:63-65`; `project_types.py:394` |
| **§6B.3 bảng tham số `lookup_material_price`** | ⚠️ | 3 sai lệch — xem §3.2 |
| **§6B.3 `deep_research` "vòng LangGraph 6 node"** | ⚠️ | Graph có **5 node** (`graph.py:44-48`) |
| **§6B.3 "vẫn nằm trong MCP server để MCP client ngoài dùng được"** | ⚠️ | MCP server **không được mount** — xem §3.4 |

### 2.7. §8 / §8B — Dự toán chi phí

| Khẳng định | KQ | Minh chứng |
|---|:--:|---|
| §8.3 khoảng ±15%/+20% | ✅ | `cost_tool.py:237,574` — `*0.85`, `*1.20` |
| §8.3 tính ngược ngân sách khi có `target_budget_vnd` | ✅ | `cost_tool.py:253-258` |
| §8.2 `limit=15` ứng viên, `exclude_name_keywords` | ✅ | `cost_tool.py:351-352` |
| §8.2 sub-model disambiguation chọn 1 dòng hoặc -1 | ✅ | `cost_tool.py:118` `_disambiguate` |
| §8.2 chạy song song `asyncio.gather` | ✅ | `cost_tool.py:427` |
| §8.2B `allow_web_fallback` mặc định `false`, gate Firecrawl | ✅ | `cost_tool.py:293,384,394`; `config.py` → `/config/chat` trả `allow_web_fallback_default: False` |
| §8B.2 `f` = 1,00 / 1,00 / 1,15 | ✅ | `cost_tool.py:110` `_FINISH_MULTIPLIER` |
| §8B.2 `f` chỉ áp cho sơn + gạch lát, chỉ khi `finish_applies` | ✅ | `cost_tool.py:301-308` `_FINISHING_SLUGS = {"son", "gach_lat"}` |
| **§8B.3 bảng hệ số 10 loại hình** | ✅ | `project_types.py:222-392` — **kiểm tra từng ô, khớp 100%** (kể cả `tuong_rao` m² mặt tường, `san_nen` cát 0,55/đá 0,05) |
| §8B.6 `price_min`/`price_max` mỗi vật liệu | ✅ | `project_types.py:60-61, 82-196` |
| §8B.6 `alt_units` quy đổi tấn→kg | ✅ | `project_types.py:66, 96` `_PER_TONNE` |
| **§8.1 `_PER_M2_COEFFICIENTS` là đường chạy thật** | ⚠️ | **Mã chết** — xem §3.3 |
| **§8.1 "Rồi qua `formulas.concrete/rebar/masonry_wall/paint`"** | ⚠️ | `cost_tool.py` **không import `formulas`** — xem §3.3 |
| **§8.2 "Với 4 hạng mục (bê tông, thép, gạch, sơn)"** | ⚠️ | Thực tế lặp mọi slug trong `project.coefficients` — `nha_pho` có **7** |

### 2.8. §9–§13 — Voice, Research, Sources, API, DB, khởi động

| Khẳng định | KQ | Minh chứng |
|---|:--:|---|
| §9.1 `STT_BACKEND=local\|http`, PhoWhisper resolve | ✅ | `config.py:129`; `app/core/voice/phowhisper.py` |
| §9.1 deploy mặc định `phowhisper-medium`, cpu, int8 | ✅ | `.env` — `WHISPER_MODEL_SIZE=phowhisper-medium` (mặc định **code** là `base`, `config.py:131`) |
| §9.1 nạp sẵn lúc khởi động | ✅ | `main.py:109-122` `_load_whisper_safe` |
| §9.2 `POST /voice/tts/stream`, `POST /voice/stt` | ✅ | `voice.py:22,33` |
| §10 LangGraph node: expander → search → aggregate → quality → response | ✅ | `graph.py:44-59` (5 node, có `add_conditional_edges` cho vòng lặp) |
| §10 `RESEARCH_MAX_ITERATIONS=3`, `QUALITY_THRESHOLD=0.75` | ✅ | `config.py:143,145` |
| §10B.2 `AnswerSource` các trường | ✅ | `app/core/chat/sources.py:80+` |
| §10B.3 `REGION_LABELS` 5 vùng + `NO_REGION_LABEL` | ✅ | `sources.py:61-68` |
| §10B.4 log `chat_turn` gồm `production_model` | ✅ | `chat.py:341` |
| §11 toàn bộ 12 nhóm endpoint | ✅ | `app/api/router.py:20-31` — khớp 100% prefix |
| §11 `PATCH /kb/{id}` | ✅ | `knowledge_base.py:80` |
| §11 `GET /config/chat` trả 4 khoá | ✅ | `config.py:52-61` — khớp từng khoá |
| §11 `/metrics` Prometheus | ✅ | `app/monitoring/metrics.py:55` |
| §12.1 sơ đồ quan hệ bảng | ✅ | `models.py` — 11 bảng, khớp sơ đồ |
| §12.1 cascade tường minh vì FK `NOT NULL` | ✅ | `models.py:100-105,137` + comment giải thích đúng lý do |
| §13 thứ tự startup | ✅ | `main.py:76,80,92,122` — đúng thứ tự |
| §13 Docker Compose 8 service | ✅ | `docker-compose.yml` — `migrate, ui, app, postgres, qdrant, rabbitmq, prometheus, grafana` |
| **§12.2 bảng migration dừng ở 0009** | ⚠️ | `0010_kb_table_heavy_chunking.py` tồn tại — xem §3.5 |
| **§12.3 "sparse — khai báo sẵn, chưa bật BM25"** | ⚠️ | Mâu thuẫn §4.2 và code — xem §3.5 |
| **§12.1 "Cạm bẫy còn tồn tại: xoá KB không dọn Qdrant"** | ⚠️ | Mâu thuẫn §4.3 và code — xem §3.5 |
| **§14 "mode mặc định: RAG"** | ⚠️ | `chat.py:191` `mode: str = "auto"` |
| §3 pipeline stage `ocr` (progress 0.2) | ❌ | `pipeline.py:75` — có event này, §3 không liệt kê |

---

## 3. Danh sách vấn đề theo mức độ nghiêm trọng

### 🔴 CRITICAL

#### 3.1. Model production thực tế ≠ model tài liệu khẳng định

Tài liệu nhấn mạnh điều này **ba lần** (§0 khung trích dẫn, §2.3B, §0B.5) rằng
model production là `google/gemini-2.5-flash`. Mặc định trong code đúng như vậy:

```python
# app/config.py:74
openrouter_chat_model: str = "google/gemini-2.5-flash"
```

Nhưng file `.env` đang chạy **ghi đè**:

```
OPENROUTER_CHAT_MODEL=openai/gpt-4o-mini
OPENROUTER_RESEARCH_MODEL=openai/gpt-4o-mini
```

**Hệ quả:** mọi câu trả lời RAG, presenter giá, presenter dự toán và agent
tool-loop đang chạy trên `gpt-4o-mini`, không phải Gemini. `GET /config/chat`
trả `default_model` đọc từ `settings` nên frontend cũng hiển thị `gpt-4o-mini`
— tức là **UI đúng, tài liệu sai**.

Đây cũng chính là chỗ tài liệu lập luận mạnh nhất ("Chỉ có **một** chỗ đổi:
`OPENROUTER_CHAT_MODEL`") — lập luận đúng, nhưng giá trị thực tế của chỗ đó
không phải cái tài liệu viết.

> **Ghi chú bối cảnh:** khác biệt này đến từ việc `.env` hiện tại được giữ lại
> có chủ ý trong đợt đồng bộ mã nguồn ngày 2026-08-09 (bản chuẩn có
> `gemini-2.5-flash`, xem `.env.new`). Cần quyết định: sửa `.env` cho khớp tài
> liệu, hay sửa tài liệu cho khớp `.env`.

> **✅ ĐÃ SỬA.** Xác nhận: `gemini-2.5-flash` là model production đúng.
> `.env` đã ghi đè bằng `.env.new` (`OPENROUTER_CHAT_MODEL` và
> `OPENROUTER_RESEARCH_MODEL` = `google/gemini-2.5-flash`). Bản `.env` cũ giữ
> lại tại `.env.bak-preflash`. Tài liệu không cần sửa — nó đã đúng ngay từ đầu.

---

### 🟠 MAJOR

#### 3.2. §6B.3 — Bảng tham số `lookup_material_price` sai 3 điểm

Tài liệu (dòng 1903–1907):

| tham số | kiểu | bắt buộc |
|---|---|:--:|
| `region` | `HN` \| `DN` \| `HCM` | **✔** |
| `material_name` | chuỗi | ✘ |
| `material_category` | chuỗi | ✘ |

Thực tế `app/core/mcp/tools/price_lookup_tool.py:27-57`:

1. **`region` KHÔNG bắt buộc** — schema ghi `"required": []`, và description
   nói rõ *"BỎ TRỐNG nếu câu hỏi không nêu vùng… ĐỪNG đoán vùng"*.
2. **Enum có 5 vùng**, không phải 3: `["HN", "DN", "HCM", "KH", "AG"]`.
3. **Thiếu hẳn tham số thứ 4 `manufacturer`** — dùng cho câu hỏi danh mục
   ("công ty X bán những loại vật liệu nào"), có thể truyền riêng mà không cần
   `material_name`.

Điểm 1 đặc biệt đáng chú ý vì tài liệu **tự mâu thuẫn**: §5B.7 đã gạch ngang
đúng khẳng định này và ghi **[ĐÃ SỬA]**, nhưng §6B.3 không được cập nhật theo.

`COST_TOOL` cũng dùng enum 5 vùng (`cost_tool.py:61`), trong khi §6B.3 và §6.6
đều nói hệ thống "chỉ có HN/DN/HCM".

> **✅ ĐÃ SỬA.** Viết lại bảng tham số `lookup_material_price` ở §6B.3: `region`
> đổi thành không bắt buộc kèm giải thích vì sao, enum 5 vùng, thêm dòng
> `manufacturer`. §6.6 cũng sửa "chỉ có HN/DN/HCM" → nêu đủ 5 mã vùng, chỉ rõ
> 3 vùng đầu có dữ liệu đầy đủ nhất.

#### 3.3. §8.1 mô tả mã chết, và gán sai module tính khối lượng

Hai lỗi trong cùng một đoạn ngắn:

**(a) `_PER_M2_COEFFICIENTS` không còn được dùng.** Nó được định nghĩa ở
`cost_tool.py:91-96` cùng `_COEFFICIENT_LABELS` và `_COEFFICIENT_UNITS`, nhưng
`grep -rn "_PER_M2_COEFFICIENTS" app/ tests/` chỉ ra **đúng 1 kết quả — chính
dòng định nghĩa**. Đường chạy thật là `project.coefficients` từ
`PROJECT_TYPES` (`cost_tool.py:305-311`) — tức là **§8B.3 mới đúng, §8.1 sai**.

**(b) `cost_tool.py` không hề gọi `formulas`.** Tài liệu viết *"Rồi qua
`formulas.concrete/rebar/masonry_wall/paint` ra khối lượng từng vật liệu (số
viên gạch, lít sơn…)"*. Thực tế cost tool tính thẳng:

```python
# cost_tool.py:305-308
for slug, per_m2 in project.coefficients.items():
    qty = area * per_m2
    if slug in _FINISHING_SLUGS:
        qty *= finish_mult
```

`formulas.py` chỉ được `quantity_tool.py:63-67` dùng — đúng như §6B.3 mô tả.
Nên §8.1 và §6B.3 đang nói ngược nhau về cùng một file.

**(c)** Kèm theo, §8.2 nói *"Với **4 hạng mục** (bê tông, thép, gạch, sơn)"* —
thực tế số hạng mục bằng số slug của loại hình: `nha_pho` có 7 (thêm xi măng,
cát, gạch lát), `nha_xuong` có 7 slug khác hẳn.

> **✅ ĐÃ SỬA.** Xoá `_PER_M2_COEFFICIENTS`/`_COEFFICIENT_LABELS`/
> `_COEFFICIENT_UNITS` khỏi `cost_tool.py` (mã chết, không nơi nào gọi). Viết
> lại §8.1 mô tả đúng vòng lặp `for slug, per_m2 in project.coefficients.items()`
> và làm rõ `formulas.py` chỉ phục vụ `estimate_material_quantity`, không phải
> `calculate_construction_cost`. Sửa "4 hạng mục" ở §8.2 và §8.3 thành "mọi
> hạng mục của loại hình — số lượng tuỳ loại hình, không cố định".

#### 3.4. MCP server không được mount — 3 tool "chỉ dùng qua MCP" không truy cập được

`app/core/mcp/server.py:58` định nghĩa `get_mcp_app()`, docstring ghi *"Runs as
an SSE MCP server alongside FastAPI on /mcp path"*. Nhưng:

```
$ grep -rn "get_mcp_app\|mount(" app/ --include=*.py
app/monitoring/metrics.py:55:    app.mount("/metrics", metrics_app)
app/core/mcp/server.py:58:def get_mcp_app():
```

**`get_mcp_app()` không bao giờ được gọi.** `main.py` chỉ mount `/metrics`.

Điều này làm sai hai khẳng định:

- §6B.3: *"Chúng vẫn nằm trong MCP server để công cụ ngoài (MCP client) dùng
  được."* — không có endpoint nào để MCP client kết nối.
- §6.4: *"Ba công cụ chỉ dùng được qua MCP client bên ngoài."*

Thực tế `rag_query`, `web_search`, `deep_research` hiện **không gọi được từ bất
kỳ đâu** ngoài `search.py`/`research.py` gọi trực tiếp handler nội bộ.

> **✅ ĐÃ SỬA (phương án a — mount thật).** Thêm `app.mount("/mcp", get_mcp_app())`
> vào `app/main.py`. Nhân tiện sửa luôn một lỗi thứ hai phát hiện khi mount:
> `get_mcp_app()` trước đó chỉ trả về hàm xử lý luồng SSE, thiếu route nhận
> `POST` mà client gửi yêu cầu về — tức trước khi sửa, dù có mount thì client
> vẫn kết nối được nhưng không gọi tool được. Nay trả về một app Starlette với
> cả `GET /mcp/sse` và `POST /mcp/messages/`.

---

### 🟡 MINOR

#### 3.5. Ba mâu thuẫn nội bộ giữa mục mới và mục cũ

Tài liệu đã được cập nhật ở phần đầu nhưng phần cuối giữ nguyên bản cũ:

| Mục cũ (sai) | Mục mới (đúng) | Code |
|---|---|---|
| §12.3 *"sparse (khai báo sẵn, **chưa bật BM25**)"* | §4.2 mô tả đầy đủ hybrid đang chạy | `client.py:143-146` ghi sparse vector mỗi lần upsert; `:296-301` fuse RRF |
| §12.1 *"Cạm bẫy **còn tồn tại**: xoá KB thì không dọn Qdrant… Script dọn: `purge_orphaned_vectors.py`"* | §4.3 *"✔ `delete_by_kb` ← đã bổ sung"* | `knowledge_base.py:138` gọi `delete_by_kb` trước khi xoá Postgres |
| §14 *"mode mặc định: **RAG**"* | §6.0 *"`auto` — **mặc định production**"* | `chat.py:191` `mode: str = "auto"` |

> **✅ ĐÃ SỬA cả ba.** §12.3 nay nói "sparse BM25 đang hoạt động", trỏ về §4.2.
> §12.1 nay nói cạm bẫy đã sửa, trỏ về §4.3, và mô tả lại `purge_orphaned_vectors.py`
> đúng vai trò dọn cặn cũ chứ không phải workaround cho lỗi còn sống. §14 viết
> lại toàn bộ ví dụ end-to-end theo đúng luồng `mode=auto` → router →
> `EXACT_STRUCTURED` (khớp §5B.4/§6.0), kèm chú thích câu hỏi giải thích thì đi
> `DOCUMENT_RAG` như thế nào.

#### 3.6. §12.2 — Bảng migration thiếu revision `0010`

Bảng liệt kê 0001→0009. Nhưng `migrations/versions/0010_kb_table_heavy_chunking.py`
tồn tại (`down_revision = "0009_price_name_matching"`), và chính tài liệu tham
chiếu tới nó **hai lần** ở §1.1 và §2.3B ("Migration `0010` thêm cờ thứ hai,
`table_heavy_chunking`"). Chỉ là bảng tổng hợp chưa được thêm dòng.

#### 3.7. Tham chiếu dòng và module lệch

| Tài liệu | Thực tế |
|---|---|
| §1.3 `documents.status` tại `models.py:101` | `models.py:120` (dòng 100–105 giờ là comment cascade) |
| §2.12 `_is_legend_row`, `_fill_table_wide_unit` thuộc lớp OCR | Cả hai ở `price_extractor.py:197,402` |
| §6B.3 `deep_research` "vòng LangGraph **6 node**" | 5 node (`graph.py:44-48`) |

#### 3.8. ❌ Thiếu — thành phần có thật nhưng không được mô tả

1. **`_infer_mapping_from_data`** (`price_extractor.py:294`) — tầng fallback
   **thứ ba** để suy cột khi cả `_detect_header` lẫn cơ chế mượn header trang
   trước đều thất bại. §5.3 và §5.5 chỉ mô tả hai tầng đầu.
2. **Tham số `manufacturer`** của `lookup_material_price` (xem §3.2).
3. **Hai vùng `KH` (Khánh Hoà) và `AG` (An Giang)** — có trong `REGION_LABELS`,
   trong enum cả hai tool, và trong query param của `/upload`. Tài liệu chỉ
   nhắc thoáng trong một dấu ngoặc ở §10B.3, còn §6.6 khẳng định *"chỉ có
   HN/DN/HCM"*.
4. **Event tiến độ `ocr` (progress 0.2)** (`pipeline.py:75`) — §3 liệt kê
   `parsing 0.1 → chunking 0.3 → …` mà bỏ qua stage này.
5. **`app/core/chat/query_context.py`, `price_answer.py`, `sources.py`** được
   nhắc tên nhưng không có mục mô tả riêng (chấp nhận được ở mức tài liệu này).
6. **OAuth Google/GitHub** (`app/core/auth/oauth.py`) — §11 nhắc một dòng,
   không có mục kiến trúc. Ít quan trọng.

---

## 4. Đề xuất chỉnh sửa

Xếp theo thứ tự nên làm:

| # | Mục | Việc cần làm | Công sức |
|---|---|---|---|
| 1 | §3.1 | **Quyết định model production trước.** Nếu Gemini là đúng: sửa `.env` (`OPENROUTER_CHAT_MODEL=google/gemini-2.5-flash`). Nếu gpt-4o-mini là đúng: sửa §0, §2.3B, §0B.5 và bỏ khung trích dẫn nhấn mạnh Gemini | 5 phút + quyết định |
| 2 | §6B.3 | Viết lại bảng tham số `lookup_material_price`: `region` **không** bắt buộc, enum 5 vùng, thêm dòng `manufacturer`. Đồng bộ với §5B.7 | 10 phút |
| 3 | §8.1 | Viết lại: bỏ `_PER_M2_COEFFICIENTS`, bỏ câu về `formulas.*`, trỏ sang §8B.3 làm nguồn duy nhất cho hệ số. Sửa §8.2 "4 hạng mục" → "mọi vật liệu của loại hình" | 15 phút |
| 4 | Code | **Xoá mã chết** `_PER_M2_COEFFICIENTS` / `_COEFFICIENT_LABELS` / `_COEFFICIENT_UNITS` (`cost_tool.py:91-108`) — giữ lại chỉ khiến người đọc sau lại tưởng đó là đường chạy thật | 5 phút |
| 5 | §3.4 | Chọn một: (a) mount MCP server trong `main.py` (`app.mount("/mcp", get_mcp_app())`) rồi giữ nguyên tài liệu; hoặc (b) sửa §6B.3/§6.4 nói rõ MCP server **chưa được expose**, 3 tool kia hiện chỉ là code dự phòng | 10 phút hoặc 1 dòng code |
| 6 | §12.3 | Sửa thành "dense COSINE 1536 + **sparse BM25 đang hoạt động** (§4.2)" | 2 phút |
| 7 | §12.1 | Xoá đoạn "Cạm bẫy còn tồn tại", thay bằng trỏ tới §4.3; đổi mô tả `purge_orphaned_vectors.py` thành "công cụ dọn cặn cũ" (đúng như §4.3 đã viết) | 3 phút |
| 8 | §14 | `mode mặc định: RAG` → `mode mặc định: auto → router quyết định`; cập nhật luôn luồng tóm tắt cho khớp §6.0 | 5 phút |
| 9 | §12.2 | Thêm dòng `0010 \| knowledge_bases.table_heavy_chunking — chọn ChunkProfile theo KB` | 1 phút |
| 10 | §5.3/§5.5 | Thêm một đoạn về `_infer_mapping_from_data` — tầng fallback thứ ba | 10 phút |
| 11 | §6.6, §10B.3 | Thống nhất số vùng: nêu rõ hệ thống hỗ trợ **5 mã vùng** (HN/DN/HCM/KH/AG), trong đó 3 vùng đầu có dữ liệu đầy đủ | 5 phút |
| 12 | §1.3, §2.12, §6B.3 | Sửa tham chiếu lệch: `models.py:120`; chuyển `_is_legend_row`/`_fill_table_wide_unit` sang mục §5.4; "5 node" | 5 phút |
| 13 | §3 | Thêm stage `ocr` (0.2) vào chuỗi tiến độ | 1 phút |

**Tổng:** khoảng **1,5 giờ** để đưa tài liệu về đúng 100%, cộng một quyết định
về model production.

---

## 5. Nhận xét tổng kết

Điểm mạnh nhất của tài liệu là nó **ghi lại lý do, không chỉ ghi lại kết quả** —
§0B.7 (những phương án bị loại bằng số liệu), §2.6 (ba loại ô rỗng và vì sao
lưới khuyết nguy hiểm nhất), §4.2 (vì sao ngưỡng chỉ gác nhánh dense) đều là
loại kiến thức thường mất đi khi người viết code rời dự án. Những mục này khớp
code tới từng hằng số.

Điểm yếu duy nhất mang tính hệ thống: **tài liệu được cập nhật theo từng đợt
sửa code, và mỗi đợt chỉ đụng vào mục liên quan trực tiếp**. Kết quả là các mục
tổng hợp ở cuối (§12, §14) và các bảng tra cứu (§6B.3, §8.1) giữ nguyên trạng
thái của hai–ba đợt refactor trước. Tất cả 11 lỗi ⚠️ đều thuộc kiểu này — không
có lỗi nào là hiểu sai kiến trúc.

Một gợi ý phòng ngừa: thêm một test kiểu `test_docs_match_code` chốt vài hằng
số dễ trôi nhất (danh sách tool trong `_AGENT_TOOLS` và `_TOOLS`, các enum
vùng, `RequestRoute`, revision migration mới nhất) — cùng loại cơ chế mà
`tests/test_sparse.py` đã dùng để khoá tokenizer không bị sửa lẻ.
