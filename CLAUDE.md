# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

### Frontend (Vite + React 18 + TypeScript)

```bash
cd frontend
npm run dev          # Start dev server on port 5173
npm run build        # TypeScript check + Vite production build
npm run typecheck    # tsc --noEmit only (no build)
```

No test runner is configured for the frontend.

**Frontend env** — set `VITE_API_URL` in `frontend/.env` (defaults to `http://localhost:8000`).

### Backend (FastAPI + Python 3.11+)

```bash
cd backend
# Run dev server — copy .env.example to .env and fill in required keys
uvicorn app.main:app --reload --port 8000

# Tests (pytest with asyncio auto-mode; conftest.py sets mock env vars)
pytest
pytest tests/test_research_crew.py -v       # single file, verbose
pytest -k "test_studio"                     # keyword filter

# Lint/format
ruff check .
ruff format --check .
mypy app/
```

**Required env vars** (`backend/.env`): `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `ANTHROPIC_API_KEY`.

**Optional provider keys**: `OPENAI_API_KEY` (scene hero images + thumbnails), `GOOGLE_API_KEY`, `EXA_API_KEY`, `SCRAPECREATORS_API_KEY`.

**One-time vendor setup** (for MCP Excalidraw canvas + headless PNG export):
```bash
cd backend/vendor/mcp_excalidraw && npm install && npm run build
cd backend/excalidraw_headless && npm install && npx playwright install chromium
```

### Supabase

```bash
supabase link --project-ref <ref>
supabase db push
```

Migrations are in `supabase/migrations/` — apply in numerical order. The `handle_new_user` trigger in `0001_init.sql` propagates `auth.users → public.users` on signup.

## Architecture

Ladder Content OS is an AI-powered video content studio. A founder researches a topic, the system generates a script and scene outline, then renders a visual Excalidraw scene. All via WebSocket-streamed CrewAI agent crews.

### Stack

- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, Radix UI, react-router-dom v6, Supabase JS client, @excalidraw/excalidraw
- **Backend:** FastAPI (Python), CrewAI agent framework, Anthropic SDK (direct + via CrewAI's litellm wrapper), Supabase Python client
- **Database:** Supabase (Postgres + pgvector) with Row-Level Security (RLS) on all content tables
- **Auth:** Supabase Auth (JWT) — verified server-side against JWKS; WS auth via `?token=` query param
- **Diagram rendering:** Local MCP Excalidraw canvas (`backend/vendor/mcp_excalidraw`) — spawned as a Node subprocess at boot

### Key architectural patterns

**Dual Supabase client pattern** (see `backend/app/deps.py`):
- `service_client()` — service-role key, bypasses RLS. Use only for `usage_log` writes, `match_knowledge_nodes` RPC, and Storage uploads.
- `user_client(jwt)` — user-scoped, honors RLS. Use for every user-content read/write. Never add manual `.eq("user_id", ...)` filters in routes — RLS enforces ownership.

**Dual LLM path** (see `backend/app/services/llm.py`):
- `anthropic_llm()` — CrewAI `LLM` (litellm wrapper). Used for simple schemas (Script, Outline, ResearchIdeas) where `output_pydantic`'s prompted JSON is reliable.
- `anthropic_client()` — raw `AsyncAnthropic` SDK. Used for structured outputs (grammar-constrained JSON via `output_format`) needed for large nested schemas like `SceneSkeleton`, and for vision-capable calls.

**WebSocket streaming** — all agent runs are WS-based:

| Endpoint | Crew | Persists? |
|---|---|---|
| `/ws/agents/research` | Research: web search + idea drafts | No (frontend POSTs accepted drafts to `/ideas`) |
| `/ws/agents/studio` | Studio: script_writer → outline_planner | Yes — upserts studio_sessions row + script/outline artifacts |
| `/ws/agents/extract` | Content extract: pasted source → full idea + script + outline | Yes — creates idea + session + all artifacts in one transaction |
| `/ws/agents/scene` | Scene: layout_planner → element_designer → Excalidraw skeleton | Yes — writes versioned `excalidraw` artifact |
| `/ws/agents/chat` | Chat: conversational refinement, `patch_scene`/`patch_script` tool use | Chat messages persisted; patches create new artifact versions |
| `/ws/agents/thumbnail` | Thumbnail: DALL-E / GPT Image prompt → N variants via OpenAI Images API | Yes — writes PNG artifacts to Storage |

All streams share an AgentEvent protocol (see `backend/app/routes/agents.py` docstring or `frontend/src/lib/agents.ts` `AgentEvent` type).

**Agent crew structure** (in `backend/app/agents/`):
- Standard crews = `agents.py` (CrewAI Agent definitions) + `tasks.py` (CrewAI Task definitions) + `crew.py` (orchestrator). Crews run sequentially (`Process.sequential`) with `stream=True`.
- Research and Scene crews use tools (`backend/app/agents/research/tools.py`); Studio crew does not.
- **Chat crew** is a single file (`crew.py`) — no CrewAI. Uses `anthropic_client()` directly with tool use (patch_scene, patch_script). Supports vision mode when `image_base64` is passed.
- **Thumbnail crew** is a single file (`crew.py`) — no CrewAI. Uses `AsyncAnthropic` to analyze a reference thumbnail, then `AsyncOpenAI` to generate N image variants. Does NOT use `output_pydantic` or CrewAI tasks.

**Data model** (see `backend/app/models/db.py`):
- Structured outputs (`Script`, `Outline`, `SceneSkeleton`, `ExtractedVideo`, `ResearchIdeas`) are Pydantic models used as `output_pydantic` on CrewAI tasks
- `SceneSkeleton` elements map 1:1 to `@excalidraw/excalidraw`'s `ExcalidrawElementSkeleton` — the frontend passes `scene.elements` directly to `convertToExcalidrawElements()` with no translation

**Artifacts versioning**: Script, outline, and excalidraw artifacts are stored as versioned rows in the `artifacts` table (Supabase). Each write increments version. The frontend can save founder edits as new versions via REST endpoints (`POST /studio-sessions/{id}/outline`, etc.).

**Kanban board**: The `/make` page displays ideas as a kanban (`frontend/src/components/kanban/`) using `@dnd-kit/core` for drag-and-drop, with position tracking persisted via `ideas.position`.

### RLS + Auth

All content tables have RLS policies (see `supabase/migrations/0002_rls_policies.sql`). The backend's `current_user` dependency verifies the Supabase JWT and returns `(user_id, raw_jwt)` — the raw JWT is passed to `user_client()` to build a Supabase client that honors RLS. WebSocket routes use `verify_ws_token(token)` for the same verification.

### Excalidraw canvas

The backend manages a local Node.js Express server (`backend/vendor/mcp_excalidraw`) that provides an HTTP API for Excalidraw operations. It's auto-started at boot (configurable via `EXCALIDRAW_CANVAS_AUTOSTART`). A Playwright headless browser (`EXCALIDRAW_HEADLESS_AUTOSTART`) enables PNG export without a human browser.

### Frontend routing

```
/                    Landing page (public)
/auth, /auth/callback, /auth/reset-password  Auth pages (public)
/onboarding          Creator profile setup (auth required)
/make                Kanban idea board + research (auth + onboarded)
/library             Saved/accepted ideas
/videos              Published videos
/settings            User settings
/studio/:id          AI studio workspace for one idea
/studio              New studio (no idea yet)
```

`RequireAuth` wraps all authenticated routes; `AuthProvider` manages session + profile state via React context.
