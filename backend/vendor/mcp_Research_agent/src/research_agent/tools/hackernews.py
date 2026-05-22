"""Hacker News tool — Algolia HN API (free, 10K req/hr, no key required)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from research_agent.config import settings
from research_agent.models import SourceRef

logger = logging.getLogger(__name__)

ALGOLIA_HN_BASE = "https://hn.algolia.com/api/v1"
TECH_EXPANSIONS = {
    "ai": "artificial intelligence",
    "llm": "large language model",
    "saas": "software as a service",
    "robotic": "robotics",
    "robotics": "robots",
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
async def search_hackernews(
    query: str,
    max_results: int = 15,
    min_points: int | None = None,
    max_age_days: int | None = None,
) -> list[SourceRef]:
    """Search Hacker News via Algolia API. Free, 10K req/hr, no key required."""
    min_points = min_points or settings.hn_min_points
    max_age_days = max_age_days or settings.hn_max_age_days

    queries = _candidate_queries(query)
    searches = [
        (queries[0], min_points, max_age_days),
        (queries[0], 0, max(max_age_days, 180)),
    ]
    searches.extend((candidate, 0, max(max_age_days, 365)) for candidate in queries[1:3])

    sources = []
    seen_ids = set()
    async with httpx.AsyncClient(timeout=20) as client:
        for search_query, points_floor, age_days in searches:
            cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=age_days)).timestamp())
            resp = await client.get(f"{ALGOLIA_HN_BASE}/search", params={
                "query": search_query,
                "tags": "story",
                "numericFilters": f"points>{points_floor},created_at_i>{cutoff_ts}",
                "hitsPerPage": max_results * 2,
            })
            resp.raise_for_status()
            data = resp.json()
            for hit in data.get("hits", []):
                object_id = hit.get("objectID", "")
                if object_id in seen_ids:
                    continue
                seen_ids.add(object_id)
                source = _source_from_hit(hit)
                if _is_relevant_hn_source(source, query):
                    sources.append(source)
            if len(sources) >= max_results:
                break

    sources.sort(key=lambda s: s.engagement.get("points", 0), reverse=True)
    logger.info(f"HackerNews returned {len(sources)} stories for '{query}'")
    return sources[:max_results]


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
async def fetch_hn_comments(story_id: str, limit: int = 50) -> list[dict]:
    """Fetch comments for a HN story via Algolia API."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{ALGOLIA_HN_BASE}/items/{story_id}")
        resp.raise_for_status()
        data = resp.json()

    comments = []
    _extract_comments(data.get("children", []), comments, limit)
    logger.info(f"Fetched {len(comments)} HN comments for story {story_id}")
    return comments[:limit]


def _extract_comments(children: list[dict], out: list[dict], limit: int):
    """Recursively extract comments from nested HN comment tree."""
    for child in children:
        if len(out) >= limit:
            break
        text = child.get("text", "")
        if text and len(text) > 20:
            out.append({
                "body": text[:1000],
                "score": child.get("points", 0) or 0,
                "platform": "hackernews",
            })
        _extract_comments(child.get("children", []), out, limit)


def _source_from_hit(hit: dict) -> SourceRef:
    points = hit.get("points", 0) or 0
    num_comments = hit.get("num_comments", 0) or 0
    created_ts = hit.get("created_at_i", 0)
    post_date = datetime.fromtimestamp(created_ts, tz=timezone.utc) if created_ts else datetime.now(timezone.utc)
    object_id = hit.get("objectID", "")
    title = hit.get("title") or hit.get("story_title") or ""
    story_text = hit.get("story_text") or hit.get("comment_text") or ""

    return SourceRef(
        title=title,
        url=hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}",
        snippet=story_text[:500] if story_text else f"HN discussion with {num_comments} comments",
        platform="hackernews",
        engagement={
            "points": points,
            "num_comments": num_comments,
            "object_id": object_id,
        },
        freshness_days=(datetime.now(timezone.utc) - post_date).days,
        relevance_score=min(1.0, max(points / 200, num_comments / 100)),
        source_agent="HackerNewsAgent",
    )


def _candidate_queries(query: str) -> list[str]:
    normalized = re.sub(r"\bv\s*/\s*s\b|\bversus\b", " vs ", query, flags=re.IGNORECASE)
    normalized = re.sub(r"[^a-zA-Z0-9\s-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    terms = [part.lower() for part in normalized.split() if len(part) > 1 and part.lower() not in {"vs", "the", "and"}]
    expanded = " ".join(TECH_EXPANSIONS.get(term, term) for term in terms)
    compact = " ".join(terms[:4])
    candidates = [normalized, expanded, compact]
    deduped = []
    for candidate in candidates:
        if candidate and candidate.lower() not in {item.lower() for item in deduped}:
            deduped.append(candidate)
    return deduped or [query]


def _is_relevant_hn_source(source: SourceRef, query: str) -> bool:
    query_terms = _important_terms(query)
    if not query_terms:
        return True
    text = f"{source.title} {source.snippet} {source.url}".lower()
    matches = sum(1 for term in query_terms if term in text)
    return matches >= min(2, len(query_terms)) or source.engagement.get("points", 0) >= 100


def _important_terms(query: str) -> set[str]:
    normalized = re.sub(r"\bv\s*/\s*s\b|\bversus\b", " ", query, flags=re.IGNORECASE)
    normalized = re.sub(r"[^a-zA-Z0-9\s-]", " ", normalized)
    stopwords = {"about", "with", "from", "into", "human", "humans", "versus", "against", "will"}
    terms = {part.lower() for part in normalized.split() if len(part) > 2 and part.lower() not in stopwords}
    expanded = set(terms)
    for term in terms:
        if term in TECH_EXPANSIONS:
            expanded.update(TECH_EXPANSIONS[term].split())
    return expanded
