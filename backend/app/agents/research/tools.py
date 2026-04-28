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
import time
from collections import defaultdict
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


def _hours_since(ts: int | None) -> float:
    """Hours between unix timestamp and now. Returns 1.0 when ts is missing
    or in the future — treats those as 'very fresh' so they aren't penalised
    by the velocity ranker."""
    if not ts:
        return 1.0
    try:
        delta = time.time() - float(ts)
    except (TypeError, ValueError):
        return 1.0
    return max(delta / 3600.0, 1.0)


# Numeric quality gates. Tuned conservatively — the goal is to drop the
# obvious noise (zero-engagement posts, ancient stragglers) without
# starving niche topics. Tighten later if signal still feels muddy.
REDDIT_MIN_SCORE = 10
REDDIT_MAX_AGE_HOURS = 28 * 24  # 28 days
YOUTUBE_MIN_VIEWS = 5_000
YOUTUBE_MAX_AGE_HOURS = 90 * 24
INSTAGRAM_MIN_PLAYS = 5_000
X_MIN_ENGAGEMENT = 30  # likes + retweets*2


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

        # Quality gate + velocity rank. Drop low-engagement / stale posts
        # before the LLM scorer ever sees them — cheaper and more reliable
        # than letting the LLM judge raw counts.
        filtered = [
            p
            for p in posts
            if p.score >= REDDIT_MIN_SCORE
            and _hours_since(p.created_utc) <= REDDIT_MAX_AGE_HOURS
        ]
        filtered.sort(
            key=lambda p: p.score / _hours_since(p.created_utc), reverse=True
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
                    for p in filtered
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
            for p in filtered
        ]
        return json.dumps(payload, ensure_ascii=False)


# ───────────────────────────────────────────────────────────────────────────
# Reddit — cross-subreddit keyword search (community discovery)
# ───────────────────────────────────────────────────────────────────────────


class _RedditSearchInput(BaseModel):
    query: str = Field(
        description="Keyword/phrase to search across all of Reddit.",
    )
    timeframe: str = Field(
        default="week",
        description="Recency window: day, week, month, year, all.",
    )
    sort: str = Field(
        default="top",
        description="One of: relevance, new, top, comment_count.",
    )
    limit: int = Field(default=25, ge=5, le=50)


class RedditSearchTool(BaseTool):
    name: str = "reddit_search"
    description: str = (
        "Search ALL of Reddit for posts matching a topic — use this BEFORE "
        "calling reddit_trending so you can discover which subreddits are "
        "actually discussing the topic instead of guessing community names. "
        "Returns a JSON object with two keys: `discovered_subreddits` (the "
        "communities ranked by post-density and total upvote weight on this "
        "topic — pick the top 2-3 to drill into with reddit_trending) and "
        "`posts` (top matching threads across Reddit). Cite `url` verbatim."
    )
    args_schema: type[BaseModel] = _RedditSearchInput

    def _run(
        self,
        query: str,
        timeframe: str = "week",
        sort: str = "top",
        limit: int = 25,
    ) -> str:
        hits = asyncio.run(
            scrapecreators.reddit_search(
                query=query,
                sort=sort,  # type: ignore[arg-type]
                timeframe=timeframe,  # type: ignore[arg-type]
                limit=limit,
            )
        )

        # Same quality gate as reddit_trending so weak threads don't sway
        # subreddit ranking.
        filtered = [
            h
            for h in hits
            if h.score >= REDDIT_MIN_SCORE
            and _hours_since(h.created_utc) <= REDDIT_MAX_AGE_HOURS
        ]

        # Group by subreddit → post_count + summed score + highest-score
        # post title. The agent uses this ranking to choose which subreddits
        # to drill into.
        by_sub: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "post_count": 0,
                "total_score": 0,
                "top_post_title": "",
                "_top_score": -1,
            }
        )
        for h in filtered:
            sub = h.subreddit or "unknown"
            entry = by_sub[sub]
            entry["post_count"] += 1
            entry["total_score"] += h.score
            if h.score > entry["_top_score"]:
                entry["_top_score"] = h.score
                entry["top_post_title"] = h.title
        for entry in by_sub.values():
            entry.pop("_top_score", None)

        discovered = [
            {"name": sub, **stats}
            for sub, stats in sorted(
                by_sub.items(),
                key=lambda kv: (kv[1]["total_score"], kv[1]["post_count"]),
                reverse=True,
            )
        ]

        # Sort posts themselves by velocity for the bullet list.
        filtered.sort(
            key=lambda h: h.score / _hours_since(h.created_utc), reverse=True
        )

        label = f"reddit search · {query}"
        emitter = sources_emitter_var.get()
        if emitter is not None:
            emitter(
                label,
                [
                    SourceRef(
                        title=h.title,
                        url=h.url,
                        published_date=_iso_from_unix(h.created_utc),
                        snippet=(h.selftext or h.title)[:280] or None,
                        platform="reddit",
                        meta={
                            "subreddit": h.subreddit,
                            "score": h.score,
                            "num_comments": h.num_comments,
                            "author": h.author,
                        },
                    )
                    for h in filtered
                ],
            )

        payload = {
            "discovered_subreddits": discovered,
            "posts": [
                {
                    "title": h.title,
                    "url": h.url,
                    "subreddit": h.subreddit,
                    "score": h.score,
                    "num_comments": h.num_comments,
                    "selftext": h.selftext,
                }
                for h in filtered
            ],
        }
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
        # Quality gate by parsed view count + age. When parsing fails we keep
        # the item rather than drop it (parse failure shouldn't be the same
        # signal as 'low quality'). Same conditions as before — escalation
        # below cannot relax these.
        def _keep(v: scrapecreators.YouTubeVideo) -> bool:
            views = scrapecreators.parse_view_count_text(v.view_count_text)
            age_h = scrapecreators.parse_relative_time_hours(v.published_time)
            if views is not None and views < YOUTUBE_MIN_VIEWS:
                return False
            if age_h is not None and age_h > YOUTUBE_MAX_AGE_HOURS:
                return False
            return True

        def _velocity(v: scrapecreators.YouTubeVideo) -> float:
            views = scrapecreators.parse_view_count_text(v.view_count_text) or 0
            age_h = scrapecreators.parse_relative_time_hours(v.published_time) or 24.0
            return views / max(age_h, 1.0)

        # Window ladder. scrapecreators returns ~one page (~20 raw videos)
        # per call and ignores client-side pagination, so on niche queries
        # the requested window often yields < `limit` after the view/age
        # gate. Escalate to a wider upload_date until we have enough kept
        # candidates. The 90-day MAX_AGE_HOURS in `_keep` still bounds how
        # old the merged pool can be, so escalation never leaks stale hits.
        LADDER = ["today", "this_week", "this_month", "this_year"]
        try:
            start_idx = LADDER.index(upload_date)
        except ValueError:
            start_idx = LADDER.index("this_week")

        raw_buffer = max(limit * 5, 50)
        seen_ids: set[str] = set()
        pooled: list[scrapecreators.YouTubeVideo] = []

        for window in LADDER[start_idx:]:
            page = asyncio.run(
                scrapecreators.youtube_search(
                    query=query,
                    upload_date=window,  # type: ignore[arg-type]
                    sort_by=sort_by,  # type: ignore[arg-type]
                    limit=raw_buffer,
                )
            )
            for v in page:
                key = v.video_id or v.url
                if not key or key in seen_ids:
                    continue
                seen_ids.add(key)
                pooled.append(v)
            kept_count = sum(1 for v in pooled if _keep(v))
            if kept_count >= limit:
                break

        filtered = [v for v in pooled if _keep(v)]
        filtered.sort(key=_velocity, reverse=True)
        filtered = filtered[:limit]

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
                            "view_count": scrapecreators.parse_view_count_text(
                                v.view_count_text
                            ),
                            "duration": v.duration,
                            "video_id": v.video_id,
                        },
                    )
                    for v in filtered
                ],
            )

        payload = [
            {
                "title": v.title,
                "url": v.url,
                "channel": v.channel,
                "published_time": v.published_time,
                "view_count_text": v.view_count_text,
                "view_count": scrapecreators.parse_view_count_text(
                    v.view_count_text
                ),
                "duration": v.duration,
            }
            for v in filtered
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

        # Engagement = likes + retweets*2. Retweets weighted higher because
        # they signal endorsement, not just glance-and-tap. Drop tweets below
        # the threshold so the LLM doesn't waste tokens on filler.
        def _engagement(t: scrapecreators.XTweet) -> int:
            return (t.like_count or 0) + (t.retweet_count or 0) * 2

        filtered = [t for t in tweets if _engagement(t) >= X_MIN_ENGAGEMENT]
        filtered.sort(key=_engagement, reverse=True)

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
                    for t in filtered
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
            for t in filtered
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

        # Quality gate: drop reels under the play threshold; sort by plays
        # descending so the highest-reach reels lead the bullet list.
        # IG's `taken_at` format is inconsistent (sometimes ISO, sometimes
        # unix-int) so we don't gate on age here — `date_posted` already
        # filters server-side.
        filtered = [
            r for r in reels if (r.play_count or 0) >= INSTAGRAM_MIN_PLAYS
        ]
        filtered.sort(key=lambda r: r.play_count or 0, reverse=True)

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
                    for r in filtered
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
            for r in filtered
        ]
        return json.dumps(payload, ensure_ascii=False)
