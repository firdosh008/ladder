"""Studio crew orchestrator (PRD §5).

Public API:

    async for event in run_studio_script(user_id, profile, idea, duration):
        ...

Two sequential tasks (script → outline). Reads each task's `output_pydantic`
off `streaming.result.tasks_output` so the route can persist them as
artifacts. Mirrors the research crew's event protocol so the frontend can
share AgentEvent typing.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator
from uuid import UUID

from crewai import Crew, Process

from app.agents.studio.agents import build_agents
from app.agents.studio.tasks import build_tasks
from app.config import settings
from app.models.db import IdeaSlice, Outline, Script, UserProfileSlice
from app.services.usage import log_usage


_PRICE_IN_PER_MTOK = 3.0
_PRICE_OUT_PER_MTOK = 15.0

_ROLE_TO_KEY = {
    "Script writer": "script_writer",
    "Outline planner": "outline_planner",
}


def _agent_key(role: str | None) -> str | None:
    if not role:
        return None
    return _ROLE_TO_KEY.get(role, role)


async def run_studio_script(
    user_id: UUID,
    profile: UserProfileSlice,
    idea: IdeaSlice,
    target_duration_min: int = 20,
) -> AsyncIterator[dict[str, Any]]:
    """Run the Studio crew and stream wire events.

    Event protocol identical to the Research vertical except for terminal
    events:
      agent_start    — agent transition (script_writer → outline_planner)
      tool_call      — none today (no tools wired); reserved
      text_delta     — LLM tokens
      task_complete  — task index advance (script done, then outline done)
      script_ready   — Script structured payload
      outline_ready  — Outline structured payload
    """

    async with log_usage(
        user_id=user_id,
        function_name="studio_script",
        model=settings.ANTHROPIC_MODEL,
        provider="anthropic",
    ) as entry:
        agents = build_agents(profile, idea)
        tasks = build_tasks(idea, target_duration_min, agents)

        crew = Crew(
            agents=[agents["script_writer"], agents["outline_planner"]],
            tasks=tasks,
            process=Process.sequential,
            stream=True,
            verbose=False,
        )

        streaming = await crew.akickoff()

        current_agent_key: str | None = None
        current_task_index: int = -1
        emitted_tool_calls: set[str] = set()
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
                tc = getattr(chunk, "tool_call", None)
                if tc is None:
                    continue
                tool_id = str(
                    getattr(tc, "tool_id", "")
                    or f"{agent_key}:{getattr(tc, 'index', 0)}"
                )
                if tool_id in emitted_tool_calls:
                    continue
                emitted_tool_calls.add(tool_id)
                yield {
                    "type": "tool_call",
                    "agent": agent_key,
                    "tool": getattr(tc, "tool_name", None) or "unknown",
                    "arguments": getattr(tc, "arguments", "") or "",
                }
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

        crew_result = streaming.result
        tasks_output = list(crew_result.tasks_output or [])

        script: Script | None = None
        outline: Outline | None = None
        for t in tasks_output:
            payload = getattr(t, "pydantic", None)
            if isinstance(payload, Script):
                script = payload
            elif isinstance(payload, Outline):
                outline = payload

        if script is None:
            raise RuntimeError("script_writer did not produce a Script payload")
        if outline is None:
            raise RuntimeError("outline_planner did not produce an Outline payload")

        metrics = getattr(crew_result, "token_usage", None)
        if metrics is not None:
            entry.input_tokens = int(getattr(metrics, "prompt_tokens", 0) or 0)
            entry.output_tokens = int(getattr(metrics, "completion_tokens", 0) or 0)
            entry.cost_usd = round(
                (entry.input_tokens / 1_000_000) * _PRICE_IN_PER_MTOK
                + (entry.output_tokens / 1_000_000) * _PRICE_OUT_PER_MTOK,
                6,
            )

        yield {"type": "script_ready", "script": script.model_dump()}
        yield {"type": "outline_ready", "outline": outline.model_dump()}
        yield {
            "type": "usage",
            "token_usage": {
                "input": entry.input_tokens,
                "output": entry.output_tokens,
                "cost_usd": entry.cost_usd,
            },
        }
        # Surface the structured payloads to the route via async-iter close.
        # The route reads them from the events themselves; nothing else to do.
        await asyncio.sleep(0)
