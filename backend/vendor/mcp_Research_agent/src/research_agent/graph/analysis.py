"""Layers 2–4: Supply-side analysis, KG filtering, and Outlier scoring."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from statistics import mean

from research_agent.graph import ResearchState
from research_agent.models import (
    AgentEvent, ContentItem, CostBreakdown, SupplySideReport, Gap, CommentCluster,
)
from research_agent.comment_mining import mine_comments
from research_agent.tools.youtube import extract_youtube_video_id, fetch_youtube_comments, get_top_videos_for_supply
from research_agent.tools.llm import llm_call
from research_agent.scoring import score_topic
from research_agent.config import settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Comment Mining Node (between Layer 1 and 2)
# ──────────────────────────────────────────────

async def comment_mining_node(state: ResearchState) -> dict:
    """Process raw comments into clusters with unmet-ask detection."""
    events = [AgentEvent(event="layer_start", layer="comment_mining", message="Mining audience comments for unmet asks").to_dict()]
    cost = state.get("cost", CostBreakdown())
    comments_raw = state.get("comments_raw", [])

    clusters = []
    if comments_raw:
        events.append(AgentEvent(event="agent_start", layer="comment_mining", agent="Clusterer", message=f"Processing {len(comments_raw)} comments").to_dict())
        clusters = await mine_comments(comments_raw, state["query"], cost_tracker=cost)
        events.append(AgentEvent(event="agent_complete", layer="comment_mining", agent="Clusterer",
                                 message=f"Found {len(clusters)} clusters, {sum(1 for c in clusters if c.unmet_ask)} unmet asks").to_dict())

    events.append(AgentEvent(event="layer_complete", layer="comment_mining", message="Comment mining complete").to_dict())
    return {"comment_clusters": clusters, "events": events, "cost": cost}


# ──────────────────────────────────────────────
# Layer 2: Supply-Side Analysis
# ──────────────────────────────────────────────

async def supply_side_node(state: ResearchState) -> dict:
    """Layer 2: Analyze what already exists — top content, engagement ratios, gaps."""
    events = [AgentEvent(event="layer_start", layer="supply_side", message="Analyzing existing content supply").to_dict()]
    cost = state.get("cost", CostBreakdown())
    query = state["query"]
    config = state.get("config")
    skip_platforms = set(config.skip_platforms if config else [])

    if "supply_side" in skip_platforms or "youtube" in skip_platforms:
        events.append(AgentEvent(event="agent_complete", layer="supply_side", agent="TopContent", message="Skipped by config").to_dict())
        events.append(AgentEvent(event="layer_complete", layer="supply_side", message="Supply-side analysis skipped").to_dict())
        return {
            "supply_report": SupplySideReport(),
            "events": events,
            "cost": cost,
        }

    # Pull top videos
    events.append(AgentEvent(event="agent_start", layer="supply_side", agent="TopContent", message="Pulling top 10 videos").to_dict())
    try:
        top_content = await get_top_videos_for_supply(query, max_results=10)
    except Exception as e:
        logger.error(f"Supply-side video pull failed: {e}")
        top_content = []
    events.append(AgentEvent(event="agent_complete", layer="supply_side", agent="TopContent", message=f"Found {len(top_content)} existing videos").to_dict())

    events.append(AgentEvent(event="agent_start", layer="supply_side", agent="CommentSentiment", message="Checking top-video comment sentiment").to_dict())
    comments_by_url = {}
    for item in top_content[:5]:
        video_id = extract_youtube_video_id(item.url)
        if not video_id:
            continue
        try:
            comments = await fetch_youtube_comments(video_id, limit=25, cost_tracker=cost)
        except Exception as e:
            logger.warning(f"Supply-side comments failed for {item.url}: {e}")
            comments = []
        comments_by_url[item.url] = comments
        item.sentiment_score = await _classify_supply_comment_sentiment(comments, query, cost)
    events.append(AgentEvent(event="agent_complete", layer="supply_side", agent="CommentSentiment",
                             message=f"Analyzed comments for {len(comments_by_url)} videos").to_dict())

    # Analyze gaps using LLM
    events.append(AgentEvent(event="agent_start", layer="supply_side", agent="GapDetection", message="Detecting content gaps").to_dict())
    gaps = _detect_supply_gaps(query, top_content, comments_by_url)
    overall_saturation = _estimate_supply_saturation(top_content, gaps)

    if top_content:
        content_summary = "\n".join(
            f"- {c.title} ({c.views:,} views, {c.likes:,} likes, engagement: {c.engagement_ratio:.4f}, "
            f"sentiment: {c.sentiment_score:.2f}, duration: {c.duration_seconds}s, published: {c.published_date})"
            for c in top_content[:10]
        )

        gap_prompt = f"""Analyze the existing content supply for the topic: "{query}"

Top existing content:
{content_summary}

Identify gaps in the following categories. For each gap found, rate confidence 0-1:
1. RECENCY gap: Are top videos older than 18 months on a fast-moving topic?
2. FORMAT gap: Is there a missing format (e.g., all long-form but audience wants shorts)?
3. DEPTH gap: Are there sophisticated questions but only shallow coverage?
4. SENTIMENT gap: High views but disappointed comments?

Also rate overall saturation (0-1, where 1 = fully saturated, no opportunity).

Respond in this exact format (one per line):
RECENCY: [confidence 0-1] | [description]
FORMAT: [confidence 0-1] | [description]
DEPTH: [confidence 0-1] | [description]
SENTIMENT: [confidence 0-1] | [description]
SATURATION: [0-1]"""

        try:
            response = await llm_call(
                prompt=gap_prompt,
                model=settings.summarization_model,
                temperature=0.3,
                max_tokens=500,
                cost_tracker=cost,
                cost_layer="supply_side",
            )

            for line in response.strip().split("\n"):
                line = line.strip()
                if line.startswith("SATURATION:"):
                    try:
                        overall_saturation = float(line.split(":")[1].strip())
                    except ValueError:
                        pass
                elif "|" in line:
                    parts = line.split("|")
                    gap_type_raw = parts[0].split(":")[0].strip().lower()
                    confidence_str = parts[0].split(":")[-1].strip()
                    description = parts[1].strip() if len(parts) > 1 else ""

                    gap_type_map = {"recency": "recency", "format": "format", "depth": "depth", "sentiment": "sentiment"}
                    gap_type = gap_type_map.get(gap_type_raw)

                    if gap_type:
                        try:
                            confidence = float(confidence_str)
                        except ValueError:
                            confidence = 0.5
                        if confidence > 0.3 and not any(g.gap_type == gap_type for g in gaps):
                            gaps.append(Gap(
                                gap_type=gap_type,
                                confidence=confidence,
                                evidence_urls=[c.url for c in top_content[:3]],
                                description=description,
                            ))
        except Exception as e:
            logger.error(f"Gap analysis failed: {e}")

    events.append(AgentEvent(event="agent_complete", layer="supply_side", agent="GapDetection",
                             message=f"Found {len(gaps)} gaps, saturation: {overall_saturation:.1f}").to_dict())

    supply_report = SupplySideReport(
        top_content=top_content,
        gaps=gaps,
        overall_saturation=overall_saturation,
    )

    events.append(AgentEvent(event="layer_complete", layer="supply_side", message="Supply-side analysis complete").to_dict())
    return {"supply_report": supply_report, "events": events, "cost": cost}


async def _classify_supply_comment_sentiment(
    comments: list[dict],
    query: str,
    cost: CostBreakdown,
) -> float:
    """Return 0-1 sentiment score for comments, where lower means disappointed/frustrated."""
    if not comments:
        return 0.5

    representative = sorted(comments, key=lambda c: c.get("score", 0), reverse=True)[:8]
    prompt = f"""Classify audience sentiment in these YouTube comments about "{query}".

Return only a number from 0 to 1:
- 0.0 = strongly disappointed, confused, or negative
- 0.5 = mixed or neutral
- 1.0 = strongly satisfied and positive

Comments:
{chr(10).join(f'- {c.get("body", "")[:300]}' for c in representative)}"""

    try:
        response = await llm_call(
            prompt=prompt,
            model=settings.summarization_model,
            temperature=0.1,
            max_tokens=20,
            cost_tracker=cost,
            cost_layer="supply_side",
        )
        return max(0.0, min(1.0, float(response.strip().split()[0])))
    except Exception as e:
        logger.warning(f"Supply sentiment classification failed: {e}")
        return 0.5


def _detect_supply_gaps(
    query: str,
    top_content: list[ContentItem],
    comments_by_url: dict[str, list[dict]],
) -> list[Gap]:
    """Detect deterministic supply-side gaps before LLM refinement."""
    gaps: list[Gap] = []
    if not top_content:
        return gaps

    evidence_urls = [c.url for c in top_content[:3]]
    ages = [_age_days(c.published_date) for c in top_content if _age_days(c.published_date) is not None]
    fast_moving = _is_fast_moving_topic(query)
    if fast_moving and ages:
        old_ratio = sum(1 for age in ages if age > 548) / len(ages)
        if old_ratio >= 0.5:
            gaps.append(Gap(
                gap_type="recency",
                confidence=round(min(0.95, 0.55 + old_ratio * 0.4), 2),
                evidence_urls=evidence_urls,
                description="Most top videos are older than 18 months on a fast-moving topic.",
            ))

    durations = [c.duration_seconds for c in top_content if c.duration_seconds > 0]
    if durations:
        long_ratio = sum(1 for duration in durations if duration >= 900) / len(durations)
        if long_ratio >= 0.7:
            gaps.append(Gap(
                gap_type="format",
                confidence=round(min(0.9, 0.45 + long_ratio * 0.45), 2),
                evidence_urls=evidence_urls,
                description="Top results skew heavily long-form, leaving room for a tighter short-form or modular version.",
            ))

    all_comments = [comment for comments in comments_by_url.values() for comment in comments]
    if all_comments:
        word_counts = [len(comment.get("body", "").split()) for comment in all_comments if comment.get("body")]
        avg_words = mean(word_counts) if word_counts else 0
        short_ratio = sum(1 for duration in durations if duration and duration <= 480) / len(durations) if durations else 0
        if avg_words >= 28 and short_ratio >= 0.2:
            gaps.append(Gap(
                gap_type="depth",
                confidence=round(min(0.9, 0.4 + min(avg_words / 80, 0.5) + short_ratio * 0.2), 2),
                evidence_urls=evidence_urls,
                description="Audience comments are relatively complex while much of the available content is short or shallow.",
            ))

    sentiment_scores = [c.sentiment_score for c in top_content[:5] if c.sentiment_score > 0]
    if sentiment_scores and mean(sentiment_scores) < 0.4:
        gaps.append(Gap(
            gap_type="sentiment",
            confidence=round(1 - mean(sentiment_scores), 2),
            evidence_urls=evidence_urls,
            description="Top content has weak audience sentiment, suggesting disappointed or under-served demand.",
        ))

    return gaps


def _estimate_supply_saturation(top_content: list[ContentItem], gaps: list[Gap]) -> float:
    """Estimate saturation from content volume, engagement, and detected gaps."""
    if not top_content:
        return 0.2

    volume_score = min(1.0, len(top_content) / 10)
    engagement_score = min(1.0, mean(c.engagement_ratio for c in top_content) / 0.05)
    gap_penalty = min(0.7, sum(g.confidence for g in gaps) / 4)
    return round(max(0.0, min(1.0, (volume_score * 0.55 + engagement_score * 0.45) - gap_penalty)), 2)


def _age_days(published_date: str) -> int | None:
    if not published_date:
        return None
    try:
        published = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - published).days


def _is_fast_moving_topic(query: str) -> bool:
    fast_terms = {
        "ai", "agent", "agents", "llm", "gpt", "claude", "gemini", "rag",
        "startup", "saas", "crypto", "fintech", "marketing", "automation",
    }
    normalized = {part.strip(".,!?;:()[]{}").lower() for part in query.split()}
    return bool(normalized & fast_terms)


# ──────────────────────────────────────────────
# Layer 3: Caller Context Filter
# ──────────────────────────────────────────────

async def kg_filter_node(state: ResearchState) -> dict:
    """Layer 3: Filter signals through caller-provided project context."""
    events = [AgentEvent(event="layer_start", layer="kg_filter", message="Filtering through caller context").to_dict()]

    user_id = state.get("user_id", "default")
    query = state["query"]

    # Use SimpleKG for standalone runs; projects can inject their own implementation.
    kg = state["knowledge_graph"]

    events.append(AgentEvent(event="agent_start", layer="kg_filter", agent="GapScore", message="Computing context gap score").to_dict())
    user_context = await kg.get_user_context(user_id)
    gap = await kg.gap_score(query, user_id)
    saturation = await kg.saturation_score(query, user_id)
    events.append(AgentEvent(event="agent_complete", layer="kg_filter", agent="GapScore",
                             message=f"Gap: {gap:.2f}, Saturation: {saturation:.2f}").to_dict())

    events.append(AgentEvent(event="layer_complete", layer="kg_filter", message="Context filtering complete").to_dict())
    return {
        "user_context": user_context,
        "kg_gap": gap,
        "kg_saturation": saturation,
        "events": events,
    }


# ──────────────────────────────────────────────
# Layer 4: Outlier Scoring
# ──────────────────────────────────────────────

async def scoring_node(state: ResearchState) -> dict:
    """Layer 4: Score the topic with cross-platform corroboration."""
    events = [AgentEvent(event="layer_start", layer="scoring", message="Computing TrendScore").to_dict()]

    events.append(AgentEvent(event="agent_start", layer="scoring", agent="TrendScore", message="Running 7-weight formula").to_dict())
    result = score_topic(
        topic=state["query"],
        sources=state.get("sources", []),
        kg_gap=state.get("kg_gap", 0.5),
        kg_saturation=state.get("kg_saturation", 0.0),
        supply_report=state.get("supply_report"),
    )
    score_breakdown = {
        "total_score": result.total_score,
        "velocity": result.velocity,
        "engagement_quality": result.engagement_quality,
        "platform_count": result.platform_count,
        "kg_alignment": result.kg_alignment,
        "supply_gap": result.supply_gap,
        "saturation": result.saturation,
        "size_mismatch": result.size_mismatch,
        "platforms": result.platforms,
        "passed": result.passed,
    }
    rejection_reason = ""
    if not result.passed:
        rejection_reason = (
            f"Topic did not pass cross-platform corroboration: "
            f"{result.platform_count} platform(s) found, 2 required."
        )
    events.append(AgentEvent(event="agent_complete", layer="scoring", agent="TrendScore",
                             message=f"Score: {result.total_score:.3f}, Platforms: {result.platforms}, Passed: {result.passed}").to_dict())

    events.append(AgentEvent(event="layer_complete", layer="scoring",
                             message=f"Topic {'PASSED' if result.passed else 'FAILED'} with score {result.total_score:.3f}").to_dict())
    return {
        "topic_score": result.total_score,
        "topic_passed": result.passed,
        "score_breakdown": score_breakdown,
        "rejection_reason": rejection_reason,
        "events": events,
    }
