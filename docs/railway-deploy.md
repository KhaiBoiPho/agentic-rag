# Deploying to Railway

This repo's `docker-compose.yml` is built for a single VM (or local Docker) and
does **not** map 1:1 onto Railway. Railway deploys each service independently
from its own Dockerfile/root directory — there is no multi-container compose
orchestration, no `depends_on`, and no GPU on standard plans. This guide lists
the services to create and the environment variables each one needs.

## Architecture on Railway

Create **one Railway project** with these services inside it (so they share
private networking):

| Railway service | Source | Notes |
|---|---|---|
| `postgres` | Railway's built-in **Postgres plugin** | Don't self-host via the `postgres:16-alpine` image — use the managed plugin, it gives you `DATABASE_URL` automatically. |
| `qdrant` | Docker image `qdrant/qdrant:v1.12.4` | Deploy as an empty Railway service pointed at this public image. Attach a volume at `/qdrant/storage` (Settings → Volumes) or data is lost on redeploy. Alternative: [Qdrant Cloud](https://cloud.qdrant.io) free tier — skip self-hosting entirely. |
| `rabbitmq` | Docker image `rabbitmq:3.13-management-alpine` | Attach a volume at `/var/lib/rabbitmq`. Alternative: [CloudAMQP](https://www.cloudamqp.com) free tier — skip self-hosting entirely. |
| `backend` | This repo, root directory `.` (uses the root `Dockerfile`) | FastAPI. |
| `migrate` | Same image as `backend`, but run as a **one-off command**, not a persistent service — see below. |
| `frontend` | This repo, root directory `web` (uses `web/Dockerfile`) | Next.js UI ("Cốt"). The old `frontend/` directory is unused — do not point a service at it. |

Railway gives every service in a project a private hostname
`<service-name>.railway.internal`, reachable from other services in the same
project without leaving the network. Use that instead of public URLs for
service-to-service traffic (backend → Postgres/Qdrant/RabbitMQ, frontend →
backend).

## 1. Postgres

Add the **Postgres** plugin from Railway's service catalog. It auto-generates
`DATABASE_URL`. This repo expects the SQLAlchemy async driver, so wire it as:

```
DATABASE_URL = postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}
```

(Railway's plugin gives you a plain `postgres://` URL — swap the scheme to
`postgresql+asyncpg://` as above, referencing the plugin's variables.)

## 2. Qdrant

New service → **Empty Service** → set image to `qdrant/qdrant:v1.12.4` →
add a volume mounted at `/qdrant/storage`. No env vars required. Note its
internal address: `qdrant.railway.internal`, port `6333`.

## 3. RabbitMQ

New service → **Empty Service** → image `rabbitmq:3.13-management-alpine` →
volume at `/var/lib/rabbitmq`. Set:

```
RABBITMQ_DEFAULT_USER=<pick something, not guest/guest>
RABBITMQ_DEFAULT_PASS=<pick something>
```

Internal address: `rabbitmq.railway.internal`, port `5672`.

## 4. Backend (`app`)

New service from this GitHub repo, **root directory `.`** (builds the repo's
top-level `Dockerfile`). Environment variables:

```
APP_ENV=production
APP_DEBUG=false
APP_PORT=${{PORT}}                 # Railway injects PORT; app already reads APP_PORT
SECRET_KEY=<openssl rand -hex 32>
JWT_SECRET_KEY=<openssl rand -hex 32>

DATABASE_URL=postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}

QDRANT_HOST=qdrant.railway.internal
QDRANT_PORT=6333

RABBITMQ_URL=amqp://<user>:<pass>@rabbitmq.railway.internal:5672/

OPENROUTER_API_KEY=<your key>
FIRECRAWL_API_KEY=<your key>

# TTS only (real OpenAI /audio/speech — OpenRouter has no such endpoint).
OPENAI_API_KEY=<your key>
OPENAI_TTS_BASE_URL=https://api.openai.com/v1
OPENAI_TTS_MODEL=tts-1

# STT — PhoWhisper (VinAI's Vietnamese Whisper fine-tune), not OpenAI.
# "local" runs it in-process on CPU; GPU is not available on standard
# Railway plans, so WHISPER_DEVICE must stay cpu (cuda crash-loops the
# service at startup trying to init CUDA that doesn't exist here).
# phowhisper-medium is the accuracy/latency tradeoff that's usable on CPU;
# phowhisper-large is more accurate but noticeably slower without a GPU.
# If you need GPU-speed PhoWhisper on Railway, run local-gpu-stt/ on your
# own GPU box instead and switch STT_BACKEND=http + STT_HTTP_URL/SECRET.
STT_BACKEND=local
WHISPER_MODEL_SIZE=phowhisper-medium
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8

CORS_ORIGINS=["https://<your-frontend>.up.railway.app"]
```

**Do not** set a volume mount over `/app` (the `docker-compose.yml`'s
`volumes: - .:/app` is dev-only live-reload — Railway builds an immutable
image per deploy, there's no host filesystem to bind to, and doing so would
just be a no-op / misconfiguration to remove if you ever copy compose env
settings over by hand).

## 5. Migrations

Railway doesn't have a `depends_on: service_completed_successfully`
equivalent. Run migrations as a one-off after the backend service's env vars
are set, using the Railway CLI:

```bash
railway link                      # select this project
railway run --service backend alembic upgrade head
```

Re-run this after every deploy that includes new migrations (there's no
automatic pre-deploy hook on Railway without a paid add-on/custom script).

`alembic upgrade head` on a brand-new Railway Postgres runs all 7 migrations
in order:

| Migration | What it does |
|---|---|
| `0001_initial_schema` | Core tables — users, knowledge_bases, documents, conversations, messages, etc. |
| `0002_material_prices` | Creates the `material_prices` table (structured price lookups) — **empty**, no rows inserted. |
| `0003_seed_system_kb` | Inserts the system user row + the first 2 system KBs ("Kiến thức về VLXD cho kỹ sư", "Dự toán giá nhà") — rows only, `document_count = 0`. |
| `0004_notes_projects` | Notes + Projects tables. |
| `0005_usage_records` | Usage/token-tracking table. |
| `0006_messages_recent_index` | Index for the recent-messages query path (performance only, no data change). |
| `0007_add_vendor_standards_kb` | Renames the 2 KBs from 0003 to their current names/descriptions, and inserts the remaining 2 ("Báo giá doanh nghiệp", "Quy chuẩn & tiêu chuẩn xây dựng Việt Nam"). |

### What you have right after migrating — and what you don't

The 4 system knowledge bases exist as empty shells (their ids are hardcoded
in `app/core/bootstrap/constants.py` and referenced by the app, so they must
exist — that's what 0003+0007 guarantee) but contain **zero documents** and
`material_prices` has **zero rows**. There is no automatic seed-data
ingestion anymore (`app/core/bootstrap/seed.py` was removed) — getting this
fresh deploy to the same working state as an existing environment means
manually uploading documents through the normal UI, once, after first
deploy:

- **"Dự toán giá nhà"** — upload your price-list PDF(s) via that KB's page
  using the special "trích giá có cấu trúc" flow (calls `POST
  /api/v1/documents/upload-price`, the only KB this endpoint accepts). This
  is what actually populates `material_prices` — see §6 below.
- The other 3 system KBs, and any user/project KBs — upload via the normal
  document-upload flow (chunk + embed into Qdrant), no different from a
  user creating their own KB.

To reproduce this repo's own local dev environment exactly (as of this
writing: 10 documents in "Dự toán giá nhà" → 10,010 `material_prices` rows,
3 documents in "Kiến thức về VLXD cho kỹ sư", the other 2 KBs empty), the
source files are still sitting in `seed_data/` (unused by the app now, but
not deleted) — drag them into the matching KB through the UI once:

```
# → "Dự toán giá nhà", via the upload-price flow:
seed_data/prices/HN/BangGia-VLXD-HaNoi-QuyII-2026.pdf
seed_data/prices/HN/CongVan-CongBoGia-VLXD-HaNoi-QuyII-2026.pdf
seed_data/prices/HN/BangGia-VLXD-BoSung-NhuaDuong-HaNoi-QuyII-2026.pdf
seed_data/prices/DN/BangGia-VLXD-DaNang-Thang06-2026.pdf
seed_data/prices/DN/CongVan-CongBoGia-VLXD-DaNang-Thang06-2026.pdf
seed_data/prices/DN/BangGia-VatTuDien-DaNang-Thang06-2026.pdf
seed_data/prices/DN/BangGia-VatTuNuoc-DaNang-Thang06-2026.pdf
seed_data/prices/HCM/ThongBao-CongBoGia-VLXD-HCM-Thang06-2026.pdf
seed_data/prices/HCM/BangGia-VLXD-KhoangSan-HCM-Thang06-2026.pdf
seed_data/prices/HCM/BangGia-VLXD-ThamKhaoThiTruong-HCM-Thang06-2026.pdf

# → "Kiến thức về VLXD cho kỹ sư", via the normal upload flow:
seed_data/knowledge/QCVN-16-2023.pdf
seed_data/knowledge/VLXDMoi_PhamHuuDuy.pdf
seed_data/knowledge/DataRAG-uoc-luong-gia-vlxd.md
```

There's no one-command way to bulk-load these on Railway — the auto-seed
task that used to do this was deliberately removed in favor of the normal
upload UI, so this is a one-time manual step per fresh deploy.

**Cost-estimation without `material_prices` populated:** the
`/api/v1/chat/stream` construction-cost tool doesn't crash or hang on a
missing price — for each material it (1) looks up `material_prices`, (2)
falls back to a live web-price search if that's empty, then (3) if even
that fails, renders an honest "_không có dữ liệu_" line for that item
instead of guessing a number. So a fresh Railway deploy is functional
immediately, just with lower-quality/no pricing until someone uploads the
real price list — it will never fabricate a number in place of missing
data.

## 6. Price extraction — what makes a document `material_prices` rows

Only PDFs uploaded through **`POST /api/v1/documents/upload-price`** (kb_id
must be the pricing KB — enforced server-side) go through structured
table/price extraction into `material_prices`; every other upload path only
chunks + embeds into Qdrant for RAG. Plain text files, scans without a
extractable table, or non-PDFs will fail that endpoint (`'No /Root object!
— Is this really a PDF?'` for non-PDFs is expected, not a bug) — it needs a
real PDF with a parseable price table (PyMuPDF/pdfplumber-extractable).

Uploading a long document does not overload the pipeline — extraction runs
as a queued background job (RabbitMQ), page-by-page/table-by-table, the
same as normal document chunking; a longer PDF just takes proportionally
longer in the background, it doesn't block the request or run synchronously
in the API process.

## 7. Frontend (`ui`)

New service from this GitHub repo, **root directory `web`**. Environment
variables:

```
API_PROXY_TARGET=http://backend.railway.internal:${{backend.PORT}}
```

This is read both at build time and at runtime by `next.config.mjs`'s
`rewrites()` — Railway sets it as a build arg automatically if declared as a
service variable before the first deploy.

The frontend already listens on Railway's `$PORT` (see `web/package.json`'s
`start` script, `next start -p ${PORT:-3210}`) — no further changes needed.

> **Migrating an existing service that was created against `frontend`:**
> Railway's root directory is a per-service setting, not something this repo
> controls — changing `docker-compose.yml` or anything else in-repo has no
> effect on it. Go to the service → **Settings → Source → Root Directory**,
> change `frontend` to `web`, then trigger a redeploy (or push a commit).
> Confirm the fix worked by checking the deploy log's startup banner — it
> should read `agentic-rag-frontend@... / Next.js 14.2.35` (old, wrong) vs.
> `cot-web@1.0.0 / Next.js 15.x` (new, correct).

After deploy, Railway assigns a public domain
(`<name>.up.railway.app`) — that's the URL to open, and the one to put back
into the backend's `CORS_ORIGINS`.

## Checklist before going live

- [ ] `WHISPER_DEVICE=cpu` on the backend (not `cuda`)
- [ ] `CORS_ORIGINS` on the backend includes the frontend's actual Railway domain
- [ ] `API_PROXY_TARGET` on the frontend points at the backend's **internal** Railway domain (`*.railway.internal`), not its public one — avoids an unnecessary public round-trip and works even if the backend has no public domain
- [ ] Ran `alembic upgrade head` against the Railway Postgres before the first request
- [ ] Qdrant and RabbitMQ each have a persistent volume attached (otherwise data disappears on every redeploy)
- [ ] `OPENROUTER_API_KEY` / `FIRECRAWL_API_KEY` / `OPENAI_API_KEY` set on the backend service
- [ ] Uploaded a price-list PDF via `upload-price` into "Dự toán giá nhà" so `material_prices` isn't empty (optional — cost estimation degrades gracefully without it, see §5, but pricing quality is much better with it)
- [ ] SSE still streams (not buffered) — Railway's edge proxy passes through `Cache-Control: no-transform`/chunked responses fine, but verify after first deploy by watching a `/api/v1/chat/stream` response arrive token-by-token rather than all at once

## Troubleshooting

**Frontend deploy log shows an old Next.js version / `agentic-rag-frontend` as
the package name:** the service's root directory is still `frontend` — see
the migration note in §7.

**`Failed to proxy http://<backend>.railway.internal:PORT/...` /
`ECONNREFUSED` in the frontend logs:** the frontend container itself is fine
(it's just relaying); the backend service isn't reachable at that address.
Check, in order:
1. Is the backend service actually **running** (not crash-looped)? Open its
   own deploy logs — a crash on `WHISPER_DEVICE=cuda` with no GPU, a missing
   `DATABASE_URL`, or a failed migration are the usual causes.
2. Does `API_PROXY_TARGET` on the frontend match the backend's **actual**
   Railway service name? It's always `<service-name>.railway.internal` —
   if you named the backend service `agentic-rag` instead of `backend`, the
   variable must read `http://agentic-rag.railway.internal:${{PORT}}`, not
   `http://backend.railway.internal:...`.
3. Is the backend bound to Railway's injected `$PORT` (`APP_PORT=${{PORT}}`
   per §4), not a hardcoded `8000`? A frontend variable hardcoded to `:8000`
   will break the moment Railway assigns the backend a different internal
   port.
