"""Studio sessions read endpoints.

Routes:
  GET  /studio-sessions/by-idea/{idea_id}
        Hydrate a studio page: returns the latest session + latest script,
        outline, and excalidraw artifacts for the idea.

  POST /studio-sessions/{session_id}/scene/share
        Upload a fully-inflated `.excalidraw` envelope to public Storage
        and return the public URL. The frontend uses this URL to open the
        scene in excalidraw.com via `excalidraw.com/#url=<encoded>`.
        See PRD §5.5 (the canonical "open in Excalidraw" affordance).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import service_client, user_client
from app.middleware.auth import current_user

router = APIRouter(prefix="/studio-sessions", tags=["studio_sessions"])

_SCENE_BUCKET = "excalidraw_scenes"
_MAX_ENVELOPE_BYTES = 2 * 1024 * 1024  # 2 MB hard cap


class StudioSessionByIdea(BaseModel):
    session: dict | None
    script: dict | None
    outline: dict | None
    scene: dict | None


class ScenePublishBody(BaseModel):
    """The full .excalidraw envelope produced by the frontend after running
    `convertToExcalidrawElements()` on the persisted skeleton."""

    envelope: dict[str, Any]


class ScenePublishResponse(BaseModel):
    public_url: str
    storage_path: str


@router.get("/by-idea/{idea_id}", response_model=StudioSessionByIdea)
async def get_session_by_idea(
    idea_id: str, ctx: tuple = Depends(current_user)
) -> StudioSessionByIdea:
    """Return the latest session + latest script / outline / excalidraw artifacts.

    Returns nulls (not 404) when no session exists yet — the studio page uses
    that signal to decide whether to auto-run the streaming crew.
    """
    _user_id, token = ctx
    client = await user_client(token)

    try:
        sess_resp = (
            await client.from_("studio_sessions")
            .select("*")
            .eq("idea_id", idea_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    if not sess_resp.data:
        return StudioSessionByIdea(
            session=None, script=None, outline=None, scene=None
        )

    session = sess_resp.data[0]
    session_id = session["id"]

    try:
        artifacts_resp = (
            await client.from_("artifacts")
            .select("*")
            .eq("session_id", session_id)
            .in_("type", ["script", "outline", "excalidraw"])
            .order("version", desc=True)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    script: dict | None = None
    outline: dict | None = None
    scene: dict | None = None
    for a in artifacts_resp.data or []:
        kind = a["type"]
        if kind == "script" and script is None:
            script = a
        elif kind == "outline" and outline is None:
            outline = a
        elif kind == "excalidraw" and scene is None:
            scene = a
        if script and outline and scene:
            break

    return StudioSessionByIdea(
        session=session, script=script, outline=outline, scene=scene
    )


@router.post(
    "/{session_id}/scene/share",
    response_model=ScenePublishResponse,
)
async def publish_scene(
    session_id: str,
    body: ScenePublishBody,
    ctx: tuple = Depends(current_user),
) -> ScenePublishResponse:
    """Upload an .excalidraw envelope to public Storage and return its URL.

    Flow:
      1. RLS-verify the caller owns the session (via user_client read).
      2. Validate the envelope shape + size.
      3. Upload via the service client (Storage bucket policies pin
         user-scoped paths so the upload itself is also locked-down).
      4. Return the public URL — frontend opens `excalidraw.com#url=<...>`.
    """
    user_id, token = ctx

    sb_user = await user_client(token)
    sess_resp = (
        await sb_user.from_("studio_sessions")
        .select("id, user_id")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    sess = sess_resp.data if sess_resp is not None else None
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")

    envelope = body.envelope
    if (
        not isinstance(envelope, dict)
        or envelope.get("type") != "excalidraw"
        or not isinstance(envelope.get("elements"), list)
    ):
        raise HTTPException(
            status_code=400,
            detail="envelope must be an Excalidraw file ({type:'excalidraw', elements:[...]})",
        )

    blob = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    if len(blob) > _MAX_ENVELOPE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"envelope exceeds {_MAX_ENVELOPE_BYTES // 1024} KB cap",
        )

    storage_path = f"{user_id}/{session_id}/{uuid4().hex}.excalidraw"

    sb_admin = await service_client()
    try:
        await sb_admin.storage.from_(_SCENE_BUCKET).upload(
            path=storage_path,
            file=blob,
            file_options={
                "content-type": "application/json",
                "x-upsert": "true",
                "cache-control": "public, max-age=300",
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Storage upload failed: {e}"
        ) from e

    try:
        public_url = await sb_admin.storage.from_(_SCENE_BUCKET).get_public_url(
            storage_path
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Storage URL resolution failed: {e}"
        ) from e

    # Mirror the latest published path on the session row for the kanban /
    # ready-to-record column. Fire-and-forget — failure here does not block
    # returning the URL to the caller.
    try:
        await (
            sb_user.from_("studio_sessions")
            .update(
                {
                    "excalidraw_url": public_url,
                    "excalidraw_storage_path": storage_path,
                }
            )
            .eq("id", session_id)
            .execute()
        )
    except Exception:
        pass

    return ScenePublishResponse(public_url=public_url, storage_path=storage_path)
