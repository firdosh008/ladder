"""People Also Ask (PAA) + autocomplete via DataForSEO API."""

from __future__ import annotations

import base64
import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from research_agent.config import settings
from research_agent.models import CostBreakdown, SourceRef
from research_agent.tools.cache import get_json, make_cache_key, set_json

logger = logging.getLogger(__name__)

DATAFORSEO_BASE = "https://api.dataforseo.com/v3"


def _auth_header() -> dict:
    """Build DataForSEO Basic auth header."""
    creds = f"{settings.dataforseo_login}:{settings.dataforseo_password}"
    encoded = base64.b64encode(creds.encode()).decode()
    return {"Authorization": f"Basic {encoded}", "Content-Type": "application/json"}


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
async def search_paa(
    query: str,
    max_results: int = 10,
    cost_tracker: CostBreakdown | None = None,
) -> list[SourceRef]:
    """Get People Also Ask questions for a query via DataForSEO."""
    if not settings.dataforseo_login:
        logger.warning("DataForSEO credentials not set — skipping PAA")
        return []

    cache_key = make_cache_key("paa", query, max_results)
    cached = await get_json(cache_key)
    if cached is not None:
        return [SourceRef(**item) for item in cached]

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{DATAFORSEO_BASE}/serp/google/organic/live/advanced",
            headers=_auth_header(),
            json=[{
                "keyword": query,
                "location_code": 2840,  # US
                "language_code": "en",
                "device": "desktop",
            }],
        )
        resp.raise_for_status()
        data = resp.json()

    sources = []
    for task in data.get("tasks", []):
        for result in task.get("result", []):
            for item in result.get("items", []):
                if item.get("type") == "people_also_ask":
                    for paa_item in item.get("items", []):
                        question = paa_item.get("title", "")
                        snippet = paa_item.get("snippet", "")
                        url = paa_item.get("url", "")
                        if question:
                            sources.append(SourceRef(
                                title=question,
                                url=url,
                                snippet=snippet[:500] if snippet else question,
                                platform="paa",
                                engagement={"type": "people_also_ask"},
                                relevance_score=0.7,
                                source_agent="PAAAgent",
                            ))

    logger.info(f"PAA returned {len(sources)} questions for '{query}'")
    if cost_tracker:
        cost_tracker.add_cost("demand_side", "dataforseo:paa", "dataforseo", 0.0006)
    sources = sources[:max_results]
    await set_json(cache_key, [s.__dict__ for s in sources], settings.paa_cache_ttl_hours * 3600)
    return sources


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
async def search_autocomplete(query: str, max_results: int = 10) -> list[str]:
    """Get Google autocomplete suggestions (free via Google's public endpoint)."""
    cache_key = make_cache_key("autocomplete", query, max_results)
    cached = await get_json(cache_key)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://suggestqueries.google.com/complete/search",
            params={"client": "firefox", "q": query},
        )
        resp.raise_for_status()
        data = resp.json()

    suggestions = data[1] if len(data) > 1 else []
    logger.info(f"Autocomplete returned {len(suggestions)} suggestions for '{query}'")
    suggestions = suggestions[:max_results]
    await set_json(cache_key, suggestions, settings.paa_cache_ttl_hours * 3600)
    return suggestions
