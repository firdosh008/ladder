"""Outlier scoring — Layer 4 TrendScore formula with 7-weight cross-platform corroboration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from research_agent.models import SourceRef, SupplySideReport

logger = logging.getLogger(__name__)


@dataclass
class ScoringWeights:
    """Tunable weights for the TrendScore formula.
    Hand-tune against 30 real test topics — don't ship defaults blindly."""
    w1_velocity: float = 0.20       # demand growth
    w2_engagement: float = 0.15     # engagement quality
    w3_platforms: float = 0.25      # cross-platform corroboration (most important)
    w4_kg_alignment: float = 0.15   # creator fit
    w5_supply_gap: float = 0.15     # unmet demand
    w6_saturation: float = -0.10    # already covered (penalty)
    w7_size_mismatch: float = -0.05 # blue-ocean filter (penalty)


# Default weights — to be re-tuned after Layer 1 rebuild
DEFAULT_WEIGHTS = ScoringWeights()


@dataclass
class TopicScore:
    """Scored topic with breakdown."""
    topic: str
    total_score: float = 0.0
    velocity: float = 0.0
    engagement_quality: float = 0.0
    platform_count: int = 0
    kg_alignment: float = 0.0
    supply_gap: float = 0.0
    saturation: float = 0.0
    size_mismatch: float = 0.0
    platforms: list[str] = field(default_factory=list)
    passed: bool = False  # True if ≥2 platforms with signal


def score_topic(
    topic: str,
    sources: list[SourceRef],
    kg_gap: float = 0.5,
    kg_saturation: float = 0.0,
    supply_report: SupplySideReport | None = None,
    weights: ScoringWeights | None = None,
) -> TopicScore:
    """Compute TrendScore for a topic from all gathered signals.

    TrendScore(topic) = 
        w₁ · velocity / baseline
      + w₂ · engagement_quality
      + w₃ · platform_count
      + w₄ · KG_alignment
      + w₅ · supply_gap_size
      - w₆ · saturation
      - w₇ · creator_size_mismatch
    """
    w = weights or DEFAULT_WEIGHTS

    # Filter sources relevant to this topic (by source_agent or content match)
    relevant = sources  # In production, filter by topic relevance

    # Platform corroboration
    relevance_scores = [s.relevance_score or 0.0 for s in relevant]
    platforms = list(set(s.platform for s in relevant if (s.relevance_score or 0.0) > 0.3))
    platform_count = len(platforms)
    platform_signal = min(1.0, platform_count / 4)  # Normalize to 0–1

    # Engagement quality (average across sources)
    if relevant:
        avg_relevance = sum(relevance_scores) / len(relevance_scores)
    else:
        avg_relevance = 0.0

    # Velocity proxy (recent vs older sources)
    recent = [s for s in relevant if s.freshness_days <= 7]
    velocity = min(1.0, len(recent) / max(len(relevant), 1))

    # Supply gap
    supply_gap = 0.5
    if supply_report:
        supply_gap = 1.0 - supply_report.overall_saturation
        if supply_report.gaps:
            supply_gap = max(supply_gap, max(g.confidence for g in supply_report.gaps))

    size_mismatch = 0.0
    if supply_report and supply_report.top_content:
        dominant_creators = [
            item for item in supply_report.top_content
            if item.channel_subscribers >= 50_000 and item.views >= 5_000
        ]
        if len(dominant_creators) >= 5:
            size_mismatch = min(1.0, len(dominant_creators) / max(len(supply_report.top_content), 1))

    # Compute score
    total = (
        w.w1_velocity * velocity
        + w.w2_engagement * avg_relevance
        + w.w3_platforms * platform_signal
        + w.w4_kg_alignment * kg_gap
        + w.w5_supply_gap * supply_gap
        + w.w6_saturation * kg_saturation  # negative weight
        + w.w7_size_mismatch * size_mismatch  # negative weight
    )

    passed = platform_count >= 2  # HARD RULE: ≥2 platforms required

    result = TopicScore(
        topic=topic,
        total_score=round(total, 4),
        velocity=velocity,
        engagement_quality=avg_relevance,
        platform_count=platform_count,
        kg_alignment=kg_gap,
        supply_gap=supply_gap,
        saturation=kg_saturation,
        size_mismatch=size_mismatch,
        platforms=platforms,
        passed=passed,
    )

    logger.info(f"Topic '{topic}' scored {result.total_score:.3f} (passed={passed}, platforms={platforms})")
    return result
