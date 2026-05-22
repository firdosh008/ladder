"""Comment mining — fetches, embeds, clusters, and matches unmet-ask templates.
This is the single biggest signal-quality improvement in the rebuild."""

from __future__ import annotations

import logging
import re
from html import unescape

import numpy as np

from research_agent.config import settings
from research_agent.models import CommentCluster, CostBreakdown
from research_agent.tools.embeddings import embed_texts
from research_agent.tools.llm import llm_call

logger = logging.getLogger(__name__)

# Templates for matching unmet asks (used by Haiku for cheap classification)
UNMET_ASK_TEMPLATES = [
    "I wish you covered {topic}",
    "I came here looking for {topic} but didn't find it",
    "Still don't understand {topic}",
    "The part about {topic} is wrong or outdated",
    "Would love a deeper dive into {topic}",
    "Why didn't you mention {topic}",
    "This is great but missing {topic}",
]


def _clean_comment(text: str) -> str:
    """Strip HTML tags and clean up comment text."""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def mine_comments(
    comments: list[dict],
    query: str,
    cost_tracker: CostBreakdown | None = None,
) -> list[CommentCluster]:
    """Full comment mining pipeline:
    1. Clean and filter comments
    2. Embed with text-embedding-3-small
    3. Cluster (k-means)
    4. Match clusters against unmet-ask templates (Haiku)
    
    Returns CommentCluster objects for synthesis layer.
    """
    if not comments:
        return []

    # Step 1: Clean
    cleaned = []
    for c in comments:
        body = _clean_comment(c.get("body", ""))
        if len(body) > 30:  # Skip very short comments
            cleaned.append({**c, "body": body})

    if len(cleaned) < 5:
        logger.info("Too few comments for meaningful clustering")
        return []

    # Step 2: Embed
    texts = [c["body"] for c in cleaned]
    try:
        embeddings = await embed_texts(texts)
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return []

    if embeddings.size == 0:
        return []

    # Step 3: Cluster (simple k-means)
    k = min(settings.comment_cluster_k, len(cleaned) // 3, 8)
    k = max(k, 2)

    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import normalize

        normed = normalize(embeddings)
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(normed)
        centroids = kmeans.cluster_centers_
    except Exception as e:
        logger.error(f"Clustering failed: {e}")
        return []

    # Step 4: Build cluster summaries
    clusters_raw: dict[int, list[dict]] = {}
    for i, label in enumerate(labels):
        clusters_raw.setdefault(int(label), []).append(cleaned[i])

    # Sort clusters by size (descending)
    sorted_clusters = sorted(clusters_raw.items(), key=lambda x: len(x[1]), reverse=True)

    # Step 5: Classify each cluster via Haiku (cheap)
    result_clusters = []
    for cluster_id, cluster_comments in sorted_clusters[:6]:  # Top 6 clusters
        # Pick top 5 representative comments by engagement
        reps = sorted(cluster_comments, key=lambda c: c.get("score", 0), reverse=True)[:5]
        rep_texts = [c["body"][:300] for c in reps]

        # Use Haiku to classify the cluster theme and detect unmet asks
        classify_prompt = f"""Analyze these comments from a discussion about "{query}".

Comments:
{chr(10).join(f'- {t}' for t in rep_texts)}

Respond in exactly this format:
THEME: [one sentence describing the common theme]
UNMET_ASK: [YES or NO — is this cluster expressing a desire for content/information that doesn't exist?]
SENTIMENT: [positive/negative/neutral/frustrated]"""

        try:
            response = await llm_call(
                prompt=classify_prompt,
                model=settings.summarization_model,
                temperature=0.2,
                max_tokens=200,
                cost_tracker=cost_tracker,
                cost_layer="comment_mining",
            )

            # Parse response
            theme = ""
            unmet = False
            sentiment = 0.0

            for line in response.strip().split("\n"):
                line = line.strip()
                if line.startswith("THEME:"):
                    theme = line[6:].strip()
                elif line.startswith("UNMET_ASK:"):
                    unmet = "YES" in line.upper()
                elif line.startswith("SENTIMENT:"):
                    sent_text = line[10:].strip().lower()
                    sentiment = {"positive": 0.7, "neutral": 0.5, "negative": 0.3, "frustrated": 0.2}.get(sent_text, 0.5)

            if theme:
                platform = cluster_comments[0].get("platform", "unknown") if cluster_comments else "unknown"
                result_clusters.append(CommentCluster(
                    theme=theme,
                    representative_comments=[c["body"][:200] for c in reps[:3]],
                    frequency=len(cluster_comments),
                    sentiment=sentiment,
                    unmet_ask=unmet,
                    source_platform=platform,
                ))

        except Exception as e:
            logger.error(f"Cluster classification failed: {e}")
            continue

    # Sort: unmet asks first, then by frequency
    result_clusters.sort(key=lambda c: (c.unmet_ask, c.frequency), reverse=True)
    logger.info(f"Comment mining produced {len(result_clusters)} clusters ({sum(1 for c in result_clusters if c.unmet_ask)} unmet asks)")
    return result_clusters
