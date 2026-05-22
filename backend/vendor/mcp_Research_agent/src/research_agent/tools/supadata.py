"""Supadata tool - video transcript extraction for demand-side research."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from datetime import datetime, timezone

from research_agent.tools.youtube import extract_youtube_video_id

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from research_agent.config import settings
from research_agent.models import CostBreakdown, SourceRef
from research_agent.tools.cache import get_json, make_cache_key, set_json

logger = logging.getLogger(__name__)

SUPADATA_API_BASE = "https://api.supadata.ai/v1"


async def search_supadata_transcripts(
    query: str,
    max_results: int = 5,
    cost_tracker: CostBreakdown | None = None,
) -> tuple[list[SourceRef], list[dict]]:
    """Search relevant YouTube videos and enrich them with Supadata transcripts."""
    if not settings.supadata_api_key:
        logger.warning("Supadata API key not set - skipping")
        return [], []

    videos = await search_youtube_supadata(query, max_results=max_results, min_views=1000, max_age_days=365)
    if not videos:
        return [], []

    tasks = [
        fetch_transcript(video.url, mode=settings.supadata_transcript_mode, cost_tracker=cost_tracker)
        for video in videos[:max_results]
    ]
    transcript_results = await asyncio.gather(*tasks, return_exceptions=True)

    sources: list[SourceRef] = []
    comments: list[dict] = []
    for video, transcript_result in zip(videos, transcript_results, strict=False):
        if isinstance(transcript_result, Exception):
            logger.warning("Supadata transcript failed for %s: %s", video.url, transcript_result)
            continue
        content = _transcript_text(transcript_result)
        if not content:
            continue

        video_id = extract_youtube_video_id(video.url)
        sources.append(SourceRef(
            title=f"Transcript: {video.title}",
            url=video.url,
            snippet=content[:500],
            platform="supadata",
            engagement={
                "type": "transcript",
                "provider": "supadata",
                "video_id": video_id,
                "lang": transcript_result.get("lang", ""),
                "source_platform": "youtube",
                "views": video.engagement.get("views", 0),
                "published_at": video.engagement.get("published_at", ""),
            },
            freshness_days=video.freshness_days,
            relevance_score=max(video.relevance_score, 0.7),
            source_agent="SupadataAgent",
        ))

        for chunk in _comment_like_chunks(content):
            comments.append({
                "body": chunk,
                "score": video.engagement.get("views", 0),
                "platform": "supadata",
                "source_url": video.url,
            })

    logger.info("Supadata returned %s transcripts for '%s'", len(sources), query)
    return sources, comments[: max_results * 6]


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
async def search_youtube_supadata(
    query: str,
    max_results: int = 10,
    min_views: int = 0,
    max_age_days: int | None = None,
) -> list[SourceRef]:
    """Search YouTube through Supadata and return normal YouTube SourceRefs."""
    if not settings.supadata_api_key:
        return []

    cache_key = make_cache_key("supadata_youtube_search", query, max_results, min_views, max_age_days)
    cached = await get_json(cache_key)
    if cached is not None:
        return [_source_from_dict(item) for item in cached]

    headers = {"x-api-key": settings.supadata_api_key}
    params = {
        "query": query,
        "type": "video",
        "limit": min(max_results * 2, 50),
        "sortBy": "relevance",
        "uploadDate": _upload_date_filter(max_age_days),
    }

    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.get(f"{SUPADATA_API_BASE}/youtube/search", headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

    sources = []
    for item in data.get("results", []):
        if item.get("type") and item.get("type") != "video":
            continue
        source = _source_from_supadata_search_item(item)
        if source.engagement.get("views", 0) < min_views:
            continue
        if max_age_days is not None and source.freshness_days and source.freshness_days > max_age_days:
            continue
        sources.append(source)

    sources.sort(key=lambda s: s.engagement.get("views", 0), reverse=True)
    sources = sources[:max_results]
    await set_json(cache_key, [_source_to_dict(source) for source in sources], settings.search_cache_ttl_hours * 3600)
    logger.info("Supadata YouTube search returned %s videos for '%s'", len(sources), query)
    return sources


def _source_from_supadata_search_item(item: dict[str, Any]) -> SourceRef:
    video_id = item.get("id") or extract_youtube_video_id(item.get("url", ""))
    url = item.get("url") or f"https://youtube.com/watch?v={video_id}"
    description = item.get("description") or item.get("snippet") or ""
    views = _safe_int(item.get("viewCount") or item.get("views") or item.get("stats", {}).get("views"))
    likes = _safe_int(item.get("likeCount") or item.get("likes") or item.get("stats", {}).get("likes"))
    comments = _safe_int(item.get("commentCount") or item.get("comments") or item.get("stats", {}).get("comments"))
    published = item.get("uploadDate") or item.get("publishedAt") or item.get("createdAt") or ""
    channel = item.get("channel") or item.get("author") or {}
    channel_title = channel.get("name") or channel.get("displayName") or item.get("channelTitle") or ""

    return SourceRef(
        title=item.get("title", ""),
        url=url,
        snippet=str(description)[:500],
        platform="youtube",
        engagement={
            "views": views,
            "likes": likes,
            "comments": comments,
            "like_ratio": round(likes / views, 4) if views else 0,
            "comment_ratio": round(comments / views, 4) if views else 0,
            "published_at": published,
            "channel_id": channel.get("id", ""),
            "channel_title": channel_title,
            "channel_subscribers": _safe_int(channel.get("subscriberCount")),
            "duration_seconds": _safe_int(item.get("duration") or item.get("media", {}).get("duration")),
            "provider": "supadata",
        },
        freshness_days=_freshness_days(published),
        relevance_score=min(1.0, views / 100000) if views else 0.7,
        source_agent="YouTubeAgent",
    )


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
async def fetch_transcript(
    url: str,
    lang: str = "en",
    mode: str = "native",
    cost_tracker: CostBreakdown | None = None,
) -> dict[str, Any]:
    """Fetch a transcript from Supadata, polling when the API returns an async job."""
    cache_key = make_cache_key("supadata_transcript", url, lang, mode)
    cached = await get_json(cache_key)
    if cached is not None:
        return cached

    headers = {"x-api-key": settings.supadata_api_key}
    params = {
        "url": url,
        "lang": lang,
        "text": "true",
        "mode": mode,
    }

    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.get(f"{SUPADATA_API_BASE}/transcript", headers=headers, params=params)
        if resp.status_code == 202:
            data = resp.json()
            job_id = data.get("jobId") or data.get("id")
            if not job_id:
                resp.raise_for_status()
            result = await _poll_transcript_job(client, job_id, headers)
        else:
            resp.raise_for_status()
            result = resp.json()

    if cost_tracker:
        credits = _billable_credits(resp)
        if credits:
            cost_tracker.add_cost("demand_side", "supadata:transcript", "supadata", credits * 0.001)

    await set_json(cache_key, result, settings.search_cache_ttl_hours * 3600)
    return result


async def _poll_transcript_job(
    client: httpx.AsyncClient,
    job_id: str,
    headers: dict[str, str],
    attempts: int = 20,
) -> dict[str, Any]:
    for _ in range(attempts):
        await asyncio.sleep(1)
        resp = await client.get(f"{SUPADATA_API_BASE}/transcript/{job_id}", headers=headers)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        if status == "completed":
            result = data.get("result")
            return result if isinstance(result, dict) else data
        if status == "failed":
            raise RuntimeError(data.get("error") or "Supadata transcript job failed")
    raise TimeoutError(f"Supadata transcript job timed out: {job_id}")


def _transcript_text(result: dict[str, Any]) -> str:
    content = result.get("content") or result.get("result", {}).get("content")
    if isinstance(content, str):
        return " ".join(content.split())
    if isinstance(content, list):
        parts = [
            str(item.get("text", "")).strip()
            for item in content
            if isinstance(item, dict) and item.get("text")
        ]
        return " ".join(" ".join(parts).split())
    return ""


def _comment_like_chunks(text: str, chunk_size: int = 700) -> list[str]:
    words = text.split()
    chunks = []
    for start in range(0, len(words), 120):
        chunk = " ".join(words[start:start + 120])
        if len(chunk) >= 80:
            chunks.append(chunk[:chunk_size])
        if len(chunks) >= 6:
            break
    return chunks


def _billable_credits(resp: httpx.Response) -> int:
    value = resp.headers.get("x-billable-requests", "0")
    try:
        return int(float(value))
    except ValueError:
        return 0





def _upload_date_filter(max_age_days: int | None) -> str:
    if max_age_days is None:
        return "year"
    if max_age_days <= 1:
        return "today"
    if max_age_days <= 7:
        return "week"
    if max_age_days <= 31:
        return "month"
    return "year"


def _freshness_days(published: str) -> int:
    if not published:
        return 0
    try:
        pub_date = datetime.fromisoformat(published.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - pub_date).days
    except (ValueError, AttributeError):
        return 0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _source_to_dict(source: SourceRef) -> dict[str, Any]:
    return {
        "title": source.title,
        "url": source.url,
        "snippet": source.snippet,
        "platform": source.platform,
        "engagement": source.engagement,
        "freshness_days": source.freshness_days,
        "relevance_score": source.relevance_score,
        "source_agent": source.source_agent,
    }


def _source_from_dict(item: dict[str, Any]) -> SourceRef:
    return SourceRef(
        title=item.get("title", ""),
        url=item.get("url", ""),
        snippet=item.get("snippet", ""),
        platform=item.get("platform", "youtube"),
        engagement=item.get("engagement", {}),
        freshness_days=item.get("freshness_days", 0),
        relevance_score=item.get("relevance_score", 0.0),
        source_agent=item.get("source_agent", "YouTubeAgent"),
    )
