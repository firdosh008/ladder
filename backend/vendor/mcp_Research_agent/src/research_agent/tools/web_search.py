"""Tavily (breadth) + Exa (semantic depth) web search tools."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from tenacity import retry, stop_after_attempt, wait_exponential

from research_agent.config import settings
from research_agent.models import SourceRef

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def tavily_search(query: str, max_results: int = 10) -> list[SourceRef]:
    """Breadth-first web search via Tavily."""
    from tavily import AsyncTavilyClient

    if not settings.tavily_api_key:
        logger.warning("Tavily API key not set — skipping")
        return []

    client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    resp = await client.search(
        query=query,
        max_results=max_results,
        search_depth="advanced",
        include_raw_content=False,
    )

    sources = []
    for r in resp.get("results", []):
        sources.append(SourceRef(
            title=r.get("title", ""),
            url=r.get("url", ""),
            snippet=r.get("content", "")[:500],
            platform="web",
            engagement={"score": r.get("score", 0)},
            relevance_score=r.get("score", 0),
            source_agent="WebSearchAgent",
        ))
    logger.info(f"Tavily returned {len(sources)} results for '{query}'")
    return sources


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def exa_search(query: str, max_results: int = 10, days_back: int = 90) -> list[SourceRef]:
    """Semantic depth search via Exa."""
    from exa_py import Exa

    if not settings.exa_api_key:
        logger.warning("Exa API key not set — skipping")
        return []

    start_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

    client = Exa(api_key=settings.exa_api_key)
    import asyncio
    resp = await asyncio.to_thread(
        client.search,
        query=query,
        num_results=max_results,
        start_published_date=start_date,
        contents={"text": {"max_characters": 500}},
    )

    sources = []
    for r in resp.results:
        score = getattr(r, "score", None)
        sources.append(SourceRef(
            title=r.title or "",
            url=r.url or "",
            snippet=(r.text or "")[:500],
            platform="web",
            engagement={"score": score or 0},
            relevance_score=score if score is not None else 0.5,
            source_agent="WebSearchAgent",
        ))
    logger.info(f"Exa returned {len(sources)} results for '{query}'")
    return sources


async def web_search(query: str, max_results: int = 10) -> list[SourceRef]:
    """Combined Tavily + Exa search. Deduplicates by URL."""
    import asyncio

    tavily_task = tavily_search(query, max_results=max_results)
    exa_task = exa_search(query, max_results=max_results)

    tavily_results, exa_results = await asyncio.gather(
        tavily_task, exa_task, return_exceptions=True
    )

    # Handle failures gracefully
    all_sources: list[SourceRef] = []
    if isinstance(tavily_results, list):
        all_sources.extend(tavily_results)
    else:
        logger.error(f"Tavily failed: {tavily_results}")
    if isinstance(exa_results, list):
        all_sources.extend(exa_results)
    else:
        logger.error(f"Exa failed: {exa_results}")

    # Deduplicate by URL
    seen = set()
    deduped = []
    for s in all_sources:
        if s.url not in seen:
            seen.add(s.url)
            deduped.append(s)

    return deduped[:max_results * 2]
