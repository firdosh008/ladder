"""Tests for ``POST /generate-diagram`` with mocked diagram pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    return TestClient(app)


def test_generate_diagram_requires_auth(client: TestClient) -> None:
    res = client.post("/generate-diagram", json={"script": "hello"})
    assert res.status_code in (401, 422)


def test_generate_diagram_happy_path(client: TestClient, make_jwt) -> None:
    token = make_jwt()

    scene = {
        "canvas_width": 1600,
        "canvas_height": 900,
        "background_color": "#ffffff",
        "elements": [
            {"id": "t1", "type": "text", "x": 50, "y": 50, "width": 120, "height": 40, "text": "A"},
            {"id": "t2", "type": "text", "x": 50, "y": 120, "width": 120, "height": 40, "text": "B"},
        ],
        "notes": None,
        "files": None,
    }

    async def fake_generate(*args: object, **kwargs: object):
        return {"scene": scene, "diagram_png_bytes": None}

    with patch(
        "app.routes.diagram.DiagramService.generate_diagram",
        new=AsyncMock(side_effect=fake_generate),
    ):
        with patch(
            "app.routes.diagram.excalidraw_canvas.ensure_canvas_running",
            new=AsyncMock(),
        ):
            res = client.post(
                "/generate-diagram",
                json={"script": "lesson"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["json"]["elements"][0]["id"] == "t1"
