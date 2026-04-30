"""Deterministic fixes after LLM scene generation — contrast, arrows, canvas."""

from __future__ import annotations

import logging
import re
from typing import Final

from app.models.db import SceneLayout, SceneSkeleton, SceneSkeletonElement

log = logging.getLogger(__name__)

_DARK_INK: Final[str] = "#1F2937"
_LIGHT_INK: Final[str] = "#FFFFFF"

_SHAPE_TYPES_BINDING: Final[frozenset[str]] = frozenset(
    {"rectangle", "diamond", "ellipse"}
)

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def _parse_hex(color: str | None) -> tuple[int, int, int] | None:
    if not color or not isinstance(color, str):
        return None
    m = _HEX_RE.match(color.strip())
    if not m:
        return None
    v = m.group(1)
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def _luma(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def is_light_canvas(background_color: str | None) -> bool:
    rgb = _parse_hex(background_color or "")
    if rgb is None:
        return True
    return _luma(rgb) > 140


def _is_near_white_stroke(color: str | None) -> bool:
    """Ink that disappears on a white canvas."""
    if color is None:
        return True
    s = color.strip().lower()
    if s in {"", "white", "#fff", "#ffffff"}:
        return True
    rgb = _parse_hex(s)
    if rgb is None:
        return False
    # Very light greys / off-whites used as “subtle” strokes
    return _luma(rgb) >= 235


def _solid_fill_dark_enough_for_white_ink(el: SceneSkeletonElement) -> bool:
    """Colored title cards etc.: captions read better with light ink."""
    if el.fillStyle != "solid":
        return False
    rgb = _parse_hex(el.backgroundColor or "")
    if rgb is None:
        return False
    if _is_near_white_stroke(el.backgroundColor):
        return False
    return _luma(rgb) < 185


def enforce_readable_colors(scene: SceneSkeleton) -> SceneSkeleton:
    """Force WCAG-ish contrast on light canvases (fixes white-on-white text)."""
    if not is_light_canvas(scene.background_color):
        return scene

    out: list[SceneSkeletonElement] = []
    for el in scene.elements:
        if el.type == "text":
            if el.strokeColor is None or _is_near_white_stroke(el.strokeColor):
                out.append(el.model_copy(update={"strokeColor": _DARK_INK}))
            else:
                out.append(el)
            continue

        if el.type in ("arrow", "line"):
            if el.strokeColor is None or _is_near_white_stroke(el.strokeColor):
                out.append(el.model_copy(update={"strokeColor": _DARK_INK}))
            else:
                out.append(el)
            continue

        if el.type in ("rectangle", "diamond", "ellipse"):
            if _solid_fill_dark_enough_for_white_ink(el):
                # Bound labels inherit strokeColor in Excalidraw — white reads on brand fills.
                out.append(el.model_copy(update={"strokeColor": _LIGHT_INK}))
            elif el.strokeColor is None or _is_near_white_stroke(el.strokeColor):
                out.append(el.model_copy(update={"strokeColor": _DARK_INK}))
            else:
                out.append(el)
            continue

        out.append(el)

    return scene.model_copy(update={"elements": out})


def repair_arrow_bindings(scene: SceneSkeleton) -> SceneSkeleton:
    """Drop arrows that reference missing ids or non-shape endpoints (common glitch)."""
    by_id = {e.id: e for e in scene.elements}
    kept: list[SceneSkeletonElement] = []
    dropped = 0

    for el in scene.elements:
        if el.type != "arrow":
            kept.append(el)
            continue

        sid = el.start.id if el.start else ""
        eid = el.end.id if el.end else ""
        start_el = by_id.get(sid)
        end_el = by_id.get(eid)

        ok = (
            start_el is not None
            and end_el is not None
            and start_el.type in _SHAPE_TYPES_BINDING
            and end_el.type in _SHAPE_TYPES_BINDING
            and sid != eid
        )
        if ok:
            kept.append(el)
        else:
            dropped += 1

    if dropped:
        log.warning(
            "scene cleanup dropped %d arrow(s) with invalid bindings "
            "(missing id or start/end not rectangle|diamond|ellipse)",
            dropped,
        )

    return scene.model_copy(update={"elements": kept})


def sync_canvas_from_layout(scene: SceneSkeleton, layout: SceneLayout) -> SceneSkeleton:
    """Planner owns canonical whiteboard chrome — avoids drift vs designer hallucination."""
    return scene.model_copy(
        update={
            "canvas_width": layout.canvas_width,
            "canvas_height": layout.canvas_height,
            "background_color": layout.background_color,
        }
    )
