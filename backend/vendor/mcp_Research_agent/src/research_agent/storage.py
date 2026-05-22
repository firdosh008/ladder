"""Supabase HTTPS persistence layer for research runs.

This module intentionally does not use direct Postgres sockets, SQLAlchemy,
asyncpg, psycopg2, Supabase poolers, or DATABASE_URL. It uses the Supabase
Python client over HTTPS so local networks that block database ports can still
persist runs.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any

from research_agent.config import settings
from research_agent.models import ResearchResult

logger = logging.getLogger(__name__)

_client = None
_init_failed = False


async def init_storage() -> bool:
    """Initialize Supabase client. Returns False when credentials/package are unavailable."""
    return await asyncio.to_thread(_init_storage_sync)


async def save_research_result(
    result: ResearchResult,
    query: str = "",
    user_id: str = "",
    product: str = "",
) -> bool:
    client = await get_supabase_client()
    if not client:
        return False

    payload = _to_jsonable(result)
    row = {
        "run_id": result.run_id,
        "user_id": user_id,
        "product": product,
        "query": query,
        "status": result.status,
        "total_cost": result.cost_breakdown.total,
        "duration_seconds": result.cost_breakdown.duration_seconds,
        "sources_count": len(result.sources),
        "result_json": payload,
        "updated_at": datetime.now(UTC).isoformat(),
    }

    try:
        await asyncio.to_thread(
            lambda: client.table("research_runs").upsert(row, on_conflict="run_id").execute()
        )
        return True
    except Exception as e:
        logger.warning(f"Supabase save failed; falling back to memory only: {type(e).__name__}: {e}")
        return False


async def get_research_result(run_id: str) -> dict[str, Any] | None:
    client = await get_supabase_client()
    if not client:
        return None

    try:
        resp = await asyncio.to_thread(
            lambda: client.table("research_runs").select("result_json").eq("run_id", run_id).limit(1).execute()
        )
        if not resp.data:
            return None
        return resp.data[0].get("result_json")
    except Exception as e:
        logger.warning(f"Supabase fetch failed: {type(e).__name__}: {e}")
        return None


async def recent_costs(limit: int = 500) -> list[dict[str, Any]]:
    client = await get_supabase_client()
    if not client:
        return []

    try:
        resp = await asyncio.to_thread(
            lambda: client.table("research_runs")
            .select("run_id,total_cost,duration_seconds,status,created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.warning(f"Supabase cost summary fetch failed: {type(e).__name__}: {e}")
        return []


async def get_creator_profile(user_id: str) -> dict | None:
    client = await get_supabase_client()
    if not client:
        return None

    try:
        resp = await asyncio.to_thread(
            lambda: client.table("creator_profiles").select("context_json").eq("user_id", user_id).limit(1).execute()
        )
        if not resp.data:
            return None
        return resp.data[0].get("context_json")
    except Exception as e:
        logger.warning(f"Supabase creator profile fetch failed: {type(e).__name__}: {e}")
        return None


async def get_supabase_client():
    if await init_storage():
        return _client
    return None


def _init_storage_sync() -> bool:
    global _client, _init_failed
    if _client:
        return True
    if _init_failed:
        return False

    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.info("Supabase storage disabled; SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing.")
        _init_failed = True
        return False

    try:
        from supabase import create_client

        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        return True
    except Exception as e:
        _init_failed = True
        logger.warning(f"Supabase storage unavailable; falling back to memory: {type(e).__name__}: {e}")
        return False


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value
