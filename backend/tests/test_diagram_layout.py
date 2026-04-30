"""Unit tests — deterministic diagram layout + fallback planner (no API calls)."""

from __future__ import annotations

import math

from app.agents.diagram.diagram_asset_layer import apply_diagram_assets
from app.agents.diagram.geometry_validator import validate_geometry
from app.agents.diagram.layout_engine import run_layout_engine
from app.agents.diagram.llm_agents import minimal_planner_from_strategist, normalize_planner_graph
from app.agents.diagram.models import (
    DiagramBrandTheme,
    LayoutBox,
    LayoutConfig,
    PlannerEdge,
    PlannerNode,
    PlannerOutput,
    StrategistOutput,
)
from app.agents.diagram.humanness import apply_humanness
from app.agents.diagram.skeleton_builder import build_scene_skeleton


def test_minimal_chain_process_layout_positions_all_nodes():
    st = StrategistOutput(
        diagram_type="process",
        aha_moment="Bottleneck clears when queue fans out.",
        core_message="Pipeline stages must stay balanced.",
        components=["Ingress", "Buffer", "Worker", "Sink"],
    )
    plan = minimal_planner_from_strategist(st)
    assert len(plan.nodes) >= 2
    placements, (cw, ch) = run_layout_engine(
        plan.nodes,
        plan.edges,
        plan.groups,
        seed=99,
        layout_config=LayoutConfig(layout_archetype=st.diagram_type),
    )
    for n in plan.nodes:
        assert n.id in placements
        box = placements[n.id]
        assert box.width >= 44 and box.height >= 44


def test_normalize_dedupe_and_single_emphasis():
    st = StrategistOutput(
        diagram_type="system",
        aha_moment="x",
        core_message="y",
        components=["Alpha", "Beta"],
    )
    messy = PlannerOutput(
        nodes=[
            PlannerNode(id="dup", label="Alpha node", type="secondary", emphasis=False),
            PlannerNode(id="dup", label="lost", type="secondary", emphasis=False),
            PlannerNode(id="b2", label="Beta", type="secondary", emphasis=False),
        ],
        edges=[
            PlannerEdge.model_validate({"from": "dup", "to": "b2", "label": None}),
        ],
        groups=[],
    )
    cleaned = normalize_planner_graph(messy, st)
    assert len(cleaned.nodes) == 2
    assert sum(1 for n in cleaned.nodes if n.emphasis) == 1


def test_skeleton_and_humanness_accept_scene_skeleton():
    st = StrategistOutput(
        diagram_type="hierarchy",
        aha_moment="Root fans into roles.",
        core_message="Org of the flow.",
        components=["CEO", "PM", "IC"],
    )
    plan = PlannerOutput(
        nodes=[
            PlannerNode(id="a", label="CEO", type="main", emphasis=True),
            PlannerNode(id="b", label="PM", type="secondary", emphasis=False),
            PlannerNode(id="c", label="IC", type="secondary", emphasis=False),
        ],
        edges=[
            PlannerEdge.model_validate({"from": "a", "to": "b", "label": None}),
            PlannerEdge.model_validate({"from": "a", "to": "c", "label": None}),
        ],
        groups=[],
    )
    placements, (cw, ch) = run_layout_engine(
        plan.nodes,
        plan.edges,
        plan.groups,
        seed=3,
        layout_config=LayoutConfig(layout_archetype=st.diagram_type),
    )
    scene = build_scene_skeleton(
        st,
        plan.nodes,
        plan.edges,
        plan.groups,
        placements,
        cw,
        ch,
        DiagramBrandTheme(primary="#00AAFF", accent="#00AAFF"),
    )
    scene2 = apply_humanness(scene, seed=12345)
    assert len(scene2.elements) == len(scene.elements)
    ids = [e.id for e in scene.elements]
    assert ids == [e.id for e in scene2.elements]
    rects_a = {e.id: (float(e.x), float(e.y)) for e in scene.elements if e.type == "rectangle"}
    rects_b = {e.id: (float(e.x), float(e.y)) for e in scene2.elements if e.type == "rectangle"}
    assert any(abs(rects_a[k][i] - rects_b[k][i]) > 1e-4 for k in rects_a for i in range(2))


def test_diagram_asset_layer_adds_svg_images_within_cap():
    st = StrategistOutput(
        diagram_type="process",
        aha_moment="Growth loop",
        core_message="User growth",
        components=["A", "B", "C", "D"],
    )
    plan = PlannerOutput(
        nodes=[
            PlannerNode(id="n1", label="Startup growth phase", type="main", emphasis=True),
            PlannerNode(id="n2", label="Server deploy", type="main", emphasis=False),
            PlannerNode(id="n3", label="User signup", type="secondary", emphasis=False),
            PlannerNode(id="n4", label="Small note", type="small", emphasis=False),
        ],
        edges=[
            PlannerEdge.model_validate({"from": "n1", "to": "n2", "label": None}),
            PlannerEdge.model_validate({"from": "n2", "to": "n3", "label": None}),
            PlannerEdge.model_validate({"from": "n3", "to": "n4", "label": None}),
        ],
        groups=[],
    )
    placements, (cw, ch) = run_layout_engine(
        plan.nodes,
        plan.edges,
        plan.groups,
        seed=7,
        layout_config=LayoutConfig(layout_archetype="process"),
    )
    theme = DiagramBrandTheme(primary="#3366CC", accent="#CC6600")
    scene = build_scene_skeleton(st, plan.nodes, plan.edges, plan.groups, placements, cw, ch, theme)
    scene_h = apply_humanness(scene, seed=11)
    out = apply_diagram_assets(scene_h, plan.nodes, theme, "process", seed=99)
    images = [e for e in out.elements if e.type == "image"]
    assert len(images) >= 1
    assert out.files
    for _fid, meta in out.files.items():
        assert meta.get("dataURL", "").startswith("data:image/svg+xml;base64,")
    assert len(images) <= max(0, math.ceil(len(plan.nodes) * 0.3))
    node_ids = {n.id for n in plan.nodes}
    grouped = [
        e
        for e in out.elements
        if e.groupIds and e.id in node_ids and e.type == "rectangle"
    ]
    assert grouped


def test_validate_geometry_reports_overlap():
    placements = {
        "a": LayoutBox(id="a", x=0, y=0, width=200, height=88),
        "b": LayoutBox(id="b", x=50, y=30, width=220, height=92),
    }
    nodes = [
        PlannerNode(id="a", label="AAA", type="main", emphasis=True),
        PlannerNode(id="b", label="BBB", type="secondary", emphasis=False),
    ]
    bugs = validate_geometry(placements, nodes)
    kinds = [b.kind for b in bugs]
    assert "overlap" in kinds or "spacing" in kinds


def test_long_planner_label_splits_rect_title_and_body_text():
    """Long / multiline node labels must not all go into bound ``label`` (centered overlap)."""
    st = StrategistOutput(
        diagram_type="process",
        aha_moment="Insight",
        core_message="Core",
        components=["A", "B"],
    )
    long_body = "This paragraph elaborates the card in detail. " * 4
    plan = PlannerOutput(
        nodes=[
            PlannerNode(
                id="n1",
                label=f"Card Title\n{long_body}",
                type="main",
                emphasis=True,
            ),
            PlannerNode(id="n2", label="Next", type="secondary", emphasis=False),
        ],
        edges=[
            PlannerEdge.model_validate({"from": "n1", "to": "n2", "label": None}),
        ],
        groups=[],
    )
    placements, (cw, ch) = run_layout_engine(
        plan.nodes,
        plan.edges,
        plan.groups,
        seed=2,
        layout_config=LayoutConfig(layout_archetype=st.diagram_type),
    )
    scene = build_scene_skeleton(
        st,
        plan.nodes,
        plan.edges,
        plan.groups,
        placements,
        cw,
        ch,
        DiagramBrandTheme(primary="#E8442A", accent="#E8442A"),
    )
    n1 = next(e for e in scene.elements if e.id == "n1")
    body = next(e for e in scene.elements if e.id == "n1-body")
    assert n1.label is not None
    assert n1.label.text.strip() == "Card Title"
    assert body.type == "text"
    assert (body.text or "").strip().startswith("This paragraph")
    assert body.y > n1.y
    assert body.x >= n1.x + 10
