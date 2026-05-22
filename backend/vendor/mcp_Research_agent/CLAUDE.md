# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run

```bash
# Install dependencies
uv pip install -e .

# Install dev dependencies
uv pip install -e ".[dev]"

# Start the server (backend + UI)
uv run python -m research_agent.main
```

Server runs at `http://localhost:8000` (dashboard) and `http://localhost:8000/docs` (Swagger).

## Lint

```bash
ruff check src/
```

Config: line-length 120, target py311, see `pyproject.toml` under `[tool.ruff]`.

## Architecture

**Pattern**: Orchestrator-Subagent with LangGraph. The pipeline is a sequential `StateGraph` with parallelism *inside* nodes, not across them. A shared `ResearchState` TypedDict flows through every node.

**6-Layer Pipeline** (wired in `src/research_agent/graph/orchestrator.py:build_research_graph`):

```
START → demand_side → comment_mining → supply_side → kg_filter → scoring → synthesis → verification → build_result → END
```

1. **Demand Side** (`graph/demand.py`): 5 agents run in parallel — WebSearch (Tavily+Exa), Reddit, YouTube, HackerNews (Algolia), PAA. Each emits `SourceRef` objects and raw comments.
2. **Comment Mining** (`graph/analysis.py:comment_mining_node` → `comment_mining.py`): Embed comments (text-embedding-3-small), k-means cluster, classify clusters for unmet asks via cheap LLM call. Outputs `CommentCluster` objects.
3. **Supply Side** (`graph/analysis.py:supply_side_node`): Pulls top YouTube videos, gap-detection prompt (recency/format/depth/sentiment), outputs `SupplySideReport`.
4. **KG Filter** (`graph/analysis.py:kg_filter_node` → `knowledge_graph.py`): Cross-references topic against creator's knowledge graph. `CreatorKG` is an ABC — both LadderFlow and Ladder Brief plug in their own backends. `SimpleKG` is the in-memory dev default (assumes "starting from zero").
5. **Scoring** (`graph/analysis.py:scoring_node` → `scoring.py`): 7-weight TrendScore formula. Hard gate: ≥2 platforms with positive velocity required. Weights are tunable via `ScoringWeights` dataclass.
6. **Synthesis** (`graph/synthesis.py`): 4 lens agents run in parallel (Strategy/Signal/Execution/Contrarian), each generates a one-sentence thesis. A moderator agent scores them (defendability × novelty × creator_fit × supply_gap) and picks the winner. All 4 candidates are surfaced (rejected ones include rejection reasons).
7. **Verification** (`graph/verification.py`): Two-question triage on winning thesis claims. Tiered evidence standards per claim type.

**State** (`graph/__init__.py`): `ResearchState` is a TypedDict with annotated reducers for lists (`merge_lists`) and events. All nodes read/write this shared dict.

**Contract** (`models.py`): `ResearchResult` is the unified output consumed by both LadderFlow and Ladder Brief. Key fields: `winning_thesis`, `rejected_candidates`, `sources`, `supply_side_report`, `unmet_asks`, `cost_breakdown`.

## Model Routing

LLM calls go through `tools/llm.py:llm_call()` which routes by model name prefix:
- `claude-*` → Anthropic (AsyncAnthropic)
- `gpt-*` / `o*` → OpenAI (AsyncOpenAI)
- `gemini-*` → Google (genai)

Models configured in `config.py:Settings`:
- `synthesis_model`: `claude-sonnet-4-20250514` (thesis generation, moderation)
- `summarization_model`: `claude-haiku-4-20250514` (gap detection, comment classification, verification)
- `classification_model`: `gemini-2.5-flash-preview-04-17`
- `embedding_model`: `text-embedding-3-small` (OpenAI)

Every LLM call tracks token usage and cost via `CostBreakdown.add_cost()`.

## Configuration

`.env` file loaded via pydantic-settings. All keys in `config.py:Settings`. Required for operation: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`. Search tools degrade gracefully if their API keys are not set (skip with warning).

## Supabase / Database Rule

**Do not use or recommend direct Postgres, Supabase Direct Connection, SQLAlchemy pooler debugging, `DATABASE_URL`, `psycopg2`, or raw asyncpg connection setup for Supabase in this repo going forward.**

Use the Supabase **Framework / Python client** approach instead:

- Prefer Supabase HTTPS client access over direct database sockets.
- Required env vars should be `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` or another explicitly chosen Supabase key, not direct DB credentials.
- Do not ask the user to debug port `5432` / `6543`, pooler hostnames, IPv4/IPv6, transaction pooler, session pooler, or DNS for Supabase Postgres.
- If persistence code needs work, implement it through the Supabase Python client (`supabase` package) and normal HTTPS requests.
- Keep local fallback behavior for development so the app can still run without Supabase.

The user explicitly does not want the direct connection approach used again.

## Key Design Rules

- **Hard gate**: A topic must register on ≥2 platforms to pass Layer 4 scoring. Single-platform signals are treated as noise.
- **Quality gates at the tool layer**: `reddit_min_score`, `youtube_min_views`, `hn_min_points`, and freshness windows are enforced in scraper code — bad data never enters the context window.
- **"Starting from zero" persona**: `SimpleKG` returns no history, meaning every topic scores high on gap. If the agent works for 0 followers, it works for everyone.
- **Cost target**: $0.70–$1.20 per research run. Model pricing table in `tools/llm.py:MODEL_PRICING`.
