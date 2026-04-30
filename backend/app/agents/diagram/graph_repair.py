"""Validate and repair planner graphs before layout (deterministic, no LLM)."""

from __future__ import annotations

from collections import defaultdict, deque

from app.agents.diagram.models import (
    DiagramArchetype,
    PlannerEdge,
    PlannerGroup,
    PlannerNode,
    PlannerOutput,
)


def repair_planner_graph(planner: PlannerOutput, archetype: DiagramArchetype) -> PlannerOutput:
    """Coerce node types, fix orphans, and enforce archetype-specific topology."""

    nodes = [_coerce_node(n) for n in planner.nodes]
    nid_set = {n.id for n in nodes}
    edges = _dedupe_edges(planner.edges, nid_set)
    groups = list(planner.groups)

    if archetype == "comparison":
        groups = _ensure_groups_cover_nodes(nodes, groups)
        column_edges = _comparison_column_chains(nodes, groups)
        edges = _dedupe_edges(column_edges + edges, nid_set)
        edges = _remove_orphans_by_edges(nodes, edges, archetype, groups)
        return PlannerOutput(nodes=nodes, edges=edges, groups=groups)

    if archetype in ("process", "timeline"):
        edges = _repair_process_chain(nodes, edges)
    elif archetype == "hierarchy":
        edges = _repair_hierarchy_single_root(nodes, edges)
    elif archetype == "system":
        edges = _repair_connected_star(nodes, edges)

    edges = _remove_orphans_by_edges(nodes, edges, archetype, None)
    groups = [g for g in groups if any(nid in nid_set for nid in g.node_ids)]
    return PlannerOutput(nodes=nodes, edges=edges, groups=groups)


def _coerce_node(n: PlannerNode) -> PlannerNode:
    t = (n.type or "secondary").lower().strip()
    if t in ("main", "secondary", "small"):
        out_t = t  # type: ignore[assignment]
    elif t in ("step", "milestone", "hub", "process", "central", "primary", "stage"):
        out_t = "main"
    elif t in ("note", "detail", "caption", "footnote", "badge", "tag"):
        out_t = "small"
    else:
        out_t = "secondary"
    return n.model_copy(update={"type": out_t})


def _dedupe_edges(edges: list[PlannerEdge], nid_set: set[str]) -> list[PlannerEdge]:
    out: list[PlannerEdge] = []
    seen: set[tuple[str, str]] = set()
    for e in edges:
        if e.from_id not in nid_set or e.to not in nid_set or e.from_id == e.to:
            continue
        key = (e.from_id, e.to)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _node_index(nodes: list[PlannerNode]) -> dict[str, int]:
    return {n.id: i for i, n in enumerate(nodes)}


def _topo_order(nodes: list[PlannerNode], edges: list[PlannerEdge]) -> list[str]:
    nids = [n.id for n in nodes]
    pos = _node_index(nodes)
    adj: dict[str, list[str]] = defaultdict(list)
    indeg: dict[str, int] = defaultdict(int)
    for e in edges:
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
    if len(order) < len(nids):
        rest = [nid for nid in nids if nid not in order]
        rest.sort(key=lambda x: pos[x])
        order.extend(rest)
    return order


def _repair_process_chain(nodes: list[PlannerNode], edges: list[PlannerEdge]) -> list[PlannerEdge]:
    order = _topo_order(nodes, edges)
    if len(order) < 2:
        return edges
    return [
        PlannerEdge.model_validate({"from": order[i], "to": order[i + 1], "label": None})
        for i in range(len(order) - 1)
    ]


def _repair_hierarchy_single_root(nodes: list[PlannerNode], edges: list[PlannerEdge]) -> list[PlannerEdge]:
    nid_set = {n.id for n in nodes}
    edges = _dedupe_edges(edges, nid_set)
    indeg: dict[str, int] = defaultdict(int)
    children: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        children[e.from_id].append(e.to)
        indeg[e.to] += 1
    for nid in nid_set:
        indeg.setdefault(nid, 0)

    roots = sorted(nid for nid in nid_set if indeg[nid] == 0)
    if not roots:
        roots = [nodes[0].id]

    if len(roots) > 1:
        main_root = roots[0]
        extra = [PlannerEdge.model_validate({"from": main_root, "to": r, "label": None}) for r in roots[1:]]
        edges = _dedupe_edges(edges + extra, nid_set)
        children = defaultdict(list)
        indeg = defaultdict(int)
        for e in edges:
            children[e.from_id].append(e.to)
            indeg[e.to] += 1
        for nid in nid_set:
            indeg.setdefault(nid, 0)
        roots = sorted(nid for nid in nid_set if indeg[nid] == 0)
        if not roots:
            roots = [nodes[0].id]

    root = roots[0]
    if root not in nid_set:
        root = nodes[0].id

    parent: dict[str, str] = {}
    q: deque[str] = deque([root])
    seen: set[str] = {root}
    while q:
        u = q.popleft()
        for v in sorted(set(children.get(u, []))):
            if v in seen:
                continue
            seen.add(v)
            parent[v] = u
            q.append(v)

    for nid in sorted(nid_set):
        if nid != root and nid not in parent:
            parent[nid] = root

    return [
        PlannerEdge.model_validate({"from": parent[nid], "to": nid, "label": None})
        for nid in nid_set
        if nid != root and nid in parent
    ]


def _comparison_column_chains(nodes: list[PlannerNode], groups: list[PlannerGroup]) -> list[PlannerEdge]:
    pos = _node_index(nodes)
    out: list[PlannerEdge] = []
    for g in groups:
        ids = sorted([nid for nid in g.node_ids if nid in pos], key=lambda x: pos[x])
        for i in range(len(ids) - 1):
            out.append(
                PlannerEdge.model_validate({"from": ids[i], "to": ids[i + 1], "label": None})
            )
    return out


def _ensure_groups_cover_nodes(nodes: list[PlannerNode], groups: list[PlannerGroup]) -> list[PlannerGroup]:
    nid_set = {n.id for n in nodes}
    assigned: set[str] = set()
    fixed: list[PlannerGroup] = []
    for i, g in enumerate(groups):
        ids = [nid for nid in g.node_ids if nid in nid_set and nid not in assigned]
        for nid in ids:
            assigned.add(nid)
        if ids:
            gid = (g.id or "").strip() or f"g{i}"
            fixed.append(
                PlannerGroup(
                    id=gid,
                    label=g.label or "",
                    node_ids=ids,
                )
            )

    orphans = [nid for nid in sorted(nid_set) if nid not in assigned]
    if len(fixed) < 2:
        all_ids = [n.id for n in nodes]
        mid = max(1, len(all_ids) // 2)
        fixed = [
            PlannerGroup(id="g0", label="A", node_ids=all_ids[:mid]),
            PlannerGroup(
                id="g1",
                label="B",
                node_ids=all_ids[mid:] if len(all_ids[mid:]) >= 1 else all_ids[-1:],
            ),
        ]
        if len(fixed[1].node_ids) == 0:
            fixed[1] = PlannerGroup(id="g1", label="B", node_ids=[all_ids[-1]])
        return fixed

    gi = 0
    while orphans:
        og = orphans.pop(0)
        target_idx = gi % len(fixed)
        g = fixed[target_idx]
        fixed[target_idx] = g.model_copy(update={"node_ids": g.node_ids + [og]})
        gi += 1
    return fixed


def _repair_connected_star(nodes: list[PlannerNode], edges: list[PlannerEdge]) -> list[PlannerEdge]:
    nid_set = {n.id for n in nodes}
    edges = _dedupe_edges(edges, nid_set)
    degree: dict[str, int] = defaultdict(int)
    for e in edges:
        degree[e.from_id] += 1
        degree[e.to] += 1

    hub_id = next((n.id for n in nodes if n.emphasis), None)
    if hub_id is None and len(nid_set) > 1:
        hub_id = max(
            nid_set,
            key=lambda x: (degree[x], -next(i for i, nn in enumerate(nodes) if nn.id == x)),
        )
    if hub_id is None:
        hub_id = nodes[0].id

    seen_pairs: set[tuple[str, str]] = set()
    out: list[PlannerEdge] = []
    for e in edges:
        key = (e.from_id, e.to)
        if key not in seen_pairs:
            seen_pairs.add(key)
            out.append(e)

    connected: set[str] = set()
    for e in out:
        connected.add(e.from_id)
        connected.add(e.to)
    for nid in sorted(nid_set):
        if nid in connected:
            continue
        if nid == hub_id:
            alt = next((x for x in sorted(nid_set) if x != hub_id), None)
            if alt is None:
                continue
            k = (alt, hub_id)
            if k not in seen_pairs and (hub_id, alt) not in seen_pairs:
                seen_pairs.add(k)
                out.append(PlannerEdge.model_validate({"from": alt, "to": hub_id, "label": None}))
            continue
        k = (hub_id, nid)
        if k not in seen_pairs:
            seen_pairs.add(k)
            out.append(PlannerEdge.model_validate({"from": hub_id, "to": nid, "label": None}))
    return _dedupe_edges(out, nid_set)


def _remove_orphans_by_edges(
    nodes: list[PlannerNode],
    edges: list[PlannerEdge],
    archetype: DiagramArchetype,
    groups: list[PlannerGroup] | None,
) -> list[PlannerEdge]:
    nid_set = {n.id for n in nodes}
    touched: set[str] = set()
    for e in edges:
        touched.add(e.from_id)
        touched.add(e.to)
    orphans = [nid for nid in nid_set if nid not in touched]
    if not orphans:
        return edges

    extra = list(edges)
    if archetype in ("process", "timeline"):
        return _repair_process_chain(nodes, extra)
    if archetype == "hierarchy":
        root = next((n.id for n in nodes if n.emphasis), nodes[0].id)
        for o in orphans:
            extra.append(PlannerEdge.model_validate({"from": root, "to": o, "label": None}))
        return _repair_hierarchy_single_root(nodes, extra)
    if archetype == "system":
        for o in orphans:
            hub = next((n.id for n in nodes if n.emphasis), nodes[0].id)
            extra.append(PlannerEdge.model_validate({"from": hub, "to": o, "label": None}))
        return _repair_connected_star(nodes, extra)
    if archetype == "comparison" and groups:
        for o in orphans:
            g_pick = min(groups, key=lambda gg: len(gg.node_ids))
            nid_list = list(g_pick.node_ids)
            anchor = next((x for x in nid_list if x != o), None)
            if anchor:
                extra.append(PlannerEdge.model_validate({"from": anchor, "to": o, "label": None}))
            else:
                extra.append(PlannerEdge.model_validate({"from": nodes[0].id, "to": o, "label": None}))
        return _dedupe_edges(extra, nid_set)
    hub = nodes[0].id
    for o in orphans:
        extra.append(PlannerEdge.model_validate({"from": hub, "to": o, "label": None}))
    return _dedupe_edges(extra, nid_set)
