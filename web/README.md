# Cốt — frontend

A fresh Next.js 15 (App Router) + React 19 frontend for the Agentic RAG
construction-materials assistant, built on the **Cốt** design system. Written
from the backend API contracts only — independent of the old `../frontend`.

## Run

```bash
# local dev (proxies /api/* → http://localhost:8000 by default)
npm install
npm run dev            # http://localhost:3210

# point at a different backend
API_PROXY_TARGET=http://localhost:8000 npm run dev
```

In Docker, `docker-compose.yml`'s `ui` service builds this directory and sets
`API_PROXY_TARGET=http://app:8000`.

## How it's wired

- **`/api/*` proxy** — `next.config.mjs` rewrites to `API_PROXY_TARGET`, with
  `compress:false` so SSE token streams are never buffered/gzipped.
- **Auth** — `lib/api.ts` adds the Bearer token and does a one-shot
  refresh-and-retry on 401; tokens live in localStorage (`lib/auth.ts`).
- **Streaming** — `lib/sse.ts` reads the `fetch` body stream (EventSource can't
  set headers) and parses `data:` frames. `ChatView` routes chat / search /
  research events per the backend's SSE shapes.
- **State** — `lib/store.ts` (Zustand) holds KBs, projects, conversations, and
  settings so the sidebar stays in sync across screens.
- **Design system** — tokens + primitives in `app/globals.css`, layout in
  `app/ui.css`. Cobalt = brand / grounded RAG data; amber = web / unverified.

## Structure

```
app/            routes (auth, chat, kb, projects, notes, usage, settings)
components/      Shell, Sidebar, chat/* (ChatView, Composer, MessageBubble, …)
lib/            api, sse, auth, store, types, models, format
```
