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
            f"Research the following topic on the public web: '{topic}'.\n\n"
            "Use the `web_search` tool at least once — run 1-3 carefully "
            "worded queries that hunt for specific, recent, non-generic "
            "signals. Aim for 8-12 total results across queries. Focus on "
            "articles, case studies, founder posts, and breakdowns — skip "
            "SEO listicles and vendor blogs when possible.\n\n"
            "Output: a bulleted list. For each signal, give the title, the "
            "URL, and a one-line note on why this signal is interesting "
            "(what is specific or counter-intuitive about it)."
        ),
        expected_output=(
            "Markdown bulleted list of 8-12 signals. Each bullet contains "
            "title, URL, and a one-line 'why this matters' note."
        ),
        agent=agents["search_agent"],
    )

    score_task = Task(
        description=(
            "Review every signal from the previous task. For each, assign "
            "an opportunity_score between 0 and 100 reflecting outlier "
            "potential for a founder-operator's video content. Reject "
            "generic or recycled takes (score <30). Reward specific, "
            "decision-level tactics (score >70). Preserve the URL for every "
            "signal so downstream agents can cite it."
        ),
        expected_output=(
            "Markdown table with columns: signal_title | url | score | "
            "reasoning. Sorted score desc."
        ),
        agent=agents["trend_scorer"],
        context=[search_task],
    )

    formulate_task = Task(
        description=(
            "Using the highest-scoring signals (score >=60), draft 3-5 "
            "distinct video ideas a founder-operator could record in their "
            "own voice.\n\n"
            "For each idea produce:\n"
            "  - title: 6-12 words, concrete, voice-matched. No clickbait.\n"
            "  - rationale: one sentence citing the trigger signal(s) and "
            "why this is specific to THIS founder.\n"
            "  - idea_type: one of systems, framework, pitch, case_study.\n"
            "  - opportunity_score: 0-100 integer — anchor to the signal's "
            "score; 60-79 = solid, 80+ = sharp outlier potential.\n"
            "  - outlier_score: 0-10 float — how counter-intuitive or "
            "against-the-grain the angle is for this audience.\n"
            "  - why_now: one short sentence (<=200 chars) on the current "
            "market reason this topic is sharp THIS week.\n"
            "  - suggested_tags: 2-4 lowercase topic tags (single words or "
            "hyphenated), useful for the user's knowledge graph.\n\n"
            "Return strict JSON that matches the schema — ideas must be a "
            "list of 3-5 objects. Do NOT wrap in markdown fences. Do NOT "
            "include a `body` field."
        ),
        expected_output=(
            "JSON object with key `ideas`, a list of 3-5 drafts matching "
            "the IdeaDraft schema (title, rationale, idea_type, "
            "opportunity_score, outlier_score, why_now, suggested_tags)."
        ),
        agent=agents["idea_formulator"],
        context=[search_task, score_task],
        output_pydantic=ResearchIdeas,
    )

    return [search_task, score_task, formulate_task]
