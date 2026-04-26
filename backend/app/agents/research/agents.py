"""Agent definitions for the Research crew.

Three roles, sequential handoff:

  search_agent    → gathers raw web signal via ExaSearchTool
  trend_scorer    → scores outlier / opportunity potential (LLM only)
  idea_formulator → converts scored signal into 3-5 shaped idea drafts
                    anchored in the user's positioning + audience + voice.
"""

from __future__ import annotations

from crewai import Agent

from app.agents.research.tools import (
    ExaSearchTool,
    InstagramReelsTool,
    RedditTrendsTool,
    XUserTweetsTool,
    YouTubeTrendsTool,
)
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
            "Surface 12-18 fresh, specific signals about the user's research "
            "topic by fanning out across the public web AND the three social "
            "platforms where founder-relevant signal lives: Reddit, YouTube, "
            "and X. Cover multiple angles through at least one query per "
            "platform."
        ),
        backstory=(
            "You are an obsessive multi-platform trend-watcher with taste "
            "for outlier signals. You always prefer concrete, recent, and "
            "unusual findings over generic overviews. You never paraphrase "
            "URLs — you copy them verbatim from the tool output.\n\n"
            "You have five search tools:\n"
            "  • web_search — public web (Exa neural search)\n"
            "  • reddit_trending — posts from a chosen subreddit\n"
            "  • youtube_trending — recent videos on a query\n"
            "  • x_user_tweets — top tweets from a chosen X handle\n"
            "  • instagram_reels — short-form video trend on a query\n\n"
            "For each crew run, derive subreddits / handles / video queries "
            "yourself from the topic AND the founder's audience and "
            "positioning. Pick subreddits the audience actually reads and X "
            "handles the audience already follows. Reddit subreddit names "
            "ARE case-sensitive (use 'AskReddit' not 'askreddit').\n\n"
            "Context about the founder whose research you are serving:\n"
            + context
        ),
        tools=[
            ExaSearchTool(),
            RedditTrendsTool(),
            YouTubeTrendsTool(),
            XUserTweetsTool(),
            InstagramReelsTool(),
        ],
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=14,
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
            "Transform the highest-scoring signals into 4-6 distinct, "
            "founder-voice video ideas — each with a title, scores, and a "
            "multi-sentence rationale grounded in specific signals."
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
