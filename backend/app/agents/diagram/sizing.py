"""Label → bounding-box heuristics and fixed node-type dimensions."""

from __future__ import annotations

from app.agents.diagram.models import PlannerNode

# Fallback when measuring label-only boxes (validation)
_DEFAULT_NODE_W = 200.0
_DEFAULT_NODE_H = 88.0

_MAIN_W, _MAIN_H = 300.0, 120.0
_SECONDARY_W, _SECONDARY_H = 220.0, 100.0
_SMALL_W, _SMALL_H = 160.0, 80.0


def node_rect_dims(node: PlannerNode) -> tuple[float, float]:
    """Fixed canvas footprint by strategist node type."""

    t = node.type
    if t == "main":
        return (_MAIN_W, _MAIN_H)
    if t == "small":
        return (_SMALL_W, _SMALL_H)
    return (_SECONDARY_W, _SECONDARY_H)


def estimate_label_fit(label: str | None) -> tuple[float, float]:
    """Heuristic text hull — used for overflow checks only."""

    line = (label or "").strip() or "—"
    w = min(420.0, max(_DEFAULT_NODE_W, 14.0 * min(len(line), 48) + 48.0))
    h = _DEFAULT_NODE_H if len(line) < 40 else min(140.0, _DEFAULT_NODE_H + 36.0)
    return (w, h)
