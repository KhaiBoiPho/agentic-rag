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
| `frontend` | This repo, root directory `frontend` (uses `frontend/Dockerfile`) | Next.js UI. |

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

# GPU is not available on standard Railway plans — must be cpu, otherwise
# faster-whisper fails to init CUDA at startup and the service crash-loops.
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

## 6. Frontend (`ui`)

New service from this GitHub repo, **root directory `frontend`**. Environment
variables:

```
API_PROXY_TARGET=http://backend.railway.internal:${{backend.PORT}}
```

This is read both at build time and at runtime by `next.config.mjs`'s
`rewrites()` — Railway sets it as a build arg automatically if declared as a
service variable before the first deploy.

The frontend already listens on Railway's `$PORT` (see
`frontend/package.json`'s `start` script) — no further changes needed.

After deploy, Railway assigns a public domain
(`<name>.up.railway.app`) — that's the URL to open, and the one to put back
into the backend's `CORS_ORIGINS`.

## Checklist before going live

- [ ] `WHISPER_DEVICE=cpu` on the backend (not `cuda`)
- [ ] `CORS_ORIGINS` on the backend includes the frontend's actual Railway domain
- [ ] `API_PROXY_TARGET` on the frontend points at the backend's **internal** Railway domain (`*.railway.internal`), not its public one — avoids an unnecessary public round-trip and works even if the backend has no public domain
- [ ] Ran `alembic upgrade head` against the Railway Postgres before the first request
- [ ] Qdrant and RabbitMQ each have a persistent volume attached (otherwise data disappears on every redeploy)
- [ ] `OPENROUTER_API_KEY` / `FIRECRAWL_API_KEY` set on the backend service
- [ ] SSE still streams (not buffered) — Railway's edge proxy passes through `Cache-Control: no-transform`/chunked responses fine, but verify after first deploy by watching a `/api/v1/chat/stream` response arrive token-by-token rather than all at once
