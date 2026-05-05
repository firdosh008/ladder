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
from pydantic import BaseModel, Field

from app.deps import user_client
from app.middleware.auth import current_user
from app.services.embeddings import generate_embedding

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
    """Create a manual knowledge node. Generates embedding via OpenAI."""
    user_id, token = ctx
    client = await user_client(token)

    embedding = await generate_embedding(payload.content_chunk)

    row = {
        "user_id": str(user_id),
        "source_type": "manual",
        "content_chunk": payload.content_chunk,
        "topic_tags": payload.topic_tags or [],
        "title": payload.title,
        "embedding": embedding,
    }
    # Remove None embedding so pgvector doesn't reject null
    if embedding is None:
        del row["embedding"]

    try:
        result = await client.from_("knowledge_nodes").insert(row).execute()
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


@router.post("/sources", response_model=SourceResponse, status_code=201)
async def create_source(
    payload: SourceCreate, ctx: tuple = Depends(current_user)
) -> SourceResponse:
    """Add a new content source."""
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
