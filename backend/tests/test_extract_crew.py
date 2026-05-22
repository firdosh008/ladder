"""Tests for the content_extract crew + /ws/agents/extract route.

Coverage:
  - Pydantic validation for ContentAnalysis / ExtractedVideo.
  - WS auth + 1st-message contract (source_content required).
  - End-to-end stream → ideas insert + studio_session insert + artifacts.
"""

from __future__ import annotations

import json
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.db import ContentAnalysis, ExtractedVideo, Outline, Script


USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
NEW_IDEA = "55555555-5555-5555-5555-555555555555"
SESSION_A = "66666666-6666-6666-6666-666666666666"
SCRIPT_A = "77777777-7777-7777-7777-777777777777"
OUTLINE_A = "88888888-8888-8888-8888-888888888888"


# ---------------------------------------------------------------------------
# Pydantic
# ---------------------------------------------------------------------------


def test_content_analysis_validates_duration_bounds() -> None:
    base = {
        "title": "x",
        "rationale": "y",
        "idea_type": "framework",
        "key_beats": ["a", "b", "c"],
    }
    with pytest.raises(ValueError):
        ContentAnalysis(**base, derived_duration_min=2)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ContentAnalysis(**base, derived_duration_min=31)  # type: ignore[arg-type]
    ContentAnalysis(**base, derived_duration_min=10)  # type: ignore[arg-type]


def test_extracted_video_full_shape() -> None:
    payload = {
        "title": "Ship faster",
        "rationale": "actionable framework",
        "idea_type": "framework",
        "derived_duration_min": 12,
        "script": {
            "sections": [
                {
                    "heading": "Open",
                    "duration_min": 3,
                    "talking_points": ["a", "b"],
                    "transition": "next",
                },
                {
                    "heading": "Body",
                    "duration_min": 6,
                    "talking_points": ["c", "d"],
                    "transition": None,
                },
            ]
        },
        "outline": {
            "items": [
                {"number": 1, "label": "Open", "beat": "Hook"},
                {"number": 2, "label": "Body", "beat": "Steps"},
                {"number": 3, "label": "Wrap", "beat": "CTA"},
            ]
        },
    }
    ev = ExtractedVideo(**payload)
    assert isinstance(ev.script, Script)
    assert isinstance(ev.outline, Outline)


# ---------------------------------------------------------------------------
# WS route — mocked run_content_extract + supabase
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


def _fake_extract_run(extracted_payload: dict):
    async def _gen(_user_id: Any, _profile: Any, _src: str):
        yield {"type": "agent_start", "agent": "analyzer"}
        yield {"type": "text_delta", "agent": "analyzer", "content": "scanning…"}
        yield {"type": "task_complete", "agent": "analyzer", "preview": "ok"}
        yield {"type": "agent_start", "agent": "extractor"}
        yield {"type": "task_complete", "agent": "extractor", "preview": "drafted"}
        yield {"type": "extract_ready", "extracted": extracted_payload}
        yield {
            "type": "usage",
            "token_usage": {"input": 1500, "output": 2200, "cost_usd": 0.038},
        }

    return _gen


def _supabase_extract_mock() -> AsyncMock:
    """Multi-table mock for the extract WS path.

    Tables used (in order):
      user_profiles    → select(...)
      ideas            → insert(...) → returns NEW_IDEA
      studio_sessions  → select empty + insert(...)
      artifacts        → select(version) ×2 + insert(...) (script + outline)
      studio_sessions  → update(scene_outline)
    """
    sb = MagicMock()

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

    # ideas insert
    ideas_insert_response = MagicMock()
    ideas_insert_response.data = [{"id": NEW_IDEA}]
    ideas_insert_chain = MagicMock()
    ideas_insert_chain.execute = AsyncMock(return_value=ideas_insert_response)
    ideas_table = MagicMock()
    ideas_table.insert.return_value = ideas_insert_chain

    # studio_sessions select empty
    sess_select_response = MagicMock()
    sess_select_response.data = []
    sess_select_builder = MagicMock()
    sess_select_builder.select.return_value = sess_select_builder
    sess_select_builder.eq.return_value = sess_select_builder
    sess_select_builder.order.return_value = sess_select_builder
    sess_select_builder.limit.return_value = sess_select_builder
    sess_select_builder.execute = AsyncMock(return_value=sess_select_response)

    # studio_sessions insert
    sess_insert_response = MagicMock()
    sess_insert_response.data = [{"id": SESSION_A}]
    sess_insert_chain = MagicMock()
    sess_insert_chain.execute = AsyncMock(return_value=sess_insert_response)

    # studio_sessions update (scene_outline mirror)
    sess_update_response = MagicMock()
    sess_update_response.data = []
    sess_update_chain = MagicMock()
    sess_update_chain.eq.return_value = sess_update_chain
    sess_update_chain.execute = AsyncMock(return_value=sess_update_response)

    studio_table = MagicMock()
    studio_table.select.return_value = sess_select_builder
    studio_table.insert.return_value = sess_insert_chain
    studio_table.update.return_value = sess_update_chain

    # artifacts version select empty
    art_version_response = MagicMock()
    art_version_response.data = []
    art_version_builder = MagicMock()
    art_version_builder.select.return_value = art_version_builder
    art_version_builder.eq.return_value = art_version_builder
    art_version_builder.order.return_value = art_version_builder
    art_version_builder.limit.return_value = art_version_builder
    art_version_builder.execute = AsyncMock(return_value=art_version_response)

    # artifacts insert (both rows at once)
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
        if name == "user_profiles":
            return profile_builder
        if name == "ideas":
            return ideas_table
        if name == "studio_sessions":
            return studio_table
        if name == "artifacts":
            return artifacts_table
        raise AssertionError(f"unexpected table: {name}")

    sb.from_.side_effect = from_
    return AsyncMock(return_value=sb)


async def test_extract_ws_rejects_missing_token(
    ws_client: Callable[[], TestClient],
) -> None:
    with ws_client() as c:
        with c.websocket_connect("/ws/agents/extract") as ws:
            code, _ = _drain_until_close(ws)
    assert code == 4401


async def test_extract_ws_rejects_blank_source(
    ws_client: Callable[[], TestClient],
    make_jwt: Callable[..., str],
) -> None:
    token = make_jwt(user_id=USER_A)
    with ws_client() as c:
        with c.websocket_connect(
            f"/ws/agents/extract?token={token}"
        ) as ws:
            ws.send_text(json.dumps({"source_content": ""}))
            code, _ = _drain_until_close(ws)
    assert code == 4400


async def test_extract_ws_streams_persists_idea_session_artifacts(
    ws_client: Callable[[], TestClient],
    make_jwt: Callable[..., str],
) -> None:
    token = make_jwt(user_id=USER_A)

    extracted_payload = {
        "title": "Ship faster",
        "rationale": "actionable framework grounded in source",
        "idea_type": "framework",
        "derived_duration_min": 12,
        "script": {
            "sections": [
                {
                    "heading": "Open with the claim",
                    "duration_min": 3,
                    "talking_points": ["claim", "stakes", "evidence"],
                    "transition": "now the fix",
                },
                {
                    "heading": "The fix",
                    "duration_min": 9,
                    "talking_points": ["step 1", "step 2", "step 3", "anti-pattern"],
                    "transition": None,
                },
            ]
        },
        "outline": {
            "items": [
                {"number": 1, "label": "Sharp open", "beat": "Hook with claim."},
                {"number": 2, "label": "The fix", "beat": "Three steps."},
                {"number": 3, "label": "Wrap", "beat": "Takeaway."},
            ]
        },
    }

    sb_mock = _supabase_extract_mock()

    with (
        patch("app.routes.agents.user_client", sb_mock),
        patch(
            "app.routes.agents.run_content_extract",
            _fake_extract_run(extracted_payload),
        ),
    ):
        with ws_client() as c:
            with c.websocket_connect(
                f"/ws/agents/extract?token={token}"
            ) as ws:
                ws.send_text(
                    json.dumps(
                        {
                            "source_content": "x" * 250,
                            "source_url": "https://x.test/post",
                        }
                    )
                )
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
    assert "extract_ready" in types
    assert "usage" in types
    assert "persisted" in types
    assert types[-1] == "complete"

    persisted = next(e for e in events if e["type"] == "persisted")
    assert persisted["idea_id"] == NEW_IDEA
    assert persisted["session_id"] == SESSION_A
    assert persisted["script_artifact_id"] == SCRIPT_A
    assert persisted["outline_artifact_id"] == OUTLINE_A

    complete = events[-1]
    assert complete["cost_usd"] == pytest.approx(0.038)
