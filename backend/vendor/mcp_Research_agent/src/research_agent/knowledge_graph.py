"""Caller context interfaces and optional persistent profile implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod

from research_agent.storage import get_creator_profile


class CreatorKG(ABC):
    """Abstract context interface. Projects can implement this when needed."""

    @abstractmethod
    async def get_user_context(self, user_id: str) -> dict:
        """Returns niche tags, past topics, audience description, and voice/tone."""
        ...

    @abstractmethod
    async def gap_score(self, topic: str, user_id: str) -> float:
        """0-1: how much this topic fills a gap in creator coverage."""
        ...

    @abstractmethod
    async def saturation_score(self, topic: str, user_id: str) -> float:
        """0-1: how much the creator has already covered this topic."""
        ...


class SimpleKG(CreatorKG):
    """In-memory context store for standalone runs and new callers with no history."""

    def __init__(self, user_data: dict | None = None):
        self._data = user_data or {}

    async def get_user_context(self, user_id: str) -> dict:
        return self._data.get(user_id, {
            "niche_tags": [],
            "past_topics": [],
            "audience_description": "General tech-interested audience, starting from zero.",
            "voice_tone": "Informative, accessible, opinionated but evidence-backed.",
        })

    async def gap_score(self, topic: str, user_id: str) -> float:
        ctx = await self.get_user_context(user_id)
        past = [t.lower() for t in ctx.get("past_topics", [])]
        topic_lower = topic.lower()

        for past_topic in past:
            if past_topic in topic_lower or topic_lower in past_topic:
                return 0.3
        return 0.8

    async def saturation_score(self, topic: str, user_id: str) -> float:
        ctx = await self.get_user_context(user_id)
        past = [t.lower() for t in ctx.get("past_topics", [])]
        topic_lower = topic.lower()

        matches = sum(1 for p in past if p in topic_lower or topic_lower in p)
        return min(1.0, matches * 0.3)


class SupabaseKG(CreatorKG):
    """Supabase HTTPS client-backed KG adapter.

    Expected table:
    creator_profiles(user_id text primary key, context_json jsonb not null)
    """

    def __init__(self):
        self._fallback = SimpleKG()

    async def get_user_context(self, user_id: str) -> dict:
        value = await get_creator_profile(user_id)
        if not value:
            return await self._fallback.get_user_context(user_id)
        return value

    async def gap_score(self, topic: str, user_id: str) -> float:
        return await SimpleKG({user_id: await self.get_user_context(user_id)}).gap_score(topic, user_id)

    async def saturation_score(self, topic: str, user_id: str) -> float:
        return await SimpleKG({user_id: await self.get_user_context(user_id)}).saturation_score(topic, user_id)


# Backwards-compatible alias for older imports. This is not direct Postgres.
PostgresKG = SupabaseKG
