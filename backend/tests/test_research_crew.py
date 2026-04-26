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
    RedditTrendsTool,
    XUserTweetsTool,
    YouTubeTrendsTool,
)
from app.models.db import IdeaDraft, ResearchIdeas
from app.providers.exa import ExaResult
from app.providers.scrapecreators import (
    InstagramReel,
    RedditPost,
    XTweet,
    YouTubeVideo,
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
    async def _gen(_user_id: Any, _profile: Any, topic: str):
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
