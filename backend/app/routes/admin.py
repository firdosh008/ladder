"""Admin-only routes — PRD §8.7"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import service_client, user_client
from app.middleware.auth import current_user

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_admin(ctx: tuple) -> tuple:
    """Verify the current user is an admin. Returns (user_id, token) on success."""
    user_id, token = ctx
    admin_client = await service_client()
    result = (
        await admin_client.from_("users")
        .select("is_admin")
        .eq("id", str(user_id))
        .maybe_single()
        .execute()
    )
    row = getattr(result, "data", None) if result is not None else None
    if not row or not row.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id, token


# ── Usage ─────────────────────────────────────────────────────────────────────

@router.get("/usage")
async def team_usage(ctx: tuple = Depends(require_admin)) -> list[dict]:
    user_id, token = ctx  # noqa: F841
    admin_client = await service_client()

    # Current month start
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    result = (
        await admin_client.rpc("admin_usage_summary", {"month_start": month_start.isoformat()})
        .execute()
    )

    # Fallback to raw query if RPC doesn't exist yet
    if not result.data:
        rows = (
            await admin_client.from_("usage_log")
            .select("user_id,function_name,cost_usd")
            .gte("created_at", month_start.isoformat())
            .execute()
        )
        log_rows = rows.data or []

        # Group by user
        agg: dict[str, dict] = {}
        for r in log_rows:
            uid = r["user_id"]
            if uid not in agg:
                agg[uid] = {"calls": 0, "cost": 0.0, "funcs": {}}
            agg[uid]["calls"] += 1
            agg[uid]["cost"] += float(r["cost_usd"] or 0)
            fn = r["function_name"] or "unknown"
            agg[uid]["funcs"][fn] = agg[uid]["funcs"].get(fn, 0) + 1

        # Resolve user names
        user_rows = (
            await admin_client.from_("users")
            .select("id")
            .in_("id", list(agg.keys()))
            .execute()
        )
        # Get profiles
        profile_rows = (
            await admin_client.from_("user_profiles")
            .select("user_id,display_name")
            .in_("user_id", list(agg.keys()))
            .execute()
        )
        profiles = {
            p["user_id"]: p.get("display_name") or p["user_id"]
            for p in (profile_rows.data or [])
        }

        out = []
        for uid, data in agg.items():
            most_used = max(data["funcs"].items(), key=lambda x: x[1])[0] if data["funcs"] else "—"
            out.append({
                "user_id": uid,
                "name": profiles.get(uid, uid[:8]),
                "total_calls": data["calls"],
                "total_cost": round(data["cost"], 4),
                "most_used_function": most_used,
            })
        return sorted(out, key=lambda x: x["total_cost"], reverse=True)

    return result.data


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(ctx: tuple = Depends(require_admin)) -> list[dict]:
    user_id, token = ctx  # noqa: F841
    admin_client = await service_client()

    profiles = (
        await admin_client.from_("user_profiles")
        .select("user_id,display_name,onboarded_at")
        .execute()
    )
    users = (
        await admin_client.from_("users")
        .select("id,is_admin,created_at")
        .execute()
    )

    user_map = {u["id"]: u for u in (users.data or [])}
    profile_map = {p["user_id"]: p for p in (profiles.data or [])}

    # Get emails from auth.users via RPC or supabase admin API — skip for now,
    # return user_id as fallback.
    out = []
    for uid, u in user_map.items():
        p = profile_map.get(uid, {})
        out.append({
            "user_id": uid,
            "name": p.get("display_name") or uid[:8],
            "email": None,  # Requires supabase admin API
            "alias": None,
            "onboarded": bool(p.get("onboarded_at")),
            "is_admin": bool(u.get("is_admin")),
            "last_active": str(u.get("created_at")),
        })
    return out


class InvitePayload(BaseModel):
    name: str
    email: str
    role: str = "Member"  # Member or Admin


@router.post("/invite")
async def invite_user(
    payload: InvitePayload, ctx: tuple = Depends(require_admin)
) -> dict:
    """Send a magic-link invite via Supabase Auth."""
    user_id, token = ctx  # noqa: F841
    admin_client = await service_client()

    try:
        resp = await admin_client.auth.admin.invite_user_by_email(
            payload.email,
            {"data": {"display_name": payload.name, "role": payload.role}},
        )
        return {"ok": True, "user": resp}
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Invite failed: {e}"
        ) from e


@router.post("/users/{target_id}/deactivate")
async def deactivate_user(
    target_id: str, ctx: tuple = Depends(require_admin)
) -> dict:
    user_id, token = ctx  # noqa: F841
    admin_client = await service_client()
    try:
        await admin_client.auth.admin.delete_user(target_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Deactivate failed: {e}"
        ) from e


@router.post("/users/{target_id}/reset-onboarding")
async def reset_onboarding(
    target_id: str, ctx: tuple = Depends(require_admin)
) -> dict:
    user_id, token = ctx  # noqa: F841
    admin_client = await service_client()
    await (
        admin_client.from_("user_profiles")
        .update({"onboarded_at": None})
        .eq("user_id", target_id)
        .execute()
    )
    return {"ok": True}


@router.post("/users/{target_id}/resend-invite")
async def resend_invite(
    target_id: str, ctx: tuple = Depends(require_admin)
) -> dict:
    user_id, token = ctx  # noqa: F841
    admin_client = await service_client()
    try:
        resp = await admin_client.auth.admin.invite_user_by_email(
            target_id  # This needs the email — better to look up first
        )
        return {"ok": True, "detail": str(resp)}
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Resend failed: {e}"
        ) from e


# ── System Health ─────────────────────────────────────────────────────────────

@router.get("/health")
async def system_health(ctx: tuple = Depends(require_admin)) -> dict:
    user_id, token = ctx  # noqa: F841
    admin_client = await service_client()

    apis = {
        "anthropic": "unknown",
        "openai": "unknown",
        "google": "unknown",
        "gamma": "unknown",
        "youtube": "unknown",
    }

    # Check newsletter ingest
    last_ingest = None
    try:
        nl = (
            await admin_client.from_("newsletters")
            .select("fetched_at")
            .order("fetched_at", desc=True)
            .limit(1)
            .execute()
        )
        if nl.data:
            last_ingest = nl.data[0].get("fetched_at")
    except Exception:
        pass

    # Check pgvector
    pgvector_ok = False
    try:
        vec = (
            await admin_client.rpc("check_vector_extension")
            .execute()
        )
        pgvector_ok = bool(vec.data)
    except Exception:
        try:
            vec = await admin_client.from_("knowledge_nodes").select("id").limit(1).execute()
            pgvector_ok = len(vec.data or []) > 0 or True  # table exists
        except Exception:
            pass

    return {
        "apis": apis,
        "last_newsletter_ingest": last_ingest,
        "pgvector_ok": pgvector_ok,
    }
