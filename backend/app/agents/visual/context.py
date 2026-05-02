"""Per-request context loader for the studio visual agent.

The agent needs the founder's idea + script + outline + brand + profile
hydrated before its first turn. This module owns that load (RLS-respecting
reads via the user-scoped client) so both the build flow and the sharpen
flow can share one entry point.

Returned shape (``SessionContext``) is a Pydantic model — small enough to
embed directly into the agent's system prompt and serialise into events.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.deps import user_client
from app.models.db import IdeaSlice, Outline, Script, UserProfileSlice

log = logging.getLogger(__name__)


class BrandSlice(BaseModel):
    """Brand row reduced to what the agent uses in prompts."""

    id: str | None = None
    name: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None


class SessionContext(BaseModel):
    """Everything the visual agent needs at boot.

    Held alongside the WS connection — never re-fetched mid-stream. If the
    user updates the script or outline in the left pane during a chat turn,
    the next turn's :func:`load_session_context` call picks it up.
    """

    user_id: str
    jwt: str = Field(repr=False)
    session_id: str
    idea: IdeaSlice
    profile: UserProfileSlice
    script: Script | None = None
    outline: Outline | None = None
    brand: BrandSlice | None = None

    def to_prompt_block(self) -> str:
        """Render a compact prose block for the agent's system prompt.

        Kept terse on purpose — full skill methodology is what eats the
        token budget; this is just the anchoring facts.
        """
        lines = [
            f"Idea: {self.idea.title}",
        ]
        if self.idea.rationale:
            lines.append(f"Rationale: {self.idea.rationale}")
        if self.profile.positioning:
            lines.append(f"Founder positioning: {self.profile.positioning}")
        if self.profile.audience:
            lines.append(f"Audience: {self.profile.audience}")
        if self.brand and self.brand.primary_color:
            lines.append(
                f"Brand: {self.brand.name or 'unnamed'} "
                f"(primary {self.brand.primary_color})"
            )
        if self.script:
            lines.append(f"Script: {len(self.script.sections)} sections.")
        if self.outline:
            lines.append(f"Outline: {len(self.outline.items)} items.")
        return "\n".join(lines)


# ─── Loaders ──────────────────────────────────────────────────────────────


async def _load_brand(brand_id: str | None, jwt: str) -> BrandSlice | None:
    if not brand_id:
        return None
    client = await user_client(jwt)
    resp = (
        await client.from_("brands")
        .select("id, name, primary_color, secondary_color")
        .eq("id", brand_id)
        .maybe_single()
        .execute()
    )
    data = resp.data if resp is not None else None
    if not data:
        return None
    return BrandSlice(
        id=str(data["id"]),
        name=data.get("name"),
        primary_color=data.get("primary_color"),
        secondary_color=data.get("secondary_color"),
    )


async def _load_session_row(session_id: str, jwt: str) -> dict[str, Any] | None:
    client = await user_client(jwt)
    resp = (
        await client.from_("studio_sessions")
        .select(
            "id, idea_id, brand_id, target_duration_min, "
            "scene_outline, status"
        )
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    return resp.data if resp is not None else None


async def _load_idea_slice(idea_id: str, jwt: str) -> IdeaSlice | None:
    client = await user_client(jwt)
    resp = (
        await client.from_("ideas")
        .select(
            "id, title, body, rationale, idea_type, opportunity_score, "
            "source_type, source_content, target_duration_min"
        )
        .eq("id", idea_id)
        .maybe_single()
        .execute()
    )
    data = resp.data if resp is not None else None
    if not data:
        return None
    return IdeaSlice(
        id=str(data["id"]),
        title=data["title"],
        body=data.get("body"),
        rationale=data.get("rationale"),
        idea_type=data.get("idea_type"),
        opportunity_score=data.get("opportunity_score"),
        source_type=data.get("source_type"),
        source_content=data.get("source_content"),
        target_duration_min=data.get("target_duration_min"),
    )


async def _load_profile_slice(user_id: UUID, jwt: str) -> UserProfileSlice:
    client = await user_client(jwt)
    resp = (
        await client.from_("user_profiles")
        .select(
            "display_name, positioning, audience, voice, "
            "creators_followed, things_to_avoid"
        )
        .eq("user_id", str(user_id))
        .maybe_single()
        .execute()
    )
    data = resp.data if resp is not None else None
    data = data or {}
    return UserProfileSlice(
        display_name=data.get("display_name"),
        positioning=data.get("positioning"),
        audience=data.get("audience"),
        voice=data.get("voice"),
        creators_followed=data.get("creators_followed") or [],
        things_to_avoid=data.get("things_to_avoid"),
    )


async def _load_latest_artifact(
    session_id: str, jwt: str, artifact_type: str
) -> dict[str, Any] | None:
    client = await user_client(jwt)
    resp = (
        await client.from_("artifacts")
        .select("content_json")
        .eq("session_id", session_id)
        .eq("type", artifact_type)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    raw = resp.data[0].get("content_json")
    return raw if isinstance(raw, dict) else None


async def load_session_context(
    user_id: UUID,
    jwt: str,
    session_id: str,
) -> SessionContext:
    """Hydrate the agent's session context from Supabase.

    Raises :class:`ValueError` when the session or its idea is not found —
    the caller should close the WS with code 4400.
    """
    session_row = await _load_session_row(session_id, jwt)
    if not session_row:
        raise ValueError(f"studio session {session_id} not found")

    idea_id = session_row.get("idea_id")
    if not idea_id:
        raise ValueError(
            f"studio session {session_id} has no idea_id (orphaned session)"
        )

    idea = await _load_idea_slice(str(idea_id), jwt)
    if not idea:
        raise ValueError(f"idea {idea_id} not found for session {session_id}")

    profile = await _load_profile_slice(user_id, jwt)
    brand = await _load_brand(session_row.get("brand_id"), jwt)

    script_json = await _load_latest_artifact(session_id, jwt, "script")
    outline_json = await _load_latest_artifact(session_id, jwt, "outline")

    script = Script.model_validate(script_json) if script_json else None
    outline = Outline.model_validate(outline_json) if outline_json else None

    return SessionContext(
        user_id=str(user_id),
        jwt=jwt,
        session_id=session_id,
        idea=idea,
        profile=profile,
        script=script,
        outline=outline,
        brand=brand,
    )


__all__ = ["BrandSlice", "SessionContext", "load_session_context"]
