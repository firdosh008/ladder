"""Tasks for the Scene crew. Sequential: plan → design.

Each task uses `output_pydantic` so CrewAI surfaces typed models on
`tasks_output[i].pydantic`. The final persisted drawing is the designer's
`SceneSkeleton` (the critic agent is not used).
"""

from __future__ import annotations

from crewai import Agent, Task

from app.models.db import Outline, Script, SceneLayout, SceneSkeleton


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


def build_tasks(
    outline: Outline,
    script: Script,
    agents: dict[str, Agent],
) -> list[Task]:
    outline_text = _outline_dump(outline)
    script_text = _script_summary(script)
    frame_count = len(outline.items)

    plan_task = Task(
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

    design_task = Task(
        description=(
            "Design Excalidraw skeleton elements that fill the layout you "
            "received from the planner. The output is "
            "ExcalidrawElementSkeleton-compatible — the frontend will "
            "inflate it via convertToExcalidrawElements().\n\n"
            "CRITICAL — YOUR JSON MUST INCLUDE THE KEY `elements` (array). "
            "The pipeline will reject the output if `elements` is missing, "
            "empty, or only canvas metadata. Put every shape, arrow, and "
            "text in `elements`. Minimum 2 items.\n\n"
            "Per-frame element rules (use the frame's `kind` to pick):\n"
            "  • title  — one centered rectangle (filled #E8442A bg, white "
            "    label) holding the frame label as `label.text`.\n"
            "  • flow   — 2-4 rectangles connected by arrows showing the "
            "    sequence. Each rectangle has its step name as label.\n"
            "  • table  — 2-column grid of rectangles (e.g. 'Wrong' vs "
            "    'Right'); use 4-6 cells total with a header row.\n"
            "  • decision — diamond at top, 2-3 rectangles below, arrows "
            "    from the diamond labelled with the branch condition.\n"
            "  • architecture — stacked rectangles (layers) with thin "
            "    arrows between them.\n"
            "  • checklist — 3-6 small ellipses (bullets) with a text "
            "    element next to each.\n"
            "  • diagram / cta — pick the closest of the above.\n\n"
            "Hard rules:\n"
            "  • Every shape MUST stay strictly inside its frame's bounding "
            "    box (use the frame's x/y/width/height as a hard clamp). "
            "    Leave at least 24px internal padding.\n"
            "  • Every element has a unique stable string id "
            "    ('f<n>-box-<k>', 'arrow-<n>-<k>', etc).\n"
            "  • Arrows reference start/end via `{id: '<element-id>'}`. The "
            "    referenced ids MUST exist in the same elements list.\n"
            "  • Style: roughness=1, strokeWidth=2, fillStyle='solid' for "
            "    title/cta cards (Cinnabar #E8442A), no fill elsewhere. "
            "    strokeColor='#F5F5F5' for outlines on the dark canvas, "
            "    '#E8442A' for accent shapes.\n"
            "  • Text elements: no `label` field, use `text` instead.\n"
            "  • Add ONE text element near the top of the canvas with the "
            "    video title (use the outline's first frame label).\n\n"
            "Return strict JSON: { canvas_width, canvas_height, background_color, "
            "elements: [ ...at least 2 ExcalidrawElementSkeleton objects... ], "
            "notes? }. NO markdown fences. NO commentary."
        ),
        expected_output=(
            "JSON object: {canvas_width, canvas_height, background_color, "
            "elements: [SceneSkeletonElement, ...], notes?}."
        ),
        agent=agents["element_designer"],
        context=[plan_task],
        output_pydantic=SceneSkeleton,
    )

    return [plan_task, design_task]
