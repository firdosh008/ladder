"""Agent WebSocket routes.

Single endpoint today: /ws/agents/research. Streams events from the Research
crew and delivers the finalised drafts to the client. Per PRD §2.1 the drafts
are NOT auto-persisted — the user picks one inline, and the frontend POSTs
the chosen draft to /ideas to create the row and open the studio session.

Event protocol (server→client):
  {"type": "agent_start",   "agent": "search_agent"}
  {"type": "tool_call",     "tool":  "web_search", "query": "..."}
  {"type": "tool_result",   "preview": "..."}
  {"type": "agent_step",    "agent": "...", "preview": "..."}
  {"type": "task_complete", "agent": "...", "preview": "..."}
  {"type": "ideas_ready",   "ideas": [...], "token_usage": {...}}
  {"type": "complete",      "count": N, "cost_usd": 0.07}
  {"type": "error",         "message": "..."}
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState

from app.agents.research import run_research
from app.deps import user_client
from app.middleware.ws_auth import WsAuthError, verify_ws_token
from app.models.db import UserProfileSlice

router = APIRouter(tags=["agents"])

# WebSocket close codes (application-level 4xxx range)
_CLOSE_UNAUTHORIZED = 4401
_CLOSE_BAD_REQUEST = 4400
_CLOSE_SERVER_ERROR = 1011


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


async def _safe_send_json(ws: WebSocket, payload: dict[str, Any]) -> bool:
    """Return True on success, False if the socket is already closed."""
    if ws.application_state != WebSocketState.CONNECTED:
        return False
    try:
        await ws.send_json(payload)
        return True
    except Exception:
        return False


@router.websocket("/ws/agents/research")
async def research_stream(
    websocket: WebSocket,
    token: str | None = None,
    topic: str | None = None,
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
        async for event in run_research(user_id, profile, cleaned_topic):
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
