"""Research crew orchestrator.

Public API:

    async for event in run_research(user_id, profile, topic):
        ...

Uses CrewAI 1.14's native streaming (`Crew(stream=True)` +
`await crew.akickoff()`) so we emit real LLM + tool events without relying on
the threaded `step_callback` shim. The final event is always
`{type: 'ideas_ready', ideas: [...], token_usage: {...}}` followed by the
usage_log write on context exit. Any exception surfaces as-is — the route
maps it to an `error` event for the client.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any, AsyncIterator
from uuid import UUID

from crewai import Crew, Process

from app.agents.research.agents import build_agents
from app.agents.research.knowledge_graph import retrieve_knowledge_context
from app.agents.research.streaming import (
    SourceRef,
    sources_emitter_var,
)
from app.agents.research.tasks import build_tasks
from app.config import settings
from app.models.db import ResearchIdeas, UserProfileSlice
from app.services.usage import log_usage


# Rough Anthropic Haiku pricing (USD per 1M tokens). Good enough for the
# usage_log until we pipe real billing.
_PRICE_IN_PER_MTOK = 1.0
_PRICE_OUT_PER_MTOK = 5.0

# Readable role → stable agent key (matches the frontend AGENT_LABELS map).
_ROLE_TO_KEY = {
    "Trend researcher": "search_agent",
    "Outlier scorer": "trend_scorer",
    "Idea architect": "idea_formulator",
}


def _agent_key(role: str | None) -> str | None:
    if not role:
        return None
    return _ROLE_TO_KEY.get(role, role)


async def run_research(
    user_id: UUID,
    profile: UserProfileSlice,
    topic: str,
    target_duration_min: int = 10,
) -> AsyncIterator[dict[str, Any]]:
    """Run the Research crew and stream wire events.

    `target_duration_min` is the founder's intended video runtime (3-60).
    The idea_formulator uses it to size each draft's scope — a 5-minute
    sharp-take vs a 30-minute deep-dive carry very different rationales
    and "why now" beats.

    Event types emitted:
      knowledge_context — pre-retrieval result (count of your own knowledge chunks)
      agent_start       — each new agent_role the stream reports
      tool_call         — the LLM has emitted a TOOL_CALL chunk (with arguments)
      sources           — ExaSearchTool pushed its results back via ContextVar
      text_delta        — the LLM is streaming output tokens (truncated per chunk)
      task_complete     — the streaming chunks moved to the next task index
      ideas_ready       — terminal event carrying the parsed ResearchIdeas
    """

    async with log_usage(
        user_id=user_id,
        function_name="research_crew",
        model=settings.ANTHROPIC_MODEL,
        provider="anthropic",
    ) as entry:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        def push(event: dict[str, Any]) -> None:
            """Thread-safe enqueue from tool callbacks."""
            loop.call_soon_threadsafe(queue.put_nowait, event)

        def emit_sources(query: str, sources: list[SourceRef]) -> None:
            push(
                {
                    "type": "sources",
                    "query": query,
                    "items": [asdict(s) for s in sources],
                }
            )

        token = sources_emitter_var.set(emit_sources)

        try:
            knowledge_context, kg_count = await retrieve_knowledge_context(
                user_id, topic
            )
            yield {
                "type": "knowledge_context",
                "count": kg_count,
            }

            agents = build_agents(profile, knowledge_context=knowledge_context)
            tasks = build_tasks(
                topic, agents, target_duration_min,
                knowledge_context=knowledge_context,
            )

            crew = Crew(
                agents=[
                    agents["search_agent"],
                    agents["trend_scorer"],
                    agents["idea_formulator"],
                ],
                tasks=tasks,
                process=Process.sequential,
                stream=True,
                verbose=False,
            )

            streaming = await crew.akickoff()

            current_agent_key: str | None = None
            current_task_index: int = -1
            emitted_tool_calls: set[str] = set()
            text_buffer: dict[str, str] = {}  # per-agent rolling text

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
                    tool_id = str(getattr(tc, "tool_id", "") or f"{agent_key}:{getattr(tc, 'index', 0)}")
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

                # Drain any pending tool emissions (sources) between chunks.
                while not queue.empty():
                    yield queue.get_nowait()

            if current_agent_key and current_task_index >= 0:
                preview = text_buffer.get(current_agent_key, "").strip()
                yield {
                    "type": "task_complete",
                    "agent": current_agent_key,
                    "preview": preview[-240:] if preview else "",
                }

            while not queue.empty():
                yield queue.get_nowait()

            crew_result = streaming.result

            raw_output = getattr(crew_result, "pydantic", None)
            if not isinstance(raw_output, ResearchIdeas):
                # idea_formulator was the last task and its output_pydantic
                # was ResearchIdeas, so crew_result.pydantic should match.
                final_task_output = (crew_result.tasks_output or [None])[-1]
                raw_output = getattr(final_task_output, "pydantic", None)

            if not isinstance(raw_output, ResearchIdeas):
                raise RuntimeError(
                    "idea_formulator did not produce a valid ResearchIdeas payload"
                )

            metrics = getattr(crew_result, "token_usage", None)
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
        finally:
            sources_emitter_var.reset(token)
