"""Settings routes — API keys, model prefs, skill files, integrations. PRD §8.3-8.5"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from app.deps import service_client, user_client
from app.middleware.auth import current_user
from app.services.linkedin import import_from_json_export, scrape_and_seed, seed_from_text

router = APIRouter(prefix="/settings", tags=["settings"])

MAX_SKILL_FILES = 3
MAX_SKILL_KB = 50


# ── API Keys ──────────────────────────────────────────────────────────────────

class KeyInfo(BaseModel):
    provider: str
    has_key: bool
    masked: str | None = None  # e.g. "sk-ant-...abc123"


@router.get("/keys", response_model=list[KeyInfo])
async def list_keys(ctx: tuple = Depends(current_user)) -> list[KeyInfo]:
    user_id, token = ctx
    client = await user_client(token)
    result = (
        await client.from_("api_keys")
        .select("provider,encrypted_key")
        .eq("user_id", str(user_id))
        .execute()
    )
    rows = result.data or []
    key_map = {r["provider"]: r["encrypted_key"] for r in rows}

    providers = ["anthropic", "openai", "google"]
    out = []
    for p in providers:
        enc = key_map.get(p)
        if enc:
            last4 = enc[-4:]
            masked = f"{enc[:3]}...{last4}"
            out.append(KeyInfo(provider=p, has_key=True, masked=masked))
        else:
            out.append(KeyInfo(provider=p, has_key=False))
    return out


class KeyPayload(BaseModel):
    provider: str
    key: str


@router.post("/keys", status_code=201)
async def save_key(
    payload: KeyPayload, ctx: tuple = Depends(current_user)
) -> dict:
    if payload.provider not in ("anthropic", "openai", "google"):
        raise HTTPException(status_code=400, detail="Unknown provider")
    if not payload.key.strip():
        raise HTTPException(status_code=400, detail="Key is required")

    user_id, token = ctx
    client = await user_client(token)

    # Simple server-side encryption: store as-is for now (Supabase vault in production).
    # Keys are stored in a user-owned RLS table — only the owner can read them.
    await (
        client.from_("api_keys")
        .upsert(
            {
                "user_id": str(user_id),
                "provider": payload.provider,
                "encrypted_key": payload.key.strip(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="user_id,provider",
        )
        .execute()
    )
    return {"ok": True}


@router.delete("/keys/{provider}", status_code=204)
async def delete_key(
    provider: str, ctx: tuple = Depends(current_user)
) -> None:
    if provider not in ("anthropic", "openai", "google"):
        raise HTTPException(status_code=400, detail="Unknown provider")
    user_id, token = ctx
    client = await user_client(token)
    await (
        client.from_("api_keys")
        .delete()
        .eq("user_id", str(user_id))
        .eq("provider", provider)
        .execute()
    )


# ── Model Preferences ─────────────────────────────────────────────────────────

FUNCTION_DEFAULTS = {
    "script_generation":    {"model": "Claude Sonnet 4.5",  "provider": "anthropic"},
    "scene_generation":     {"model": "Claude Sonnet 4.5",  "provider": "anthropic"},
    "scene_editing":        {"model": "Claude Sonnet 4.5",  "provider": "anthropic"},
    "research_agent":       {"model": "GPT-4o",             "provider": "openai"},
    "refine_chat":          {"model": "Claude Sonnet 4.5",  "provider": "anthropic"},
    "content_extraction":   {"model": "Gemini 1.5 Pro",     "provider": "google"},
    "thumbnail_generation":  {"model": "DALL-E 3",          "provider": "image"},
    "newsletter_extraction": {"model": "Claude Haiku",      "provider": "anthropic"},
}

AVAILABLE_MODELS = {
    "anthropic": ["Claude Opus 4.5", "Claude Sonnet 4.5", "Claude Haiku"],
    "openai":    ["GPT-4o", "GPT-4o Mini", "GPT-4-turbo"],
    "google":    ["Gemini 1.5 Pro", "Gemini 1.5 Flash"],
    "image":     ["DALL-E 3", "NanoBanana Pro"],
}

PROVIDER_LABELS = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "google": "Google AI",
    "image": "Image",
}


class ModelPrefRow(BaseModel):
    function_name: str
    model: str
    provider: str


class EstimatedCost(BaseModel):
    function_name: str
    avg_cost: float | None = None
    avg_tokens: int | None = None


@router.get("/model-prefs", response_model=list[ModelPrefRow])
async def list_model_prefs(ctx: tuple = Depends(current_user)) -> list[ModelPrefRow]:
    user_id, token = ctx
    client = await user_client(token)
    result = (
        await client.from_("user_model_prefs")
        .select("function_name,model,provider")
        .eq("user_id", str(user_id))
        .execute()
    )
    rows = result.data or []
    prefs = {r["function_name"]: r for r in rows}

    out = []
    for fn, defaults in FUNCTION_DEFAULTS.items():
        row = prefs.get(fn)
        out.append(ModelPrefRow(
            function_name=fn,
            model=row["model"] if row else defaults["model"],
            provider=row["provider"] if row else defaults["provider"],
        ))
    return out


@router.put("/model-prefs")
async def save_model_pref(
    payload: ModelPrefRow, ctx: tuple = Depends(current_user)
) -> dict:
    user_id, token = ctx
    client = await user_client(token)

    if payload.function_name not in FUNCTION_DEFAULTS:
        raise HTTPException(status_code=400, detail="Unknown function")
    if payload.provider not in AVAILABLE_MODELS:
        raise HTTPException(status_code=400, detail="Unknown provider")

    await (
        client.from_("user_model_prefs")
        .upsert(
            {
                "user_id": str(user_id),
                "function_name": payload.function_name,
                "model": payload.model,
                "provider": payload.provider,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="user_id,function_name",
        )
        .execute()
    )
    return {"ok": True}


@router.get("/estimated-costs", response_model=list[EstimatedCost])
async def estimated_costs(ctx: tuple = Depends(current_user)) -> list[EstimatedCost]:
    user_id, token = ctx
    client = await user_client(token)
    result = (
        await client.from_("usage_log")
        .select("function_name,cost_usd,input_tokens,output_tokens")
        .eq("user_id", str(user_id))
        .execute()
    )
    rows = result.data or []
    agg: dict[str, list[dict]] = {}
    for r in rows:
        fn = r["function_name"]
        if fn not in agg:
            agg[fn] = []
        agg[fn].append(r)

    out = []
    for fn in FUNCTION_DEFAULTS:
        entries = agg.get(fn, [])
        if entries:
            avg_cost = sum(e["cost_usd"] or 0 for e in entries) / len(entries)
            avg_tokens = sum(
                (e.get("input_tokens") or 0) + (e.get("output_tokens") or 0)
                for e in entries
            ) // len(entries)
            out.append(EstimatedCost(
                function_name=fn, avg_cost=round(avg_cost, 4), avg_tokens=avg_tokens
            ))
        else:
            out.append(EstimatedCost(function_name=fn))
    return out


# ── Skill Files ───────────────────────────────────────────────────────────────

class SkillFileResponse(BaseModel):
    id: str
    filename: str
    storage_path: str
    file_summary: str | None = None
    file_size_kb: int | None = None
    created_at: str | None = None


@router.get("/skills", response_model=list[SkillFileResponse])
async def list_skills(ctx: tuple = Depends(current_user)) -> list[SkillFileResponse]:
    user_id, token = ctx
    client = await user_client(token)
    result = (
        await client.from_("skill_files")
        .select("id,filename,storage_path,file_summary,file_size_kb,created_at")
        .eq("user_id", str(user_id))
        .order("created_at")
        .execute()
    )
    return [SkillFileResponse(**r) for r in (result.data or [])]


def _summarize_md(content: str, max_chars: int = 160) -> str:
    """Extract first heading or first non-empty line as a summary."""
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:max_chars]
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped:
            return stripped[:max_chars]
    return "(empty file)"


@router.post("/skills", status_code=201)
async def upload_skill(
    file: UploadFile, ctx: tuple = Depends(current_user)
) -> SkillFileResponse:
    user_id, token = ctx

    # Validate file type
    filename = file.filename or "untitled.md"
    if not filename.lower().endswith(".md"):
        raise HTTPException(
            status_code=400, detail="Only .md files are accepted"
        )

    raw = await file.read()

    # Check size limits
    file_kb = round(len(raw) / 1024, 1)
    if file_kb > MAX_SKILL_KB:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds {MAX_SKILL_KB} KB limit (is {file_kb} KB)",
        )

    # Count existing files
    client = await user_client(token)
    existing = (
        await client.from_("skill_files")
        .select("id,file_size_kb")
        .eq("user_id", str(user_id))
        .execute()
    )
    rows = existing.data or []

    if len(rows) >= MAX_SKILL_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_SKILL_FILES} skill files allowed",
        )

    combined_kb = sum((r.get("file_size_kb") or 0) for r in rows) + file_kb
    if combined_kb > MAX_SKILL_KB:
        raise HTTPException(
            status_code=400,
            detail=f"Combined size would exceed {MAX_SKILL_KB} KB ({round(combined_kb, 1)} KB)",
        )

    # Upload to storage
    safe_name = f"{uuid.uuid4()}.md"
    storage_path = f"{user_id}/{safe_name}"

    admin_client = await service_client()
    try:
        await (
            admin_client.storage
            .from_("skill_files")
            .upload(
                storage_path, raw, {"content-type": "text/markdown", "upsert": "false"}
            )
        )
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Storage upload failed: {e}"
        ) from e

    # Generate summary
    content = raw.decode("utf-8", errors="replace")
    summary = _summarize_md(content)

    # Insert DB row
    result = (
        await client.from_("skill_files")
        .insert({
            "user_id": str(user_id),
            "filename": filename,
            "storage_path": storage_path,
            "file_summary": summary,
            "file_size_kb": file_kb,
        })
        .execute()
    )
    row = result.data[0] if result.data else None
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create skill file record")
    return SkillFileResponse(**row)


@router.delete("/skills/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: str, ctx: tuple = Depends(current_user)
) -> None:
    user_id, token = ctx
    client = await user_client(token)

    # Get storage path first
    row = (
        await client.from_("skill_files")
        .select("storage_path")
        .eq("id", skill_id)
        .eq("user_id", str(user_id))
        .maybe_single()
        .execute()
    )
    row_data = getattr(row, "data", None) if row is not None else None
    if not row_data:
        raise HTTPException(status_code=404, detail="Skill file not found")

    # Delete from storage
    admin_client = await service_client()
    try:
        await (
            admin_client.storage
            .from_("skill_files")
            .remove([row_data["storage_path"]])
        )
    except Exception:
        pass  # Don't fail the delete if storage cleanup fails

    # Delete from DB
    await (
        client.from_("skill_files")
        .delete()
        .eq("id", skill_id)
        .eq("user_id", str(user_id))
        .execute()
    )


# ── Integrations ──────────────────────────────────────────────────────────────

class IntegrationToken(BaseModel):
    token: str


class YouTubeCreds(BaseModel):
    client_id: str
    client_secret: str


@router.post("/integrations/notion")
async def save_notion_token(
    payload: IntegrationToken, ctx: tuple = Depends(current_user)
) -> dict:
    user_id, token = ctx
    client = await user_client(token)
    await (
        client.from_("user_profiles")
        .update({"notion_token": payload.token.strip()})
        .eq("user_id", str(user_id))
        .execute()
    )
    return {"ok": True}


@router.post("/integrations/gamma")
async def save_gamma_key(
    payload: IntegrationToken, ctx: tuple = Depends(current_user)
) -> dict:
    user_id, token = ctx
    client = await user_client(token)
    await (
        client.from_("user_profiles")
        .update({"gamma_api_key": payload.token.strip()})
        .eq("user_id", str(user_id))
        .execute()
    )
    return {"ok": True}


@router.post("/integrations/nano-banana")
async def save_nano_banana_key(
    payload: IntegrationToken, ctx: tuple = Depends(current_user)
) -> dict:
    user_id, token = ctx
    client = await user_client(token)
    await (
        client.from_("user_profiles")
        .update({"nano_banana_api_key": payload.token.strip()})
        .eq("user_id", str(user_id))
        .execute()
    )
    return {"ok": True}


@router.post("/integrations/youtube")
async def save_youtube_creds(
    payload: YouTubeCreds, ctx: tuple = Depends(current_user)
) -> dict:
    user_id, token = ctx
    client = await user_client(token)
    await (
        client.from_("user_profiles")
        .update({
            "youtube_client_id": payload.client_id.strip(),
            "youtube_client_secret": payload.client_secret.strip(),
        })
        .eq("user_id", str(user_id))
        .execute()
    )
    return {"ok": True, "message": "YouTube credentials saved. OAuth flow not yet implemented."}


@router.post("/integrations/linkedin")
async def save_linkedin(
    payload: IntegrationToken, ctx: tuple = Depends(current_user)
) -> dict:
    user_id, token = ctx
    url = payload.token.strip()

    client = await user_client(token)
    await (
        client.from_("user_profiles")
        .update({"linkedin_url": url})
        .eq("user_id", str(user_id))
        .execute()
    )

    result = await scrape_and_seed(user_id, url, token)
    return result


@router.post("/integrations/linkedin/manual")
async def save_linkedin_manual(
    payload: IntegrationToken, ctx: tuple = Depends(current_user)
) -> dict:
    user_id, token = ctx
    return await seed_from_text(user_id, payload.token, token)


@router.post("/integrations/linkedin/import")
async def import_linkedin_export(
    file: UploadFile, ctx: tuple = Depends(current_user)
) -> dict:
    user_id, token = ctx

    filename = file.filename or "export"
    lower = filename.lower()
    if not (lower.endswith(".json") or lower.endswith(".pdf")):
        raise HTTPException(
            status_code=400, detail="Only .json or .pdf files are accepted. Please upload your LinkedIn data export."
        )

    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=400, detail="File too large (max 5 MB)."
        )

    if lower.endswith(".pdf"):
        return await _import_from_pdf(user_id, raw, token)

    try:
        import json
        json_data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=400, detail="Invalid JSON file. Please upload your LinkedIn data export JSON."
        )

    if not isinstance(json_data, dict):
        raise HTTPException(
            status_code=400, detail="JSON must be an object. Please upload your LinkedIn profile export."
        )

    return await import_from_json_export(user_id, json_data, token)


async def _import_from_pdf(user_id: uuid.UUID, raw: bytes, token: str) -> dict:
    """Extract text from a LinkedIn profile PDF and feed it into knowledge_nodes."""
    from io import BytesIO
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(raw))
    except Exception:
        raise HTTPException(
            status_code=400, detail="Could not read PDF file. Please upload a valid LinkedIn profile PDF."
        )

    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)

    text = "\n".join(pages).strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="No text could be extracted from the PDF. The file may be scanned or image-based.",
        )

    return await seed_from_text(user_id, text, token)


@router.delete("/integrations/{provider}", status_code=204)
async def disconnect_integration(
    provider: str, ctx: tuple = Depends(current_user)
) -> None:
    user_id, token = ctx
    client = await user_client(token)

    if provider == "youtube":
        patch = {
            "youtube_connected": False,
            "youtube_channel_name": None,
            "youtube_subscriber_count": None,
            "youtube_last_sync": None,
            "youtube_client_id": None,
            "youtube_client_secret": None,
        }
    elif provider == "notion":
        patch = {"notion_token": None}
    elif provider == "gamma":
        patch = {"gamma_api_key": None}
    elif provider == "nano-banana":
        patch = {"nano_banana_api_key": None}
    elif provider == "linkedin":
        patch = {"linkedin_url": None, "linkedin_imported_at": None}
    else:
        raise HTTPException(status_code=400, detail="Unknown integration provider")

    await (
        client.from_("user_profiles")
        .update(patch)
        .eq("user_id", str(user_id))
        .execute()
    )


@router.get("/integrations")
async def list_integrations(ctx: tuple = Depends(current_user)) -> list[dict]:
    user_id, token = ctx
    client = await user_client(token)
    result = (
        await client.from_("user_profiles")
        .select(
            "youtube_connected,youtube_channel_name,youtube_subscriber_count,"
            "youtube_last_sync,youtube_client_id,notion_token,gamma_api_key,"
            "nano_banana_api_key,linkedin_url,linkedin_imported_at"
        )
        .eq("user_id", str(user_id))
        .maybe_single()
        .execute()
    )
    row = (getattr(result, "data", None) if result is not None else None) or {}

    return [
        {
            "name": "YouTube",
            "connected": bool(row.get("youtube_connected")),
            "channel_name": row.get("youtube_channel_name"),
            "subscriber_count": row.get("youtube_subscriber_count"),
            "last_sync": row.get("youtube_last_sync"),
            "has_creds": bool(row.get("youtube_client_id")),
        },
        {
            "name": "Notion",
            "connected": bool(row.get("notion_token")),
        },
        {
            "name": "Gamma",
            "connected": bool(row.get("gamma_api_key")),
        },
        {
            "name": "NanoBanana Pro",
            "connected": bool(row.get("nano_banana_api_key")),
        },
        {
            "name": "LinkedIn",
            "connected": bool(row.get("linkedin_url")),
            "url": row.get("linkedin_url"),
            "imported_at": row.get("linkedin_imported_at"),
        },
    ]
