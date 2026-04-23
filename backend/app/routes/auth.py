from fastapi import APIRouter, Depends

from app.deps import user_client
from app.middleware.auth import current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def me(ctx: tuple = Depends(current_user)) -> dict:
    """Return the current user + profile. Creates the profile row on first call."""
    user_id, jwt = ctx
    client = await user_client(jwt)

    profile = (
        await client.from_("user_profiles")
        .select("*")
        .eq("user_id", str(user_id))
        .maybe_single()
        .execute()
    )

    return {
        "user_id": str(user_id),
        "profile": profile.data,
        "onboarded": bool(profile.data and profile.data.get("onboarded_at")),
    }


@router.post("/onboard")
async def onboard(payload: dict, ctx: tuple = Depends(current_user)) -> dict:
    """Upsert the user_profiles row and mark onboarded_at. RLS enforces ownership."""
    user_id, jwt = ctx
    client = await user_client(jwt)

    row = {
        "user_id": str(user_id),
        "display_name": payload.get("display_name"),
        "positioning": payload.get("positioning"),
        "audience": payload.get("audience"),
        "voice": payload.get("voice"),
        "creators_followed": payload.get("creators_followed") or [],
        "things_to_avoid": payload.get("things_to_avoid"),
        "onboarded_at": "now()",
    }

    result = (
        await client.from_("user_profiles")
        .upsert(row, on_conflict="user_id")
        .execute()
    )
    return {"profile": result.data[0] if result.data else None}
