"""Tasks for the content_extract crew."""

from __future__ import annotations

from crewai import Agent, Task

from app.models.db import ContentAnalysis, ExtractedVideo


def build_tasks(source_content: str, agents: dict[str, Agent]) -> list[Task]:
    analyze_task = Task(
        description=(
            "Read the pasted source below and produce a ContentAnalysis "
            "with these fields:\n"
            "  - title: a tight, founder-voice video title (5-12 words). "
            "Don't reuse the source's title verbatim.\n"
            "  - rationale: 2-3 sentences explaining WHY this source makes "
            "a strong video for THIS founder's audience.\n"
            "  - idea_type: one of 'systems', 'framework', 'pitch', "
            "'case_study'. Pick the closest fit.\n"
            "  - derived_duration_min: integer minutes. Use 8-12 for a "
            "tight tactical breakdown, 15-22 for a deeper framework, "
            "23-30 only when the source genuinely supports it.\n"
            "  - key_beats: 4-8 bullets — the SPECIFIC arguments / moments "
            "the script must hit. Each 8-25 words. NO summarising — pick "
            "the moves.\n\n"
            "Return strict JSON, no markdown fences.\n\n"
            "PASTED SOURCE\n"
            "=============\n"
            f"{source_content}\n"
            "=============\n"
        ),
        expected_output=(
            "JSON object with keys: title, rationale, idea_type, "
            "derived_duration_min, key_beats."
        ),
        agent=agents["analyzer"],
        output_pydantic=ContentAnalysis,
    )

    extract_task = Task(
        description=(
            "Using the ContentAnalysis from the previous step AND the "
            "pasted source, produce a ExtractedVideo with:\n"
            "  - title, rationale, idea_type, derived_duration_min — "
            "carry forward from the analysis (you may sharpen the title).\n"
            "  - script: 3-7 sections. Each section has heading "
            "(3-7 words), duration_min (sums roughly to "
            "derived_duration_min), 3-7 talking_points (8-30 words each), "
            "and a transition (15-35 words). Talking points must be "
            "anchored in the pasted source — when you assert a claim, "
            "make sure the source supports it.\n"
            "  - outline: 3-10 numbered OutlineItems mirroring the script. "
            "Each item has number, label (3-6 words, punchy), beat (1-2 "
            "sentences, 25-60 words).\n\n"
            "Constraints:\n"
            "  • Don't invent stats or quotes the source doesn't have.\n"
            "  • Don't open with 'In this video...'. Lead with the most "
            "interesting beat.\n"
            "  • Avoid 'Ultimate', avoid hype. Keep founder voice.\n\n"
            "Return strict JSON matching the ExtractedVideo schema. NO "
            "markdown fences."
        ),
        expected_output=(
            "JSON object with keys: title, rationale, idea_type, "
            "derived_duration_min, script (Script), outline (Outline)."
        ),
        agent=agents["extractor"],
        context=[analyze_task],
        output_pydantic=ExtractedVideo,
    )

    return [analyze_task, extract_task]
