"""Agent definitions for the content_extract crew (PRD §2 Option 3 / §11.11).

Two roles, sequential handoff:

  analyzer   → reads pasted source, decides title / type / duration / beats
  extractor  → expands the analysis into a full Script + Outline that the
               studio can hydrate immediately.
"""

from __future__ import annotations

from crewai import Agent

from app.models.db import UserProfileSlice
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


def build_agents(profile: UserProfileSlice) -> dict[str, Agent]:
    llm = anthropic_llm(temperature=0.5)
    profile_ctx = _profile_context(profile)

    analyzer = Agent(
        role="Source analyzer",
        goal=(
            "Decide what video this pasted source could become. Pick a "
            "title, an idea type, a realistic runtime, and the 4-8 key "
            "beats the script must hit."
        ),
        backstory=(
            "You read long-form posts, threads, and newsletters and you "
            "spot the video idea hiding inside them. You don't summarise "
            "the source — you imagine the video the founder would record "
            "if this source was their starting point.\n\n"
            "Founder context:\n" + profile_ctx
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=3,
    )

    extractor = Agent(
        role="Source extractor",
        goal=(
            "Expand the analysis into a full Script (sections + talking "
            "points + transitions) and a numbered Outline. Stay grounded "
            "in the pasted source — never invent facts the source doesn't "
            "support."
        ),
        backstory=(
            "You are a script writer who works from one source at a time. "
            "Every talking point you write traces back to a sentence in "
            "the pasted source OR a clear inference from it. You write "
            "talking points (NOT verbatim narration), in the founder's "
            "voice, and you end every section with a transition.\n\n"
            "Founder context:\n" + profile_ctx
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=4,
    )

    return {"analyzer": analyzer, "extractor": extractor}
