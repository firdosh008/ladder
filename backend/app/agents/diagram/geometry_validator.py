"""Deterministic geometric checks and repairs on node placement (no LLM)."""

from __future__ import annotations

import math

from app.agents.diagram.models import (
    DiagramArchetype,
    GeometryIssue,
    LayoutBox,
    PlannerEdge,
    PlannerNode,
)
from app.agents.diagram.sizing import estimate_label_fit

MIN_CLEARANCE = 8.0
MIN_NODE_EDGE_SEPARATION = 24.0
_REPAIR_ITERS = 48


def _overlap_area(a: LayoutBox, b: LayoutBox) -> float:
    ix = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
    iy = min(a.y + a.height, b.y + b.height) - max(a.y, b.y)
    if ix <= 0 or iy <= 0:
        return 0.0
    return ix * iy


def _exterior_clearance(a: LayoutBox, b: LayoutBox) -> float:
    dx = max(0.0, max(b.x - (a.x + a.width), a.x - (b.x + b.width)))
    dy = max(0.0, max(b.y - (a.y + a.height), a.y - (b.y + b.height)))
    return math.hypot(dx, dy)


def _center(b: LayoutBox) -> tuple[float, float]:
    return (b.x + b.width / 2.0, b.y + b.height / 2.0)


def validate_geometry(
    placements: dict[str, LayoutBox],
    nodes: list[PlannerNode],
    *,
    canvas_width: int | None = None,
    canvas_height: int | None = None,
    min_gap: float = MIN_NODE_EDGE_SEPARATION,
) -> list[GeometryIssue]:
    """Detect overlaps, tight separation, label overflow, bounds."""

    issues: list[GeometryIssue] = []
    nid_set = list(placements.keys())
    nid_to_label = {n.id: n.label for n in nodes}
    rects = [(nid, placements[nid]) for nid in nid_set]

    for i, (ida, aa) in enumerate(rects):
        for idb, bb in rects[i + 1 :]:
            oa = _overlap_area(aa, bb)
            if oa > 18.0:
                issues.append(
                    GeometryIssue(
                        kind="overlap",
                        severity="high",
                        detail=f"Overlapping hulls (~{oa:.0f}px²) {ida} ∩ {idb}",
                        node_ids=sorted({ida, idb}),
                    )
                )
            else:
                d = _exterior_clearance(aa, bb)
                if min_gap > d > 1e-6:
                    issues.append(
                        GeometryIssue(
                            kind="spacing",
                            severity="medium",
                            detail=f"Tight clearance {ida}/{idb}: ~{d:.1f}px",
                            node_ids=sorted({ida, idb}),
                        )
                    )

    for nid, box in placements.items():
        label = nid_to_label.get(nid)
        est_w, est_h = estimate_label_fit(label)
        if box.width + 14 < est_w * 0.85 or box.height + 22 < est_h * 0.85:
            issues.append(
                GeometryIssue(
                    kind="overflow_estimate",
                    severity="low",
                    detail=f"{nid}: box may truncate long label visually",
                    node_ids=[nid],
                )
            )

    if canvas_width is not None and canvas_height is not None:
        margin = 4.0
        for nid, box in placements.items():
            if (
                box.x < margin - 1
                or box.y < margin - 1
                or box.x + box.width > float(canvas_width) - margin
                or box.y + box.height > float(canvas_height) - margin
            ):
                issues.append(
                    GeometryIssue(
                        kind="out_of_bounds",
                        severity="high",
                        detail=f"{nid} exceeds canvas",
                        node_ids=[nid],
                    )
                )

    return issues[:96]


def validate_edges_against_layout(
    edges: list[PlannerEdge],
    placements: dict[str, LayoutBox],
    archetype: DiagramArchetype,
) -> list[GeometryIssue]:
    """Flag arrow direction mismatches (horizontal process vs vertical hierarchy)."""

    issues: list[GeometryIssue] = []
    filt = [e for e in edges if e.from_id in placements and e.to in placements]
    for e in filt:
        a, b = placements[e.from_id], placements[e.to]
        ca, cb = _center(a), _center(b)
        dx, dy = abs(cb[0] - ca[0]), abs(cb[1] - ca[1])
        if archetype in ("process", "timeline"):
            if dx < 8.0 and dy > 12.0:
                issues.append(
                    GeometryIssue(
                        kind="arrow_axis",
                        severity="medium",
                        detail=f"process edge {e.from_id}→{e.to} not horizontal",
                        node_ids=[e.from_id, e.to],
                    )
                )
            if ca[0] > cb[0] + 4.0:
                issues.append(
                    GeometryIssue(
                        kind="arrow_direction",
                        severity="low",
                        detail=f"process edge {e.from_id}→{e.to} goes right-to-left",
                        node_ids=[e.from_id, e.to],
                    )
                )
        elif archetype == "hierarchy":
            if cb[1] <= ca[1] + 4.0:
                issues.append(
                    GeometryIssue(
                        kind="arrow_direction",
                        severity="medium",
                        detail=f"hierarchy edge {e.from_id}→{e.to} does not flow downward",
                        node_ids=[e.from_id, e.to],
                    )
                )
    return issues


def repair_placement_spacing(
    placements: dict[str, LayoutBox],
    *,
    target_gap: float = MIN_NODE_EDGE_SEPARATION,
    max_iters: int = _REPAIR_ITERS,
) -> dict[str, LayoutBox]:
    """Push overlapping / tight boxes apart deterministically."""

    ids = list(placements.keys())
    if len(ids) < 2:
        return placements
    boxes = {i: placements[i].model_copy() for i in ids}

    for _ in range(max_iters):
        moved = False
        for i, ia in enumerate(ids):
            for ib in ids[i + 1 :]:
                a, b = boxes[ia], boxes[ib]
                if _overlap_area(a, b) > 1e-3:
                    cax, cay = _center(a)
                    cbx, cby = _center(b)
                    dx, dy = cax - cbx, cay - cby
                    ln = math.hypot(dx, dy) or 1.0
                    push = (target_gap + 2.0) / ln
                    dx *= push * 0.52
                    dy *= push * 0.52
                    boxes[ia] = a.model_copy(update={"x": a.x + dx, "y": a.y + dy})
                    boxes[ib] = b.model_copy(update={"x": b.x - dx, "y": b.y - dy})
                    moved = True
                else:
                    d = _exterior_clearance(a, b)
                    if d < target_gap and d >= 0.0:
                        cax, cay = _center(a)
                        cbx, cby = _center(b)
                        dx, dy = cax - cbx, cay - cby
                        ln = math.hypot(dx, dy) or 1.0
                        need = (target_gap - d) * 0.51
                        dx = need * dx / ln
                        dy = need * dy / ln
                        boxes[ia] = a.model_copy(update={"x": a.x + dx, "y": a.y + dy})
                        boxes[ib] = b.model_copy(update={"x": b.x - dx, "y": b.y - dy})
                        moved = True
        if not moved:
            break

    min_x = min(b.x for b in boxes.values())
    min_y = min(b.y for b in boxes.values())
    pad_fix_x = max(0.0, 12.0 - min_x)
    pad_fix_y = max(0.0, 12.0 - min_y)
    for k in boxes:
        b_ = boxes[k]
        boxes[k] = b_.model_copy(update={"x": b_.x + pad_fix_x, "y": b_.y + pad_fix_y})
    return boxes


def shift_into_canvas(
    placements: dict[str, LayoutBox],
    canvas_width: int,
    canvas_height: int,
    margin: float,
) -> dict[str, LayoutBox]:
    """Translate all boxes so they fit inside [margin, canvas-margin]."""

    if not placements:
        return placements
    out = {k: v.model_copy() for k, v in placements.items()}
    min_x = min(b.x for b in out.values())
    min_y = min(b.y for b in out.values())
    max_r = max(b.x + b.width for b in out.values())
    max_b = max(b.y + b.height for b in out.values())
    dx, dy = 0.0, 0.0
    if min_x < margin:
        dx = margin - min_x
    if min_y < margin:
        dy = margin - min_y
    for k in out:
        b = out[k]
        out[k] = b.model_copy(update={"x": b.x + dx, "y": b.y + dy})
    max_r = max(b.x + b.width for b in out.values())
    max_b = max(b.y + b.height for b in out.values())
    dx2 = 0.0
    dy2 = 0.0
    if max_r > float(canvas_width) - margin:
        dx2 = float(canvas_width) - margin - max_r
    if max_b > float(canvas_height) - margin:
        dy2 = float(canvas_height) - margin - max_b
    if dx2 or dy2:
        for k in out:
            b = out[k]
            out[k] = b.model_copy(update={"x": b.x + dx2, "y": b.y + dy2})
    return out


def has_critical_geometry_issues(issues: list[GeometryIssue]) -> bool:
    return any(gi.kind in ("overlap", "out_of_bounds") for gi in issues)
