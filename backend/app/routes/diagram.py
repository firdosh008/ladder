"""Diagram generation via Claude + local Excalidraw MCP canvas (HTTP-backed)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.deps import service_client, user_client
from app.middleware.auth import current_user
from app.services import excalidraw_canvas
from app.services.diagram_service import DiagramService

router = APIRouter(tags=["diagram"])
log = logging.getLogger(__name__)

_SCENE_BUCKET = "excalidraw_scenes"


class GenerateDiagramBody(BaseModel):
    script: str = Field(..., max_length=80_000)
    session_id: str | None = Field(
        default=None,
        description="When set, persists a versioned ``excalidraw`` artifact for this studio session.",
    )


class GenerateDiagramResponse(BaseModel):
    """Wire JSON still uses the key ``json`` (alias); Python field is ``diagram`` so BaseModel.json is not shadowed."""

    model_config = ConfigDict(populate_by_name=True)

    diagram_url: str | None = None
    diagram: dict[str, Any] = Field(
        ...,
        serialization_alias="json",
        validation_alias="json",
    )
    artifact_id: str | None = None


def _vendor_path() -> Path | None:
    raw = settings.EXCALIDRAW_VENDOR_ROOT.strip()
    return Path(raw) if raw else None


async def _next_artifact_version(jwt: str, session_id: str) -> int:
    client = await user_client(jwt)
    resp = (
        await client.from_("artifacts")
        .select("version")
        .eq("session_id", session_id)
        .eq("type", "excalidraw")
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    if resp.data:
        return int(resp.data[0]["version"]) + 1
    return 1


async def _persist_diagram_scene(
    user_id_str: str,
    jwt: str,
    session_id: str,
    scene: dict[str, Any],
) -> str:
    client = await user_client(jwt)
    ver = await _next_artifact_version(jwt, session_id)
    el_count = len(scene.get("elements") or [])
    summary = f"MCP Canvas diagram — {el_count} elements."
    inserted = (
        await client.from_("artifacts")
        .insert(
            {
                "user_id": user_id_str,
                "session_id": session_id,
                "type": "excalidraw",
                "version": ver,
                "content_text": summary,
                "content_json": scene,
            },
        )
        .execute()
    )
    if not inserted.data:
        raise RuntimeError("diagram artifact insert returned no row")
    return str(inserted.data[0]["id"])


@router.post(
    "/generate-diagram",
    response_model=GenerateDiagramResponse,
    response_model_by_alias=True,
)
async def generate_diagram(
    body: GenerateDiagramBody,
    ctx: tuple = Depends(current_user),
) -> GenerateDiagramResponse:
    user_uuid, jwt = ctx
    user_id_str = str(user_uuid)

    vendor = _vendor_path()

    async def _boot_canvas() -> None:
        await excalidraw_canvas.ensure_canvas_running(
            vendor=vendor,
            http_base=settings.EXCALIDRAW_HTTP_URL,
            autostart=settings.EXCALIDRAW_CANVAS_AUTOSTART,
        )

    try:
        await asyncio.wait_for(_boot_canvas(), timeout=600.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Excalidraw canvas boot timed out") from None

    svc = DiagramService(canvas_base_url=settings.EXCALIDRAW_HTTP_URL)
    try:
        result = await svc.generate_diagram(
            body.script,
            wait_for_live_viewer_seconds=55.0,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        log.exception("diagram generation failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    scene_payload = result["scene"]

    png_bytes = result.get("diagram_png_bytes")
    png_url: str | None = None

    if isinstance(png_bytes, (bytes, bytearray)) and len(png_bytes) > 0:
        sb_admin = await service_client()
        storage_path = f"{user_id_str}/{body.session_id or 'adhoc'}/diagram-{uuid4().hex}.png"
        try:
            await sb_admin.storage.from_(_SCENE_BUCKET).upload(
                path=storage_path,
                file=bytes(png_bytes),
                file_options={
                    "content-type": "image/png",
                    "x-upsert": "true",
                    "cache-control": "public, max-age=3600",
                },
            )
            png_url = await sb_admin.storage.from_(_SCENE_BUCKET).get_public_url(storage_path)
        except Exception:
            log.exception("diagram PNG upload failed — returning JSON only")

    artifact_id: str | None = None
    sid = body.session_id
    if sid:
        try:
            artifact_id = await _persist_diagram_scene(
                user_id_str,
                jwt,
                sid,
                scene_payload,
            )
        except Exception as e:
            log.exception("failed to persist excalidraw artifact")
            raise HTTPException(status_code=500, detail=f"artifact persist failed: {e}") from e

    return GenerateDiagramResponse(
        diagram_url=png_url,
        diagram=scene_payload,
        artifact_id=artifact_id,
    )
