"""Feature flags and shadow-mode helpers for product migration."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from research_agent.config import settings
from research_agent.models import ResearchResult

logger = logging.getLogger(__name__)


def unified_enabled(product: str) -> bool:
    if product == "ladderbrief":
        return settings.unified_agent_enabled_ladderbrief
    return settings.unified_agent_enabled_ladderflow


async def run_legacy_shadow(query: str, user_id: str, product: str) -> dict[str, Any] | None:
    """Call a legacy pipeline endpoint for side-by-side comparison when configured."""
    if not settings.shadow_mode_enabled or not settings.legacy_research_endpoint:
        return None

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(settings.legacy_research_endpoint, json={
                "query": query,
                "user_id": user_id,
                "product": product,
            })
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning(f"Legacy shadow run failed: {e}")
        return {"error": str(e)}


def compare_shadow_outputs(unified: ResearchResult, legacy: dict[str, Any] | None) -> dict[str, Any]:
    if not legacy:
        return {}
    return {
        "legacy_available": "error" not in legacy,
        "legacy_error": legacy.get("error"),
        "unified_status": unified.status,
        "unified_cost": unified.cost_breakdown.total,
        "unified_sources": len(unified.sources),
        "unified_thesis": unified.winning_thesis.statement if unified.winning_thesis else "",
        "legacy_summary": legacy.get("summary") or legacy.get("winning_thesis") or "",
    }
