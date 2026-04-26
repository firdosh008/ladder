"""Task definitions for the Research crew. Sequential pipeline:
search → score → formulate."""

from __future__ import annotations

from crewai import Agent, Task

from app.models.db import ResearchIdeas


def build_tasks(
    topic: str,
    agents: dict[str, Agent],
) -> list[Task]:
    search_task = Task(
        description=(
            f"Research this topic across the web AND social platforms: "
            f"'{topic}'.\n\n"
            "Cast a wide net using ALL FIVE tools. Aim for at least:\n"
            "  • 2 `web_search` queries on different angles (tactics, "
            "contrarian takes, recent shifts)\n"
            "  • 1-2 `reddit_trending` calls on subreddits where the "
            "founder's audience actually hangs out (derive these from their "
            "audience + positioning — not generic 'Entrepreneur' or 'CEO' "
            "subs unless those genuinely fit). Use sort='hot' or "
            "sort='top' with timeframe='week'. Subreddit names are "
            "case-sensitive — use canonical capitalisation.\n"
            "  • 1 `youtube_trending` call with sort_by='popular' and "
            "upload_date='this_week' or 'this_month'\n"
            "  • 1 `x_user_tweets` call on a relevant founder/builder "
            "handle (derive from creators_followed in the founder's "
            "context if any are listed; otherwise pick a credible "
            "operator in the topic's space)\n"
            "  • 1 `instagram_reels` call with date_posted='last-week' "
            "to surface short-form video angles\n\n"
            "Aggregate until you have 12-18 specific, recent, non-generic "
            "signals across platforms. Skip SEO listicles, vendor blogs, "
            "and low-engagement community posts (Reddit score <10).\n\n"
            "Output: a bulleted list. For each signal give:\n"
            "  • title (verbatim from the source)\n"
            "  • full url (verbatim — no markdown link syntax)\n"
            "  • platform: web | reddit | youtube | x | instagram\n"
            "  • why-this-matters: 1-2 sentences (25-60 words) naming what "
            "is specific or counter-intuitive about it."
        ),
        expected_output=(
            "Markdown bulleted list of 12-18 signals drawn from at least "
            "3 distinct platforms. Each bullet contains title, raw URL, "
            "platform tag, and a 25-60 word 'why this matters' note."
        ),
        agent=agents["search_agent"],
    )

    score_task = Task(
        description=(
            "Review every signal from the previous task. For each, assign "
            "an opportunity_score between 0 and 100 reflecting outlier "
            "potential for a founder-operator's video content. Reject "
            "generic or recycled takes (score <30). Reward specific, "
            "decision-level tactics (score >70). Preserve the URL verbatim "
            "so downstream agents can cite it.\n\n"
            "Group-reason briefly: identify the 2-3 distinct narrative "
            "threads that emerge from the highest-scoring signals, because "
            "the next agent will build ideas along those threads."
        ),
        expected_output=(
            "Markdown table with columns: signal_title | url | score | "
            "reasoning (1 sentence). Sorted score desc. Followed by a short "
            "'Narrative threads' section listing the 2-3 angles with a "
            "one-line description each."
        ),
        agent=agents["trend_scorer"],
        context=[search_task],
    )

    formulate_task = Task(
        description=(
            "Using the highest-scoring signals (score >=60) and the "
            "narrative threads, draft 4-6 distinct video ideas the founder "
            "could actually record in their own voice. Each idea must be "
            "specific enough that two different founders would produce "
            "two different videos from it.\n\n"
            "For each idea produce:\n"
            "  - title: 6-12 words, concrete, voice-matched. No clickbait. "
            "No 'The Ultimate Guide' / 'X Things You' template phrasing.\n"
            "  - rationale: 2-3 sentences (50-100 words) that (a) name the "
            "trigger signal, (b) explain why this angle is sharp for THIS "
            "founder's positioning and audience, and (c) hint at the "
            "opening beat.\n"
            "  - idea_type: one of systems, framework, pitch, case_study.\n"
            "  - opportunity_score: 0-100 integer — anchor to the source "
            "signal's score; 60-79 = solid, 80+ = sharp outlier potential.\n"
            "  - outlier_score: 0-10 float — how counter-intuitive or "
            "against-the-grain the angle is for this audience. Reserve 8+ "
            "for takes that directly contradict consensus.\n"
            "  - why_now: one sentence (<=220 chars) on the current market "
            "reason this topic is sharp THIS week. Must cite a concrete "
            "trigger from the signals.\n"
            "  - suggested_tags: 2-4 lowercase topic tags (single words or "
            "hyphenated), useful for the user's knowledge graph.\n\n"
            "Return strict JSON that matches the IdeaDraft schema. Ideas "
            "must be a list of 4-6 objects. Do NOT wrap in markdown fences. "
            "Do NOT include a `body` field."
        ),
        expected_output=(
            "JSON object with key `ideas`, a list of 4-6 drafts matching "
            "the IdeaDraft schema (title, rationale, idea_type, "
            "opportunity_score, outlier_score, why_now, suggested_tags)."
        ),
        agent=agents["idea_formulator"],
        context=[search_task, score_task],
        output_pydantic=ResearchIdeas,
    )

    return [search_task, score_task, formulate_task]
