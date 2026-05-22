"""Side-channel for tools to publish structured events back to the crew runner.

CrewAI's native streaming (`Crew(stream=True)` + `await crew.akickoff()`) yields
LLM text + tool-call chunks — but the *results* of a tool call are consumed by
CrewAI internally and never surface in the stream. We need the search results
(titles + URLs) on the wire so the UI can show real source cards.

Pattern: a ContextVar holds an emitter callable scoped to a single crew run.
The tool reads it synchronously from whatever thread it runs in (ContextVars
propagate through `asyncio.to_thread` and `run_in_executor` via
`contextvars.copy_context`). The emitter marshals onto the asyncio loop via
`loop.call_soon_threadsafe`.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

Platform = Literal["web", "reddit", "youtube", "x", "instagram"]


@dataclass(frozen=True)
class SourceRef:
    """A single source discovered by a search tool during a crew run.

    `thumbnail` and `meta` are platform-specific previews so the UI can show
    real cards (YT thumbnail, tweet engagement, Reddit score, ...) instead of
    bare URL chips. Older clients ignore these fields safely.
    """

    title: str
    url: str
    published_date: str | None = None
    snippet: str | None = None
    platform: Platform = "web"
    thumbnail: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


SourcesEmitter = Callable[[str, list[SourceRef]], None]

sources_emitter_var: ContextVar[SourcesEmitter | None] = ContextVar(
    "ladder_research_sources_emitter",
    default=None,
)
