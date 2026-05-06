"""Videos page — kanban data and weekly suggestions.

Routes:
  GET  /videos/kanban              All four columns + channel summary
  GET  /videos/weekly-suggestions  Current week's suggestion (or null)
  POST /videos/weekly-suggestions  Save suggestions for current week
  POST /videos/weekly-suggestions/dismiss  Dismiss current week
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import user_client
from app.middleware.auth import current_user

router = APIRouter(prefix="/videos", tags=["videos"])


# ── Response models ─────────────────────────────────────────────────────────


class ChannelSummaryOut(BaseModel):
    total_views_month: int | None = None
    best_video_title: str | None = None
    avg_ctr: float | None = None
    avg_outlier_score: float | None = None
    total_videos: int = 0


class KanbanResponse(BaseModel):
    ideas: list[dict[str, Any]]
    in_progress: list[dict[str, Any]]
    ready: list[dict[str, Any]]
    published: list[dict[str, Any]]
    channel_summary: ChannelSummaryOut | None = None
    youtube_connected: bool = False


class WeeklySuggestionOut(BaseModel):
    id: str
    week_start: str
    ideas: list[dict[str, Any]]
    dismissed: bool
    generated_at: str | None = None


class WeeklySuggestionSaveBody(BaseModel):
    ideas: list[dict[str, Any]]


# ── Helpers ─────────────────────────────────────────────────────────────────


def _this_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


async def _fetch_ideas(client, user_id: str) -> list[dict[str, Any]]:
    resp = await (
        client.from_("ideas")
        .select("*")
        .eq("status", "new")
        .eq("archived", False)
        .order("position", desc=False, nullsfirst=False)
        .order("opportunity_score", desc=True, nullsfirst=False)
        .order("created_at", desc=True)
        .limit(200)
        .execute()
    )
    return resp.data or []


async def _fetch_in_progress(client, user_id: str) -> list[dict[str, Any]]:
    """Sessions with status='active', joined with their idea title/type."""
    resp = await (
        client.from_("studio_sessions")
        .select("*, ideas!inner(title, idea_type)")
        .eq("status", "active")
        .eq("archived", False)
        .order("updated_at", desc=True)
        .limit(200)
        .execute()
    )

    sessions = resp.data or []
    if not sessions:
        return []

    session_ids = [s["id"] for s in sessions]

    # Fetch artifact progress per session in one query.
    art_resp = await (
        client.from_("artifacts")
        .select("session_id, type")
        .in_("session_id", session_ids)
        .in_("type", ["script", "outline", "excalidraw", "thumbnail"])
        .execute()
    )

    progress_by_session: dict[str, set[str]] = {sid: set() for sid in session_ids}
    for a in art_resp.data or []:
        progress_by_session[a["session_id"]].add(a["type"])

    result: list[dict[str, Any]] = []
    for s in sessions:
        ideas_data = s.get("ideas") or {}
        sid = s["id"]
        progress = progress_by_session.get(sid, set())
        result.append({
            "session_id": sid,
            "idea_id": s["idea_id"],
            "title": ideas_data.get("title") or s.get("topic_text") or "Untitled",
            "idea_type": ideas_data.get("idea_type"),
            "brand_color": s.get("brand_color"),
            "brand_id": str(s["brand_id"]) if s.get("brand_id") else None,
            "updated_at": s["updated_at"],
            "has_script": "script" in progress,
            "has_outline": "outline" in progress,
            "has_scene": "excalidraw" in progress,
            "has_thumbnail": "thumbnail" in progress,
        })
    return result


async def _fetch_ready(client, user_id: str) -> list[dict[str, Any]]:
    """Sessions with status='completed' that have an excalidraw artifact."""
    resp = await (
        client.from_("studio_sessions")
        .select("*, ideas!inner(title, idea_type)")
        .eq("status", "completed")
        .eq("archived", False)
        .order("updated_at", desc=True)
        .limit(200)
        .execute()
    )

    sessions = resp.data or []
    if not sessions:
        return []

    session_ids = [s["id"] for s in sessions]

    art_resp = await (
        client.from_("artifacts")
        .select("session_id, type, file_url")
        .in_("session_id", session_ids)
        .in_("type", ["excalidraw", "thumbnail"])
        .order("version", desc=True)
        .execute()
    )

    # Per session: does it have excalidraw? what's the latest thumbnail URL?
    has_excalidraw: set[str] = set()
    thumbnail_urls: dict[str, str] = {}
    for a in art_resp.data or []:
        sid = a["session_id"]
        if a["type"] == "excalidraw":
            has_excalidraw.add(sid)
        elif a["type"] == "thumbnail" and sid not in thumbnail_urls:
            thumbnail_urls[sid] = a.get("file_url") or ""

    result: list[dict[str, Any]] = []
    for s in sessions:
        sid = s["id"]
        if sid not in has_excalidraw:
            continue
        ideas_data = s.get("ideas") or {}
        result.append({
            "session_id": sid,
            "idea_id": s["idea_id"],
            "title": ideas_data.get("title") or s.get("topic_text") or "Untitled",
            "idea_type": ideas_data.get("idea_type"),
            "target_duration_min": s.get("target_duration_min"),
            "thumbnail_url": thumbnail_urls.get(sid),
            "output_type": s.get("output_type"),
            "excalidraw_url": s.get("excalidraw_url"),
        })
    return result


async def _fetch_published(client, user_id: str) -> list[dict[str, Any]]:
    resp = await (
        client.from_("yt_metrics")
        .select("*")
        .order("published_at", desc=True, nullsfirst=False)
        .limit(200)
        .execute()
    )
    return resp.data or []


async def _fetch_channel_summary(client) -> ChannelSummaryOut | None:
    resp = await client.from_("yt_metrics").select("views, ctr, outlier_score, title, watch_time_hrs").execute()
    rows = resp.data or []
    if not rows:
        return None

    total_views = sum(r.get("views") or 0 for r in rows)
    ctrs = [r["ctr"] for r in rows if r.get("ctr") is not None]
    scores = [r["outlier_score"] for r in rows if r.get("outlier_score") is not None]
    best = max(rows, key=lambda r: r.get("views") or 0)

    return ChannelSummaryOut(
        total_views_month=total_views,
        best_video_title=best.get("title"),
        avg_ctr=round(sum(ctrs) / len(ctrs), 4) if ctrs else None,
        avg_outlier_score=round(sum(scores) / len(scores), 2) if scores else None,
        total_videos=len(rows),
    )


async def _fetch_youtube_connected(client) -> bool:
    resp = await client.from_("user_profiles").select("youtube_connected").maybe_single().execute()
    return bool(resp.data.get("youtube_connected")) if resp.data else False


# ── Routes ──────────────────────────────────────────────────────────────────


@router.get("/kanban", response_model=KanbanResponse)
async def get_kanban(ctx: tuple = Depends(current_user)) -> KanbanResponse:
    user_id, token = ctx
    client = await user_client(token)

    results = await asyncio.gather(
        _fetch_ideas(client, str(user_id)),
        _fetch_in_progress(client, str(user_id)),
        _fetch_ready(client, str(user_id)),
        _fetch_published(client, str(user_id)),
        _fetch_channel_summary(client),
        _fetch_youtube_connected(client),
        return_exceptions=True,
    )

    def ok_or_default(idx: int, default: Any) -> Any:
        val = results[idx]
        return default if isinstance(val, BaseException) else val

    return KanbanResponse(
        ideas=ok_or_default(0, []),
        in_progress=ok_or_default(1, []),
        ready=ok_or_default(2, []),
        published=ok_or_default(3, []),
        channel_summary=ok_or_default(4, None),
        youtube_connected=ok_or_default(5, False),
    )


@router.get("/weekly-suggestions")
async def get_weekly_suggestions(
    ctx: tuple = Depends(current_user),
) -> WeeklySuggestionOut | None:
    _user_id, token = ctx
    client = await user_client(token)
    monday = _this_monday()

    resp = await (
        client.from_("weekly_suggestions")
        .select("*")
        .eq("week_start", monday.isoformat())
        .maybe_single()
        .execute()
    )

    row = resp.data if resp else None
    if not row:
        return None

    return WeeklySuggestionOut(
        id=str(row["id"]),
        week_start=str(row["week_start"]),
        ideas=row["ideas"] or [],
        dismissed=bool(row.get("dismissed", False)),
        generated_at=str(row["generated_at"]) if row.get("generated_at") else None,
    )


@router.post("/weekly-suggestions", status_code=201)
async def save_weekly_suggestions(
    body: WeeklySuggestionSaveBody,
    ctx: tuple = Depends(current_user),
) -> WeeklySuggestionOut:
    user_id, token = ctx
    client = await user_client(token)
    monday = _this_monday()

    row = {
        "user_id": str(user_id),
        "week_start": monday.isoformat(),
        "ideas": body.ideas,
        "dismissed": False,
    }

    resp = await (
        client.from_("weekly_suggestions")
        .upsert(row, on_conflict="user_id, week_start")
        .execute()
    )

    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to save weekly suggestions")

    r = resp.data[0]
    return WeeklySuggestionOut(
        id=str(r["id"]),
        week_start=str(r["week_start"]),
        ideas=r["ideas"] or [],
        dismissed=bool(r.get("dismissed", False)),
        generated_at=str(r["generated_at"]) if r.get("generated_at") else None,
    )


@router.post("/weekly-suggestions/dismiss")
async def dismiss_weekly_suggestions(
    ctx: tuple = Depends(current_user),
) -> dict[str, str]:
    user_id, token = ctx
    client = await user_client(token)
    monday = _this_monday()

    await (
        client.from_("weekly_suggestions")
        .update({"dismissed": True})
        .eq("user_id", str(user_id))
        .eq("week_start", monday.isoformat())
        .execute()
    )

    return {"status": "ok"}
