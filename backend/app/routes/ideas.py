from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.deps import user_client
from app.middleware.auth import current_user

router = APIRouter(prefix="/ideas", tags=["ideas"])


class IdeaCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: str | None = None
    idea_type: str | None = None
    status: str = "new"
    opportunity_score: int | None = Field(default=None, ge=0, le=100)
    outlier_score: float | None = Field(default=None, ge=0, le=10)
    rationale: str | None = None
    source_type: str = "manual"
    source_content: str | None = None
    source_content_url: str | None = None
    project_id: str | None = None
    position: float | None = None
    # Founder-chosen target runtime in minutes (3-60). Mirrors the dropdown
    # on /make's research tile so the Studio crew can size the script for
    # the same length without the user re-picking on every re-run.
    target_duration_min: int | None = Field(default=None, ge=3, le=60)
    # Snapshot of the research crew's findings (sources + queries + topic)
    # written at idea-creation time so /studio/:id can render the same
    # rich preview cards across tabs / devices / reloads. Shape is owned by
    # the frontend; backend just persists it as JSONB.
    research_snapshot: dict[str, Any] | None = None


class IdeaUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = None
    idea_type: str | None = None
    status: str | None = None
    opportunity_score: int | None = Field(default=None, ge=0, le=100)
    outlier_score: float | None = Field(default=None, ge=0, le=10)
    rationale: str | None = None
    project_id: str | None = None
    position: float | None = None
    target_duration_min: int | None = Field(default=None, ge=3, le=60)


class IdeasListResponse(BaseModel):
    ideas: list[dict]


class IdeaResponse(BaseModel):
    idea: dict


@router.get("", response_model=IdeasListResponse)
async def list_ideas(
    ctx: tuple = Depends(current_user),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> IdeasListResponse:
    """List the caller's ideas. RLS filters to user_id = auth.uid()."""
    _user_id, token = ctx
    client = await user_client(token)

    try:
        q = client.from_("ideas").select("*")
        if status:
            q = q.eq("status", status)
        result = (
            await q.order("position", desc=False, nullsfirst=False)
            .order("opportunity_score", desc=True, nullsfirst=False)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    return IdeasListResponse(ideas=result.data or [])


@router.post("", response_model=IdeaResponse, status_code=201)
async def create_idea(
    payload: IdeaCreate, ctx: tuple = Depends(current_user)
) -> IdeaResponse:
    """Insert a new idea for the caller. user_id is set explicitly; RLS enforces it."""
    user_id, token = ctx
    client = await user_client(token)

    row = payload.model_dump(exclude_none=True)
    row["user_id"] = str(user_id)

    if "position" not in row:
        try:
            tail = (
                await client.from_("ideas")
                .select("position")
                .eq("status", row["status"])
                .order("position", desc=True, nullsfirst=False)
                .limit(1)
                .execute()
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e
        last = (tail.data or [{}])[0].get("position") if tail.data else None
        row["position"] = (last or 0) + 1000

    try:
        result = await client.from_("ideas").insert(row).execute()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    if not result.data:
        raise HTTPException(status_code=400, detail="Insert returned no row")

    return IdeaResponse(idea=result.data[0])


@router.patch("/{idea_id}", response_model=IdeaResponse)
async def update_idea(
    idea_id: str, payload: IdeaUpdate, ctx: tuple = Depends(current_user)
) -> IdeaResponse:
    """Partially update an idea. RLS blocks updates to rows the caller doesn't own."""
    _user_id, token = ctx
    client = await user_client(token)

    patch = payload.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        result = (
            await client.from_("ideas")
            .update(patch)
            .eq("id", idea_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    if not result.data:
        raise HTTPException(status_code=404, detail="Idea not found")

    return IdeaResponse(idea=result.data[0])


@router.delete("/{idea_id}", status_code=204)
async def delete_idea(idea_id: str, ctx: tuple = Depends(current_user)) -> None:
    """Delete an idea. RLS ensures only the owner can delete."""
    _user_id, token = ctx
    client = await user_client(token)

    try:
        await client.from_("ideas").delete().eq("id", idea_id).execute()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e
