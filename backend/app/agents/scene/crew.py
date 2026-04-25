"""Scene crew orchestrator (PRD §5.5 / §11.4).

    async for event in run_scene_build(user_id, profile, idea, outline, script):
        ...

Build flow: planner → designer. The designer's SceneSkeleton is persisted.

Event protocol:
  agent_start   — layout_planner | element_designer
  text_delta    — LLM tokens
  task_complete — task index advance
  scene_ready   — final SceneSkeleton (designer output)
  usage         — token + cost rollup
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator
from uuid import UUID

from crewai import Crew, Process

from app.agents.scene.agents import build_agents
from app.agents.scene.tasks import build_tasks
from app.config import settings
from app.models.db import IdeaSlice, Outline, SceneSkeleton, Script, UserProfileSlice
from app.services.usage import log_usage


_PRICE_IN_PER_MTOK = 3.0
_PRICE_OUT_PER_MTOK = 15.0

_ROLE_TO_KEY = {
    "Layout planner": "layout_planner",
    "Element designer": "element_designer",
}


def _agent_key(role: str | None) -> str | None:
    if not role:
        return None
    return _ROLE_TO_KEY.get(role, role)


async def _stream_crew_events(
    crew: Crew,
) -> AsyncIterator[dict[str, Any]]:
    """Run a crew with stream=True and yield wire events."""

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


def _bill_usage(entry: Any, metrics: Any) -> None:
    if metrics is None:
        return
    entry.input_tokens = int(getattr(metrics, "prompt_tokens", 0) or 0)
    entry.output_tokens = int(getattr(metrics, "completion_tokens", 0) or 0)
    entry.cost_usd = round(
        (entry.input_tokens / 1_000_000) * _PRICE_IN_PER_MTOK
        + (entry.output_tokens / 1_000_000) * _PRICE_OUT_PER_MTOK,
        6,
    )


async def run_scene_build(
    user_id: UUID,
    profile: UserProfileSlice,
    idea: IdeaSlice,
    outline: Outline,
    script: Script,
) -> AsyncIterator[dict[str, Any]]:
    """Plan → design. Designer's SceneSkeleton is the only scene output."""

    async with log_usage(
        user_id=user_id,
        function_name="scene_build",
        model=settings.ANTHROPIC_MODEL,
        provider="anthropic",
    ) as entry:
        agents = build_agents(profile, idea)
        tasks = build_tasks(outline, script, agents)

        crew = Crew(
            agents=[agents["layout_planner"], agents["element_designer"]],
            tasks=tasks,
            process=Process.sequential,
            stream=True,
            verbose=False,
        )

        crew_result: Any = None
        async for ev in _stream_crew_events(crew):
            if ev.get("type") == "_result":
                crew_result = ev["result"]
                continue
            yield ev

        tasks_output = list(getattr(crew_result, "tasks_output", []) or [])
        skeleton = _extract_pydantic(tasks_output, SceneSkeleton)

        if skeleton is None:
            raise RuntimeError(
                "element_designer did not produce a SceneSkeleton payload"
            )

        _bill_usage(entry, getattr(crew_result, "token_usage", None))

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
