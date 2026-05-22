"""Shared embedding helper — OpenAI text-embedding-3-small (1536d) with semantic chunking."""

from __future__ import annotations

import logging
import re

from app.config import settings

log = logging.getLogger(__name__)

# ~500 tokens ≈ 2000 chars; 10% overlap preserves narrative continuity across chunks.
_CHUNK_SIZE = 2000
_CHUNK_OVERLAP = 200


def _split_sentences(text: str) -> list[str]:
    """Split text on sentence boundaries (.!? followed by whitespace)."""
    raw = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in raw if s.strip()]


def semantic_chunk(
    text: str,
    chunk_size: int = _CHUNK_SIZE,
    overlap: int = _CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks at sentence boundaries.

    Never splits mid-sentence unless a single sentence exceeds *chunk_size*,
    in which case it falls back to fixed-width windows with the configured
    overlap.  A 10 % overlap ensures that the boundary between consecutive
    chunks does not lose context hooks needed for accurate retrieval.
    """
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    sentences = _split_sentences(text)
    if not sentences:
        return [text]

    chunks: list[str] = []
    current: list[str] = []  # accumulate sentences, join once full
    current_len = 0

    for sent in sentences:
        sent_len = len(sent)

        if current_len + sent_len + (1 if current else 0) <= chunk_size:
            current.append(sent)
            current_len += sent_len + (1 if len(current) > 1 else 0)
        else:
            if current:
                chunks.append(" ".join(current))

            if sent_len > chunk_size:
                # Single sentence longer than chunk_size — hard split with overlap.
                start = 0
                while start < len(sent):
                    segment = sent[start : start + chunk_size]
                    chunks.append(segment.strip())
                    if start + chunk_size >= len(sent):
                        break
                    start += chunk_size - overlap
                current = []
                current_len = 0
            else:
                # Carry overlap from the previous chunk's tail into the new chunk.
                if chunks and overlap > 0:
                    prev = chunks[-1]
                    tail = prev[-overlap:] if len(prev) > overlap else prev
                    current = [tail, sent]
                    current_len = len(tail) + 1 + sent_len
                else:
                    current = [sent]
                    current_len = sent_len

    if current:
        chunks.append(" ".join(current))

    return chunks


async def generate_embedding(text: str) -> list[float] | None:
    """Return a 1536-d embedding vector, or None if no OpenAI key is configured.

    Kept for backward-compatibility with callers that need a single embedding.
    For multi-chunk ingestion, prefer :func:`chunk_and_embed`.
    """
    if not settings.OPENAI_API_KEY:
        log.warning("OPENAI_API_KEY not configured — skipping embedding generation")
        return None

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        resp = await client.embeddings.create(
            input=text[:8000],
            model="text-embedding-3-small",
        )
        return resp.data[0].embedding
    except Exception:
        log.exception("Embedding generation failed")
        return None


async def chunk_and_embed(
    text: str,
    chunk_size: int = _CHUNK_SIZE,
    overlap: int = _CHUNK_OVERLAP,
) -> list[tuple[str, list[float]]]:
    """Chunk *text* semantically and return ``(chunk_text, embedding)`` pairs.

    Returns an empty list when no OpenAI key is configured or the input is
    empty, so callers can safely iterate over the result without extra guards.
    """
    if not text or not text.strip():
        return []

    chunks = semantic_chunk(text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        return []

    if not settings.OPENAI_API_KEY:
        log.warning("OPENAI_API_KEY not configured — skipping chunk embedding")
        return []

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        resp = await client.embeddings.create(
            input=chunks,
            model="text-embedding-3-small",
        )
        return [
            (chunk, data.embedding)
            for chunk, data in zip(chunks, resp.data)
        ]
    except Exception:
        log.exception("Batch embedding generation failed")
        return []
