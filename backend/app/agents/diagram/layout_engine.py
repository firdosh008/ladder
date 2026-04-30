"""Deterministic layouts — all coordinates computed here (LLM-safe)."""

from __future__ import annotations

import math
from collections import defaultdict, deque

from app.agents.diagram.models import (
    DiagramArchetype,
    LayoutBox,
    LayoutConfig,
    PlannerEdge,
    PlannerGroup,
    PlannerNode,
)
from app.agents.diagram.sizing import node_rect_dims


def _nid_set(nodes: list[PlannerNode]) -> set[str]:
    return {n.id for n in nodes}


def _filter_edges(nodes: list[PlannerNode], edges: list[PlannerEdge]) -> list[PlannerEdge]:
    nids = _nid_set(nodes)
    out: list[PlannerEdge] = []
    for e in edges:
        if e.from_id in nids and e.to in nids and e.from_id != e.to:
            out.append(e)
    return out


def _node_index(nodes: list[PlannerNode]) -> dict[str, int]:
    return {n.id: i for i, n in enumerate(nodes)}


def _process_chain_order(nodes: list[PlannerNode], edges: list[PlannerEdge]) -> list[str]:
    nids = [n.id for n in nodes]
    pos = _node_index(nodes)
    adj: dict[str, list[str]] = defaultdict(list)
    indeg: dict[str, int] = defaultdict(int)
    for e in _filter_edges(nodes, edges):
        adj[e.from_id].append(e.to)
        indeg[e.to] += 1
    for nid in nids:
        indeg.setdefault(nid, 0)
    q = sorted([nid for nid in nids if indeg[nid] == 0], key=lambda x: pos[x])
    order: list[str] = []
    while q:
        u = q.pop(0)
        order.append(u)
        for v in sorted(adj.get(u, []), key=lambda x: pos[x]):
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
        q.sort(key=lambda x: pos[x])
    for nid in nids:
        if nid not in order:
            order.append(nid)
    return order


def layout_process(
    nodes: list[PlannerNode], edges: list[PlannerEdge], pad: float, title_band: float, h_gap: float
) -> dict[str, LayoutBox]:
    nid_to_node = {n.id: n for n in nodes}
    seq = _process_chain_order(nodes, edges)
    row_chunks: list[tuple[str, float, float]] = []
    for nid in seq:
        n = nid_to_node[nid]
        w, h = node_rect_dims(n)
        row_chunks.append((nid, w, h))
    row_h = max((h for _, _, h in row_chunks), default=100.0)
    x = pad
    placements: dict[str, LayoutBox] = {}
    for nid, w, h in row_chunks:
        yy = pad + title_band + (row_h - h) / 2.0
        placements[nid] = LayoutBox(id=nid, x=x, y=yy, width=w, height=h)
        x += w + h_gap
    return placements


def layout_hierarchy(
    nodes: list[PlannerNode],
    edges: list[PlannerEdge],
    pad: float,
    title_band: float,
    h_gap: float,
    v_gap: float,
    canvas_w: float,
) -> dict[str, LayoutBox]:
    nid_to_node = {n.id: n for n in nodes}
    nids = _nid_set(nodes)
    filt = _filter_edges(nodes, edges)
    indeg: dict[str, int] = defaultdict(int)
    children: dict[str, list[str]] = defaultdict(list)
    for e in filt:
        children[e.from_id].append(e.to)
        indeg[e.to] += 1
    for nid in nids:
        indeg.setdefault(nid, 0)
    roots = sorted(nid for nid in nids if indeg[nid] == 0)
    root = roots[0] if roots else nodes[0].id

    level: dict[str, int] = {root: 0}
    q: deque[str] = deque([root])
    order_visit: list[str] = []
    while q:
        u = q.popleft()
        order_visit.append(u)
        lu = level[u]
        for v in sorted(set(children.get(u, []))):
            cand = lu + 1
            if v not in level or cand > level[v]:
                level[v] = cand
            if v not in order_visit:
                q.append(v)
    for nid in nids:
        level.setdefault(nid, 0)

    by_level: dict[int, list[str]] = defaultdict(list)
    max_lv = 0
    for nid in nids:
        lv = level[nid]
        by_level[lv].append(nid)
        max_lv = max(max_lv, lv)
    for lv in by_level:
        by_level[lv].sort()

    placements: dict[str, LayoutBox] = {}
    y_cursor = pad + title_band
    usable_w = canvas_w - 2 * pad
    for lv in range(max_lv + 1):
        bucket = by_level[lv]
        dims = [(nid_to_node[i], node_rect_dims(nid_to_node[i])) for i in bucket]
        widths = [d[1][0] for d in dims]
        total_w = sum(widths) + h_gap * max(0, len(bucket) - 1)
        scale = min(1.0, usable_w / total_w) if total_w > 1e-6 else 1.0
        row_w = sum(w * scale for w in widths) + h_gap * scale * max(0, len(bucket) - 1)
        x_cursor = pad + max(0.0, (usable_w - row_w) / 2.0)
        row_h = 0.0
        for nid, (_, (tw, th)) in zip(bucket, dims, strict=True):
            w_, h_ = tw * scale, th * scale
            row_h = max(row_h, h_)
            placements[nid] = LayoutBox(id=nid, x=x_cursor, y=y_cursor, width=w_, height=h_)
            x_cursor += w_ + h_gap * scale
        y_cursor += row_h + v_gap

    return placements


def layout_comparison(
    nodes: list[PlannerNode],
    groups: list[PlannerGroup],
    pad: float,
    title_band: float,
    h_gap: float,
    v_gap: float,
) -> dict[str, LayoutBox]:
    nid_to_node = {n.id: n for n in nodes}
    placements: dict[str, LayoutBox] = {}
    col_widths: list[float] = []
    col_nodes: list[list[str]] = []
    for g in groups:
        ids = [nid for nid in g.node_ids if nid in nid_to_node]
        col_nodes.append(ids)
        mw = 0.0
        for nid in ids:
            mw = max(mw, node_rect_dims(nid_to_node[nid])[0])
        col_widths.append(mw)
    inter_col = h_gap
    x_col = pad
    for col_idx, ids in enumerate(col_nodes):
        y = pad + title_band
        cw = col_widths[col_idx] if col_idx < len(col_widths) else 220.0
        for nid in ids:
            n = nid_to_node[nid]
            w, h = node_rect_dims(n)
            x = x_col + (cw - w) / 2.0
            placements[nid] = LayoutBox(id=nid, x=x, y=y, width=w, height=h)
            y += h + v_gap
        x_col += cw + inter_col
    return placements


def layout_system(
    nodes: list[PlannerNode],
    edges: list[PlannerEdge],
    pad: float,
    title_band: float,
    h_gap: float,
) -> dict[str, LayoutBox]:
    nid_to_node = {n.id: n for n in nodes}
    nids = [n.id for n in nodes]
    filt = _filter_edges(nodes, edges)
    deg: dict[str, int] = defaultdict(int)
    for e in filt:
        deg[e.from_id] += 1
        deg[e.to] += 1
    hub = next((n.id for n in nodes if n.emphasis), None)
    if hub is None and len(nids) > 1:
        hub = max(nids, key=lambda x: (deg[x], -next(i for i, nn in enumerate(nodes) if nn.id == x)))
    if hub is None:
        hub = nids[0]

    others = [nid for nid in nids if nid != hub]
    hw, hh = node_rect_dims(nid_to_node[hub])
    max_sat_r = 0.0
    for nid in others:
        w, h = node_rect_dims(nid_to_node[nid])
        max_sat_r = max(max_sat_r, math.hypot(w, h) / 2.0)
    n_others = len(others)
    R = max(220.0, max_sat_r * 2.0 + h_gap * 0.6) + (n_others * 4)
    cx, cy = 0.0, 0.0
    placements: dict[str, LayoutBox] = {
        hub: LayoutBox(id=hub, x=cx - hw / 2.0, y=cy - hh / 2.0, width=hw, height=hh)
    }
    for i, nid in enumerate(others):
        w, h = node_rect_dims(nid_to_node[nid])
        ang = 2 * math.pi * i / max(1, n_others) - math.pi / 2.0
        px = cx + R * math.cos(ang) - w / 2.0
        py = cy + R * math.sin(ang) - h / 2.0
        placements[nid] = LayoutBox(id=nid, x=px, y=py, width=w, height=h)

    min_x = min(b.x for b in placements.values())
    min_y = min(b.y for b in placements.values())
    dx = pad - min_x
    dy = pad + title_band - min_y
    out: dict[str, LayoutBox] = {}
    for nid, b in placements.items():
        out[nid] = b.model_copy(update={"x": b.x + dx, "y": b.y + dy})
    return out


def compute_canvas_size(
    placements: dict[str, LayoutBox], edge_margin: float
) -> tuple[int, int]:
    if not placements:
        return (1280, 800)
    max_r = max(b.x + b.width for b in placements.values())
    max_b = max(b.y + b.height for b in placements.values())
    cw = int(max(1280.0, max_r + edge_margin))
    ch = int(max(820.0, max_b + edge_margin + 40))
    return (cw, ch)


def run_layout_engine(
    nodes: list[PlannerNode],
    edges: list[PlannerEdge],
    groups: list[PlannerGroup],
    *,
    seed: int,  # noqa: ARG001 — reserved for future deterministic variants
    layout_config: LayoutConfig,
) -> tuple[dict[str, LayoutBox], tuple[int, int]]:
    _ = seed
    sm = layout_config.spacing_multiplier
    pad = layout_config.padding
    title_band = layout_config.title_band
    h_gap = layout_config.horizontal_gap * sm
    v_gap = layout_config.vertical_gap * sm
    arch: DiagramArchetype = layout_config.layout_archetype

    canvas_w_guess = 1400.0 + h_gap * 2.0

    if arch in ("process", "timeline"):
        placements = layout_process(nodes, edges, pad, title_band, h_gap)
    elif arch == "hierarchy":
        placements = layout_hierarchy(nodes, edges, pad, title_band, h_gap, v_gap, canvas_w_guess)
    elif arch == "comparison":
        placements = layout_comparison(
            nodes, groups if groups else [], pad, title_band, h_gap, v_gap
        )
    else:
        placements = layout_system(nodes, edges, pad, title_band, h_gap)

    cw, ch = compute_canvas_size(placements, edge_margin=pad)
    if arch == "hierarchy" and float(cw) > canvas_w_guess + 20:
        placements = layout_hierarchy(nodes, edges, pad, title_band, h_gap, v_gap, float(cw))
        cw, ch = compute_canvas_size(placements, edge_margin=pad)

    return placements, (cw, ch)
