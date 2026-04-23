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
