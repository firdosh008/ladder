"""Layer 5: Synthesis — 4-lens thesis generation + moderator. The product moat."""

from __future__ import annotations

import asyncio
import json
import logging

from research_agent.graph import ResearchState
from research_agent.models import AgentEvent, Thesis, CostBreakdown
from research_agent.tools.embeddings import top_k_by_relevance
from research_agent.tools.llm import llm_call
from research_agent.config import settings

logger = logging.getLogger(__name__)

# The four strategic lenses
LENSES = [
    {
        "name": "strategy",
        "label": "Strategy Lens",
        "prompt": "What's the macro-narrative — the framing that recasts the topic in a way nobody else is seeing?",
        "system": """You are a strategic content analyst. Your job is to find the BIG narrative frame.
Don't think about tactics — think about the story arc. What's the paradigm shift? What's the reframing that makes people say 'I never thought of it that way'?
Your thesis should be ONE provocative sentence that reframes the entire conversation.""",
    },
    {
        "name": "signal",
        "label": "Signal Lens",
        "prompt": "What's the leading indicator nobody else has noticed yet — the signal in the noise?",
        "system": """You are a signal detection analyst. Your job is to find what's NEXT.
Look at early-stage data, emerging patterns, contrarian indicators. What's the thing that will be obvious in 6 months but nobody's talking about now?
Your thesis should be ONE sentence about a specific, verifiable leading indicator.""",
    },
    {
        "name": "execution",
        "label": "Execution Lens",
        "prompt": "What's the operator-level 'how to actually do this' that nobody has explained well?",
        "system": """You are a practitioner and operator. Your job is to find the IMPLEMENTATION gap.
Everyone talks about the 'what' and 'why'. You care about the 'how' — the specific, actionable, step-by-step approach that actually works in practice.
Your thesis should be ONE sentence about a specific execution approach that's been overlooked.""",
    },
    {
        "name": "contrarian",
        "label": "Contrarian Lens",
        "prompt": "What's the dominant view, and why is it wrong?",
        "system": """You are a contrarian analyst. Your job is to find where the CONSENSUS IS WRONG.
Not contrarian for the sake of it — find the specific, defensible argument for why the majority view is incomplete, outdated, or based on flawed assumptions.
Your thesis should be ONE sentence that challenges the dominant narrative with evidence.""",
    },
]


async def synthesis_node(state: ResearchState) -> dict:
    """Layer 5: Run 4 perspective agents in parallel, then moderator picks winner.
    STORM-inspired: perspectives produce candidates, moderator picks."""

    events = [AgentEvent(event="layer_start", layer="synthesis", message="Generating thesis candidates from 4 lenses").to_dict()]
    cost = state.get("cost", CostBreakdown())
    query = state["query"]

    if state.get("topic_passed") is False:
        reason = state.get("rejection_reason") or "Topic did not pass scoring gates."
        events.append(AgentEvent(
            event="layer_complete",
            layer="synthesis",
            message=f"Synthesis skipped: {reason}",
        ).to_dict())
        return {
            "candidate_theses": [],
            "winning_thesis": None,
            "rejected_theses": [],
            "events": events,
            "cost": cost,
        }

    config = state.get("config")
    if config and cost.total >= config.cost_ceiling:
        reason = f"Cost ceiling reached before synthesis: ${cost.total:.4f} >= ${config.cost_ceiling:.4f}."
        events.append(AgentEvent(
            event="layer_complete",
            layer="synthesis",
            message=f"Synthesis skipped: {reason}",
        ).to_dict())
        return {
            "candidate_theses": [],
            "winning_thesis": None,
            "rejected_theses": [],
            "rejection_reason": reason,
            "events": events,
            "cost": cost,
        }

    # Build context from all gathered data
    sources = state.get("sources", [])
    supply = state.get("supply_report")
    clusters = state.get("comment_clusters", [])
    user_ctx = state.get("user_context", {})

    # Prepare a condensed briefing for each lens agent
    ranked_sources = sorted(sources, key=lambda x: x.relevance_score or 0.0, reverse=True)
    source_lines = [
        f"- [{s.platform}] {s.title} (relevance: {(s.relevance_score or 0.0):.2f})"
        for s in ranked_sources
    ]
    if len(source_lines) > 20:
        try:
            top_indices = await top_k_by_relevance(source_lines, query, k=20)
            source_lines = [source_lines[idx] for idx, _ in top_indices]
        except Exception as e:
            logger.warning(f"Embedding pre-filter failed; falling back to relevance sort: {e}")
            source_lines = source_lines[:20]
    source_summary = "\n".join(source_lines[:20])

    supply_summary = ""
    if supply:
        gap_text = "\n".join(f"  - {g.gap_type}: {g.description} (confidence: {g.confidence:.1f})" for g in supply.gaps)
        supply_summary = f"Supply saturation: {supply.overall_saturation:.1f}\nGaps found:\n{gap_text}" if supply.gaps else f"Supply saturation: {supply.overall_saturation:.1f}, no significant gaps"

    unmet_summary = ""
    if clusters:
        unmet = [c for c in clusters if c.unmet_ask]
        if unmet:
            unmet_summary = "Unmet audience asks:\n" + "\n".join(f"  - {c.theme} ({c.frequency} comments)" for c in unmet)

    briefing = f"""TOPIC: {query}

TOP SOURCES ({len(sources)} total):
{source_summary}

SUPPLY-SIDE:
{supply_summary}

{unmet_summary}

CREATOR CONTEXT:
{json.dumps(user_ctx, indent=2)}

Topic score: {state.get('topic_score', 0):.3f}
Platforms with signal: {len(set(s.platform for s in sources))}"""

    # Run 4 lens agents in parallel
    async def run_lens(lens: dict) -> Thesis:
        events.append(AgentEvent(event="agent_start", layer="synthesis", agent=lens["label"],
                                 message=f"Generating {lens['name']} thesis").to_dict())
        try:
            prompt = f"""{lens['prompt']}

Here is all the research data:
{briefing}

Respond in EXACTLY this format:
THESIS: [one sentence thesis statement]
POINT_1: [supporting point with specific evidence]
POINT_2: [supporting point with specific evidence]
POINT_3: [supporting point with specific evidence]
RATIONALE: [why make THIS content, because the existing top content misses what]"""

            response = await llm_call(
                prompt=prompt,
                system=lens["system"],
                model=settings.synthesis_model,
                temperature=0.8,
                max_tokens=800,
                cost_tracker=cost,
                cost_layer="synthesis",
            )

            # Parse response
            thesis = Thesis(lens=lens["name"])
            points = []
            for line in response.strip().split("\n"):
                line = line.strip()
                if line.startswith("THESIS:"):
                    thesis.statement = line[7:].strip()
                elif line.startswith("POINT_"):
                    points.append(line.split(":", 1)[1].strip() if ":" in line else line)
                elif line.startswith("RATIONALE:"):
                    thesis.supply_side_rationale = line[10:].strip()

            thesis.supporting_points = points
            events.append(AgentEvent(event="agent_complete", layer="synthesis", agent=lens["label"],
                                     message=f"Generated: {thesis.statement[:80]}...").to_dict())
            return thesis

        except Exception as e:
            logger.error(f"Lens {lens['name']} failed: {e}")
            events.append(AgentEvent(event="agent_error", layer="synthesis", agent=lens["label"], message=str(e)).to_dict())
            return Thesis(lens=lens["name"], statement=f"[Failed: {str(e)[:100]}]")

    # Parallel execution
    candidates = await asyncio.gather(*[run_lens(lens) for lens in LENSES])

    # Moderator: score and pick winner
    events.append(AgentEvent(event="agent_start", layer="synthesis", agent="Moderator",
                             message="Scoring and selecting winning thesis").to_dict())

    candidates_text = "\n\n".join(
        f"[{c.lens.upper()}] {c.statement}\nPoints: {'; '.join(c.supporting_points)}\nRationale: {c.supply_side_rationale}"
        for c in candidates if c.statement and not c.statement.startswith("[Failed")
    )

    moderator_prompt = f"""You are a content strategy moderator. Score these 4 thesis candidates for the topic "{query}".

{candidates_text}

Score each on 4 dimensions (1-10):
- Defendability: Can this be argued with evidence?
- Novelty: Has this NOT been said before?
- Creator fit: Does this match someone starting from zero?
- Supply gap: Does this fill a gap in existing content?

For each candidate, compute: score = defendability × novelty × creator_fit × supply_gap (out of 10000)

Respond in this EXACT format:
WINNER: [strategy/signal/execution/contrarian]
SCORES:
strategy: [total_score] | [rejection_reason if not winner]
signal: [total_score] | [rejection_reason if not winner]
execution: [total_score] | [rejection_reason if not winner]
contrarian: [total_score] | [rejection_reason if not winner]"""

    try:
        mod_response = await llm_call(
            prompt=moderator_prompt,
            system="You are an objective content strategy evaluator. Be brutally honest in scoring. The bar is 'would I publicly argue this?'",
            model=settings.synthesis_model,
            temperature=0.3,
            max_tokens=500,
            cost_tracker=cost,
            cost_layer="synthesis",
        )

        # Parse moderator response
        winner_lens = "strategy"
        scores = {}
        for line in mod_response.strip().split("\n"):
            line = line.strip()
            if line.startswith("WINNER:"):
                winner_lens = line[7:].strip().lower()
            elif "|" in line:
                for lens_name in ["strategy", "signal", "execution", "contrarian"]:
                    if line.lower().startswith(lens_name):
                        parts = line.split("|")
                        score_part = parts[0].split(":")[-1].strip()
                        reason = parts[1].strip() if len(parts) > 1 else ""
                        try:
                            scores[lens_name] = (float(score_part), reason)
                        except ValueError:
                            scores[lens_name] = (0, reason)

        # Assign scores and rejection reasons
        winning = None
        rejected = []
        for c in candidates:
            if c.lens in scores:
                c.score = scores[c.lens][0]
                if c.lens != winner_lens:
                    c.rejection_reason = scores[c.lens][1]

            if c.lens == winner_lens:
                winning = c
            else:
                rejected.append(c)

        if not winning:
            winning = candidates[0]  # Fallback
            rejected = list(candidates[1:])

    except Exception as e:
        logger.error(f"Moderator failed: {e}")
        winning = candidates[0]
        rejected = list(candidates[1:])
        for r in rejected:
            r.rejection_reason = "Moderator evaluation failed — defaulted to first candidate"

    events.append(AgentEvent(event="agent_complete", layer="synthesis", agent="Moderator",
                             message=f"Winner: {winning.lens} — {winning.statement[:80]}...").to_dict())
    events.append(AgentEvent(event="layer_complete", layer="synthesis",
                             message=f"Thesis synthesis complete — {winning.lens} lens wins").to_dict())

    return {
        "candidate_theses": list(candidates),
        "winning_thesis": winning,
        "rejected_theses": rejected,
        "events": events,
        "cost": cost,
    }
