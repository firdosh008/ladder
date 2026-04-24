"""Tools exposed to the Research crew.

CrewAI's BaseTool runs synchronously from the agent's perspective. We bridge
to our async Exa provider with asyncio.run-in-a-dedicated-loop so the crew
(which is itself invoked from an asyncio task) doesn't double-loop.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from app.agents.research.streaming import SourceRef, sources_emitter_var
from app.providers import exa


class _ExaSearchInput(BaseModel):
    query: str = Field(description="Natural-language web search query.")
    num_results: int = Field(default=8, ge=1, le=20)


class ExaSearchTool(BaseTool):
    name: str = "web_search"
    description: str = (
        "Search the public web for recent articles, posts, and discussions via "
        "Exa's neural search. Returns a JSON list of {title, url, text, "
        "published_date, score}. Use for trend discovery. Cite the `url` field "
        "verbatim in downstream outputs."
    )
    args_schema: type[BaseModel] = _ExaSearchInput

    def _run(self, query: str, num_results: int = 8) -> str:
        results = asyncio.run(exa.search(query=query, num_results=num_results))

        emitter = sources_emitter_var.get()
        if emitter is not None:
            emitter(
                query,
                [
                    SourceRef(
                        title=r.title,
                        url=r.url,
                        published_date=r.published_date,
                        snippet=(r.text or "")[:220] or None,
                    )
                    for r in results
                ],
            )

        payload: list[dict[str, Any]] = [
            {
                "title": r.title,
                "url": r.url,
                "text": r.text,
                "published_date": r.published_date,
                "score": r.score,
            }
            for r in results
        ]
        return json.dumps(payload, ensure_ascii=False)
