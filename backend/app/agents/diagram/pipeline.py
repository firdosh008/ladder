"""Orchestrate strategist → planner → graph repair → layout → validation → skeleton → critique → layout loop."""

from __future__ import annotations

import logging

from app.agents.diagram.geometry_validator import (
    has_critical_geometry_issues,
    repair_placement_spacing,
    shift_into_canvas,
    validate_edges_against_layout,
    validate_geometry,
)
from app.agents.diagram.diagram_asset_layer import apply_diagram_assets
from app.agents.diagram.graph_repair import repair_planner_graph
from app.agents.diagram.humanness import apply_humanness
from app.agents.diagram.layout_adjuster import adjust_layout_config
from app.agents.diagram.layout_engine import compute_canvas_size, run_layout_engine
from app.agents.diagram.llm_agents import (
    normalize_planner_graph,
    run_planner,
    run_strategist,
    run_visual_diagram_critic,
)
from app.agents.diagram.models import (
    AgentTokenUsage,
    DiagramArchetype,
    DiagramBrandTheme,
    DiagramPipelineDebug,
    GeometryIssue,
    IterationDebug,
    LayoutConfig,
    NodeLayoutDebug,
    VisualCriticOutput,
)
from app.agents.diagram.render_scene import render_scene_to_image
from app.agents.diagram.skeleton_builder import build_scene_skeleton
from app.models.db import SceneSkeleton

log = logging.getLogger(__name__)

_MAX_IT = 3
_SCORE_PASS = 8


class DiagramPipelineError(RuntimeError):
    pass


def _resolved_theme(
    brand_accent: str | None,
    brand_theme: DiagramBrandTheme | None,
) -> DiagramBrandTheme:
    if brand_theme is not None:
        return brand_theme
    if brand_accent:
        hx = brand_accent if brand_accent.startswith("#") else f"#{brand_accent}"
        return DiagramBrandTheme(accent=hx, primary=hx)
    return DiagramBrandTheme()


async def run_diagram_pipeline(
    source_text: str,
    *,
    seed: int = 42,
    brand_accent: str | None = None,
    brand_theme: DiagramBrandTheme | None = None,
) -> tuple[SceneSkeleton, DiagramPipelineDebug, VisualCriticOutput]:
    """Critic loop adjusts layout config only — planner runs once after graph repair."""

    if not source_text.strip():
        raise DiagramPipelineError("source_text is empty")

    theme = _resolved_theme(brand_accent, brand_theme)

    tot_in = tot_out = 0
    st, i1, o1 = await run_strategist(source_text)
    tot_in += i1
    tot_out += o1

    current_planner, i2, o2 = await run_planner(st, source_text)
    tot_in += i2
    tot_out += o2
    current_planner = normalize_planner_graph(current_planner, st)
    current_planner = repair_planner_graph(current_planner, st.diagram_type)

    layout_configs_per_iteration: list[LayoutConfig] = []
    geometry_issues_per_iteration: list[list[GeometryIssue]] = []
    iteration_debug: list[IterationDebug] = []
    critic_runs: list[VisualCriticOutput] = []
    png_paths_per_iteration: list[str] = []
    planner_versions = [current_planner]

    layout_cf = LayoutConfig(layout_archetype=st.diagram_type)
    final_raw: SceneSkeleton | None = None
    last_placements: dict | None = None
    last_crit: VisualCriticOutput | None = None
    graph_arch: DiagramArchetype = st.diagram_type

    for iteration in range(_MAX_IT):
        if layout_cf.layout_archetype != graph_arch:
            current_planner = repair_planner_graph(current_planner, layout_cf.layout_archetype)
            graph_arch = layout_cf.layout_archetype
        placements, _ = run_layout_engine(
            current_planner.nodes,
            current_planner.edges,
            current_planner.groups,
            seed=seed + iteration * 97,
            layout_config=layout_cf,
        )
        min_sep = max(24.0, layout_cf.horizontal_gap * 0.12)
        placements = repair_placement_spacing(placements, target_gap=min_sep)
        cw, ch = compute_canvas_size(placements, edge_margin=layout_cf.padding)
        placements = shift_into_canvas(
            placements, cw, ch, margin=max(16.0, layout_cf.padding * 0.5)
        )
        cw, ch = compute_canvas_size(placements, edge_margin=layout_cf.padding)

        geo = validate_geometry(
            placements,
            current_planner.nodes,
            canvas_width=cw,
            canvas_height=ch,
            min_gap=min_sep * 0.85,
        )
        if layout_cf.layout_archetype in ("process", "timeline", "hierarchy"):
            geo = list(geo) + validate_edges_against_layout(
                current_planner.edges, placements, layout_cf.layout_archetype
            )

        layout_configs_per_iteration.append(layout_cf.model_copy())
        geometry_issues_per_iteration.append(geo)
        iteration_debug.append(
            IterationDebug(
                layout_type=layout_cf.layout_archetype,
                geometry_issue_count=len(geo),
                geometry_issues=[g.detail for g in geo[:16]],
            )
        )

        raw_sk = build_scene_skeleton(
            st,
            current_planner.nodes,
            current_planner.edges,
            current_planner.groups,
            placements,
            cw,
            ch,
            theme,
        )
        png = render_scene_to_image(raw_sk)
        png_paths_per_iteration.append(str(png))

        crit, ic, oc = await run_visual_diagram_critic(
            png, st, current_planner, source_text[:12_000]
        )
        tot_in += ic
        tot_out += oc
        critic_runs.append(crit)
        last_crit = crit
        final_raw = raw_sk
        last_placements = placements

        log.info(
            "diagram iteration=%d score=%d geom_issues=%d layout=%s overlap_crit=%s",
            iteration,
            crit.score,
            len(geo),
            layout_cf.layout_archetype,
            has_critical_geometry_issues(geo),
        )

        if crit.score >= _SCORE_PASS and not has_critical_geometry_issues(geo):
            break
        if iteration < _MAX_IT - 1:
            layout_cf = adjust_layout_config(layout_cf, crit, geo)

    if final_raw is None or last_crit is None or not critic_runs or last_placements is None:
        raise DiagramPipelineError("visual critic produced no verdict")

    nid_to_node = {n.id: n for n in current_planner.nodes}
    node_layout_final = [
        NodeLayoutDebug(
            id=nid,
            x=float(box.x),
            y=float(box.y),
            width=float(box.width),
            height=float(box.height),
            type=nid_to_node[nid].type,
        )
        for nid, box in sorted(last_placements.items(), key=lambda t: t[0])
        if nid in nid_to_node
    ]
    edges_final = [
        {"source": e.from_id, "target": e.to} for e in current_planner.edges[:96]
    ]

    final_scene = apply_humanness(final_raw, seed=seed + 9043)
    final_scene = apply_diagram_assets(
        final_scene,
        list(current_planner.nodes),
        theme,
        graph_arch,
        seed=seed + 18011,
    )

    debug = DiagramPipelineDebug(
        strategist=st,
        planner_versions=planner_versions,
        layout_configs_per_iteration=layout_configs_per_iteration,
        geometry_issues_per_iteration=geometry_issues_per_iteration,
        critic_runs=critic_runs,
        final_score=last_crit.score,
        iterations_used=len(critic_runs),
        token_usage=AgentTokenUsage(input_tokens=tot_in, output_tokens=tot_out),
        render_png_paths_per_iteration=png_paths_per_iteration,
        brand_theme=theme,
        node_layout_final=node_layout_final,
        edges_final=edges_final,
        iteration_debug=iteration_debug,
    )
    return final_scene, debug, last_crit
