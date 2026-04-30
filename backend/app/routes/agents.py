"""Agent WebSocket routes.

Four endpoints today:

  /ws/agents/research?token=...&topic=...
        Streams the Research crew. Drafts are NOT auto-persisted —
        the user picks one inline, frontend POSTs to /ideas.

  /ws/agents/studio?token=...&idea_id=...&duration=...
        Streams the Studio crew (script_writer → outline_planner) for an
        existing idea. On completion: upserts a studio_sessions row for
        (user_id, idea_id), writes script + outline as artifacts (versioned),
        and emits {type:'persisted', session_id, script_artifact_id,
        outline_artifact_id}.

  /ws/agents/extract?token=...
        Streams the content_extract crew. The client sends the source as
        the FIRST WS message (JSON {source_content: "..."}). On completion:
        creates an idea + studio_session + script + outline artifacts and
        emits {type:'persisted', idea_id, session_id, ...} so the client
        can navigate to /studio/:idea_id.

  /ws/agents/scene?token=...&session_id=...&brand_accent=RRGGBB (optional hex, no #)
        Streams the Scene crew (layout_planner → element_designer) over an
        existing studio session. On completion: writes a versioned
        `excalidraw` artifact and emits {type:'persisted', session_id,
        scene_artifact_id}.

Common event protocol:
  {"type": "agent_start",    "agent": "..."}
  {"type": "tool_call",      "agent": "...", "tool": "...", "arguments": "..."}
  {"type": "sources",        "query": "...", "items": [...]}      # research only
  {"type": "text_delta",     "agent": "...", "content": "..."}
  {"type": "task_complete",  "agent": "...", "preview": "..."}
  {"type": "ideas_ready",    "ideas": [...], "token_usage": {...}} # research
  {"type": "script_ready",   "script": {...}}                      # studio
  {"type": "outline_ready",  "outline": {...}}                     # studio
  {"type": "extract_ready",  "extracted": {...}}                   # extract
  {"type": "scene_ready",    "scene": {...}}                       # scene
  {"type": "usage",          "token_usage": {...}}
  {"type": "persisted",      ...}                                  # studio/extract/scene
  {"type": "complete",       "cost_usd": 0.07}
  {"type": "error",          "message": "..."}
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState

from app.agents.content_extract import run_content_extract
from app.agents.research import run_research
from app.agents.scene import run_scene_build
from app.agents.studio import run_studio_script
from app.deps import user_client
from app.middleware.ws_auth import WsAuthError, verify_ws_token
from app.models.db import IdeaSlice, Outline, Script, UserProfileSlice

router = APIRouter(tags=["agents"])

log = logging.getLogger(__name__)

_HEX_7 = re.compile(r"^#[0-9a-fA-F]{6}$")
_HEX_3 = re.compile(r"^#[0-9a-fA-F]{3}$")
_HEX_8 = re.compile(r"^#[0-9a-fA-F]{8}$")


def _normalize_brand_hex(v: Any) -> str | None:
    """Normalize session/brand color cells to uppercase #RRGGBB for scene design.

    Accepts common variants: missing ``#``, 3-digit shorthand, 8-digit with alpha
    (strips alpha). Fails closed to None so callers can fall back explicitly.
    """
    if v is None:
        return None
    if not isinstance(v, str):
        v = str(v)
    s = v.strip()
    if not s:
        return None
    cand = s if s.startswith("#") else f"#{s}"
    cand_u = cand.upper()
    # #RRGGBBAA (8 hex after #)
    if _HEX_8.match(cand_u):
        cand_u = "#" + cand_u[1:7]
    if _HEX_7.match(cand_u):
        return cand_u
    if _HEX_3.match(cand_u):
        r, g, b = cand_u[1], cand_u[2], cand_u[3]
        return f"#{r}{r}{g}{g}{b}{b}".upper()
    # Last resort: scrape a 6-digit hex substring (e.g. pasted CSS noise)
    m = re.search(r"#?([0-9a-fA-F]{6})\b", s, flags=re.I)
    if m:
        h = "#" + m.group(1).upper()
        return h if _HEX_7.match(h) else None
    return None


# WebSocket close codes (application-level 4xxx range)
_CLOSE_UNAUTHORIZED = 4401
_CLOSE_BAD_REQUEST = 4400
_CLOSE_SERVER_ERROR = 1011

_MAX_SOURCE_CONTENT_CHARS = 60_000


# ─── Helpers ───────────────────────────────────────────────────────────────


async def _load_profile(user_id: UUID, jwt: str) -> UserProfileSlice:
    """Read the caller's profile subset via the user-scoped (RLS) client."""
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


async def _load_idea(idea_id: str, jwt: str) -> IdeaSlice | None:
    """Fetch an idea row (RLS-scoped) and reduce it to the studio slice."""
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


async def _load_session(jwt: str, session_id: str) -> dict[str, Any] | None:
    """Fetch a studio_sessions row (RLS-scoped) for the scene crew.

    Uses ``select('*')`` so Postgres does not require any single optional column
    (e.g. ``brand_color`` before migration 20260429000001 is applied).
    """
    client = await user_client(jwt)
    resp = (
        await client.from_("studio_sessions")
        .select("*")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    return resp.data if resp is not None else None


async def _resolve_scene_brand_color(
    jwt: str,
    session: dict[str, Any],
) -> str | None:
    """Accent for Excalidraw scene design: session override, else linked brand.

    Order: ``studio_sessions.brand_color`` (valid hex) wins; otherwise fetch
    ``brands.primary_color`` via ``studio_sessions.brand_id``.
    """
    from_session = _normalize_brand_hex(session.get("brand_color"))
    if from_session:
        return from_session

    bid = session.get("brand_id")
    if bid is None or bid == "":
        return None

    client = await user_client(jwt)
    resp = (
        await client.from_("brands")
        .select("primary_color")
        .eq("id", str(bid))
        .maybe_single()
        .execute()
    )
    row = resp.data if resp is not None else None
    if not row:
        return None
    raw_pc = row.get("primary_color")
    resolved = _normalize_brand_hex(raw_pc)
    if resolved is None and raw_pc is not None and str(raw_pc).strip() != "":
        log.warning(
            "could not normalize brands.primary_color for brand_id=%s (raw=%r)",
            bid,
            raw_pc,
        )
    return resolved


async def _load_latest_artifact(
    jwt: str,
    session_id: str,
    artifact_type: str,
) -> dict[str, Any] | None:
    """Return the latest-version artifact row of a given type for a session."""
    client = await user_client(jwt)
    resp = (
        await client.from_("artifacts")
        .select("id, type, version, content_json")
        .eq("session_id", session_id)
        .eq("type", artifact_type)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


async def _ensure_studio_session(
    user_id: UUID,
    jwt: str,
    idea_id: str,
    target_duration_min: int,
) -> str:
    """Return the studio_sessions.id for (user_id, idea_id), creating if missing.

    If a session already exists but the founder has since picked a new
    runtime (via the duration control on /studio), refresh the row's
    `target_duration_min` so downstream crews — notably the scene crew,
    which reads from `studio_sessions` — see the up-to-date value rather
    than the duration this session was originally created with.
    """
    client = await user_client(jwt)
    existing = (
        await client.from_("studio_sessions")
        .select("id, target_duration_min")
        .eq("idea_id", idea_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if existing.data:
        row = existing.data[0]
        session_id = str(row["id"])
        if row.get("target_duration_min") != target_duration_min:
            await (
                client.from_("studio_sessions")
                .update({"target_duration_min": target_duration_min})
                .eq("id", session_id)
                .execute()
            )
        return session_id

    insert = (
        await client.from_("studio_sessions")
        .insert(
            {
                "user_id": str(user_id),
                "idea_id": idea_id,
                "target_duration_min": target_duration_min,
                "status": "active",
            }
        )
        .execute()
    )
    if not insert.data:
        raise RuntimeError("studio_sessions insert returned no row")
    return str(insert.data[0]["id"])


def _script_to_text(script: dict[str, Any]) -> str:
    """Flat-text rendering of a Script for content_text and previews."""
    lines: list[str] = []
    for i, sec in enumerate(script.get("sections") or [], start=1):
        lines.append(f"{i}. {sec.get('heading','')} ({sec.get('duration_min','?')} min)")
        for tp in sec.get("talking_points") or []:
            lines.append(f"  • {tp}")
        if sec.get("transition"):
            lines.append(f"  → {sec['transition']}")
        lines.append("")
    return "\n".join(lines).strip()


def _outline_to_text(outline: dict[str, Any]) -> str:
    lines: list[str] = []
    for it in outline.get("items") or []:
        lines.append(f"{it.get('number','?')}. {it.get('label','')} — {it.get('beat','')}")
    return "\n".join(lines).strip()


async def _next_artifact_version(
    jwt: str,
    session_id: str,
    artifact_type: str,
) -> int:
    client = await user_client(jwt)
    resp = (
        await client.from_("artifacts")
        .select("version")
        .eq("session_id", session_id)
        .eq("type", artifact_type)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    if resp.data:
        return int(resp.data[0]["version"]) + 1
    return 1


async def _persist_script_outline(
    user_id: UUID,
    jwt: str,
    session_id: str,
    script: dict[str, Any],
    outline: dict[str, Any],
) -> tuple[str, str]:
    """Insert versioned script + outline artifacts. Returns (script_id, outline_id)."""
    client = await user_client(jwt)

    script_version = await _next_artifact_version(jwt, session_id, "script")
    outline_version = await _next_artifact_version(jwt, session_id, "outline")

    rows = [
        {
            "user_id": str(user_id),
            "session_id": session_id,
            "type": "script",
            "version": script_version,
            "content_text": _script_to_text(script),
            "content_json": script,
        },
        {
            "user_id": str(user_id),
            "session_id": session_id,
            "type": "outline",
            "version": outline_version,
            "content_text": _outline_to_text(outline),
            "content_json": outline,
        },
    ]
    inserted = await client.from_("artifacts").insert(rows).execute()
    if not inserted.data or len(inserted.data) != 2:
        raise RuntimeError("artifacts insert did not return both rows")

    script_id = next(r["id"] for r in inserted.data if r["type"] == "script")
    outline_id = next(r["id"] for r in inserted.data if r["type"] == "outline")

    # Mirror outline as plain text on the session for the kanban preview.
    await (
        client.from_("studio_sessions")
        .update({"scene_outline": _outline_to_text(outline)})
        .eq("id", session_id)
        .execute()
    )
    return str(script_id), str(outline_id)


async def _persist_scene_skeleton(
    user_id: UUID,
    jwt: str,
    session_id: str,
    scene: dict[str, Any],
) -> str:
    """Insert a versioned `excalidraw` artifact. Returns the new artifact id."""
    client = await user_client(jwt)
    version = await _next_artifact_version(jwt, session_id, "excalidraw")
    el_count = len(scene.get("elements") or [])
    summary = (
        f"Scene skeleton — {el_count} elements on a "
        f"{scene.get('canvas_width')}×{scene.get('canvas_height')} canvas."
    )
    inserted = (
        await client.from_("artifacts")
        .insert(
            {
                "user_id": str(user_id),
                "session_id": session_id,
                "type": "excalidraw",
                "version": version,
                "content_text": summary,
                "content_json": scene,
            }
        )
        .execute()
    )
    if not inserted.data:
        raise RuntimeError("scene artifact insert returned no row")
    return str(inserted.data[0]["id"])


async def _safe_send_json(ws: WebSocket, payload: dict[str, Any]) -> bool:
    if ws.application_state != WebSocketState.CONNECTED:
        return False
    try:
        await ws.send_json(payload)
        return True
    except Exception:
        return False


# ─── /ws/agents/research ───────────────────────────────────────────────────


@router.websocket("/ws/agents/research")
async def research_stream(
    websocket: WebSocket,
    token: str | None = None,
    topic: str | None = None,
    duration: int | None = None,
) -> None:
    await websocket.accept()

    try:
        user_id, jwt = await verify_ws_token(token)
    except WsAuthError as e:
        await websocket.close(code=_CLOSE_UNAUTHORIZED, reason=str(e))
        return

    cleaned_topic = (topic or "").strip()
    if not cleaned_topic or len(cleaned_topic) > 500:
        await websocket.close(
            code=_CLOSE_BAD_REQUEST,
            reason="topic must be 1-500 chars",
        )
        return

    # Founder-chosen runtime gates how the idea_formulator scopes each draft.
    # Out-of-range or missing values quietly snap to the default so a stale
    # client can't break the run.
    target_duration_min = duration if duration and 3 <= duration <= 60 else 10

    try:
        profile = await _load_profile(user_id, jwt)
    except Exception as e:
        await _safe_send_json(
            websocket, {"type": "error", "message": f"profile load failed: {e}"}
        )
        await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    draft_count = 0
    cost_usd = 0.0

    try:
        async for event in run_research(
            user_id, profile, cleaned_topic, target_duration_min
        ):
            if event.get("type") == "ideas_ready":
                token_usage = event.get("token_usage") or {}
                cost_usd = float(token_usage.get("cost_usd") or 0.0)
                draft_count = len(event.get("ideas") or [])
            await _safe_send_json(websocket, event)
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        raise
    except Exception as e:
        await _safe_send_json(
            websocket, {"type": "error", "message": f"crew failed: {e}"}
        )
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    await _safe_send_json(
        websocket,
        {"type": "complete", "count": draft_count, "cost_usd": cost_usd},
    )
    if websocket.application_state == WebSocketState.CONNECTED:
        await websocket.close()


# ─── /ws/agents/studio ─────────────────────────────────────────────────────


@router.websocket("/ws/agents/studio")
async def studio_stream(
    websocket: WebSocket,
    token: str | None = None,
    idea_id: str | None = None,
    duration: int | None = None,
) -> None:
    await websocket.accept()

    try:
        user_id, jwt = await verify_ws_token(token)
    except WsAuthError as e:
        await websocket.close(code=_CLOSE_UNAUTHORIZED, reason=str(e))
        return

    if not idea_id:
        await websocket.close(code=_CLOSE_BAD_REQUEST, reason="idea_id required")
        return

    try:
        idea = await _load_idea(idea_id, jwt)
    except Exception as e:
        await _safe_send_json(
            websocket, {"type": "error", "message": f"idea load failed: {e}"}
        )
        await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    if idea is None:
        await websocket.close(code=_CLOSE_BAD_REQUEST, reason="idea not found")
        return

    # Resolution order: explicit URL override → idea row's stored preference
    # → 20-minute default. URL value still must be in-range to win.
    if duration and 3 <= duration <= 60:
        target_duration_min = duration
    elif idea.target_duration_min and 3 <= idea.target_duration_min <= 60:
        target_duration_min = idea.target_duration_min
    else:
        target_duration_min = 20

    try:
        profile = await _load_profile(user_id, jwt)
    except Exception as e:
        await _safe_send_json(
            websocket, {"type": "error", "message": f"profile load failed: {e}"}
        )
        await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    cost_usd = 0.0
    last_script: dict[str, Any] | None = None
    last_outline: dict[str, Any] | None = None

    try:
        async for event in run_studio_script(
            user_id, profile, idea, target_duration_min
        ):
            t = event.get("type")
            if t == "script_ready":
                last_script = event.get("script")
            elif t == "outline_ready":
                last_outline = event.get("outline")
            elif t == "usage":
                cost_usd = float((event.get("token_usage") or {}).get("cost_usd") or 0.0)
            await _safe_send_json(websocket, event)
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        raise
    except Exception as e:
        await _safe_send_json(
            websocket, {"type": "error", "message": f"crew failed: {e}"}
        )
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    if last_script is None or last_outline is None:
        await _safe_send_json(
            websocket,
            {"type": "error", "message": "studio crew did not produce script + outline"},
        )
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    try:
        session_id = await _ensure_studio_session(
            user_id, jwt, idea_id, target_duration_min
        )
        script_artifact_id, outline_artifact_id = await _persist_script_outline(
            user_id, jwt, session_id, last_script, last_outline
        )
    except Exception as e:
        await _safe_send_json(
            websocket, {"type": "error", "message": f"persist failed: {e}"}
        )
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    await _safe_send_json(
        websocket,
        {
            "type": "persisted",
            "session_id": session_id,
            "idea_id": idea_id,
            "script_artifact_id": script_artifact_id,
            "outline_artifact_id": outline_artifact_id,
        },
    )
    await _safe_send_json(
        websocket,
        {"type": "complete", "cost_usd": cost_usd},
    )
    if websocket.application_state == WebSocketState.CONNECTED:
        await websocket.close()


# ─── /ws/agents/extract ────────────────────────────────────────────────────


@router.websocket("/ws/agents/extract")
async def extract_stream(
    websocket: WebSocket,
    token: str | None = None,
) -> None:
    await websocket.accept()

    try:
        user_id, jwt = await verify_ws_token(token)
    except WsAuthError as e:
        await websocket.close(code=_CLOSE_UNAUTHORIZED, reason=str(e))
        return

    # First message must carry the source content.
    try:
        first = await asyncio.wait_for(websocket.receive_text(), timeout=15.0)
    except asyncio.TimeoutError:
        await websocket.close(
            code=_CLOSE_BAD_REQUEST,
            reason="expected source_content message within 15s",
        )
        return
    except WebSocketDisconnect:
        return

    try:
        first_payload = json.loads(first)
    except json.JSONDecodeError:
        await websocket.close(code=_CLOSE_BAD_REQUEST, reason="invalid JSON")
        return

    source_content = (first_payload.get("source_content") or "").strip()
    source_url = (first_payload.get("source_url") or "").strip() or None
    if not source_content or len(source_content) > _MAX_SOURCE_CONTENT_CHARS:
        await websocket.close(
            code=_CLOSE_BAD_REQUEST,
            reason=f"source_content must be 1-{_MAX_SOURCE_CONTENT_CHARS} chars",
        )
        return

    try:
        profile = await _load_profile(user_id, jwt)
    except Exception as e:
        await _safe_send_json(
            websocket, {"type": "error", "message": f"profile load failed: {e}"}
        )
        await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    extracted: dict[str, Any] | None = None
    cost_usd = 0.0

    try:
        async for event in run_content_extract(user_id, profile, source_content):
            t = event.get("type")
            if t == "extract_ready":
                extracted = event.get("extracted")
            elif t == "usage":
                cost_usd = float((event.get("token_usage") or {}).get("cost_usd") or 0.0)
            await _safe_send_json(websocket, event)
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        raise
    except Exception as e:
        await _safe_send_json(
            websocket, {"type": "error", "message": f"crew failed: {e}"}
        )
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    if extracted is None:
        await _safe_send_json(
            websocket, {"type": "error", "message": "no extracted payload"}
        )
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    try:
        client = await user_client(jwt)
        idea_row = (
            await client.from_("ideas")
            .insert(
                {
                    "user_id": str(user_id),
                    "title": extracted["title"],
                    "rationale": extracted.get("rationale"),
                    "idea_type": extracted.get("idea_type"),
                    "source_type": "content_extract",
                    "source_content": source_content,
                    "source_content_url": source_url,
                }
            )
            .execute()
        )
        if not idea_row.data:
            raise RuntimeError("ideas insert returned no row")
        new_idea_id = str(idea_row.data[0]["id"])

        session_id = await _ensure_studio_session(
            user_id,
            jwt,
            new_idea_id,
            int(extracted.get("derived_duration_min") or 20),
        )
        script_artifact_id, outline_artifact_id = await _persist_script_outline(
            user_id,
            jwt,
            session_id,
            extracted["script"],
            extracted["outline"],
        )
    except Exception as e:
        await _safe_send_json(
            websocket, {"type": "error", "message": f"persist failed: {e}"}
        )
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    await _safe_send_json(
        websocket,
        {
            "type": "persisted",
            "idea_id": new_idea_id,
            "session_id": session_id,
            "script_artifact_id": script_artifact_id,
            "outline_artifact_id": outline_artifact_id,
        },
    )
    await _safe_send_json(
        websocket,
        {"type": "complete", "cost_usd": cost_usd},
    )
    if websocket.application_state == WebSocketState.CONNECTED:
        await websocket.close()


# ─── /ws/agents/scene ──────────────────────────────────────────────────────


@router.websocket("/ws/agents/scene")
async def scene_stream(
    websocket: WebSocket,
    token: str | None = None,
    session_id: str | None = None,
) -> None:
    """Stream the Scene crew over an existing studio session.

    Loads the session + latest script + latest outline + the parent idea +
    the user's profile via RLS, runs the 3-agent crew, persists the final
    SceneSkeleton as a versioned `excalidraw` artifact, and emits a
    `persisted` event with the new artifact id.
    """
    await websocket.accept()
    qp = websocket.query_params
    brand_accent_qs = qp.get("brand_accent")
    font_family_qs = qp.get("font_family")

    try:
        user_id, jwt = await verify_ws_token(token)
    except WsAuthError as e:
        await websocket.close(code=_CLOSE_UNAUTHORIZED, reason=str(e))
        return

    if not session_id:
        await websocket.close(
            code=_CLOSE_BAD_REQUEST, reason="session_id required"
        )
        return

    try:
        session = await _load_session(jwt, session_id)
    except Exception as e:
        await _safe_send_json(
            websocket, {"type": "error", "message": f"session load failed: {e}"}
        )
        await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    if session is None:
        await websocket.close(
            code=_CLOSE_BAD_REQUEST, reason="session not found"
        )
        return

    idea_id = session.get("idea_id")
    if not idea_id:
        await websocket.close(
            code=_CLOSE_BAD_REQUEST,
            reason="session has no idea_id (cannot resolve scene context)",
        )
        return

    try:
        script_row = await _load_latest_artifact(jwt, session_id, "script")
        outline_row = await _load_latest_artifact(jwt, session_id, "outline")
    except Exception as e:
        await _safe_send_json(
            websocket, {"type": "error", "message": f"artifact load failed: {e}"}
        )
        await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    if script_row is None or outline_row is None:
        await websocket.close(
            code=_CLOSE_BAD_REQUEST,
            reason="session is missing a script + outline artifact",
        )
        return

    try:
        script = Script(**(script_row["content_json"] or {}))
        outline = Outline(**(outline_row["content_json"] or {}))
    except Exception as e:
        await _safe_send_json(
            websocket,
            {"type": "error", "message": f"artifact shape invalid: {e}"},
        )
        await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    try:
        idea = await _load_idea(idea_id, jwt)
    except Exception as e:
        await _safe_send_json(
            websocket, {"type": "error", "message": f"idea load failed: {e}"}
        )
        await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    if idea is None:
        await websocket.close(code=_CLOSE_BAD_REQUEST, reason="idea not found")
        return

    try:
        profile = await _load_profile(user_id, jwt)
    except Exception as e:
        await _safe_send_json(
            websocket, {"type": "error", "message": f"profile load failed: {e}"}
        )
        await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    cost_usd = 0.0
    last_scene: dict[str, Any] | None = None

    try:
        hint_hex = (
            _normalize_brand_hex(brand_accent_qs) if brand_accent_qs else None
        )
        resolved_hex = await _resolve_scene_brand_color(jwt, session)
        # Client hint mirrors Studio picker; DB path covers hydrate-only loads.
        brand_color = hint_hex or resolved_hex
    except Exception as e:
        await _safe_send_json(
            websocket,
            {
                "type": "error",
                "message": f"could not resolve brand accent for scene: {e}",
            },
        )
        await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    # Excalidraw built-in fontFamily integers: 1 (Virgil), 2 (Helvetica),
    # 3 (Cascadia), 5 (Excalifont), 6 (Nunito), 7 (Lilita One), 8 (Comic
    # Shanns), 9 (Liberation Sans). Anything outside this set or unparseable
    # falls back to None (designer prompt picks the default).
    _VALID_FONT_FAMILIES = {1, 2, 3, 5, 6, 7, 8, 9}
    font_family: int | None = None
    if font_family_qs:
        try:
            ff = int(font_family_qs)
            if ff in _VALID_FONT_FAMILIES:
                font_family = ff
        except ValueError:
            font_family = None

    try:
        async for event in run_scene_build(
            user_id,
            profile,
            idea,
            outline,
            script,
            brand_color=brand_color,
            font_family=font_family,
        ):
            t = event.get("type")
            if t == "scene_ready":
                last_scene = event.get("scene")
            elif t == "usage":
                cost_usd = float(
                    (event.get("token_usage") or {}).get("cost_usd") or 0.0
                )
            await _safe_send_json(websocket, event)
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        raise
    except Exception as e:
        await _safe_send_json(
            websocket, {"type": "error", "message": f"crew failed: {e}"}
        )
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    if last_scene is None:
        await _safe_send_json(
            websocket,
            {
                "type": "error",
                "message": "scene crew did not produce a skeleton",
            },
        )
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    try:
        scene_artifact_id = await _persist_scene_skeleton(
            user_id, jwt, session_id, last_scene
        )
    except Exception as e:
        await _safe_send_json(
            websocket, {"type": "error", "message": f"persist failed: {e}"}
        )
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    await _safe_send_json(
        websocket,
        {
            "type": "persisted",
            "session_id": session_id,
            "scene_artifact_id": scene_artifact_id,
        },
    )
    await _safe_send_json(
        websocket,
        {"type": "complete", "cost_usd": cost_usd},
    )
    if websocket.application_state == WebSocketState.CONNECTED:
        await websocket.close()
