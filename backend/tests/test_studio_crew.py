"""Tests for the Studio crew + /ws/agents/studio route.

Coverage:
  - Pydantic validation for Script / Outline / IdeaSlice.
  - WS auth + idea-id requirement.
  - End-to-end stream → persisted artifacts (script + outline) via mocked
    run_studio_script + supabase tables.
  - GET /studio-sessions/by-idea/{idea_id} returns the latest artifacts.
"""

from __future__ import annotations

from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.db import IdeaSlice, Outline, OutlineItem, Script, ScriptSection


USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
IDEA_A = "11111111-1111-1111-1111-111111111111"
SESSION_A = "22222222-2222-2222-2222-222222222222"
SCRIPT_A = "33333333-3333-3333-3333-333333333333"
OUTLINE_A = "44444444-4444-4444-4444-444444444444"


# ---------------------------------------------------------------------------
# Pydantic
# ---------------------------------------------------------------------------


def test_script_section_validates_duration_bounds() -> None:
    with pytest.raises(ValueError):
        ScriptSection(heading="x", duration_min=0, talking_points=["a"])
    with pytest.raises(ValueError):
        ScriptSection(heading="x", duration_min=20, talking_points=["a"])
    ScriptSection(heading="x", duration_min=1, talking_points=["a"])
    ScriptSection(heading="x", duration_min=15, talking_points=["a"])


def test_script_requires_at_least_two_sections() -> None:
    sec = ScriptSection(heading="x", duration_min=2, talking_points=["a"])
    with pytest.raises(ValueError):
        Script(sections=[sec])
    Script(sections=[sec, sec])


def test_outline_requires_three_items() -> None:
    item = OutlineItem(number=1, label="a", beat="b")
    with pytest.raises(ValueError):
        Outline(items=[item, item])
    Outline(items=[item, item, item])


def test_idea_slice_strips_unknown_idea_types() -> None:
    with pytest.raises(ValueError):
        IdeaSlice(title="x", idea_type="opinion")  # type: ignore[arg-type]
    IdeaSlice(title="x", idea_type="systems")


# ---------------------------------------------------------------------------
# WS route — mocked run_studio_script + supabase
# ---------------------------------------------------------------------------


@pytest.fixture
def ws_client() -> Callable[[], TestClient]:
    from app.main import app

    def _build() -> TestClient:
        return TestClient(app)

    return _build


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


def _fake_studio_run(script_payload: dict, outline_payload: dict):
    async def _gen(_user_id: Any, _profile: Any, _idea: Any, _duration: int):
        yield {"type": "agent_start", "agent": "script_writer"}
        yield {"type": "text_delta", "agent": "script_writer", "content": "writing…"}
        yield {"type": "task_complete", "agent": "script_writer", "preview": "done"}
        yield {"type": "script_ready", "script": script_payload}
        yield {"type": "agent_start", "agent": "outline_planner"}
        yield {"type": "task_complete", "agent": "outline_planner", "preview": "ok"}
        yield {"type": "outline_ready", "outline": outline_payload}
        yield {
            "type": "usage",
            "token_usage": {"input": 800, "output": 1500, "cost_usd": 0.025},
        }

    return _gen


def _supabase_studio_mock(idea_row: dict | None) -> AsyncMock:
    """Multi-table mock for the studio WS path.

    Tables used (in order):
      ideas            → select(...) for _load_idea
      user_profiles    → select(...) for _load_profile
      studio_sessions  → select(...) for existing session lookup, then insert(...)
      artifacts        → select(...) for next_version (×2), then insert(...)
      studio_sessions  → update(...) for scene_outline mirror
    """
    sb = MagicMock()

    # ideas SELECT
    ideas_response = MagicMock()
    ideas_response.data = idea_row
    ideas_builder = MagicMock()
    ideas_builder.select.return_value = ideas_builder
    ideas_builder.eq.return_value = ideas_builder
    ideas_builder.maybe_single.return_value = ideas_builder
    ideas_builder.execute = AsyncMock(return_value=ideas_response)

    # user_profiles SELECT
    profile_response = MagicMock()
    profile_response.data = {
        "display_name": "Alex",
        "positioning": "founder",
        "audience": "founders",
        "voice": "direct",
        "creators_followed": None,
        "things_to_avoid": None,
    }
    profile_builder = MagicMock()
    profile_builder.select.return_value = profile_builder
    profile_builder.eq.return_value = profile_builder
    profile_builder.maybe_single.return_value = profile_builder
    profile_builder.execute = AsyncMock(return_value=profile_response)

    # studio_sessions SELECT (existing lookup) → empty
    sess_select_response = MagicMock()
    sess_select_response.data = []
    sess_select_builder = MagicMock()
    sess_select_builder.select.return_value = sess_select_builder
    sess_select_builder.eq.return_value = sess_select_builder
    sess_select_builder.order.return_value = sess_select_builder
    sess_select_builder.limit.return_value = sess_select_builder
    sess_select_builder.execute = AsyncMock(return_value=sess_select_response)

    # studio_sessions INSERT → returns SESSION_A
    sess_insert_response = MagicMock()
    sess_insert_response.data = [{"id": SESSION_A}]
    sess_insert_chain = MagicMock()
    sess_insert_chain.execute = AsyncMock(return_value=sess_insert_response)

    # studio_sessions UPDATE (scene_outline mirror)
    sess_update_response = MagicMock()
    sess_update_response.data = []
    sess_update_chain = MagicMock()
    sess_update_chain.eq.return_value = sess_update_chain
    sess_update_chain.execute = AsyncMock(return_value=sess_update_response)

    studio_table = MagicMock()
    studio_table.select.side_effect = [
        sess_select_builder,
        sess_select_builder,
        sess_select_builder,
    ]
    studio_table.insert.return_value = sess_insert_chain
    studio_table.update.return_value = sess_update_chain
    # Also expose .select / .eq directly for the chain pattern.
    for attr in ("select", "eq", "order", "limit"):
        if not hasattr(sess_select_builder, attr):
            setattr(sess_select_builder, attr, MagicMock(return_value=sess_select_builder))

    # artifacts SELECT (version) — both calls return empty
    art_version_response = MagicMock()
    art_version_response.data = []
    art_version_builder = MagicMock()
    art_version_builder.select.return_value = art_version_builder
    art_version_builder.eq.return_value = art_version_builder
    art_version_builder.order.return_value = art_version_builder
    art_version_builder.limit.return_value = art_version_builder
    art_version_builder.execute = AsyncMock(return_value=art_version_response)

    # artifacts INSERT
    art_insert_response = MagicMock()
    art_insert_response.data = [
        {"id": SCRIPT_A, "type": "script"},
        {"id": OUTLINE_A, "type": "outline"},
    ]
    art_insert_chain = MagicMock()
    art_insert_chain.execute = AsyncMock(return_value=art_insert_response)

    artifacts_table = MagicMock()
    artifacts_table.select.return_value = art_version_builder
    artifacts_table.insert.return_value = art_insert_chain

    def from_(name: str):
        if name == "ideas":
            return ideas_builder
        if name == "user_profiles":
            return profile_builder
        if name == "studio_sessions":
            return studio_table
        if name == "artifacts":
            return artifacts_table
        raise AssertionError(f"unexpected table: {name}")

    sb.from_.side_effect = from_
    return AsyncMock(return_value=sb)


async def test_studio_ws_rejects_missing_idea_id(
    ws_client: Callable[[], TestClient],
    make_jwt: Callable[..., str],
) -> None:
    token = make_jwt(user_id=USER_A)
    with ws_client() as c:
        with c.websocket_connect(f"/ws/agents/studio?token={token}") as ws:
            code, _ = _drain_until_close(ws)
    assert code == 4400


async def test_studio_ws_rejects_missing_token(
    ws_client: Callable[[], TestClient],
) -> None:
    with ws_client() as c:
        with c.websocket_connect(
            f"/ws/agents/studio?idea_id={IDEA_A}"
        ) as ws:
            code, _ = _drain_until_close(ws)
    assert code == 4401


async def test_studio_ws_streams_persists_and_emits_persisted(
    ws_client: Callable[[], TestClient],
    make_jwt: Callable[..., str],
) -> None:
    token = make_jwt(user_id=USER_A)

    script_payload = {
        "sections": [
            {
                "heading": "Open with a sharp claim",
                "duration_min": 4,
                "talking_points": ["claim", "evidence", "stakes"],
                "transition": "next, the fix",
            },
            {
                "heading": "The fix",
                "duration_min": 6,
                "talking_points": ["step 1", "step 2", "step 3"],
                "transition": None,
            },
        ]
    }
    outline_payload = {
        "items": [
            {"number": 1, "label": "Sharp open", "beat": "Hook with the claim."},
            {"number": 2, "label": "The fix", "beat": "Three steps."},
            {"number": 3, "label": "Wrap", "beat": "Close with the takeaway."},
        ]
    }

    idea_row = {
        "id": IDEA_A,
        "title": "Ship faster",
        "body": None,
        "rationale": "founder voice",
        "idea_type": "framework",
        "opportunity_score": 80,
        "source_type": "manual",
        "source_content": None,
    }

    sb_mock = _supabase_studio_mock(idea_row)

    with (
        patch("app.routes.agents.user_client", sb_mock),
        patch(
            "app.routes.agents.run_studio_script",
            _fake_studio_run(script_payload, outline_payload),
        ),
    ):
        with ws_client() as c:
            with c.websocket_connect(
                f"/ws/agents/studio?token={token}&idea_id={IDEA_A}&duration=20"
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
    assert "script_ready" in types
    assert "outline_ready" in types
    assert "usage" in types
    assert "persisted" in types
    assert types[-1] == "complete"

    persisted = next(e for e in events if e["type"] == "persisted")
    assert persisted["session_id"] == SESSION_A
    assert persisted["idea_id"] == IDEA_A
    assert persisted["script_artifact_id"] == SCRIPT_A
    assert persisted["outline_artifact_id"] == OUTLINE_A

    complete = events[-1]
    assert complete["cost_usd"] == pytest.approx(0.025)


# ---------------------------------------------------------------------------
# GET /studio-sessions/by-idea/{idea_id}
# ---------------------------------------------------------------------------


async def test_studio_session_get_returns_nulls_when_no_session(
    client, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt(user_id=USER_A)

    sess_response = MagicMock()
    sess_response.data = []
    sess_builder = MagicMock()
    sess_builder.select.return_value = sess_builder
    sess_builder.eq.return_value = sess_builder
    sess_builder.order.return_value = sess_builder
    sess_builder.limit.return_value = sess_builder
    sess_builder.execute = AsyncMock(return_value=sess_response)

    sb = MagicMock()
    sb.from_.return_value = sess_builder

    with patch(
        "app.routes.studio_sessions.user_client",
        AsyncMock(return_value=sb),
    ):
        res = await client.get(
            f"/studio-sessions/by-idea/{IDEA_A}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body == {
        "session": None,
        "script": None,
        "outline": None,
        "scene": None,
    }


async def test_studio_session_get_returns_latest_artifacts(
    client, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt(user_id=USER_A)

    sess_response = MagicMock()
    sess_response.data = [{"id": SESSION_A, "idea_id": IDEA_A}]
    sess_builder = MagicMock()
    sess_builder.select.return_value = sess_builder
    sess_builder.eq.return_value = sess_builder
    sess_builder.order.return_value = sess_builder
    sess_builder.limit.return_value = sess_builder
    sess_builder.execute = AsyncMock(return_value=sess_response)

    art_response = MagicMock()
    art_response.data = [
        {"id": SCRIPT_A, "type": "script", "version": 2, "content_json": {"sections": []}},
        {"id": OUTLINE_A, "type": "outline", "version": 1, "content_json": {"items": []}},
    ]
    art_builder = MagicMock()
    art_builder.select.return_value = art_builder
    art_builder.eq.return_value = art_builder
    art_builder.in_.return_value = art_builder
    art_builder.order.return_value = art_builder
    art_builder.execute = AsyncMock(return_value=art_response)

    sb = MagicMock()

    def from_(name: str):
        if name == "studio_sessions":
            return sess_builder
        if name == "artifacts":
            return art_builder
        raise AssertionError(f"unexpected table: {name}")

    sb.from_.side_effect = from_

    with patch(
        "app.routes.studio_sessions.user_client",
        AsyncMock(return_value=sb),
    ):
        res = await client.get(
            f"/studio-sessions/by-idea/{IDEA_A}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["session"] is not None
    assert body["script"]["id"] == SCRIPT_A
    assert body["outline"]["id"] == OUTLINE_A
