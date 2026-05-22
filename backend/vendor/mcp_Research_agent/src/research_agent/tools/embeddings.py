"""Embeddings tool — text-embedding-3-small ($0.02/1M tokens, basically free)."""

from __future__ import annotations

import logging
from typing import Sequence

import numpy as np
from tenacity import retry, stop_after_attempt, wait_exponential

from research_agent.config import settings

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def embed_texts(texts: Sequence[str], model: str | None = None) -> np.ndarray:
    """Embed a batch of texts with OpenAI's text-embedding-3-small. 
    Returns (N, dim) numpy array."""
    from openai import AsyncOpenAI

    if not texts:
        return np.array([])

    model = model or settings.embedding_model
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # OpenAI batch limit is 2048 texts per call
    all_embeddings = []
    batch_size = 512
    for i in range(0, len(texts), batch_size):
        batch = list(texts[i:i + batch_size])
        # Truncate long texts to avoid token limit
        batch = [t[:8000] if len(t) > 8000 else t for t in batch]
        resp = await client.embeddings.create(input=batch, model=model)
        all_embeddings.extend([e.embedding for e in resp.data])

    result = np.array(all_embeddings, dtype=np.float32)
    logger.info(f"Embedded {len(texts)} texts → {result.shape}")
    return result


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Compute pairwise cosine similarity between two embedding matrices."""
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-8)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-8)
    return a_norm @ b_norm.T


async def top_k_by_relevance(
    texts: list[str],
    query: str,
    k: int = 20,
) -> list[tuple[int, float]]:
    """Return indices and scores of top-k most relevant texts to the query.
    Used as embedding pre-filter before LLM synthesis calls (5–10× cost reduction)."""
    if not texts:
        return []

    all_texts = [query] + texts
    embeddings = await embed_texts(all_texts)
    query_emb = embeddings[0:1]
    text_embs = embeddings[1:]

    similarities = cosine_similarity(query_emb, text_embs)[0]
    top_indices = np.argsort(similarities)[::-1][:k]

    return [(int(idx), float(similarities[idx])) for idx in top_indices]
