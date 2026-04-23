# Ladder Content OS — Handoff / Context Doc

Last updated: 2026-04-23. Purpose: bring a fresh Claude session (or a human contributor) up to speed without re-reading the whole chat history.

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
- FastAPI on Python 3.11+
- uv for package management
- pydantic-settings for config
- supabase-py for Postgres access (two-client pattern)
- python-jose[cryptography] for JWT verification via Supabase's JWKS
- httpx for the JWKS fetch + any outbound LLM calls

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

---

## 4. Repo layout

```
ladder-os/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + CORS + routers
│   │   ├── config.py            # pydantic-settings (reads backend/.env)
│   │   ├── deps.py              # service_client + user_client factories
│   │   ├── middleware/auth.py   # JWKS-based JWT verification
│   │   └── routes/
│   │       ├── health.py        # GET /health
│   │       └── auth.py          # GET /auth/me, POST /auth/onboard
│   ├── pyproject.toml
│   ├── .env                     # gitignored, filled
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Router + AuthProvider + RequireAuth guards
│   │   ├── lib/
│   │   │   ├── supabase.ts      # createClient with VITE_ env vars
│   │   │   ├── auth.tsx         # AuthProvider, useAuth, RequireAuth
│   │   │   ├── motion.ts        # fadeUp/stagger presets
│   │   │   └── cn.ts
│   │   ├── components/          # Landing + Hero + Nav + CTA + sections
│   │   ├── pages/
│   │   │   ├── Auth.tsx         # WORKS — signup/signin/Google OAuth
│   │   │   ├── Onboarding.tsx   # DUMMY — not wired to backend
│   │   │   ├── Make.tsx         # DUMMY
│   │   │   ├── Videos.tsx       # DUMMY
│   │   │   ├── Library.tsx      # DUMMY
│   │   │   ├── Settings.tsx     # DUMMY
│   │   │   └── Studio.tsx       # DUMMY
│   │   └── vite-env.d.ts
│   ├── .env                     # gitignored, filled with VITE_SUPABASE_*
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

- [x] All 16 tables in Supabase, RLS enabled on each. Verified 2026-04-23.
- [x] `handle_new_user()` trigger fires on signup — creates `public.users` + `public.user_profiles` rows (confirmed: `user_profiles` has rows for signups, all other fields NULL as expected).
- [x] `match_knowledge_nodes` RPC + indexes deployed.
- [x] Frontend landing page (`/`) — Landing.tsx + all section components.
- [x] Frontend auth page (`/auth`) — email/password signup + signin + Google OAuth button. Sends confirmation email; redirects to `/onboarding` after confirm.
- [x] `RequireAuth` guard redirects unauthenticated users to `/auth` with `state.from` for post-login bounce-back.
- [x] Frontend `lib/supabase.ts` + `lib/auth.tsx` (AuthProvider, useAuth hook, session lifecycle).
- [x] Backend FastAPI scaffold with CORS.
- [x] Backend JWKS-based JWT middleware (`current_user` dependency).
- [x] Backend `GET /health`, `GET /auth/me`, `POST /auth/onboard`.

---

## 6. What's NOT built yet — priority-ordered backlog

### P0 — unblock onboarding
1. **Wire `Onboarding.tsx` to `POST /auth/onboard`.** Form should collect display_name, positioning, audience, voice, creators_followed[], things_to_avoid, then call backend with `Authorization: Bearer <session.access_token>`. On success → navigate to `/make`.
2. **Wire `Settings.tsx` read/write of `user_profiles`** (same shape; editable post-onboarding).
3. **Add a frontend `api` helper** — thin fetch wrapper that auto-injects the Supabase access token from the current session. Use it for every backend call.

### P1 — ingestion surfaces (currently all dummy)
4. **Ideas CRUD** — backend routes `GET/POST/PATCH/DELETE /ideas` + wire to `Make.tsx` / `Library.tsx`.
5. **Studio sessions CRUD** — backend `GET/POST/PATCH /studio-sessions` + wire to `Studio.tsx`. This is the core workflow (idea → outline → excalidraw → thumbnail).
6. **Projects + brands CRUD** — simple tables, used by sessions.
7. **Sources (newsletters, etc.)** + `newsletter_items` ingestion route (later — requires forwarding alias setup).

### P1 — agents
8. **First agent: outline generator** for studio sessions. Uses Anthropic (Claude Opus 4.7 or Sonnet 4.6) — `claude-opus-4-7` or `claude-sonnet-4-6`. Populate `ANTHROPIC_API_KEY` in `backend/.env`.
9. **Embedding pipeline** — OpenAI text-embedding-3-small (1536 dims) writes to `knowledge_nodes`. Triggered on new newsletter_items, ideas, artifacts.
10. **Retrieval agent** — calls `match_knowledge_nodes` RPC, feeds results into the outline generator.

### P1 — ancillary
11. **YouTube metrics fetcher** — `yt_metrics` table is empty; needs YouTube Data API wiring + background refresh.
12. **Storage flows** — image uploads (thumbnails, chat images, excalidraw exports) into Supabase Storage; update `*_storage_path` columns on relevant rows.
13. **Usage logging** — every LLM call should write to `usage_log`.

### P2 — polish
14. Magic link or passkey as alternate auth path.
15. `/auth/callback` route if we move away from `emailRedirectTo` pointing at `/onboarding` directly.
16. Proper error boundaries and toast UI (currently the auth page has minimal error rendering).

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
- `frontend/.env` — `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL=http://localhost:8000`.

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

---

## 10. What to do next session (suggested first task)

**Wire the Onboarding form to `POST /auth/onboard`.** It's the smallest end-to-end vertical slice that proves the auth → backend → Supabase → RLS loop. Once that's working, the same pattern applies to every other page.

Rough shape:
1. Create `frontend/src/lib/api.ts` — a `fetch`-wrapper that reads `session.access_token` from the Supabase client and attaches `Authorization: Bearer ...`.
2. In `Onboarding.tsx`, on submit, call `api.post("/auth/onboard", formState)`.
3. On success, `navigate("/make")`.
4. Also fetch `GET /auth/me` in `AuthProvider` on session change, cache `profile` + `onboarded` flag, and use it to auto-redirect new users to `/onboarding` if not onboarded.

That's the template for every subsequent feature.
