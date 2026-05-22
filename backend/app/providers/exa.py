"""Exa search provider — thin async wrapper around exa-py.

exa-py ships a synchronous client. We wrap it in asyncio.to_thread so routes
and agents can await it without blocking the event loop.

Freshness: by default we constrain results to the last 90 days via
`start_published_date`. The Research crew is for *trend* discovery — old
papers and 2023 listicles drown out current signal otherwise.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

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

_DEFAULT_FRESHNESS_DAYS = 90


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


def _default_start_date() -> str:
    """ISO date for `start_published_date`, defaulting to 90 days ago (UTC)."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_DEFAULT_FRESHNESS_DAYS)
    return cutoff.strftime("%Y-%m-%dT00:00:00.000Z")


async def search(
    query: str,
    num_results: int = 8,
    include_text: bool = True,
    start_published_date: str | None = None,
) -> list[ExaResult]:
    """Run a neural web search via Exa and return normalised results.

    `start_published_date` defaults to 90 days ago so the crew sees current
    signal (not old academic papers). Pass an explicit ISO date string to
    override, or `""` to disable the filter entirely.
    """
    client = _get_client()
    cutoff = (
        start_published_date
        if start_published_date is not None
        else _default_start_date()
    )

    def _do_search() -> list[ExaResult]:
        kwargs: dict = {
            "num_results": num_results,
            "text": include_text,
            "type": "neural",
        }
        if cutoff:
            kwargs["start_published_date"] = cutoff
        resp = client.search_and_contents(query, **kwargs)
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
