"""LinkedIn profile ingestion and knowledge-graph seeding.

Supports three ingestion paths:
  1. URL scrape via ScrapeCreators (public profiles)
  2. JSON export import (official LinkedIn data export)
  3. Manual text paste (fallback for private profiles)

All paths format data into readable text, chunk + embed it, and store it
in knowledge_nodes with ``source_type = "linkedin"`` so the existing
knowledge-graph retrieval picks it up automatically.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from app.deps import service_client, user_client
from app.providers import scrapecreators
from app.services.embeddings import chunk_and_embed
from app.services.linkedin_parser import parse_linkedin_json

log = logging.getLogger(__name__)


async def scrape_and_seed(user_id: UUID, linkedin_url: str, token: str) -> dict:
    """Scrape *linkedin_url* via ScrapeCreators, then chunk+embed into knowledge_nodes.

    Returns ``{"ok": True, "chunks_created": N}`` on success, or
    ``{"ok": False, "error": "..."}`` on failure.
    """
    if not linkedin_url.strip():
        return {"ok": False, "error": "LinkedIn URL is empty"}

    log.info("Scraping LinkedIn profile for user %s: %s", user_id, linkedin_url)

    profile = await scrapecreators.linkedin_profile(linkedin_url)
    if profile is None:
        return {"ok": False, "error": "Could not fetch LinkedIn profile. The page may be private or blocked."}

    text = _format_profile(profile)
    if not text.strip():
        return {"ok": False, "error": "LinkedIn profile returned no usable content."}

    pairs = await chunk_and_embed(text)
    if not pairs:
        return {"ok": False, "error": "Could not generate embeddings. Check that OPENAI_API_KEY is configured."}

    service = await service_client()
    now = datetime.now(timezone.utc).isoformat()
    title = f"LinkedIn Profile — {profile.name or 'Unknown'}"

    rows = [
        {
            "user_id": str(user_id),
            "source_type": "linkedin",
            "source_id": None,
            "content_chunk": chunk,
            "embedding": embedding,
            "title": title,
            "created_at": now,
        }
        for chunk, embedding in pairs
    ]

    try:
        await service.from_("knowledge_nodes").insert(rows).execute()
    except Exception:
        log.exception("Failed to insert LinkedIn knowledge nodes for user %s", user_id)
        return {"ok": False, "error": "Database insert failed"}

    user = await user_client(token)
    try:
        await (
            user.from_("user_profiles")
            .update({"linkedin_imported_at": now})
            .eq("user_id", str(user_id))
            .execute()
        )
    except Exception:
        log.exception("Failed to update linkedin_imported_at for user %s", user_id)

    log.info("LinkedIn profile seeded into knowledge graph for user %s: %d chunks", user_id, len(rows))
    return {"ok": True, "chunks_created": len(rows)}


async def seed_from_text(user_id: UUID, text: str, token: str) -> dict:
    """Chunk + embed raw text and store as linkedin knowledge nodes.

    Used as a fallback when the LinkedIn profile is private and the user
    manually pastes their profile content.
    """
    if not text.strip():
        return {"ok": False, "error": "Text is empty"}

    pairs = await chunk_and_embed(text)
    if not pairs:
        return {"ok": False, "error": "Could not generate embeddings. Check that OPENAI_API_KEY is configured."}

    service = await service_client()
    now = datetime.now(timezone.utc).isoformat()

    rows = [
        {
            "user_id": str(user_id),
            "source_type": "linkedin",
            "source_id": None,
            "content_chunk": chunk,
            "embedding": embedding,
            "title": "LinkedIn Profile (manual)",
            "created_at": now,
        }
        for chunk, embedding in pairs
    ]

    try:
        await service.from_("knowledge_nodes").insert(rows).execute()
    except Exception:
        log.exception("Failed to insert manual LinkedIn knowledge nodes for user %s", user_id)
        return {"ok": False, "error": "Database insert failed"}

    user = await user_client(token)
    try:
        await (
            user.from_("user_profiles")
            .update({"linkedin_imported_at": now})
            .eq("user_id", str(user_id))
            .execute()
        )
    except Exception:
        log.exception("Failed to update linkedin_imported_at for user %s", user_id)

    log.info("Manual LinkedIn text seeded into knowledge graph for user %s: %d chunks", user_id, len(rows))
    return {"ok": True, "chunks_created": len(rows)}


def _format_profile(p: scrapecreators.LinkedInProfile) -> str:
    """Render a LinkedInProfile into a dense, readable text block for embedding."""
    parts: list[str] = []

    parts.append(f"LinkedIn Profile: {p.name or 'Unknown'}")
    if p.location:
        parts.append(f"Location: {p.location}")
    if p.followers:
        parts.append(f"Followers: {p.followers:,}")

    if p.about:
        parts.append(f"\nAbout:\n{p.about}")

    if p.experience:
        parts.append("\nExperience:")
        for exp in p.experience:
            name = exp.get("name") or exp.get("title") or "Unknown Company"
            loc = exp.get("location", "")
            loc_str = f" ({loc})" if loc else ""
            role = ""
            member = exp.get("member") or {}
            if isinstance(member, dict):
                role = member.get("description") or member.get("title") or ""
            role_str = f" — {role}" if role and "***" not in role else ""
            parts.append(f"- {name}{loc_str}{role_str}")

    if p.education:
        parts.append("\nEducation:")
        for edu in p.education:
            name = edu.get("name") or "Unknown School"
            member = edu.get("member") or {}
            start = ""
            end = ""
            if isinstance(member, dict):
                start = str(member.get("startDate") or "")
                end = str(member.get("endDate") or "")
            years = ""
            if start:
                years = f" ({start} — {end})" if end else f" ({start})"
            parts.append(f"- {name}{years}")

    if p.articles:
        parts.append("\nArticles:")
        for art in p.articles:
            headline = art.get("headline") or "Untitled"
            body = (art.get("articleBody") or "")[:300]
            parts.append(f"- {headline}")
            if body:
                parts.append(f"  {body}")

    if p.publications:
        parts.append("\nPublications:")
        for pub in p.publications:
            name = pub.get("name") or "Untitled"
            url = pub.get("url", "")
            url_str = f" ({url})" if url else ""
            parts.append(f"- {name}{url_str}")

    if p.projects:
        parts.append("\nProjects:")
        for proj in p.projects:
            name = proj.get("name") or "Untitled"
            desc = (proj.get("description") or "")[:200]
            parts.append(f"- {name}")
            if desc:
                parts.append(f"  {desc}")

    if p.recommendations:
        parts.append("\nRecommendations:")
        for rec in p.recommendations:
            rec_name = rec.get("name") or "Unknown"
            text = (rec.get("text") or "")[:200]
            parts.append(f"- {rec_name}: {text}")

    return "\n".join(parts)


async def import_from_json_export(user_id: UUID, json_data: dict, token: str) -> dict:
    """Import a LinkedIn data export JSON and seed into knowledge_nodes.

    Parses the LinkedIn export JSON, formats it into text, deletes any
    existing linkedin-sourced knowledge nodes for this user, then chunks
    and embeds the new data.

    Returns ``{"ok": True, "chunks_created": N}`` on success, or
    ``{"ok": False, "error": "..."}`` on failure.
    """
    if not json_data:
        return {"ok": False, "error": "JSON data is empty"}

    text = parse_linkedin_json(json_data)
    if not text.strip():
        return {"ok": False, "error": "Could not extract profile data from the uploaded JSON. Check that it is a LinkedIn data export."}

    pairs = await chunk_and_embed(text)
    if not pairs:
        return {"ok": False, "error": "Could not generate embeddings. Check that OPENAI_API_KEY is configured."}

    service = await service_client()
    now = datetime.now(timezone.utc).isoformat()
    title = f"LinkedIn Profile — {json_data.get('firstName', json_data.get('name', 'Unknown'))}"

    # Delete old linkedin nodes for this user before inserting new ones
    try:
        await (
            service.from_("knowledge_nodes")
            .delete()
            .eq("user_id", str(user_id))
            .eq("source_type", "linkedin")
            .execute()
        )
    except Exception:
        log.exception("Failed to delete old LinkedIn knowledge nodes for user %s", user_id)

    rows = [
        {
            "user_id": str(user_id),
            "source_type": "linkedin",
            "source_id": None,
            "content_chunk": chunk,
            "embedding": embedding,
            "title": title,
            "created_at": now,
        }
        for chunk, embedding in pairs
    ]

    try:
        await service.from_("knowledge_nodes").insert(rows).execute()
    except Exception:
        log.exception("Failed to insert LinkedIn knowledge nodes for user %s", user_id)
        return {"ok": False, "error": "Database insert failed"}

    user = await user_client(token)
    try:
        await (
            user.from_("user_profiles")
            .update({"linkedin_imported_at": now})
            .eq("user_id", str(user_id))
            .execute()
        )
    except Exception:
        log.exception("Failed to update linkedin_imported_at for user %s", user_id)

    log.info("LinkedIn JSON import seeded into knowledge graph for user %s: %d chunks", user_id, len(rows))
    return {"ok": True, "chunks_created": len(rows)}
