"""Deterministic fixes after LLM scene generation — contrast, arrows, canvas."""

from __future__ import annotations

import logging
import re
import textwrap
from typing import Final

from app.models.db import (
    SceneElementLabel,
    SceneLayout,
    SceneSkeleton,
    SceneSkeletonElement,
)

log = logging.getLogger(__name__)

_DARK_INK: Final[str] = "#1F2937"
_LIGHT_INK: Final[str] = "#FFFFFF"

_SHAPE_TYPES_BINDING: Final[frozenset[str]] = frozenset(
    {"rectangle", "diamond", "ellipse"}
)

_PAINT_ORDER: Final[dict[str, int]] = {
    "rectangle": 0,
    "diamond": 0,
    "ellipse": 0,
    "image": 0,
    "arrow": 1,
    "line": 1,
    "text": 2,
}

_TEXT_LINE_HEIGHT_RATIO: Final[float] = 1.25
_MIN_TEXT_WRAP_WIDTH: Final[float] = 120.0
_MIN_CHARS_PER_LINE: Final[int] = 12
_MAX_CHARS_PER_LINE: Final[int] = 56
_DEFAULT_FONT_SIZE: Final[float] = 20.0

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


def enforce_font_family(
    scene: SceneSkeleton, font_family: int | None
) -> SceneSkeleton:
    """Stamp the user-chosen ``fontFamily`` on every text element + bound
    label. The LLM does not always honour the prompt instruction; this
    deterministic pass guarantees the picker selection is what the founder
    sees on the canvas. ``None`` is a no-op (Excalidraw default).

    Geometry, content, colors are untouched — only the typography integer.
    Label dicts inherit a ``fontFamily`` key so the bound caption picks the
    same family when ``convertToExcalidrawElements`` inflates it.
    """
    if font_family is None:
        return scene

    out: list[SceneSkeletonElement] = []
    for el in scene.elements:
        has_text = isinstance(el.text, str) and el.text.strip() != ""
        has_label = el.label is not None and (el.label.text or "").strip() != ""
        if not has_text and not has_label and el.type != "text":
            out.append(el)
            continue

        update: dict = {"fontFamily": font_family}
        if has_label and el.label is not None:
            update["label"] = SceneElementLabel(
                text=el.label.text, fontFamily=font_family
            )
        out.append(el.model_copy(update=update))

    return scene.model_copy(update={"elements": out})


def enforce_brand_dominance(
    scene: SceneSkeleton, brand_color: str | None
) -> SceneSkeleton:
    """Make the brand color the dominant fill on shape elements.

    The LLM only paints title cards + a few accent strokes by default. To
    reflect the user's brand on the board, walk shape elements (rectangles,
    diamonds, ellipses) that have **no fill** and paint them solid brand
    color — keeping every Nth shape (~30%) as wireframe-only so the canvas
    does not become a wall of one swatch. Already-filled shapes (whether the
    LLM picked brand or another color) are left alone.

    Arrows, lines, plain text, and shapes with explicit non-empty fills are
    untouched. Stroke colors fall through to ``enforce_readable_colors``
    which flips bound-label strokes to white on dark fills.
    """
    if not brand_color:
        return scene
    rgb = _parse_hex(brand_color)
    if rgb is None:
        return scene
    # Only treat the brand color as a "dominant fill" if it is dark enough
    # for white labels to read on it. A pale brand swatch becomes an accent
    # stroke instead (handled by the LLM prompt + readable-colors pass).
    if _luma(rgb) >= 185:
        return scene

    out: list[SceneSkeletonElement] = []
    paint_count = 0
    skip_every = 3  # leave roughly every 3rd unfilled shape as wireframe
    fill_idx = 0
    for el in scene.elements:
        if el.type not in ("rectangle", "diamond", "ellipse"):
            out.append(el)
            continue

        bg = (el.backgroundColor or "").strip().lower()
        already_filled = (
            bg not in ("", "transparent", "#ffffff", "#fff", "white")
            and el.fillStyle == "solid"
        )
        if already_filled:
            out.append(el)
            continue

        # Wireframe rotation: keep ~1 in `skip_every` shapes unfilled for rhythm.
        is_wireframe_slot = fill_idx % skip_every == (skip_every - 1)
        fill_idx += 1
        if is_wireframe_slot:
            out.append(el)
            continue

        out.append(
            el.model_copy(
                update={
                    "backgroundColor": brand_color,
                    "fillStyle": "solid",
                    # Stroke: a hint, but enforce_readable_colors will swap
                    # to white if the fill is dark enough (it is — gated by
                    # luma above).
                    "strokeColor": brand_color,
                }
            )
        )
        paint_count += 1

    if paint_count:
        log.info(
            "scene cleanup painted %d shape(s) with brand color %s",
            paint_count, brand_color,
        )
    return scene.model_copy(update={"elements": out})


def _chars_per_line_for_box(width_px: float, font_size: float) -> int:
    """Heuristic Latin char budget per line for Excalidraw-style boxed text."""
    fs = max(10.0, min(72.0, font_size))
    w = max(_MIN_TEXT_WRAP_WIDTH, float(width_px))
    raw = int(w / (fs * 0.52))
    return max(_MIN_CHARS_PER_LINE, min(_MAX_CHARS_PER_LINE, raw))


def _wrap_paragraph(paragraph: str, width_chars: int) -> str:
    p = paragraph.strip()
    if not p:
        return ""
    lines = textwrap.wrap(
        p,
        width=max(_MIN_CHARS_PER_LINE, width_chars),
        break_long_words=True,
        break_on_hyphens=False,
    )
    return "\n".join(lines)


def _wrap_plain_text(text: str, width_chars: int) -> str:
    parts = text.split("\n")
    return "\n".join(_wrap_paragraph(part, width_chars) for part in parts)


def wrap_scene_text_elements(scene: SceneSkeleton) -> SceneSkeleton:
    """Insert newline wraps + taller boxes so long copy fits the declared width.

    Excalidraw respects explicit ``\\n`` and uses ``width`` as the wrap column;
    the LLM often emits a single long line — reflow before rendering.
    """
    out: list[SceneSkeletonElement] = []
    for el in scene.elements:
        fs = float(el.fontSize or _DEFAULT_FONT_SIZE)

        if el.type == "text":
            raw_t = el.text or ""
            if not raw_t.strip():
                out.append(el)
                continue
            wbox = float(el.width) if el.width > 8 else 280.0
            cpl = _chars_per_line_for_box(wbox, fs)
            wrapped = _wrap_plain_text(raw_t, cpl)
            if wrapped == raw_t:
                out.append(el)
                continue
            lines = wrapped.count("\n") + 1
            min_h = lines * fs * _TEXT_LINE_HEIGHT_RATIO + 6.0
            nh = min(8000.0, max(float(el.height), min_h))
            out.append(el.model_copy(update={"text": wrapped, "height": nh}))
            continue

        if el.label is not None and (el.label.text or "").strip():
            lt = el.label.text or ""
            inner_w = max(40.0, float(el.width) - 24.0) if el.width > 0 else 200.0
            cpl = min(44, _chars_per_line_for_box(inner_w, fs))
            wrapped_l = _wrap_plain_text(lt, cpl)
            if wrapped_l != lt:
                out.append(
                    el.model_copy(
                        update={
                            "label": SceneElementLabel(
                                text=wrapped_l,
                                fontFamily=el.label.fontFamily,
                            )
                        }
                    )
                )
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


def sort_elements_paint_order(scene: SceneSkeleton) -> SceneSkeleton:
    """Shapes/images → connectors → text so lettering paints on top."""
    indexed = list(enumerate(scene.elements))

    def tier(tp: str) -> int:
        return _PAINT_ORDER.get(tp, 99)

    indexed.sort(key=lambda it: (tier(it[1].type), it[0]))
    return scene.model_copy(update={"elements": [el for _, el in indexed]})


def sync_canvas_from_layout(scene: SceneSkeleton, layout: SceneLayout) -> SceneSkeleton:
    """Planner owns canonical whiteboard chrome — avoids drift vs designer hallucination."""
    return scene.model_copy(
        update={
            "canvas_width": layout.canvas_width,
            "canvas_height": layout.canvas_height,
            "background_color": layout.background_color,
        }
    )
