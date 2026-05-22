"""Scene crew orchestrator (PRD §5.5 / §11.4).

    async for event in run_scene_build(user_id, profile, idea, outline, script):
        ...

Two-stage build:

  1. CrewAI planner crew → SceneLayout (small/flat schema, prompted JSON
     via `output_pydantic` is fine and gives us native streaming).
  2. Direct Anthropic call with structured outputs → SceneSkeleton (large
     nested schema; CrewAI's prompted JSON dropped `elements` regularly,
     grammar-constrained sampling fixes it).

Event protocol (matches the frontend SceneRunPanel agent keys):
  agent_start   — layout_planner | element_designer
  text_delta    — LLM tokens (planner only; designer is one-shot)
  task_complete — task index advance
  scene_ready   — final SceneSkeleton (designer output)
  usage         — token + cost rollup (combined planner + designer)
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator
from uuid import UUID

from crewai import Crew, Process

from app.agents.scene.agents import build_agents
from app.agents.scene.designer import run_designer
from app.agents.scene.tasks import build_planner_task
from app.config import settings
from app.models.db import (
    IdeaSlice,
    Outline,
    SceneLayout,
    Script,
    UserProfileSlice,
)
from app.services.scene_visual_assets import enrich_scene_visuals
from app.services.usage import log_usage


_PRICE_IN_PER_MTOK = 1.0
_PRICE_OUT_PER_MTOK = 5.0

_ROLE_TO_KEY = {
    "Layout planner": "layout_planner",
}


def _agent_key(role: str | None) -> str | None:
    if not role:
        return None
    return _ROLE_TO_KEY.get(role, role)


async def _stream_planner(
    crew: Crew,
) -> AsyncIterator[dict[str, Any]]:
    """Run the planner crew with stream=True and yield wire events."""

    streaming = await crew.akickoff()
    current_agent_key: str | None = None
    current_task_index: int = -1
    text_buffer: dict[str, str] = {}

    async for chunk in streaming:
        agent_role = getattr(chunk, "agent_role", "") or ""
        agent_key = _agent_key(agent_role)
        task_index = int(getattr(chunk, "task_index", 0) or 0)

        if agent_key and agent_key != current_agent_key:
            current_agent_key = agent_key
            yield {"type": "agent_start", "agent": agent_key}

        if task_index != current_task_index:
            if current_task_index >= 0 and current_agent_key:
                preview = text_buffer.get(current_agent_key, "").strip()
                yield {
                    "type": "task_complete",
                    "agent": current_agent_key,
                    "preview": preview[-240:] if preview else "",
                }
                text_buffer[current_agent_key] = ""
            current_task_index = task_index

        chunk_type = getattr(chunk, "chunk_type", None)
        chunk_type_name = (
            getattr(chunk_type, "value", chunk_type)
            if chunk_type is not None
            else "text"
        )
        if chunk_type_name == "tool_call":
            continue

        content = getattr(chunk, "content", "") or ""
        if content and agent_key:
            text_buffer[agent_key] = (text_buffer.get(agent_key, "") + content)[-4000:]
            yield {
                "type": "text_delta",
                "agent": agent_key,
                "content": content,
            }

    if current_agent_key and current_task_index >= 0:
        preview = text_buffer.get(current_agent_key, "").strip()
        yield {
            "type": "task_complete",
            "agent": current_agent_key,
            "preview": preview[-240:] if preview else "",
        }

    yield {"type": "_result", "result": streaming.result}


def _extract_pydantic(tasks_output: list[Any], expected_type: type) -> Any | None:
    for task in reversed(tasks_output):
        payload = getattr(task, "pydantic", None)
        if isinstance(payload, expected_type):
            return payload
    return None


def _bill(input_tokens: int, output_tokens: int) -> float:
    return round(
        (input_tokens / 1_000_000) * _PRICE_IN_PER_MTOK
        + (output_tokens / 1_000_000) * _PRICE_OUT_PER_MTOK,
        6,
    )


async def run_scene_build(
    user_id: UUID,
    profile: UserProfileSlice,
    idea: IdeaSlice,
    outline: Outline,
    script: Script,
    brand_color: str | None = None,
    font_family: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Plan (CrewAI) → design (Anthropic structured outputs).

    `brand_color` (optional 7-char hex like '#E8442A') becomes the primary
    accent for filled title/cta cards and accent strokes in the generated
    Excalidraw scene. Set per-session by the studio header's color picker.

    `font_family` (optional Excalidraw fontFamily integer; 1/2/3/5/6/7/8/9)
    is forwarded to the designer; when set, every text/label gets that
    fontFamily so the founder's chosen typeface threads end-to-end. None
    means the designer leaves fontFamily off (Excalidraw default).
    """

    if settings.ENABLE_MCP_SCENE_DIAGRAM:
        from app.agents.scene import mcp_diagram

        async for ev in mcp_diagram.run_scene_mcp_diagram(
            user_id,
            profile,
            idea,
            outline,
            script,
            brand_color=brand_color,
            font_family=font_family,
        ):
            yield ev
        return

    async with log_usage(
        user_id=user_id,
        function_name="scene_build",
        model=settings.ANTHROPIC_MODEL,
        provider="anthropic",
    ) as entry:
        agents = build_agents(profile, idea)
        planner_task = build_planner_task(outline, script, agents)

        crew = Crew(
            agents=[agents["layout_planner"]],
            tasks=[planner_task],
            process=Process.sequential,
            stream=True,
            verbose=False,
        )

        crew_result: Any = None
        async for ev in _stream_planner(crew):
            if ev.get("type") == "_result":
                crew_result = ev["result"]
                continue
            yield ev

        tasks_output = list(getattr(crew_result, "tasks_output", []) or [])
        layout = _extract_pydantic(tasks_output, SceneLayout)
        if layout is None:
            raise RuntimeError(
                "layout_planner did not produce a SceneLayout payload"
            )

        planner_usage = getattr(crew_result, "token_usage", None)
        planner_in = int(getattr(planner_usage, "prompt_tokens", 0) or 0)
        planner_out = int(getattr(planner_usage, "completion_tokens", 0) or 0)

        # Designer — direct Anthropic call with grammar-constrained JSON.
        yield {"type": "agent_start", "agent": "element_designer"}

        skeleton, designer_in, designer_out = await run_designer(
            profile=profile,
            idea=idea,
            layout=layout,
            script=script,
            outline=outline,
            brand_color=brand_color,
            font_family=font_family,
        )

        skeleton = await enrich_scene_visuals(skeleton, idea, outline, layout)

        yield {
            "type": "task_complete",
            "agent": "element_designer",
            "preview": (skeleton.notes or "")[-240:],
        }

        entry.input_tokens = planner_in + designer_in
        entry.output_tokens = planner_out + designer_out
        entry.cost_usd = _bill(entry.input_tokens, entry.output_tokens)

        yield {"type": "scene_ready", "scene": skeleton.model_dump()}
        yield {
            "type": "usage",
            "token_usage": {
                "input": entry.input_tokens,
                "output": entry.output_tokens,
                "cost_usd": entry.cost_usd,
            },
        }
        await asyncio.sleep(0)
