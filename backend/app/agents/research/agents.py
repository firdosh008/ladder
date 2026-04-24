"""Agent definitions for the Research crew.

Three roles, sequential handoff:

  search_agent    → gathers raw web signal via ExaSearchTool
  trend_scorer    → scores outlier / opportunity potential (LLM only)
  idea_formulator → converts scored signal into 3-5 shaped idea drafts
                    anchored in the user's positioning + audience + voice.
"""

from __future__ import annotations

from crewai import Agent

from app.agents.research.tools import ExaSearchTool
from app.models.db import UserProfileSlice
from app.services.llm import anthropic_llm


def _profile_context(profile: UserProfileSlice) -> str:
    """Short prose block every agent sees so drafts stay on-brand."""
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
    llm = anthropic_llm(temperature=0.4)
    context = _profile_context(profile)

    search_agent = Agent(
        role="Trend researcher",
        goal=(
            "Surface 8-12 fresh, specific signals about the user's research "
            "topic from the public web."
        ),
        backstory=(
            "You are an obsessive trend-watcher with taste for outlier "
            "signals. You always prefer concrete, recent, and unusual "
            "findings over generic overviews.\n\n"
            "Context about the founder whose research you are serving:\n"
            + context
        ),
        tools=[ExaSearchTool()],
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=6,
    )

    trend_scorer = Agent(
        role="Outlier scorer",
        goal=(
            "Score each signal from 0-100 for outlier potential — how "
            "counter-intuitive, specific, and useful it would be for a "
            "founder-operator's content."
        ),
        backstory=(
            "You are a sceptical editor who rejects filler. You reward "
            "signals that are specific, non-obvious, and tied to a founder "
            "decision or tactic. You reject listicles, platitudes, and "
            "recycled LinkedIn takes.\n\n"
            "Context:\n" + context
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=3,
    )

    idea_formulator = Agent(
        role="Idea architect",
        goal=(
            "Transform the highest-scoring signals into 3-5 distinct, "
            "founder-voice video ideas — each with a title, opportunity "
            "score, and rationale."
        ),
        backstory=(
            "You turn trend signals into specific, punchy video ideas that "
            "a founder-operator would actually record. Every idea sounds "
            "like it came from THEIR voice, targets THEIR audience, and "
            "respects what they've said to avoid.\n\n"
            "Context:\n" + context
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=3,
    )

    return {
        "search_agent": search_agent,
        "trend_scorer": trend_scorer,
        "idea_formulator": idea_formulator,
    }
