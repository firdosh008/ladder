"""Studio sessions read endpoints.

Routes:
  GET  /studio-sessions/by-idea/{idea_id}
        Hydrate a studio page: returns the latest session + latest script,
        outline, and excalidraw artifacts for the idea.

  PATCH /studio-sessions/{session_id}
        Patch session-level fields (`brand_color`, `brand_id`) whitelisted in
        StudioSessionPatchBody. Used by the studio header brand picker and color
        accents for the scene designer.

  POST /studio-sessions/{session_id}/outline
        Persist a founder-edited outline as a new versioned `outline`
        artifact. Mirrors the same versioning behavior as the streaming
        crew so history is preserved.

  POST /studio-sessions/{session_id}/scene
        Persist an updated scene skeleton (e.g. typography-only refresh)
        as a new versioned `excalidraw` artifact — same shape as crew output.

  POST /studio-sessions/{session_id}/scene/share
        Upload a fully-inflated `.excalidraw` envelope to public Storage
        and return the public URL. The frontend uses this URL to open the
        scene in excalidraw.com via `excalidraw.com/#url=<encoded>`.
        Max serialized envelope size is configurable (`SCENE_PUBLISH_MAX_ENVELOPE_BYTES`).
        See PRD §5.5 (the canonical "open in Excalidraw" affordance).
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4  # noqa: F811 (re-imported in refine)

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.deps import service_client, user_client
from app.middleware.auth import current_user

router = APIRouter(prefix="/studio-sessions", tags=["studio_sessions"])

_SCENE_BUCKET = "excalidraw_scenes"


class StudioSessionByIdea(BaseModel):
    session: dict | None
    script: dict | None
    outline: dict | None
    scene: dict | None
    thumbnails: list[dict] | None = None


_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class StudioSessionPatchBody(BaseModel):
    """Whitelisted session-level fields the frontend can patch.

    Exposes `brand_color`, `brand_id`. Use `exclude_unset` at apply time — each
    key may be patched independently (`brand_color` for excalidraw accents,
    `brand_id` to link the session row to a `brands` record). Pass `null` on a
    key to clear it.
    """

    brand_color: str | None = Field(default=None)
    brand_id: UUID | None = Field(default=None)

    @field_validator("brand_color")
    @classmethod
    def _validate_brand_color(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _HEX_COLOR_RE.match(v):
            raise ValueError("brand_color must be a 7-char hex string like #E8442A")
        return v.upper()


class StudioSessionPatchResponse(BaseModel):
    id: str
    brand_color: str | None
    brand_id: str | None = None


class OutlineSaveBody(BaseModel):
    """Founder-edited outline payload — same shape as the streaming Outline."""

    outline: dict[str, Any]


class OutlineSaveResponse(BaseModel):
    artifact_id: str
    version: int


class ScriptSaveBody(BaseModel):
    """Script payload — same shape as the streaming Script."""

    script: dict[str, Any]


class ScriptSaveResponse(BaseModel):
    artifact_id: str
    version: int


class SceneSkeletonSaveBody(BaseModel):
    """Scene payload matching ``SceneSkeleton`` / frontend ``Scene`` type."""

    scene: dict[str, Any]


class SceneSkeletonSaveResponse(BaseModel):
    artifact_id: str
    version: int


class ScenePublishBody(BaseModel):
    """The full .excalidraw envelope produced by the frontend after running
    `convertToExcalidrawElements()` on the persisted skeleton."""

    envelope: dict[str, Any]


class ScenePublishResponse(BaseModel):
    public_url: str  # raw Storage URL (the .excalidraw file)
    storage_path: str
    excalidraw_url: str  # full https://excalidraw.com/#url=<encoded> — copy/share


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
            session=None, script=None, outline=None, scene=None, thumbnails=None
        )

    session = sess_resp.data[0]
    session_id = session["id"]

    try:
        artifacts_resp = (
            await client.from_("artifacts")
            .select("*")
            .eq("session_id", session_id)
            .in_("type", ["script", "outline", "excalidraw", "thumbnail"])
            .order("version", desc=True)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    script: dict | None = None
    outline: dict | None = None
    scene: dict | None = None
    thumbnails: list[dict] = []
    for a in artifacts_resp.data or []:
        kind = a["type"]
        if kind == "script" and script is None:
            script = a
        elif kind == "outline" and outline is None:
            outline = a
        elif kind == "excalidraw" and scene is None:
            scene = a
        elif kind == "thumbnail":
            # Collect all thumbnail artifacts for this session (up to 6).
            # They come ordered by version DESC so the latest run is first.
            if len(thumbnails) < 6:
                thumbnails.append(a)
        if script and outline and scene and len(thumbnails) >= 6:
            break

    return StudioSessionByIdea(
        session=session,
        script=script,
        outline=outline,
        scene=scene,
        thumbnails=thumbnails if thumbnails else None,
    )


@router.patch(
    "/{session_id}",
    response_model=StudioSessionPatchResponse,
)
async def patch_session(
    session_id: str,
    body: StudioSessionPatchBody,
    ctx: tuple = Depends(current_user),
) -> StudioSessionPatchResponse:
    """Patch the small whitelist of session fields the studio header owns."""
    _user_id, token = ctx
    client = await user_client(token)

    raw_patch = body.model_dump(exclude_unset=True)
    if not raw_patch:
        raise HTTPException(
            status_code=400, detail="at least one of brand_color, brand_id is required",
        )

    update_payload: dict[str, Any] = {}
    if "brand_color" in raw_patch:
        update_payload["brand_color"] = raw_patch["brand_color"]
    if "brand_id" in raw_patch:
        bid = raw_patch["brand_id"]
        update_payload["brand_id"] = str(bid) if bid is not None else None

    try:
        resp = (
            await client.from_("studio_sessions")
            .update(update_payload)
            .eq("id", session_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    if not resp.data:
        raise HTTPException(status_code=404, detail="session not found")

    row = resp.data[0]
    bir = row.get("brand_id")
    return StudioSessionPatchResponse(
        id=str(row["id"]),
        brand_color=row.get("brand_color"),
        brand_id=str(bir) if bir is not None else None,
    )


def _outline_to_text(outline: dict[str, Any]) -> str:
    lines: list[str] = []
    for it in outline.get("items") or []:
        lines.append(
            f"{it.get('number','?')}. {it.get('label','')} — {it.get('beat','')}"
        )
    return "\n".join(lines).strip()


def _script_to_text(script: dict[str, Any]) -> str:
    lines: list[str] = []
    for sec in script.get("sections") or []:
        lines.append(
            f"{sec.get('heading','')} ({sec.get('duration_min','?')} min): "
            + "; ".join(sec.get("talking_points") or [])
        )
    return "\n".join(lines).strip()


@router.post(
    "/{session_id}/script",
    response_model=ScriptSaveResponse,
)
async def save_script(
    session_id: str,
    body: ScriptSaveBody,
    ctx: tuple = Depends(current_user),
) -> ScriptSaveResponse:
    """Persist an AI-patched script as a new versioned ``script`` artifact."""
    user_id, token = ctx
    client = await user_client(token)

    sess_resp = (
        await client.from_("studio_sessions")
        .select("id")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    sess = sess_resp.data if sess_resp is not None else None
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")

    script = body.script
    sections = script.get("sections") if isinstance(script, dict) else None
    if not isinstance(sections, list) or not sections:
        raise HTTPException(status_code=400, detail="script.sections must be a non-empty list")

    latest = (
        await client.from_("artifacts")
        .select("version")
        .eq("session_id", session_id)
        .eq("type", "script")
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    next_version = int(latest.data[0]["version"]) + 1 if latest.data else 1

    inserted = (
        await client.from_("artifacts")
        .insert(
            {
                "user_id": str(user_id),
                "session_id": session_id,
                "type": "script",
                "version": next_version,
                "content_text": _script_to_text(script),
                "content_json": script,
            }
        )
        .execute()
    )
    if not inserted.data:
        raise HTTPException(status_code=500, detail="script insert returned no row")

    return ScriptSaveResponse(
        artifact_id=str(inserted.data[0]["id"]),
        version=next_version,
    )


@router.post(
    "/{session_id}/outline",
    response_model=OutlineSaveResponse,
)
async def save_outline(
    session_id: str,
    body: OutlineSaveBody,
    ctx: tuple = Depends(current_user),
) -> OutlineSaveResponse:
    """Persist a founder-edited outline as a new versioned `outline` artifact.

    Inserts at version+1 and mirrors the plain-text rendering on the
    `studio_sessions.scene_outline` column so the kanban preview stays in
    sync. RLS makes sure only the session owner can write here.
    """
    user_id, token = ctx
    client = await user_client(token)

    # Confirm the session exists + RLS-owned by the caller.
    sess_resp = (
        await client.from_("studio_sessions")
        .select("id")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    sess = sess_resp.data if sess_resp is not None else None
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")

    outline = body.outline
    items = outline.get("items") if isinstance(outline, dict) else None
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="outline.items must be a non-empty list")

    # Pick the next version slot for this session's outline artifacts.
    latest = (
        await client.from_("artifacts")
        .select("version")
        .eq("session_id", session_id)
        .eq("type", "outline")
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    next_version = int(latest.data[0]["version"]) + 1 if latest.data else 1

    inserted = (
        await client.from_("artifacts")
        .insert(
            {
                "user_id": str(user_id),
                "session_id": session_id,
                "type": "outline",
                "version": next_version,
                "content_text": _outline_to_text(outline),
                "content_json": outline,
            }
        )
        .execute()
    )
    if not inserted.data:
        raise HTTPException(status_code=500, detail="outline insert returned no row")

    # Mirror onto the session row so the kanban preview reflects the edit.
    try:
        await (
            client.from_("studio_sessions")
            .update({"scene_outline": _outline_to_text(outline)})
            .eq("id", session_id)
            .execute()
        )
    except Exception:
        pass

    return OutlineSaveResponse(
        artifact_id=str(inserted.data[0]["id"]),
        version=next_version,
    )


@router.post(
    "/{session_id}/scene",
    response_model=SceneSkeletonSaveResponse,
)
async def save_scene_skeleton(
    session_id: str,
    body: SceneSkeletonSaveBody,
    ctx: tuple = Depends(current_user),
) -> SceneSkeletonSaveResponse:
    """Persist an updated scene skeleton as a new versioned ``excalidraw`` row.

    Used for founder-driven edits that keep geometry intact — e.g. bulk
    ``fontFamily`` swaps — without re-running the scene LLM crew.
    """
    user_id, token = ctx
    client = await user_client(token)

    sess_resp = (
        await client.from_("studio_sessions")
        .select("id")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    sess = sess_resp.data if sess_resp is not None else None
    if not sess:
        raise HTTPException(status_code=404, detail="session not found")

    scene = body.scene
    elements = scene.get("elements") if isinstance(scene, dict) else None
    if not isinstance(elements, list) or len(elements) == 0:
        raise HTTPException(
            status_code=400,
            detail="scene.elements must be a non-empty list",
        )

    latest = (
        await client.from_("artifacts")
        .select("version")
        .eq("session_id", session_id)
        .eq("type", "excalidraw")
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    next_version = int(latest.data[0]["version"]) + 1 if latest.data else 1

    cw = scene.get("canvas_width")
    ch = scene.get("canvas_height")
    summary = (
        f"Scene skeleton — {len(elements)} elements on a "
        f"{cw}×{ch} canvas."
    )

    inserted = (
        await client.from_("artifacts")
        .insert(
            {
                "user_id": str(user_id),
                "session_id": session_id,
                "type": "excalidraw",
                "version": next_version,
                "content_text": summary,
                "content_json": scene,
            }
        )
        .execute()
    )
    if not inserted.data:
        raise HTTPException(status_code=500, detail="scene insert returned no row")

    return SceneSkeletonSaveResponse(
        artifact_id=str(inserted.data[0]["id"]),
        version=next_version,
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
    max_bytes = settings.SCENE_PUBLISH_MAX_ENVELOPE_BYTES
    if len(blob) > max_bytes:
        cap_mb = max_bytes / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=(
                f"envelope exceeds publish limit ({cap_mb:.1f} MiB). "
                "Raise SCENE_PUBLISH_MAX_ENVELOPE_BYTES in server config or "
                "reduce embedded images in the scene."
            ),
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

    excalidraw_url = f"https://excalidraw.com/#url={quote(public_url, safe='')}"
    return ScenePublishResponse(
        public_url=public_url,
        storage_path=storage_path,
        excalidraw_url=excalidraw_url,
    )


class ChatHistoryResponse(BaseModel):
    messages: list[dict[str, Any]]


@router.get(
    "/{session_id}/chat",
    response_model=ChatHistoryResponse,
)
async def get_chat_history(
    session_id: str, ctx: tuple = Depends(current_user)
) -> ChatHistoryResponse:
    """Return the full chat history for a session."""
    _user_id, token = ctx
    client = await user_client(token)

    try:
        resp = (
            await client.from_("chat_messages")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    return ChatHistoryResponse(messages=resp.data or [])


# ─── Thumbnail: select + refine ──────────────────────────────────────────────


class ThumbnailSelectBody(BaseModel):
    """Select which thumbnail variant is the session's primary thumbnail."""

    artifact_id: UUID


class ThumbnailSelectResponse(BaseModel):
    thumbnail_selected_id: str | None


@router.post(
    "/{session_id}/thumbnail/select",
    response_model=ThumbnailSelectResponse,
)
async def select_thumbnail(
    session_id: str,
    body: ThumbnailSelectBody,
    ctx: tuple = Depends(current_user),
) -> ThumbnailSelectResponse:
    """Set ``thumbnail_selected_id`` on the session row."""
    _user_id, token = ctx
    client = await user_client(token)

    try:
        resp = (
            await client.from_("studio_sessions")
            .update({"thumbnail_selected_id": str(body.artifact_id)})
            .eq("id", session_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    if not resp.data:
        raise HTTPException(status_code=404, detail="session not found")

    row = resp.data[0]
    tsid = row.get("thumbnail_selected_id")
    return ThumbnailSelectResponse(
        thumbnail_selected_id=str(tsid) if tsid else None,
    )


class ThumbnailRefineBody(BaseModel):
    """Refine a thumbnail variant — re-generates with new instruction."""

    artifact_id: UUID
    instruction: str = Field(min_length=1, max_length=500)


class ThumbnailRefineResponse(BaseModel):
    artifact_id: str
    file_url: str
    storage_path: str
    width: int
    height: int


@router.post(
    "/{session_id}/thumbnail/refine",
    response_model=ThumbnailRefineResponse,
)
async def refine_thumbnail(
    session_id: str,
    body: ThumbnailRefineBody,
    ctx: tuple = Depends(current_user),
) -> ThumbnailRefineResponse:
    """Refine an existing thumbnail with a new instruction.

    Fetches the existing artifact, extracts its prompt context, appends the
    refinement instruction, and generates a single new variant.
    """
    user_id, token = ctx
    client = await user_client(token)

    # Verify session exists
    sess_resp = (
        await client.from_("studio_sessions")
        .select("id")
        .eq("id", session_id)
        .maybe_single()
        .execute()
    )
    if not sess_resp.data:
        raise HTTPException(status_code=404, detail="session not found")

    # Load the existing thumbnail artifact
    art_resp = (
        await client.from_("artifacts")
        .select("id, type, content_json, file_url, storage_path")
        .eq("id", str(body.artifact_id))
        .eq("type", "thumbnail")
        .maybe_single()
        .execute()
    )
    if not art_resp.data:
        raise HTTPException(status_code=404, detail="thumbnail artifact not found")

    artifact = art_resp.data
    content_json = artifact.get("content_json") or {}

    # Build refinement prompt with safety constraints
    refinement_prompt = (
        f"Refine this YouTube thumbnail design based on the following instruction: "
        f"{body.instruction}. "
        f"Keep the same general subject and layout but apply the requested changes. "
        f"Clean graphic-design style with bold typography and abstract geometric elements. "
        f"High contrast, saturated colors, educational tech aesthetic. "
        f"IMPORTANT: NO human faces, NO people, NO photorealistic humans, "
        f"NO celebrities. Use ONLY abstract art, typography, icons, and shapes."
    )[:3900]

    # Check config
    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    from app.agents.thumbnail.crew import _generate_one_image, _resolve_image_model

    data_url = await _generate_one_image(refinement_prompt)
    if not data_url:
        raise HTTPException(
            status_code=500,
            detail="Image generation failed. The prompt may have been blocked by safety filters. Try a different instruction.",
        )

    # Decode and upload
    import base64
    from uuid import uuid4

    try:
        header, b64_data = data_url.split(",", 1)
        img_bytes = base64.b64decode(b64_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bad image data: {e}") from e

    from app.deps import service_client as _service_client

    sb_admin = await _service_client()
    storage_path = f"{user_id}/{session_id}/thumbnails/{uuid4().hex}.png"

    try:
        await sb_admin.storage.from_("excalidraw_scenes").upload(
            path=storage_path,
            file=img_bytes,
            file_options={
                "content-type": "image/png",
                "cache-control": "public, max-age=31536000",
            },
        )
        public_url = await sb_admin.storage.from_("excalidraw_scenes").get_public_url(
            storage_path
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {e}") from e

    # Persist as new artifact
    latest = (
        await client.from_("artifacts")
        .select("version")
        .eq("session_id", session_id)
        .eq("type", "thumbnail")
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    next_version = int(latest.data[0]["version"]) + 1 if latest.data else 1

    inserted = (
        await client.from_("artifacts")
        .insert(
            {
                "user_id": str(user_id),
                "session_id": session_id,
                "type": "thumbnail",
                "version": next_version,
                "content_text": f"Refined thumbnail — {body.instruction[:100]}",
                "content_json": {
                    "width": 1792,
                    "height": 1024,
                    "refined_from_artifact_id": str(body.artifact_id),
                    "refinement_instruction": body.instruction,
                    "prompt_version": (
                        content_json.get("prompt_version") or 1
                    ) + 1,
                },
                "file_url": public_url,
                "storage_path": storage_path,
            }
        )
        .execute()
    )
    if not inserted.data:
        raise HTTPException(status_code=500, detail="artifact insert returned no row")

    return ThumbnailRefineResponse(
        artifact_id=str(inserted.data[0]["id"]),
        file_url=public_url,
        storage_path=storage_path,
        width=1792,
        height=1024,
    )
