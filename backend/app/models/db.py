"""Pydantic models — Python-side mirrors of the Supabase tables.

Subset for the Research vertical. Expand per-vertical as crews are added.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class UserProfileSlice(BaseModel):
    """The fields the Research crew interpolates into agent prompts.

    Kept minimal so prompts don't drift when the profile schema grows.
    """

    display_name: str | None = None
    positioning: str | None = None
    audience: str | None = None
    voice: str | None = None
    creators_followed: list[str] = Field(default_factory=list)
    things_to_avoid: str | None = None


class IdeaDraft(BaseModel):
    """A single research-agent idea before it is persisted.

    Shape matches PRD §11.8 research_agent output. `body` is NOT produced by
    the agent — it's reserved for the user's own notes once they accept the
    idea into studio.
    """

    title: str = Field(min_length=1, max_length=500)
    rationale: str | None = None
    idea_type: Literal["systems", "framework", "pitch", "case_study"] | None = None
    opportunity_score: int | None = Field(default=None, ge=0, le=100)
    outlier_score: float | None = Field(default=None, ge=0, le=10)
    why_now: str | None = Field(default=None, max_length=280)
    suggested_tags: list[str] = Field(default_factory=list)


class ResearchIdeas(BaseModel):
    """Structured output of the idea_formulator task."""

    ideas: list[IdeaDraft] = Field(min_length=1, max_length=8)
