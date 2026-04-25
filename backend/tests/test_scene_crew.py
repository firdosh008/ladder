"""Tests for the Scene crew + /ws/agents/scene route + /scene/share endpoint.

Coverage:
  - Pydantic validation for SceneSkeletonElement / SceneLayout / SceneSkeleton.
  - WS auth + session_id requirement.
  - End-to-end stream → persisted scene artifact via mocked run_scene_build
    and supabase tables.
  - POST /studio-sessions/{id}/scene/share uploads to Storage and returns the
    public URL.
"""

from __future__ import annotations

from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.db import (
    SceneFrame,
    SceneLayout,
    SceneSkeleton,
    SceneSkeletonElement,
)


USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
IDEA_A = "11111111-1111-1111-1111-111111111111"
SESSION_A = "22222222-2222-2222-2222-222222222222"
SCRIPT_A = "33333333-3333-3333-3333-333333333333"
OUTLINE_A = "44444444-4444-4444-4444-444444444444"
SCENE_A = "55555555-5555-5555-5555-555555555555"


# ---------------------------------------------------------------------------
# Pydantic
# ---------------------------------------------------------------------------


def test_scene_skeleton_element_requires_known_type() -> None:
    with pytest.raises(ValueError):
        SceneSkeletonElement(id="x", type="hexagon", x=0, y=0, width=10, height=10)  # type: ignore[arg-type]
    SceneSkeletonElement(id="x", type="rectangle", x=0, y=0, width=10, height=10)


def test_scene_skeleton_element_clamps_dimensions() -> None:
    with pytest.raises(ValueError):
        SceneSkeletonElement(id="x", type="rectangle", x=0, y=0, width=-1, height=10)
    with pytest.raises(ValueError):
        SceneSkeletonElement(id="x", type="rectangle", x=0, y=0, width=10, height=99999)


def test_scene_layout_rejects_undersized_canvas() -> None:
    f = SceneFrame(
        number=1, label="x", kind="title", x=0, y=0,
        width=100, height=100, description="ok",
    )
    with pytest.raises(ValueError):
        SceneLayout(canvas_width=400, canvas_height=600, frames=[f, f])
    SceneLayout(canvas_width=1600, canvas_height=900, frames=[f, f])


def test_scene_skeleton_requires_at_least_two_elements() -> None:
    el = SceneSkeletonElement(
        id="r1", type="rectangle", x=0, y=0, width=200, height=80
    )
    with pytest.raises(ValueError):
        SceneSkeleton(canvas_width=1600, canvas_height=900, elements=[el])
    SceneSkeleton(canvas_width=1600, canvas_height=900, elements=[el, el])


# ---------------------------------------------------------------------------
# WS route — mocked run_scene_build + supabase
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


def _fake_scene_run(scene_payload: dict):
    async def _gen(_user_id: Any, _profile: Any, _idea: Any, _outline: Any, _script: Any):
        yield {"type": "agent_start", "agent": "layout_planner"}
        yield {"type": "text_delta", "agent": "layout_planner", "content": "planning…"}
        yield {"type": "task_complete", "agent": "layout_planner", "preview": "ok"}
        yield {"type": "agent_start", "agent": "element_designer"}
        yield {"type": "text_delta", "agent": "element_designer", "content": "drawing…"}
        yield {"type": "task_complete", "agent": "element_designer", "preview": "ok"}
        yield {"type": "scene_ready", "scene": scene_payload}
        yield {
            "type": "usage",
            "token_usage": {"input": 1200, "output": 2200, "cost_usd": 0.04},
        }

    return _gen


def _supabase_scene_mock() -> AsyncMock:
    """Multi-table mock for the scene WS path.

    Tables touched (in order):
      studio_sessions   → select(...) for session lookup
      artifacts         → select(...) for latest script
      artifacts         → select(...) for latest outline
      ideas             → select(...) for _load_idea
      user_profiles     → select(...) for _load_profile
      artifacts         → select(...) for next_version
      artifacts         → insert(...)
    """
    sb = MagicMock()

    # studio_sessions SELECT (single)
    sess_resp = MagicMock()
    sess_resp.data = {
        "id": SESSION_A,
        "user_id": USER_A,
        "idea_id": IDEA_A,
        "target_duration_min": 20,
        "status": "active",
    }
    sess_builder = MagicMock()
    sess_builder.select.return_value = sess_builder
    sess_builder.eq.return_value = sess_builder
    sess_builder.maybe_single.return_value = sess_builder
    sess_builder.execute = AsyncMock(return_value=sess_resp)

    # artifacts SELECT — used for: latest script, latest outline, next_version
    script_row = {
        "id": SCRIPT_A,
        "type": "script",
        "version": 1,
        "content_json": {
            "sections": [
                {
                    "heading": "Open with the claim",
                    "duration_min": 4,
                    "talking_points": ["a", "b", "c"],
                    "transition": None,
                },
                {
                    "heading": "Wrap",
                    "duration_min": 3,
                    "talking_points": ["d", "e"],
                    "transition": None,
                },
            ]
        },
    }
    outline_row = {
        "id": OUTLINE_A,
        "type": "outline",
        "version": 1,
        "content_json": {
            "items": [
                {"number": 1, "label": "Open", "beat": "Hook the viewer."},
                {"number": 2, "label": "Body", "beat": "Walk the steps."},
                {"number": 3, "label": "Wrap", "beat": "Land the takeaway."},
            ]
        },
    }
    art_responses = [
        MagicMock(data=[script_row]),
        MagicMock(data=[outline_row]),
        MagicMock(data=[]),  # next_version for excalidraw → empty → 1
    ]
    art_builder = MagicMock()
    art_builder.select.return_value = art_builder
    art_builder.eq.return_value = art_builder
    art_builder.order.return_value = art_builder
    art_builder.limit.return_value = art_builder
    art_builder.execute = AsyncMock(side_effect=art_responses)

    art_insert_responses = [MagicMock(data=[{"id": SCENE_A, "type": "excalidraw"}])]
    art_insert_chain = MagicMock()
    art_insert_chain.execute = AsyncMock(side_effect=art_insert_responses)

    artifacts_table = MagicMock()
    artifacts_table.select.return_value = art_builder
    artifacts_table.insert.return_value = art_insert_chain

    # ideas SELECT
    idea_resp = MagicMock()
    idea_resp.data = {
        "id": IDEA_A,
        "title": "Ship faster",
        "body": None,
        "rationale": "founder voice",
        "idea_type": "framework",
        "opportunity_score": 80,
        "source_type": "manual",
        "source_content": None,
    }
    idea_builder = MagicMock()
    idea_builder.select.return_value = idea_builder
    idea_builder.eq.return_value = idea_builder
    idea_builder.maybe_single.return_value = idea_builder
    idea_builder.execute = AsyncMock(return_value=idea_resp)

    # user_profiles SELECT
    profile_resp = MagicMock()
    profile_resp.data = {
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
    profile_builder.execute = AsyncMock(return_value=profile_resp)

    def from_(name: str):
        if name == "studio_sessions":
            return sess_builder
        if name == "artifacts":
            return artifacts_table
        if name == "ideas":
            return idea_builder
        if name == "user_profiles":
            return profile_builder
        raise AssertionError(f"unexpected table: {name}")

    sb.from_.side_effect = from_
    return AsyncMock(return_value=sb)


async def test_scene_ws_rejects_missing_token(
    ws_client: Callable[[], TestClient],
) -> None:
    with ws_client() as c:
        with c.websocket_connect(
            f"/ws/agents/scene?session_id={SESSION_A}"
        ) as ws:
            code, _ = _drain_until_close(ws)
    assert code == 4401


async def test_scene_ws_rejects_missing_session_id(
    ws_client: Callable[[], TestClient],
    make_jwt: Callable[..., str],
) -> None:
    token = make_jwt(user_id=USER_A)
    with ws_client() as c:
        with c.websocket_connect(f"/ws/agents/scene?token={token}") as ws:
            code, _ = _drain_until_close(ws)
    assert code == 4400


async def test_scene_ws_streams_persists_and_emits_persisted(
    ws_client: Callable[[], TestClient],
    make_jwt: Callable[..., str],
) -> None:
    token = make_jwt(user_id=USER_A)

    scene_payload = {
        "canvas_width": 1600,
        "canvas_height": 1200,
        "background_color": "#1A1A2E",
        "elements": [
            {
                "id": "title-card",
                "type": "rectangle",
                "x": 600,
                "y": 80,
                "width": 400,
                "height": 100,
                "label": {"text": "Open"},
                "backgroundColor": "#E8442A",
                "fillStyle": "solid",
                "strokeColor": "#F5F5F5",
                "strokeWidth": 2,
                "roughness": 1,
            },
            {
                "id": "f2-step",
                "type": "rectangle",
                "x": 600,
                "y": 280,
                "width": 400,
                "height": 100,
                "label": {"text": "Body"},
                "strokeColor": "#F5F5F5",
                "strokeWidth": 2,
                "roughness": 1,
            },
            {
                "id": "arrow-1",
                "type": "arrow",
                "x": 800,
                "y": 180,
                "width": 0,
                "height": 100,
                "start": {"id": "title-card"},
                "end": {"id": "f2-step"},
            },
        ],
        "notes": "clean — pass-through",
    }

    sb_mock = _supabase_scene_mock()

    with (
        patch("app.routes.agents.user_client", sb_mock),
        patch(
            "app.routes.agents.run_scene_build",
            _fake_scene_run(scene_payload),
        ),
    ):
        with ws_client() as c:
            with c.websocket_connect(
                f"/ws/agents/scene?token={token}&session_id={SESSION_A}"
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
    assert "scene_ready" in types
    assert "usage" in types
    assert "persisted" in types
    assert types[-1] == "complete"

    persisted = next(e for e in events if e["type"] == "persisted")
    assert persisted["session_id"] == SESSION_A
    assert persisted["scene_artifact_id"] == SCENE_A

    scene_ready = next(e for e in events if e["type"] == "scene_ready")
    assert scene_ready["scene"]["canvas_width"] == 1600
    assert len(scene_ready["scene"]["elements"]) == 3

    complete = events[-1]
    assert complete["cost_usd"] == pytest.approx(0.04)


# ---------------------------------------------------------------------------
# POST /studio-sessions/{id}/scene/share
# ---------------------------------------------------------------------------


async def test_scene_share_uploads_envelope_and_returns_public_url(
    client, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt(user_id=USER_A)

    # user_client: session lookup + (later) update mirror.
    sess_resp = MagicMock(data={"id": SESSION_A, "user_id": USER_A})
    sess_builder = MagicMock()
    sess_builder.select.return_value = sess_builder
    sess_builder.eq.return_value = sess_builder
    sess_builder.maybe_single.return_value = sess_builder
    sess_builder.execute = AsyncMock(return_value=sess_resp)

    update_chain = MagicMock()
    update_chain.eq.return_value = update_chain
    update_chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    sess_table = MagicMock()
    sess_table.select.return_value = sess_builder
    sess_table.update.return_value = update_chain

    sb_user = MagicMock()
    sb_user.from_.return_value = sess_table
    user_client_mock = AsyncMock(return_value=sb_user)

    # service_client: storage upload + public URL.
    storage_bucket = MagicMock()
    storage_bucket.upload = AsyncMock(return_value=None)
    storage_bucket.get_public_url = MagicMock(
        return_value="https://test.supabase.co/storage/v1/object/public/excalidraw_scenes/some/path.excalidraw"
    )
    sb_admin = MagicMock()
    sb_admin.storage.from_ = MagicMock(return_value=storage_bucket)
    service_client_mock = AsyncMock(return_value=sb_admin)

    envelope = {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": [
            {
                "id": "x",
                "type": "rectangle",
                "x": 0,
                "y": 0,
                "width": 100,
                "height": 100,
            }
        ],
        "appState": {"viewBackgroundColor": "#1A1A2E"},
        "files": {},
    }

    with (
        patch("app.routes.studio_sessions.user_client", user_client_mock),
        patch("app.routes.studio_sessions.service_client", service_client_mock),
    ):
        res = await client.post(
            f"/studio-sessions/{SESSION_A}/scene/share",
            headers={"Authorization": f"Bearer {token}"},
            json={"envelope": envelope},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["public_url"].endswith(".excalidraw")
    assert body["storage_path"].startswith(f"{USER_A}/{SESSION_A}/")

    # Upload was called with bytes that decode to the envelope.
    storage_bucket.upload.assert_awaited_once()
    upload_kwargs = storage_bucket.upload.await_args.kwargs
    assert upload_kwargs["path"].startswith(f"{USER_A}/{SESSION_A}/")
    assert isinstance(upload_kwargs["file"], (bytes, bytearray))


async def test_scene_share_rejects_envelopes_that_arent_excalidraw_files(
    client, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt(user_id=USER_A)

    sess_resp = MagicMock(data={"id": SESSION_A, "user_id": USER_A})
    sess_builder = MagicMock()
    sess_builder.select.return_value = sess_builder
    sess_builder.eq.return_value = sess_builder
    sess_builder.maybe_single.return_value = sess_builder
    sess_builder.execute = AsyncMock(return_value=sess_resp)
    sb_user = MagicMock()
    sb_user.from_.return_value = sess_builder
    user_client_mock = AsyncMock(return_value=sb_user)

    with patch("app.routes.studio_sessions.user_client", user_client_mock):
        res = await client.post(
            f"/studio-sessions/{SESSION_A}/scene/share",
            headers={"Authorization": f"Bearer {token}"},
            json={"envelope": {"foo": "bar"}},
        )
    assert res.status_code == 400


async def test_scene_share_404s_when_session_missing(
    client, make_jwt: Callable[..., str]
) -> None:
    token = make_jwt(user_id=USER_A)

    sess_resp = MagicMock(data=None)
    sess_builder = MagicMock()
    sess_builder.select.return_value = sess_builder
    sess_builder.eq.return_value = sess_builder
    sess_builder.maybe_single.return_value = sess_builder
    sess_builder.execute = AsyncMock(return_value=sess_resp)
    sb_user = MagicMock()
    sb_user.from_.return_value = sess_builder
    user_client_mock = AsyncMock(return_value=sb_user)

    with patch("app.routes.studio_sessions.user_client", user_client_mock):
        res = await client.post(
            f"/studio-sessions/{SESSION_A}/scene/share",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "envelope": {
                    "type": "excalidraw",
                    "version": 2,
                    "source": "https://excalidraw.com",
                    "elements": [],
                    "appState": {},
                    "files": {},
                }
            },
        )
    assert res.status_code == 404
