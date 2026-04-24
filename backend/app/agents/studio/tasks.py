"""Tasks for the Studio crew. Sequential: script → outline."""

from __future__ import annotations

from crewai import Agent, Task

from app.models.db import IdeaSlice, Outline, Script


def build_tasks(
    idea: IdeaSlice,
    target_duration_min: int,
    agents: dict[str, Agent],
) -> list[Task]:
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
            "Rules:\n"
            "  • No filler ('In this video...'). Open with the most "
            "interesting beat.\n"
            "  • Don't recap the title back to the user.\n"
            "  • Reference specifics from the founder's notes / pasted "
            "source when present — don't invent stats.\n"
            "  • Avoid em-dash overload, avoid hype words, avoid 'Ultimate'.\n\n"
            "Return strict JSON matching the Script schema. NO markdown "
            "fences."
        ),
        expected_output=(
            "JSON object with key `sections`, a list of 3-8 ScriptSection "
            "objects (heading, duration_min, talking_points, transition)."
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
