"""Knowledge graph retrieval for the Research crew.

Pre-fetches the founder's own accumulated knowledge (past scripts, ideas,
manual notes, extracted content) so the scorer and formulator can cross-
reference external signals against what the founder already knows.

Single public function:

    retrieve_knowledge_context(user_id, topic) -> str | None
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.deps import service_client
from app.services.embeddings import generate_embedding

log = logging.getLogger(__name__)

_MATCH_COUNT = 12
_MIN_SIMILARITY = 0.5


async def retrieve_knowledge_context(
    user_id: UUID,
    topic: str,
) -> tuple[str | None, int]:
    """Retrieve the user's own knowledge relevant to *topic*.

    Returns ``(context_block, count)`` where *context_block* is a formatted
    string listing related knowledge chunks (source types, content excerpts,
    similarity scores), and *count* is the number of chunks retrieved.
    Returns ``(None, 0)`` when no embedding can be generated or the graph is
    empty.
    """
    embedding = await generate_embedding(topic)
    if embedding is None:
        log.info("Skipping knowledge retrieval — no embedding generated for topic %r", topic)
        return None, 0

    client = await service_client()
    try:
        # NOTE: query_text is omitted until the hybrid-search branch of the
        # RPC is fixed to cast similarity to float (migration 20260506000001).
        # The pure-vector branch returns double precision correctly.
        result = await client.rpc(
            "match_knowledge_nodes",
            {
                "query_user_id": str(user_id),
                "query_embedding": embedding,
                "match_count": _MATCH_COUNT,
            },
        ).execute()
    except Exception:
        log.exception("match_knowledge_nodes RPC failed for user %s", user_id)
        return None, 0

    rows = result.data or []
    rows = [
        r for r in rows
        if isinstance(r.get("similarity"), (int, float))
        and r["similarity"] >= _MIN_SIMILARITY
    ]
    if not rows:
        return None, 0

    chunks: list[str] = [
        "── Founder's existing knowledge (from their knowledge graph) ──"
    ]
    for i, row in enumerate(rows, 1):
        source_type = row.get("source_type") or "unknown"
        content = (row.get("content_chunk") or "")[:400]
        sim = row.get("similarity")
        sim_str = f" · {sim:.0%} match" if isinstance(sim, (int, float)) else ""
        origin = _source_label(source_type)
        chunks.append(
            f"{i}. [{origin}]{sim_str}\n"
            f"   \"{content}\""
        )
    return "\n\n".join(chunks), len(rows)


def _source_label(source_type: str) -> str:
    """Short human-readable label for a knowledge_node source_type."""
    labels: dict[str, str] = {
        "manual": "note",
        "idea": "idea",
        "script": "script",
        "outline": "outline",
        "yt_transcript": "transcript",
        "skill_file": "file",
        "extract": "extract",
    }
    return labels.get(source_type, source_type)
