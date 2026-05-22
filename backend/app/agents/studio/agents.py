"""Agent definitions for the Studio crew (PRD §5).

Two roles, sequential handoff:

  script_writer    → writes section-by-section talking points + transitions
                     in the founder's voice, anchored to their positioning
                     and audience.
  outline_planner  → reads the finished script and produces a numbered
                     scene outline (the user-facing TOC + beats).
"""

from __future__ import annotations

from crewai import Agent

from app.models.db import IdeaSlice, UserProfileSlice
from app.services.llm import anthropic_llm


def _profile_context(profile: UserProfileSlice) -> str:
    parts = [
        f"Founder name: {profile.display_name or 'unknown'}",
        f"Positioning: {profile.positioning or 'not specified'}",
        f"Audience: {profile.audience or 'not specified'}",
        f"Voice: {profile.voice or 'not specified'}",
    ]
    if profile.creators_followed:
        parts.append(
            "Creators they admire: " + ", ".join(profile.creators_followed)
        )
    if profile.things_to_avoid:
        parts.append(f"Things to avoid: {profile.things_to_avoid}")
    return "\n".join(parts)


def _idea_context(idea: IdeaSlice) -> str:
    parts = [f"Title: {idea.title}"]
    if idea.idea_type:
        parts.append(f"Type: {idea.idea_type}")
    if idea.opportunity_score is not None:
        parts.append(f"Opportunity score: {idea.opportunity_score}/100")
    if idea.rationale:
        parts.append(f"Rationale: {idea.rationale}")
    if idea.body:
        parts.append(f"Founder's notes:\n{idea.body}")
    if idea.source_content:
        label = "Pasted source" if idea.source_type == "content_extract" else "Source / topic"
        parts.append(f"{label}:\n{idea.source_content}")
    return "\n".join(parts)


def build_agents(
    profile: UserProfileSlice,
    idea: IdeaSlice,
) -> dict[str, Agent]:
    llm = anthropic_llm(temperature=0.55)
    profile_ctx = _profile_context(profile)
    idea_ctx = _idea_context(idea)

    script_writer = Agent(
        role="Script writer",
        goal=(
            "Draft a section-by-section script for this video — talking "
            "points and transitions, NOT word-for-word copy. Keep the "
            "founder's voice consistent across sections."
        ),
        backstory=(
            "You write scripts the founder will actually record in their "
            "own voice. You write talking points, never paragraphs to be "
            "read verbatim. You think in scenes: each section earns its "
            "place, ends with a transition that hands off to the next, and "
            "stays specific. You never use the word 'Ultimate'. You never "
            "begin a video with 'Hi everyone'.\n\n"
            "Founder context:\n" + profile_ctx + "\n\n"
            "Video idea:\n" + idea_ctx
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=4,
    )

    outline_planner = Agent(
        role="Outline planner",
        goal=(
            "Translate the finished script into a numbered scene outline — "
            "one row per section with a short label and a 1-2 sentence "
            "beat description. This is the table-of-contents the founder "
            "will approve before scenes are built."
        ),
        backstory=(
            "You compress scripts into outlines. You preserve the order of "
            "sections, you use punchy labels, and your beats describe what "
            "the viewer experiences (not what the script says).\n\n"
            "Founder context:\n" + profile_ctx + "\n\n"
            "Video idea:\n" + idea_ctx
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=3,
    )

    return {"script_writer": script_writer, "outline_planner": outline_planner}
