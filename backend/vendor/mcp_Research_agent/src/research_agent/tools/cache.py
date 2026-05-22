"""Small async cache helper.

Uses Redis when available and falls back to process memory for local/dev runs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

import httpx

from research_agent.config import settings

logger = logging.getLogger(__name__)

_memory_cache: dict[str, tuple[float, Any]] = {}
_redis_client = None
_redis_failed = False
_upstash_failed = False


def make_cache_key(namespace: str, *parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"research_agent:{namespace}:{digest}"


async def get_json(key: str) -> Any | None:
    now = time.time()
    if key in _memory_cache:
        expires_at, value = _memory_cache[key]
        if expires_at > now:
            return value
        del _memory_cache[key]

    if settings.upstash_redis_rest_url and settings.upstash_redis_rest_token:
        return await _upstash_get_json(key)

    client = await _get_redis()
    if not client:
        return None

    try:
        cached = await client.get(key)
    except Exception as e:
        logger.warning(f"Redis cache read failed: {e}")
        return None

    if not cached:
        return None
    return json.loads(cached)


async def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    _memory_cache[key] = (time.time() + ttl_seconds, value)

    if settings.upstash_redis_rest_url and settings.upstash_redis_rest_token:
        await _upstash_set_json(key, value, ttl_seconds)
        return

    client = await _get_redis()
    if not client:
        return

    try:
        await client.set(key, json.dumps(value, default=str), ex=ttl_seconds)
    except Exception as e:
        logger.warning(f"Redis cache write failed: {e}")


async def _upstash_get_json(key: str) -> Any | None:
    global _upstash_failed
    if _upstash_failed:
        return None

    try:
        resp = await _upstash_request("GET", key)
        result = resp.get("result")
        return json.loads(result) if result else None
    except Exception as e:
        _upstash_failed = True
        logger.warning(f"Upstash cache read failed; using memory cache only: {e}")
        return None


async def _upstash_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    global _upstash_failed
    if _upstash_failed:
        return

    try:
        await _upstash_request("SET", key, json.dumps(value, default=str), "EX", str(ttl_seconds))
    except Exception as e:
        _upstash_failed = True
        logger.warning(f"Upstash cache write failed; using memory cache only: {e}")


async def _upstash_request(*command: str) -> dict:
    base_url = settings.upstash_redis_rest_url.rstrip("/")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            base_url,
            headers={"Authorization": f"Bearer {settings.upstash_redis_rest_token}"},
            json=list(command),
        )
        resp.raise_for_status()
        return resp.json()


async def _get_redis():
    global _redis_client, _redis_failed
    if not settings.redis_url:
        return None
    if _redis_failed:
        return None
    if _redis_client:
        return _redis_client

    try:
        import redis.asyncio as redis

        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        await _redis_client.ping()
        return _redis_client
    except Exception as e:
        _redis_failed = True
        logger.info(f"Redis unavailable; using in-memory cache fallback: {e}")
        return None
