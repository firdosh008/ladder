"""Smoke tests for POST /generate-diagram (Claude + MCP canvas)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

os.environ.setdefault("EXCALIDRAW_CANVAS_AUTOSTART", "false")

from httpx import ASGITransport, AsyncClient


@pytest.fixture()
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_generate_diagram_returns_scene_json() -> None:
    from app.main import app
    from app.middleware.auth import current_user

    stub_user = (UUID("00000000-0000-4000-8000-000000000002"), "test-jwt")

    async def fake_user():
        return stub_user

    app.dependency_overrides[current_user] = fake_user

    mock_result = {
        "scene": {
            "canvas_width": 900,
            "canvas_height": 600,
            "background_color": "#FCFCFD",
            "elements": [
                {"id": "a1", "type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 40}
            ],
            "files": {},
        },
        "finalized_tool": True,
        "diagram_png_bytes": None,
        "tokens_est": 12,
        "websocket_ok": False,
    }

    with (
        patch(
            "app.routes.diagram.excalidraw_canvas.ensure_canvas_running",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.diagram_service.DiagramService.generate_diagram",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post(
                "/generate-diagram",
                json={"script": "hello video"},
                headers={"Authorization": "Bearer x"},
            )

    app.dependency_overrides.clear()

    assert res.status_code == 200
    data = res.json()
    assert data["artifact_id"] is None
    assert data["json"]["elements"][0]["id"] == "a1"
