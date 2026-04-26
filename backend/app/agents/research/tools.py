"""Tools exposed to the Research crew.

CrewAI's BaseTool runs synchronously from the agent's perspective. We bridge
to our async providers with asyncio.run-in-a-dedicated-loop so the crew
(which is itself invoked from an asyncio task) doesn't double-loop.

Four tools today, fanning out across the public web (Exa) plus three social
platforms (Reddit, YouTube, X) via ScrapeCreators. Each tool emits its own
batch of platform-tagged SourceRefs through the contextvar side-channel so
the UI can group/label sources by origin.

When official provider APIs come online we replace `app.providers.scrapecreators`
internals; the tool surface here stays unchanged.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.agents.research.streaming import SourceRef, sources_emitter_var
from app.providers import exa, scrapecreators


def _domain_of(url: str) -> str | None:
    """Return the bare hostname of a URL, or None if unparseable."""
    if not url:
        return None
    try:
        from urllib.parse import urlparse

        host = urlparse(url).hostname or ""
        return host[4:] if host.startswith("www.") else host or None
    except Exception:
        return None


def _iso_from_unix(ts: int | None) -> str | None:
    """Convert a Reddit-style epoch second timestamp into ISO date (UTC)."""
    if not ts:
        return None
    try:
        from datetime import datetime, timezone

        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None


# ───────────────────────────────────────────────────────────────────────────
# Exa — public web search
# ───────────────────────────────────────────────────────────────────────────


class _ExaSearchInput(BaseModel):
    query: str = Field(description="Natural-language web search query.")
    num_results: int = Field(default=8, ge=1, le=20)


class ExaSearchTool(BaseTool):
    name: str = "web_search"
    description: str = (
        "Search the public web for recent articles, posts, and discussions via "
        "Exa's neural search. Returns a JSON list of {title, url, text, "
        "published_date, score}. Use for trend discovery. Cite the `url` field "
        "verbatim in downstream outputs."
    )
    args_schema: type[BaseModel] = _ExaSearchInput

    def _run(self, query: str, num_results: int = 8) -> str:
        results = asyncio.run(exa.search(query=query, num_results=num_results))

        emitter = sources_emitter_var.get()
        if emitter is not None:
            emitter(
                query,
                [
                    SourceRef(
                        title=r.title,
                        url=r.url,
                        published_date=r.published_date,
                        snippet=(r.text or "")[:280] or None,
                        platform="web",
                        meta={
                            "domain": _domain_of(r.url),
                            "score": r.score,
                        },
                    )
                    for r in results
                ],
            )

        payload: list[dict[str, Any]] = [
            {
                "title": r.title,
                "url": r.url,
                "text": r.text,
                "published_date": r.published_date,
                "score": r.score,
            }
            for r in results
        ]
        return json.dumps(payload, ensure_ascii=False)


# ───────────────────────────────────────────────────────────────────────────
# Reddit — subreddit listings
# ───────────────────────────────────────────────────────────────────────────


class _RedditTrendsInput(BaseModel):
    subreddit: str = Field(
        description="Subreddit name without the r/ prefix, e.g. 'startups'."
    )
    sort: str = Field(
        default="hot",
        description="One of: hot, new, top, rising.",
    )
    timeframe: str = Field(
        default="week",
        description=(
            "Only used when sort='top'. One of: day, week, month, year, all."
        ),
    )
    limit: int = Field(default=15, ge=1, le=50)


class RedditTrendsTool(BaseTool):
    name: str = "reddit_trending"
    description: str = (
        "Fetch trending posts from a specific subreddit. Use to surface what "
        "a community is currently discussing about a topic. Best subreddits "
        "depend on the topic — pick from the founder's audience and "
        "positioning. Returns a JSON list of {title, url, subreddit, score, "
        "num_comments, selftext}. Cite the `url` field verbatim."
    )
    args_schema: type[BaseModel] = _RedditTrendsInput

    def _run(
        self,
        subreddit: str,
        sort: str = "hot",
        timeframe: str = "week",
        limit: int = 15,
    ) -> str:
        posts = asyncio.run(
            scrapecreators.reddit_subreddit(
                subreddit=subreddit,
                sort=sort,  # type: ignore[arg-type]
                timeframe=timeframe,  # type: ignore[arg-type]
                limit=limit,
            )
        )

        label = f"r/{subreddit} · {sort}"
        emitter = sources_emitter_var.get()
        if emitter is not None:
            emitter(
                label,
                [
                    SourceRef(
                        title=p.title,
                        url=p.url,
                        published_date=_iso_from_unix(p.created_utc),
                        snippet=(p.selftext or p.title)[:280] or None,
                        platform="reddit",
                        meta={
                            "subreddit": p.subreddit,
                            "score": p.score,
                            "num_comments": p.num_comments,
                            "author": p.author,
                        },
                    )
                    for p in posts
                ],
            )

        payload = [
            {
                "title": p.title,
                "url": p.url,
                "subreddit": p.subreddit,
                "score": p.score,
                "num_comments": p.num_comments,
                "selftext": p.selftext,
                "author": p.author,
            }
            for p in posts
        ]
        return json.dumps(payload, ensure_ascii=False)


# ───────────────────────────────────────────────────────────────────────────
# YouTube — search
# ───────────────────────────────────────────────────────────────────────────


class _YouTubeTrendsInput(BaseModel):
    query: str = Field(description="Search query for YouTube videos.")
    upload_date: str = Field(
        default="this_week",
        description="One of: today, this_week, this_month, this_year.",
    )
    sort_by: str = Field(
        default="popular",
        description="One of: relevance, popular.",
    )
    limit: int = Field(default=10, ge=1, le=30)


class YouTubeTrendsTool(BaseTool):
    name: str = "youtube_trending"
    description: str = (
        "Search YouTube for recent videos matching a query. Use to surface "
        "what creators are publishing on a topic right now. Returns a JSON "
        "list of {title, url, channel, published_time, view_count_text}. "
        "Cite the `url` field verbatim."
    )
    args_schema: type[BaseModel] = _YouTubeTrendsInput

    def _run(
        self,
        query: str,
        upload_date: str = "this_week",
        sort_by: str = "popular",
        limit: int = 10,
    ) -> str:
        videos = asyncio.run(
            scrapecreators.youtube_search(
                query=query,
                upload_date=upload_date,  # type: ignore[arg-type]
                sort_by=sort_by,  # type: ignore[arg-type]
                limit=limit,
            )
        )

        label = f"YouTube · {query}"
        emitter = sources_emitter_var.get()
        if emitter is not None:
            emitter(
                label,
                [
                    SourceRef(
                        title=v.title,
                        url=v.url,
                        published_date=v.published_time,
                        snippet=(
                            f"{v.channel} · {v.view_count_text or ''}".strip(" ·")
                            or None
                        ),
                        platform="youtube",
                        thumbnail=(
                            f"https://i.ytimg.com/vi/{v.video_id}/mqdefault.jpg"
                            if v.video_id
                            else None
                        ),
                        meta={
                            "channel": v.channel,
                            "view_count_text": v.view_count_text,
                            "duration": v.duration,
                            "video_id": v.video_id,
                        },
                    )
                    for v in videos
                ],
            )

        payload = [
            {
                "title": v.title,
                "url": v.url,
                "channel": v.channel,
                "published_time": v.published_time,
                "view_count_text": v.view_count_text,
                "duration": v.duration,
            }
            for v in videos
        ]
        return json.dumps(payload, ensure_ascii=False)


# ───────────────────────────────────────────────────────────────────────────
# X / Twitter — user's top tweets
# ───────────────────────────────────────────────────────────────────────────


class _XTweetsInput(BaseModel):
    handle: str = Field(
        description="X/Twitter handle without the @ prefix, e.g. 'OpenAI'."
    )
    limit: int = Field(default=15, ge=1, le=50)


class XUserTweetsTool(BaseTool):
    name: str = "x_user_tweets"
    description: str = (
        "Fetch a public X (Twitter) account's most-popular tweets. Use to "
        "surface what a specific founder, builder, or thought-leader is "
        "currently being amplified for. Twitter only exposes ~100 popular "
        "tweets per account publicly. Returns a JSON list of {text, url, "
        "handle, like_count, view_count}. Cite the `url` field verbatim."
    )
    args_schema: type[BaseModel] = _XTweetsInput

    def _run(self, handle: str, limit: int = 15) -> str:
        tweets = asyncio.run(
            scrapecreators.x_user_tweets(handle=handle, limit=limit)
        )

        label = f"@{handle}"
        emitter = sources_emitter_var.get()
        if emitter is not None:
            emitter(
                label,
                [
                    SourceRef(
                        title=(t.text[:120] or f"@{handle}"),
                        url=t.url,
                        published_date=t.created_at,
                        snippet=t.text[:280] or None,
                        platform="x",
                        meta={
                            "handle": t.handle,
                            "like_count": t.like_count,
                            "view_count": t.view_count,
                            "reply_count": t.reply_count,
                            "retweet_count": t.retweet_count,
                            "full_text": t.text,
                        },
                    )
                    for t in tweets
                ],
            )

        payload = [
            {
                "text": t.text,
                "url": t.url,
                "handle": t.handle,
                "created_at": t.created_at,
                "like_count": t.like_count,
                "view_count": t.view_count,
                "reply_count": t.reply_count,
                "retweet_count": t.retweet_count,
            }
            for t in tweets
        ]
        return json.dumps(payload, ensure_ascii=False)


# ───────────────────────────────────────────────────────────────────────────
# Instagram — reels search by keyword
# ───────────────────────────────────────────────────────────────────────────


class _InstagramReelsInput(BaseModel):
    query: str = Field(description="Keyword to search Instagram reels for.")
    date_posted: str = Field(
        default="last-week",
        description=(
            "One of: last-hour, last-day, last-week, last-month, last-year."
        ),
    )
    limit: int = Field(default=10, ge=1, le=30)


class InstagramReelsTool(BaseTool):
    name: str = "instagram_reels"
    description: str = (
        "Search Instagram reels by keyword. Use to surface short-form video "
        "trends — what creators are filming on a topic right now. Returns a "
        "JSON list of {caption, url, owner_handle, play_count, like_count, "
        "comment_count}. Cite the `url` field verbatim."
    )
    args_schema: type[BaseModel] = _InstagramReelsInput

    def _run(
        self,
        query: str,
        date_posted: str = "last-week",
        limit: int = 10,
    ) -> str:
        reels = asyncio.run(
            scrapecreators.instagram_reels_search(
                query=query,
                date_posted=date_posted,  # type: ignore[arg-type]
                limit=limit,
            )
        )

        label = f"IG · {query}"
        emitter = sources_emitter_var.get()
        if emitter is not None:
            emitter(
                label,
                [
                    SourceRef(
                        title=(r.caption[:120] or f"@{r.owner_handle or 'reel'}"),
                        url=r.url,
                        published_date=r.taken_at,
                        snippet=r.caption[:280] or None,
                        platform="instagram",
                        meta={
                            "owner_handle": r.owner_handle,
                            "owner_full_name": r.owner_full_name,
                            "play_count": r.play_count,
                            "like_count": r.like_count,
                            "comment_count": r.comment_count,
                            "duration_sec": r.duration_sec,
                        },
                    )
                    for r in reels
                ],
            )

        payload = [
            {
                "caption": r.caption,
                "url": r.url,
                "owner_handle": r.owner_handle,
                "owner_full_name": r.owner_full_name,
                "play_count": r.play_count,
                "like_count": r.like_count,
                "comment_count": r.comment_count,
                "duration_sec": r.duration_sec,
            }
            for r in reels
        ]
        return json.dumps(payload, ensure_ascii=False)
