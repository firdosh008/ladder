"""Agents for the Scene crew (PRD §5.5 / §11.4).

Only one CrewAI agent now: the layout planner. The element designer used to
be a CrewAI agent with `output_pydantic=SceneSkeleton`, but that path
relies on prompted JSON which dropped the top-level `elements` array on a
large fraction of runs. The designer is now a direct Anthropic call with
grammar-constrained structured outputs — see `app/agents/scene/designer.py`.

Founder context (positioning / voice / brand) is interpolated into every
backstory — PRD §11 cardinal rule: no hardcoded user identifiers.
"""

from __future__ import annotations

from crewai import Agent

from app.models.db import IdeaSlice, UserProfileSlice
from app.services.llm import anthropic_llm


def _profile_context(profile: UserProfileSlice) -> str:
    parts = [
        f"Founder: {profile.display_name or 'unknown'}",
        f"Positioning: {profile.positioning or 'not specified'}",
        f"Audience: {profile.audience or 'not specified'}",
    ]
    if profile.things_to_avoid:
        parts.append(f"Things to avoid: {profile.things_to_avoid}")
    return "\n".join(parts)


def _idea_context(idea: IdeaSlice) -> str:
    parts = [f"Title: {idea.title}"]
    if idea.idea_type:
        parts.append(f"Idea type: {idea.idea_type}")
    if idea.rationale:
        parts.append(f"Rationale: {idea.rationale}")
    return "\n".join(parts)


def build_agents(
    profile: UserProfileSlice,
    idea: IdeaSlice,
) -> dict[str, Agent]:
    # Lower temperature than studio: scene generation is structural, not
    # creative. We want determinism on coordinates + label exactness.
    llm = anthropic_llm(temperature=0.25)

    profile_ctx = _profile_context(profile)
    idea_ctx = _idea_context(idea)

    layout_planner = Agent(
        role="Layout planner",
        goal=(
            "Translate a numbered video outline into a spatial layout for an "
            "Excalidraw scene. Decide the canvas size, the flow direction, "
            "and one rectangular region per outline frame so the founder can "
            "walk through the diagram on screen without zooming or "
            "scrolling around."
        ),
        backstory=(
            "You think in flowcharts. You allocate generous spacing, never "
            "let regions overlap, and you bias toward top-to-bottom flow for "
            "anything longer than 4 frames (it scrolls naturally on a Loom "
            "recording). You scale the canvas to fit the content rather than "
            "forcing content into a fixed canvas.\n\n"
            "Founder context:\n" + profile_ctx + "\n\n"
            "Video idea:\n" + idea_ctx
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=3,
    )

    return {"layout_planner": layout_planner}
