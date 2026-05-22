"""Research orchestrator using the standalone MCP Research Agent.

Public API:

    async for event in run_research(user_id, profile, topic):
        ...

This replaces the old CrewAI-based pipeline. It:
1. Calls the standalone MCP Research Agent via JSON-RPC.
2. Emits real-time `sources` events as they are discovered.
3. Adapts the rich MCP `ResearchResult` into Ladder's `IdeaDraft[]` using Claude.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any, AsyncIterator
from uuid import UUID

from app.agents.research.knowledge_graph import retrieve_knowledge_context
from app.agents.research.streaming import (
    SourceRef,
    sources_emitter_var,
)
from app.agents.research.mcp_research_adapter import transform_mcp_to_ladder_ideas
from app.config import settings
from app.models.db import UserProfileSlice
from app.services.usage import log_usage

log = logging.getLogger(__name__)

# Rough Anthropic Haiku pricing (USD per 1M tokens) for the adapter call.
_PRICE_IN_PER_MTOK = 1.0
_PRICE_OUT_PER_MTOK = 5.0


async def run_research(
    user_id: UUID,
    profile: UserProfileSlice,
    topic: str,
    target_duration_min: int = 10,
) -> AsyncIterator[dict[str, Any]]:
    """Run research via the MCP Agent and stream wire events.

    `target_duration_min` is the founder's intended video runtime (3-60).

    Event types emitted:
      knowledge_context — pre-retrieval result
      agent_start       — progress indicators for the UI
      sources           — emitted when MCP returns its source list
      ideas_ready       — terminal event carrying the parsed ResearchIdeas
    """
    
    async with log_usage(
        user_id=user_id,
        function_name="mcp_research_pipeline",
        model=settings.ANTHROPIC_MODEL,
        provider="anthropic",
    ) as entry:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        all_sources: list[dict[str, Any]] = []

        def push(event: dict[str, Any]) -> None:
            """Thread-safe enqueue."""
            loop.call_soon_threadsafe(queue.put_nowait, event)

        def emit_sources(query: str, sources: list[SourceRef]) -> None:
            serialized = [asdict(s) for s in sources]
            all_sources.extend(serialized)
            push(
                {
                    "type": "sources",
                    "query": query,
                    "items": serialized,
                }
            )

        token = sources_emitter_var.set(emit_sources)

        try:
            # 1. Retrieve knowledge graph
            knowledge_context, kg_count = await retrieve_knowledge_context(
                user_id, topic
            )
            yield {
                "type": "knowledge_context",
                "count": kg_count,
            }

            # 2. Start MCP research
            yield {"type": "agent_start", "agent": "search_agent"}
            
            # The MCP agent runs the full demand -> supply -> synthesis pipeline
            # Wait for it to complete. In the future we can wire up an async 
            # callback for real-time layer events from the MCP server.
            from app.services.mcp_research_client import stream_mcp_research
            
            mcp_result = None
            async for payload in stream_mcp_research(
                query=topic,
                context={
                    "user_id": str(user_id),
                    "positioning": profile.positioning,
                    "audience": profile.audience,
                },
            ):
                if payload["type"] == "stream_event":
                    event = payload["event"]
                    # Map MCP events to Ladder UI events
                    msg = event.get("message", "")
                    if msg:
                        # Map layer/agent names for UI
                        agent_name = event.get("agent", "") or event.get("layer", "research")
                        push({
                            "type": "tool_call",
                            "agent": "search_agent",
                            "tool": agent_name,
                            "arguments": msg
                        })
                elif payload["type"] == "final_result":
                    mcp_result = payload["result"]
            
            if not mcp_result:
                raise RuntimeError("No final result from MCP Research Agent")

            if mcp_result.get("status") in {"error", "failed", "rejected"}:
                error = (
                    mcp_result.get("error")
                    or mcp_result.get("rejection_reason")
                    or f"MCP Research Agent returned status={mcp_result.get('status')}"
                )
                raise RuntimeError(error)
            
            # 3. Emit sources found by MCP
            mcp_sources = mcp_result.get("sources", [])
            mapped_sources = []
            for s in mcp_sources:
                # Map MCP source fields to Ladder SourceRef
                mapped_sources.append(SourceRef(
                    title=s.get("title", "Untitled"),
                    url=s.get("url", ""),
                    snippet=s.get("snippet", ""),
                    platform=s.get("platform", "web"),
                    meta=s.get("engagement", {}),
                ))
            
            if mapped_sources:
                emit_sources(topic, mapped_sources)
                
            # Drain queue
            while not queue.empty():
                yield queue.get_nowait()
                
            yield {"type": "task_complete", "agent": "search_agent", "preview": "Extracted sources and generated thesis."}

            # 4. Formulate Ladder IdeaDrafts
            yield {"type": "agent_start", "agent": "idea_formulator"}
            
            ideas_model, usage = await transform_mcp_to_ladder_ideas(
                mcp_result=mcp_result,
                profile=profile,
                topic=topic,
                target_duration_min=target_duration_min,
                knowledge_context=knowledge_context,
            )
            
            entry.input_tokens = usage.get("input_tokens", 0)
            entry.output_tokens = usage.get("output_tokens", 0)
            
            # Total cost is the MCP run cost + the adapter LLM cost
            mcp_cost = mcp_result.get("cost_breakdown", {}).get("total", 0.0)
            adapter_cost = (
                (entry.input_tokens / 1_000_000) * _PRICE_IN_PER_MTOK
                + (entry.output_tokens / 1_000_000) * _PRICE_OUT_PER_MTOK
            )
            entry.cost_usd = round(mcp_cost + adapter_cost, 6)

            yield {"type": "task_complete", "agent": "idea_formulator", "preview": "Formatted ideas."}

            while not queue.empty():
                yield queue.get_nowait()

            yield {
                "type": "ideas_ready",
                "ideas": [i.model_dump() for i in ideas_model.ideas],
                "sources": all_sources,
                "token_usage": {
                    "input": entry.input_tokens,
                    "output": entry.output_tokens,
                    "cost_usd": entry.cost_usd,
                },
            }
        finally:
            sources_emitter_var.reset(token)
