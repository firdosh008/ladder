# Ladder Backend

FastAPI + Supabase. Python 3.11+.

## Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# fill in Supabase keys
uvicorn app.main:app --reload --port 8000
```

## Routes

- `GET  /health` — liveness.
- `GET  /auth/me` — current user + profile. Requires `Authorization: Bearer <jwt>`.
- `POST /auth/onboard` — write profile + mark onboarded_at.

## Architecture

See `../backend-dys.md` for the full spec — data layer, RLS rules, pgvector
retrieval, usage logging, BYOK, cross-user isolation test. Everything here is
built to satisfy those cardinal rules.

## Excalidraw MCP canvas (optional)

Studio can render scenes via the vendored [`mcp_excalidraw`](vendor/mcp_excalidraw)
server instead of the CrewAI planner path.

```bash
cd vendor/mcp_excalidraw
npm install
npm run build
npx playwright install chromium   # needed for PNG export / headless tab
```

Set `ENABLE_MCP_SCENE_DIAGRAM=true` and configure `EXCALIDRAW_*` vars in `.env`
(see `.env.example`). REST `POST /generate-diagram` uses the same canvas HTTP API.

When `EXCALIDRAW_CANVAS_AUTOSTART=true` (default), **uvicorn starts the canvas**
(and Playwright headless when `EXCALIDRAW_HEADLESS_AUTOSTART=true`) during API
lifespan — no separate terminal unless autostart is disabled or boot fails.
On Windows the canvas subprocess inherits the API console (required by asyncio).
