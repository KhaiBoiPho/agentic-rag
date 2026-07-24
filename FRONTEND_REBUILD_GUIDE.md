# Agentic RAG — Frontend Rebuild Guide

This document is the complete specification for building a **new, original** frontend
for the Agentic RAG backend. It describes every backend API, every data shape, every
feature flow, and the hard-won implementation gotchas — **without** reference to any
existing/company UI design. Build the visuals your own way; only the API contracts and
behavior below are fixed by the backend.

---

## 1. What the system is

A Vietnamese construction-materials AI assistant with Retrieval-Augmented Generation.
Users chat with an LLM that can answer from uploaded documents (RAG), search the web,
run multi-step "deep research", estimate construction costs from a structured price
database, and talk by voice.

**Backend stack (already built, do not change):**
- FastAPI (REST + SSE) on port **8000**, gRPC on **50051** (frontend uses REST only).
- PostgreSQL (users, KBs, documents, conversations, messages, material_prices, notes, projects, usage).
- Qdrant (vector store for RAG chunks).
- RabbitMQ (async document-ingestion queue).
- OpenRouter (LLM, embeddings, TTS), Firecrawl (web search), local Whisper (STT).

**Frontend responsibilities:** auth UI, chat UI with 3 modes (Chat / Search / Research),
document-backed RAG with citations, a construction-cost form flow, voice, and management
screens for Knowledge Bases, Projects, Notes, Usage, and Settings.

---

## 2. How to run

```bash
# from repo root
docker compose up -d --build          # starts everything
curl http://localhost:8000/health     # {"status":"ok"} when backend is up
```

Services and ports:

| Service   | Port(s)              | Purpose                              |
|-----------|----------------------|--------------------------------------|
| app       | 8000 (REST), 50051   | FastAPI backend                      |
| ui        | 3210                 | Frontend (you are rebuilding this)   |
| postgres  | 5433 → 5432          | Database                             |
| qdrant    | 6333 / 6334          | Vector store                         |
| rabbitmq  | 5672 / 15672 (mgmt)  | Ingestion queue                      |
| prometheus| 9090                 | Metrics (optional)                   |
| grafana   | 3001                 | Dashboards (optional)                |

**Required environment (`.env` at repo root):**
- `OPENROUTER_API_KEY` — required for chat/embeddings/TTS.
- `FIRECRAWL_API_KEY` — required for Search & Research (web).
- DB/Qdrant/RabbitMQ URLs are set by docker-compose for the `app` container.

**The frontend MUST proxy `/api/*` to the backend** (`http://app:8000` inside Docker,
`http://localhost:8000` in local dev). The current setup uses a Next.js rewrite; any
framework works as long as `/api/...` requests reach the backend. Container should serve
on port **3210** (see `docker-compose.yml` `ui` service — keep that contract or update it).

> **Critical proxy rule:** do **NOT** gzip/compress or buffer SSE responses. The backend
> sends `Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no` on every
> streaming endpoint — your proxy/server must preserve streaming (no response
> compression). If SSE is buffered, tokens/steps arrive all at once at the end instead
> of streaming. (Next.js's default `compress: true` broke this; disable compression for
> API routes or rely on `no-transform`.)

---

## 3. Authentication

JWT with short-lived access token + long-lived refresh token.

- `access_token` expires in 15 min, `refresh_token` in 7 days.
- Send `Authorization: Bearer <access_token>` on every authenticated request.
- On `401`, POST the refresh token to `/api/v1/auth/refresh` to get a new pair, then retry.
- Store both tokens client-side (e.g. localStorage keys of your choosing). Clear on logout.

### Endpoints
| Method | Path                          | Body                                            | Returns |
|--------|-------------------------------|-------------------------------------------------|---------|
| POST   | `/api/v1/auth/register`       | `{email, password, full_name?}`                 | `TokenResponse` (201) |
| POST   | `/api/v1/auth/login`          | `{email, password}`                             | `TokenResponse` |
| POST   | `/api/v1/auth/refresh`        | `{refresh_token}`                               | `TokenResponse` |
| POST   | `/api/v1/auth/logout`         | `{refresh_token}`                               | 204 |
| GET    | `/api/v1/auth/oauth/google`   | —                                               | redirect (optional, may be unconfigured) |
| GET    | `/api/v1/auth/oauth/github`   | —                                               | redirect (optional, may be unconfigured) |

`TokenResponse` = `{ access_token: string, refresh_token: string, token_type: "bearer" }`.

Errors return `{ "detail": "<message>" }` with a 4xx status.

**JWT payload** (decodable client-side for display): `sub` (user id), `email`, `exp`.

---

## 4. API reference (non-streaming)

All paths below require the `Authorization` header unless noted. IDs are UUID strings.
Timestamps (`created_at`, `updated_at`) are **Unix seconds (integer)**.

### 4.1 Knowledge Bases — `/api/v1/kb`
| Method | Path            | Body                     | Returns |
|--------|-----------------|--------------------------|---------|
| GET    | `/api/v1/kb/`   | —                        | `KBResponse[]` |
| POST   | `/api/v1/kb/`   | `{name, description?}`   | `KBResponse` (201) |
| DELETE | `/api/v1/kb/{id}` | —                      | 204 |

`KBResponse = { id, name, description, document_count:int, created_at:int, is_system:bool }`

> **System KBs** (`is_system: true`) are read-only, seeded price data. Do not allow
> uploads/deletes on them in the UI (backend returns 403).

### 4.2 Documents — `/api/v1/documents`
| Method | Path                                   | Body / Query                             | Returns |
|--------|----------------------------------------|------------------------------------------|---------|
| GET    | `/api/v1/documents/{kb_id}?limit&offset` | —                                      | `{ total:int, documents: Document[] }` |
| POST   | `/api/v1/documents/upload/{kb_id}`     | multipart `file`; query `chunk_token_num?, chunk_overlap_pct?, table_context_size?` | `IngestJobResponse` (202) |
| POST   | `/api/v1/documents/upload-price/{kb_id}` | multipart `file` (structured price doc) | `IngestJobResponse` (202) |
| DELETE | `/api/v1/documents/{document_id}`      | —                                        | 204 |

`Document = { id, filename, status, chunk_count:int, created_at:int }`
`IngestJobResponse = { job_id, filename, status:"queued" }`

**Ingestion is async** (RabbitMQ). After upload, `status` goes `pending → processing →
done` (or `error`). The UI should **poll** `GET /api/v1/documents/{kb_id}` to reflect
progress. Use `?limit=200` — the price KB alone has ~70 docs and there is no pagination UI.
Max file size is enforced backend-side (returns 400 if exceeded).

### 4.3 Projects — `/api/v1/projects`
A Project bundles multiple KBs so chat retrieves across all of them at once.

| Method | Path                                          | Body                       | Returns |
|--------|-----------------------------------------------|----------------------------|---------|
| GET    | `/api/v1/projects`                            | —                          | `ProjectResponse[]` |
| POST   | `/api/v1/projects`                            | `{name, description?}`     | `ProjectResponse` (201) |
| PATCH  | `/api/v1/projects/{id}`                        | `{name?, description?}`    | `ProjectResponse` |
| PUT    | `/api/v1/projects/{id}/knowledge-bases`        | `{kb_ids: string[]}`       | `ProjectResponse` |
| DELETE | `/api/v1/projects/{id}`                         | —                          | 204 |

`ProjectResponse = { id, name, description, kb_ids:string[], kb_names:string[], created_at:int, updated_at:int }`

### 4.4 Notes — `/api/v1/notes` (personal scratchpad, not chat)
| Method | Path                  | Body                       | Returns |
|--------|-----------------------|----------------------------|---------|
| GET    | `/api/v1/notes`       | —                          | `NoteResponse[]` |
| POST   | `/api/v1/notes`       | `{title?, content?}`       | `NoteResponse` (201) |
| PATCH  | `/api/v1/notes/{id}`  | `{title?, content?}`       | `NoteResponse` |
| DELETE | `/api/v1/notes/{id}`  | —                          | 204 |

`NoteResponse = { id, title, content, created_at:int, updated_at:int }`

### 4.5 Usage — `/api/v1/usage`
| Method | Path              | Returns |
|--------|-------------------|---------|
| GET    | `/api/v1/usage`   | `UsageResponse` |

```
UsageResponse = {
  total_cost_usd, total_duration_ms, total_messages,
  total_prompt_tokens, total_completion_tokens,
  avg_duration_ms, avg_cost_usd,
  daily: [{ date:"YYYY-MM-DD", cost_usd, messages }],   // oldest→newest, ~14 days
  history: [{ id, model, prompt_tokens, completion_tokens, cost_usd, duration_ms, created_at:int }]
}
```
Token counts are real; cost is an estimate from a static per-model table.

### 4.6 Config — `/api/v1/config/skills`
| Method | Path                     | Returns |
|--------|--------------------------|---------|
| GET    | `/api/v1/config/skills`  | `{ skills: SkillMeta[] }` |

`SkillMeta = { id, label, icon, description }`. Skills: `write, learn, code, chill, life`.
A skill sets the assistant's system prompt when passed as `skill_id` to chat.
(There is no `/models` endpoint — the model list is a **frontend constant**, see §7.)

### 4.7 Voice — `/api/v1/voice`
| Method | Path                       | Body                                   | Returns |
|--------|----------------------------|----------------------------------------|---------|
| POST   | `/api/v1/voice/stt?language=vi` | multipart `audio` (webm/wav/mp3)   | `{ text }` |
| POST   | `/api/v1/voice/tts/stream` | `{ text, voice? }` (voice default "alloy") | streamed audio bytes (`audio/wav`) |

STT uses local Whisper (default Vietnamese). TTS streams audio you play via `<audio>`/Web Audio.

### 4.8 Health
`GET /health` → `{status:"ok"}`. `GET /metrics` → Prometheus (ignore in UI).

---

## 5. Streaming endpoints (the core) — SSE format

All three stream **Server-Sent Events**: lines of `data: <json>\n\n`. Because they need the
`Authorization` header, **you cannot use `EventSource`** (it can't set headers). Use
`fetch()` + `response.body.getReader()` and parse lines yourself:

```
POST the JSON body with Authorization header.
Read the ReadableStream, decode UTF-8, split on "\n".
For each line starting with "data: ", JSON.parse the remainder and handle the event.
```

### 5.1 Chat — `POST /api/v1/chat/stream`

**Request body (`ChatRequest`):**
```
{
  message: string,
  conversation_id: string,        // a UUID you generate up front (see §6.1) — enables server history
  kb_id: string | null,           // active KB for RAG
  project_id: string | null,      // if set, retrieval spans all KBs in the project (overrides kb_id)
  model: string | null,           // OpenRouter model id; null → backend default (gpt-4o-mini)
  skill_id: string | null,        // e.g. "write"; sets system prompt
  temperature: number,            // default 0.7
  max_tokens: number,             // default 2048
  use_rag: boolean,               // true when a KB or project is active
  top_k: number,                  // retrieval depth, e.g. 5
  score_threshold: number,        // default 0.5 (relevance floor; below this = no citation)
  mode: "rag" | "agent",          // "agent" lets the LLM call construction-cost tools
  form_submission: null | { form_id: string, data: object }  // human-in-the-loop result, see §6.4
}
```

**SSE events:**
- Token: `{ "type":"text", "delta":"<token>", "done":false }` — append `delta` to the message.
- Final: `{ "type":"text", "delta":"", "done":true, "sources":[...], "rag_context": {...}|null }`
- Form request (intent detected, no answer this turn):
  `{ "type":"form_request", "form_id":"construction_cost", "title":"...", "fields":[...], "prefill":{...}, "done":true }`

`sources` on the final event can be **two shapes mixed**:
- RAG document citation: `{ chunk_id, document_name, content, score }` (score 0..1 → show as %)
- Web citation: `{ url, title }` (or `{url,title,snippet}`)
- Agent tool log (mode:"agent"): `{ name, arguments, result }` — for debugging, not a citation chip.

`rag_context` (final event) = `{ kind: "kb"|"project", name: string }` when the answer used
document data, else `null`. Drives the "RAG · <name>" badge.

### 5.2 Web Search — `POST /api/v1/search/web`

**Request:** `{ query: string, max_results?: number, scrape?: boolean, context?: string }`
- `context` = recent chat turns as plain text (for follow-up resolution, see §6.6).

**SSE events (in order):**
1. `{ "type":"sources", "sources":[{url,title,snippet}], "done":false }` — arrives first.
2. `{ "type":"token", "delta":"<token>", "done":false }` — many; the streamed summary answer.
3. `{ "type":"done", "done":true }`
- Error at any point: `{ "error":"<msg>", "done":true }`.

The answer contains inline citations like `[1]`, `[2]` that map to the `sources` array by
1-based index. Render them as small numbered badges linking to `sources[n-1].url` (see §6.7).

### 5.3 Deep Research — `POST /api/v1/research/stream`

**Request:**
```
{
  query: string,
  max_iterations: number,      // e.g. 2
  max_search_results: number,  // e.g. 6
  quality_threshold: number,   // e.g. 0.75
  search_first: boolean,       // true = quick web search first, seeds the graph
  context: string              // recent chat turns (follow-up resolution)
}
```

**SSE events** — two kinds:

*Step/progress events* (drive a collapsible "thinking" panel + progress bar):
```
{ "node":"<node>", "status":"<status>", "content":"<human text>", "progress":0..1,
  "iteration":int, "sources"?:[{url,title,snippet}] }
```
Nodes appear roughly in this order (accumulate them into a step list):
`start` → `pre_search` (if search_first) → `prompt_expander` → `web_searcher` →
`content_aggregator` → `quality_checker` → `response_generator`.
`status` is `started` / `completed` / `ready`. `progress` climbs 0.0 → ~0.9.

*Answer streaming events* (the final conversational answer, token by token):
- `{ "node":"response_generator", "status":"streaming", "content":"<token>", "progress":0.95, "done":false }`
- `{ "node":"response_generator", "status":"completed", "content":"<full answer>", "sources":[{url,title,snippet}], "progress":1.0, "done":false }`
- `{ "node":"done", "status":"completed", "content":"", "progress":1.0, "done":true }`

**Frontend handling:** route `response_generator/streaming` tokens into the *visible answer*
(append `content`), route every other node event into a *separate step list* (do NOT write
step text into the answer). The answer also uses `[1]`,`[2]` inline citations mapping to the
final `sources`.

---

## 6. Feature flows (end to end)

### 6.1 Conversations & history (important)
- Generate a **real UUID** for `conversation_id` the moment a new chat starts (before the
  first message), e.g. `crypto.randomUUID()`. Reuse it for every turn in that conversation.
- Send it on **every** chat turn (and on form submissions, §6.4). The backend persists each
  turn server-side and injects the **last 10 messages** as context automatically — you do
  **not** send history yourself for chat.
- Keep a client-side conversation list (localStorage is fine) for the sidebar; the server
  stores messages for context/history, keyed by that UUID.

### 6.2 Plain chat
Active KB/project = none → `use_rag:false`. Just stream tokens into the assistant bubble.
Badge: **"Chat thường — không dùng RAG"** (plain). Model/temperature/max_tokens come from
Settings (§7).

### 6.3 RAG chat (document-grounded)
A KB or Project is active → `use_rag:true`, pass `kb_id` or `project_id`.
- On the final event, `sources` holds document chunks `{document_name, score, ...}`.
- Render **citation chips** below the answer: index + `document_name` + `score×100`%.
- Badge logic:
  - If `rag_context` present **and** at least one document citation returned → **"RAG · <name>"**.
  - If a KB/project was active but retrieval returned **no** citations (off-topic question)
    → downgrade to **"Chat thường — không dùng RAG"** (do not falsely credit the KB).
- `score_threshold` (0.5) filters near-noise matches server-side.

### 6.4 Construction-cost tool (human-in-the-loop form)
This is the marquee flow. Sequence:
1. User asks something like *"dự toán giá xây nhà 100m2 ở Hà Nội"*. Backend **intent detection**
   returns a `form_request` event (no answer). The message the user typed **is persisted**
   (so a name mentioned in it survives into history).
2. Frontend renders an **inline form** from the schema:
   - `area_per_floor_m2` (number, required)
   - `num_floors` (number, required, default 1)
   - `region` (select: HN=Hà Nội, DN=Đà Nẵng, HCM=TPHCM, required)
   - `finish_level` (select: tho / hoan_thien_co_ban / hoan_thien_cao_cap, default hoan_thien_co_ban)
   - `prefill` may pre-populate some fields.
3. On submit, POST to `/api/v1/chat/stream` with:
   `{ form_submission: { form_id:"construction_cost", data:{...} }, conversation_id, kb_id }`
   (no `message`).
4. Backend computes the estimate and **streams a conversational answer** (tokens), then a
   final event with `sources` + `rag_context`.
   - Prices found in the **document price DB** → cited as RAG chips (`document_name`, score 1.0 =
     100%, exact structured extraction) and `rag_context` set → **"RAG · Dự toán giá nhà"** badge.
   - Prices missing from the DB → the tool falls back to a **web search**; those show as inline
     `[n]` web citations + a "Nguồn" footer, flagged "giá tham khảo từ web, chưa xác thực".
   - A given estimate can be **mixed** (some RAG chips, some web `[n]`). Badge is RAG if any
     document price was used.
5. The form result is also persisted to history.

> Data coverage note: Hà Nội & Đà Nẵng have full material data (steel/brick/paint/etc.);
> HCM currently has little, so HCM estimates lean on web fallback. This is data, not a UI bug.

### 6.5 Web Search mode
Composer has a **mode switch**: Chat / Search / Research. In Search mode, call
`/api/v1/search/web` (§5.2). Render: streamed summary answer + numbered `[n]` badges +
a sources list. Badge: **"Tìm kiếm web"** (globe icon) — never a RAG badge.

### 6.6 Deep Research mode
Call `/api/v1/research/stream` with `search_first:true`. Render:
- A **collapsible "Research" panel** listing each step as it arrives (label + spinner→check),
  with a **progress %** bar in its header (from `progress`). Open by default while running;
  user can collapse/expand. When the run finishes, all steps show done.
- Suggested step labels (Vietnamese): Bắt đầu / Search trước (context) / Mở rộng câu hỏi /
  Tìm kiếm trên web / Tổng hợp nội dung / Kiểm tra chất lượng / Soạn câu trả lời.
- The **answer streams** token-by-token below the panel (from `response_generator/streaming`).
- Badge: **"Nghiên cứu web"** (globe icon).

### 6.7 Context for Search/Research follow-ups
Before calling Search/Research, build a short `context` string from the **last ~6 messages**
(`"User: ...\nAssistant: ..."`), taken *before* appending the new user message. Pass it as
`context`. The backend resolves follow-ups against it (e.g. "còn ở HCM?" → a full standalone
query). This is why Search/Research stay on-topic across turns.

### 6.8 Voice
1. Record mic audio (`MediaRecorder`, webm) until the user stops.
2. POST the blob to `/api/v1/voice/stt` → get `{text}`.
3. **Auto-send** that text as a normal chat turn (mark it as voice-initiated).
4. When the assistant reply finishes, POST the reply text to `/api/v1/voice/tts/stream` and
   **auto-play** the streamed audio. Show a "speaking" indicator; the spoken audio may not be
   verbatim, so display an indicator rather than promising exact text match.

### 6.9 KB / Documents / Projects / Notes / Usage / Settings
Straightforward CRUD against §4. Key UX:
- Sidebar lists KBs and Projects; keep these in a **shared global store** so creating/deleting
  in a management screen updates the sidebar immediately (don't fetch them separately per view).
- KB detail: list documents with live status (poll while any is `processing`); upload (not on
  system KBs); delete.
- Usage: stat cards (totals/averages) + a simple daily bar chart + a history table.
- Settings: model picker + temperature + max_tokens (see §7).

---

## 7. Settings & model list (frontend-owned)

There is **no backend models endpoint**. Keep a curated constant list of OpenRouter model ids
that are verified to work on this account, grouped by a relative price tier (Budget / Standard /
Premium). A known-good set at time of writing:

```
Budget:   openai/gpt-4o-mini (default), openai/gpt-4.1-mini,
          google/gemini-2.5-flash-lite, meta-llama/llama-3.1-8b-instruct
Standard: openai/gpt-4o, openai/gpt-4.1, google/gemini-2.5-flash
Premium:  anthropic/claude-sonnet-4.5, google/gemini-2.5-pro,
          openai/gpt-5, anthropic/claude-opus-4.1
```
Default model = `openai/gpt-4o-mini`. Selected model is passed as `model` on chat requests
(store it; `null`/unset means backend default). Temperature (0–2) and max output tokens are
also passed per request. These apply to new messages only.

> Many plausible OpenRouter ids 404 on this account — verify before adding new ones.

---

## 8. Message model (client-side) & rendering

Assemble each assistant message from the stream into a shape roughly like:

```
ChatMessage = {
  id, role: "user" | "assistant",
  content: string,                 // accumulated tokens
  streaming?: boolean,
  sources?: Source[],              // from final event (RAG chunks and/or web {url,title})
  ragContext?: { kind:"kb"|"project", name } // → "RAG · name" badge
  webMode?: "search" | "research",  // → "Tìm kiếm web" / "Nghiên cứu web" badge
  pendingForm?: {...form schema...}, // construction-cost form to render inline
  researchSteps?: { node, status, content?, progress? }[], // research panel
  researchProgress?: number,
  viaVoice?: boolean,
}
```

Rendering rules:
- **Markdown**: render assistant content as GitHub-flavored markdown (tables, lists, bold,
  links). BUT **while `streaming` is true, render plain text** (e.g. `white-space: pre-wrap`),
  and only switch to full markdown parsing once streaming ends. Re-parsing the whole markdown
  AST on every token starves the browser's paint loop and makes the answer "pop in" all at
  once instead of streaming. This matters most on long answers.
- **Inline `[n]` citation badges**: post-process the final markdown, replacing a bare `[1]`
  (not followed by `(` — that would be a real link) with a small superscript pill linking to
  the matching web source. Also render a "Nguồn" footer listing the numbered web sources.
- **RAG citation chips**: for sources with `document_name`, render chips: index + name + score%.
- **Badge row** above the answer: RAG (kb/project) > web (search/research) > plain — mutually
  exclusive, per §6.3/§6.5/§6.6.
- **Research panel**: collapsible; header shows current step + progress %; body lists steps with
  a spinner (running) or check (done). Memoize it so it doesn't re-render on every answer token
  (otherwise its animation causes the same paint starvation as above).

Layout gotcha: make `html, body { overflow: hidden }` and let **only the message list scroll**
internally. Otherwise a tall element (like the cost form) pushes the page past 100vh, the body
scrolls too, and you get a double scrollbar + the view jumping on auto-scroll-to-bottom.

---

## 9. Screens (functional, design-agnostic)

Build these however you like visually:
1. **Login / Register** — email+password; store tokens; redirect to chat.
2. **App shell** — collapsible sidebar (nav: Chat, Notes, Projects, Knowledge Base, Usage,
   Settings) + lists of KBs, Projects, and recent conversations; main content area.
3. **Chat** — welcome state (empty) + message list + composer. Composer has: text input,
   mode switch (Chat/Search/Research), a mic/Speak button, and Send. Selecting a KB/Project
   scopes RAG. Messages render per §8.
4. **Knowledge Base** — list KBs; per-KB document list with status + upload + delete
   (system KBs read-only).
5. **Projects** — CRUD; assign KBs to a project.
6. **Notes** — simple title/content CRUD scratchpad.
7. **Usage** — totals, daily chart, history table.
8. **Settings** — model picker (tiers), temperature, max tokens; applies to new messages.

---

## 10. Implementation gotchas checklist

- [ ] SSE via `fetch` + reader, not `EventSource` (need Bearer header).
- [ ] Proxy must not compress/buffer SSE (preserve `no-transform`; disable gzip on `/api`).
- [ ] Plain text while streaming; full markdown only when done.
- [ ] `conversation_id` = real UUID, generated up front, sent every turn (incl. form submit).
- [ ] Badge precedence: RAG (only if real citations) → web (search/research) → plain.
- [ ] Inline `[n]` → citation badges; RAG `document_name` → chips with score%.
- [ ] Research: split step events (panel) from answer tokens (bubble); progress bar; memoize panel.
- [ ] `html,body{overflow:hidden}`, only the message list scrolls.
- [ ] Shared global store for KBs/Projects so the sidebar stays in sync.
- [ ] Poll document status after upload until `done`/`error`.
- [ ] Refresh-token retry on 401.
- [ ] Model list is a frontend constant; default `openai/gpt-4o-mini`.

---

*This guide is derived solely from the backend's public API behavior and generic UX patterns.
It contains no proprietary UI code or design. Build the new frontend originally from here.*
