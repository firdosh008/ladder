"""The main LangGraph orchestrator — wires all 6 layers into a single graph."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from langgraph.graph import StateGraph, START, END

from research_agent.adapters import adapt_research_output
from research_agent.graph import ResearchState
from research_agent.graph.demand import demand_side_node
from research_agent.graph.analysis import (
    comment_mining_node,
    supply_side_node,
    kg_filter_node,
    scoring_node,
)
from research_agent.graph.synthesis import synthesis_node
from research_agent.graph.verification import verification_node
from research_agent.models import (
    ResearchInput, ResearchConfig, ResearchResult, CostBreakdown, AgentEvent, SupplySideReport,
)
from research_agent.knowledge_graph import CreatorKG, SimpleKG

logger = logging.getLogger(__name__)


def _build_result(state: ResearchState) -> dict:
    """Final node: assemble the ResearchResult from all state."""
    cost = state.get("cost", CostBreakdown())

    result = ResearchResult(
        winning_thesis=state.get("winning_thesis"),
        rejected_candidates=state.get("rejected_theses", []),
        sources=state.get("sources", []),
        supply_side_report=state.get("supply_report") or SupplySideReport(),
        unmet_asks=state.get("comment_clusters", []),
        cost_breakdown=cost,
        score_breakdown=state.get("score_breakdown", {}),
        verification_notes=state.get("verification_notes", []),
        adapted_output=adapt_research_output(
            state.get("output_mode") or state.get("product", "research_report"),
            state.get("winning_thesis"),
            state.get("rejected_theses", []),
            state.get("supply_report") or SupplySideReport(),
            state.get("comment_clusters", []),
        ),
        raw_data={
            "comments_raw": state.get("comments_raw", []),
            "events": state.get("events", []),
        },
        run_id=state.get("run_id", ""),
        completed_at=datetime.now(UTC).isoformat(),
        status="rejected" if state.get("rejection_reason") else "complete",
        rejection_reason=state.get("rejection_reason"),
    )

    events = [AgentEvent(event="result", layer="output", message="Research complete",
                         data={"total_cost": cost.total, "sources_count": len(result.sources)}).to_dict()]

    return {"result": result, "events": events}


def build_research_graph() -> StateGraph:
    """Construct the full research pipeline as a LangGraph StateGraph.

    Pipeline:
        START → demand_side → comment_mining → supply_side → kg_filter → scoring → synthesis → verification → build_result → END
    
    The demand_side node runs 5 agents in parallel internally.
    The synthesis node runs 4 lens agents in parallel internally.
    """
    graph = StateGraph(ResearchState)

    # Add nodes
    graph.add_node("demand_side", demand_side_node)
    graph.add_node("comment_mining", comment_mining_node)
    graph.add_node("supply_side", supply_side_node)
    graph.add_node("kg_filter", kg_filter_node)
    graph.add_node("scoring", scoring_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("verification", verification_node)
    graph.add_node("build_result", _build_result)

    # Wire edges (sequential pipeline — parallelism happens INSIDE nodes)
    graph.add_edge(START, "demand_side")
    graph.add_edge("demand_side", "comment_mining")
    graph.add_edge("comment_mining", "supply_side")
    graph.add_edge("supply_side", "kg_filter")
    graph.add_edge("kg_filter", "scoring")
    graph.add_edge("scoring", "synthesis")
    graph.add_edge("synthesis", "verification")
    graph.add_edge("verification", "build_result")
    graph.add_edge("build_result", END)

    return graph


# Compiled graph singleton
research_graph = build_research_graph().compile()


async def run_research(
    input: ResearchInput | str | None = None,
    knowledge_graph: CreatorKG | None = None,
    config: ResearchConfig | None = None,
    context: dict | None = None,
    query: str | None = None,
    input_type: str = "freeform",
    user_id: str = "default",
    output_mode: str = "research_report",
    product: str = "research_report",
    run_id: str | None = None,
    event_callback=None,
) -> ResearchResult:
    """Execute the full research pipeline.
    
    Args:
        input: ResearchInput or a plain string for compatibility
        query: Compatibility shortcut for callers that still pass a plain query
        user_id: Creator's user ID for KG lookup
        context: Caller-provided audience/project context for standalone runs
        output_mode: research_report by default; legacy adapter modes can be requested explicitly
        knowledge_graph: Product-specific CreatorKG implementation
        config: Per-run limits and platform/lens preferences
        run_id: Optional run ID (generated if not provided)
        event_callback: Optional async callback for real-time events
    
    Returns:
        ResearchResult with winning thesis, sources, supply analysis, etc.
    """
    import uuid

    if isinstance(input, ResearchInput):
        research_input = input
    else:
        research_input = ResearchInput(
            query=input or query or "",
            input_type=input_type,
            user_id=user_id,
            context=context or {},
            output_mode=output_mode,
            product=product,
        )

    if not research_input.query.strip():
        return ResearchResult(
            run_id=run_id or str(uuid.uuid4()),
            status="error",
            error="Research query is required",
        )

    config = config or ResearchConfig()
    context = context if context is not None else getattr(research_input, "context", None)
    knowledge_graph = knowledge_graph or (SimpleKG({research_input.user_id or user_id: context}) if context else SimpleKG())
    user_id = research_input.user_id or user_id
    output_mode = research_input.output_mode or output_mode or research_input.product or product
    product = output_mode
    run_id = run_id or str(uuid.uuid4())
    start_time = time.time()

    initial_state: ResearchState = {
        "query": research_input.query,
        "input_type": research_input.input_type,
        "user_id": user_id,
        "context": context or {},
        "output_mode": output_mode,
        "product": product,
        "run_id": run_id,
        "config": config,
        "knowledge_graph": knowledge_graph,
        "sources": [],
        "comments_raw": [],
        "events": [],
        "cost": CostBreakdown(run_id=run_id),
    }

    logger.info(f"Starting research run {run_id} for query: '{research_input.query}'")

    # Stream through the graph
    final_state = None
    async for event in research_graph.astream(initial_state, stream_mode="updates"):
        for node_name, node_output in event.items():
            # Forward events to WebSocket
            if event_callback and "events" in node_output:
                for evt in node_output["events"]:
                    await event_callback(evt)
            final_state = node_output

    # Extract result
    if final_state and "result" in final_state:
        result = final_state["result"]
    else:
        # Build result from last known state
        result = ResearchResult(
            run_id=run_id,
            status="error",
            error="Pipeline did not complete",
        )

    result.cost_breakdown.duration_seconds = round(time.time() - start_time, 2)
    logger.info(f"Research run {run_id} complete in {result.cost_breakdown.duration_seconds}s, cost: ${result.cost_breakdown.total:.2f}")
    return result
