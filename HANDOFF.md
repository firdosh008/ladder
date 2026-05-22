# Ladder Content OS — Handoff / Context Doc

Last updated: 2026-05-02. Purpose: bring a fresh session (or a human contributor) up to speed without re-reading the whole chat history.

**Recent (scene vertical, 2026-05-02 — commit `5583651`):** Diagram prompt rewritten from "context-first illustration" to **explainer / whiteboard illustration** mode in `backend/app/agents/excalidraw_design_guide.py` — explicit anti-UI / anti-dashboard rules, hand-drawn organic asymmetry, multi-point curved arrows, hierarchy *without* heavy rectangles, soft accents (`#f08c00` strokes / `#ffec99` whisper fills, ≤ ~55% opaque coverage), default `roughness: 1`, density target **12–26 elements**. Vision QA prompt updated to reject "dashboard / Kanban cards / admin panels" outputs. JSON parser in `app/services/diagram_service.py` hardened: balanced-brace slicer (respects strings), smart-quote normalization, idempotent trailing-comma stripping, plus an explicit "Output contract" appended to the user prompt; temperature dropped 0.35 → 0.28; added `stop_sequences=["```"]`. Frontend Studio.tsx no longer renders the in-page Live Excalidraw iframe block — the live canvas now appears only inside `ScenePreviewModal` while a diagram run is active (gated by `VITE_EXCALIDRAW_CANVAS_URL`). New **`backend/excalidraw-skill-master/`** drop-in Claude Code skill (`SKILL.md` + `CLAUDE.md` + `README.md`) documenting MCP setup, 10 visual techniques, and the screenshot-iterate loop — reference docs, not part of the runtime.

**Major architectural shift (between 2026-04-26 and 2026-05-02):** Scene generation has bifurcated. The original CrewAI-planner-+-Anthropic-structured-outputs-designer path **still exists** in `app/agents/scene/{agents,tasks,designer,crew}.py`, but is now gated behind `settings.ENABLE_MCP_SCENE_DIAGRAM`. When that flag is **on** (the active path now), `run_scene_build` delegates to `app.agents.scene.mcp_diagram.run_scene_mcp_diagram`, which drives a **live local Excalidraw canvas** (vendored `mcp_excalidraw` Express server at `127.0.0.1:3000`) via `ExcalidrawCanvasClient` HTTP and runs an iterative draft → draw → PNG export → vision-QA loop in `app/services/diagram_service.py`. A Playwright headless tab supplies the WebSocket client required for PNG export. Default model for diagram drafting + vision QA is `DIAGRAM_ANTHROPIC_MODEL=claude-sonnet-4-6`; default `ANTHROPIC_MODEL` is now `claude-haiku-4-5`. **Structured outputs is OFF by default** for the legacy designer path (`SCENE_DESIGNER_STRUCTURED_OUTPUTS=False`) because grammar compilation kept hitting "Schema is too complex" / overload errors — the legacy designer falls straight through to prompted-JSON + `_validate_with_salvage`.

**Earlier (research vertical, 2026-04-26):** Research crew fans out across **5 platforms in parallel** — Exa (web), Reddit, YouTube, X, Instagram. Single async HTTP wrapper at `app/providers/scrapecreators.py` covers the four social platforms via the **ScrapeCreators API** (`SCRAPECREATORS_API_KEY`); provider returns normalized dataclasses (`RedditPost`, `YouTubeVideo`, `XTweet`, `InstagramReel`). Each tool emits **platform-tagged** `SourceRef`s through `sources_emitter_var`; `ResearchRunPanel` source rail renders a colored pill (web/reddit/yt/x/ig) on every card.

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
- **AI stack:** CrewAI (multi-agent orchestration), Anthropic SDK (`claude-sonnet-4-6` as default via CrewAI's LLM factory), OpenAI SDK (reserved for embeddings), `exa-py` for neural web search, **ScrapeCreators REST API for Reddit / YouTube / X / Instagram** (single API key, see `app/providers/scrapecreators.py`)

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
9. **Every LLM is constructed through `services/llm.py`**, never inline. That's the single place where model ID, provider, and API key get bound. When BYOK lands in v2, only this factory changes. Two factories live there:
   - `anthropic_llm()` — CrewAI `LLM` (litellm under the hood). Use inside Crews.
   - `anthropic_client()` — raw `AsyncAnthropic` SDK client. Use when you need features CrewAI's wrapper can't express — most importantly **structured outputs** (grammar-constrained JSON via `output_format: json_schema`).
10. **Structured artifacts use Anthropic structured outputs, not CrewAI `output_pydantic`.** CrewAI's `output_pydantic` injects the schema into the system prompt and asks nicely. That's fine for small/flat schemas (`Script`, `Outline`, `ResearchIdeas`). For **large nested schemas** like `SceneSkeleton` it fails — the model regularly drops required arrays under in-context bias from prior tasks. Use `client.messages.create(extra_body={"output_format": {"type": "json_schema", "schema": <pydantic>.model_json_schema()}}, extra_headers={"anthropic-beta": "structured-outputs-2025-11-13"})` for those. Strip Anthropic-unsupported keywords (`minimum`/`maximum`/`minLength`/`maxLength`/`pattern`/`format`/`default`) from the schema before sending; Pydantic still validates server-side.
11. **Per-platform providers wrap a single backend.** `app/providers/scrapecreators.py` is the only file that talks to ScrapeCreators. Each platform-shaped async function (`reddit_subreddit`, `youtube_search`, `x_user_tweets`, `instagram_reels_search`) returns a normalized frozen dataclass. When the official APIs land (Reddit OAuth via `asyncpraw`, YouTube Data API v3, Twikit for X, …), the swap is **module-internal**: signatures and dataclasses don't change, just the HTTP plumbing under each function. Tools, `SourceRef`, frontend types, and the WS event protocol must stay stable across the transition.

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
│   │   │   └── db.py                     # Pydantic mirrors — IdeaSlice, IdeaDraft/ResearchIdeas, Script/ScriptSection, Outline/OutlineItem, SceneLayout/SceneFrame/SceneSkeleton/SceneSkeletonElement, ContentAnalysis, ExtractedVideo, UserProfileSlice
│   │   ├── providers/
│   │   │   ├── exa.py                    # async wrapper around exa-py neural search
│   │   │   └── scrapecreators.py         # async wrapper for Reddit/YouTube/X/IG via ScrapeCreators
│   │   ├── services/
│   │   │   ├── llm.py                    # anthropic_llm() / anthropic_client() factories
│   │   │   ├── usage.py                  # log_usage() async context manager
│   │   │   ├── excalidraw_canvas.py      # spawn + supervise vendored mcp_excalidraw Node server (+ headless Playwright tab)
│   │   │   ├── excalidraw_http.py        # ExcalidrawCanvasClient — async wrapper over /api/* on the live canvas
│   │   │   ├── diagram_service.py        # plan → draw on canvas → PNG export → vision QA loop → SceneSkeleton
│   │   │   └── scene_visual_assets.py    # post-step that decorates SceneSkeleton with hero images/icons
│   │   ├── agents/
│   │   │   ├── excalidraw_design_guide.py  # DESIGN_SKILL_SYSTEM_RULES / DIAGRAM_JSON_INSTRUCTIONS / VISION_REVIEW_PROMPT (explainer-illustration prompt set)
│   │   │   ├── research/                 # research crew (3 agents → ResearchIdeas)
│   │   │   ├── studio/                   # studio crew (script_writer → outline_planner)
│   │   │   ├── content_extract/          # content_extract crew (analyzer → extractor)
│   │   │   └── scene/                    # legacy CrewAI planner + structured-output designer (now gated behind ENABLE_MCP_SCENE_DIAGRAM=False)
│   │   │       ├── agents.py             # layout_planner only (designer left CrewAI in 2026-04-25 hybrid rewrite)
│   │   │       ├── tasks.py              # planner task (output_pydantic=SceneLayout)
│   │   │       ├── designer.py           # direct Anthropic call → SceneSkeleton (structured outputs OFF by default; prompted-JSON + salvage)
│   │   │       ├── crew.py               # run_scene_build — branches on ENABLE_MCP_SCENE_DIAGRAM
│   │   │       ├── mcp_diagram.py        # NEW path: drives DiagramService, mirrors scene_build wire events
│   │   │       ├── skeleton_text_layout.py
│   │   │       └── skeleton_scene_cleanup.py
│   │   └── routes/
│   │       ├── health.py                 # GET /health
│   │       ├── auth.py                   # GET /auth/me, POST /auth/onboard
│   │       ├── ideas.py                  # GET/POST/PATCH/DELETE /ideas
│   │       ├── studio_sessions.py        # GET /studio-sessions/by-idea/{id}, POST …/scene/share
│   │       ├── diagram.py                # POST /generate-diagram (REST entry to DiagramService — also persists artifact + uploads PNG)
│   │       └── agents.py                 # WebSocket /ws/agents/{research,studio,extract,scene}
│   ├── tests/                            # pytest-asyncio + httpx + starlette TestClient
│   ├── vendor/                           # untracked — `mcp_excalidraw` Node Express canvas (cloned/built at runtime)
│   ├── excalidraw-skill-master/          # Claude Code skill drop-in (SKILL.md + CLAUDE.md + README.md) — reference docs only
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
│   │   │   ├── agents.ts                 # WS clients: research, studio, extract, scene; publishScene()
│   │   │   ├── motion.ts                 # fadeUp/stagger presets
│   │   │   └── cn.ts
│   │   ├── components/
│   │   │   ├── research/
│   │   │   │   └── ResearchRunPanel.tsx       # inline on /make (PRD §2 Option 2)
│   │   │   ├── extract/
│   │   │   │   └── ContentExtractPanel.tsx    # inline on /make Option 3
│   │   │   ├── studio/StudioScriptStream.tsx
│   │   │   ├── scene/SceneRunPanel.tsx, SceneView.tsx  # Excalidraw embed + build CTA
│   │   │   ├── kanban/                   # Videos.tsx board
│   │   │   ├── ui/                       # Button, Badge, Input, Card, ...
│   │   │   └── app/Shell.tsx             # layout shell
│   │   ├── pages/
│   │   │   ├── Auth.tsx                  # WORKS
│   │   │   ├── Onboarding.tsx            # WORKS (wired to /auth/onboard)
│   │   │   ├── Make.tsx                  # WORKS (research + content-extract live; pick-from-ideas wires existing rows)
│   │   │   ├── Videos.tsx                # WORKS (Kanban on ideas, hover-delete)
│   │   │   ├── Library.tsx               # DUMMY
│   │   │   ├── Settings.tsx              # PARTIAL — Profile tab works, others dummy
│   │   │   └── Studio.tsx                # WORKS: script + outline + scene column (Build scene, Excalidraw); chat placeholder
│   │   └── vite-env.d.ts
│   ├── .env                              # gitignored, filled with VITE_SUPABASE_*
│   └── .env.example
├── supabase/
│   └── migrations/
│       ├── 20260423000001_init.sql          # tables + trigger
│       ├── 20260423000002_rls_policies.sql  # RLS on everything
│       ├── 20260423000003_indexes.sql       # performance
│       ├── 20260423000004_match_function.sql# pgvector RPC
│       └── 20260425000001_excalidraw_bucket.sql  # public Storage bucket for published .excalidraw
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

### AI — Research vertical (first crew, 2026-04-25; multi-platform 2026-04-26)
- [x] Shared agent foundation: `providers/exa.py`, `providers/scrapecreators.py`, `services/llm.py`, `services/usage.py`, `middleware/ws_auth.py`, `models/db.py`.
- [x] `backend/app/agents/research/` — five tools (`ExaSearchTool`, `RedditTrendsTool`, `YouTubeTrendsTool`, `XUserTweetsTool`, `InstagramReelsTool`) + three-agent crew (trend researcher, outlier scorer, idea architect) producing `ResearchIdeas` via `output_pydantic`. `search_agent` derives subreddits / handles / video queries / IG queries from the user's profile + topic on the fly (no separate entity-resolver agent yet — was discussed in research, deferred until result quality demands it).
- [x] `IdeaDraft` schema expanded to full PRD §11.8 shape: `title, rationale, idea_type, opportunity_score, outlier_score (0-10), why_now (≤280 chars), suggested_tags[]`. Dropped the non-PRD `body` field (reserved for user notes post-save).
- [x] `WebSocket /ws/agents/research?token=...&topic=...` — verifies JWT, loads profile, streams events. **No longer auto-persists drafts** — per PRD §2.1 the user picks one inline; the frontend POSTs it to `/ideas` and navigates to `/studio/:id`. Route now only touches `user_profiles` (read).
- [x] Research run surface moved inline per PRD §2 Option 2: `ResearchRunPanel` renders directly on `/make` (no drawer). Completed runs mirror to `sessionStorage` so a refresh doesn't lose drafts. "New research" button clears it. "Save all to /videos" button bulk-creates ideas in one click. Per-draft pick still saves and opens studio.
- [x] Make page deviation fixed: StudioSetupDialog gate removed from research path (PRD: no modal between click and run). Extract button honestly disabled ("extract crew ships next"). Fake `gpt-4o · ~$0.03` caption replaced with `exa · sonnet-4.6`. Dead `StudioSetupDialog.tsx` + `components/studio/` directory deleted.
- [x] Tests (`tests/test_research_crew.py`): Exa tool JSON, event mappers, Pydantic bounds (inc. new `outlier_score` + `suggested_tags` default), WS auth + topic validation, streaming happy path asserting no ideas-table writes + full §11.8 shape on the wire. Per-tool serialization + platform-tag emission tests for Reddit / YouTube / X / Instagram. IG provider's 404→empty-list path verified (ScrapeCreators returns 404 + `error: not_found` for queries with zero matches; the provider swallows that).
- [x] Full backend test suite: **68 passing, 0 failing** (`uv run pytest -q`).

#### Multi-platform research (shipped 2026-04-26)
- **Provider** — `app/providers/scrapecreators.py` exposes four platform-shaped async functions: `reddit_subreddit(subreddit, sort, timeframe, limit)`, `youtube_search(query, upload_date, sort_by, limit)`, `x_user_tweets(handle, limit)`, `instagram_reels_search(query, date_posted, limit)`. Each returns a normalized frozen dataclass (`RedditPost` / `YouTubeVideo` / `XTweet` / `InstagramReel`). All four endpoints cost **1 credit / call** on the ScrapeCreators free tier (100 credits to start; pay-as-you-go after).
- **Endpoint quirks captured in code:**
  - Reddit: `timeframe` is only valid when `sort='top'` (provider only sends it in that case). Subreddit names ARE case-sensitive — agent prompt hardened to use canonical capitalisation.
  - X: only the **~100 most-popular tweets** per account are publicly available, not chronological/latest. Tool description reflects this.
  - Instagram: returns **404 + `error: not_found`** (with 200-shaped body) when the query matches zero reels. Provider treats this as `[]` rather than raising — niche queries should degrade gracefully, not blow up the crew.
- **Tools** — `app/agents/research/tools.py` adds `RedditTrendsTool`, `YouTubeTrendsTool`, `XUserTweetsTool`, `InstagramReelsTool` alongside the existing `ExaSearchTool`. Each tool wraps the provider call with `asyncio.run()`, emits platform-tagged `SourceRef`s through `sources_emitter_var`, and returns a JSON-serialised list back to the LLM. `SourceRef` gained a `platform: Literal["web","reddit","youtube","x","instagram"]` field (default `"web"`) so the existing Exa flow is unchanged.
- **Search agent** — `tools=[Exa, Reddit, YouTube, X, Instagram]`, `max_iter=14`. Backstory + task prompt direct it to fan out: 2 web queries + 1-2 reddit + 1 youtube + 1 x + 1 ig per crew run, deriving subreddits/handles/queries from the founder's audience + positioning. Output bullets carry a `platform` tag.
- **Frontend** — `Source.platform?: SourcePlatform` added to `lib/agents.ts`; `ResearchRunPanel` source rail renders a `PlatformPill` (`web` neutral, `reddit` orange `#ff4500`, `youtube` red `#ff0000`, `x` white, `instagram` pink `#E1306C`). The pill labels are `web/reddit/yt/x/ig`. The shared `'sources'` event protocol (§11) is unchanged — clients on older builds simply see `platform=undefined` and default to web.
- **Smoke tests** — `backend/probe_provider.py` (uses the actual provider module) and `backend/probe_scrapecreators.py` (raw httpx) both verified end-to-end against the live API as of 2026-04-26. Real signal observed: r/startups top-of-week posts; the *Gemini Enterprise Agent Platform* announcement (333k views); OpenAI's *"GPT-5.5 and GPT-5.5 Pro are now available in the API"* tweet (441k views); IG reels at 22k+ plays for `query='startup'`. Probe scripts are intentionally throwaway — delete once stable.
- **Forward-compat note** — when official provider APIs come online (Reddit OAuth via `asyncpraw`, YouTube Data API v3, Twikit/BYOK for X, no plan for IG), only `app/providers/scrapecreators.py` and the corresponding tool's import need to change. Tool surface, `SourceRef` shape, frontend types, and the WebSocket event protocol stay identical. See §3 #11 for the rule.

### Dummy-data sweep (2026-04-25 evening)
- [x] `Library.tsx` — all four tabs rewritten. KnowTab: real profile completeness % + per-field rendering from `useAuth()`. SourcesTab: alias driven by real `profile.forwarding_alias` with a pending state when null. Graph/Insights: honest empty states naming what ships next. Fabricated `{1,284 nodes / +62 / alex+ladder@ingest.ladder.so}` gone.
- [x] `Settings.tsx` — Profile tab gains read-only email (from `user.email`) + forwarding alias + copy button. Brands/Skills: honest empty states. Models: "server-default keys active, BYOK in v2" + a live/pending table with research_agent marked live. Integrations rows are driven by `profile.youtube_connected`.
- [x] `Sidebar.tsx` — hardcoded `topIdeas` array replaced with real top-3 by `opportunity_score` from `useIdeas({status:"new"})`; clicks navigate to `/studio/:id`. Fabricated "2 jobs running · $4.21" strip removed.
- [x] `Studio.tsx` — ripped hardcoded SCRIPT/OUTLINE/CHAT_SEED + the `setTimeout` pseudo-streaming. Now loads the real idea via `useIdeas()` + URL `:id`, shows title/score/outlier/rationale/body/source_content, and three honest "ships next" placeholders for Script / Scene / Sharpen panels.
- [x] Frontend typechecks clean (`npx tsc --noEmit`).

### Native-streaming rewrite (shipped 2026-04-25 late evening)
Problem: drawer hung after `agent_start` for the three agents because the old event stream was built on CrewAI's threaded `step_callback` with speculative `getattr(step, "tool"/"tool_input"/"result"/"output")` shape-guessing that never matched real payloads.

Shipped:
- `backend/app/agents/research/crew.py` — dropped the `step_callback` + `asyncio.Queue` bridge. Uses `Crew(stream=True)` + `async for chunk in await crew.akickoff():` and emits events directly.
- `agents.research.streaming` — new `sources_emitter_var: ContextVar[SourcesEmitter]` side-channel. `ExaSearchTool._run` reads it and pushes real search result titles+URLs+snippets into the runner's queue so they appear in the stream as `sources` events (CrewAI's native stream only surfaces tool-call *arguments*, not *results*).
- New event protocol (see §11 below): `agent_start` on `agent_role` transition, `tool_call` on TOOL_CALL chunks (with real tool_name + arguments JSON), `sources` on ExaSearchTool results, `text_delta` on TEXT chunks, `task_complete` on `task_index` advance. Dropped `tool_result` + `agent_step` (step_callback-era artefacts).
- `streaming.result.pydantic` / `streaming.result.tasks_output[-1].pydantic` for the `ResearchIdeas`; `streaming.result.token_usage` for real input/output tokens.
- `ResearchRunPanel.tsx` (replaces the old drawer) — inline full-width section on `/make`. Two-column layout on lg+ : left column = Drafts → Agents → Activity; right column = numbered Sources rail (Perplexity-style, collapses beyond 6). Each agent row shows status dot + tool-call pills + tail of streaming text. Draft cards carry opportunity + outlier scores, multi-sentence rationale, `why now` callout, suggested tags, and two save paths: pick-one → studio, or Save-all → /videos. `sessionStorage` key `ladder:research:last` persists the terminal state across refreshes within the same tab.
- `tasks.py` prompts hardened: search now demands 12-18 signals from 2-4 distinct queries, scorer surfaces narrative threads, formulator produces 4-6 drafts with 50-100-word rationales.
- `outlier_score` is now persisted: wired through `IdeaCreate` (backend), `pickDraft` (drawer), and `CardDetailSheet` (editable). `why_now` + `suggested_tags` remain wire-only per storage decision (option b from 2026-04-25 planning).

### Kanban hover-delete (shipped 2026-04-25 late evening)
- `KanbanCardView` now renders a trash affordance in the top-right that fades in on `group-hover` / focus. Click → `window.confirm` → `deleteIdea()`. Pointer-down is stopped so the drag handle doesn't swallow the click.
- Threaded `onCardDelete` through `Column` → `Board` → `Videos.tsx`, which reuses `useIdeas().deleteIdea` and clears the detail sheet if the deleted card happens to be open.

### AI — Studio vertical (shipped 2026-04-25 overnight)
The /make → /studio loop now produces a real script + outline. Two-task sequential crew, native CrewAI streaming, persists to `studio_sessions` + versioned `artifacts`.

- `backend/app/agents/studio/` — `script_writer` + `outline_planner` agents, sequential tasks (`Script` then `Outline` via `output_pydantic` per task), `run_studio_script(user_id, profile, idea, target_duration_min)` async generator.
- `backend/app/models/db.py` — `IdeaSlice`, `Script`/`ScriptSection`, `Outline`/`OutlineItem` Pydantic models. Bounds: 2-12 sections × 1-15 min each, 3-18 outline items, 8-30 word talking points (enforced in prompt, not validator).
- `WebSocket /ws/agents/studio?token=...&idea_id=...&duration=...` — verifies JWT, loads idea via RLS, loads profile, streams `agent_start` / `text_delta` / `task_complete` / `script_ready` / `outline_ready` / `usage`. On completion: upserts a `studio_sessions` row for `(user_id, idea_id)`, writes versioned `artifacts` rows (type=`script` / `outline`, JSON in `content_json`, plain-text mirror in `content_text`), mirrors the outline to `studio_sessions.scene_outline`, then emits `persisted` + `complete`.
- `GET /studio-sessions/by-idea/{idea_id}` — returns `{session, script, outline}` (latest version of each artifact). Used by the studio page to hydrate before deciding to stream.
- `frontend/src/components/studio/StudioScriptStream.tsx` — `useStudioStream(ideaId)` hook: hits the GET first, hydrates if a script artifact exists, otherwise opens the WS. Exposes `state.{script, outline, runtime, status, error, cost, hydratedFromDb, rerun}`. Companion `ScriptView` (sectioned cards with talking points + transitions) and `OutlineView` (numbered scene rows). `StudioRunStrip` shows live agent dots + cost.
- `frontend/src/pages/Studio.tsx` — replaced the static placeholder copy with the live panels. Three-column grid: Script (live) | Scene/Outline (live) | Sharpen (still placeholder). Re-run button on the strip (status `ready` only).

### AI — Content-extract vertical (shipped 2026-04-25 overnight)
PRD §2 Option 3 is now fully live. Paste long-form content on `/make`, get an idea + script + outline + studio session in one shot.

- `backend/app/agents/content_extract/` — `analyzer` (decides title / type / runtime / key beats) + `extractor` (drafts `ExtractedVideo` = title + rationale + idea_type + derived_duration_min + Script + Outline). `output_pydantic` per task: `ContentAnalysis` then `ExtractedVideo`.
- `WebSocket /ws/agents/extract?token=...` — first client message is `{source_content: "...", source_url?: "..."}` (max 60k chars, 15s read timeout). On completion: inserts an `ideas` row (`source_type = "content_extract"`, `source_content` keeps the original paste, `source_content_url` keeps the optional URL), creates a `studio_sessions` row, writes versioned script + outline artifacts, emits `persisted` with the new `idea_id` + `session_id`.
- `frontend/src/components/extract/ContentExtractPanel.tsx` — inline panel on `/make` Option 3. 2-agent timeline + extracted-video preview card + source rail. Auto-navigates to `/studio/:idea_id` ~700ms after `persisted` so the user sees the success state, then lands in studio with the script already hydrated from artifacts (no re-run).
- `frontend/src/pages/Make.tsx` — Option 3 is now live: input enabled, button gated on ≥80 chars, character counter when below threshold. Research and content-extract panels are mutually exclusive (starting one clears the other's setup state).

### AI — Scene (Excalidraw) vertical (shipped 2026-04-25, hybrid rewrite 2026-04-25 late)
End-to-end **build_scene**: outline + script in → Excalidraw **skeleton** out → persisted + embedded in Studio.

- **Data shape:** `SceneSkeleton` in `app/models/db.py` mirrors `@excalidraw/excalidraw`’s `ExcalidrawElementSkeleton` (camelCase fields) so the frontend can call `convertToExcalidrawElements()` with no translation. Persisted as `artifacts.type = excalidraw` (versioned JSON in `content_json`).
- **Hybrid pipeline** (`backend/app/agents/scene/`):
  1. **Planner — CrewAI** (`agents.py` + `tasks.py`). Single `layout_planner` agent, single sequential task with `output_pydantic=SceneLayout`. Streams `agent_start` / `text_delta` / `task_complete` via `Crew(stream=True)`.
  2. **Designer — direct Anthropic** (`designer.py`). `client.messages.create(...)` with `output_format: json_schema(SceneSkeleton)` and the `structured-outputs-2025-11-13` beta header. Grammar-constrained sampling guarantees `elements` exists. One-shot, non-streaming (the artifact is structural, not narrative).
- The crew has **no critic**. Don't reintroduce one without a strong reason — the original critic + `output_pydantic` design was the source of the validation noise that motivated this rewrite.
- **WebSocket** `GET /ws/agents/scene?token=...&session_id=...` — loads session + latest script + outline + idea + profile, runs `run_scene_build`, streams the usual `agent_start` / `text_delta` / `task_complete`, then `scene_ready` + `usage`, then persists and emits `persisted` with `scene_artifact_id` and `complete`. The frontend `SceneRunPanel` agent keys (`layout_planner`, `element_designer`) are unchanged — only the implementation behind the designer key shifted.
- **Open in Excalidraw:** frontend inflates the skeleton, then `POST /studio-sessions/{session_id}/scene/share` uploads the full Excalidraw file JSON to Storage bucket `excalidraw_scenes` (public read; RLS path-scoped write). Public URL is opened as `excalidraw.com/#url=<encodeURIComponent(url)>`. Migration: `20260425000001_excalidraw_bucket.sql`.
- **Hydration:** `GET /studio-sessions/by-idea/{idea_id}` returns `scene` = latest `excalidraw` artifact (or null). No separate critique row.
- **Frontend:** `SceneRunPanel` + lazy `SceneView` (`@excalidraw/excalidraw`), download + share affordances. `useStudioStream` holds `sessionId` + `scene` for the scene column.

#### Postmortem — why the second agent had to leave CrewAI

What we kept hitting (every other run, 2026-04-25):

```
ERROR:root:Anthropic API call failed: 1 validation error for SceneSkeleton
elements
  Field required [type=missing, input_value={'canvas_width': 2000, 'c...able (pricing models).'}]
```

…and intermittently the planner's `frames[].description` blew past its 400-char cap.

Two real problems, one architectural:

1. **In-context contamination.** `Task(context=[plan_task])` puts the planner's `SceneLayout` (with `frames[].description`) directly into the designer's prompt. The model then mirrors that shape and emits `{canvas_width, ..., frames-style-descriptions}` instead of `{..., elements: [...]}`. Prompted JSON has no defense against this — the schema is just text in the system prompt fighting more recent text in the user prompt.
2. **CrewAI retry doesn't help.** `output_pydantic` retries re-prompt with the same conceptual mistake; the model converges on the wrong shape, not the right one.

The correct fix was structural, not prompt-engineering:

- **Planner stayed as CrewAI** — its schema (`SceneLayout`) is small and flat; prompted JSON is fine and we keep token-by-token streaming for the UI.
- **Designer became a direct Anthropic call** with `output_format: {type: "json_schema", schema: SceneSkeleton.model_json_schema()}`. The schema is compiled into a grammar that constrains token sampling; the model literally cannot emit JSON missing `elements`. This is Anthropic's "Structured Outputs" feature (beta header `structured-outputs-2025-11-13`, GA on Sonnet 4.6).
- **Schema cleaning.** Anthropic's grammar compiler is fussy about JSON Schema. `designer._clean_schema()` walks the Pydantic-emitted schema and:
  - **Strips unsupported keywords** (`minimum`, `maximum`, `minLength`, `maxLength`, `pattern`, `format`, `default`, `not`, `if`/`then`/`else`).
  - **Forces `additionalProperties: false` on every `object` node.** Without this Anthropic 400s with `"For 'object' type, 'additionalProperties' must be explicitly set to false"`. Pydantic only emits it when the model has `extra="forbid"` — walking the schema is more defensive than touching every model class.
  - `SceneSkeleton.model_validate()` still runs server-side as defence in depth.
- **Resilience.** Structured outputs is beta and the grammar compiler can return transient `503 overloaded_error` / `"Grammar compilation is temporarily unavailable"`. The designer handles this in three layers:
  1. **Retry** the structured-outputs call up to 3 times with 1.5s + 4s backoff on `overloaded_error` / 429 / 503 / 529.
  2. **Fall back to prompted JSON** if structured outputs stays unavailable. Same system prompt + the JSON Schema appended; we extract the first `{...}` blob (handles fenced output) and validate with Pydantic.
  3. **Self-correction pass** on the prompted-JSON path — if validation fails, re-prompt once with the Pydantic error injected and a hard reminder that `elements` is required.

  Every other (non-overload) `APIError` raises immediately.

- **Visible/invisible-constraint trap (don't repeat this).** Pydantic post-validation MUST NOT enforce constraints we strip from the schema we send to Anthropic. We hit this with `string_too_long` on a label cap: the model produced a perfectly grammar-valid output, our schema cleaner stripped `maxLength` so the model had no way to know the cap existed, and Pydantic then rejected. The fix has two halves:
  1. **Caps on `SceneElementLabel.text` / `SceneSkeletonElement.text` / `SceneSkeleton.notes` are now generous** — sanity ceilings (2000 / 4000 / 4000), not UX guidelines. Aesthetic guidance lives in the system prompt, not the validator.
  2. **`_validate_with_salvage()`** in `designer.py` truncates over-cap strings rather than raising, but only when *every* validation error is a length cap — real shape mismatches still raise loudly. A truncated scene is better than a 500.

  General rule: anything `_clean_schema()` strips before sending should be a soft constraint on our side too (loose, salvageable) — never a hard reject.
- **`SceneFrame.description` cap raised** 400 → 1000 in `app/models/db.py`. The planner reasonably writes longer-form intent notes; the cap was producing false validation failures upstream of the real bug.

**Standing rule going forward** (also encoded in §3 #10): any agent step that produces a large nested artifact (Script + Scene + future Sharpen edits + edit_scene diffs) should use `anthropic_client()` + structured outputs, not CrewAI `output_pydantic`. Reserve `output_pydantic` for small/flat schemas where prompted JSON is reliable.

### AI — Scene (Excalidraw, **live MCP canvas path**) — current default since ~2026-04-30
The hybrid CrewAI+structured-outputs designer described above is now **dormant by default**. `run_scene_build` (in `app/agents/scene/crew.py`) branches on `settings.ENABLE_MCP_SCENE_DIAGRAM`; the active production path delegates to `app.agents.scene.mcp_diagram.run_scene_mcp_diagram`, which drives a real Excalidraw canvas through `app/services/diagram_service.py`. This path treats the diagram as a **drawing-on-a-live-canvas problem**, not a "produce JSON in one shot" problem — Claude drafts JSON, the backend pushes it to a real Excalidraw via HTTP, exports a PNG, then asks Claude (vision) to grade its own work and emit element-level patches.

#### Lifecycle (per scene WS run)

1. **Boot the canvas (once per process).** `app/main.py` lifespan calls `excalidraw_canvas.ensure_canvas_running(...)`:
   - Resolves the vendor checkout (`backend/vendor/mcp_excalidraw` by default; override via `EXCALIDRAW_VENDOR_ROOT`).
   - If `dist/` is missing: runs `npm ci` (or `npm install`) + `npm run build` under an `asyncio.Lock`.
   - Spawns `node dist/server.js` with `HOST`/`PORT` from `EXCALIDRAW_HTTP_URL`. Stderr is teed to `/tmp/ladder-exc-canvas-<pid>-<port>.stderr.log` so we can surface tail on EADDRINUSE.
   - Polls `GET /health` until `status=="healthy"` (timeout `EXCALIDRAW_CANVAS_HEALTH_WAIT_SECONDS`).
   - **Headless tab** — when `EXCALIDRAW_HEADLESS_AUTOSTART=true`, spawns Playwright `scripts/headless-canvas.mjs` (env `EXCALIDRAW_HEADLESS_URL`) so PNG export has at least one WebSocket client; waits for `/health.websocket_clients ≥ 1` (timeout `EXCALIDRAW_HEADLESS_CONNECT_TIMEOUT_S`). On Playwright bootstrap failure the error tells the user to `cd <vendor>/mcp_excalidraw && npx playwright install chromium`.
   - Module-level globals (`_canvas_proc`, `_headless_proc`, `_we_started_*`) track ownership; lifespan shutdown calls `shutdown_managed_children()` to terminate only the procs we spawned.
2. **Compose the brief.** `mcp_diagram.compose_scene_brief()` flattens `idea.title`, voice/audience snippets from `UserProfileSlice`, the numbered outline beats, and per-section script talking points + bridges into a single Markdown blob. This is the only thing the drafter sees — no schemas, no founder PII, no in-context contamination from a planner pass.
3. **Wait for a live viewer.** `DiagramService.stream_diagram_generation()` calls `excalidraw_canvas.wait_for_websocket_clients(timeout_s=120)` first. If the headless tab hasn't connected yet, the run blocks here — PNG export needs at least one client; the upstream MCP server returns 503 on `POST /api/export/image` otherwise.
4. **Outer loop — at most `DIAGRAM_MAX_ITERATIONS` redraws** (default **1**, configurable up to 8). Each iteration:
   - **Draft.** `_draft_payload()` calls `anthropic_client().messages.create(model=DIAGRAM_ANTHROPIC_MODEL, max_tokens=8192, temperature=0.28, stop_sequences=["```"])` with the system rules from `excalidraw_design_guide.DESIGN_SKILL_SYSTEM_RULES + DIAGRAM_JSON_INSTRUCTIONS`, the script brief, an iteration-specific layout hint, optional `brand_color`, optional `font_family`, accumulated `feedback_notes` from prior passes, and a final "Output contract" block demanding `{ "elements": [...] }`. Returns a JSON dict — no structured outputs (Anthropic rejects `additionalProperties: true` and prefill is unsupported on the Sonnet 4.x models we use, so we lean on tolerant parsing).
   - **Parse.** `json.loads(raw_text)` first; on failure `_extract_json_object()` strips ``` ``` fences, runs the **balanced-brace slicer** `_balanced_json_object_slice()` (string-aware — avoids greedy `rfind('}')` truncation), normalizes smart quotes (`“”‘’` → ASCII), and idempotently strips trailing commas. Reject if `elements` isn't a list.
   - **Re-id.** `assign_fresh_element_ids()` rewrites every LLM-supplied id to a 14-char `[a-z0-9]` token and remaps `startBinding.elementId`, `endBinding.elementId`, `boundElements[].id`, `start.id`, `end.id`. This is the single piece of state that survives between drafter and vision QA — vision must reference these canvas-truth ids verbatim, never semantic placeholders like `step1`.
   - **Push to canvas.** `ExcalidrawCanvasClient.clear_canvas()` → `batch_create_elements(elements)` → 150ms breath → `set_viewport(scroll_to_content=True)` so the headless tab has the full diagram in frame for the PNG.
   - **Inner vision-QA loop — up to 3 passes per outer iteration.** Each pass:
     1. `export_image_png_base64()` — POST `/api/export/image`, base64 PNG.
     2. `get_all_elements()` — fresh truth from the canvas (id-keyed).
     3. `_vision_review(png_b64, elements)` — Claude vision call with `VISION_REVIEW_PROMPT` and the elements JSON (truncated to 140k chars). Returns `{approved: bool, corrections: [{id, patch}], notes}`. Non-JSON response auto-approves with `notes="parse_error"` (cheap-out fallback rather than a hard fail).
     4. **If approved:** export final PNG bytes, run `canvas_elements_to_scene_dict()` to clean server-only fields (`createdAt`/`updatedAt`/`version`) and recompute the bounding-box canvas (clamped to `800–4800 × 600–4800` with 120px padding), validate against `SceneSkeleton.model_validate()` (warning-only — never raises), break.
     5. **If patches:** filter to ids actually on the canvas (logged warning for any others), `update_element(id, patch)` each one via `PUT /api/elements/{id}`, append `notes` to outer-loop `feedback`, retry the inner pass.
     6. **If no patches but rejected:** record the note as feedback for the next outer redraw and break the inner loop.
   - **Outer-loop redraw bias.** `_iteration_design_guidance()` rewrites the prompt for pass N: pass 1 forbids habitual templates; pass 2+ tells the model "prior composition failed QA — abandon its spatial archetype entirely" so we don't get cyclic layouts. `feedback` from QA notes is concatenated into each subsequent draft prompt.
5. **Persist.** When the inner loop breaks with `approved=True` (or after exhausting iterations), `mcp_diagram.run_scene_mcp_diagram` validates the scene dict, runs `enrich_scene_visuals(...)` (hero images / icons via `scene_visual_assets.py`), and yields `task_complete` → `diagram_complete` (`{iterations}`) → `scene_ready` (full `Scene`) → `usage`. The WebSocket route in `agents.py` (§ `/ws/agents/scene`) writes a versioned `excalidraw` artifact and emits `persisted` with `scene_artifact_id`.
6. **Token + cost accounting.** `DiagramService.last_input_tokens` / `last_output_tokens` accumulate across **every** Anthropic call in the run (drafter + vision QA). Billed as flat `$1/Mtok` in, `$5/Mtok` out into `usage_log` under `function_name="scene_build_mcp_canvas"`, model `DIAGRAM_ANTHROPIC_MODEL`.

#### Wire events the frontend sees during a run
- `agent_start { agent: "diagram_agent" }` — once at the top.
- `diagram_draft { phase: "waiting_live_viewer" }` then per iteration `phase: "drawn"` with `iteration` + `element_count`.
- `diagram_iteration { iteration, phase: "draft" | "vision" | "approved", layout_hint? }` — UX progress beats.
- `task_complete { agent: "diagram_agent", preview: "" }` once the canvas is approved.
- `diagram_complete { iterations }`.
- `scene_ready { scene: <SceneSkeleton dict> }`.
- `usage { token_usage: {input, output, cost_usd} }`.
- `persisted { scene_artifact_id }` (added by the WS route, not `DiagramService`).

#### Frontend surface for the live canvas

- `frontend/src/pages/Studio.tsx` no longer iframes the canvas inline (commit `5583651` deleted that section). The live view appears only inside `ScenePreviewModal` while a diagram run is active: `Studio` flips `liveCanvasDuringRun=true` via the `onDiagramRunActive` callback the moment `SceneRunPanel` opens its WS, and the modal swaps its body from the read-only `SceneView` (lazy-loaded `@excalidraw/excalidraw`) to a sandboxed `<iframe>` pointing at `VITE_EXCALIDRAW_CANVAS_URL` (e.g. `http://127.0.0.1:3000`). When that env var is unset the modal renders an honest empty state telling the user how to wire it up.
- After the run terminates the modal flips back to `SceneView` driven by the persisted scene JSON. "Open in Excalidraw" still routes through `POST /studio-sessions/{session_id}/scene/share` (Storage upload + `excalidraw.com/#url=…`) — the live-canvas iframe is preview-only.

#### Settings that govern the path

| Setting | Default | What it does |
| --- | --- | --- |
| `ENABLE_MCP_SCENE_DIAGRAM` | `False` | When True, `/ws/agents/scene` runs the live-canvas path; otherwise it runs the legacy CrewAI planner + Anthropic designer. **Production currently runs with this on.** |
| `EXCALIDRAW_VENDOR_ROOT` | `backend/vendor/mcp_excalidraw` | Where to find / build the Node canvas. |
| `EXCALIDRAW_HTTP_URL` | `http://127.0.0.1:3000` | Canvas Express server URL. Same value goes into `VITE_EXCALIDRAW_CANVAS_URL`. |
| `EXCALIDRAW_CANVAS_AUTOSTART` | `True` | Spawn `node dist/server.js` if `/health` is unreachable. |
| `EXCALIDRAW_CANVAS_HEALTH_WAIT_SECONDS` | `240` | Boot timeout — first build can be slow. |
| `EXCALIDRAW_HEADLESS_AUTOSTART` | `True` | Spawn Playwright headless tab so PNG export has a WS client. |
| `EXCALIDRAW_HEADLESS_CONNECT_TIMEOUT_S` | `180.0` | How long to wait for the tab to connect. |
| `DIAGRAM_ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Model for both drafter + vision QA. **Must support vision.** |
| `DIAGRAM_MAX_ITERATIONS` | `1` | Outer redraw cap. Each iteration clears the canvas and starts fresh. |
| `SCENE_DESIGNER_STRUCTURED_OUTPUTS` | `False` | Legacy designer toggle (off — too many "Schema is too complex" 400s). |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5` | Default for crews **other** than diagram (research / studio / extract). |

#### Why this exists (postmortem)
The 2026-04-25 hybrid (planner-CrewAI + structured-outputs-designer) hit a wall on two fronts simultaneously: (1) Anthropic's grammar compiler started returning persistent `Schema is too complex` 400s on the full `SceneSkeleton` schema, which was already being trimmed via `_clean_schema()`, and (2) the resulting one-shot JSON outputs read as **dashboard mocks** — uniform card grids, framed every block, dense filled rectangles — because the model was producing what it knew "looked like a diagram" rather than a hand-explained illustration. The live-canvas path solves both: no structured outputs (so no compiler errors), and a vision-QA loop that can *see* the rendered output and reject UI-mock aesthetics. The 2026-05-02 prompt rewrite codified the rejection rule into `VISION_REVIEW_PROMPT` ("Reject when: Layout reads as dashboard, Kanban cards, admin panels…").

#### Skill file: `backend/excalidraw-skill-master/`
Added in commit `5583651`. This is **not runtime code** — it's a Claude Code skill drop-in (`SKILL.md` + `CLAUDE.md` + `README.md`) that documents the same MCP canvas + screenshot-iterate workflow. It's intended for engineers using Claude Code interactively to draw diagrams against a local `mcp_excalidraw` install (the upstream `yctimlin/mcp_excalidraw` repo, not our vendored fork). Can be deleted without affecting the API.

### Shared agent plumbing
- `frontend/src/lib/agents.ts` — `runStudioStream`, `runExtractStream`, `runSceneStream`, `fetchStudioByIdea`, `publishScene`, plus event types. Common WS pump: `consumeStream(url, onEvent, finalise, initialPayload?)`.
- `backend/app/routes/agents.py` — WS routes share helpers: `_load_profile`, `_load_idea`, `_load_session`, `_load_latest_artifact`, `_ensure_studio_session`, `_persist_script_outline`, `_persist_scene_skeleton`, `_safe_send_json`, `_next_artifact_version`.

### Tests
- `tests/test_studio_crew.py` — script/outline hydration, Pydantic bounds, WS, `GET /studio-sessions/by-idea/{id}`.
- `tests/test_extract_crew.py` — content-extract crew + WS.
- `tests/test_scene_crew.py` — `SceneSkeleton` / layout Pydantic, scene WS (mocked `run_scene_build`), `POST …/scene/share` Storage path.
- Full backend: run `uv run pytest -q` (expect **~62** passed, a few xfail/xpass per legacy tests). Frontend: `npx tsc --noEmit`.

---

## 6. What's NOT built yet — priority-ordered backlog

### P0 — close the studio loop
1. **Sharpen crew** — Studio chat sidebar. Small streaming crew that rewrites script sections on request; persist to `chat_messages` (`ChatPanel` still placeholder in Studio).
2. **gen_outline polish** — Inline editing for the scene outline (rename / reorder / add / delete frames) per PRD.
3. **gen_thumbnail** — DALL·E 3 (or product-chosen) variants, refinement loops, reference URL flow.
4. **Approve-and-build gating** — `outline_approved` + button semantics so regens are intentional.
5. **Studio header pills** — Output type, brand, duration: interactive pills + regen affordances, three-zone duration slider.
6. **Error recovery** — e.g. retry from step, “taking longer” copy (no silent fallbacks; align with product rules).
7. **edit_scene (screenshot-to-edit)** — Vision parse → label→element map → JSON diff + artifact update.
8. **Optional later:** reintroduce a **critic** or post-validator only if we need automated QA on skeletons (e.g. arrow-binding sanity, label uniqueness). Don't put it back in CrewAI's `output_pydantic` path — run it as a second Anthropic structured-outputs call so a critic failure can't silently corrupt the designer's grammar-valid output.

### P1 — knowledge + retrieval
9. **Embedding pipeline** — OpenAI `text-embedding-3-small` (1536 dims) writes to `knowledge_nodes`. Triggered on new newsletter_items, ideas, artifacts. OpenAI SDK is already installed.
10. **Retrieval agent** — calls `match_knowledge_nodes` RPC with explicit `user_id`, feeds results into script/scene/sharpen crews.
11. **Newsletter ingestion** — `sources` + `newsletter_items` + forwarding alias flow. `user_profiles.forwarding_alias` already surfaces on Make.

### P1 — still-dummy surfaces
12. **Projects + brands CRUD** — simple tables, used by sessions. Settings → Brands tab is dummy.
13. **Library.tsx** — all four tabs are still mostly placeholder/empty-state (see dummy-data sweep notes above for partial honesty).
14. **Settings.tsx** — only Profile is fully real; other tabs partial/dummy.

### P1 — ancillary
15. **YouTube metrics fetcher** — `yt_metrics` table is empty; needs YouTube Data API wiring + background refresh.
16. **Storage flows** — image uploads (thumbnails, chat images) into Supabase Storage; `excalidraw_scenes` exists for published scene files.
17. **BYOK via Supabase Vault** — per `backend-dys.md`; swap server-default keys in `services/llm.py` for per-user Vault reads.

### P2 — polish
18. Magic link or passkey as alternate auth path.
19. `/auth/callback` route if we move away from `emailRedirectTo` pointing at `/onboarding` directly.
20. Proper error boundaries and global toast UI.
21. **Real cost accounting** in `usage_log` — today crews use a flat model price map; replace with actuals when provider usage is clean.

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
  - **Required for the multi-platform research crew (Reddit/YouTube/X/Instagram):** `SCRAPECREATORS_API_KEY` (sign up at scrapecreators.com — 100 free credits, then $10 / 5k credits, 1 credit per call across all four platforms).
  - **Required for the live-canvas scene path (active default):** Node 18+ + npm on `PATH` (the Express canvas builds + runs from `backend/vendor/mcp_excalidraw`); Playwright Chromium for the headless export tab (run `cd backend/vendor/mcp_excalidraw && npx playwright install chromium` once). Set `ENABLE_MCP_SCENE_DIAGRAM=true` to flip `/ws/agents/scene` onto the live-canvas pipeline; see the table in §5 "AI — Scene (live MCP canvas path)" for every related toggle.
  - Optional: `ANTHROPIC_MODEL` (default `claude-haiku-4-5` for non-diagram crews), `DIAGRAM_ANTHROPIC_MODEL` (default `claude-sonnet-4-6` — must support vision), `OPENAI_API_KEY` (for embeddings, not used yet, and for `dall-e-3` hero thumbnails when `SCENE_IMAGE_GEN_ENABLED=true`).
- `frontend/.env` — `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL=http://localhost:8000`, `VITE_EXCALIDRAW_CANVAS_URL=http://127.0.0.1:3000` (optional — when set, `ScenePreviewModal` shows the live MCP canvas in an iframe while a diagram run is active). The frontend derives the WebSocket base URL from `VITE_API_URL` (`http://` → `ws://`, `https://` → `wss://`).

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

## 10. What to do next session (suggested)

Pick one vertical from **§6 P0** — most product leverage next:

- **Sharpen (chat) crew** + `chat_messages` persistence — unblocks in-flow script/outline edits from Studio.
- **gen_thumbnail** — closes the Loom + social slice after scene + script are stable.
- **edit_scene** — vision on screenshot → diff on `SceneSkeleton` (depends on stable labels/ids in designer output).

**Embedding + retrieval (§6 P1 #9–11)** is the parallel track: first real consumer of `match_knowledge_nodes` for personalized script/scene context.

When touching agents: follow the existing **native `Crew(stream=True)`** pattern in `research/`, `studio/`, `content_extract/`, and `scene/` — do not reintroduce threaded `step_callback` bridges. For any step that returns a **large nested artifact** (anything Skeleton-shaped), follow `scene/designer.py` and call Anthropic directly with `output_format: json_schema` — do not put it back inside CrewAI `output_pydantic` (see §5 scene postmortem and §3 #10).

When touching the diagram pipeline: changes to **prompt copy** live in `app/agents/excalidraw_design_guide.py` (three constants — `DESIGN_SKILL_SYSTEM_RULES`, `DIAGRAM_JSON_INSTRUCTIONS`, `VISION_REVIEW_PROMPT`); **JSON parser robustness** lives in `_extract_json_object()` / `_balanced_json_object_slice()` in `app/services/diagram_service.py`; **iteration cadence** is `DIAGRAM_MAX_ITERATIONS` × inner 3-pass vision QA, hard-coded inside `stream_diagram_generation`. The id-rewrite step (`assign_fresh_element_ids`) is the load-bearing piece that makes vision corrections referenceable — don't skip it. Any change to the canvas HTTP client surface (`excalidraw_http.py`) must also handle the upstream MCP server returning 503 on PNG export when `websocket_clients == 0`.

---

## 11. Agent event protocol (reference)

Every `/ws/agents/*` endpoint emits events in this shape. The frontend drawer is generic over it.

```json
{"type": "agent_start",   "agent": "search_agent"}
{"type": "tool_call",     "agent": "search_agent", "tool": "web_search", "arguments": "{\"query\":\"...\",\"num_results\":10}"}
{"type": "sources",       "query": "...", "items": [{"title":"...","url":"https://...","published_date":"2026-04-10","snippet":"..."}]}
{"type": "text_delta",    "agent": "...", "content": "partial chunk"}
{"type": "task_complete", "agent": "...", "preview": "tail of output"}
{"type": "ideas_ready",   "ideas": [...], "token_usage": {"input": 0, "output": 0, "cost_usd": 0.0}}
{"type": "complete",      "count":  4,    "cost_usd": 0.07}
{"type": "error",         "message": "..."}
```

**Vertical-specific terminal payloads (examples):**
- Research: `ideas_ready`
- Studio: `script_ready`, `outline_ready`, then `persisted` with `script_artifact_id` + `outline_artifact_id`
- Extract: `extract_ready`, then `persisted` with `idea_id` + `session_id` + artifact ids
- Scene (legacy CrewAI path, `ENABLE_MCP_SCENE_DIAGRAM=False`): `agent_start { agent: "layout_planner" | "element_designer" }` → `text_delta` → `task_complete` → `scene_ready` → `usage` → `persisted { scene_artifact_id }`.
- Scene (live MCP canvas path, `ENABLE_MCP_SCENE_DIAGRAM=True` — current default): `agent_start { agent: "diagram_agent" }` → `diagram_draft { phase: "waiting_live_viewer" | "drawn", iteration?, element_count? }` → `diagram_iteration { iteration, phase: "draft" | "vision" | "approved", layout_hint? }` (repeats per iteration / inner pass) → `task_complete { agent: "diagram_agent" }` → `diagram_complete { iterations }` → `scene_ready` → `usage` → `persisted { scene_artifact_id }`.

Shared: `agent_start`, `text_delta`, `task_complete`, `usage`, `complete`, `error`. Research emits `tool_call` + `sources` for **every** search tool — Exa (`platform=web`), Reddit (`platform=reddit`), YouTube (`platform=youtube`), X (`platform=x`), Instagram (`platform=instagram`) — all flowing through the same `app.agents.research.streaming.sources_emitter_var` ContextVar. Each emitted `SourceRef` carries its `platform` tag; older clients that don't read `platform` simply default-render as `web`.
