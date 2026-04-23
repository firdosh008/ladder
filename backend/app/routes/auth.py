from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from pydantic import BaseModel, Field

from app.deps import user_client
from app.middleware.auth import current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class OnboardPayload(BaseModel):
    display_name: str
    positioning: str
    audience: str
    voice: str
    creators_followed: list[str] = Field(default_factory=list)
    things_to_avoid: str | None = None


class MeResponse(BaseModel):
    user_id: str
    email: str | None = None
    profile: dict | None = None
    onboarded: bool


class OnboardResponse(BaseModel):
    profile: dict | None


@router.get("/me", response_model=MeResponse)
async def me(ctx: tuple = Depends(current_user)) -> MeResponse:
    """Return the current user + profile. Creates the profile row on first call."""
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

    return MeResponse(
        user_id=str(user_id),
        email=email,
        profile=profile.data,
        onboarded=bool(profile.data and profile.data.get("onboarded_at")),
    )


@router.post("/onboard", response_model=OnboardResponse)
async def onboard(
    payload: OnboardPayload, ctx: tuple = Depends(current_user)
) -> OnboardResponse:
    """Upsert the user_profiles row and mark onboarded_at. RLS enforces ownership."""
    user_id, token = ctx
    client = await user_client(token)

    row = {
        "user_id": str(user_id),
        "display_name": payload.display_name,
        "positioning": payload.positioning,
        "audience": payload.audience,
        "voice": payload.voice,
        "creators_followed": payload.creators_followed,
        "things_to_avoid": payload.things_to_avoid,
        "onboarded_at": datetime.now(timezone.utc).isoformat(),
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
