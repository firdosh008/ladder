"""Tests for deterministic label/body stacking in scene skeletons."""

from __future__ import annotations

from app.agents.scene.skeleton_text_layout import repack_rect_body_text_below_labels
from app.models.db import (
    SceneElementLabel,
    SceneFrame,
    SceneLayout,
    SceneSkeleton,
    SceneSkeletonElement,
)


def test_repack_moves_long_centered_text_below_rect_label():
    layout = SceneLayout(
        canvas_width=1200,
        canvas_height=800,
        frames=[
            SceneFrame(
                number=1,
                label="F1",
                kind="flow",
                x=0,
                y=0,
                width=1200,
                height=800,
                description="full canvas frame for geometry tests",
            ),
            SceneFrame(
                number=2,
                label="F2",
                kind="flow",
                x=0,
                y=0,
                width=10,
                height=10,
                description="second frame satisfies min_length",
            ),
        ],
    )
    rect = SceneSkeletonElement(
        id="card1",
        type="rectangle",
        x=120.0,
        y=120.0,
        width=200.0,
        height=160.0,
        label=SceneElementLabel(text="Character Trust"),
    )
    before = SceneSkeletonElement(
        id="body1",
        type="text",
        x=170.0,
        y=160.0,
        width=100.0,
        height=80.0,
        text="Kids aged 4–10 already trust the mascot to solve problems. " * 2,
    )
    scene = SceneSkeleton(
        canvas_width=1200,
        canvas_height=800,
        elements=[
            SceneSkeletonElement(
                id="t",
                type="text",
                x=72.0,
                y=32.0,
                width=400.0,
                height=40.0,
                text="Video title placeholder long enough for test",
            ),
            rect,
            before,
        ],
    )
    out = repack_rect_body_text_below_labels(scene, layout)
    t = next(e for e in out.elements if e.id == "body1")
    assert t.x == rect.x + 12.0
    assert t.y >= rect.y + 36.0
    assert t.width == rect.width - 24.0
    assert t.height >= 48.0
