"""ScrapeCreators provider — single async HTTP wrapper for the four social
platforms we ingest (Reddit, YouTube, X, Instagram).

Per-platform fetchers return *normalized* dataclasses (RedditPost,
YouTubeVideo, XTweet, InstagramReel). When official provider APIs come
online — Reddit OAuth / asyncpraw, YouTube Data API v3, X via Twikit or
paid alternates — only this module changes. Tool signatures and return
shapes stay identical, so the swap is mechanical.

ScrapeCreators billing: every successful call = 1 credit. 4xx responses
that fail validation are *not* charged (verified during the probe).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.scrapecreators.com"


# ─── Normalized result shapes ───────────────────────────────────────────────


@dataclass(frozen=True)
class RedditPost:
    title: str
    url: str
    subreddit: str
    score: int
    num_comments: int
    created_utc: int
    selftext: str
    author: str | None


@dataclass(frozen=True)
class RedditSearchHit:
    """A single post returned by the cross-Reddit search endpoint.

    Same shape as RedditPost but adds nothing — kept as a separate type so
    callers can tell whether a result came from `/v1/reddit/search` (broad,
    cross-subreddit discovery) versus `/v1/reddit/subreddit` (targeted feed).
    """

    title: str
    url: str
    subreddit: str
    score: int
    num_comments: int
    created_utc: int
    selftext: str
    author: str | None


@dataclass(frozen=True)
class YouTubeVideo:
    video_id: str
    url: str
    title: str
    channel: str | None
    published_time: str | None
    view_count_text: str | None
    duration: str | None


@dataclass(frozen=True)
class XTweet:
    tweet_id: str
    url: str
    text: str
    handle: str
    created_at: str | None
    like_count: int | None
    view_count: int | None
    reply_count: int | None
    retweet_count: int | None


@dataclass(frozen=True)
class InstagramReel:
    reel_id: str
    url: str
    caption: str
    owner_handle: str | None
    owner_full_name: str | None
    play_count: int | None
    like_count: int | None
    comment_count: int | None
    duration_sec: float | None
    taken_at: str | None


# ─── HTTP plumbing ──────────────────────────────────────────────────────────


def _headers() -> dict[str, str]:
    if not settings.SCRAPECREATORS_API_KEY:
        raise RuntimeError(
            "SCRAPECREATORS_API_KEY is not configured. Set it in backend/.env."
        )
    return {"x-api-key": settings.SCRAPECREATORS_API_KEY}


async def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{_BASE}{path}", headers=_headers(), params=params)
        if r.status_code >= 400:
            logger.warning(
                "scrapecreators %s -> %d: %s", path, r.status_code, r.text[:200]
            )
            r.raise_for_status()
        return r.json()


# ─── Reddit ─────────────────────────────────────────────────────────────────


async def reddit_subreddit(
    subreddit: str,
    sort: Literal["hot", "new", "top", "rising"] = "hot",
    timeframe: Literal["day", "week", "month", "year", "all"] = "week",
    limit: int = 15,
) -> list[RedditPost]:
    """Fetch posts from a subreddit. `timeframe` only applies when sort='top'."""
    params: dict[str, Any] = {"subreddit": subreddit, "sort": sort, "trim": "true"}
    if sort == "top":
        params["timeframe"] = timeframe
    data = await _get("/v1/reddit/subreddit", params)
    posts = data.get("posts") or []
    out: list[RedditPost] = []
    for p in posts[:limit]:
        permalink = p.get("permalink") or ""
        out.append(
            RedditPost(
                title=p.get("title") or "",
                url=(
                    f"https://reddit.com{permalink}"
                    if permalink
                    else (p.get("url") or "")
                ),
                subreddit=p.get("subreddit") or subreddit,
                score=int(p.get("score") or p.get("ups") or 0),
                num_comments=int(p.get("num_comments") or 0),
                created_utc=int(p.get("created") or 0),
                selftext=(p.get("selftext") or "")[:500],
                author=p.get("author"),
            )
        )
    return out


async def reddit_search(
    query: str,
    sort: Literal["relevance", "new", "top", "comment_count"] = "top",
    timeframe: Literal["day", "week", "month", "year", "all"] = "week",
    limit: int = 25,
) -> list[RedditSearchHit]:
    """Cross-Reddit keyword search. Use this BEFORE picking subreddits so
    you can see which communities are actually discussing a topic, instead
    of guessing from positioning text.

    The endpoint searches every subreddit at once; each post carries its
    `subreddit` field, which the caller groups on to discover communities.
    """
    params: dict[str, Any] = {
        "query": query,
        "sort": sort,
        "timeframe": timeframe,
        "trim": "true",
    }
    data = await _get("/v1/reddit/search", params)
    posts = data.get("posts") or []
    out: list[RedditSearchHit] = []
    for p in posts[:limit]:
        permalink = p.get("permalink") or ""
        out.append(
            RedditSearchHit(
                title=p.get("title") or "",
                url=(
                    f"https://reddit.com{permalink}"
                    if permalink
                    else (p.get("url") or "")
                ),
                subreddit=p.get("subreddit") or "",
                score=int(p.get("score") or p.get("ups") or 0),
                num_comments=int(p.get("num_comments") or 0),
                created_utc=int(p.get("created") or 0),
                selftext=(p.get("selftext") or "")[:500],
                author=p.get("author"),
            )
        )
    return out


# ─── YouTube ────────────────────────────────────────────────────────────────


async def youtube_search(
    query: str,
    upload_date: Literal["today", "this_week", "this_month", "this_year"] = "this_week",
    sort_by: Literal["relevance", "popular"] = "popular",
    limit: int = 10,
) -> list[YouTubeVideo]:
    """Search YouTube for recent videos matching `query`."""
    params: dict[str, Any] = {
        "query": query,
        "uploadDate": upload_date,
        "sortBy": sort_by,
        "type": "videos",
    }
    data = await _get("/v1/youtube/search", params)
    videos = data.get("videos") or []
    out: list[YouTubeVideo] = []
    for v in videos[:limit]:
        vid = v.get("id") or ""
        channel_obj = v.get("channel")
        channel = (
            channel_obj.get("title")
            if isinstance(channel_obj, dict)
            else (v.get("channelTitle") or v.get("channel"))
        )
        out.append(
            YouTubeVideo(
                video_id=vid,
                url=v.get("url")
                or (f"https://www.youtube.com/watch?v={vid}" if vid else ""),
                title=v.get("title") or "",
                channel=channel if isinstance(channel, str) else None,
                published_time=v.get("publishedTimeText") or v.get("publishedTime"),
                view_count_text=v.get("viewCountText") or v.get("viewCount"),
                duration=v.get("lengthText") or v.get("duration"),
            )
        )
    return out


# ─── X / Twitter ────────────────────────────────────────────────────────────


async def x_user_tweets(handle: str, limit: int = 15) -> list[XTweet]:
    """Fetch a user's most-popular tweets (Twitter only exposes ~100 publicly)."""
    data = await _get(
        "/v1/twitter/user-tweets", {"handle": handle, "trim": "true"}
    )
    tweets = data.get("tweets") or []
    out: list[XTweet] = []
    for t in tweets[:limit]:
        legacy = t.get("legacy") or {}
        rest_id = t.get("rest_id") or legacy.get("id_str") or ""
        text = (
            legacy.get("full_text")
            or t.get("full_text")
            or t.get("text")
            or ""
        )
        view_count: int | None = None
        views = t.get("views") or {}
        if isinstance(views, dict) and views.get("count"):
            try:
                view_count = int(views["count"])
            except (TypeError, ValueError):
                view_count = None
        out.append(
            XTweet(
                tweet_id=rest_id,
                url=f"https://x.com/{handle}/status/{rest_id}" if rest_id else "",
                text=text[:500],
                handle=handle,
                created_at=legacy.get("created_at"),
                like_count=_int_or_none(legacy.get("favorite_count")),
                view_count=view_count,
                reply_count=_int_or_none(legacy.get("reply_count")),
                retweet_count=_int_or_none(legacy.get("retweet_count")),
            )
        )
    return out


def _int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float_or_none(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


_VIEW_RE = re.compile(r"([\d,.]+)\s*([KkMmBb])?", re.UNICODE)
_RELTIME_RE = re.compile(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?", re.I)
_UNIT_HOURS = {
    "second": 1 / 3600,
    "minute": 1 / 60,
    "hour": 1.0,
    "day": 24.0,
    "week": 24.0 * 7,
    "month": 24.0 * 30,
    "year": 24.0 * 365,
}


def parse_view_count_text(text: str | None) -> int | None:
    """Parse YouTube-style view strings into ints.

    Examples: '1.2M views' → 1_200_000, '47K' → 47_000, '1,234 views' → 1234.
    Returns None when the string can't be parsed (caller should keep the item
    rather than drop it on parse failure).
    """
    if not text:
        return None
    m = _VIEW_RE.search(text)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    suffix = (m.group(2) or "").lower()
    try:
        n = float(raw)
    except ValueError:
        return None
    mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(suffix, 1)
    return int(n * mult)


def parse_relative_time_hours(text: str | None) -> float | None:
    """Parse 'N units ago' strings into hours-since-posted.

    Examples: '2 weeks ago' → 336.0, '3 days ago' → 72.0, '5 hours ago' → 5.0.
    Returns None when unparseable so callers can default to 'unknown age'.
    """
    if not text:
        return None
    m = _RELTIME_RE.search(text)
    if not m:
        return None
    try:
        n = int(m.group(1))
    except ValueError:
        return None
    unit = m.group(2).lower()
    return n * _UNIT_HOURS.get(unit, 1.0)


# ─── Instagram ──────────────────────────────────────────────────────────────


async def instagram_reels_search(
    query: str,
    date_posted: Literal[
        "last-hour", "last-day", "last-week", "last-month", "last-year"
    ] = "last-week",
    limit: int = 10,
) -> list[InstagramReel]:
    """Search Instagram reels by keyword. Returns recent + popular matches.

    ScrapeCreators returns 404 + `error: not_found` when the query matches no
    reels (semantically "empty result", not "endpoint missing"). We swallow
    that into an empty list so the crew degrades gracefully on niche queries.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{_BASE}/v2/instagram/reels/search",
            headers=_headers(),
            params={"query": query, "date_posted": date_posted},
        )
        if r.status_code == 404:
            try:
                body = r.json()
            except ValueError:
                body = {}
            if body.get("error") == "not_found":
                return []
        if r.status_code >= 400:
            logger.warning(
                "scrapecreators ig/reels/search -> %d: %s",
                r.status_code,
                r.text[:200],
            )
            r.raise_for_status()
        data = r.json()
    reels = data.get("reels") or data.get("items") or data.get("results") or []
    out: list[InstagramReel] = []
    for r in reels[:limit]:
        owner = r.get("owner") or {}
        rid = r.get("id") or r.get("shortcode") or ""
        out.append(
            InstagramReel(
                reel_id=str(rid),
                url=r.get("url")
                or (
                    f"https://www.instagram.com/reel/{r.get('shortcode')}"
                    if r.get("shortcode")
                    else ""
                ),
                caption=(r.get("caption") or "")[:500],
                owner_handle=owner.get("username") if isinstance(owner, dict) else None,
                owner_full_name=owner.get("full_name") if isinstance(owner, dict) else None,
                play_count=_int_or_none(r.get("video_play_count")),
                like_count=_int_or_none(r.get("like_count")),
                comment_count=_int_or_none(r.get("comment_count")),
                duration_sec=_float_or_none(r.get("video_duration")),
                taken_at=r.get("taken_at"),
            )
        )
    return out


# ─── LinkedIn ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LinkedInProfile:
    """Structured data returned by /v1/linkedin/profile."""

    name: str | None
    image: str | None
    location: str | None
    followers: int | None
    about: str | None
    experience: list[dict]  # {name, url, location, role_description}
    education: list[dict]   # {name, url, startDate, endDate}
    articles: list[dict]    # {headline, author, datePublished, articleBody}
    publications: list[dict]  # {name, url}
    projects: list[dict]     # {name, url, dateRange, description, contributors}
    recommendations: list[dict]  # {name, link, image, text}
    recent_posts: list[dict]    # {title, activityType, link, image}
    similar_profiles: list[dict]  # {name, link, image}


async def linkedin_profile(url: str) -> LinkedInProfile | None:
    """Fetch a public LinkedIn profile via ScrapeCreators.

    Returns None when the profile can't be fetched (private, not found, etc.).
    """
    try:
        data = await _get("/v1/linkedin/profile", {"url": url})
    except Exception:
        logger.exception("LinkedIn profile fetch failed for %s", url)
        return None

    if not data.get("success"):
        logger.warning("LinkedIn profile fetch unsuccessful for %s: %s", url, data)
        return None

    def _list(key: str) -> list[dict]:
        items = data.get(key) or []
        return items if isinstance(items, list) else []

    followers = data.get("followers")
    try:
        followers = int(followers) if followers else None
    except (TypeError, ValueError):
        followers = None

    return LinkedInProfile(
        name=data.get("name"),
        image=data.get("image"),
        location=data.get("location"),
        followers=followers,
        about=data.get("about"),
        experience=_list("experience"),
        education=_list("education"),
        articles=_list("articles"),
        publications=_list("publications"),
        projects=_list("projects"),
        recommendations=_list("recommendations"),
        recent_posts=_list("recentPosts"),
        similar_profiles=_list("similarProfiles"),
    )
