"""Tasks for the Studio crew. Sequential: script → outline."""

from __future__ import annotations

from typing import Any

from crewai import Agent, Task

from app.models.db import IdeaSlice, Outline, Script


def _sources_block(sources: list[dict[str, Any]]) -> str:
    """Format research sources for the script writer.

    All platforms are citable but with different evidence weight:
      - web: statistics, research findings, market data
      - reddit: community sentiment, user experiences, pain points
      - youtube: creator perspectives, visual trends
      - x: operator hot-takes, expert opinions
      - instagram: cultural patterns, visual trends

    The script writer should cite the RIGHT platform for the claim type:
    statistics → web, community sentiment → reddit, expert views → x/youtube.
    """
    if not sources:
        return ""
    lines = [
        "RESEARCH SOURCES — cite these. Format: [source:N] where N is the number.",
        "Different platforms carry different evidence weight:",
        "  web → statistics, research findings, market data (cite for numbers)",
        "  reddit → community sentiment, pain points, user experiences (cite for perspective)",
        "  youtube → creator insights, visual trends (cite for viewpoint)",
        "  x → operator hot-takes, expert opinions (cite for expert perspective)",
        "  instagram → cultural patterns (cite for trend context)",
        "",
    ]
    for i, s in enumerate(sources, 1):
        title = s.get("title") or "Untitled"
        url = s.get("url") or ""
        snippet = (s.get("snippet") or "")[:2000]
        platform = s.get("platform") or "web"
        meta = s.get("meta") or {}
        lines.append(f"[source:{i}] [{platform}] {title}")
        lines.append(f"      URL: {url}")
        if snippet:
            lines.append(f"      Content: {snippet}")
        if meta.get("score"):
            lines.append(f"      Engagement: score={meta['score']}")
        if meta.get("view_count"):
            lines.append(f"      Views: {meta['view_count']:,}")
        if meta.get("channel"):
            lines.append(f"      Channel: {meta['channel']}")
        if meta.get("handle"):
            lines.append(f"      Author: @{meta['handle']}")
        lines.append("")
    return "\n".join(lines)


def build_tasks(
    idea: IdeaSlice,
    target_duration_min: int,
    agents: dict[str, Agent],
    sources: list[dict[str, Any]] | None = None,
) -> list[Task]:
    source_block = _sources_block(sources or [])

    script_task = Task(
        description=(
            f"Write a {target_duration_min}-minute video script for the "
            f"idea titled: '{idea.title}'.\n\n"
            "The script must be a list of 3-8 sections, each with:\n"
            "  - heading: 3-7 words, concrete (not 'Introduction' / "
            "'Conclusion' — name what the section is about).\n"
            "  - duration_min: integer minutes (sum should land within "
            f"~10% of {target_duration_min} minutes; never under {max(target_duration_min - 4, 3)}).\n"
            "  - talking_points: 3-7 bullets. Each is a SINGLE thought the "
            "founder will riff on — NOT a paragraph, NOT a paraphrase of "
            "another bullet. Each bullet 8-30 words.\n"
            "  - transition: 1 sentence (15-35 words) bridging into the "
            "next section. May be omitted on the final section only.\n\n"
            "CITATION RULES (CRITICAL):\n"
            "  • CITE ONLY WHAT YOU CAN SEE: before adding [source:N] to a "
            "statistic, VERIFY that the EXACT number, percentage, or finding "
            "appears in that source's Content/Engagement data above.\n"
            "  • If the source doesn't contain the number → DON'T CITE IT. "
            "Use a DIFFERENT source that actually has the stat.\n"
            "  • If NO source contains a stat you want to use → DON'T USE "
            "THE STAT. Replace it with a claim the sources DO support.\n"
            "  • Example (correct): source:3 snippet says '73% of startups "
            "fail' → you write '73% of startups fail [source:3]'.\n"
            "  • Example (WRONG): you write '$500/hr lawyer fees [source:2]' "
            "but source:2 never mentions lawyer fees → this is a FABRICATED "
            "citation. Never do this.\n"
            "  • You may use the same source multiple times.\n\n"
            "Other Rules:\n"
            "  • No filler ('In this video...'). Open with the most "
            "interesting beat.\n"
            "  • Don't recap the title back to the user.\n"
            "  • Avoid em-dash overload, avoid hype words, avoid 'Ultimate'.\n\n"
            + source_block + "\n\n"
            "Return strict JSON matching the Script schema. NO markdown "
            "fences."
        ),
        expected_output=(
            "JSON object with key `sections`, a list of 3-8 ScriptSection "
            "objects (heading, duration_min, talking_points with [source:N] "
            "citations on every factual claim, transition)."
        ),
        agent=agents["script_writer"],
        output_pydantic=Script,
    )

    outline_task = Task(
        description=(
            "Compress the finished script into a numbered scene outline. "
            "One OutlineItem per script section, in order:\n"
            "  - number: 1-indexed integer matching section order.\n"
            "  - label: 3-6 words, punchier than the script's heading. "
            "Title-case allowed.\n"
            "  - beat: 1-2 sentences (25-60 words) describing what the "
            "viewer experiences in this scene — visuals, the question or "
            "claim that anchors it, the takeaway.\n\n"
            "If a script section earns it, you may also produce an extra "
            "outline row for a strong opening hook OR a closing CTA — but "
            "only when the script clearly supports it. Keep total items "
            "between 3 and 12.\n\n"
            "Return strict JSON matching the Outline schema. NO markdown "
            "fences."
        ),
        expected_output=(
            "JSON object with key `items`, a list of 3-12 OutlineItems."
        ),
        agent=agents["outline_planner"],
        context=[script_task],
        output_pydantic=Outline,
    )

    return [script_task, outline_task]
