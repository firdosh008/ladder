"""Usage logger — writes a row to usage_log for every agent run.

Per backend-dys.md cardinal rule: every Python endpoint that touches an LLM
writes to usage_log with provider, model, tokens, cost_usd, latency_ms. The
service client is used because usage_log is an admin-owned signal.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import AsyncIterator
from uuid import UUID

from app.deps import service_client


@dataclass
class UsageEntry:
    user_id: str
    function_name: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


@asynccontextmanager
async def log_usage(
    user_id: UUID | str,
    function_name: str,
    model: str,
    provider: str,
) -> AsyncIterator[UsageEntry]:
    """Context-manage an agent call. Caller mutates `entry` with token counts
    and cost during the run; this wrapper measures latency and writes the row
    on exit regardless of exception."""
    started = perf_counter()
    entry = UsageEntry(
        user_id=str(user_id),
        function_name=function_name,
        model=model,
        provider=provider,
    )
    try:
        yield entry
    finally:
        entry.latency_ms = int((perf_counter() - started) * 1000)
        try:
            sb = await service_client()
            await sb.from_("usage_log").insert(asdict(entry)).execute()
        except Exception:
            # Never let logging failure surface to the caller — the agent run
            # already succeeded (or failed) on its own terms.
            pass
