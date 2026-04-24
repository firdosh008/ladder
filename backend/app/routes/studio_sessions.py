"""Studio sessions read endpoints.

Today only one route — `GET /studio-sessions/by-idea/{idea_id}` — used by the
Studio page to hydrate an existing script + outline before deciding whether
to auto-stream a new one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import user_client
from app.middleware.auth import current_user

router = APIRouter(prefix="/studio-sessions", tags=["studio_sessions"])


class StudioSessionByIdea(BaseModel):
    session: dict | None
    script: dict | None
    outline: dict | None


@router.get("/by-idea/{idea_id}", response_model=StudioSessionByIdea)
async def get_session_by_idea(
    idea_id: str, ctx: tuple = Depends(current_user)
) -> StudioSessionByIdea:
    """Return the latest studio session + latest script/outline artifacts for an idea.

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
        return StudioSessionByIdea(session=None, script=None, outline=None)

    session = sess_resp.data[0]
    session_id = session["id"]

    try:
        artifacts_resp = (
            await client.from_("artifacts")
            .select("*")
            .eq("session_id", session_id)
            .in_("type", ["script", "outline"])
            .order("version", desc=True)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    script: dict | None = None
    outline: dict | None = None
    for a in artifacts_resp.data or []:
        if script is None and a["type"] == "script":
            script = a
        elif outline is None and a["type"] == "outline":
            outline = a
        if script and outline:
            break

    return StudioSessionByIdea(session=session, script=script, outline=outline)
