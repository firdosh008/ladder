# Standalone Research Agent

A standalone, multi-platform research engine with a FastAPI UI and a direct JSON-RPC 2.0 MCP endpoint. The core agent is project-neutral: external projects pass their own `query`, `context`, `config`, and `output_mode`.

Legacy LadderFlow and Ladder Brief output adapters still exist, but the default contract is:

```json
{
  "query": "AI agents for customer support",
  "context": {},
  "config": {},
  "output_mode": "research_report"
}
```

## Quick Start

```powershell
uv venv
uv pip install -e .
uv run python -m research_agent.main
```

Open the dashboard at [http://localhost:8000](http://localhost:8000). The UI calls the MCP `run_research` tool through `POST /mcp`.

## MCP Tools

The server implements MCP over plain HTTP JSON-RPC. It does not depend on an MCP SDK.

- `run_research`: run the full research pipeline and return a completed report
- `get_research_result`: fetch a completed run by `run_id`
- `list_sources`: list source references for a completed run
- `run_eval`: run the local eval harness

List tools:

```powershell
Invoke-RestMethod http://localhost:8000/mcp -Method Post -ContentType 'application/json' -Body '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Run research:

```powershell
Invoke-RestMethod http://localhost:8000/mcp -Method Post -ContentType 'application/json' -Body '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"run_research","arguments":{"query":"AI agents for customer support","context":{},"config":{},"output_mode":"research_report"}}}'
```

## Pipeline

1. Demand-side signals from web, Reddit, YouTube/Supadata, Hacker News, and People Also Ask.
2. Comment mining for audience unmet asks.
3. Supply-side analysis for existing content and gaps.
4. Caller-provided context filter using the `context` object.
5. Trend scoring and cross-platform corroboration.
6. Four-lens synthesis.
7. Verification and report assembly.

## Multi-Project Usage

Treat this repo as one independent research service. Other projects should call MCP with their own context instead of depending on project-specific state inside the agent.

Example `context`:

```json
{
  "niche_tags": ["B2B SaaS", "support automation"],
  "past_topics": ["AI chatbot setup guide"],
  "audience_description": "Founders and support leads",
  "voice_tone": "Practical, evidence-backed, direct"
}
```

Use `output_mode: "research_report"` for neutral output. Request `ladderflow` or `ladderbrief` only when a legacy adapter is explicitly needed.
