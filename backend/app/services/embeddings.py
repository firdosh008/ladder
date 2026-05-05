"""Shared embedding helper — OpenAI text-embedding-3-small (1536d)."""

from __future__ import annotations

import logging

from app.config import settings

log = logging.getLogger(__name__)


async def generate_embedding(text: str) -> list[float] | None:
    """Return a 1536-d embedding vector, or None if no OpenAI key is configured."""
    if not settings.OPENAI_API_KEY:
        log.warning("OPENAI_API_KEY not configured — skipping embedding generation")
        return None

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        resp = await client.embeddings.create(
            input=text[:8000],  # model max token limit safety
            model="text-embedding-3-small",
        )
        return resp.data[0].embedding
    except Exception:
        log.exception("Embedding generation failed")
        return None
