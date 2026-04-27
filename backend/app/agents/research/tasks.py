"""Task definitions for the Research crew. Sequential pipeline:
search → score → formulate."""

from __future__ import annotations

from datetime import datetime, timezone

from crewai import Agent, Task

from app.models.db import ResearchIdeas


def build_tasks(
    topic: str,
    agents: dict[str, Agent],
) -> list[Task]:
    today = datetime.now(tz=timezone.utc)
    year = today.year
    today_str = today.strftime("%B %Y")

    search_task = Task(
        description=(
            f"Today is {today_str}. Research this topic across the web AND "
            f"social platforms: '{topic}'.\n\n"
            f"FRESHNESS RULE — every signal must be from {year} or the past "
            "few weeks. Reject anything that smells stale (old papers, "
            f"pre-{year} listicles, evergreen vendor blogs). When you call "
            "web_search, ALWAYS bake the current year or a 'this month' / "
            f"'past 30 days' / '{year}' phrase into the query so the index "
            "returns recent results. Web results are server-side filtered "
            "to the last 90 days but query phrasing still matters.\n\n"
            "REQUIRED TOOL SEQUENCE — follow it in order:\n"
            f"  1. `web_search` — 2 queries on different angles, each "
            f"phrased with '{year}' or 'recent' (tactics, contrarian "
            "takes, recent shifts).\n"
            "  2. `reddit_search` — call ONCE with the topic phrase and "
            "timeframe='week'. Read the `discovered_subreddits` list it "
            "returns. THIS IS HOW YOU FIND THE RIGHT COMMUNITIES — do NOT "
            "guess subreddit names from the founder's positioning.\n"
            "  3. `reddit_trending` — drill into the TOP 2-3 subreddits "
            "from step 2's `discovered_subreddits` list, using sort='top' "
            "timeframe='week'. Use the exact subreddit name casing the "
            "search returned.\n"
            "  4. `youtube_trending` — 1 call with sort_by='popular' and "
            "upload_date='this_week' or 'this_month'. The tool already "
            "drops <5k-view videos and ranks by view-velocity.\n"
            "  5. `x_user_tweets` — call on 2-3 DIFFERENT handles for "
            "multi-creator coverage. Prefer handles from the founder's "
            "creators_followed list (in their context) if any are listed. "
            "Otherwise pick credible operators in the topic's space.\n"
            "  6. `instagram_reels` — 1 call with date_posted='last-week'. "
            "Tool drops <5k-play reels.\n\n"
            "Numeric quality gates already run inside each social tool "
            "(min Reddit score 10, min YouTube views 5k, min IG plays 5k, "
            "min X engagement 30, max age 28-90 days depending on "
            "platform). Don't second-guess them — anything you receive "
            "has already cleared the bar.\n\n"
            "Aggregate until you have 12-18 specific, recent, non-generic "
            "signals across at least 4 distinct platforms. Skip SEO "
            "listicles and vendor blogs.\n\n"
            "Output: a bulleted list. For each signal give:\n"
            "  • title (verbatim from the source)\n"
            "  • full url (verbatim — no markdown link syntax)\n"
            "  • platform: web | reddit | youtube | x | instagram\n"
            "  • engagement: short metric tag — e.g. 'reddit score 142', "
            "'47K views, 3 days', '@handle · 12K likes', 'IG 220K plays'. "
            "Pull these from the tool output verbatim.\n"
            "  • why-this-matters: 1-2 sentences (25-60 words) naming "
            "what is specific or counter-intuitive about it."
        ),
        expected_output=(
            "Markdown bulleted list of 12-18 signals drawn from at least "
            "4 distinct platforms (must include reddit, youtube, x, AND "
            "instagram alongside web). Each bullet contains title, raw "
            "URL, platform tag, engagement metric, and a 25-60 word 'why "
            "this matters' note."
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
            "CROSS-PLATFORM CORROBORATION — if the same idea or tension "
            "appears on 2+ platforms (e.g. a Reddit thread AND a YouTube "
            "video about the same shift), bump that signal's score by "
            "+10. Multi-platform appearance is a strong trend signal "
            "because each platform's algorithm gates content "
            "independently. Note the corroborating URLs in the reasoning "
            "column when this applies.\n\n"
            "Group-reason briefly: identify the 2-3 distinct narrative "
            "threads that emerge from the highest-scoring signals, "
            "because the next agent will build ideas along those threads."
        ),
        expected_output=(
            "Markdown table with columns: signal_title | url | score | "
            "reasoning (1 sentence; mention 'corroborated by <other_url>' "
            "when relevant). Sorted score desc. Followed by a short "
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
