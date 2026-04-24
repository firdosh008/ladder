"""Research crew orchestrator.

Public API:

    async for event in run_research(user_id, profile, topic):
        ...

Event shape matches the WebSocket protocol documented in the plan. The final
event has `type='ideas_ready'` and carries the structured `IdeaDraft` list.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator
from uuid import UUID

from crewai import Crew, Process

from app.agents.research.agents import build_agents
from app.agents.research.tasks import build_tasks
from app.config import settings
from app.models.db import ResearchIdeas, UserProfileSlice
from app.services.usage import log_usage


# Rough Anthropic Sonnet pricing (USD per 1M tokens). Good enough for the
# usage_log until we pipe real billing.
_PRICE_IN_PER_MTOK = 3.0
_PRICE_OUT_PER_MTOK = 15.0


def _step_to_event(step: Any) -> dict[str, Any] | None:
    """Normalise a CrewAI step_callback payload into our wire event shape."""
    agent_name = getattr(step, "agent", None) or getattr(step, "role", None)

    tool = getattr(step, "tool", None)
    if tool:
        tool_input = getattr(step, "tool_input", None) or getattr(step, "input", None)
        return {
            "type": "tool_call",
            "tool": str(tool),
            "query": str(tool_input) if tool_input else "",
            "agent": str(agent_name) if agent_name else None,
        }

    result = getattr(step, "result", None)
    if result is not None:
        return {
            "type": "tool_result",
            "preview": str(result)[:240],
            "agent": str(agent_name) if agent_name else None,
        }

    output = getattr(step, "output", None) or getattr(step, "return_values", None)
    if output is not None:
        return {
            "type": "agent_step",
            "agent": str(agent_name) if agent_name else None,
            "preview": str(output)[:240],
        }

    return None


def _task_to_event(task_output: Any) -> dict[str, Any]:
    agent_name = getattr(task_output, "agent", None)
    return {
        "type": "task_complete",
        "agent": str(agent_name) if agent_name else None,
        "preview": str(getattr(task_output, "raw", ""))[:240],
    }


async def run_research(
    user_id: UUID,
    profile: UserProfileSlice,
    topic: str,
) -> AsyncIterator[dict[str, Any]]:
    """Run the Research crew. Yields event dicts. The final event is always
    `{type: 'ideas_ready', ideas: [...]}` on success, or an exception is
    raised (the caller surfaces it as an `error` event)."""

    async with log_usage(
        user_id=user_id,
        function_name="research_crew",
        model=settings.ANTHROPIC_MODEL,
        provider="anthropic",
    ) as entry:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        DONE = {"__done__": True}

        def _emit(event: dict[str, Any] | None) -> None:
            if event is None:
                return
            loop.call_soon_threadsafe(queue.put_nowait, event)

        def step_callback(step: Any) -> None:
            try:
                _emit(_step_to_event(step))
            except Exception:
                return

        def task_callback(task_output: Any) -> None:
            try:
                _emit(_task_to_event(task_output))
            except Exception:
                return

        agents = build_agents(profile)
        tasks = build_tasks(topic, agents)

        crew = Crew(
            agents=[
                agents["search_agent"],
                agents["trend_scorer"],
                agents["idea_formulator"],
            ],
            tasks=tasks,
            process=Process.sequential,
            step_callback=step_callback,
            task_callback=task_callback,
            verbose=False,
        )

        for name in ("search_agent", "trend_scorer", "idea_formulator"):
            yield {"type": "agent_start", "agent": name}

        async def _run() -> Any:
            try:
                return await crew.kickoff_async()
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, DONE)

        runner = asyncio.create_task(_run())

        try:
            while True:
                item = await queue.get()
                if item is DONE:
                    break
                yield item

            crew_result = await runner
        except Exception:
            runner.cancel()
            raise

        final_task = tasks[-1]
        raw_output = getattr(final_task.output, "pydantic", None)
        if not isinstance(raw_output, ResearchIdeas):
            # Fall through with an error — the route will translate to WS error.
            raise RuntimeError(
                "idea_formulator did not produce a valid ResearchIdeas payload"
            )

        metrics = getattr(crew_result, "token_usage", None) or getattr(
            crew, "usage_metrics", None
        )
        if metrics is not None:
            entry.input_tokens = int(getattr(metrics, "prompt_tokens", 0) or 0)
            entry.output_tokens = int(getattr(metrics, "completion_tokens", 0) or 0)
            entry.cost_usd = round(
                (entry.input_tokens / 1_000_000) * _PRICE_IN_PER_MTOK
                + (entry.output_tokens / 1_000_000) * _PRICE_OUT_PER_MTOK,
                6,
            )

        yield {
            "type": "ideas_ready",
            "ideas": [i.model_dump() for i in raw_output.ideas],
            "token_usage": {
                "input": entry.input_tokens,
                "output": entry.output_tokens,
                "cost_usd": entry.cost_usd,
            },
        }
