from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from pydantic import BaseModel

from app.deps import service_client, user_client
from app.middleware.auth import current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class OnboardPayload(BaseModel):
    display_name: str | None = None
    positioning: str | None = None
    audience: str | None = None
    voice: str | None = None
    creators_followed: list[str] | None = None
    things_to_avoid: str | None = None


class MeResponse(BaseModel):
    user_id: str
    email: str | None = None
    profile: dict | None = None
    onboarded: bool


class OnboardResponse(BaseModel):
    profile: dict | None


async def _ensure_user_rows(user_id: str) -> dict | None:
    """Bootstrap public.users + public.user_profiles if the handle_new_user()
    trigger didn't run (missing or pre-trigger account). Idempotent.

    Uses the service client because public.users has no INSERT RLS policy.
    Returns the freshly-ensured user_profiles row, or None if the upsert yields
    nothing.
    """
    admin = await service_client()
    await (
        admin.from_("users")
        .upsert({"id": user_id}, on_conflict="id")
        .execute()
    )
    result = await (
        admin.from_("user_profiles")
        .upsert({"user_id": user_id}, on_conflict="user_id")
        .execute()
    )
    return result.data[0] if result.data else None


@router.get("/me", response_model=MeResponse)
async def me(ctx: tuple = Depends(current_user)) -> MeResponse:
    """Return the current user + profile. Creates the rows on first call if missing."""
    user_id, token = ctx
    client = await user_client(token)

    # Signature was already verified by the middleware; reading claims here is safe.
    claims = jwt.get_unverified_claims(token)
    email = claims.get("email")

    try:
        profile = (
            await client.from_("user_profiles")
            .select("*")
            .eq("user_id", str(user_id))
            .maybe_single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    # supabase-py 2.x: maybe_single().execute() returns None when no row matches.
    # Older versions returned an object with data=None. Handle both.
    profile_data = getattr(profile, "data", None) if profile is not None else None

    # Self-heal: if the trigger didn't create the rows, do it now.
    if profile_data is None:
        try:
            profile_data = await _ensure_user_rows(str(user_id))
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Supabase error (bootstrap): {e}"
            ) from e

    return MeResponse(
        user_id=str(user_id),
        email=email,
        profile=profile_data,
        onboarded=bool(profile_data and profile_data.get("onboarded_at")),
    )


class ProfileUpdate(BaseModel):
    """Partial profile fields for inline edit (Library > What I Know)."""

    display_name: str | None = None
    positioning: str | None = None
    audience: str | None = None
    voice: str | None = None
    creators_followed: list[str] | None = None
    things_to_avoid: str | None = None


@router.patch("/profile", response_model=OnboardResponse)
async def update_profile(
    payload: ProfileUpdate, ctx: tuple = Depends(current_user)
) -> OnboardResponse:
    """Partially update the caller's user_profiles row. Saves-on-blur for Library."""
    user_id, token = ctx
    client = await user_client(token)

    patch = payload.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        result = (
            await client.from_("user_profiles")
            .update(patch)
            .eq("user_id", str(user_id))
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    if not result.data:
        raise HTTPException(status_code=404, detail="Profile not found")

    return OnboardResponse(profile=result.data[0])


@router.post("/onboard", response_model=OnboardResponse)
async def onboard(
    payload: OnboardPayload, ctx: tuple = Depends(current_user)
) -> OnboardResponse:
    """Upsert the user_profiles row and mark onboarded_at. RLS enforces ownership."""
    user_id, token = ctx

    # Self-heal: ensure public.users + public.user_profiles rows exist. Belt-and-
    # suspenders — /auth/me already does this, but this covers direct onboard hits.
    try:
        await _ensure_user_rows(str(user_id))
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Supabase error (bootstrap): {e}"
        ) from e

    client = await user_client(token)

    # Only include fields the caller actually sent — different screens submit
    # different subsets (onboarding step 1+2 sends positioning/audience/creators,
    # Settings sends the full profile). Excluding unset keys means missing
    # fields don't clobber existing values on the upsert.
    row = {
        "user_id": str(user_id),
        "onboarded_at": datetime.now(timezone.utc).isoformat(),
        **payload.model_dump(exclude_none=True),
    }

    try:
        result = (
            await client.from_("user_profiles")
            .upsert(row, on_conflict="user_id")
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    return OnboardResponse(profile=result.data[0] if result.data else None)
