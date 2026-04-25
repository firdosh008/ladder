"""Agents for the Scene crew (PRD §5.5 / §11.4).

Two roles, sequential handoff:

  layout_planner   → produces SceneLayout: canvas, flow, per-frame regions.
  element_designer → produces SceneSkeleton (Excalidraw element list) — this
                     is what the user sees; no critic pass.

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

    element_designer = Agent(
        role="Element designer",
        goal=(
            "Inside each layout frame, draw the right Excalidraw primitives "
            "for that frame's kind (flow, table, decision, architecture, "
            "checklist, title, cta, diagram). Connect frames with arrows "
            "that bind to element ids. You MUST return a full SceneSkeleton "
            "JSON with a non-empty `elements` array (minimum 2 items). "
            "Use the Ladder palette: Cinnabar #E8442A for accents, near-white "
            "#F5F5F5 for strokes/text on the dark canvas, no fills unless the "
            "frame is a title or CTA card."
        ),
        backstory=(
            "You produce ExcalidrawElementSkeleton JSON. You assign every "
            "element a stable string id ('f1-box', 'f2-diamond', 'arrow-1') "
            "so arrows can bind by id. Text labels on shapes match the "
            "outline frame label EXACTLY — that's how screenshot-to-edit "
            "later finds them. You use roughness=1 (hand-drawn) and "
            "strokeWidth=2 unless a frame demands emphasis. You never "
            "overlap regions: shapes stay inside their frame's bounding "
            "box with at least 24px internal padding. Never omit the top-level "
            "`elements` key — the app validates your output and will fail if "
            "it is missing.\n\n"
            "Founder context:\n" + profile_ctx + "\n\n"
            "Video idea:\n" + idea_ctx
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=4,
    )

    return {
        "layout_planner": layout_planner,
        "element_designer": element_designer,
    }
