"""Visual agent WebSocket — drives the live Excalidraw MCP canvas.

Endpoint::

    GET /ws/agents/visual?token=<jwt>&session_id=<uuid>&steer=<optional note>

Replaces the legacy ``POST /generate-diagram`` (and its Anthropic-loop
``DiagramService``). The frontend's "Generate Visual" button in
``SceneRunPanel`` connects here and consumes the same event protocol
documented in HANDOFF.md §11.

Auth flows through ``verify_ws_token`` (the same JWKS cache as HTTP). Close
codes follow the standing convention: 4401 unauthorized, 4400 bad request,
1011 server error.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState

from app.agents.visual import run_visual_build
from app.agents.visual.context import load_session_context
from app.middleware.ws_auth import WsAuthError, verify_ws_token

router = APIRouter(tags=["agents"])
log = logging.getLogger(__name__)

_CLOSE_UNAUTHORIZED = 4401
_CLOSE_BAD_REQUEST = 4400
_CLOSE_SERVER_ERROR = 1011

_MAX_STEER_CHARS = 1200


async def _safe_send_json(ws: WebSocket, payload: dict[str, Any]) -> bool:
    if ws.application_state != WebSocketState.CONNECTED:
        return False
    try:
        await ws.send_json(payload)
        return True
    except Exception:
        return False


@router.websocket("/ws/agents/visual")
async def visual_stream(
    websocket: WebSocket,
    token: str | None = None,
    session_id: str | None = None,
    steer: str | None = None,
) -> None:
    """One-shot canvas build for a studio session.

    Streams ``agent_start`` / ``tool_call`` / ``text_delta`` /
    ``task_complete`` while the agent draws, then ``scene_ready`` /
    ``persisted`` / ``usage`` / ``complete`` on success. ``error`` on any
    failure path; the socket closes after.
    """
    await websocket.accept()

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

    steer_note: str | None = None
    if steer:
        cleaned = steer.strip()
        if cleaned:
            steer_note = cleaned[:_MAX_STEER_CHARS]

    try:
        context = await load_session_context(user_id, jwt, session_id)
    except ValueError as e:
        # 4400: session not found / orphaned / idea missing.
        await _safe_send_json(websocket, {"type": "error", "message": str(e)})
        await websocket.close(code=_CLOSE_BAD_REQUEST, reason=str(e))
        return
    except Exception as e:
        log.exception("visual context load failed")
        await _safe_send_json(
            websocket, {"type": "error", "message": f"context load failed: {e}"}
        )
        await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    cost_usd = 0.0
    scene_artifact_id: str | None = None

    try:
        async for event in run_visual_build(context, steer_note=steer_note):
            t = event.get("type")
            if t == "persisted":
                scene_artifact_id = event.get("scene_artifact_id")
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
            websocket, {"type": "error", "message": f"visual build failed: {e}"}
        )
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close(code=_CLOSE_SERVER_ERROR)
        return

    if scene_artifact_id is None:
        # The build emitted an `error` event already; close cleanly.
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close()
        return

    if websocket.application_state == WebSocketState.CONNECTED:
        await websocket.close()
