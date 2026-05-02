"""CrewAI tools wrapping our own backend (non-MCP).

The MCP tools (``create_element``, ``batch_create_elements``, …) come from
``mcp_excalidraw_tools()`` in ``mcp.py``. This module hosts the four tools
that talk to **our** stack:

  • ``ScriptOutlineTool``     — returns the current script + outline as JSON
  • ``BrandPaletteTool``      — returns brand color tokens for this session
  • ``KnowledgeRetrievalTool``— ``match_knowledge_nodes`` RPC against the
                                founder's pgvector knowledge graph
  • ``PersistArtifactTool``   — write a versioned ``excalidraw`` artifact

Each tool is constructor-injected with the per-request state it needs
(``jwt``, ``user_id``, ``session_id``, ``brand_id``). State stays as Pydantic
fields on the tool instance — that mirrors the research vertical's stateless
pattern but lets us bind RLS-scoped credentials per WS connection.

PR1 (current): tools land here, fully shape-correct. ``KnowledgeRetrievalTool``
gracefully degrades when the embedding pipeline (§6 P1 #9) hasn't shipped.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from app.agents.visual.context import BrandSlice
from app.config import settings
from app.deps import service_client, user_client

log = logging.getLogger(__name__)


def _truncate(blob: str, limit: int = 24_000) -> str:
    """Bound JSON returned to the LLM so a giant artifact can't blow context."""
    if len(blob) <= limit:
        return blob
    return blob[: limit - 12] + "…[truncated]"


# ─── ScriptOutlineTool ────────────────────────────────────────────────────


class _ScriptOutlineInput(BaseModel):
    """No args — the tool snapshots whatever the session currently holds."""

    model_config = ConfigDict(extra="forbid")


class ScriptOutlineTool(BaseTool):
    """Hand the agent the current script + outline JSON on demand.

    Useful when the agent has been chatting for a while and wants to re-read
    the source of truth, or when the user just edited the outline in the
    left pane and the agent needs to pick up the change.
    """

    name: str = "get_script_and_outline"
    description: str = (
        "Return the current script and scene outline for this studio session "
        "as JSON. No arguments — call when you need to refresh your memory of "
        "the source material before drawing or refining."
    )
    args_schema: type[BaseModel] = _ScriptOutlineInput

    jwt: str = Field(repr=False)
    session_id: str

    def _run(self) -> str:
        return asyncio.run(self._fetch())

    async def _fetch(self) -> str:
        client = await user_client(self.jwt)
        resp = (
            await client.from_("artifacts")
            .select("type, version, content_json")
            .eq("session_id", self.session_id)
            .in_("type", ["script", "outline"])
            .order("version", desc=True)
            .execute()
        )
        rows = resp.data or []
        # Keep highest-version row per type only.
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            t = row.get("type")
            if t and t not in latest:
                latest[t] = row.get("content_json") or {}
        return _truncate(
            json.dumps(
                {
                    "script": latest.get("script"),
                    "outline": latest.get("outline"),
                },
                ensure_ascii=False,
            )
        )


# ─── BrandPaletteTool ─────────────────────────────────────────────────────


class _BrandPaletteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BrandPaletteTool(BaseTool):
    """Hand the agent the brand color tokens for this session.

    The agent should weave brand primary color into hero shapes / accent
    rules. If the session has no brand assigned, returns ``{"brand": null}``
    and the agent should default to neutral plus one accent of its choice.
    """

    name: str = "get_brand_palette"
    description: str = (
        "Return the brand color tokens for this session: "
        "{name, primary_color, secondary_color}. No arguments. If no brand is "
        "set, returns {brand: null} — fall back to neutral + one accent."
    )
    args_schema: type[BaseModel] = _BrandPaletteInput

    brand: BrandSlice | None = None

    def _run(self) -> str:
        if self.brand is None:
            return json.dumps({"brand": None})
        return json.dumps({"brand": self.brand.model_dump()})


# ─── KnowledgeRetrievalTool ───────────────────────────────────────────────


class _KnowledgeRetrievalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(
        description=(
            "Natural-language query — what context from the founder's prior "
            "videos / newsletters / research would help the current task."
        )
    )
    k: int = Field(default=6, ge=1, le=20)


class KnowledgeRetrievalTool(BaseTool):
    """pgvector retrieval against the founder's knowledge graph.

    Calls the ``match_knowledge_nodes`` RPC with an explicit ``user_id`` —
    per HANDOFF.md §3 #6 we filter by user before similarity, even under the
    service-role client, as defence in depth.

    PR1 status: this tool ships shape-correct but the embedding pipeline
    that *fills* ``knowledge_nodes`` is §6 P1 #9 (not yet built). Until that
    lands the tool returns an empty result set — the agent should treat
    "no relevant past content" as a normal answer, not an error.
    """

    name: str = "search_founder_knowledge"
    description: str = (
        "Search the founder's prior content (past videos, newsletter items, "
        "research artefacts) for context relevant to the current task. "
        "Returns up to k semantically similar items: "
        "[{title, kind, summary, score}]. Use sparingly — only when prior "
        "framings or evidence would meaningfully improve the current output."
    )
    args_schema: type[BaseModel] = _KnowledgeRetrievalInput

    user_id: str

    def _run(self, query: str, k: int = 6) -> str:
        return asyncio.run(self._fetch(query, k))

    async def _fetch(self, query: str, k: int) -> str:
        if not settings.OPENAI_API_KEY:
            log.info(
                "knowledge_retrieval skipped — OPENAI_API_KEY not set "
                "(embedding pipeline pending)."
            )
            return json.dumps({"items": [], "note": "embedding pipeline not yet enabled"})

        try:
            embedding = await self._embed(query)
        except Exception as e:
            log.warning("knowledge_retrieval embed failed: %s", e)
            return json.dumps({"items": [], "error": "embed_failed"})

        try:
            sb = await service_client()
            resp = await sb.rpc(
                "match_knowledge_nodes",
                {
                    "query_user_id": self.user_id,
                    "query_embedding": embedding,
                    "match_count": k,
                },
            ).execute()
        except Exception as e:
            log.warning("match_knowledge_nodes RPC failed: %s", e)
            return json.dumps({"items": [], "error": "rpc_failed"})

        items = []
        for row in (resp.data or [])[:k]:
            items.append(
                {
                    "title": row.get("title"),
                    "kind": row.get("kind"),
                    "summary": (row.get("summary") or "")[:480],
                    "score": row.get("similarity"),
                }
            )
        return _truncate(json.dumps({"items": items}))

    async def _embed(self, text: str) -> list[float]:
        # Lazy import — the OpenAI SDK is currently unused outside this path.
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return list(resp.data[0].embedding)


# ─── PersistArtifactTool ──────────────────────────────────────────────────


class _PersistArtifactInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene: dict[str, Any] = Field(
        description=(
            "Full Excalidraw scene JSON — what `export_scene` (MCP) returned "
            "or an equivalent envelope with elements + appState + files. "
            "This becomes the new versioned artifact."
        ),
    )
    note: str | None = Field(
        default=None,
        description="Optional human-readable note saved as content_text.",
    )


class PersistArtifactTool(BaseTool):
    """Snapshot the current canvas as a versioned ``excalidraw`` artifact.

    The agent calls this when it considers the diagram "done" or when the
    user asks to save. Versioning is automatic — each call writes the next
    integer version. The returned ``artifact_id`` lets the agent reference
    the snapshot in a follow-up message.

    Heads-up: this writes through the user-scoped client so RLS still
    enforces ownership. Under no circumstances drop to service-role here.
    """

    name: str = "persist_scene_artifact"
    description: str = (
        "Save the current canvas state as a versioned excalidraw artifact "
        "for this studio session. Pass the full scene JSON and an optional "
        "note. Returns {artifact_id, version}."
    )
    args_schema: type[BaseModel] = _PersistArtifactInput

    user_id: str
    jwt: str = Field(repr=False)
    session_id: str

    def _run(self, scene: dict[str, Any], note: str | None = None) -> str:
        return asyncio.run(self._persist(scene, note))

    async def _persist(
        self, scene: dict[str, Any], note: str | None
    ) -> str:
        client = await user_client(self.jwt)

        version_resp = (
            await client.from_("artifacts")
            .select("version")
            .eq("session_id", self.session_id)
            .eq("type", "excalidraw")
            .order("version", desc=True)
            .limit(1)
            .execute()
        )
        next_version = (
            int(version_resp.data[0]["version"]) + 1 if version_resp.data else 1
        )

        el_count = len(scene.get("elements") or [])
        summary = note or f"Visual agent diagram — {el_count} elements."

        inserted = (
            await client.from_("artifacts")
            .insert(
                {
                    "user_id": self.user_id,
                    "session_id": self.session_id,
                    "type": "excalidraw",
                    "version": next_version,
                    "content_text": summary[:4000],
                    "content_json": scene,
                }
            )
            .execute()
        )
        if not inserted.data:
            return json.dumps({"ok": False, "error": "insert returned no row"})
        return json.dumps(
            {
                "ok": True,
                "artifact_id": str(inserted.data[0]["id"]),
                "version": next_version,
            }
        )


__all__ = [
    "ScriptOutlineTool",
    "BrandPaletteTool",
    "KnowledgeRetrievalTool",
    "PersistArtifactTool",
]
