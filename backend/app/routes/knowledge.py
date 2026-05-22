"""REST endpoints for Library: knowledge graph, sources, insights.

Knowledge nodes:
  GET  /knowledge              list caller's nodes (paginated, filterable)
  POST /knowledge              create manual node (with embedding)
  DELETE /knowledge/{id}       soft-delete a node
  GET  /knowledge/accumulated  auto-accumulated feed (scripts, ideas, etc.)
  GET  /knowledge/topics       topic territory analysis

Sources:
  GET   /sources               list caller's sources
  POST  /sources               create a source
  PATCH /sources/{id}          toggle active/paused
  DELETE /sources/{id}         delete source
  GET   /sources/{id}/items    last 5 newsletter items for a source

Insights:
  GET   /insights              curated signals (last 7 days)
  PATCH /insights/{id}/read    mark as read
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from jose import jwt
from pydantic import BaseModel, Field

from app.deps import user_client
from app.middleware.auth import current_user
from app.services.embeddings import chunk_and_embed

router = APIRouter(tags=["knowledge"])

# ─── Pydantic models ────────────────────────────────────────────────────────


class KnowledgeNodeResponse(BaseModel):
    id: str
    source_type: str | None = None
    source_id: str | None = None
    content_chunk: str
    topic_tags: list[str] | None = None
    created_at: str | None = None
    title: str | None = None


class KnowledgeListResponse(BaseModel):
    nodes: list[KnowledgeNodeResponse]
    has_more: bool


class KnowledgeCreate(BaseModel):
    title: str | None = None
    content_chunk: str = Field(min_length=1, max_length=10000)
    topic_tags: list[str] | None = None


class AccumulatedEntry(BaseModel):
    id: str
    source_type: str
    source_title: str | None = None
    summary: str | None = None
    created_at: str | None = None
    session_id: str | None = None


class AccumulatedFeedResponse(BaseModel):
    entries: list[AccumulatedEntry]


class TagCount(BaseModel):
    tag: str
    count: int


class TopicTerritoryResponse(BaseModel):
    covered: list[TagCount]
    thin: list[TagCount]
    open_gaps: list[str]


class InsightResponse(BaseModel):
    id: str
    title: str
    body: str | None = None
    signal_type: str | None = None
    source_ref: str | None = None
    read: bool = False
    created_at: str | None = None


class InsightsListResponse(BaseModel):
    insights: list[InsightResponse]


class SourceResponse(BaseModel):
    id: str
    name: str
    source_type: str | None = None
    sender_email: str | None = None
    auto_extract: bool = True
    status: str = "active"
    last_received_at: str | None = None
    created_at: str | None = None
    ideas_extracted_this_month: int = 0


class SourcesListResponse(BaseModel):
    sources: list[SourceResponse]


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_type: str | None = None
    sender_email: str | None = None
    auto_extract: bool = True


class SourceUpdate(BaseModel):
    status: str | None = None  # "active" | "paused"


class NewsletterItemResponse(BaseModel):
    id: str
    received_at: str | None = None
    subject: str | None = None
    summary: str | None = None
    processed_at: str | None = None


class SourceItemsResponse(BaseModel):
    items: list[NewsletterItemResponse]
    ideas_extracted_this_month: int


# ─── Knowledge nodes ────────────────────────────────────────────────────────


@router.get("/knowledge", response_model=KnowledgeListResponse)
async def list_knowledge(
    ctx: tuple = Depends(current_user),
    source_type: str | None = Query(default=None),
    before: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> KnowledgeListResponse:
    """List caller's knowledge_nodes. RLS enforces user_id filter."""
    _user_id, token = ctx
    client = await user_client(token)

    q = (
        client.from_("knowledge_nodes")
        .select("*")
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .limit(limit + 1)
    )
    if source_type:
        q = q.eq("source_type", source_type)
    if before:
        q = q.lt("created_at", before)

    try:
        result = await q.execute()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    rows = result.data or []
    has_more = len(rows) > limit
    nodes = rows[:limit]

    return KnowledgeListResponse(nodes=nodes, has_more=has_more)


@router.post("/knowledge", response_model=KnowledgeNodeResponse, status_code=201)
async def create_knowledge(
    payload: KnowledgeCreate, ctx: tuple = Depends(current_user)
) -> KnowledgeNodeResponse:
    """Create manual knowledge node(s). Chunks long content and inserts one row per chunk."""
    user_id, token = ctx
    client = await user_client(token)

    pairs = await chunk_and_embed(payload.content_chunk)
    if not pairs:
        # No embeddings generated (e.g. missing API key) — insert a single
        # unembedded row so the content is still saved.
        try:
            result = await client.from_("knowledge_nodes").insert({
                "user_id": str(user_id),
                "source_type": "manual",
                "content_chunk": payload.content_chunk,
                "topic_tags": payload.topic_tags or [],
                "title": payload.title,
            }).execute()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e
        if not result.data:
            raise HTTPException(status_code=400, detail="Insert returned no row")
        return KnowledgeNodeResponse(**result.data[0])

    rows = []
    for i, (chunk_text, embedding) in enumerate(pairs):
        chunk_title = payload.title
        if chunk_title and len(pairs) > 1:
            chunk_title = f"{chunk_title} (part {i + 1}/{len(pairs)})"
        rows.append({
            "user_id": str(user_id),
            "source_type": "manual",
            "source_id": None,
            "content_chunk": chunk_text,
            "topic_tags": payload.topic_tags or [],
            "title": chunk_title,
            "embedding": embedding,
        })

    try:
        result = await client.from_("knowledge_nodes").insert(rows).execute()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    if not result.data:
        raise HTTPException(status_code=400, detail="Insert returned no row")

    return KnowledgeNodeResponse(**result.data[0])


@router.delete("/knowledge/{node_id}", status_code=204)
async def delete_knowledge(
    node_id: str, ctx: tuple = Depends(current_user)
) -> None:
    """Soft-delete a knowledge node. RLS ensures only the owner can delete."""
    _user_id, token = ctx
    client = await user_client(token)

    now = datetime.now(timezone.utc).isoformat()
    try:
        result = (
            await client.from_("knowledge_nodes")
            .update({"deleted_at": now})
            .eq("id", node_id)
            .is_("deleted_at", "null")
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    if not result.data:
        raise HTTPException(status_code=404, detail="Knowledge node not found")


@router.get("/knowledge/accumulated", response_model=AccumulatedFeedResponse)
async def accumulated_feed(
    ctx: tuple = Depends(current_user),
    limit: int = Query(default=50, ge=1, le=200),
) -> AccumulatedFeedResponse:
    """Auto-accumulated knowledge: scripts, ideas, extracted content, transcripts."""
    _user_id, token = ctx
    client = await user_client(token)

    try:
        result = (
            await client.from_("knowledge_nodes")
            .select("*, ideas(title), studio_sessions!inner(id)")
            .is_("deleted_at", "null")
            .in_("source_type", ["idea", "script", "yt_transcript", "skill_file", "extract"])
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception:
        # If the joined query fails (missing foreign keys), fall back to a
        # plain select. The accumulated feed is non-critical UX.
        try:
            result = (
                await client.from_("knowledge_nodes")
                .select("*")
                .is_("deleted_at", "null")
                .in_("source_type", ["idea", "script", "yt_transcript", "skill_file", "extract"])
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    entries: list[AccumulatedEntry] = []
    for row in result.data or []:
        title = row.get("title")
        summary = row.get("content_chunk", "")[:200] if row.get("content_chunk") else None
        source_title = title
        if not source_title:
            ideas = row.get("ideas")
            if isinstance(ideas, dict):
                source_title = ideas.get("title")
            elif isinstance(ideas, list) and ideas:
                source_title = ideas[0].get("title") if isinstance(ideas[0], dict) else None

        entries.append(
            AccumulatedEntry(
                id=row["id"],
                source_type=row.get("source_type", "unknown"),
                source_title=source_title,
                summary=summary,
                created_at=row.get("created_at"),
                session_id=row.get("source_id"),
            )
        )

    return AccumulatedFeedResponse(entries=entries)


@router.get("/knowledge/topics", response_model=TopicTerritoryResponse)
async def topic_territory(
    ctx: tuple = Depends(current_user),
) -> TopicTerritoryResponse:
    """Tag-frequency analysis: covered (3+), thin (1-2), open gaps (unused)."""
    _user_id, token = ctx
    client = await user_client(token)

    try:
        nodes = (
            await client.from_("knowledge_nodes")
            .select("topic_tags")
            .is_("deleted_at", "null")
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    counts: dict[str, int] = {}
    for row in nodes.data or []:
        for tag in row.get("topic_tags") or []:
            tag = tag.strip().lower()
            if tag:
                counts[tag] = counts.get(tag, 0) + 1

    covered: list[TagCount] = []
    thin: list[TagCount] = []
    for tag, count in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        if count >= 3:
            covered.append(TagCount(tag=tag, count=count))
        else:
            thin.append(TagCount(tag=tag, count=count))

    # Open gaps: tags that exist in the tags table but have zero knowledge_nodes.
    try:
        all_tags = await client.from_("tags").select("name").execute()
    except Exception:
        all_tags = type("", (), {"data": []})()

    tag_names = {t["name"].strip().lower() for t in (all_tags.data or []) if t.get("name")}
    open_gaps = sorted(tag_names - set(counts.keys()))

    return TopicTerritoryResponse(covered=covered, thin=thin, open_gaps=open_gaps)


# ─── Sources ────────────────────────────────────────────────────────────────


@router.get("/sources", response_model=SourcesListResponse)
async def list_sources(
    ctx: tuple = Depends(current_user),
) -> SourcesListResponse:
    """List the caller's connected sources."""
    _user_id, token = ctx
    client = await user_client(token)

    try:
        result = (
            await client.from_("sources")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    sources: list[SourceResponse] = []
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for row in result.data or []:
        # Count ideas extracted this month for this source
        ideas_count = 0
        try:
            ideas = (
                await client.from_("ideas")
                .select("id", count="exact")
                .eq("source_id", row["id"])
                .gte("created_at", month_start.isoformat())
                .execute()
            )
            ideas_count = getattr(ideas, "count", 0) or 0
        except Exception:
            pass

        sources.append(
            SourceResponse(
                id=row["id"],
                name=row.get("name", ""),
                source_type=row.get("source_type"),
                sender_email=row.get("sender_email"),
                auto_extract=row.get("auto_extract", True),
                status=row.get("status", "active"),
                last_received_at=row.get("last_received_at"),
                created_at=row.get("created_at"),
                ideas_extracted_this_month=ideas_count,
            )
        )

    return SourcesListResponse(sources=sources)


def _derive_alias(email: str | None, user_id: str) -> str:
    """Derive a forwarding alias from email or user_id."""
    if email and "@" in email:
        local = email.split("@")[0].lower()
        local = "".join(c for c in local if c.isalnum() or c in "._-")
        if local:
            return f"{local}@ladder.so"
    short_id = user_id.replace("-", "")[:8]
    return f"founder-{short_id}@ladder.so"


@router.post("/sources", response_model=SourceResponse, status_code=201)
async def create_source(
    payload: SourceCreate, ctx: tuple = Depends(current_user)
) -> SourceResponse:
    """Add a new content source. Provisions forwarding alias on first source."""
    user_id, token = ctx
    client = await user_client(token)

    row = {
        "user_id": str(user_id),
        **payload.model_dump(exclude_none=True),
    }
    try:
        result = await client.from_("sources").insert(row).execute()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    if not result.data:
        raise HTTPException(status_code=400, detail="Insert returned no row")

    # Provision forwarding alias on first newsletter-source addition.
    try:
        profile = await client.from_("user_profiles").select("forwarding_alias").eq("user_id", str(user_id)).maybe_single().execute()
    except Exception:
        profile = None

    alias = None
    if profile and profile.data and not profile.data.get("forwarding_alias"):
        claims = jwt.get_unverified_claims(token)
        email = claims.get("email")
        alias = _derive_alias(email, str(user_id))
        try:
            await client.from_("user_profiles").update({"forwarding_alias": alias}).eq("user_id", str(user_id)).execute()
        except Exception:
            pass  # Non-critical — alias card will show next profile refresh

    return SourceResponse(
        id=result.data[0]["id"],
        name=result.data[0].get("name", ""),
        source_type=result.data[0].get("source_type"),
        sender_email=result.data[0].get("sender_email"),
        auto_extract=result.data[0].get("auto_extract", True),
        status=result.data[0].get("status", "active"),
        last_received_at=result.data[0].get("last_received_at"),
        created_at=result.data[0].get("created_at"),
        ideas_extracted_this_month=0,
    )


@router.patch("/sources/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: str, payload: SourceUpdate, ctx: tuple = Depends(current_user)
) -> SourceResponse:
    """Toggle source active/paused. RLS enforces ownership."""
    _user_id, token = ctx
    client = await user_client(token)

    patch = payload.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        result = (
            await client.from_("sources")
            .update(patch)
            .eq("id", source_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    if not result.data:
        raise HTTPException(status_code=404, detail="Source not found")

    return SourceResponse(
        id=result.data[0]["id"],
        name=result.data[0].get("name", ""),
        source_type=result.data[0].get("source_type"),
        sender_email=result.data[0].get("sender_email"),
        auto_extract=result.data[0].get("auto_extract", True),
        status=result.data[0].get("status", "active"),
        last_received_at=result.data[0].get("last_received_at"),
        created_at=result.data[0].get("created_at"),
        ideas_extracted_this_month=0,
    )


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: str, ctx: tuple = Depends(current_user)
) -> None:
    """Delete a source (cascades to newsletter_items)."""
    _user_id, token = ctx
    client = await user_client(token)

    try:
        await client.from_("sources").delete().eq("id", source_id).execute()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e


@router.get("/sources/{source_id}/items", response_model=SourceItemsResponse)
async def source_items(
    source_id: str, ctx: tuple = Depends(current_user)
) -> SourceItemsResponse:
    """Last 5 newsletter items for a source, plus monthly extracted idea count."""
    _user_id, token = ctx
    client = await user_client(token)

    try:
        result = (
            await client.from_("newsletter_items")
            .select("*")
            .eq("source_id", source_id)
            .order("received_at", desc=True)
            .limit(5)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    items = [
        NewsletterItemResponse(
            id=row["id"],
            received_at=row.get("received_at"),
            subject=row.get("subject"),
            summary=row.get("summary"),
            processed_at=row.get("processed_at"),
        )
        for row in (result.data or [])
    ]

    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ideas_count = 0
    try:
        ideas = (
            await client.from_("ideas")
            .select("id", count="exact")
            .eq("source_id", source_id)
            .gte("created_at", month_start.isoformat())
            .execute()
        )
        ideas_count = getattr(ideas, "count", 0) or 0
    except Exception:
        pass

    return SourceItemsResponse(items=items, ideas_extracted_this_month=ideas_count)


# ─── Insights ───────────────────────────────────────────────────────────────


@router.get("/insights", response_model=InsightsListResponse)
async def list_insights(
    ctx: tuple = Depends(current_user),
    limit: int = Query(default=50, ge=1, le=200),
) -> InsightsListResponse:
    """Curated signals from the last 7 days."""
    _user_id, token = ctx
    client = await user_client(token)

    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    try:
        result = (
            await client.from_("insights")
            .select("*")
            .gte("created_at", since)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    return InsightsListResponse(insights=result.data or [])


@router.patch("/insights/{insight_id}/read", status_code=204)
async def mark_insight_read(
    insight_id: str, ctx: tuple = Depends(current_user)
) -> None:
    """Mark an insight as read."""
    _user_id, token = ctx
    client = await user_client(token)

    try:
        result = (
            await client.from_("insights")
            .update({"read": True})
            .eq("id", insight_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Supabase error: {e}") from e

    if not result.data:
        raise HTTPException(status_code=404, detail="Insight not found")


class GenerateInsightsResponse(BaseModel):
    insights: list[InsightResponse]
    generated: int


@router.post("/insights/generate", response_model=GenerateInsightsResponse)
async def generate_insights(
    ctx: tuple = Depends(current_user),
) -> GenerateInsightsResponse:
    """Synthesize insights from the user's profile, recent ideas, and tags.

    Uses the Anthropic client to produce 2-4 curated research signals relevant
    to the user's positioning. Idempotent — skips generation if insights were
    generated in the last 24 hours.
    """
    user_id, token = ctx
    client = await user_client(token)

    # ── Guard: skip if insights were generated in the last 24 hours ──
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    try:
        recent = (
            await client.from_("insights")
            .select("id", count="exact")
            .gte("created_at", since)
            .execute()
        )
        if getattr(recent, "count", 0) and (recent.count or 0) > 0:
            return GenerateInsightsResponse(insights=[], generated=0)
    except Exception:
        pass

    # ── Gather context ──
    try:
        profile_result = (
            await client.from_("user_profiles")
            .select("positioning, audience, voice")
            .eq("user_id", str(user_id))
            .maybe_single()
            .execute()
        )
        profile = profile_result.data if profile_result else None
    except Exception:
        profile = None

    positioning = (profile or {}).get("positioning", "") or ""
    audience = (profile or {}).get("audience", "") or ""

    # Recent ideas (last 30 days)
    idea_titles: list[str] = []
    idea_tags: set[str] = set()
    try:
        ideas_result = (
            await client.from_("ideas")
            .select("title, idea_type")
            .gte("created_at", (datetime.now(timezone.utc) - timedelta(days=30)).isoformat())
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        for row in ideas_result.data or []:
            idea_titles.append(row.get("title", ""))
    except Exception:
        pass

    # Tags from knowledge_nodes
    try:
        kn = (
            await client.from_("knowledge_nodes")
            .select("topic_tags")
            .is_("deleted_at", "null")
            .limit(50)
            .execute()
        )
        for row in kn.data or []:
            for tag in row.get("topic_tags") or []:
                if tag.strip():
                    idea_tags.add(tag.strip().lower())
    except Exception:
        pass

    # ── Build prompt ──
    context_parts: list[str] = []
    if positioning:
        context_parts.append(f"The user's positioning: {positioning}")
    if audience:
        context_parts.append(f"Their target audience: {audience}")
    if idea_titles:
        context_parts.append(
            "Recent video ideas: " + "; ".join(idea_titles[:10])
        )
    if idea_tags:
        context_parts.append(
            "Recurring topic tags: " + ", ".join(sorted(idea_tags)[:15])
        )

    context_block = "\n".join(context_parts) if context_parts else (
        "A new user with no profile or ideas yet."
    )

    system = (
        "You are a research signal analyst for a video content platform. "
        "Based on the user's profile, recent ideas, and topic tags, identify "
        "2-4 synthesized insights that represent emerging trends, content gaps, "
        "or audience signals relevant to their positioning.\n\n"
        "Each insight should be SPECIFIC — reference real patterns, not generic "
        "advice. Format your output as a JSON array of objects with keys: "
        "title (a provocative headline string, max 120 chars), "
        "body (1-2 sentences explaining the signal, max 400 chars), "
        "signal_type (one of: trend_shift, positioning_gap, audience_signal), "
        "source_ref (optional string — a specific source or reference if applicable).\n\n"
        "Output ONLY the JSON array, no other text."
    )

    from app.services.llm import anthropic_client

    llm = anthropic_client()
    try:
        resp = await llm.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=system,
            messages=[
                {"role": "user", "content": context_block},
            ],
        )
        raw = (resp.content[0].text if resp.content else "").strip()
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"LLM call failed: {e}"
        ) from e

    # ── Parse the JSON response ──
    import json as _json

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[:-3]
    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError:
        raise HTTPException(
            status_code=502, detail="LLM returned unparseable output"
        )

    if not isinstance(parsed, list):
        raise HTTPException(
            status_code=502, detail="LLM output was not a list"
        )

    # ── Insert insights ──
    inserted: list[InsightResponse] = []
    for item in parsed[:4]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or "").strip()
        if not title:
            continue
        try:
            result = (
                await client.from_("insights")
                .insert({
                    "user_id": str(user_id),
                    "title": title[:200],
                    "body": str(item.get("body", "") or "")[:600],
                    "signal_type": str(item.get("signal_type", "") or "")[:40],
                    "source_ref": str(item.get("source_ref", "") or "")[:300],
                })
                .execute()
            )
            if result.data:
                row = result.data[0]
                inserted.append(InsightResponse(
                    id=row["id"],
                    title=row.get("title", ""),
                    body=row.get("body"),
                    signal_type=row.get("signal_type"),
                    source_ref=row.get("source_ref"),
                    read=False,
                    created_at=row.get("created_at"),
                ))
        except Exception:
            continue

    return GenerateInsightsResponse(insights=inserted, generated=len(inserted))
