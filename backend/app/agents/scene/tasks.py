"""Tasks for the Scene crew.

Only the planner task lives here now. The element designer is no longer a
CrewAI task — it's a direct Anthropic structured-outputs call in
`app/agents/scene/designer.py`. CrewAI's `output_pydantic` is prompted JSON,
which the model dropped on a large `SceneSkeleton` schema; the designer step
needs grammar-constrained output.

`_outline_dump` and `_script_summary` are reused by the designer module as
prompt-context formatters — kept here so there's one canonical layout.
"""

from __future__ import annotations

from crewai import Agent, Task

from app.models.db import Outline, Script, SceneLayout


def _outline_dump(outline: Outline) -> str:
    lines: list[str] = []
    for it in outline.items:
        lines.append(f"  {it.number}. [{it.label}] {it.beat}")
    return "\n".join(lines)


def _script_summary(script: Script) -> str:
    """Compact script summary — section headings + total runtime."""
    lines = [
        f"  - {sec.heading} ({sec.duration_min}m)" for sec in script.sections
    ]
    total = sum(sec.duration_min for sec in script.sections)
    return "\n".join(lines) + f"\n  Total: {total} min"


def build_planner_task(
    outline: Outline,
    script: Script,
    agents: dict[str, Agent],
) -> Task:
    outline_text = _outline_dump(outline)
    script_text = _script_summary(script)
    frame_count = len(outline.items)

    return Task(
        description=(
            f"Produce a SceneLayout for this {frame_count}-frame outline:\n"
            f"{outline_text}\n\n"
            f"Script context (for runtime sense):\n{script_text}\n\n"
            "Rules:\n"
            "  • One frame per outline item, in the same order.\n"
            "  • Pick canvas_width 1600-2400 and canvas_height that fits all "
            "    frames with padding. Round to multiples of 100.\n"
            "  • flow_direction: 'top-to-bottom' for >4 frames, "
            "    'left-to-right' otherwise.\n"
            "  • Frame regions MUST NOT overlap. Leave at least 80px gutter "
            "    between frames.\n"
            "  • Each frame's `kind` is your call based on the beat: title "
            "    cards / CTAs use 'title' or 'cta'; cause-effect or "
            "    procedural beats use 'flow'; comparisons use 'table'; "
            "    branching logic uses 'decision'; layered systems use "
            "    'architecture'; numbered steps use 'checklist'.\n"
            "  • Each frame's `label` matches the outline label VERBATIM "
            "    (this is what users will see on the canvas).\n"
            "  • `description` is a short note (≤80 words) telling the "
            "    element designer what this frame should depict.\n"
            "  • background_color: '#1A1A2E' (PRD-mandated dark canvas).\n\n"
            "Return strict JSON matching the SceneLayout schema. NO markdown "
            "fences. NO commentary."
        ),
        expected_output=(
            "JSON object: {canvas_width, canvas_height, background_color, "
            "flow_direction, frames: [{number, label, kind, x, y, width, "
            "height, description}, ...]}."
        ),
        agent=agents["layout_planner"],
        output_pydantic=SceneLayout,
    )
