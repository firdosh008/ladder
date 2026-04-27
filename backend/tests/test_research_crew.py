"""Tests for the Research crew + /ws/agents/research route.

Coverage:
  - ExaSearchTool wraps exa.search correctly and emits sources via
    the ContextVar side-channel.
  - Pydantic models validate the draft shape (incl. score bounds).
  - The WebSocket route auths + streams events from run_research verbatim,
    terminates with a `complete` event carrying the draft count + cost.
  - The route performs NO ideas-table writes (drafts are persisted by the
    frontend when the user picks one — per PRD §2.1).
"""

from __future__ import annotations

import json
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.agents.research.streaming import SourceRef, sources_emitter_var
from app.agents.research.tools import (
    ExaSearchTool,
    InstagramReelsTool,
    RedditSearchTool,
    RedditTrendsTool,
    XUserTweetsTool,
    YouTubeTrendsTool,
)
from app.models.db import IdeaDraft, ResearchIdeas
from app.providers.exa import ExaResult
from app.providers.scrapecreators import (
    InstagramReel,
    RedditPost,
    RedditSearchHit,
    XTweet,
    YouTubeVideo,
    parse_relative_time_hours,
    parse_view_count_text,
)


# ---------------------------------------------------------------------------
# ExaSearchTool
# ---------------------------------------------------------------------------


def test_exa_tool_serialises_results_as_json() -> None:
    fake = [
        ExaResult(
            title="Hook",
            url="https://x.test/1",
            text="body",
            published_date="2026-04-10",
            score=0.87,
        )
    ]

    async def fake_search(query: str, num_results: int = 8) -> list[ExaResult]:
        assert query == "ai agents"
        assert num_results == 5
        return fake

    with patch("app.agents.research.tools.exa.search", fake_search):
        out = ExaSearchTool()._run(query="ai agents", num_results=5)

    payload = json.loads(out)
    assert payload == [
        {
            "title": "Hook",
            "url": "https://x.test/1",
            "text": "body",
            "published_date": "2026-04-10",
            "score": 0.87,
        }
    ]


def test_exa_tool_emits_sources_when_emitter_set() -> None:
    fake = [
        ExaResult(
            title="Outlier finding",
            url="https://x.test/outlier",
            text="body text " * 40,
            published_date="2026-04-10",
            score=0.9,
        ),
        ExaResult(
            title="Context piece",
            url="https://x.test/context",
            text="shorter body",
            published_date=None,
            score=0.8,
        ),
    ]

    emissions: list[tuple[str, list[SourceRef]]] = []

    def emit(query: str, sources: list[SourceRef]) -> None:
        emissions.append((query, sources))

    async def fake_search(query: str, num_results: int = 8) -> list[ExaResult]:
        return fake

    token = sources_emitter_var.set(emit)
    try:
        with patch("app.agents.research.tools.exa.search", fake_search):
            ExaSearchTool()._run(query="ai agents", num_results=8)
    finally:
        sources_emitter_var.reset(token)

    assert len(emissions) == 1
    query, sources = emissions[0]
    assert query == "ai agents"
    assert len(sources) == 2
    assert sources[0].url == "https://x.test/outlier"
    assert sources[0].title == "Outlier finding"
    assert sources[0].snippet and len(sources[0].snippet) <= 280


def test_exa_tool_is_a_noop_when_no_emitter() -> None:
    fake = [
        ExaResult(title="x", url="https://x.test/1", text="y", published_date=None, score=None)
    ]

    async def fake_search(query: str, num_results: int = 8) -> list[ExaResult]:
        return fake

    # sources_emitter_var is unset at module scope
    with patch("app.agents.research.tools.exa.search", fake_search):
        out = ExaSearchTool()._run(query="x")
    assert json.loads(out)[0]["url"] == "https://x.test/1"


def test_exa_tool_tags_sources_with_web_platform() -> None:
    fake = [ExaResult(title="t", url="https://x.test/1", text="b", published_date=None, score=None)]
    emissions: list[tuple[str, list[SourceRef]]] = []

    async def fake_search(query: str, num_results: int = 8) -> list[ExaResult]:
        del query, num_results
        return fake

    token = sources_emitter_var.set(lambda q, s: emissions.append((q, s)))
    try:
        with patch("app.agents.research.tools.exa.search", fake_search):
            ExaSearchTool()._run(query="ai")
    finally:
        sources_emitter_var.reset(token)
    assert emissions[0][1][0].platform == "web"


# ---------------------------------------------------------------------------
# RedditTrendsTool
# ---------------------------------------------------------------------------


def test_reddit_tool_serialises_and_emits_platform_tagged_sources() -> None:
    fake = [
        RedditPost(
            title="Ex-founders moving back to corporate — what roles?",
            url="https://reddit.com/r/startups/comments/abc/test",
            subreddit="startups",
            score=79,
            num_comments=42,
            created_utc=1776977641,
            selftext="long body " * 20,
            author="Full_Marketing9298",
        ),
    ]
    emissions: list[tuple[str, list[SourceRef]]] = []

    async def fake_fetch(
        subreddit: str,
        sort: str = "hot",
        timeframe: str = "week",
        limit: int = 15,
    ) -> list[RedditPost]:
        assert subreddit == "startups"
        assert sort == "top"
        assert timeframe == "week"
        del limit
        return fake

    token = sources_emitter_var.set(lambda q, s: emissions.append((q, s)))
    try:
        with patch(
            "app.agents.research.tools.scrapecreators.reddit_subreddit",
            fake_fetch,
        ):
            out = RedditTrendsTool()._run(
                subreddit="startups", sort="top", timeframe="week"
            )
    finally:
        sources_emitter_var.reset(token)

    payload = json.loads(out)
    assert payload[0]["url"] == "https://reddit.com/r/startups/comments/abc/test"
    assert payload[0]["score"] == 79
    assert payload[0]["subreddit"] == "startups"

    assert len(emissions) == 1
    label, sources = emissions[0]
    assert label == "r/startups · top"
    assert sources[0].platform == "reddit"
    assert sources[0].url == "https://reddit.com/r/startups/comments/abc/test"


# ---------------------------------------------------------------------------
# YouTubeTrendsTool
# ---------------------------------------------------------------------------


def test_youtube_tool_serialises_and_emits_platform_tagged_sources() -> None:
    fake = [
        YouTubeVideo(
            video_id="3wMwdzxIyN0",
            url="https://www.youtube.com/watch?v=3wMwdzxIyN0",
            title="Google Announces Gemini Enterprise Agent Platform",
            channel="Some Channel",
            published_time="1 day ago",
            view_count_text="42K views",
            duration="12:30",
        )
    ]
    emissions: list[tuple[str, list[SourceRef]]] = []

    async def fake_fetch(
        query: str,
        upload_date: str = "this_week",
        sort_by: str = "popular",
        limit: int = 10,
    ) -> list[YouTubeVideo]:
        assert query == "ai agents"
        assert sort_by == "popular"
        del upload_date, limit
        return fake

    token = sources_emitter_var.set(lambda q, s: emissions.append((q, s)))
    try:
        with patch(
            "app.agents.research.tools.scrapecreators.youtube_search", fake_fetch
        ):
            out = YouTubeTrendsTool()._run(query="ai agents")
    finally:
        sources_emitter_var.reset(token)

    payload = json.loads(out)
    assert payload[0]["url"] == "https://www.youtube.com/watch?v=3wMwdzxIyN0"
    assert payload[0]["channel"] == "Some Channel"

    label, sources = emissions[0]
    assert label == "YouTube · ai agents"
    assert sources[0].platform == "youtube"
    assert sources[0].published_date == "1 day ago"


# ---------------------------------------------------------------------------
# XUserTweetsTool
# ---------------------------------------------------------------------------


def test_x_tool_serialises_and_emits_platform_tagged_sources() -> None:
    fake = [
        XTweet(
            tweet_id="2047743592278745425",
            url="https://x.com/OpenAI/status/2047743592278745425",
            text="Some tweet body",
            handle="OpenAI",
            created_at="Fri Apr 24 18:24:52 +0000 2026",
            like_count=1234,
            view_count=440886,
            reply_count=10,
            retweet_count=42,
        )
    ]
    emissions: list[tuple[str, list[SourceRef]]] = []

    async def fake_fetch(handle: str, limit: int = 15) -> list[XTweet]:
        assert handle == "OpenAI"
        del limit
        return fake

    token = sources_emitter_var.set(lambda q, s: emissions.append((q, s)))
    try:
        with patch(
            "app.agents.research.tools.scrapecreators.x_user_tweets", fake_fetch
        ):
            out = XUserTweetsTool()._run(handle="OpenAI")
    finally:
        sources_emitter_var.reset(token)

    payload = json.loads(out)
    assert payload[0]["url"] == "https://x.com/OpenAI/status/2047743592278745425"
    assert payload[0]["view_count"] == 440886

    label, sources = emissions[0]
    assert label == "@OpenAI"
    assert sources[0].platform == "x"


# ---------------------------------------------------------------------------
# InstagramReelsTool
# ---------------------------------------------------------------------------


def test_instagram_tool_serialises_and_emits_platform_tagged_sources() -> None:
    fake = [
        InstagramReel(
            reel_id="DOq6eV6iIgD",
            url="https://www.instagram.com/reel/DOq6eV6iIgD",
            caption="A long caption about ai agents",
            owner_handle="some_creator",
            owner_full_name="Some Creator",
            play_count=120000,
            like_count=4200,
            comment_count=88,
            duration_sec=42.5,
            taken_at="2026-04-20T12:00:00Z",
        )
    ]
    emissions: list[tuple[str, list[SourceRef]]] = []

    async def fake_fetch(
        query: str,
        date_posted: str = "last-week",
        limit: int = 10,
    ) -> list[InstagramReel]:
        assert query == "ai agents"
        del date_posted, limit
        return fake

    token = sources_emitter_var.set(lambda q, s: emissions.append((q, s)))
    try:
        with patch(
            "app.agents.research.tools.scrapecreators.instagram_reels_search",
            fake_fetch,
        ):
            out = InstagramReelsTool()._run(query="ai agents")
    finally:
        sources_emitter_var.reset(token)

    payload = json.loads(out)
    assert payload[0]["url"] == "https://www.instagram.com/reel/DOq6eV6iIgD"
    assert payload[0]["play_count"] == 120000
    assert payload[0]["owner_handle"] == "some_creator"

    label, sources = emissions[0]
    assert label == "IG · ai agents"
    assert sources[0].platform == "instagram"


def test_instagram_provider_swallows_404_not_found_as_empty() -> None:
    """ScrapeCreators returns 404 + error:not_found for niche queries with no
    matches. The provider should treat this as an empty result, not raise."""
    import httpx
    from app.providers import scrapecreators

    async def fake_get(self: Any, url: str, headers: Any = None, params: Any = None) -> httpx.Response:  # noqa: ARG001
        del self, url, headers, params
        return httpx.Response(
            404,
            json={"success": False, "error": "not_found", "message": "No reels found"},
        )

    async def run() -> list[InstagramReel]:
        with patch("app.providers.scrapecreators.settings.SCRAPECREATORS_API_KEY", "k"):
            with patch.object(httpx.AsyncClient, "get", fake_get):
                return await scrapecreators.instagram_reels_search("nichequery")

    import asyncio as _asyncio

    result = _asyncio.run(run())
    assert result == []


# ---------------------------------------------------------------------------
# Provider parsers (YouTube view-count + relative-time strings)
# ---------------------------------------------------------------------------


def test_parse_view_count_text_handles_k_m_b_and_commas() -> None:
    assert parse_view_count_text("1.2M views") == 1_200_000
    assert parse_view_count_text("47K views") == 47_000
    assert parse_view_count_text("1,234 views") == 1234
    assert parse_view_count_text("2B views") == 2_000_000_000
    assert parse_view_count_text("") is None
    assert parse_view_count_text(None) is None
    assert parse_view_count_text("just text") is None


def test_parse_relative_time_hours_covers_units() -> None:
    assert parse_relative_time_hours("3 hours ago") == 3.0
    assert parse_relative_time_hours("1 day ago") == 24.0
    assert parse_relative_time_hours("2 weeks ago") == 24.0 * 14
    assert parse_relative_time_hours("1 month ago") == 24.0 * 30
    assert parse_relative_time_hours("nothing here") is None
    assert parse_relative_time_hours(None) is None


# ---------------------------------------------------------------------------
# RedditSearchTool — cross-Reddit discovery
# ---------------------------------------------------------------------------


def test_reddit_search_tool_returns_discovered_subreddits_ranked() -> None:
    fake = [
        RedditSearchHit(
            title="Building agents with Claude",
            url="https://reddit.com/r/LocalLLaMA/comments/a/x",
            subreddit="LocalLLaMA",
            score=420,
            num_comments=88,
            created_utc=int(__import__("time").time()) - 3600,
            selftext="body",
            author="u1",
        ),
        RedditSearchHit(
            title="How I shipped my first agent",
            url="https://reddit.com/r/LocalLLaMA/comments/b/y",
            subreddit="LocalLLaMA",
            score=210,
            num_comments=15,
            created_utc=int(__import__("time").time()) - 7200,
            selftext="b",
            author="u2",
        ),
        RedditSearchHit(
            title="Agent eval frameworks",
            url="https://reddit.com/r/MachineLearning/comments/c/z",
            subreddit="MachineLearning",
            score=180,
            num_comments=22,
            created_utc=int(__import__("time").time()) - 10800,
            selftext="c",
            author="u3",
        ),
    ]

    async def fake_search(
        query: str,
        sort: str = "top",
        timeframe: str = "week",
        limit: int = 25,
    ) -> list[RedditSearchHit]:
        assert query == "ai agents"
        del sort, timeframe, limit
        return fake

    emissions: list[tuple[str, list[SourceRef]]] = []
    token = sources_emitter_var.set(lambda q, s: emissions.append((q, s)))
    try:
        with patch(
            "app.agents.research.tools.scrapecreators.reddit_search", fake_search
        ):
            out = RedditSearchTool()._run(query="ai agents")
    finally:
        sources_emitter_var.reset(token)

    payload = json.loads(out)
    assert "discovered_subreddits" in payload
    assert "posts" in payload

    subs = payload["discovered_subreddits"]
    # LocalLLaMA outranks MachineLearning on summed score (420+210 vs 180).
    assert subs[0]["name"] == "LocalLLaMA"
    assert subs[0]["post_count"] == 2
    assert subs[0]["total_score"] == 630
    assert subs[0]["top_post_title"] == "Building agents with Claude"
    assert subs[1]["name"] == "MachineLearning"

    assert len(emissions) == 1
    label, sources = emissions[0]
    assert label == "reddit search · ai agents"
    assert all(s.platform == "reddit" for s in sources)


def test_reddit_search_tool_drops_low_score_posts() -> None:
    """Posts under REDDIT_MIN_SCORE shouldn't influence subreddit ranking."""
    now = int(__import__("time").time())
    fake = [
        RedditSearchHit(
            title="Real signal",
            url="https://reddit.com/r/Real/comments/a",
            subreddit="Real",
            score=120,
            num_comments=5,
            created_utc=now - 3600,
            selftext="",
            author=None,
        ),
        RedditSearchHit(
            title="Noise",
            url="https://reddit.com/r/NoiseSub/comments/b",
            subreddit="NoiseSub",
            score=2,  # below REDDIT_MIN_SCORE
            num_comments=0,
            created_utc=now - 3600,
            selftext="",
            author=None,
        ),
    ]

    async def fake_search(query: str, **_: Any) -> list[RedditSearchHit]:
        del query
        return fake

    with patch(
        "app.agents.research.tools.scrapecreators.reddit_search", fake_search
    ):
        out = RedditSearchTool()._run(query="x")

    payload = json.loads(out)
    sub_names = [s["name"] for s in payload["discovered_subreddits"]]
    assert "Real" in sub_names
    assert "NoiseSub" not in sub_names


# ---------------------------------------------------------------------------
# Numeric pre-filters in existing tools
# ---------------------------------------------------------------------------


def test_reddit_trends_tool_drops_low_score_and_stale_posts() -> None:
    import time as _time

    now = int(_time.time())
    fake = [
        RedditPost(
            title="Fresh hot",
            url="https://reddit.com/r/x/comments/1",
            subreddit="x",
            score=80,
            num_comments=5,
            created_utc=now - 3600,
            selftext="",
            author=None,
        ),
        RedditPost(
            title="Too old",
            url="https://reddit.com/r/x/comments/2",
            subreddit="x",
            score=200,
            num_comments=10,
            created_utc=now - 60 * 24 * 3600,  # 60 days old
            selftext="",
            author=None,
        ),
        RedditPost(
            title="Score too low",
            url="https://reddit.com/r/x/comments/3",
            subreddit="x",
            score=3,
            num_comments=0,
            created_utc=now - 3600,
            selftext="",
            author=None,
        ),
    ]

    async def fake_fetch(
        subreddit: str,
        sort: str = "hot",
        timeframe: str = "week",
        limit: int = 15,
    ) -> list[RedditPost]:
        del subreddit, sort, timeframe, limit
        return fake

    with patch(
        "app.agents.research.tools.scrapecreators.reddit_subreddit", fake_fetch
    ):
        out = RedditTrendsTool()._run(subreddit="x")

    payload = json.loads(out)
    titles = [p["title"] for p in payload]
    assert titles == ["Fresh hot"]


def test_youtube_tool_drops_videos_under_view_threshold() -> None:
    fake = [
        YouTubeVideo(
            video_id="a",
            url="https://www.youtube.com/watch?v=a",
            title="Big hit",
            channel="ch",
            published_time="1 day ago",
            view_count_text="120K views",
            duration="10:00",
        ),
        YouTubeVideo(
            video_id="b",
            url="https://www.youtube.com/watch?v=b",
            title="Tiny",
            channel="ch",
            published_time="1 day ago",
            view_count_text="800 views",
            duration="3:00",
        ),
    ]

    async def fake_fetch(
        query: str,
        upload_date: str = "this_week",
        sort_by: str = "popular",
        limit: int = 10,
    ) -> list[YouTubeVideo]:
        del query, upload_date, sort_by, limit
        return fake

    with patch(
        "app.agents.research.tools.scrapecreators.youtube_search", fake_fetch
    ):
        out = YouTubeTrendsTool()._run(query="ai")

    payload = json.loads(out)
    titles = [v["title"] for v in payload]
    assert titles == ["Big hit"]
    # Parsed view_count surfaces in the JSON payload too.
    assert payload[0]["view_count"] == 120_000


def test_x_tool_drops_low_engagement_tweets() -> None:
    fake = [
        XTweet(
            tweet_id="1",
            url="https://x.com/h/status/1",
            text="hot take",
            handle="h",
            created_at="now",
            like_count=5,  # 5 + 0*2 = 5 → drop
            view_count=10,
            reply_count=0,
            retweet_count=0,
        ),
        XTweet(
            tweet_id="2",
            url="https://x.com/h/status/2",
            text="amplified",
            handle="h",
            created_at="now",
            like_count=200,
            view_count=4000,
            reply_count=8,
            retweet_count=40,
        ),
    ]

    async def fake_fetch(handle: str, limit: int = 15) -> list[XTweet]:
        del handle, limit
        return fake

    with patch(
        "app.agents.research.tools.scrapecreators.x_user_tweets", fake_fetch
    ):
        out = XUserTweetsTool()._run(handle="h")

    payload = json.loads(out)
    ids = [t["url"] for t in payload]
    assert ids == ["https://x.com/h/status/2"]


def test_instagram_tool_drops_low_play_reels() -> None:
    fake = [
        InstagramReel(
            reel_id="hi",
            url="https://www.instagram.com/reel/hi",
            caption="",
            owner_handle="o",
            owner_full_name=None,
            play_count=100_000,
            like_count=1000,
            comment_count=10,
            duration_sec=12.0,
            taken_at=None,
        ),
        InstagramReel(
            reel_id="lo",
            url="https://www.instagram.com/reel/lo",
            caption="",
            owner_handle="o",
            owner_full_name=None,
            play_count=200,
            like_count=2,
            comment_count=0,
            duration_sec=12.0,
            taken_at=None,
        ),
    ]

    async def fake_fetch(
        query: str,
        date_posted: str = "last-week",
        limit: int = 10,
    ) -> list[InstagramReel]:
        del query, date_posted, limit
        return fake

    with patch(
        "app.agents.research.tools.scrapecreators.instagram_reels_search",
        fake_fetch,
    ):
        out = InstagramReelsTool()._run(query="x")

    payload = json.loads(out)
    urls = [r["url"] for r in payload]
    assert urls == ["https://www.instagram.com/reel/hi"]


# ---------------------------------------------------------------------------
# Pydantic validation
# ---------------------------------------------------------------------------


def test_idea_draft_validates_score_bounds() -> None:
    with pytest.raises(ValueError):
        IdeaDraft(title="ok", opportunity_score=150)
    with pytest.raises(ValueError):
        IdeaDraft(title="ok", opportunity_score=-1)
    IdeaDraft(title="ok", opportunity_score=0)
    IdeaDraft(title="ok", opportunity_score=100)


def test_idea_draft_validates_outlier_bounds() -> None:
    with pytest.raises(ValueError):
        IdeaDraft(title="ok", outlier_score=11)
    with pytest.raises(ValueError):
        IdeaDraft(title="ok", outlier_score=-0.1)
    IdeaDraft(title="ok", outlier_score=0)
    IdeaDraft(title="ok", outlier_score=10)


def test_idea_draft_defaults_suggested_tags_to_empty_list() -> None:
    d = IdeaDraft(title="ok")
    assert d.suggested_tags == []


def test_research_ideas_requires_at_least_one_draft() -> None:
    with pytest.raises(ValueError):
        ResearchIdeas(ideas=[])


# ---------------------------------------------------------------------------
# WebSocket route — with run_research mocked
# ---------------------------------------------------------------------------


USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _profile_client(profile_row: dict | None) -> tuple[AsyncMock, MagicMock]:
    """Builder for the user_profiles select used by _load_profile."""
    response = MagicMock()
    response.data = profile_row

    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.maybe_single.return_value = builder
    builder.execute = AsyncMock(return_value=response)

    sb = MagicMock()
    sb.from_.return_value = builder
    return AsyncMock(return_value=sb), sb


@pytest.fixture
def ws_client() -> Callable[[], TestClient]:
    from app.main import app

    def _build() -> TestClient:
        return TestClient(app)

    return _build


def _fake_run_research(ideas_payload: list[dict]):
    async def _gen(
        _user_id: Any,
        _profile: Any,
        topic: str,
        target_duration_min: int = 10,
    ):
        del target_duration_min
        yield {"type": "agent_start", "agent": "search_agent"}
        yield {
            "type": "tool_call",
            "agent": "search_agent",
            "tool": "web_search",
            "arguments": json.dumps({"query": topic, "num_results": 10}),
        }
        yield {
            "type": "sources",
            "query": topic,
            "items": [
                {
                    "title": "Source 1",
                    "url": "https://x.test/1",
                    "published_date": "2026-04-01",
                    "snippet": "first snippet",
                },
                {
                    "title": "Source 2",
                    "url": "https://x.test/2",
                    "published_date": None,
                    "snippet": "second snippet",
                },
            ],
        }
        yield {
            "type": "text_delta",
            "agent": "search_agent",
            "content": "partial thought …",
        }
        yield {"type": "task_complete", "agent": "idea_formulator", "preview": ""}
        yield {
            "type": "ideas_ready",
            "ideas": ideas_payload,
            "token_usage": {"input": 1000, "output": 2500, "cost_usd": 0.04},
        }

    return _gen


def _drain_until_close(ws) -> tuple[int | None, list[dict]]:
    from starlette.websockets import WebSocketDisconnect

    events: list[dict] = []
    try:
        while True:
            events.append(ws.receive_json())
    except WebSocketDisconnect as e:
        return e.code, events
    except Exception:
        return None, events


async def test_ws_rejects_missing_token(ws_client: Callable[[], TestClient]) -> None:
    with ws_client() as c:
        with c.websocket_connect("/ws/agents/research?topic=test") as ws:
            code, _ = _drain_until_close(ws)
    assert code == 4401


async def test_ws_rejects_blank_topic(
    ws_client: Callable[[], TestClient],
    make_jwt: Callable[..., str],
) -> None:
    token = make_jwt(user_id=USER_A)
    with ws_client() as c:
        with c.websocket_connect(
            f"/ws/agents/research?token={token}&topic="
        ) as ws:
            code, _ = _drain_until_close(ws)
    assert code == 4400


async def test_ws_streams_events_and_never_writes_ideas(
    ws_client: Callable[[], TestClient],
    make_jwt: Callable[..., str],
) -> None:
    """Per PRD §2.1 the route never persists drafts — it only streams them to
    the client. The frontend saves the one the user picks."""
    token = make_jwt(user_id=USER_A)
    drafts = [
        {
            "title": f"Idea {i}",
            "rationale": "signal",
            "idea_type": "framework",
            "opportunity_score": 80 - i,
            "outlier_score": 6.0 + i,
            "why_now": "trending this week",
            "suggested_tags": ["ai", "agents"],
        }
        for i in range(3)
    ]
    profile_row = {
        "display_name": "Alex",
        "positioning": "founder",
        "audience": "founders",
        "voice": "direct",
        "creators_followed": None,
        "things_to_avoid": None,
    }
    profile_mock, profile_sb = _profile_client(profile_row)

    with (
        patch("app.routes.agents.user_client", profile_mock),
        patch(
            "app.routes.agents.run_research",
            _fake_run_research(drafts),
        ),
    ):
        with ws_client() as c:
            with c.websocket_connect(
                f"/ws/agents/research?token={token}&topic=ai+agents"
            ) as ws:
                events = []
                while True:
                    try:
                        events.append(ws.receive_json())
                    except Exception:
                        break
                    if events[-1]["type"] == "complete":
                        break

    types = [e["type"] for e in events]
    assert types[0] == "agent_start"
    assert "tool_call" in types
    assert "sources" in types
    assert "text_delta" in types
    assert "task_complete" in types
    assert "ideas_ready" in types
    assert types[-1] == "complete"
    # No idea_saved events — drafts are not persisted by the route.
    assert "idea_saved" not in types

    sources_ev = next(e for e in events if e["type"] == "sources")
    assert sources_ev["query"] == "ai agents"
    assert len(sources_ev["items"]) == 2
    assert sources_ev["items"][0]["url"] == "https://x.test/1"

    tool_call_ev = next(e for e in events if e["type"] == "tool_call")
    assert tool_call_ev["tool"] == "web_search"
    assert tool_call_ev["agent"] == "search_agent"
    # arguments is a JSON string of the tool call args
    args = json.loads(tool_call_ev["arguments"])
    assert args["query"] == "ai agents"

    ideas_ready = next(e for e in events if e["type"] == "ideas_ready")
    assert len(ideas_ready["ideas"]) == 3
    # Full PRD §11.8 shape made it through.
    for idea in ideas_ready["ideas"]:
        assert set(idea.keys()) >= {
            "title",
            "rationale",
            "idea_type",
            "opportunity_score",
            "outlier_score",
            "why_now",
            "suggested_tags",
        }

    complete = events[-1]
    assert complete["count"] == 3
    assert complete["cost_usd"] == pytest.approx(0.04)

    # user_client was called exactly once (profile load) — no insert clients.
    assert profile_mock.await_count == 1
    # Only the user_profiles table was ever touched.
    assert profile_sb.from_.call_args_list == [
        (("user_profiles",), {}),
    ]
