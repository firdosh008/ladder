"""Exa search provider — thin async wrapper around exa-py.

exa-py ships a synchronous client. We wrap it in asyncio.to_thread so routes
and agents can await it without blocking the event loop.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from exa_py import Exa

from app.config import settings


@dataclass(frozen=True)
class ExaResult:
    title: str
    url: str
    text: str
    published_date: str | None
    score: float | None


_client: Exa | None = None


def _get_client() -> Exa:
    """Lazy-init. Raises if EXA_API_KEY is missing — crews must fail loudly."""
    global _client
    if _client is None:
        if not settings.EXA_API_KEY:
            raise RuntimeError(
                "EXA_API_KEY is not configured. Set it in backend/.env."
            )
        _client = Exa(api_key=settings.EXA_API_KEY)
    return _client


async def search(
    query: str,
    num_results: int = 8,
    include_text: bool = True,
) -> list[ExaResult]:
    """Run a neural web search via Exa and return normalised results."""
    client = _get_client()

    def _do_search() -> list[ExaResult]:
        resp = client.search_and_contents(
            query,
            num_results=num_results,
            text=include_text,
            type="neural",
        )
        out: list[ExaResult] = []
        for r in getattr(resp, "results", []) or []:
            text = getattr(r, "text", None) or ""
            out.append(
                ExaResult(
                    title=getattr(r, "title", "") or "",
                    url=getattr(r, "url", "") or "",
                    text=text[:2000],
                    published_date=getattr(r, "published_date", None),
                    score=getattr(r, "score", None),
                )
            )
        return out

    return await asyncio.to_thread(_do_search)
