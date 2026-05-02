# Ladder Content OS — Handoff / Context Doc

Last updated: 2026-05-02. Purpose: bring a fresh session (or a human contributor) up to speed without re-reading the whole chat history.

**Recent (visual cut-over, 2026-05-02 — PR1 + PR2 LANDED):** The Excalidraw vertical is now driven by the live `mcp_excalidraw` MCP server + CrewAI Skills. The old `services/diagram_service.py` (Anthropic agent loop with 9 hand-rolled `diagram_*` REST tools) and its `POST /generate-diagram` route are **gone**. The "Generate Visual" button now opens a WebSocket to `/ws/agents/visual` and streams the live agent's tool calls + text deltas while it draws on the MCP canvas. The right-rail Sharpen chat is still a UI stub — that's PR3.

- One CrewAI agent (`StudioVisualAgent`, Sonnet 4.6) reused by **two flows** — `run_visual_build` (one-shot, PR2 LANDED) and `SharpenChatFlow` (long-lived chat with three modes: Refine text · Screenshot to edit · Regenerate scene; persists to `chat_messages`; PR3 PENDING).
- Tools: full 26-tool MCP surface from `yctimlin/mcp_excalidraw` via `crewai_tools.MCPServerAdapter` (stdio), plus 4 backend tools — `ScriptOutlineTool`, `BrandPaletteTool`, `KnowledgeRetrievalTool`, `PersistArtifactTool`.
- Skills (verbatim prompt injection): `excalidraw-canvas` (operational MCP tips), `excalidraw-diagram` (methodology — moved from `backend/excalidraw-diagram-skill-main/`, Playwright renderer dropped, render section repointed at MCP `get_canvas_screenshot`), `ladder-voice` (non-sycophantic / opinionated / voice-preserving). All three load at INSTRUCTIONS level via CrewAI's filesystem skill loader. User-uploaded `skill_files` inject per-turn in PR3.

Cut-over PRs:
- **PR1 (landed 2026-05-02):** scaffolding — `crewai-tools[mcp]` dep, skills folder moved + authored, `app/agents/visual/{__init__,agent,tools,mcp,skills,context}.py`, settings + `.env.example` extended.
- **PR2 (landed 2026-05-02):** `run_visual_build` async generator + `WS /ws/agents/visual` route (`backend/app/routes/visual.py`) + frontend `runVisualBuild` WS client + `SceneRunPanel` repointed. Deleted: `services/diagram_service.py` (610 lines), `services/excalidraw_http.py` (175 lines), `routes/diagram.py` (179 lines), `tests/test_diagram_route.py`, `app/agents/scene/` (shim), `DIAGRAM_ANTHROPIC_MODEL` + `DIAGRAM_AGENT_MAX_TURNS` settings. Backend: **67 passing** (legacy diagram-route test was the only loss). Frontend `npx tsc --noEmit` clean. Frontend dropped: `generateDiagramFromScript`, `GenerateDiagramResponse`, `buildDiagramScriptInput`. New event type `scene_ready` carries the final scene JSON. Live activity tail (most recent tool call name / text-delta tail) surfaces under the strip while the agent draws.
- **PR3 (next):** `SharpenChatFlow` + WS `/ws/agents/sharpen`. Real `chat_messages` persistence. `SkillDropdown` reads `skill_files` rows. Frontend `ChatPanel.send()` rewired to WS pump.

Open implementation calls (all confirmed 2026-05-02): per-WS adapter spawn (option a), single shared canvas for local dev, browser → `ws://localhost:3000` direct (proxy lands when hosted), hybrid skills storage (system in repo, user in Storage), kill the legacy "Generate Visual" path entirely (chat is the only refinement entry), Sonnet 4.6.

**Earlier (research vertical, 2026-04-26):** Research crew fans out across **5 platforms in parallel** — Exa (web), Reddit, YouTube, X, Instagram. Single async HTTP wrapper at `app/providers/scrapecreators.py` covers the four social platforms via the **ScrapeCreators API** (`SCRAPECREATORS_API_KEY`); provider returns normalized dataclasses (`RedditPost`, `YouTubeVideo`, `XTweet`, `InstagramReel`) so swapping to official APIs later only changes that file. Each tool emits **platform-tagged** `SourceRef`s through the existing `sources_emitter_var` side-channel; the `ResearchRunPanel` source rail renders a colored pill (web/reddit/yt/x/ig) on every card. ScrapeCreators is the temporary unified backend until per-platform official APIs come online (Reddit OAuth, YouTube Data API v3, etc.).

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
10. **Structured artifacts use Anthropic structured outputs, not CrewAI `output_pydantic`.** CrewAI's `output_pydantic` injects the schema into the system prompt and asks nicely. That's fine for small/flat schemas (`Script`, `Outline`, `ResearchIdeas`). For **large nested schemas** the model regularly drops required arrays under in-context bias. Use `client.messages.create(extra_body={"output_format": {"type": "json_schema", "schema": <pydantic>.model_json_schema()}}, extra_headers={"anthropic-beta": "structured-outputs-2025-11-13"})` for those. Strip Anthropic-unsupported keywords (`minimum`/`maximum`/`minLength`/`maxLength`/`pattern`/`format`/`default`) from the schema before sending; Pydantic still validates server-side. **Note (post 2026-05-02):** the new visual agent doesn't produce a structured artifact — it drives a live MCP canvas via tool calls — so this rule does not apply there. The canvas state is exported via `export_scene` (an MCP tool) and persisted as a versioned `excalidraw` artifact by `PersistArtifactTool`.
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
│   │   │   ├── llm.py                    # anthropic_llm() — CrewAI LLM factory
│   │   │   └── usage.py                  # log_usage() async context manager
│   │   ├── agents/
│   │   │   ├── research/                 # research crew (3 agents → ResearchIdeas)
│   │   │   ├── studio/                   # studio crew (script_writer → outline_planner)
│   │   │   ├── content_extract/          # content_extract crew (analyzer → extractor)
│   │   │   └── visual/                   # PR2 LANDED: StudioVisualAgent + run_visual_build (BuildVisualFlow) + 4 backend tools + MCP adapter + skill loader. SharpenChatFlow ships in PR3.
│   │   └── routes/
│   │       ├── health.py                 # GET /health
│   │       ├── auth.py                   # GET /auth/me, POST /auth/onboard
│   │       ├── ideas.py                  # GET/POST/PATCH/DELETE /ideas
│   │       ├── studio_sessions.py        # GET /studio-sessions/by-idea/{id}, POST …/scene/share
│   │       ├── agents.py                 # WebSocket /ws/agents/{research,studio,extract}
│   │       └── visual.py                 # WebSocket /ws/agents/visual (PR2 LANDED)
│   ├── skills/                           # NEW (2026-05-02): system skills loaded by visual agent. Verbatim prompt injection.
│   │   ├── excalidraw-canvas/SKILL.md         # operational MCP tool tips
│   │   ├── excalidraw-diagram/                # methodology + references/ (color-palette, element-templates, json-schema). Moved from backend/excalidraw-diagram-skill-main/.
│   │   └── ladder-voice/SKILL.md         # non-sycophantic / voice-preserving rules
│   ├── vendor/mcp_excalidraw/            # cloned yctimlin/mcp_excalidraw checkout (gitignored). dist/server.js = canvas, dist/index.js = MCP stdio. Build with `npm ci && npm run build` once.
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

### AI — Visual + Sharpen vertical (PR2 landed 2026-05-02; PR3 pending)

The Excalidraw vertical is now driven by the live `mcp_excalidraw` MCP server + CrewAI Skills. The legacy `DiagramService` Anthropic-loop agent and the prior `SceneSkeleton` hybrid crew are both **gone**. See top-of-file "Recent (visual cut-over)" for the headline summary.

**Backend (PR1 + PR2 landed):**
- `backend/pyproject.toml` adds `crewai-tools[mcp]` (lockfile: `crewai-tools==1.14.2`, `mcpadapt==0.1.20`).
- `backend/skills/` populated: `excalidraw-canvas/SKILL.md` (~75 lines operational MCP tool tips — tool ordering, batching, snapshot discipline, screenshot-fix loop), `excalidraw-diagram/SKILL.md` (the 552-line methodology, moved here from `backend/excalidraw-diagram-skill-main/`; render section repointed at MCP `get_canvas_screenshot` / `export_to_image`; Playwright renderer + helper files dropped), `ladder-voice/SKILL.md` (~50 lines non-sycophantic working rules). `excalidraw-diagram/references/` keeps `color-palette.md` + `element-templates.md` + `json-schema.md`. CrewAI 1.14.2 supports `Agent(skills=[Path,...])`; the discoverer walks **child folders** of each path so we hand it the parent `backend/skills/` once.
- `backend/app/agents/visual/` package:
  - `agent.py` — `build_visual_agent(context, mcp_tools, *, extra_skill_paths=None, temperature=0.45)` factory. One CrewAI `Agent` reused by both flows. Backstory anchors session facts; methodology lives in the skills. Bound to Sonnet 4.6 via `VISUAL_AGENT_ANTHROPIC_MODEL` + `services/llm.py`'s extended `anthropic_llm(*, model=...)`.
  - `tools.py` — four backend `BaseTool`s (`ScriptOutlineTool`, `BrandPaletteTool`, `KnowledgeRetrievalTool`, `PersistArtifactTool`). State (`jwt`, `user_id`, `session_id`, `brand`) declared as Pydantic fields. `KnowledgeRetrievalTool` gracefully returns `{items: []}` when `OPENAI_API_KEY` is unset (embedding pipeline is §6 P1 #9 — separate ship).
  - `mcp.py` — `mcp_excalidraw_tools()` cm wraps `mcpadapt.MCPAdapt(StdioServerParameters(command="node", args=[<vendor>/dist/index.js], env={EXPRESS_SERVER_URL: settings.EXCALIDRAW_HTTP_URL, **os.environ}), _SanitisingCrewAIAdapter())`. Sanitiser flattens upstream's multi-type JSON schemas (`type: [...]`) to a single type so CrewAI's strict converter accepts them — see "Multi-type JSON Schema mismatch" postmortem below. Per-WS spawn (option a in the cut-over decisions), tears down on exit.
  - `skills.py` — `system_skill_paths()` returns `[Path(backend/skills)]` so CrewAI's discoverer enumerates all three system skills in one entry. Empty-folder defensive.
  - `context.py` — `SessionContext` Pydantic model + `load_session_context(user_id, jwt, session_id)` async loader. Rehydrates idea + profile + brand + latest script + latest outline from Supabase under RLS via `user_client(jwt)`.
  - `build.py` — `run_visual_build(context, *, steer_note=None) -> AsyncIterator[event]`. Boots the canvas (`excalidraw_canvas.ensure_canvas_running` is also called from FastAPI lifespan, but the build re-checks as a safety net), opens the MCP cm, kicks off `Crew(stream=True)` with one Task, streams chunks → wire events. Final stretch pulls `export_scene` (or `get_scene` / `describe_scene`) from MCP, persists a versioned `excalidraw` artifact via `user_client` (RLS enforced — never service-role here), emits `scene_ready` + `persisted` + `usage` + `complete`. Wraps in `log_usage("visual_build_crew", model=VISUAL_AGENT_ANTHROPIC_MODEL)` per §3 #8.
  - `__init__.py` — re-exports `run_visual_build`.
- `backend/app/routes/visual.py` — `WS /ws/agents/visual?token=…&session_id=…&steer=…`. Auth via `verify_ws_token`. Loads `SessionContext`, streams `run_visual_build` events. Same close-code convention as research/studio (4401 / 4400 / 1011). Registered in `app/main.py`.
- Settings (`backend/app/config.py`): `VISUAL_AGENT_ANTHROPIC_MODEL = "claude-sonnet-4-6"`, `VISUAL_AGENT_MAX_ITER = 36`, `MCP_EXCALIDRAW_ENTRY = "dist/index.js"`. `DIAGRAM_*` settings deleted.

**Frontend (PR2):**
- `frontend/src/lib/agents.ts` — added `runVisualBuild(sessionId, opts={steer?}, onEvent)` returning `{scene, scene_artifact_id, cost_usd}`. Removed `generateDiagramFromScript`, `GenerateDiagramResponse`, `buildDiagramScriptInput`. `AgentEvent` gained `scene_ready` carrying the final `Scene`.
- `frontend/src/components/scene/SceneRunPanel.tsx` — `startRun()` opens the WS via `runVisualBuild`. Surfaces an `activity` tail under the strip (most recent tool call name / text-delta tail) so the user sees something while the agent draws. Dropped the `diagramScript` prop entirely — the agent reads script + outline through its own `get_script_and_outline` tool.
- `frontend/src/pages/Studio.tsx` — dropped `buildDiagramScriptInput` import + the derived `diagramScript` memo; `<SceneRunPanel>` no longer receives `diagramScript`.

**Verified (2026-05-02):**
- Backend: `uv run pytest -q` → **67 passed, 2 xfailed, 3 xpassed**. Drop from 68 is the deleted `tests/test_diagram_route.py` only.
- Frontend: `npx tsc --noEmit` clean.
- Smoke: routes registered as `/ws/agents/{research,studio,extract,visual}`. Diagram route is gone.

**Local-dev runtime requirement (unchanged from prior commit):**
`backend/vendor/mcp_excalidraw/` must be a clone of `yctimlin/mcp_excalidraw` with `npm ci && npm run build` run once. That produces:
- `dist/server.js` — Express + Vite canvas (port 3000); FastAPI lifespan auto-spawns it.
- `dist/index.js` — MCP stdio adapter; the visual flow spawns this per-WS via `MCPServerAdapter`. The MCP server reads `EXPRESS_SERVER_URL` to find the canvas.

**Still ahead (PR3):**

- **`SharpenChatFlow`** — long-lived WS at `/ws/agents/sharpen?token=…&session_id=…`. Three modes from the existing `ChatPanel.tsx`:
  - **Refine text** — agent told "no canvas tools allowed this turn"; edits script/outline in-place. Emits `script_delta` / `outline_delta` for the left pane to pick up.
  - **Screenshot to edit** — user pastes PNG → agent uses MCP `query_elements` + Sonnet vision → JSON diff → `update_element`/`delete_element`/`batch_create_elements` → confirms.
  - **Regenerate scene** — proxies into `BuildVisualFlow` with the user's steer note pre-pended; outline preserved per PRD §11.5.
  - Per-turn write to `chat_messages`. PRD §11.7 budget: last 15 turns verbatim + rolling summary, total ~18K tokens/turn. User-uploaded `skill_files` from Storage inject as one extra skill on the turn they're picked.

**Open implementation calls (locked 2026-05-02):**
1. **Per-WS-connection MCP adapter spawn** (option a): each `BuildVisualFlow` / `SharpenChatFlow` opens `mcp_excalidraw_tools()` for its lifetime. Slow first boot; clean lifecycle. Singleton-adapter alternative rejected — would mix tool calls across users.
2. **Single shared canvas** for local dev (one Node `dist/server.js` on port 3000, managed by `services/excalidraw_canvas.py`). Hosted multi-tenant canvas isolation is a separate item — needs upstream rooms or per-session subprocess.
3. **Browser → `ws://localhost:3000` direct** for live canvas updates (the canvas server already broadcasts WebSocket frames on every element change). Hosted version proxies through FastAPI.
4. **Hybrid skills storage** — system skills in repo (`backend/skills/`), user-uploaded skills in Supabase Storage (referenced via `skill_files` table). System skills load every turn; user skill loads on selection.
5. **Single entry point for visual generation = chat.** No "quick draw without chat" path. Chat agent's `regenerate scene` mode covers it. The legacy `SceneRunPanel`'s "Generate Visual" button stays in PR2 but calls the new endpoint, not the old one.
6. **Sonnet 4.6** for the visual agent — diagram-driving with vision + multi-turn MCP needs the headroom.

**Don't repeat:** the prior cut-over (commit `33d206d`, "fix the canvas implementation using mcp") replaced the structured-outputs designer with a hand-rolled Anthropic agent loop that exposed only 9 of the 26 MCP tools and bypassed the MCP protocol entirely (talked REST directly). It also never injected the methodology skill (552 lines sitting on the floor at `backend/excalidraw-diagram-skill-main/SKILL.md`, never reaching the system prompt). The visual cut-over fixes both.

**Multi-type JSON Schema mismatch (PR2 hot-fix, 2026-05-02):** the upstream MCP server's tool definitions use `type: ["string", "number"]` for `fontFamily` (and may add similar fields later). `mcpadapt`'s schema converter handles this fine, but `crewai_tools.MCPServerAdapter` then re-runs the schema through CrewAI's strict `crewai.utilities.pydantic_schema_utils.create_model_from_schema`, which raises `Unsupported JSON schema type: ['string', 'number']`. We bypass `MCPServerAdapter` entirely and use `mcpadapt.MCPAdapt` directly with a tiny `_SanitisingCrewAIAdapter` subclass that flattens multi-type properties to a single non-null type before delegating. The upstream server's `normalizeFontFamily()` accepts both names and numeric IDs at runtime, so narrowing to `string` doesn't lose behaviour. Don't fix this by patching `vendor/mcp_excalidraw/src/index.ts` — the sanitiser survives upstream re-clones / re-builds and absorbs future multi-type fields automatically.

**Anthropic strict-mode caps (PR2 hot-fix, 2026-05-02):** Anthropic's API caps `strict` tools at 20/request AND union-typed parameters at 16/request. CrewAI 1.14.2 hardcodes `"strict": True` on every tool it builds (`crewai.utilities.agent_utils.convert_tools_to_openai_schema`, line 207). The visual agent's MCP toolkit blows past both caps: 30 tools = `400 Too many strict tools (30)`; even after trimming to 16, optional MCP fields produce 45 unions = `400 too many parameters with union types`. Two complementary fixes in PR2:

1. **Disable strict mode globally** — `app/services/llm.py` runs `_install_tool_schema_patches()` at module import, monkey-patching `convert_tools_to_openai_schema` to pop `strict` off every tool dict. The Anthropic provider then reads `bool(func_info.get("strict")) → False` and skips the strict path entirely; no caps apply. Idempotent (marker attribute on the wrapper). Disabling strict trades grammar-constrained tool calls for more permissive tool calls — fine here because CrewAI's own retry handles malformed calls. The patch ALSO walks `sys.modules` and rebinds the symbol in every consumer that already grabbed a reference (e.g. `crewai.agents.crew_agent_executor` does `from … import convert_tools_to_openai_schema`, copying the function reference into its own namespace — reassigning at the source module isn't enough). Affects every CrewAI agent in this process (research/studio/extract/visual), which is correct — none of them benefit meaningfully from strict.

2. **Build-tool whitelist** still applies — `app/agents/visual/mcp.py` (`ALL_VISUAL_MCP_TOOLS`, 11 tools — CRUD + inspect + viewport + snapshots + final read). The whitelist is then sub-divided into per-agent slices (see "Three-agent split" below).

**Why not switch providers?** DeepSeek was considered (OpenAI-compatible, cheaper). Their strict mode is **more** restrictive — "all properties of every object must be set as required, and `additionalProperties: false`" — and most MCP tools have many optional fields. Without DeepSeek strict mode, function calling works but the visual agent loses Sonnet 4.6's vision (load-bearing for screenshot loops + PR3 screenshot-to-edit). Stay on Sonnet 4.6 with strict disabled.

**Three-agent split (PR2.5, 2026-05-02):** the strict-off patch alone wasn't enough — Anthropic's separate **16-union-typed-parameter cap** still fired because CrewAI's pydantic round-trip wraps every optional MCP field in `anyOf: [<type>, {type: null}]` (~45 unions across the 16-tool whitelist). Two fixes were tried and abandoned: (a) `tool_search` lazy loading via `AnthropicCompletion` — Anthropic validates *every* tool's schema upfront even when `defer_loading=True`, so the cap still fired; (b) stripping the null branch via `crewai.utilities.pydantic_schema_utils.strip_null_from_types` in the same patch site — got under the API cap, but the agent kept emitting literal `null` for optional fields and the MCP server's Zod validators (`vendor/mcp_excalidraw/src/index.ts`) rejected the calls. **The shipped fix is to split the visual agent into three agents with disjoint tool sets so each per-agent API request stays under 16 unions naturally — no schema modification.**

Per-tool union count (raw, no patches — verified 2026-05-02):
- `batch_create_elements`: 16 (one per optional field per element item)
- `update_element`: 14
- `query_elements`: 7
- `set_viewport`: 5
- `get_canvas_screenshot` / `export_scene` / `persist_scene_artifact`: 1 each
- everything else: 0

Per-agent split:

| Agent (wire key) | Tools | Unions | Role |
|---|---|---|---|
| `visual_planner` | `get_script_and_outline`, `get_brand_palette`, `search_founder_knowledge`, `describe_scene`, `query_elements` | **7** | Reads source material + (if canvas non-empty) inspects existing state. Outputs a free-text plan. No drawing tools. |
| `visual_drawer` | `batch_create_elements`, `delete_element`, `clear_canvas`, `align_elements`, `snapshot_scene`, `restore_snapshot` | **16** | Executes the plan on the canvas. Receives planner output (and on refine passes, the critic's notes) as task context. **No `update_element`** — edit pattern is delete + batch_create. |
| `visual_critic` | `get_canvas_screenshot`, `describe_scene`, `query_elements`, `set_viewport`, `export_scene`, `persist_scene_artifact` | **15** | Screenshots the canvas, audits, returns either `VERDICT: PASS` (and persists) or `VERDICT: FIX` + numbered notes (back to drawer). Sonnet 4.6 vision is load-bearing. |

`update_element` is dropped entirely. The "edit" pattern is delete-and-recreate — Excalidraw elements are cheap, so the critic returns a list of element ids to delete plus a list of new elements to create, and the drawer applies it via `delete_element` + `batch_create_elements`. Loses some token efficiency vs. an in-place patch, but keeps every per-agent API request under the cap with zero schema patches.

Orchestration (`app/agents/visual/build.py:run_visual_build`):
1. Open `mcp_excalidraw_tools(tool_names=ALL_VISUAL_MCP_TOOLS)` once for the whole run — one Node subprocess, slice the tool list per-agent.
2. **Planner kickoff** (one CrewAI `Crew(stream=True)` with one task) → emit events tagged `visual_planner`. Capture the planner's output text as the `plan_brief`.
3. **Drawer kickoff** with `plan_brief` injected into the task description → emit events tagged `visual_drawer`.
4. **Refine loop** up to `VISUAL_REFINE_MAX_ITERS` iterations:
   a. **Critic kickoff** → emit events tagged `visual_critic`. Parse `VERDICT: PASS|FIX` from the final task output.
   b. If `PASS`, break. Otherwise inject the critic's `notes` into a new drawer task description and re-kickoff the drawer.
5. **Final stretch** — pull `export_scene` from MCP (defence-in-depth re-persist if the critic skipped it), emit `scene_ready` + `persisted` + `usage` (sum of all per-Crew `streaming.result.token_usage`) + `complete`.

Settings (`backend/app/config.py`):
- `VISUAL_AGENT_ANTHROPIC_MODEL = "claude-sonnet-4-6"` — used by all three agents.
- `VISUAL_AGENT_MAX_ITER = 24` — per-agent CrewAI tool-call cap (drawer hits this hardest).
- `VISUAL_REFINE_MAX_ITERS = 3` — max critic-drawer refine cycles before we ship whatever's on the canvas.

Wire-event protocol unchanged from PR2 except for `agent` field values: `visual_planner` / `visual_drawer` / `visual_critic` instead of `visual_director`. The frontend's `SceneRunPanel` already handles arbitrary agent names through the generic `text_delta` / `tool_call` events — no map update needed.

**Reading the new flow when adding features (e.g. PR3 sharpen):** PR3's `SharpenChatFlow` should reuse the same building blocks PR2 wired — `mcp_excalidraw_tools()` cm, `build_visual_agent(context, mcp_tools, extra_skill_paths=...)`, and the same wire-event protocol. The chat loop differs only in shape: a long-lived WS that accepts user turns interleaved with tool calls (CrewAI Flow with `@listen("user_message")`), and per-turn writes to `chat_messages`. The agent itself is the same.

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
1. **Visual cut-over PR3 — `SharpenChatFlow` + WS.** Replaces `ChatPanel.send()`'s stub. WS at `/ws/agents/sharpen?token=…&session_id=…`. Three modes: Refine text · Screenshot to edit · Regenerate scene. Real `chat_messages` persistence (table already exists). `SkillDropdown` reads `skill_files` rows; selected skill loads from Storage and injects per-turn (capped per PRD §11.7). Reuses the same `build_visual_agent` factory + `mcp_excalidraw_tools` cm PR2 shipped — only the loop shape changes.
3. **gen_outline polish** — Inline editing for the scene outline (rename / reorder / add / delete frames) per PRD.
4. **gen_thumbnail** — DALL·E 3 (or product-chosen) variants, refinement loops, reference URL flow.
5. **Approve-and-build gating** — `outline_approved` + button semantics so regens are intentional.
6. **Studio header pills** — Output type, brand, duration: interactive pills + regen affordances, three-zone duration slider.
7. **Error recovery** — e.g. retry from step, "taking longer" copy (no silent fallbacks; align with product rules).
8. **Optional later:** reintroduce a **critic** or post-validator only if the visual agent's output needs automated QA (e.g. arrow-binding sanity, label uniqueness across the canvas). Don't put it back as a CrewAI `output_pydantic` task. Run it as a second Anthropic call (vision + structured outputs) over the persisted `excalidraw` artifact, returning a list of fixups the visual agent then applies via MCP tools.

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

## 10. What to do next session (suggested)

The visual cut-over (§5 "Visual + Sharpen vertical") is the active workstream. PR1 + PR2 have landed (Generate Visual now drives the live MCP canvas via `/ws/agents/visual`). **PR3 is next** — wire the right-rail Sharpen chat: WS `/ws/agents/sharpen`, three modes (Refine text / Screenshot to edit / Regenerate scene), real `chat_messages` persistence, real `skill_files` dropdown.

Parallel tracks (§6 P1 #9–11) — embedding pipeline + retrieval — would unlock `KnowledgeRetrievalTool` (today it gracefully degrades to `{items: []}`).

When touching agents: follow the existing **native `Crew(stream=True)`** pattern in `research/`, `studio/`, and `content_extract/` — do not reintroduce threaded `step_callback` bridges. The new visual agent doesn't produce a structured artifact (it drives MCP tool calls), so the §3 #10 standing rule about Anthropic structured outputs does not apply there; use it for any future Skeleton-shaped output instead.

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
- **Visual (PR2 LANDED):** `agent_start` (`agent: "visual_director"`), `tool_call` for every MCP / backend tool the agent invokes (e.g. `batch_create_elements`, `get_canvas_screenshot`, `update_element`, `persist_scene_artifact`), `text_delta` for narrative reasoning, `task_complete` once the single build task finishes, `scene_ready` carrying the final `Scene` JSON, `persisted` with `scene_artifact_id`, `usage`, then `complete`. The frontend may additionally subscribe directly to `ws://localhost:3000` (the canvas server's own WebSocket) for real-time canvas frames — that channel is **separate** from `/ws/agents/visual` and is not auth'd in local dev.
- **Sharpen (PR3, PENDING):** terminal events depend on mode — `script_delta` / `outline_delta` for "Refine text", `tool_call` + `scene_ready` for "Screenshot to edit" and "Regenerate scene", plus `chat_message_persisted` per turn for `chat_messages` writes.

Shared: `agent_start`, `text_delta`, `task_complete`, `usage`, `complete`, `error`. Research emits `tool_call` + `sources` for **every** search tool — Exa (`platform=web`), Reddit (`platform=reddit`), YouTube (`platform=youtube`), X (`platform=x`), Instagram (`platform=instagram`) — all flowing through the same `app.agents.research.streaming.sources_emitter_var` ContextVar. Each emitted `SourceRef` carries its `platform` tag; older clients that don't read `platform` simply default-render as `web`.
