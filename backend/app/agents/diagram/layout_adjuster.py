"""Deterministic layout tuning driven by geometric hits + critic intent strings."""

from __future__ import annotations

import re

from app.agents.diagram.models import (
    DiagramArchetype,
    GeometryIssue,
    LayoutConfig,
    VisualCriticOutput,
)


def adjust_layout_config(
    prev: LayoutConfig,
    critic: VisualCriticOutput,
    geometry_issues: list[GeometryIssue],
) -> LayoutConfig:
    """Never calls an LLM — pure rule surface."""

    sm = prev.spacing_multiplier
    hg = prev.horizontal_gap
    vg = prev.vertical_gap
    pad = prev.padding
    tb = prev.title_band
    arch: DiagramArchetype = prev.layout_archetype

    for g in geometry_issues:
        if g.kind in ("overlap", "out_of_bounds"):
            sm = min(5.5, sm * 1.15)
            hg = min(560.0, hg * 1.08)
            vg = min(420.0, vg * 1.1)
            pad = min(260.0, pad + 12.0)
        elif g.kind == "spacing":
            sm = min(5.2, sm * 1.08)
            hg = min(520.0, hg * 1.06)
            vg = min(400.0, vg * 1.06)
        elif g.kind in ("arrow_axis", "arrow_direction"):
            sm = min(5.0, sm * 1.06)
            hg = min(500.0, hg * 1.05)
            vg = min(380.0, vg * 1.05)
        elif g.kind == "overflow_estimate":
            pad = min(260.0, pad + 8.0)
            sm = min(5.0, sm * 1.04)

    lowered = [_norm(a) for a in critic.layout_actions]
    lowered_text = "\n".join(lowered)

    if _any_kw(lowered_text, ["hierarchy", "hierarchical", "tree", "upstream"]):
        arch = "hierarchy"
    if _any_kw(lowered_text, ["timeline", "chronological", "sequence_horizontal"]):
        arch = "timeline"
    if _any_kw(lowered_text, ["process", "pipeline", "left_to_right", "leftright"]):
        arch = "process"
    if _any_kw(lowered_text, ["system", "mesh", "force", "hub", "radial", "dense_graph"]):
        arch = "system"
    if _any_kw(lowered_text, ["comparison", "split", "two_column", "contrast", "columns"]):
        arch = "comparison"

    for act in lowered:
        if "spacing" in act or "inflate" in act or "spread" in act:
            sm = min(5.8, sm * 1.12)
            hg = min(580.0, hg * 1.1)
        if "cluster" in act or "separate" in act:
            vg = min(460.0, vg * 1.12)
            sm = min(6.0, sm * 1.06)
        if "padding" in act or "comfort" in act or "clutter" in act:
            pad = min(280.0, pad + 12.0)
            tb = min(180.0, tb + 6.0)
        if "align" in act or "grid" in act:
            hg = min(540.0, hg * 1.04)
            vg = min(420.0, vg * 1.04)
        if "compress" in act or ("tight" in act and "not" not in act):
            sm = max(0.35, sm * 0.92)

    return LayoutConfig(
        horizontal_gap=round(hg, 2),
        vertical_gap=round(vg, 2),
        padding=round(pad, 2),
        spacing_multiplier=round(sm, 4),
        title_band=round(tb, 2),
        layout_archetype=arch,
    )


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def _any_kw(blob: str, keys: list[str]) -> bool:
    return any(k in blob for k in keys)
