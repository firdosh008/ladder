"""YouTube tool — video search + comment fetching via YT Data API + Apify fallback."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from research_agent.config import settings
from research_agent.models import CostBreakdown, SourceRef, ContentItem
from research_agent.tools.cache import get_json, make_cache_key, set_json

logger = logging.getLogger(__name__)

YT_API_BASE = "https://www.googleapis.com/youtube/v3"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def search_youtube(
    query: str,
    max_results: int = 10,
    min_views: int | None = None,
    max_age_days: int | None = None,
) -> list[SourceRef]:
    """Search YouTube for videos. Uses YT Data API (free, 10K units/day)."""
    min_views = min_views or settings.youtube_min_views
    max_age_days = max_age_days or settings.youtube_max_age_days

    if settings.supadata_api_key:
        try:
            from research_agent.tools.supadata import search_youtube_supadata

            supadata_results = await search_youtube_supadata(
                query,
                max_results=max_results,
                min_views=min_views,
                max_age_days=max_age_days,
            )
            if supadata_results:
                return supadata_results
        except Exception as e:
            logger.warning("Supadata YouTube search failed, falling back to YouTube Data API: %s", e)

    if not settings.youtube_api_key:
        logger.warning("YouTube API key not set — skipping")
        return []

    published_after = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    async with httpx.AsyncClient(timeout=30) as client:
        # Step 1: Search for video IDs
        search_resp = await client.get(f"{YT_API_BASE}/search", params={
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "relevance",
            "maxResults": max_results * 2,
            "publishedAfter": published_after,
            "key": settings.youtube_api_key,
        })
        search_resp.raise_for_status()
        search_data = search_resp.json()

        video_ids = [item["id"]["videoId"] for item in search_data.get("items", []) if "videoId" in item.get("id", {})]
        if not video_ids:
            return []

        # Step 2: Get video statistics and metadata
        stats_resp = await client.get(f"{YT_API_BASE}/videos", params={
            "part": "statistics,snippet,contentDetails",
            "id": ",".join(video_ids),
            "key": settings.youtube_api_key,
        })
        stats_resp.raise_for_status()
        stats_data = stats_resp.json()

        channel_ids = list({
            item.get("snippet", {}).get("channelId", "")
            for item in stats_data.get("items", [])
            if item.get("snippet", {}).get("channelId")
        })
        channel_subscribers = {}
        if channel_ids:
            channels_resp = await client.get(f"{YT_API_BASE}/channels", params={
                "part": "statistics",
                "id": ",".join(channel_ids),
                "key": settings.youtube_api_key,
            })
            channels_resp.raise_for_status()
            channels_data = channels_resp.json()
            for channel in channels_data.get("items", []):
                stats = channel.get("statistics", {})
                channel_subscribers[channel.get("id", "")] = int(stats.get("subscriberCount", 0))

    sources = []
    for item in stats_data.get("items", []):
        stats = item.get("statistics", {})
        snippet = item.get("snippet", {})
        content_details = item.get("contentDetails", {})
        channel_id = snippet.get("channelId", "")
        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        comments_count = int(stats.get("commentCount", 0))
        duration_seconds = parse_youtube_duration(content_details.get("duration", ""))

        if views < min_views:
            continue

        published = snippet.get("publishedAt", "")
        try:
            pub_date = datetime.fromisoformat(published.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - pub_date).days
        except (ValueError, AttributeError):
            age_days = 0

        sources.append(SourceRef(
            title=snippet.get("title", ""),
            url=f"https://youtube.com/watch?v={item['id']}",
            snippet=snippet.get("description", "")[:500],
            platform="youtube",
            engagement={
                "views": views,
                "likes": likes,
                "comments": comments_count,
                "like_ratio": round(likes / views, 4) if views > 0 else 0,
                "comment_ratio": round(comments_count / views, 4) if views > 0 else 0,
                "published_at": published,
                "channel_id": channel_id,
                "channel_title": snippet.get("channelTitle", ""),
                "channel_subscribers": channel_subscribers.get(channel_id, 0),
                "duration_seconds": duration_seconds,
            },
            freshness_days=age_days,
            relevance_score=min(1.0, views / 100000),
            source_agent="YouTubeAgent",
        ))

    sources.sort(key=lambda s: s.engagement.get("views", 0), reverse=True)
    logger.info(f"YouTube returned {len(sources)} videos for '{query}'")
    return sources[:max_results]


async def get_top_videos_for_supply(query: str, max_results: int = 10) -> list[ContentItem]:
    """Pull top videos for supply-side analysis — returns ContentItem objects."""
    sources = await search_youtube(query, max_results=max_results, min_views=1000, max_age_days=1825)
    return [
        ContentItem(
            title=s.title,
            url=s.url,
            views=s.engagement.get("views", 0),
            likes=s.engagement.get("likes", 0),
            comments_count=s.engagement.get("comments", 0),
            published_date=s.engagement.get("published_at", ""),
            channel_id=s.engagement.get("channel_id", ""),
            channel_title=s.engagement.get("channel_title", ""),
            channel_subscribers=s.engagement.get("channel_subscribers", 0),
            duration_seconds=s.engagement.get("duration_seconds", 0),
            engagement_ratio=s.engagement.get("like_ratio", 0) + s.engagement.get("comment_ratio", 0),
            sentiment_score=0.0,
        )
        for s in sources
    ]


def parse_youtube_duration(duration: str) -> int:
    """Parse an ISO-8601 YouTube duration like PT1H2M3S into seconds."""
    if not duration:
        return 0

    match = re.fullmatch(r"P(?:(?P<days>\d+)D)?T?(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?", duration)
    if not match:
        return 0

    parts = {key: int(value) if value else 0 for key, value in match.groupdict().items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


def extract_youtube_video_id(url: str) -> str:
    """Extract a YouTube video ID from common watch and short URLs."""
    match = re.search(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else ""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
async def fetch_youtube_comments(
    video_id: str,
    limit: int = 50,
    cost_tracker: CostBreakdown | None = None,
) -> list[dict]:
    """Fetch top comments for a YouTube video using the configured comments provider."""
    provider = settings.youtube_comments_provider.lower().strip()
    cache_key = make_cache_key("youtube_comments", provider, video_id, limit)
    cached = await get_json(cache_key)
    if cached is not None:
        return cached

    if provider in {"apify", "auto"} and settings.apify_api_key:
        try:
            comments = await fetch_youtube_comments_apify(video_id, limit=limit, cost_tracker=cost_tracker)
            if comments or provider == "apify":
                await set_json(cache_key, comments, settings.search_cache_ttl_hours * 3600)
                return comments
        except Exception as e:
            if provider == "apify":
                raise
            logger.warning("Apify YouTube comments failed, falling back to YouTube Data API: %s", e)

    if provider == "apify":
        logger.warning("APIFY_API_KEY not set - cannot fetch YouTube comments with Apify")
        return []

    if provider in {"none", "disabled", "off"}:
        return []

    if not settings.youtube_api_key:
        return await fetch_youtube_comments_apify(video_id, limit=limit, cost_tracker=cost_tracker)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{YT_API_BASE}/commentThreads", params={
            "part": "snippet",
            "videoId": video_id,
            "order": "relevance",
            "maxResults": min(limit, 100),
            "key": settings.youtube_api_key,
        })

        if resp.status_code == 403:
            logger.warning(f"Comments disabled for video {video_id}")
            comments = await fetch_youtube_comments_apify(video_id, limit=limit, cost_tracker=cost_tracker)
            await set_json(cache_key, comments, settings.search_cache_ttl_hours * 3600)
            return comments
        resp.raise_for_status()
        data = resp.json()

    comments = []
    for item in data.get("items", []):
        s = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
        body = s.get("textDisplay", "")
        likes = s.get("likeCount", 0)
        if body and len(body) > 20:
            comments.append({
                "body": body[:1000],
                "score": likes,
                "platform": "youtube",
            })

    logger.info(f"Fetched {len(comments)} YouTube comments for {video_id}")
    comments = comments[:limit]
    await set_json(cache_key, comments, settings.search_cache_ttl_hours * 3600)
    return comments


async def fetch_youtube_comments_apify(
    video_id: str,
    limit: int = 50,
    cost_tracker: CostBreakdown | None = None,
) -> list[dict]:
    """Fetch YouTube comments through an Apify actor when the Data API path is unavailable."""
    if not settings.apify_api_key:
        return []

    actor_id = settings.apify_youtube_comments_actor.replace("/", "~")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    payload = {
        "startUrls": [{"url": video_url}],
        "maxComments": limit,
        "maxResults": limit,
        "sort": "top",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items",
            params={"token": settings.apify_api_key, "clean": "true"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    comments = []
    for item in data if isinstance(data, list) else []:
        body = (
            item.get("text")
            or item.get("comment")
            or item.get("commentText")
            or item.get("body")
            or ""
        )
        score = item.get("likeCount", item.get("likes", item.get("score", 0))) or 0
        if body and len(body) > 20:
            comments.append({
                "body": str(body)[:1000],
                "score": int(score) if isinstance(score, int | float) else 0,
                "platform": "youtube",
            })

    if cost_tracker and comments:
        cost_tracker.add_cost(
            "demand_side",
            "apify:youtube_comments",
            "apify",
            len(comments) * 0.0005,
        )

    logger.info(f"Apify fetched {len(comments)} YouTube comments for {video_id}")
    comments = comments[:limit]
    await set_json(make_cache_key("youtube_comments", "apify", video_id, limit), comments, settings.search_cache_ttl_hours * 3600)
    return comments
