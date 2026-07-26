# Agentic RAG

A monolithic AI backend for a Vietnamese construction-materials domain assistant, combining **RAG**, **deterministic tool-calling for cost estimation**, **local voice I/O (GPU-capable)**, and an **MCP server** — exposed via FastAPI (HTTP/SSE), with a Next.js chat frontend.

---

## Architecture

![Architecture](docs/im1.png)

---

## 1. Tech stack

| Layer | Technology | Why |
|---|---|---|
| **API** | FastAPI (HTTP + SSE) | SSE for the chat UI's token stream |
| **LLM / embeddings / vision** | OpenRouter (OpenAI-compatible), model per task set independently in `.env` | One API key, swappable models per task without code changes |
| **Vector store** | Qdrant | Named-vector collection, batched upsert (200 pts/request — large PDFs otherwise hit `WriteTimeout`); dense-vector search only today despite a sparse (BM25) config also present — see `docs/kien-truc-he-thong.md` §16 |
| **Relational store** | PostgreSQL 16 + SQLAlchemy (async, `asyncpg`) + Alembic | Users, KBs, documents, and **structured** material-price rows (`material_prices` table) — exact lookups, not vector search |
| **Job queue** | RabbitMQ (`aio-pika`) | Every document upload, including into the 4 system KBs (§3) — one path, no separate startup-seeding job |
| **STT** | `faster-whisper` (CTranslate2) running **PhoWhisper** (Vietnamese fine-tune), `STT_BACKEND=local` (in-process) or `http` (your own GPU box via tunnel — used for GPU-less hosts like Railway) | No external STT API dependency; PhoWhisper measurably beats plain Whisper on Vietnamese |
| **TTS** | OpenAI's real `/v1/audio/speech` (`tts-1`), called directly — separate `OPENAI_API_KEY`, not via OpenRouter | OpenRouter has no genuine TTS endpoint; only "TTS-shaped" option there is a conversational audio-chat model, which can paraphrase instead of reading verbatim (see §2.3) |
| **Tool calling / MCP** | Custom `Tool` + `handle_*` registry (`app/core/mcp/tools/`), OpenAI-style tool-calling loop (`app/core/llm/tool_loop.py`) | Price/quantity/cost math is deterministic Python, never LLM-computed — see §4 |
| **Deep research** | LangGraph graph (expand → search → aggregate → quality-check → summarize) | Separate problem from tool-calling (iterative web search), kept as its own graph rather than folded into the tool loop |
| **Frontend** | Next.js 16 (App Router) + React 19, Tailwind, Zustand store | Chat/Search/Research are composer actions in one chat view, not separate routes (see §5) |
| **Auth** | JWT (access + refresh) + OAuth2 (Google, GitHub) | |
| **Monitoring** | Prometheus + Grafana (optional profile) | |

---

## 2. System flow

### 2.1. Chat — the full request pipeline

The frontend always sends `mode: "agent"` (there's no mode picker in the UI for this) — five
checks run in order, stopping at the first match:

```
User message → POST /api/v1/chat/stream
   │
   ├─ 1. form_submission present?
   │       → run the construction-cost tool directly (§4), no detection needed
   │
   ├─ 2. detect_small_talk(message)   app/core/chat/intent.py
   │       exact-match greeting/farewell/thanks/etc.?
   │       → canned reply, ZERO LLM calls, ~0.1s (see docs/kien-truc-he-thong.md §7)
   │
   ├─ 3. detect_intent(message)
   │       matches the fixed construction-cost intent?
   │       → SSE `form_request` event, render a form client-side, LLM never invoked
   │
   ├─ 4. off-topic guard   app/core/chat/topic_guard.py
   │       (only when no kb_id/project_id/skill_id is active)
   │       cheap classifier call says "not remotely related to construction/
   │       engineering/tech"? → polite refusal, main model never called
   │       (docs/kien-truc-he-thong.md §8)
   │
   └─ 5. run_tool_loop() — last 10 messages fetched as history, LLM decides
         whether to call lookup_material_price/calculate_construction_cost
         itself (§4) → SSE token deltas → frontend renders + (if the turn
         was voice-initiated) speaks the finished reply back
```

Full step-by-step detail, including the DB tables/Qdrant payload involved at each stage:
**[docs/kien-truc-he-thong.md](docs/kien-truc-he-thong.md)**.

### 2.2. Document ingestion (upload or system-KB seed)

Two pipelines share the same chunking/embedding backbone:

```
PDF/DOCX/TXT bytes
   │
   ├─ ChunkDispatcher.chunk()          app/core/chunking/dispatcher.py
   │     PdfChunker: PyMuPDF (text blocks, reading order) + pdfplumber (tables → HTML)
   │
   ├─ 0 chunks (scanned/image-only PDF)?
   │     → OCR fallback: render each page to an image, transcribe via an
   │       OpenRouter vision model (app/core/ingestion/ocr_fallback.py),
   │       re-chunk the transcribed text — only triggers when normal
   │       extraction found nothing, to avoid a vision call per page on
   │       every PDF
   │
   ├─ split_oversized_table_chunk()    a single table chunk can exceed the
   │     embedding model's 8192-token hard limit (a real 78-row price table
   │     → ~20k tokens) — split by row groups, repeat the header row in each
   │     piece so column context isn't lost; OpenRouter rejects the whole
   │     batch if even one item is oversized, not just that item
   │
   ├─ OpenRouterClient.embed()         text-embedding-3-small, 1536-dim,
   │     batched (EMBED_BATCH_SIZE)
   │
   ├─► QdrantStore.upsert_chunks()     batched 200 pts/request — narrative
   │     text + table HTML, tagged with region/source_type/price_period
   │     metadata for RAG retrieval and citation
   │
   └─► [price-extraction mode only] extract_price_rows()
         app/core/ingestion/price_extractor.py → MaterialPriceRepository
         → `material_prices` (Postgres) — see §4 for why this is a separate,
           structured store instead of relying on the vector search above
```

**One entry point:** `POST /api/v1/documents/upload/{kb_id}` or `/upload-price/{kb_id}` → publishes a job to RabbitMQ → `app/queue/consumer.py` picks it up → `IngestionPipeline`/`PriceExtractionPipeline`. This is also how the 4 system KBs (§3) get populated — there is no separate startup-time seeding step; every KB, system or user-created, is filled the same way, through the normal upload UI.

### 2.3. Voice

```
Composer mic button → MediaRecorder (browser) → stop → webm blob
   │
   ▼
POST /api/v1/voice/stt  →  STTProvider.transcribe()  (app/core/voice/stt.py)
   │   STT_BACKEND=local (in-process faster-whisper, CPU/GPU) or
   │   STT_BACKEND=http (a GPU box you run yourself, e.g. local-gpu-stt/,
   │   reached over an ngrok tunnel — the way to get GPU STT on a host
   │   with no GPU, e.g. Railway). Model: PhoWhisper (VinAI's Vietnamese
   │   Whisper fine-tune) via a CTranslate2 conversion — picked over plain
   │   Whisper after real testing showed it's meaningfully more accurate
   │   on Vietnamese speech.
   ▼
transcript → auto-sent as a normal chat message (viaVoice=true) → goes
through the full pipeline in §2.1 like any typed message (small talk,
off-topic guard, and RAG/tool-calling all apply identically — there is
no via_voice flag sent to the backend at all)
   │
   ▼
LLM reply streamed + displayed as normal chat text
   │
   ▼
POST /api/v1/voice/tts/stream  →  OpenAITTSService.stream()
   │   calls OpenAI's real /v1/audio/speech directly (separate
   │   OPENAI_API_KEY, not routed through OpenRouter) — takes the exact
   │   text already streamed above and renders it as audio verbatim
   ▼
frontend plays the WAV; the whole composer (typing, sending, starting a
new recording) stays locked until playback actually finishes
```

**Fixed since an earlier version:** TTS used to go through OpenRouter's `gpt-audio-mini` via
`/chat/completions` (`modalities: ["text","audio"]`) — since that's a *conversational* audio
model rather than a dedicated TTS engine, it would sometimes paraphrase instead of reading the
displayed text verbatim, even with an explicit "read verbatim" system prompt (OpenRouter has no
real `/audio/speech` endpoint to fall back to). Replaced with a direct call to OpenAI's actual
TTS API, which only ever renders the given text — no conversational framing, no risk of
"replying" instead of reading.

---

## 3. Construction-materials domain layer

4 fixed knowledge bases (`app/core/bootstrap/constants.py`) exist in every deployment — their **identity** is hardcoded (fixed UUIDs, name/description set by migration `0007_add_vendor_standards_kb.py`) but their **content is not auto-seeded**: each starts empty and is populated by manually uploading documents through the normal upload UI, exactly like a user-created KB. Only the KB shell itself is protected (`403` on `DELETE /api/v1/kb/{id}` for these 4, checked against `is_system_kb()`) — uploading into them, and deleting individual documents from them, is allowed for any authenticated user:

| KB | Purpose |
|---|---|
| **Dự toán giá nhà** | Official Sở Xây dựng price-announcement PDFs (công văn + phụ lục) — Hà Nội, Đà Nẵng, TP.HCM. National-average reference pricing for the cost-estimate flow (§4). **The only KB where `/upload-price/{kb_id}` (structured price-row extraction into `material_prices`) is allowed** — the other 3 reject that endpoint with 403 and only take the normal `/upload/{kb_id}` (RAG chunking, no structured extraction). |
| **Báo giá doanh nghiệp** | Vendor/company price quotes from anywhere in the country — narrative RAG content, not structured extraction. |
| **Kiến thức về VLXD cho kỹ sư** | Quantity-takeoff / cost-estimation methodology playbook, QCVN 16:2023, materials reference content for engineers. |
| **Quy chuẩn & tiêu chuẩn xây dựng Việt Nam** | QCVN/TCVN — Vietnamese national construction codes and standards. |

`seed_data/` still exists in-repo (the price/knowledge PDFs originally used to bootstrap these 4 KBs before this became a manual-upload flow) but nothing ingests it automatically anymore — there is no `app/core/bootstrap/seed.py` and no startup-time ingestion task. To populate a fresh deployment, upload real documents through the KB detail page in the UI (the "Dự toán giá nhà" page has extra Khu vực/Kỳ công bố fields that route to `/upload-price`; the other 3 use the plain uploader).

Full pipeline detail, header-detection heuristics, and known data-quality caveats (a source PDF genuinely lacking a price category is reported honestly as "no data", not guessed): **[docs/construction-pricing-pipeline.md](docs/construction-pricing-pipeline.md)**.

## 4. Why price math is deterministic Python, never LLM-computed

This is the core design constraint of the whole domain layer, not a stylistic choice:

- **`estimate_material_quantity`** — quantity-takeoff formulas (`app/core/construction/formulas.py`) straight from the methodology playbook's chapters (concrete §16, rebar §17, masonry §19, plaster §20, tile §21, paint §22). Pure Python, no LLM in the loop.
- **`lookup_material_price`** — direct SQL against `material_prices` (`WHERE region=... AND material_name ILIKE ...`), not vector similarity — a wrong material/region/period match here means a wrong cost downstream, so it reports "not found" instead of guessing.
- **`calculate_construction_cost`** — orchestrates the two above per material category, then **uses an LLM only to disambiguate which DB row is the right product** among unit-filtered candidates (e.g. distinguishing "bê tông thương phẩm" — ready-mix concrete — from "bê tông đúc sẵn" — precast concrete panels — when both loosely match a name search). The LLM never invents a price; it only picks an index into real rows, or says none fit, which maps to an honest "no data for this category" line rather than a wrong number. This replaced an earlier hand-maintained keyword-exclusion list, which was correct but too brittle to extend as new vendor files were added.

Two fixed-pipeline vs. free tool-calling **modes** exist side by side:
- **Fixed pipeline** (`app/core/chat/intent.py` → form → direct tool call, no LLM at all) for the one well-known, high-stakes intent ("giá xây nhà 100m2 ở Hà Nội") — guarantees correct parameters instead of trusting an LLM to parse them from free text.
- **`mode="agent"`** (`run_tool_loop()`) for open-ended questions — the LLM decides whether/which tool to call, with the risk of misparsed parameters that the fixed pipeline avoids.

Two more checks run *before* either of the above, both skip the LLM (or use a cheap fixed one)
to cut cost/latency on turns that don't need the real model at all: exact-match small talk
(greetings/thanks/etc. → canned reply, ~0.1s) and an off-topic guard (a cheap classifier call
refuses questions with no plausible connection to construction/engineering/tech, e.g. sports
trivia, before the user's actual selected — possibly premium — model ever gets called). Full
detail: **[docs/kien-truc-he-thong.md](docs/kien-truc-he-thong.md)** §7–§9.

---

## 5. Frontend

Next.js 16 (App Router) + React 19 + Tailwind, single-page chat app with a 6-item sidebar:
**Chat**, **Notes**, **Projects**, **Knowledge Base**, **Usage**, **Settings**.

- **Chat** is the main surface — the composer has a Chat/Search/Research mode switch (not
  separate routes; picking Search/Research just changes which streaming endpoint the current
  turn hits) plus a mic button for voice. Sidebar has a "RAG scope" section to pick the active
  KB/Project for the conversation.
- **Settings** has a 3-tier model picker (Budget/Standard/Premium — a frontend-owned constant
  list, there's no `/models` backend endpoint), temperature, and max tokens — these apply to
  new messages, they don't retroactively change anything already answered.
- **Knowledge Base** / **Projects** / **Notes** / **Usage** are straightforward CRUD screens
  against the matching REST endpoints.

Server-side `rewrites()` proxy `/api/*` to the backend, preserving the `Authorization` header
and — critically — **not** compressing/buffering SSE responses (`compress: false` in
`next.config.mjs`), otherwise streamed tokens arrive all at once instead of incrementally.

---

## 6. Prerequisites

- Docker + Docker Compose v24+
- An OpenRouter API key ([openrouter.ai/keys](https://openrouter.ai/keys)) — required for chat, embeddings, OCR fallback, and TTS
- **(Optional) NVIDIA GPU** for faster local Whisper STT — see §8

---

## 7. Quick start

```bash
git clone https://github.com/KhaiBoiPho/agentic-rag.git
cd agentic-rag
bash scripts/setup.sh              # creates .env with random secrets
# edit .env — fill in OPENROUTER_API_KEY at minimum
docker compose up -d --build
```

Services start in order: `postgres` → `migrate` → `qdrant` + `rabbitmq` → `app` → `ui`. The 4 system knowledge bases (§3) exist from the first `migrate` run but start **empty** — upload documents into them through the UI to populate. See [docs/getting-started.md](docs/getting-started.md) for the full walkthrough, troubleshooting, and how to test each feature end-to-end.

| Service | URL |
|---|---|
| UI | http://localhost:3210 |
| API docs | http://localhost:8000/docs |
| RabbitMQ | http://localhost:15672 (guest / guest) |
| Qdrant | http://localhost:6333/dashboard |

---

## 8. GPU (optional — local Whisper STT)

`faster-whisper` runs on CPU (`WHISPER_DEVICE=cpu`, `int8`) with no extra setup — fine for the `base`/`small` models. For `medium`/`large` on an NVIDIA GPU:

1. `.env`: `WHISPER_MODEL_SIZE=medium`, `WHISPER_DEVICE=cuda`, `WHISPER_COMPUTE_TYPE=float16`.
2. The `app` image already includes the pip-only CUDA runtime libs (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12` in `pyproject.toml`) with `LD_LIBRARY_PATH` pointed at them in the `Dockerfile` — no need to switch to a full `nvidia/cuda` base image.
3. `docker-compose.yml`'s `app` service already requests GPU passthrough (`deploy.resources.reservations.devices`, driver `nvidia`) — requires [`nvidia-container-toolkit`](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) installed on the **host**.
4. **If you run Docker Desktop** (macOS, or Linux with the Docker Desktop app rather than the native `dockerd`): GPU passthrough may fail with `could not select device driver "nvidia"` even with the toolkit installed on the host — Docker Desktop runs its own VM-based engine, separate from the host's native `dockerd`, and the two don't automatically share GPU config. Check `docker context ls` — if you have both a `desktop-linux` and a `default` context, switch to the native one: `docker context use default`, then verify with `docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi` before bringing the stack up there. `make`/`docker compose` need no changes — the `Makefile` already auto-detects the active socket.

Verify a GPU load actually happened: `docker compose logs app | grep -i whisper` should show `Loading local Whisper model=medium device=cuda compute_type=float16` followed by `Local Whisper model loaded and ready` with no CUDA/cuDNN errors; `docker compose exec app nvidia-smi` should list the GPU from inside the container.

---

## 9. Moving to another machine without re-uploading everything

Since KB content is only ever added by uploading through the UI (§3 — no automatic seeding), a fresh `docker compose up` on a new machine starts with all 4 system KBs (and any user KBs) **empty**. Re-uploading and re-ingesting (chunk → embed → extract) a large document set from scratch costs real time and OpenRouter API calls — the largest realistic source PDF (a several-hundred-page price annex) alone takes several minutes just for embedding. To avoid that on a new machine or after switching Docker engines, copy the two volumes that hold the already-processed result instead of re-uploading:

```bash
# On the source machine (stack stopped, so nothing's mid-write):
docker compose stop
docker run --rm -v agentic-rag_postgres_data:/data -v "$(pwd)":/backup alpine \
  tar czf /backup/backups/postgres_data.tar.gz -C /data .
docker run --rm -v agentic-rag_qdrant_data:/data -v "$(pwd)":/backup alpine \
  tar czf /backup/backups/qdrant_data.tar.gz -C /data .
docker compose start
```

```bash
# On the target machine, BEFORE the first `docker compose up`:
docker volume create agentic-rag_postgres_data
docker volume create agentic-rag_qdrant_data
docker run --rm -v agentic-rag_postgres_data:/data -v "$(pwd)":/backup alpine \
  tar xzf /backup/backups/postgres_data.tar.gz -C /data
docker run --rm -v agentic-rag_qdrant_data:/data -v "$(pwd)":/backup alpine \
  tar xzf /backup/backups/qdrant_data.tar.gz -C /data
docker compose up -d
```

With the volumes restored, the 4 system KBs (and any user KBs) come back exactly as they were — documents, chunks, and `material_prices` rows all live in Postgres/Qdrant, not in `seed_data/` or any other in-repo file, so there's nothing else to re-run. The `backups/` directory is gitignored (large binary dumps, regenerate locally rather than committing) — verify the exact volume name with `docker volume ls | grep -E "postgres_data|qdrant_data"` first if your Compose project directory isn't named `agentic-rag` (Compose derives the volume prefix from the directory name).

---

## 10. Environment

Copy `.env.example` to `.env` and fill in your keys. Every variable is documented with inline comments in [.env.example](.env.example).

**Minimum required:**
- `OPENROUTER_API_KEY` — LLM chat, embeddings, and vision OCR fallback go through OpenRouter
- `OPENAI_API_KEY` — real TTS (`/v1/audio/speech`), called directly, not via OpenRouter (§2.3)
- `SECRET_KEY` + `JWT_SECRET_KEY` — generate with `openssl rand -hex 32` (done automatically by `scripts/setup.sh`)

**Optional (feature-gated):**
- Local Whisper GPU: `STT_BACKEND=local`, `WHISPER_DEVICE=cuda`, `WHISPER_COMPUTE_TYPE=float16` (§8) — or `STT_BACKEND=http` to point at a GPU box you run yourself (`local-gpu-stt/`), for hosts with no GPU of their own
- Deep research web search: `FIRECRAWL_API_KEY`
- OAuth: `GOOGLE_CLIENT_ID/SECRET`, `GITHUB_CLIENT_ID/SECRET`

**Not used anymore, may still appear in old notes:** ElevenLabs (`ELEVENLABS_*`), RunPod (`RUNPOD_*`, tried for STT then dropped — cold-start too slow), gRPC (`GRPC_HOST/PORT`, removed entirely — no real consumer ever used it).

---

## 11. Makefile

```bash
make up                          # build + start all containers
make down                        # stop and remove containers
make restart                     # restart app container only
make logs                        # follow app logs
make shell                       # bash inside app container

make migrate                     # alembic upgrade head
make migrate-down                # rollback one revision
make migrate-gen msg="your msg"  # autogenerate migration from model changes

make proto                       # compile .proto → Python stubs
make test                        # pytest + coverage
make lint && make fmt            # ruff check + format
make monitoring                  # start Prometheus + Grafana
```

`DOCKER_HOST` is auto-detected from whichever Docker socket exists (Docker Desktop macOS, native Linux Engine, or Docker Desktop Linux) — no manual edits needed regardless of which engine you're on.

---

## 12. Monitoring (optional)

```bash
docker compose --profile monitoring up -d
```

| Service | URL | Credentials |
|---|---|---|
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3001 | admin / admin |

Dashboard is auto-provisioned from `grafana/dashboards/agentic_rag.json`.

---

## 13. Project structure

```
agentic-rag/
├── app/
│   ├── main.py              # FastAPI app factory + startup (Qdrant connect, system-KB seed, Whisper load)
│   ├── config.py            # Settings (reads .env)
│   ├── api/v1/               # REST endpoints (auth, chat, documents, knowledge_base, search, research, voice, config)
│   ├── core/
│   │   ├── chunking/        # PDF / DOCX / TXT chunkers + dispatcher
│   │   ├── ingestion/       # Ingestion pipelines (generic + price-extraction), OCR fallback, price_extractor
│   │   ├── construction/    # Deterministic quantity/cost formulas (§4)
│   │   ├── chat/            # Fixed-pipeline intent detection + form schemas
│   │   ├── retrieval/       # Qdrant dense-vector retriever
│   │   ├── llm/             # OpenRouter client + tool-calling loop
│   │   ├── research/        # LangGraph research graph
│   │   ├── voice/           # STT (local/http backends, PhoWhisper), TTS (OpenAI direct)
│   │   ├── mcp/             # MCP server + tools (price_lookup, quantity, cost)
│   │   ├── bootstrap/       # Fixed system-KB IDs/names + is_system_kb() (constants.py) — see §3
│   │   └── auth/            # JWT, OAuth, passwords
│   ├── db/
│   │   ├── postgres/        # SQLAlchemy models + repos (incl. material_prices)
│   │   └── qdrant/          # Vector store client
│   ├── queue/               # RabbitMQ publisher + consumer
│   └── monitoring/          # Prometheus metrics + middleware
├── web/                     # Next.js 15 (App Router) + React 19 — single chat surface, see §5
├── seed_data/                # PDFs originally used to bootstrap the 4 system KBs — no longer auto-ingested, see §3
├── backups/                  # gitignored — local Postgres/Qdrant volume dumps (§9)
├── scripts/                  # setup.sh, one-off ingestion/dedup scripts used during development
├── migrations/               # Alembic migrations
├── grafana/                 # Prometheus config + dashboards
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

---

## 14. API

Swagger UI at http://localhost:8000/docs (when `APP_DEBUG=true`).

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Register |
| `POST` | `/api/v1/auth/login` | Login → tokens |
| `GET` | `/api/v1/auth/oauth/google` | Google OAuth2 |
| `GET` | `/api/v1/auth/oauth/github` | GitHub OAuth2 |
| `POST/GET` | `/api/v1/kb` | Create / list KBs (system KBs included, flagged `is_system: true`) |
| `DELETE` | `/api/v1/kb/{id}` | Delete a KB (403 on the 4 system KBs — only the shell is protected, see §3) |
| `POST` | `/api/v1/documents/upload/{kb_id}` | Upload document to KB — allowed on any KB, including system KBs |
| `POST` | `/api/v1/documents/upload-price/{kb_id}` | Upload a material price-announcement PDF (`region`, `price_period` query params) — extracts structured rows into Postgres alongside normal RAG chunking. Only allowed for the "Dự toán giá nhà" system KB (403 elsewhere) — see [docs/construction-pricing-pipeline.md](docs/construction-pricing-pipeline.md) |
| `GET` | `/api/v1/documents/{kb_id}` | List documents in a KB |
| `POST` | `/api/v1/chat/stream` | Streaming chat (SSE) — small talk / off-topic guard / fixed-intent form / agent tool-calling, in that order (§2.1). A message matching the fixed construction-cost intent returns a `form_request` event instead of an LLM answer; submit the filled form back via `form_submission` to run the tool directly, no detection re-run |
| `POST` | `/api/v1/search` | Web search (Firecrawl) |
| `POST` | `/api/v1/research` | Deep research (LangGraph) |
| `POST` | `/api/v1/voice/stt` | Transcribe audio (STT_BACKEND=local or http — §2.3) |
| `POST` | `/api/v1/voice/tts/stream` | Synthesize speech (OpenAI `/v1/audio/speech`, streamed WAV — §2.3) |
| `GET` | `/health` | Health check |
| `GET` | `/metrics` | Prometheus metrics |

---

## 15. Further reading

- **[docs/kien-truc-he-thong.md](docs/kien-truc-he-thong.md)** (Vietnamese) — the deepest-detail system doc: every Postgres table and its purpose, the Qdrant payload shape, the full chat pipeline step by step, small talk, the off-topic guard, the tool-calling flow, ingestion, voice, every frontend screen, deployment, and known rough edges
- [docs/getting-started.md](docs/getting-started.md) — clone-to-running walkthrough, first-run troubleshooting, end-to-end feature tests
- [docs/construction-pricing-pipeline.md](docs/construction-pricing-pipeline.md) — full detail on the price-extraction heuristics, known data-quality limits, and how to add a new fixed-pipeline intent/form
- [docs/railway-deploy.md](docs/railway-deploy.md) — deploying each service separately on Railway
- [docs/local-gpu-stt-demo.md](docs/local-gpu-stt-demo.md) — running STT on your own GPU box + ngrok tunnel
