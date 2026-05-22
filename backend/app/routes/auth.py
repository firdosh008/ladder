import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
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
    linkedin_url: str | None = None


class MeResponse(BaseModel):
    user_id: str
    email: str | None = None
    profile: dict | None = None
    onboarded: bool
    is_admin: bool = False


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

    # Check is_admin from public.users
    is_admin = False
    try:
        user_row = (
            await client.from_("users")
            .select("is_admin")
            .eq("id", str(user_id))
            .maybe_single()
            .execute()
        )
        user_data = getattr(user_row, "data", None) if user_row is not None else None
        is_admin = bool(user_data and user_data.get("is_admin"))
    except Exception:
        pass  # Non-critical — default to false

    return MeResponse(
        user_id=str(user_id),
        email=email,
        profile=profile_data,
        onboarded=bool(profile_data and profile_data.get("onboarded_at")),
        is_admin=is_admin,
    )


class ProfileUpdate(BaseModel):
    """Partial profile fields for inline edit (Library > What I Know) and Settings."""

    display_name: str | None = None
    positioning: str | None = None
    audience: str | None = None
    voice: str | None = None
    creators_followed: list[str] | None = None
    things_to_avoid: str | None = None
    linkedin_url: str | None = None
    theme: str | None = None
    font_scale: str | None = None


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


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile, ctx: tuple = Depends(current_user)
) -> dict:
    """Upload a profile avatar to Supabase Storage."""
    user_id, token = ctx

    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(
            status_code=400, detail="Only image files are accepted"
        )

    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Avatar must be under 5 MB")

    ext = (file.filename or "avatar.png").rsplit(".", 1)[-1]
    if ext not in ("png", "jpg", "jpeg", "gif", "webp"):
        ext = "png"
    storage_path = f"{user_id}/avatar.{ext}"

    # Upload using service client (bypasses RLS on storage)
    admin_client = await service_client()
    try:
        result = (
            await admin_client.storage
            .from_("avatars")
            .upload(
                storage_path, raw,
                {"content-type": content_type, "upsert": "true"},
            )
        )
        # supabase-py 2.x returns the dict directly, 1.x wrapped it
        if hasattr(result, "path"):
            path = result.path or storage_path
        else:
            # result is a Response object or dict
            path = storage_path
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Storage upload failed: {e}"
        ) from e

    # Update user_profiles
    client = await user_client(token)
    await (
        client.from_("user_profiles")
        .update({"avatar_storage_path": path})
        .eq("user_id", str(user_id))
        .execute()
    )

    # Build public URL
    public_url = (
        f"{admin_client.supabase_url}/storage/v1/object/public/avatars/{path}"
    )

    return {"avatar_storage_path": path, "avatar_url": public_url}
