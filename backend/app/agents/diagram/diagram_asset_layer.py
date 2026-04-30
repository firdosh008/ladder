"""Asset selection + brand-styled SVG icons for diagram SceneSkeleton (post-layout)."""

from __future__ import annotations

import base64
import html
import math
import re
import time
from random import Random

from app.agents.diagram.models import DiagramArchetype, DiagramBrandTheme, PlannerNode
from app.models.db import SceneElementLabel, SceneSkeleton, SceneSkeletonElement

_GAP_MIN = 16.0
_GAP_MAX = 24.0
_ICON_MAIN = (52.0, 56.0)
_ICON_SEC = (44.0, 48.0)
_BADGE_PAD = 6.0
_EDGE_PAD = 12.0


def _norm_hex(h: str, fallback: str) -> str:
    if not h or not isinstance(h, str):
        return fallback
    s = h.strip()
    if not s.startswith("#"):
        s = f"#{s}"
    if re.match(r"^#[0-9A-Fa-f]{6}$", s):
        return s
    return fallback


def _local_density(placements: dict[str, tuple[float, float, float, float]], nid: str) -> int:
    """Count nearby node centers (expanded hull) — high ⇒ crowded."""

    ax, ay, aw, ah = placements[nid]
    cx, cy = ax + aw / 2.0, ay + ah / 2.0
    expand = 45.0
    n = 0
    for oid, (bx, by, bw, bh) in placements.items():
        if oid == nid:
            continue
        ox, oy = bx + bw / 2.0, by + bh / 2.0
        if abs(ox - cx) < (aw + bw) / 2.0 + expand and abs(oy - cy) < (ah + bh) / 2.0 + expand:
            n += 1
    return n


def _node_rect_from_elements(
    elements: list[SceneSkeletonElement],
) -> dict[str, tuple[float, float, float, float]]:
    out: dict[str, tuple[float, float, float, float]] = {}
    for el in elements:
        if el.type != "rectangle":
            continue
        if el.id in {"title-core"} or el.id.startswith("grp-"):
            continue
        out[el.id] = (float(el.x), float(el.y), float(el.width), float(el.height))
    return out


def _asset_query_from_label(label: str) -> str:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", label.lower())
    if words:
        return " ".join(words[:3])
    return "concept"


def _svg_data_url(svg_xml: str) -> str:
    raw = svg_xml.encode("utf-8")
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _svg_icon_paths(key: str) -> str:
    """Minimal 24×24 outline paths (stroke-only designs)."""

    k = key.lower()
    if any(w in k for w in ("server", "cloud", "api", "serverless")):
        return '<rect x="4" y="6" width="16" height="10" rx="1.5" fill="none"/>'
    if any(w in k for w in ("user", "people", "team", "customer")):
        return (
            '<circle cx="12" cy="9" r="3" fill="none"/>'
            '<path d="M6 19c0-3 2.7-5 6-5s6 2 6 5" fill="none"/>'
        )
    if any(w in k for w in ("money", "revenue", "sale", "price")):
        return '<path d="M12 5v14M9 8h4.5a2 2 0 010 4H10a2 2 0 000 4h5" fill="none"/>'
    if any(w in k for w in ("growth", "chart", "metric", "trend", "up")):
        return '<path d="M4 17 L9 11 L13 14 L20 7" fill="none"/><path d="M17 7h3v3" fill="none"/>'
    if any(w in k for w in ("shield", "security", "risk", "safe")):
        return '<path d="M12 3 L19 6v6c0 4-3 7-7 8-4-1-7-4-7-8V6z" fill="none"/>'
    if any(w in k for w in ("link", "chain", "connect", "flow", "arrow")):
        return '<path d="M9 12a3 3 0 010-4l1-1a3 3 0 014 4l-1 1" fill="none"/><path d="M15 12a3 3 0 010 4l-1 1a3 3 0 01-4-4l1-1" fill="none"/>'
    if any(w in k for w in ("idea", "light", "spark", "new")):
        return '<path d="M12 3v3M12 18v1M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M3 12h3M18 12h3M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1M10 14a2 2 0 104 0c0 1-1 2-2 3-1-1-2-2-2-3z" fill="none"/>'
    # default diamond node
    return '<path d="M12 4 L19 12 L12 20 L5 12 Z" fill="none"/>'


def build_brand_svg(
    asset_type: str,
    query: str,
    stroke_hex: str,
    fill_hex: str | None,
) -> str:
    """Single inline SVG, outline-first, optional light fill."""

    stroke = html.escape(_norm_hex(stroke_hex, "#3B82F6"))
    fill_attr = ""
    if fill_hex:
        fh = html.escape(_norm_hex(fill_hex, "#64748B"))
        fill_attr = f' fill="{fh}" fill-opacity="0.12"'
    inner = _svg_icon_paths(query)
    if asset_type == "illustration":
        inner += '<circle cx="12" cy="12" r="10" stroke-width="0.8" fill="none" opacity="0.35"/>'
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'width="24" height="24" stroke="{stroke}" stroke-width="1.4" '
        f'stroke-linecap="round" stroke-linejoin="round"{fill_attr}>{inner}</svg>'
    )


def decide_asset_targets(
    nodes: list[PlannerNode],
    placements: dict[str, tuple[float, float, float, float]],
    archetype: DiagramArchetype,
    *,
    seed: int,
) -> list[tuple[PlannerNode, str, str]]:
    """Return up to 30% of nodes as (node, asset_type, asset_query).

    asset_type is ``icon`` or ``illustration`` (illustration used sparingly).
    Skips ``small`` nodes and locally dense areas.
    """

    if not nodes or not placements:
        return []

    n_total = len(nodes)
    max_assets = max(0, math.ceil(n_total * 0.3))
    if max_assets == 0:
        return []

    dense_threshold = 5 if n_total >= 12 else 4
    dense_nids = {n.id for n in nodes if _local_density(placements, n.id) >= dense_threshold}

    candidates: list[PlannerNode] = []
    for node in nodes:
        if node.type == "small":
            continue
        if node.id not in placements:
            continue
        if node.id in dense_nids:
            continue
        candidates.append(node)

    mains = [n for n in candidates if n.type == "main"]
    secs = [n for n in candidates if n.type == "secondary"]
    mains.sort(key=lambda x: (not x.emphasis, x.id))
    rng = Random(seed + 4242)
    secs_shuffled = secs[:]
    rng.shuffle(secs_shuffled)
    ordered = mains + secs_shuffled

    picked: list[PlannerNode] = []
    for node in ordered:
        if len(picked) >= max_assets:
            break
        picked.append(node)

    out: list[tuple[PlannerNode, str, str]] = []
    for i, node in enumerate(picked):
        q = _asset_query_from_label(node.label)
        # Few illustrations — mostly icons (whiteboard style).
        at = "illustration" if (i % 5 == 0 and node.emphasis) else "icon"
        out.append((node, at, q))
    return out


def _pick_icon_xy(
    rect: tuple[float, float, float, float],
    size: float,
    gap: float,
    canvas_w: int,
    canvas_h: int,
    prefer_top: bool,
) -> tuple[float, float] | None:
    rx, ry, rw, rh = rect
    cx = rx + rw / 2.0
    cy = ry + rh / 2.0
    opts: list[tuple[float, float]] = []
    if prefer_top:
        opts.append((cx - size / 2.0, ry - gap - size))
        opts.append((rx - gap - size, cy - size / 2.0))
    else:
        opts.append((rx - gap - size, cy - size / 2.0))
        opts.append((cx - size / 2.0, ry - gap - size))
    opts.append((rx + rw + gap, cy - size / 2.0))

    for ix, iy in opts:
        if (
            ix >= _EDGE_PAD
            and iy >= _EDGE_PAD
            and ix + size <= float(canvas_w) - _EDGE_PAD
            and iy + size <= float(canvas_h) - _EDGE_PAD
        ):
            return (ix, iy)
    return None


def _emphasis_badge_label(node: PlannerNode) -> str | None:
    if not node.emphasis:
        return None
    w = node.label.strip().split()
    if w:
        tag = w[0][:8]
        return tag[:1].upper() + tag[1:] if tag else "Key"
    return "Key"


def apply_diagram_assets(
    scene: SceneSkeleton,
    nodes: list[PlannerNode],
    theme: DiagramBrandTheme,
    archetype: DiagramArchetype,
    *,
    seed: int,
) -> SceneSkeleton:
    """Inject SVG image elements + optional badges; group with node rect. Layout boxes unchanged."""

    placements = _node_rect_from_elements(list(scene.elements))
    if not placements:
        return scene

    stroke = _norm_hex(theme.primary, "#3B82F6")
    sec = _norm_hex(theme.secondary, "#64748B")

    gap = _GAP_MIN + (seed % 9) * 0.333  # 16–18ish
    prefer_top = archetype in ("process", "timeline", "comparison")

    targets = decide_asset_targets(nodes, placements, archetype, seed=seed)
    if not targets:
        return scene

    node_by_id = {n.id: n for n in nodes}

    icon_plans: list[tuple[PlannerNode, str, str, float, float, float]] = []
    for node, asset_type, query in targets:
        rect = placements.get(node.id)
        if not rect:
            continue
        iw, ih = _ICON_MAIN if node.type == "main" else _ICON_SEC
        size = min(iw, ih)
        pos = _pick_icon_xy(rect, size, gap, scene.canvas_width, scene.canvas_height, prefer_top)
        if pos is None:
            continue
        ix, iy = pos
        icon_plans.append((node, asset_type, query, size, ix, iy))

    grouped_nids: set[str] = {p[0].id for p in icon_plans}
    for n in nodes:
        if n.emphasis and n.id in placements:
            grouped_nids.add(n.id)

    rebuilt: list[SceneSkeletonElement] = []
    for el in scene.elements:
        if el.type == "rectangle" and el.id in grouped_nids:
            rebuilt.append(el.model_copy(update={"groupIds": [f"dg-{el.id}"]}))
        else:
            rebuilt.append(el)

    files: dict[str, dict[str, str | int]] = dict(scene.files or {})
    new_els = rebuilt
    ts_ms = int(time.time() * 1000)
    badged: set[str] = set()

    for node, asset_type, query, size, ix, iy in icon_plans:
        rect = placements[node.id]
        svg = build_brand_svg(asset_type, query, stroke, sec if asset_type == "illustration" else None)
        data_url = _svg_data_url(svg)
        file_id = f"dgf-{node.id}"[:64]
        files[file_id] = {
            "mimeType": "image/svg+xml",
            "id": file_id,
            "dataURL": data_url,
            "created": ts_ms,
        }

        gid = f"dg-{node.id}"
        new_els.append(
            SceneSkeletonElement(
                id=f"dgi-{node.id}"[:64],
                type="image",
                x=ix,
                y=iy,
                width=size,
                height=size,
                fileId=file_id,
                groupIds=[gid],
                strokeColor=stroke,
                roughness=0,
            )
        )

        badge = _emphasis_badge_label(node)
        if badge:
            bw = min(72.0, 8.0 * len(badge) + 2 * _BADGE_PAD)
            bh = 22.0
            bx = rect[0] + rect[2] - bw - 4.0
            by = rect[1] - bh * 0.35
            if by < _EDGE_PAD:
                by = rect[1] + 4.0
            new_els.append(
                SceneSkeletonElement(
                    id=f"dgb-{node.id}"[:64],
                    type="rectangle",
                    x=bx,
                    y=by,
                    width=bw,
                    height=bh,
                    label=SceneElementLabel(text=badge[:20]),
                    strokeColor=stroke,
                    backgroundColor=f"{sec}33",
                    fillStyle="solid",
                    strokeWidth=1.2,
                    roughness=0,
                    fontFamily=theme.font,
                    groupIds=[gid],
                )
            )
            badged.add(node.id)

    for node in nodes:
        if not node.emphasis or node.id in badged or node.id not in placements:
            continue
        if node.id not in grouped_nids:
            continue
        badge = _emphasis_badge_label(node)
        if not badge:
            continue
        rect = placements[node.id]
        gid = f"dg-{node.id}"
        bw = min(72.0, 8.0 * len(badge) + 2 * _BADGE_PAD)
        bh = 22.0
        bx = rect[0] + rect[2] - bw - 4.0
        by = rect[1] - bh * 0.35
        if by < _EDGE_PAD:
            by = rect[1] + 4.0
        new_els.append(
            SceneSkeletonElement(
                id=f"dgb-{node.id}"[:64],
                type="rectangle",
                x=bx,
                y=by,
                width=bw,
                height=bh,
                label=SceneElementLabel(text=badge[:20]),
                strokeColor=stroke,
                backgroundColor=f"{sec}33",
                fillStyle="solid",
                strokeWidth=1.2,
                roughness=0,
                fontFamily=theme.font,
                groupIds=[gid],
            )
        )
        badged.add(node.id)

    max_r = max(e.x + e.width for e in new_els)
    max_b = max(e.y + e.height for e in new_els)
    cw = int(max(scene.canvas_width, max_r + 80))
    ch = int(max(scene.canvas_height, max_b + 100))

    return SceneSkeleton(
        canvas_width=cw,
        canvas_height=ch,
        background_color=scene.background_color,
        elements=new_els,
        notes=scene.notes,
        files=files or None,
    )
