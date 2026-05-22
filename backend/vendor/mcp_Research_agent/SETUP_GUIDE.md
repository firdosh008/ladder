# Research Agent MCP — Setup Guide

> **For:** Any developer or project integrating with the Standalone Research Agent MCP  
> **Last updated:** May 2026

---

## What Is This?

The Research Agent is a **standalone MCP (Model Context Protocol) server** that runs a 6-layer multi-platform research pipeline. It accepts a topic and returns a thesis-backed research report with source provenance, supply-side gap analysis, and audience signal mining.

**Any project** can call it — you don't need to know the internals. You send a query + optional context via JSON-RPC, and get back a structured `ResearchResult`.

### Pipeline Overview

```
Query → Demand Signals → Comment Mining → Supply Analysis → Context Filter → Scoring → Thesis Synthesis → Verification → Result
         (5 agents)       (k-means +        (YT gap         (caller        (7-weight    (4-lens +          (fact-
          parallel)        embeddings)        detection)       context)       formula)     moderator)         check)
```

**Platforms scraped in parallel:** Web (Tavily + Exa), Reddit, YouTube, Hacker News, People Also Ask, Supadata video transcripts.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Python** | ≥ 3.11 | Required. Python 3.12+ recommended |
| **uv** | Latest | Package manager. Install via `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Git** | Any | To clone the repo |
| **OS** | Windows / macOS / Linux | Tested on Windows, should work everywhere |

**Optional:**
- Redis / Upstash — for cross-process caching (falls back to in-memory)
- Supabase account — for persistent run storage (falls back to in-memory)

---

## Step 1: Clone the Repository

```bash
git clone <repo-url> research-agent
cd research-agent
```

---

## Step 2: Create Virtual Environment & Install Dependencies

```bash
# Create venv
uv venv

# Install the package (editable mode)
uv pip install -e .

# Optional: Install dev dependencies (tests, linting)
uv pip install -e ".[dev]"
```

> [!NOTE]
> The project uses `setuptools` with `pyproject.toml`. All dependencies are listed in `pyproject.toml` under `[project.dependencies]`.

---

## Step 3: Configure Environment Variables

Copy the example env file:

```bash
# Windows (PowerShell)
Copy-Item .env.example .env

# macOS / Linux
cp .env.example .env
```

Then edit `.env` with your actual API keys. Here's what each key does and which are required:

### 🔴 Required Keys (Agent won't produce useful output without these)

| Variable | Provider | Purpose | How to Get |
|----------|----------|---------|------------|
| `ANTHROPIC_API_KEY` | Anthropic | Thesis synthesis, moderation, summarization (Claude Sonnet) | [console.anthropic.com](https://console.anthropic.com/) |
| `OPENAI_API_KEY` | OpenAI | Comment embeddings (`text-embedding-3-small`) | [platform.openai.com](https://platform.openai.com/api-keys) |

> [!IMPORTANT]
> Without these two keys, the pipeline will fail on synthesis and comment mining — the two most important layers.

### 🟡 Recommended Keys (Significantly better results with these)

| Variable | Provider | Purpose | How to Get |
|----------|----------|---------|------------|
| `TAVILY_API_KEY` | Tavily | Breadth-first web search | [tavily.com](https://tavily.com/) |
| `EXA_API_KEY` | Exa | Semantic depth web search | [exa.ai](https://exa.ai/) |
| `SCRAPE_CREATORS_API_KEY` | ScrapeCreators | Reddit post search (better than public API) | [scrapecreators.com](https://scrapecreators.com/) |
| `SUPADATA_API_KEY` | Supadata | YouTube video search + transcript extraction | [supadata.ai](https://supadata.ai/) |
| `YOUTUBE_API_KEY` | Google | YouTube Data API (free, 10K units/day) | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) — enable "YouTube Data API v3" |

### 🟢 Optional Keys (Nice to have, agent degrades gracefully without them)

| Variable | Provider | Purpose | How to Get |
|----------|----------|---------|------------|
| `GOOGLE_API_KEY` | Google | Gemini Flash for cheap classification | [Google AI Studio](https://aistudio.google.com/apikey) |
| `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` | DataForSEO | People Also Ask + autocomplete data | [dataforseo.com](https://dataforseo.com/) |
| `APIFY_API_KEY` | Apify | YouTube comments fallback scraper | [apify.com](https://apify.com/) |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | Supabase | Persistent run storage & creator profiles | [supabase.com](https://supabase.com/) |
| `REDIS_URL` or `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN` | Redis / Upstash | Cross-process cache (24–72h TTL) | [upstash.com](https://upstash.com/) or local Redis |
| `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` | LangSmith | Pipeline tracing & debugging | [smith.langchain.com](https://smith.langchain.com/) |
| `SLACK_WEBHOOK_URL` | Slack | Cost alerts (> $3/run or > $50/day) | [api.slack.com](https://api.slack.com/messaging/webhooks) |

### Configuration Defaults

These can be set in `.env` but have sensible defaults:

| Variable | Default | Meaning |
|----------|---------|---------|
| `MAX_COST_PER_RUN` | `3.0` | Slack alert if a single run exceeds this ($) |
| `MAX_DAILY_SPEND` | `50.0` | Slack alert if daily spend exceeds this ($) |
| `YOUTUBE_COMMENTS_PROVIDER` | `apify` | Options: `apify`, `auto`, `none` |
| `SUPADATA_TRANSCRIPT_MODE` | `native` | Transcript extraction mode |
| `REDDIT_ALLOWED_SUBREDDITS` | (empty) | Comma-separated allowlist, e.g. `MachineLearning,artificial` |

> [!WARNING]
> **Never commit your `.env` file to Git.** Make sure `.gitignore` includes `.env`.

---

## Step 4: (Optional) Set Up Supabase Storage

If you want persistent run storage (recommended for production), create these tables in your Supabase project:

```sql
-- Research run results
create table if not exists research_runs (
    run_id text primary key,
    user_id text,
    product text,
    query text,
    status text,
    total_cost float,
    duration_seconds float,
    sources_count int,
    result_json jsonb,
    created_at timestamptz default now(),
    updated_at timestamptz
);

-- Creator context profiles (optional, for custom KG)
create table if not exists creator_profiles (
    user_id text primary key,
    context_json jsonb not null
);
```

> [!NOTE]
> **Without Supabase:** The agent still works — it stores runs in memory and logs to console. You just lose persistence across restarts.

---

## Step 5: Start the Server

```bash
# Using uv
uv run python -m research_agent.main

# Or activate the venv first
# Windows
.\.venv\Scripts\activate
python -m research_agent.main

# macOS / Linux
source .venv/bin/activate
python -m research_agent.main
```

The server starts at:
- **Dashboard UI:** [http://localhost:8000](http://localhost:8000)
- **Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check:** [http://localhost:8000/health](http://localhost:8000/health)
- **MCP Endpoint:** `POST http://localhost:8000/mcp`

---

## Step 6: Verify It Works

### Check Health

```bash
# PowerShell
Invoke-RestMethod http://localhost:8000/health

# curl
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "UP",
  "server": "standalone-research-agent-mcp",
  "version": "1.0.0",
  "tools": {
    "total": 4,
    "names": ["run_research", "get_research_result", "list_sources", "run_eval"]
  }
}
```

### List MCP Tools

```bash
# PowerShell
Invoke-RestMethod http://localhost:8000/mcp -Method Post -ContentType 'application/json' -Body '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# curl
curl -X POST http://localhost:8000/mcp -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

### Run a Quick Test Research

```bash
# PowerShell
Invoke-RestMethod http://localhost:8000/mcp -Method Post -ContentType 'application/json' -Body '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"run_research","arguments":{"query":"AI agents for customer support","context":{},"config":{"cost_ceiling":1.5},"output_mode":"research_report"}}}'

# curl
curl -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "run_research",
      "arguments": {
        "query": "AI agents for customer support",
        "context": {},
        "config": {"cost_ceiling": 1.5},
        "output_mode": "research_report"
      }
    }
  }'
```

> [!TIP]
> Set a low `cost_ceiling` (e.g. `1.5`) for your first test run to verify everything works without spending much.

---

## How to Integrate from Your Project

### The Contract

Your project calls one MCP tool: `run_research`. You send JSON-RPC requests and get back a structured result.

**Request format (JSON-RPC 2.0):**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "run_research",
    "arguments": {
      "query": "Your research topic or question",
      "context": {
        "niche_tags": ["B2B SaaS", "support automation"],
        "past_topics": ["AI chatbot setup guide"],
        "audience_description": "Founders and support leads",
        "voice_tone": "Practical, evidence-backed, direct"
      },
      "config": {
        "cost_ceiling": 3.0,
        "timeout_seconds": 300,
        "skip_platforms": [],
        "lens_preferences": null
      },
      "output_mode": "research_report",
      "input_type": "freeform",
      "user_id": "your-user-id"
    }
  }
}
```

### Arguments Explained

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `query` | string | ✅ Yes | The research topic, URL, or freeform brief |
| `context` | object | No | Your project/user context — niche, past topics, audience, tone. This replaces the creator KG for standalone usage |
| `config` | object | No | Per-run controls: `cost_ceiling`, `timeout_seconds`, `skip_platforms`, `lens_preferences` |
| `output_mode` | string | No | `"research_report"` (default). Legacy modes: `"ladderflow"`, `"ladderbrief"` |
| `input_type` | string | No | `"freeform"` (default), `"keywords"`, `"youtube_url"`, `"newsletter_url"` |
| `user_id` | string | No | User identifier for KG context lookup. Default: `"default"` |
| `run_id` | string | No | Caller-supplied run ID. Auto-generated if not provided |
| `async` | boolean | No | When `true`, starts run in background and returns `run_id` immediately for polling |

### Response Structure

The response is wrapped in MCP's JSON-RPC format. The key payload is inside `result.content[0].text`, which is a JSON string:

```json
{
  "success": true,
  "data": {
    "run_id": "uuid",
    "status": "complete",
    "winning_thesis": {
      "lens": "strategy",
      "statement": "One-sentence thesis",
      "supporting_points": ["Point 1", "Point 2", "Point 3"],
      "supply_side_rationale": "Why this content, because existing top videos miss X",
      "score": 7200.0
    },
    "rejected_candidates": [
      {
        "lens": "signal",
        "statement": "...",
        "rejection_reason": "Lower novelty score"
      }
    ],
    "sources": [
      {
        "title": "Source Title",
        "url": "https://...",
        "snippet": "...",
        "platform": "web|reddit|youtube|hackernews|paa|supadata",
        "engagement": {},
        "freshness_days": 5,
        "relevance_score": 0.85
      }
    ],
    "supply_side_report": {
      "top_content": [],
      "gaps": [
        {
          "gap_type": "recency|format|depth|sentiment",
          "confidence": 0.85,
          "description": "...",
          "evidence_urls": []
        }
      ],
      "overall_saturation": 0.4
    },
    "unmet_asks": [
      {
        "theme": "Audience wants deeper coverage of X",
        "frequency": 12,
        "unmet_ask": true,
        "representative_comments": ["...", "..."],
        "source_platform": "reddit"
      }
    ],
    "cost_breakdown": {
      "total": 0.85,
      "layer_costs": {},
      "tool_costs": {},
      "model_costs": {},
      "duration_seconds": 42.5
    },
    "score_breakdown": {
      "total_score": 0.65,
      "platform_count": 3,
      "platforms": ["web", "reddit", "youtube"],
      "passed": true
    },
    "verification_notes": [],
    "adapted_output": {}
  }
}
```

### Async / Background Runs

For long-running research (can take 30–120s), use async mode:

**Start async run:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "run_research",
    "arguments": {
      "query": "Your topic",
      "async": true
    }
  }
}
```

Returns immediately with `run_id` and `websocket_url`.

**Poll for result:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "get_research_result",
    "arguments": { "run_id": "the-run-id" }
  }
}
```

**Or stream via WebSocket:**
```
ws://localhost:8000/ws/research/{run_id}
```

Events streamed:
- `layer_start` / `layer_complete` — pipeline progress
- `agent_start` / `agent_complete` / `agent_error` — per-agent status
- `complete` — final result
- `error` — pipeline failure

---

## REST API (Alternative to MCP)

You can also use the REST API directly:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /api/research` | POST | Start a background research run |
| `GET /api/research/{run_id}` | GET | Get result of a completed run |
| `GET /api/health` | GET | Health check |
| `GET /api/ops/costs` | GET | Cost summary dashboard data |
| `GET /health` | GET | MCP-style health check |
| `POST /mcp` | POST | JSON-RPC 2.0 MCP endpoint |

---

## Integration Examples

### Python (httpx)

```python
import httpx

async def run_research(query: str, context: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post("http://localhost:8000/mcp", json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "run_research",
                "arguments": {
                    "query": query,
                    "context": context or {},
                    "config": {"cost_ceiling": 2.0},
                    "output_mode": "research_report",
                }
            }
        })
        result = resp.json()
        import json
        payload = json.loads(result["result"]["content"][0]["text"])
        return payload["data"]
```

### JavaScript / TypeScript (fetch)

```typescript
async function runResearch(query: string, context: Record<string, any> = {}) {
  const resp = await fetch("http://localhost:8000/mcp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "tools/call",
      params: {
        name: "run_research",
        arguments: {
          query,
          context,
          config: { cost_ceiling: 2.0 },
          output_mode: "research_report",
        },
      },
    }),
  });
  const result = await resp.json();
  const payload = JSON.parse(result.result.content[0].text);
  return payload.data;
}
```

### curl (Quick one-liner)

```bash
curl -s -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"run_research","arguments":{"query":"AI agents for SaaS","output_mode":"research_report"}}}' \
  | python -m json.tool
```

---

## Skipping Platforms

If you don't have certain API keys or want faster/cheaper runs, skip specific platforms:

```json
{
  "config": {
    "skip_platforms": ["paa", "supadata"],
    "cost_ceiling": 1.0
  }
}
```

Available platform names: `web`, `reddit`, `youtube`, `hackernews`, `hn`, `paa`, `supadata`, `supply_side`.

---

## Cost Expectations

| Scenario | Estimated Cost | Time |
|----------|---------------|------|
| Full run (all platforms, synthesis) | $0.70 – $1.20 | 30–90s |
| Cheap run (skip PAA + Supadata) | $0.40 – $0.80 | 20–60s |
| Minimal run (web + HN only) | $0.20 – $0.50 | 15–40s |

Costs are tracked per-run in `cost_breakdown` and logged to console.

---

## Project Structure

```
research-agent/
├── .env.example           # Template for env vars
├── pyproject.toml         # Dependencies and build config
├── src/research_agent/
│   ├── main.py            # FastAPI server + MCP endpoint + WebSocket
│   ├── models.py          # ResearchResult, SourceRef, Thesis, CostBreakdown
│   ├── config.py          # Settings loaded from .env
│   ├── adapters.py        # Output format adapters (research_report, ladderflow, ladderbrief)
│   ├── comment_mining.py  # Embed → cluster → classify unmet asks
│   ├── knowledge_graph.py # CreatorKG ABC + SimpleKG + SupabaseKG
│   ├── scoring.py         # 7-weight TrendScore formula
│   ├── storage.py         # Supabase HTTPS persistence
│   ├── ops.py             # LangSmith, cost alerts
│   ├── rollout.py         # Feature flags, shadow mode
│   ├── eval.py            # Evaluation harness
│   ├── graph/
│   │   ├── __init__.py    # ResearchState TypedDict
│   │   ├── orchestrator.py# LangGraph pipeline wiring
│   │   ├── demand.py      # Layer 1: 5 demand-side agents
│   │   ├── analysis.py    # Layers 2-4: supply, KG, scoring
│   │   ├── synthesis.py   # Layer 5: 4-lens thesis + moderator
│   │   └── verification.py# Layer 6: tiered fact-checking
│   └── tools/
│       ├── llm.py         # Multi-provider LLM router (Claude/GPT/Gemini)
│       ├── web_search.py  # Tavily + Exa
│       ├── reddit.py      # ScrapeCreators + Reddit JSON
│       ├── youtube.py     # YT Data API + Apify comments
│       ├── supadata.py    # Supadata YouTube search + transcripts
│       ├── hackernews.py  # Algolia HN API (free)
│       ├── paa.py         # DataForSEO PAA + Google autocomplete
│       ├── embeddings.py  # OpenAI text-embedding-3-small
│       └── cache.py       # Redis / Upstash / in-memory cache
├── tests/                 # Unit tests
├── ui/                    # Dashboard frontend (HTML/CSS/JS)
└── eval_dataset.example.json  # Sample eval dataset
```

---

## Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/test_mcp_contract.py -v
```

---

## Running the Linter

```bash
uv run ruff check src/
```

Config: line-length 120, target Python 3.11 (see `pyproject.toml`).

---

## Troubleshooting

### "Anthropic API key not set"
→ Check `ANTHROPIC_API_KEY` in `.env`. Make sure there are no trailing spaces.

### "Redis unavailable" warning
→ This is normal. The agent falls back to in-memory cache. Set `REDIS_URL` or `UPSTASH_REDIS_REST_URL` for persistent caching.

### "Supabase storage disabled" warning
→ This is normal. The agent stores runs in memory. Set `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` for persistence.

### Research run takes > 2 minutes
→ The full pipeline with all platforms can take 30–120s. For faster runs, use `skip_platforms` to disable slow providers.

### "Topic did not pass cross-platform corroboration"
→ The scoring layer requires a topic to appear on **≥2 platforms** to proceed to synthesis. This is by design — single-platform signals are treated as noise. Try a broader or more popular query.

### YouTube comments return empty
→ Check `YOUTUBE_API_KEY` and/or `APIFY_API_KEY`. Some videos have comments disabled. The agent handles this gracefully but returns fewer comment clusters.

### Port 8000 already in use
→ Kill the existing process or set a different port in `.env`:
```
# Not yet an .env var — edit src/research_agent/config.py:
port: int = 8001
```

---

## FAQ

**Q: Can multiple projects use this simultaneously?**  
A: Yes. The server is stateless per request. Each call gets its own `run_id`. Concurrent calls run in parallel.

**Q: Is there authentication?**  
A: Not currently. The server is designed for internal/local use. Add your own auth middleware if exposing externally.

**Q: Can I add a custom output format?**  
A: Yes. Add a new adapter function in `src/research_agent/adapters.py` and register the `output_mode` name.

**Q: What if I only need part of the pipeline?**  
A: Use `skip_platforms` to disable demand-side agents. The pipeline will still run all downstream layers with whatever data it collects.

**Q: How do I inject my project's creator/user context?**  
A: Pass it in the `context` argument of `run_research`. The agent uses it for KG alignment scoring. No need to modify the agent code.

---

> [!TIP]
> **Minimum viable setup:** `ANTHROPIC_API_KEY` + `OPENAI_API_KEY` + `TAVILY_API_KEY`. Everything else is optional and degrades gracefully.
