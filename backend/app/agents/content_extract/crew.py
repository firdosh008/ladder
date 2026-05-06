"""Content-extract crew orchestrator (PRD §2 Option 3 / §11.11).

Public API:

    async for event in run_content_extract(user_id, profile, source_content):
        ...

Two sequential tasks (analyze → extract). Final structured output is an
ExtractedVideo. The route uses it to insert one ideas row + one
studio_sessions row + script + outline artifacts on completion.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator
from uuid import UUID

from crewai import Crew, Process

from app.agents.content_extract.agents import build_agents
from app.agents.content_extract.tasks import build_tasks
from app.agents.research.knowledge_graph import retrieve_knowledge_context
from app.config import settings
from app.models.db import ExtractedVideo, UserProfileSlice
from app.services.usage import log_usage


_PRICE_IN_PER_MTOK = 1.0
_PRICE_OUT_PER_MTOK = 5.0

_ROLE_TO_KEY = {
    "Source analyzer": "analyzer",
    "Source extractor": "extractor",
}


def _agent_key(role: str | None) -> str | None:
    if not role:
        return None
    return _ROLE_TO_KEY.get(role, role)


async def run_content_extract(
    user_id: UUID,
    profile: UserProfileSlice,
    source_content: str,
) -> AsyncIterator[dict[str, Any]]:
    """Run the content_extract crew and stream wire events.

    Terminal events:
      knowledge_context — pre-retrieval result (count of own knowledge chunks)
      extract_ready     — ExtractedVideo (after extract task)
      usage             — token + cost summary
    """

    async with log_usage(
        user_id=user_id,
        function_name="content_extract",
        model=settings.ANTHROPIC_MODEL,
        provider="anthropic",
    ) as entry:
        knowledge_context, kg_count = await retrieve_knowledge_context(
            user_id, source_content[:200]
        )
        yield {
            "type": "knowledge_context",
            "count": kg_count,
        }

        agents = build_agents(profile, knowledge_context=knowledge_context)
        tasks = build_tasks(source_content, agents, knowledge_context=knowledge_context)

        crew = Crew(
            agents=[agents["analyzer"], agents["extractor"]],
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

        extracted: ExtractedVideo | None = None
        for t in tasks_output:
            payload = getattr(t, "pydantic", None)
            if isinstance(payload, ExtractedVideo):
                extracted = payload
                break

        if extracted is None:
            raise RuntimeError(
                "content_extract did not produce an ExtractedVideo payload"
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

        yield {"type": "extract_ready", "extracted": extracted.model_dump()}
        yield {
            "type": "usage",
            "token_usage": {
                "input": entry.input_tokens,
                "output": entry.output_tokens,
                "cost_usd": entry.cost_usd,
            },
        }
        await asyncio.sleep(0)
