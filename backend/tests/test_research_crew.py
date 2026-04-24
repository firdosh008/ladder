"""Tests for the Research crew + /ws/agents/research route.

Coverage:
  - ExaSearchTool wraps exa.search correctly.
  - _step_to_event / _task_to_event produce the expected wire events.
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

from app.agents.research import crew as crew_mod
from app.agents.research.tools import ExaSearchTool
from app.models.db import IdeaDraft, ResearchIdeas
from app.providers.exa import ExaResult


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


# ---------------------------------------------------------------------------
# Event normalisation
# ---------------------------------------------------------------------------


def test_step_to_event_tool_call() -> None:
    step = MagicMock(spec=["tool", "tool_input", "agent"])
    step.tool = "web_search"
    step.tool_input = "ai agents trend"
    step.agent = "search_agent"
    ev = crew_mod._step_to_event(step)
    assert ev == {
        "type": "tool_call",
        "tool": "web_search",
        "query": "ai agents trend",
        "agent": "search_agent",
    }


def test_step_to_event_tool_result() -> None:
    step = MagicMock(spec=["result", "agent"])
    step.result = "x" * 500
    step.agent = "search_agent"
    ev = crew_mod._step_to_event(step)
    assert ev is not None
    assert ev["type"] == "tool_result"
    assert len(ev["preview"]) == 240


def test_task_to_event_shape() -> None:
    task_out = MagicMock(spec=["agent", "raw"])
    task_out.agent = "idea_formulator"
    task_out.raw = "some markdown output" * 30
    ev = crew_mod._task_to_event(task_out)
    assert ev["type"] == "task_complete"
    assert ev["agent"] == "idea_formulator"
    assert len(ev["preview"]) == 240


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


def _profile_client(profile_row: dict | None) -> AsyncMock:
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
            "tool": "web_search",
            "query": topic,
            "agent": "search_agent",
        }
        yield {"type": "task_complete", "agent": "idea_formulator"}
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
    assert "task_complete" in types
    assert "ideas_ready" in types
    assert types[-1] == "complete"
    # No idea_saved events — drafts are not persisted by the route.
    assert "idea_saved" not in types

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
