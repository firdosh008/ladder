"""Pydantic models — Python-side mirrors of the Supabase tables.

Per-vertical structured outputs live here too. Keep prompt-facing schemas
narrow on purpose — every field present in a model is one the LLM is
asked to produce, so any field added here must justify its prompt budget.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ─── Profile / inputs ──────────────────────────────────────────────────────


class UserProfileSlice(BaseModel):
    """The fields agents interpolate into prompts.

    Kept minimal so prompts don't drift when the profile schema grows.
    """

    display_name: str | None = None
    positioning: str | None = None
    audience: str | None = None
    voice: str | None = None
    creators_followed: list[str] = Field(default_factory=list)
    things_to_avoid: str | None = None


class IdeaSlice(BaseModel):
    """Subset of an idea row passed into studio crews."""

    id: str | None = None
    title: str = Field(min_length=1, max_length=500)
    body: str | None = None
    rationale: str | None = None
    idea_type: Literal["systems", "framework", "pitch", "case_study"] | None = None
    opportunity_score: int | None = None
    source_type: str | None = None
    source_content: str | None = None  # research topic OR pasted source content


# ─── Research vertical ─────────────────────────────────────────────────────


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


# ─── Studio vertical (script + outline) ────────────────────────────────────


class ScriptSection(BaseModel):
    """One section of a video script — talking points + transition."""

    heading: str = Field(min_length=1, max_length=200)
    duration_min: int = Field(ge=1, le=15)
    talking_points: list[str] = Field(min_length=1, max_length=10)
    transition: str | None = Field(default=None, max_length=320)


class Script(BaseModel):
    """PRD §5: 'talking points per scene and transition statements (not
    word-for-word copy)'. We constrain to 2-12 sections so the studio UI
    fits and the LLM doesn't sprawl."""

    sections: list[ScriptSection] = Field(min_length=2, max_length=12)


class OutlineItem(BaseModel):
    """One row of the scene outline. Numbered for stable referencing in chat."""

    number: int = Field(ge=1)
    label: str = Field(min_length=1, max_length=160)
    beat: str = Field(min_length=1, max_length=480)


class Outline(BaseModel):
    """Numbered scene outline, generated AFTER the script settles so each
    item maps to a specific section + beat."""

    items: list[OutlineItem] = Field(min_length=3, max_length=18)


# ─── Content-extract vertical ──────────────────────────────────────────────


class ContentAnalysis(BaseModel):
    """Pre-flight analysis of pasted content. Drives duration + idea shape."""

    title: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=600)
    idea_type: Literal["systems", "framework", "pitch", "case_study"] = "framework"
    derived_duration_min: int = Field(ge=3, le=30)
    key_beats: list[str] = Field(min_length=3, max_length=10)


class ExtractedVideo(BaseModel):
    """Final structured output of the content_extract crew.

    Carries everything we need to create an idea + studio_session +
    script/outline artifacts in a single transaction.
    """

    title: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=600)
    idea_type: Literal["systems", "framework", "pitch", "case_study"] = "framework"
    derived_duration_min: int = Field(ge=3, le=30)
    script: Script
    outline: Outline
