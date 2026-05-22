"""Operational monitoring helpers: tracing env, cost summaries, and alerts."""

from __future__ import annotations

import logging
import os

import httpx

from research_agent.config import settings
from research_agent.models import ResearchResult
from research_agent.storage import recent_costs

logger = logging.getLogger(__name__)


def configure_langsmith() -> None:
    """Enable LangSmith tracing for LangChain/LangGraph integrations when configured."""
    if not settings.langsmith_api_key:
        return
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
    os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)


async def maybe_send_cost_alert(result: ResearchResult) -> None:
    if not settings.slack_webhook_url:
        return
    if result.cost_breakdown.total > settings.max_cost_per_run:
        await _send_slack_alert(
            f"Research run {result.run_id} cost ${result.cost_breakdown.total:.2f}, "
            f"above ${settings.max_cost_per_run:.2f}."
        )


async def cost_summary(limit: int = 500) -> dict:
    rows = await recent_costs(limit=limit)
    costs = [row["total_cost"] for row in rows]
    durations = [row["duration_seconds"] for row in rows]
    return {
        "runs": len(rows),
        "cost": _distribution(costs),
        "latency_seconds": _distribution(durations),
        "daily_spend_estimate": sum(costs),
    }


async def _send_slack_alert(text: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(settings.slack_webhook_url, json={"text": text})
    except Exception as e:
        logger.warning(f"Slack alert failed: {e}")


def _distribution(values: list[float]) -> dict:
    if not values:
        return {"avg": 0, "p50": 0, "p95": 0, "p99": 0}
    ordered = sorted(values)
    return {
        "avg": round(sum(ordered) / len(ordered), 4),
        "p50": round(_percentile(ordered, 50), 4),
        "p95": round(_percentile(ordered, 95), 4),
        "p99": round(_percentile(ordered, 99), 4),
    }


def _percentile(ordered: list[float], percentile: int) -> float:
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * percentile / 100
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight
