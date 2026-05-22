"""Reddit tool — posts + comment mining via ScrapeCreators or direct API."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from research_agent.config import settings
from research_agent.models import CostBreakdown, SourceRef
from research_agent.tools.cache import get_json, make_cache_key, set_json

logger = logging.getLogger(__name__)

SCRAPE_CREATORS_BASE = "https://api.scrapecreators.com/v1"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def search_reddit(
    query: str,
    subreddits: list[str] | None = None,
    max_results: int = 15,
    sort: str = "top",
    min_score: int | None = None,
    max_age_days: int | None = None,
    cost_tracker: CostBreakdown | None = None,
) -> list[SourceRef]:
    """Search Reddit for posts matching a query. Uses ScrapeCreators if API key is available, 
    else falls back to Reddit's public JSON API."""

    min_score = min_score or settings.reddit_min_score
    max_age_days = max_age_days or settings.reddit_max_age_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    if settings.scrape_creators_api_key:
        results = await _scrape_creators_search(query, subreddits, max_results, sort, min_score, cutoff)
        if cost_tracker and results:
            cost_tracker.add_cost("demand_side", "scrapecreators:reddit_search", "scrapecreators", len(results) * 0.001)
        return results
    else:
        return await _reddit_json_search(query, max_results, sort, min_score, cutoff)


async def _scrape_creators_search(
    query: str, subreddits: list[str] | None, max_results: int, sort: str,
    min_score: int, cutoff: datetime,
) -> list[SourceRef]:
    """Reddit search via ScrapeCreators API."""
    async with httpx.AsyncClient(timeout=30) as client:
        headers = {"x-api-key": settings.scrape_creators_api_key}
        scrape_creators_sort = "comment_count" if sort == "controversial" else sort
        params = {
            "query": query,
            "sort": scrape_creators_sort,
            "limit": max_results * 2,  # over-fetch, then filter
        }
        if subreddits:
            params["subreddits"] = ",".join(subreddits)

        resp = await client.get(f"{SCRAPE_CREATORS_BASE}/reddit/search", headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

    sources = []
    for post in data.get("posts", data.get("results", [])):
        score = post.get("score", post.get("ups", 0))
        created = post.get("created_utc", 0)
        if isinstance(created, (int, float)):
            post_date = datetime.fromtimestamp(created, tz=timezone.utc)
        else:
            post_date = datetime.now(timezone.utc)

        if score < min_score or post_date < cutoff or not _is_relevant_reddit_post(post, query):
            continue

        subreddit = _post_subreddit(post)
        sources.append(SourceRef(
            title=post.get("title", ""),
            url=f"https://reddit.com{post.get('permalink', '')}",
            snippet=post.get("selftext", post.get("body", ""))[:500],
            platform="reddit",
            engagement={
                "score": score,
                "num_comments": post.get("num_comments", 0),
                "upvote_ratio": post.get("upvote_ratio", 0),
                "subreddit": subreddit,
            },
            freshness_days=(datetime.now(timezone.utc) - post_date).days,
            relevance_score=min(1.0, score / 500),
            source_agent="RedditAgent",
        ))

    logger.info(f"Reddit (ScrapeCreators) returned {len(sources)} posts for '{query}'")
    return sources[:max_results]


async def _reddit_json_search(
    query: str, max_results: int, sort: str, min_score: int, cutoff: datetime,
) -> list[SourceRef]:
    """Fallback: Reddit public JSON endpoint (no auth required, rate-limited)."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            "https://www.reddit.com/search.json",
            params={"q": query, "sort": sort, "limit": max_results * 2, "t": "month"},
            headers={"User-Agent": "LadderResearchAgent/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

    sources = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        score = post.get("score", 0)
        post_date = datetime.fromtimestamp(post.get("created_utc", 0), tz=timezone.utc)

        if score < min_score or post_date < cutoff or not _is_relevant_reddit_post(post, query):
            continue

        subreddit = _post_subreddit(post)
        sources.append(SourceRef(
            title=post.get("title", ""),
            url=f"https://reddit.com{post.get('permalink', '')}",
            snippet=post.get("selftext", "")[:500],
            platform="reddit",
            engagement={
                "score": score,
                "num_comments": post.get("num_comments", 0),
                "upvote_ratio": post.get("upvote_ratio", 0),
                "subreddit": subreddit,
            },
            freshness_days=(datetime.now(timezone.utc) - post_date).days,
            relevance_score=min(1.0, score / 500),
            source_agent="RedditAgent",
        ))

    logger.info(f"Reddit (JSON) returned {len(sources)} posts for '{query}'")
    return sources[:max_results]


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
async def fetch_reddit_comments(permalink: str, limit: int = 50) -> list[dict]:
    """Fetch top comments for a Reddit post by permalink."""
    cache_key = make_cache_key("reddit_comments", permalink, limit)
    cached = await get_json(cache_key)
    if cached is not None:
        return cached

    url = f"https://www.reddit.com{permalink}.json"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            url,
            params={"limit": limit, "sort": "top", "depth": 2},
            headers={"User-Agent": "LadderResearchAgent/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

    comments = []
    if len(data) >= 2:
        for child in data[1].get("data", {}).get("children", []):
            c = child.get("data", {})
            body = c.get("body", "")
            if body and c.get("score", 0) >= 1 and len(body) > 20:
                comments.append({
                    "body": body[:1000],
                    "score": c.get("score", 0),
                    "platform": "reddit",
                })

    logger.info(f"Fetched {len(comments)} comments from {permalink}")
    comments = comments[:limit]
    await set_json(cache_key, comments, settings.search_cache_ttl_hours * 3600)
    return comments


def _is_relevant_reddit_post(post: dict, query: str) -> bool:
    subreddit = _post_subreddit(post)
    allowed = _allowed_subreddits()
    if allowed and subreddit and subreddit.lower() not in allowed:
        return False

    terms = _important_terms(query)
    if not terms:
        return True

    text = " ".join([
        str(post.get("title", "")),
        str(post.get("selftext", "")),
        str(post.get("body", "")),
        subreddit,
    ]).lower()
    tokens = set(re.findall(r"[a-z0-9]+", text))
    matches = sum(1 for term in terms if term in tokens or term in text)
    required = 1 if len(terms) == 1 else min(2, len(terms))
    return matches >= required


def _important_terms(query: str) -> set[str]:
    stopwords = {
        "about", "after", "against", "also", "and", "are", "can", "for", "from",
        "has", "have", "how", "into", "should", "that", "the", "their", "this",
        "what", "when", "where", "which", "why", "with", "without",
    }
    synonyms = {
        "ai": {"ai", "artificial", "intelligence", "llm", "agent", "agents"},
        "agent": {"agent", "agents", "ai"},
        "agents": {"agent", "agents", "ai"},
        "saas": {"saas", "software"},
    }
    terms = {
        token
        for token in re.findall(r"[a-z0-9]+", query.lower())
        if len(token) > 2 and token not in stopwords
    }
    expanded = set(terms)
    for term in terms:
        expanded.update(synonyms.get(term, set()))
    return expanded


def _post_subreddit(post: dict) -> str:
    subreddit = post.get("subreddit") or post.get("subreddit_name_prefixed") or ""
    subreddit = str(subreddit)
    return subreddit[2:] if subreddit.lower().startswith("r/") else subreddit


def _allowed_subreddits() -> set[str]:
    raw = settings.reddit_allowed_subreddits.strip()
    if not raw:
        return set()
    return {
        item.strip().lower().removeprefix("r/")
        for item in raw.split(",")
        if item.strip()
    }
