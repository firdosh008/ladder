"""Graph + deterministic layout → SceneSkeleton (ExcalidrawElementSkeleton rows)."""

from __future__ import annotations

import re

from app.agents.diagram.layout_engine import _filter_edges
from app.agents.diagram.models import (
    DiagramBrandTheme,
    LayoutBox,
    PlannerEdge,
    PlannerGroup,
    PlannerNode,
    StrategistOutput,
)
from app.models.db import (
    SceneElementBinding,
    SceneElementLabel,
    SceneSkeleton,
    SceneSkeletonElement,
)


def _norm_hex(raw: str | None, fallback: str) -> str:
    if not raw or not isinstance(raw, str):
        return fallback
    s = raw.strip()
    if not s:
        return fallback
    if not s.startswith("#"):
        s = f"#{s}"
    if re.match(r"^#[0-9A-Fa-f]{6}$", s):
        return s
    if re.match(r"^#[0-9A-Fa-f]{8}$", s):
        return s[:7]
    return fallback


def _theme_palette(t: DiagramBrandTheme) -> set[str]:
    return {
        _norm_hex(t.primary, t.primary),
        _norm_hex(t.secondary, t.secondary),
        _norm_hex(t.accent, t.accent),
        _norm_hex(t.text, t.text),
        _norm_hex(t.background, t.background),
    }


def _snap_color(c: str | None, t: DiagramBrandTheme, *, prefer: str) -> str:
    """Force ``c`` onto the brand palette."""

    pal = list(_theme_palette(t))
    candidate = _norm_hex(c, prefer)
    if candidate in pal:
        return candidate
    pref = _norm_hex(prefer, t.primary)
    if pref in pal:
        return pref
    return pal[0]


def _with_alpha(hex6: str, alpha: str) -> str:
    base = _norm_hex(hex6, "#000000")
    if len(base) == 9:
        return base
    return f"{base}{alpha}"


def layout_group_backgrounds(
    groups: list[PlannerGroup],
    placements: dict[str, LayoutBox],
    theme: DiagramBrandTheme,
    padding: float = 36.0,
) -> list[SceneSkeletonElement]:
    secondary = _snap_color(theme.secondary, theme, prefer=theme.secondary)
    rects: list[SceneSkeletonElement] = []
    for g in groups:
        boxes = [placements[n] for n in g.node_ids if n in placements]
        if len(boxes) < 2:
            continue
        min_x = min(b.x for b in boxes) - padding
        min_y = min(b.y for b in boxes) - padding
        max_x = max(b.x + b.width for b in boxes) + padding
        max_y = max(b.y + b.height for b in boxes) + padding
        rects.append(
            SceneSkeletonElement(
                id=f"grp-{g.id}",
                type="rectangle",
                x=min_x,
                y=min_y,
                width=max_x - min_x,
                height=max_y - min_y,
                label=SceneElementLabel(text=g.label.strip()[:160])
                if (g.label and g.label.strip())
                else None,
                strokeColor=_snap_color(None, theme, prefer=secondary),
                backgroundColor=_with_alpha(secondary, "22"),
                fillStyle="solid",
                strokeWidth=1,
                roughness=0,
                fontFamily=theme.font,
            )
        )
    return rects


def _node_colors(node: PlannerNode, theme: DiagramBrandTheme) -> tuple[str, str | None, float]:
    """stroke, background, stroke_width."""

    primary = _snap_color(theme.primary, theme, prefer=theme.primary)
    secondary = _snap_color(theme.secondary, theme, prefer=theme.secondary)
    accent = _snap_color(theme.accent, theme, prefer=theme.accent)
    if node.emphasis:
        return accent, _with_alpha(accent, "33"), 3.2
    if node.type == "main":
        return primary, _with_alpha(primary, "22"), 2.5
    if node.type == "small":
        return secondary, _with_alpha(secondary, "18"), 1.8
    return secondary, _with_alpha(secondary, "14"), 2.0


def _title_and_body_from_planner_label(raw: str) -> tuple[str, str | None]:
    """Short title for bound ``label``; long / following clauses as optional body text."""

    s = (raw or "").strip()
    if not s:
        return "—", None
    max_title = 52
    if "\n" in s:
        first, rest = s.split("\n", 1)
        title = (first.strip()[:max_title] or "—")
        body = rest.strip()
        return (title, body[:3800] if body else None)
    if len(s) <= max_title:
        return s, None
    window = min(120, len(s))
    chunk = s[:window]
    dot = chunk.rfind(". ")
    if dot >= 18:
        title = s[: dot + 1].strip()[:max_title]
        body = s[dot + 1 :].strip()
        return (title or s[:max_title], body[:3800] if body else None)
    sp = s[:max_title].rfind(" ")
    if sp >= 10:
        title = s[:sp].strip()[:max_title]
        body = s[sp:].strip()
        return (title, body[:3800] if body else None)
    title = s[: max_title - 1] + "…"
    body = s[max_title - 1 :].strip()
    return (title, body[:3800] if body else None)


_TITLE_BAND = 40.0
_BODY_PAD_X = 12.0
_BODY_PAD_BOTTOM = 12.0


def build_scene_skeleton(
    strategist: StrategistOutput,
    nodes: list[PlannerNode],
    edges: list[PlannerEdge],
    groups: list[PlannerGroup],
    placements: dict[str, LayoutBox],
    canvas_width: int,
    canvas_height: int,
    theme: DiagramBrandTheme,
) -> SceneSkeleton:
    """Assemble rectangles + arrows (+ optional group frames) using brand tokens only."""

    text_c = _snap_color(theme.text, theme, prefer=theme.text)
    bg_scene = _snap_color(theme.background, theme, prefer=theme.background)
    filt_edges = _filter_edges(nodes, edges)

    elements: list[SceneSkeletonElement] = []

    elements.append(
        SceneSkeletonElement(
            id="title-core",
            type="text",
            x=72.0,
            y=32.0,
            width=min(980.0, float(canvas_width) - 144),
            height=52.0,
            text=strategist.core_message,
            strokeColor=text_c,
            strokeWidth=2,
            roughness=1,
            fontSize=22,
            fontFamily=theme.font,
        )
    )

    group_back = layout_group_backgrounds(groups, placements, theme)
    elements.extend(group_back)

    nid_to_node = {n.id: n for n in nodes}
    for nid, box in placements.items():
        pn = nid_to_node.get(nid)
        if not pn:
            continue
        stroke, fill, sw = _node_colors(pn, theme)
        w = max(box.width, 44.0)
        h = max(box.height, 44.0)
        title, body = _title_and_body_from_planner_label(pn.label)
        elements.append(
            SceneSkeletonElement(
                id=nid,
                type="rectangle",
                x=box.x,
                y=box.y,
                width=w,
                height=h,
                label=SceneElementLabel(text=title),
                strokeColor=stroke,
                strokeWidth=sw,
                roughness=1,
                backgroundColor=fill,
                fillStyle="solid" if fill else None,
                fontFamily=theme.font,
            )
        )
        if body:
            elements.append(
                SceneSkeletonElement(
                    id=f"{nid}-body",
                    type="text",
                    x=box.x + _BODY_PAD_X,
                    y=box.y + _TITLE_BAND,
                    width=max(44.0, w - 2 * _BODY_PAD_X),
                    height=max(48.0, h - _TITLE_BAND - _BODY_PAD_BOTTOM),
                    text=body,
                    strokeColor=text_c,
                    strokeWidth=1,
                    roughness=0,
                    fontSize=13,
                    fontFamily=theme.font,
                )
            )
    seen_arrow: set[tuple[str, str]] = set()
    for ie, ed in enumerate(filt_edges):
        key = (ed.from_id, ed.to)
        if key in seen_arrow:
            continue
        seen_arrow.add(key)
        a, b = placements[ed.from_id], placements[ed.to]
        sx = a.x + a.width * 0.5
        sy = a.y + a.height * 0.5
        ex = b.x + b.width * 0.5
        ey = b.y + b.height * 0.5
        aid = f"arr-{ed.from_id}-{ed.to}-{ie}"
        elements.append(
            SceneSkeletonElement(
                id=aid,
                type="arrow",
                x=sx,
                y=sy,
                width=max(8.0, abs(ex - sx)),
                height=max(8.0, abs(ey - sy)),
                start=SceneElementBinding(id=ed.from_id),
                end=SceneElementBinding(id=ed.to),
                strokeColor=_snap_color(None, theme, prefer=theme.primary),
                strokeWidth=2,
                roughness=1,
                fontFamily=theme.font,
            )
        )
        if ed.label:
            mx = (sx + ex) * 0.5
            my = (sy + ey) * 0.5
            elements.append(
                SceneSkeletonElement(
                    id=f"{aid}-lbl",
                    type="text",
                    x=mx,
                    y=my,
                    width=160.0,
                    height=36.0,
                    text=ed.label[:120],
                    strokeColor=text_c,
                    fontSize=14,
                    roughness=0,
                    fontFamily=theme.font,
                )
            )

    short_aha = (
        strategist.aha_moment[:180] + "…"
        if len(strategist.aha_moment) > 180
        else strategist.aha_moment
    )
    elements.append(
        SceneSkeletonElement(
            id="note-aha",
            type="text",
            x=72.0,
            y=float(canvas_height) - 120.0,
            width=min(900.0, float(canvas_width) - 144),
            height=64.0,
            text=f"Insight: {short_aha}",
            strokeColor=_snap_color(theme.secondary, theme, prefer=text_c),
            fontSize=13,
            roughness=1,
            fontFamily=theme.font,
        )
    )

    return SceneSkeleton(
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        background_color=bg_scene,
        elements=elements,
        notes=strategist.aha_moment[:3990],
    )
