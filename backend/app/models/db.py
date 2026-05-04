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
    # Founder-chosen target runtime (3-60 min). Set from /make's research
    # tile dropdown or the content_extract analyzer's derived duration. The
    # Studio crew uses it as the script_writer's `target_duration_min` when
    # the WS URL doesn't override it. Null = "let Studio default".
    target_duration_min: int | None = Field(default=None, ge=3, le=60)


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


# ─── Studio scene (Excalidraw skeleton) ────────────────────────────────────

# Map 1:1 to the @excalidraw/excalidraw `ExcalidrawElementSkeleton` shape.
# We persist this lean format and inflate it on the frontend via the official
# `convertToExcalidrawElements()` helper. PRD §5.5 / §11.4.

SceneElementType = Literal[
    "rectangle", "ellipse", "diamond", "text", "arrow", "line", "image"
]
SceneFrameKind = Literal[
    "title",
    "flow",
    "table",
    "decision",
    "architecture",
    "checklist",
    "diagram",
    "cta",
]


class SceneElementLabel(BaseModel):
    """Inline label on a shape (becomes a bound text element on inflate).

    Length cap is generous on purpose: Anthropic's structured-outputs grammar
    compiler doesn't enforce maxLength, so a tight Pydantic cap creates a
    visible/invisible-constraint mismatch (model produces fine output, we
    reject it). The designer prompt steers the model toward short captions;
    this cap is a sanity ceiling, not a UX guideline.

    ``fontFamily`` mirrors the field on ``SceneSkeletonElement`` so the
    bound caption rendered by ``convertToExcalidrawElements`` picks up the
    user-chosen typeface (without it the inflated text falls back to the
    Excalidraw default).
    """

    text: str = Field(min_length=1, max_length=2000)
    fontFamily: int | None = Field(default=None, ge=1, le=99)


class SceneElementBinding(BaseModel):
    """Reference to another scene element by id (for arrow start/end)."""

    id: str = Field(min_length=1, max_length=64)


class SceneSkeletonElement(BaseModel):
    """One ExcalidrawElementSkeleton row.

    Field names match the Excalidraw skeleton API verbatim (camelCase) so the
    frontend can hand the JSON to `convertToExcalidrawElements()` with no
    translation step.
    """

    id: str = Field(min_length=1, max_length=64)
    type: SceneElementType
    x: float
    y: float
    width: float = Field(ge=0, le=8000)
    height: float = Field(ge=0, le=8000)
    text: str | None = Field(default=None, max_length=4000)  # type='text'
    label: SceneElementLabel | None = None  # bound label on shapes
    strokeColor: str | None = None
    backgroundColor: str | None = None
    fillStyle: Literal["solid", "hachure", "cross-hatch"] | None = None
    strokeWidth: float | None = Field(default=None, ge=0.5, le=8)
    roughness: int | None = Field(default=None, ge=0, le=2)
    fontSize: int | None = Field(default=None, ge=10, le=72)
    fontFamily: int | None = Field(default=None, ge=1, le=99)
    start: SceneElementBinding | None = None  # arrow only
    end: SceneElementBinding | None = None  # arrow only
    fileId: str | None = Field(default=None, max_length=80)  # type='image'
    groupIds: list[str] | None = Field(default=None, max_length=8)


class SceneFrame(BaseModel):
    """One layout cell from the planner — bounding region for a frame.

    The element_designer fills each frame with the appropriate primitives
    (rect/diamond/arrow/text).
    """

    number: int = Field(ge=1)
    label: str = Field(min_length=1, max_length=160)
    kind: SceneFrameKind
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0, le=8000)
    height: float = Field(gt=0, le=8000)
    description: str = Field(min_length=1, max_length=1000)


class SceneLayout(BaseModel):
    """Planner output — overall canvas + per-frame regions.

    Drives the designer's spatial decisions. Critic consumes this to verify
    the designer respected the regions.
    """

    canvas_width: int = Field(ge=800, le=4800)
    canvas_height: int = Field(ge=600, le=4800)
    background_color: str = Field(default="#FFFFFF", max_length=12)
    flow_direction: Literal["left-to-right", "top-to-bottom"] = "top-to-bottom"
    frames: list[SceneFrame] = Field(min_length=2, max_length=12)


class SceneSkeleton(BaseModel):
    """Final scene artifact persisted to `artifacts.content_json`.

    The frontend reads this and calls `convertToExcalidrawElements(elements)`
    to render. The same elements + a Excalidraw header are uploaded to
    Storage on the user's request to produce an `excalidraw.com#url=...` link.
    """

    canvas_width: int = Field(ge=800, le=4800)
    canvas_height: int = Field(ge=600, le=4800)
    background_color: str = Field(default="#FFFFFF", max_length=12)
    elements: list[SceneSkeletonElement] = Field(min_length=2, max_length=240)
    notes: str | None = Field(default=None, max_length=4000)
    #: Binary payloads for ``image`` elements — Excalidraw ``files`` map (fileId → metadata).
    files: dict[str, dict[str, str | int]] | None = Field(default=None)
