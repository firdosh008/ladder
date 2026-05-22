"""Output adapters for the standalone research result.

Adapters stay outside the core graph: the graph produces research primitives;
callers decide whether they want the neutral report or a project-specific artifact.
"""

from __future__ import annotations

from research_agent.models import CommentCluster, SupplySideReport, Thesis


def adapt_research_output(
    output_mode: str,
    winning_thesis: Thesis | None,
    rejected_candidates: list[Thesis],
    supply_report: SupplySideReport,
    unmet_asks: list[CommentCluster],
) -> dict:
    if not winning_thesis:
        return {}
    supply_report = supply_report or SupplySideReport()
    if output_mode == "ladderbrief":
        return adapt_for_ladderbrief(winning_thesis, rejected_candidates, supply_report, unmet_asks)
    if output_mode == "ladderflow":
        return adapt_for_ladderflow(winning_thesis, rejected_candidates, supply_report, unmet_asks)
    return adapt_for_research_report(winning_thesis, rejected_candidates, supply_report, unmet_asks)


def adapt_for_research_report(
    thesis: Thesis,
    rejected_candidates: list[Thesis],
    supply_report: SupplySideReport,
    unmet_asks: list[CommentCluster],
) -> dict:
    return {
        "output_mode": "research_report",
        "executive_summary": thesis.statement,
        "lens": thesis.lens,
        "supporting_points": thesis.supporting_points,
        "supply_side_rationale": thesis.supply_side_rationale,
        "supply_gaps": [
            {
                "type": gap.gap_type,
                "confidence": gap.confidence,
                "description": gap.description,
                "evidence_urls": gap.evidence_urls,
            }
            for gap in supply_report.gaps
        ],
        "unmet_asks": [
            {
                "theme": cluster.theme,
                "frequency": cluster.frequency,
                "representative_comments": cluster.representative_comments,
                "source_platform": cluster.source_platform,
            }
            for cluster in unmet_asks
            if cluster.unmet_ask
        ],
        "rejected_angles": [
            {"lens": item.lens, "statement": item.statement, "reason": item.rejection_reason or ""}
            for item in rejected_candidates
        ],
    }


def adapt_for_ladderflow(
    thesis: Thesis,
    rejected_candidates: list[Thesis],
    supply_report: SupplySideReport,
    unmet_asks: list[CommentCluster],
) -> dict:
    sections = thesis.supporting_points[:6] or [thesis.statement]
    questions = []
    for point in sections[:3]:
        questions.append(f"What is the strongest evidence behind this point: {point}")
        questions.append(f"Where would a smart skeptic disagree with this point: {point}")

    return {
        "product": "ladderflow",
        "format": "podcast_outline",
        "opening_hook": thesis.statement,
        "sections": [
            {
                "title": f"Section {idx + 1}",
                "talking_point": point,
                "evidence_prompt": "Use source provenance from the research result while answering.",
            }
            for idx, point in enumerate(sections)
        ],
        "interview_questions": questions,
        "voice_agent_prompt": (
            "Interview the creator to defend, nuance, and personalize the thesis. "
            "Push for concrete examples, contrarian edges, and lived operator detail."
        ),
        "unmet_asks_to_probe": [cluster.theme for cluster in unmet_asks if cluster.unmet_ask][:5],
        "rejected_angles": [
            {"lens": item.lens, "reason": item.rejection_reason or ""}
            for item in rejected_candidates
        ],
    }


def adapt_for_ladderbrief(
    thesis: Thesis,
    rejected_candidates: list[Thesis],
    supply_report: SupplySideReport,
    unmet_asks: list[CommentCluster],
) -> dict:
    center_id = "thesis"
    point_nodes = [
        {
            "id": f"point_{idx + 1}",
            "type": "supporting_point",
            "text": point,
        }
        for idx, point in enumerate(thesis.supporting_points[:6])
    ]
    sticky_nodes = [
        {
            "id": f"gap_{idx + 1}",
            "type": "sticky_note",
            "text": f"{gap.gap_type}: {gap.description}",
            "confidence": gap.confidence,
        }
        for idx, gap in enumerate(supply_report.gaps[:4])
    ]
    unmet_nodes = [
        {
            "id": f"ask_{idx + 1}",
            "type": "audience_ask",
            "text": cluster.theme,
            "frequency": cluster.frequency,
        }
        for idx, cluster in enumerate([c for c in unmet_asks if c.unmet_ask][:4])
    ]

    nodes = [
        {"id": center_id, "type": "thesis", "text": thesis.statement, "lens": thesis.lens},
        *point_nodes,
        *sticky_nodes,
        *unmet_nodes,
    ]
    edges = [
        {"from": center_id, "to": node["id"], "label": "supports"}
        for node in point_nodes
    ] + [
        {"from": node["id"], "to": center_id, "label": "opportunity"}
        for node in sticky_nodes + unmet_nodes
    ]

    return {
        "product": "ladderbrief",
        "format": "canvas_outline",
        "nodes": nodes,
        "edges": edges,
        "rejected_angles": [
            {"lens": item.lens, "reason": item.rejection_reason or ""}
            for item in rejected_candidates
        ],
    }
