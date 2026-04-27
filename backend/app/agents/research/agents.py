"""Agent definitions for the Research crew.

Three roles, sequential handoff:

  search_agent    → gathers raw web signal via ExaSearchTool
  trend_scorer    → scores outlier / opportunity potential (LLM only)
  idea_formulator → converts scored signal into 3-5 shaped idea drafts
                    anchored in the user's positioning + audience + voice.
"""

from __future__ import annotations

from datetime import datetime, timezone

from crewai import Agent

from app.agents.research.tools import (
    ExaSearchTool,
    InstagramReelsTool,
    RedditSearchTool,
    RedditTrendsTool,
    XUserTweetsTool,
    YouTubeTrendsTool,
)
from app.models.db import UserProfileSlice
from app.services.llm import anthropic_llm


def _today_context() -> str:
    """A short prose block telling the agent what 'today' means.

    LLMs default to their training-cutoff sense of 'recent', which is usually
    a year or two stale. We bind today's UTC date into every backstory so the
    search agent phrases queries like 'X 2026' instead of 'X 2024'.
    """
    today = datetime.now(tz=timezone.utc)
    return (
        f"Today's date: {today.strftime('%A, %B %d, %Y')} "
        f"(year {today.year}). When you write search queries, ALWAYS "
        f"include the current year or 'this week' / 'past month' so you "
        f"surface fresh signal rather than 2023/2024 artefacts."
    )


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
    today = _today_context()

    search_agent = Agent(
        role="Trend researcher",
        goal=(
            "Surface 12-18 fresh, specific signals about the user's research "
            "topic — published or posted within the last few weeks — by "
            "fanning out across the public web AND the four social platforms "
            "where founder-relevant signal lives: Reddit, YouTube, X, and "
            "Instagram. Cover multiple angles through at least one query per "
            "platform."
        ),
        backstory=(
            f"{today}\n\n"
            "You are an obsessive multi-platform trend-watcher with taste "
            "for outlier signals. You always prefer concrete, recent, and "
            "unusual findings over generic overviews. You never paraphrase "
            "URLs — you copy them verbatim from the tool output.\n\n"
            "You have six search tools:\n"
            "  • web_search — public web (Exa neural search). Already "
            "filtered to the last 90 days, but you must still phrase "
            "queries with the current year or 'this month' / 'recent' so "
            "the index returns fresh signal.\n"
            "  • reddit_search — cross-Reddit keyword search. ALWAYS call "
            "this BEFORE reddit_trending. It returns a "
            "`discovered_subreddits` list ranked by topic-density — pick "
            "the top 2-3 from THAT list to feed into reddit_trending. Do "
            "NOT guess subreddit names from positioning text; let real "
            "post density tell you where the conversation actually is.\n"
            "  • reddit_trending — posts from a chosen subreddit (use only "
            "after reddit_search has surfaced the right communities).\n"
            "  • youtube_trending — recent videos on a query (use "
            "upload_date='this_week' or 'this_month'). Tool already filters "
            "to >=5k views and ranks by view-velocity.\n"
            "  • x_user_tweets — top tweets from a chosen X handle. Call "
            "this for 2-3 DIFFERENT handles per topic so coverage is "
            "multi-creator. Prefer handles from the founder's "
            "creators_followed list when present; else pick credible "
            "operators in the topic's space.\n"
            "  • instagram_reels — short-form video trend on a query "
            "(use date_posted='last-week' or 'last-month'). Tool already "
            "filters to >=5k plays.\n\n"
            "Numeric quality gates run inside the tools — by the time a "
            "result reaches you it has cleared engagement / freshness "
            "thresholds. Your job is to pick angles, not to second-guess "
            "the gates.\n\n"
            "Reddit subreddit names ARE case-sensitive — use whatever "
            "casing reddit_search returned (e.g. 'AskReddit' not "
            "'askreddit').\n\n"
            "Context about the founder whose research you are serving:\n"
            + context
        ),
        tools=[
            ExaSearchTool(),
            RedditSearchTool(),
            RedditTrendsTool(),
            YouTubeTrendsTool(),
            XUserTweetsTool(),
            InstagramReelsTool(),
        ],
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=18,
    )

    trend_scorer = Agent(
        role="Outlier scorer",
        goal=(
            "Score each signal from 0-100 for outlier potential — how "
            "counter-intuitive, specific, and useful it would be for a "
            "founder-operator's content."
        ),
        backstory=(
            f"{today}\n\n"
            "You are a sceptical editor who rejects filler. You reward "
            "signals that are specific, non-obvious, and tied to a founder "
            "decision or tactic. You reject listicles, platitudes, and "
            "recycled LinkedIn takes. Heavily prefer signals that are from "
            "the current calendar year — older signals must clear a higher "
            "bar.\n\n"
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
            f"{today}\n\n"
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
