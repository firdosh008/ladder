# Ladder Content OS — Handoff / Context Doc

Last updated: 2026-04-25. Purpose: bring a fresh Claude session (or a human contributor) up to speed without re-reading the whole chat history.

---

## 1. What this project is

**Ladder Content OS** — a video production assistant for founder-operators. The loop it automates:

> rough idea → script → Excalidraw scene → Loom recording → thumbnail → post.

The product thesis: don't press "generate". Build a workflow that *ladders* a founder's raw thoughts into a publishable video while keeping their voice. Heavy emphasis on voice-match, brand consistency, and a knowledge graph of the founder's own content as retrieval context.

See `backend-dys.md` for the full data-layer spec (source of truth — read it) and `design-sys.md` for visual language.

---

## 2. Stack

### Frontend
- Vite + React 18 + TypeScript
- React Router v6
- Tailwind (custom tokens in `tailwind.config.js` — cinnabar `#E8442A`, bone, night, etc.)
- framer-motion for animation
- @phosphor-icons/react for icons
- @supabase/supabase-js v2 for auth + data (browser-side)
- Fonts: Playfair Display (display), Geist (body), JetBrains Mono (data)

### Backend
- FastAPI on Python 3.11–3.13 (pinned `<3.14` — pyo3 in `pydantic-core` doesn't support 3.14 yet)
- uv for package management, `.python-version` pins to 3.12
- pydantic-settings for config
- supabase-py for Postgres access (two-client pattern)
- python-jose[cryptography] for JWT verification via Supabase's JWKS
- httpx for the JWKS fetch + any outbound LLM calls
- Native FastAPI WebSockets for streaming agent runs to the UI
- **AI stack:** CrewAI (multi-agent orchestration), Anthropic SDK (`claude-sonnet-4-6` as default via CrewAI's LLM factory), OpenAI SDK (reserved for embeddings), `exa-py` for neural web search

### Data
- Supabase (Postgres + pgvector + Auth + Storage + RLS)
- 16 tables, all RLS-protected, all user-scoped via `user_id`
- pgvector `embedding vector(1536)` on `knowledge_nodes`
- Retrieval RPC `match_knowledge_nodes(query_user_id, query_embedding, match_count)` — **explicit user_id filter before similarity ordering** (defense in depth even under service role)

---

## 3. Key architectural decisions (do not violate)

1. **Every user-scoped table has `user_id uuid NOT NULL` with `ON DELETE CASCADE` to `auth.users`.** No exceptions. Even join tables (idea_tags) enforce ownership via subquery policies.
2. **RLS is on for every table**, enforced via `user_id = auth.uid()` (plus a self-select policy on `users`). Backend must never disable RLS casually.
3. **Two-client Supabase pattern:**
   - `service_client()` — cached, uses service role key, bypasses RLS. Only for explicit admin ops or pgvector RPC with explicit `user_id` filter.
   - `user_client(jwt)` — authenticated with the user's JWT, honors RLS. **Use this for every user-scoped query.**
4. **JWT verification via JWKS, not HS256 shared secret.** Supabase has migrated to asymmetric ES256 signing. Backend fetches `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, caches 10 min, verifies with the JWK matching `kid`. See `backend/app/middleware/auth.py`.
5. **`handle_new_user()` trigger on `auth.users` bootstraps `public.users` + `public.user_profiles` rows.** Without this, first API call after signup will 500 trying to satisfy FKs. Verified working as of 2026-04-23.
6. **Retrieval always passes explicit `user_id`.** The `match_knowledge_nodes` RPC filters `WHERE user_id = query_user_id` *before* similarity — RLS is the second layer, not the first.
7. **WebSockets auth via `?token=<jwt>` query param**, verified with the same JWKS cache as HTTP routes (`app/middleware/ws_auth.py`). Browsers cannot set `Authorization` on `new WebSocket()`, so the query param is the only viable channel. Close codes: `4401` unauthorized, `4400` bad request, `1011` server error.
8. **Every agent run writes exactly one `usage_log` row** via the `log_usage()` async context manager (`app/services/usage.py`) with `function_name`, `model`, `provider`, token counts, latency, and cost. This is non-negotiable — it's how we'll bill BYOK later.
9. **Every LLM is constructed through `services/llm.py`**, never inline. That's the single place where model ID, provider, and API key get bound. When BYOK lands in v2, only this factory changes.

---

## 4. Repo layout

```
ladder-os/
├── backend/
│   ├── app/
│   │   ├── main.py                       # FastAPI app + CORS + routers
│   │   ├── config.py                     # pydantic-settings (reads backend/.env)
│   │   ├── deps.py                       # service_client + user_client factories
│   │   ├── middleware/
│   │   │   ├── auth.py                   # HTTP JWT (JWKS) — current_user dep
│   │   │   └── ws_auth.py                # WebSocket JWT verification (?token=)
│   │   ├── models/
│   │   │   └── db.py                     # Pydantic mirrors (UserProfileSlice, IdeaDraft, ResearchIdeas)
│   │   ├── providers/
│   │   │   └── exa.py                    # async wrapper around exa-py neural search
│   │   ├── services/
│   │   │   ├── llm.py                    # anthropic_llm() — CrewAI LLM factory
│   │   │   └── usage.py                  # log_usage() async context manager
│   │   ├── agents/
│   │   │   └── research/
│   │   │       ├── tools.py              # ExaSearchTool (CrewAI BaseTool)
│   │   │       ├── agents.py             # 3 agents (researcher / scorer / architect)
│   │   │       ├── tasks.py              # sequential task pipeline
│   │   │       └── crew.py               # run_research() async generator
│   │   └── routes/
│   │       ├── health.py                 # GET /health
│   │       ├── auth.py                   # GET /auth/me, POST /auth/onboard
│   │       ├── ideas.py                  # GET/POST/PATCH/DELETE /ideas
│   │       └── agents.py                 # WebSocket /ws/agents/research
│   ├── tests/                            # pytest-asyncio + httpx + starlette TestClient
│   ├── pyproject.toml
│   ├── .python-version                   # 3.12 (pyo3/pydantic-core 3.14 pin)
│   ├── .env                              # gitignored, filled
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.tsx                       # Router + AuthProvider + RequireAuth guards
│   │   ├── lib/
│   │   │   ├── supabase.ts               # createClient with VITE_ env vars
│   │   │   ├── auth.tsx                  # AuthProvider, useAuth, RequireAuth
│   │   │   ├── api.ts                    # fetch wrapper injecting Supabase access token
│   │   │   ├── useIdeas.ts               # ideas hook (list/create/update/delete + refresh)
│   │   │   ├── agents.ts                 # runResearchStream() WebSocket client
│   │   │   ├── motion.ts                 # fadeUp/stagger presets
│   │   │   └── cn.ts
│   │   ├── components/
│   │   │   ├── research/
│   │   │   │   └── ResearchStreamDrawer.tsx   # live agent timeline + idea cards
│   │   │   ├── studio/StudioSetupDialog.tsx
│   │   │   ├── kanban/                   # Videos.tsx board
│   │   │   ├── ui/                       # Button, Badge, Input, Card, ...
│   │   │   └── app/Shell.tsx             # layout shell
│   │   ├── pages/
│   │   │   ├── Auth.tsx                  # WORKS
│   │   │   ├── Onboarding.tsx            # WORKS (wired to /auth/onboard)
│   │   │   ├── Make.tsx                  # PARTIAL — research option is live; extract is dummy
│   │   │   ├── Videos.tsx                # WORKS (Kanban on ideas)
│   │   │   ├── Library.tsx               # DUMMY
│   │   │   ├── Settings.tsx              # PARTIAL — Profile tab works, others dummy
│   │   │   └── Studio.tsx                # DUMMY
│   │   └── vite-env.d.ts
│   ├── .env                              # gitignored, filled with VITE_SUPABASE_*
│   └── .env.example
├── supabase/
│   └── migrations/
│       ├── 20260423000001_init.sql          # tables + trigger
│       ├── 20260423000002_rls_policies.sql  # RLS on everything
│       ├── 20260423000003_indexes.sql       # performance
│       └── 20260423000004_match_function.sql# pgvector RPC
├── backend-dys.md              # data layer spec (read this)
├── design-sys.md               # visual language
└── HANDOFF.md                  # this file
```

---

## 5. What's built and verified working

### Platform
- [x] All 16 tables in Supabase, RLS enabled on each. Verified 2026-04-23.
- [x] `handle_new_user()` trigger fires on signup — creates `public.users` + `public.user_profiles` rows (confirmed: `user_profiles` has rows for signups, all other fields NULL as expected).
- [x] `match_knowledge_nodes` RPC + indexes deployed.
- [x] Backend FastAPI scaffold with CORS.
- [x] Backend JWKS-based HTTP JWT middleware (`current_user` dependency).
- [x] Backend JWKS-based WebSocket auth (`verify_ws_token`, `?token=` query param, shared JWKS cache with HTTP).
- [x] `service_client()` / `user_client(jwt)` pattern in `deps.py`.

### Auth + onboarding
- [x] Frontend landing page (`/`) — Landing.tsx + all section components.
- [x] Frontend auth page (`/auth`) — email/password signup + signin + Google OAuth. Sends confirmation email; redirects to `/onboarding` after confirm.
- [x] `RequireAuth` guard redirects unauthenticated users to `/auth` with `state.from`; unboarded users bounced to `/onboarding`.
- [x] Frontend `lib/supabase.ts`, `lib/auth.tsx` (AuthProvider/useAuth), `lib/api.ts` (token-injecting fetch wrapper).
- [x] Backend `GET /health`, `GET /auth/me`, `POST /auth/onboard` — fully wired; `/auth/me` self-heals missing public rows.
- [x] `Onboarding.tsx` form → `POST /auth/onboard` → `flushSync` profile commit → navigate `/make`.
- [x] `Settings.tsx` Profile tab reads + upserts `user_profiles` via the same endpoint.

### Ideas
- [x] Backend `GET/POST/PATCH/DELETE /ideas` with auto-position (tail of `status` column).
- [x] Frontend `useIdeas()` hook — optimistic updates, `refresh()` exposed.
- [x] `Videos.tsx` Kanban board (add, drag to reorder/move, delete cards).

### AI — Research vertical (first crew, 2026-04-25)
- [x] Shared agent foundation: `providers/exa.py`, `services/llm.py`, `services/usage.py`, `middleware/ws_auth.py`, `models/db.py`.
- [x] `backend/app/agents/research/` — `ExaSearchTool` + three-agent crew (trend researcher, outlier scorer, idea architect) producing `ResearchIdeas` via `output_pydantic`.
- [x] `run_research()` async generator — wraps the crew in `log_usage(...)`, bridges CrewAI's threaded `step_callback` / `task_callback` into an `asyncio.Queue`, yields wire events.
- [x] `POST` equivalent: `WebSocket /ws/agents/research?token=...&topic=...` — verifies JWT, loads profile, streams events, persists each idea into `ideas` with `source_type="research"`, `status="new"`, tail-of-column positioning.
- [x] Make page rewired: research option opens `ResearchStreamDrawer` (live agent timeline + idea cards popping in); `refresh()` fires on close.
- [x] Dummy removed from Make page: hardcoded "4.2× trending" banner deleted; hardcoded alias replaced with `profile.forwarding_alias`; "keys · 3/4 configured" deleted.
- [x] Tests (`tests/test_research_crew.py`, 10 cases): Exa tool JSON shape, event mappers, Pydantic bounds, WS close codes, full streaming happy path with 3 persisted ideas, cross-user isolation (user A's JWT never produces a row with user B's `user_id`, even if drafts try).
- [x] Full backend test suite: **38 passing, 0 failing** (`uv run pytest -q`).

---

## 6. What's NOT built yet — priority-ordered backlog

### P0 — finish the Make → Studio → Videos loop
1. **Studio sessions CRUD** — backend `GET/POST/PATCH /studio-sessions` + wire to `Studio.tsx`. Still fully dummy (hardcoded `SCRIPT`, `OUTLINE`, `CHAT_SEED`).
2. **Script + Scene crews** — Studio's outline generator and scene breakdown. First consumers of `match_knowledge_nodes` (retrieval lands here). Reuse the LLM factory, `log_usage`, and WS event protocol from the Research crew.
3. **Content-extract crew** — Make page option 3 ("Turn content into a video"). Currently still dummy — the `intent.kind === "extract"` branch just navigates to `/studio/extract?...` which doesn't exist.
4. **Sharpen crew** — Studio chat sidebar. Small streaming crew that rewrites script sections on request.

### P1 — knowledge + retrieval
5. **Embedding pipeline** — OpenAI `text-embedding-3-small` (1536 dims) writes to `knowledge_nodes`. Triggered on new newsletter_items, ideas, artifacts. OpenAI SDK is already installed.
6. **Retrieval agent** — calls `match_knowledge_nodes` RPC with explicit `user_id`, feeds results into Script/Scene crews.
7. **Newsletter ingestion** — `sources` + `newsletter_items` + forwarding alias flow. `user_profiles.forwarding_alias` already surfaces in the Make page.

### P1 — still-dummy surfaces
8. **Projects + brands CRUD** — simple tables, used by sessions. Settings → Brands tab is dummy.
9. **Library.tsx** — all four tabs (What I know / Knowledge graph / Sources / Insights) are placeholder.
10. **Settings.tsx** — only Profile works; Brands/Models/Skill files/Integrations tabs are dummy.

### P1 — ancillary
11. **YouTube metrics fetcher** — `yt_metrics` table is empty; needs YouTube Data API wiring + background refresh.
12. **Storage flows** — image uploads (thumbnails, chat images, excalidraw exports) into Supabase Storage; update `*_storage_path` columns on relevant rows.
13. **BYOK via Supabase Vault** — per `backend-dys.md`; swap the server-default keys in `services/llm.py` for per-user Vault reads.

### P2 — polish
14. Magic link or passkey as alternate auth path.
15. `/auth/callback` route if we move away from `emailRedirectTo` pointing at `/onboarding` directly.
16. Proper error boundaries and toast UI (Make page already surfaces crew errors in the drawer, but there's no global toast yet).
17. Real cost accounting in `usage_log` — today we use a flat Sonnet price map in `crew.py`. When CrewAI surfaces per-provider token details cleanly, replace with actuals.

---

## 7. Local run (fresh terminal)

### Backend
```bash
cd ladder-os/backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
# verify: curl http://localhost:8000/health → {"status":"ok"}
# swagger UI: http://localhost:8000/docs
```

### Frontend
```bash
cd ladder-os/frontend
npm install
npm run dev
# http://localhost:5173
```

### Environment files (already filled, gitignored)
- `backend/.env` — `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `CORS_ORIGINS`. **No JWT secret needed** (JWKS verification). Old `SUPABASE_JWT_SECRET` line can stay unused.
  - **Required to run any agent vertical:** `ANTHROPIC_API_KEY`, `EXA_API_KEY`. The factories intentionally raise `RuntimeError` on missing keys rather than silently falling back to a cheaper provider.
  - Optional: `ANTHROPIC_MODEL` (default `claude-sonnet-4-6`), `OPENAI_API_KEY` (for embeddings, not used yet).
- `frontend/.env` — `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL=http://localhost:8000`. The frontend derives the WebSocket base URL from `VITE_API_URL` (`http://` → `ws://`, `https://` → `wss://`).

---

## 8. Supabase dashboard config (done, but documented in case of reset)

- **Authentication → URL Configuration → Site URL:** `http://localhost:5173`
- **Authentication → URL Configuration → Redirect URLs:** `http://localhost:5173/**`
- **Authentication → Providers → Google:** enabled with Client ID/Secret from Google Cloud Console. Google OAuth client has:
  - JavaScript origins: `https://lqjlfuhucwgsxerulqlf.supabase.co`
  - Redirect URIs: `https://lqjlfuhucwgsxerulqlf.supabase.co/auth/v1/callback`

Project ref: `lqjlfuhucwgsxerulqlf`.

---

## 9. Known gotchas

1. **Vite env vars require the `VITE_` prefix and a dev server restart after editing `.env`.** Otherwise you get a white screen + console warning from `supabase.ts`.
2. **Supabase CLI migration files need timestamp prefixes** (`20260423000001_*.sql`), not sequential `0001_*.sql`. Already renamed.
3. **JWT Signing Keys vs Legacy JWT Secret:** project has migrated to ES256. Backend uses JWKS, not the legacy shared secret. Don't revert to HS256.
4. **`emailRedirectTo` in `signUp` must be in Supabase's Redirect URL allow list** or confirmation emails bounce.
5. **Anthropic model IDs (as of 2026-01):** Opus 4.7 = `claude-opus-4-7`, Sonnet 4.6 = `claude-sonnet-4-6`, Haiku 4.5 = `claude-haiku-4-5-20251001`. Default to latest.
6. **Python must be 3.11–3.13.** `pydantic-core` currently builds via `pyo3 0.24.1` which doesn't support Python 3.14. `backend/pyproject.toml` has `requires-python = ">=3.11,<3.14"` and `backend/.python-version` pins to `3.12`. If `uv sync` ever tries to build pyo3 for 3.14, delete `.venv` and re-sync.
7. **CrewAI step/task callbacks run in a worker thread.** Never call `await` inside them. Push events onto an `asyncio.Queue` via `loop.call_soon_threadsafe(queue.put_nowait, event)` (see `app/agents/research/crew.py`).
8. **WebSockets auth is `?token=<jwt>`**, never a header. Browsers can't set `Authorization` on `new WebSocket()`. The server verifies via the same JWKS cache as HTTP routes. Close codes: 4401 (bad token), 4400 (bad params), 1011 (server error).
9. **Agent verticals follow a fixed shape.** When adding a new crew (Script, Scene, Sharpen, ...): put it under `app/agents/<name>/`, use `anthropic_llm()` from `services/llm.py`, wrap the run in `log_usage(..., function_name="<crew>_crew")`, expose via `/ws/agents/<name>`, emit events matching the protocol in §11 below. Do not deviate — the frontend drawer is generic over the event shape.

---

## 10. What to do next session (suggested first task)

**Ship the Studio vertical: Script + Scene crews backed by the knowledge graph.**

This is the next high-leverage slice because it:
- unblocks the core loop (Make → Studio → Videos),
- is the first consumer of `match_knowledge_nodes` (so it forces the embedding pipeline to land), and
- reuses every abstraction the Research vertical already shipped (LLM factory, `log_usage`, WS auth, event protocol, drawer).

Rough shape:
1. Backend `routes/studio_sessions.py` — `GET/POST/PATCH /studio-sessions` + `GET /studio-sessions/:id/artifacts` (same CRUD pattern as `ideas.py`).
2. Embedding pipeline: trigger on new `newsletter_items`, `ideas`, `artifacts` rows → chunk → `text-embedding-3-small` → `knowledge_nodes` with explicit `user_id` + `source_type` / `source_id`.
3. `app/agents/script/` — Retrieval agent (calls `match_knowledge_nodes` via `service_client` with the user_id from the verified JWT) → Outline agent → Script writer. Structured `output_pydantic` for each stage.
4. `WebSocket /ws/agents/script?token=...&idea_id=...` — same event protocol as the research WS. Stream outline first, then scene cards, persist into `studio_sessions` + `artifacts`.
5. Frontend: replace the hardcoded `SCRIPT` / `OUTLINE` / `CHAT_SEED` in `Studio.tsx` with a generic version of `ResearchStreamDrawer` — the component is already shaped around the event protocol and should be easy to extract into `components/agents/AgentStreamDrawer.tsx`.

The Research vertical is the template. Copy its structure file-for-file.

---

## 11. Agent event protocol (reference)

Every `/ws/agents/*` endpoint emits events in this shape. The frontend drawer is generic over it.

```json
{"type": "agent_start",   "agent": "search_agent"}
{"type": "tool_call",     "tool":  "web_search", "query": "...", "agent": "search_agent"}
{"type": "tool_result",   "preview": "...", "agent": "search_agent"}
{"type": "agent_step",    "agent": "...", "preview": "..."}
{"type": "task_complete", "agent": "...", "preview": "..."}
{"type": "ideas_ready",   "ideas": [...], "token_usage": {"input": 0, "output": 0, "cost_usd": 0.0}}
{"type": "idea_saved",    "idea":  {"id": "...", "title": "...", "opportunity_score": 87}}
{"type": "complete",      "saved":  4, "cost_usd": 0.07}
{"type": "error",         "message": "..."}
```

`ideas_ready` / `idea_saved` are Research-specific names — for the Script vertical swap in `outline_ready` / `section_saved`, etc. Keep `agent_start`, `tool_call`, `tool_result`, `agent_step`, `task_complete`, `complete`, and `error` identical so the drawer renders the timeline without changes.
