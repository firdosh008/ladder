"""Pure helpers for MCP diagram ↔ Studio scene translation."""

from __future__ import annotations

from app.services.diagram_service import canvas_elements_to_scene_dict


def test_canvas_elements_to_scene_dict_sizes_canvas() -> None:
    els = [
        {
            "id": "a",
            "type": "rectangle",
            "x": 100,
            "y": 100,
            "width": 200,
            "height": 80,
        },
        {
            "id": "b",
            "type": "rectangle",
            "x": 500,
            "y": 300,
            "width": 120,
            "height": 120,
        },
    ]
    scene = canvas_elements_to_scene_dict(
        els,
        canvas_width=1600,
        canvas_height=900,
        background_color="#ffffff",
    )
    assert scene["background_color"] == "#ffffff"
    assert len(scene["elements"]) == 2
    assert scene["canvas_width"] >= 800
    assert scene["canvas_height"] >= 600
    assert "createdAt" not in scene["elements"][0]
