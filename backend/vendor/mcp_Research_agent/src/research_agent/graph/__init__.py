"""LangGraph shared state — flows through all nodes in the research pipeline."""

from __future__ import annotations

from typing import Annotated, TypedDict
from langgraph.graph import add_messages

from research_agent.knowledge_graph import CreatorKG
from research_agent.models import (
    SourceRef, CommentCluster, SupplySideReport,
    Thesis, CostBreakdown, ResearchResult, ResearchConfig,
)


def merge_lists(a: list, b: list) -> list:
    """Reducer: merge two lists."""
    return a + b


def merge_dicts(a: dict, b: dict) -> dict:
    """Reducer: merge two dicts."""
    return {**a, **b}


class ResearchState(TypedDict, total=False):
    """Shared state that flows through the LangGraph research pipeline."""

    # --- Input ---
    query: str
    input_type: str
    user_id: str
    context: dict
    output_mode: str
    product: str
    run_id: str
    config: ResearchConfig
    knowledge_graph: CreatorKG

    # --- Layer 1: Demand-side sources ---
    sources: Annotated[list[SourceRef], merge_lists]
    comments_raw: Annotated[list[dict], merge_lists]

    # --- Layer 1b: Comment mining ---
    comment_clusters: list[CommentCluster]

    # --- Layer 2: Supply-side ---
    supply_report: SupplySideReport

    # --- Layer 3: KG context ---
    user_context: dict
    kg_gap: float
    kg_saturation: float

    # --- Layer 4: Scoring ---
    topic_score: float
    score_breakdown: dict
    topic_passed: bool
    rejection_reason: str

    # --- Layer 5: Synthesis ---
    candidate_theses: list[Thesis]
    winning_thesis: Thesis
    rejected_theses: list[Thesis]

    # --- Layer 6: Verification ---
    verified: bool
    verification_notes: list[dict]

    # --- Cost ---
    cost: CostBreakdown

    # --- Events (for WebSocket streaming) ---
    events: Annotated[list[dict], merge_lists]

    # --- Final ---
    result: ResearchResult
    error: str
