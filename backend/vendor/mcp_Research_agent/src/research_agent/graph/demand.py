"""Layer 1: Demand-side signal agents — parallel pull from web, Reddit, YouTube, HN, PAA."""

from __future__ import annotations

import asyncio
import logging
import re
import time

import httpx
from tenacity import RetryError

from research_agent.graph import ResearchState
from research_agent.models import AgentEvent, CostBreakdown, SourceRef
from research_agent.tools.web_search import web_search
from research_agent.tools.reddit import search_reddit, fetch_reddit_comments
from research_agent.tools.youtube import search_youtube, fetch_youtube_comments
from research_agent.tools.hackernews import search_hackernews, fetch_hn_comments
from research_agent.tools.paa import search_paa, search_autocomplete
from research_agent.tools.supadata import search_supadata_transcripts

logger = logging.getLogger(__name__)


async def demand_side_node(state: ResearchState) -> dict:
    """Layer 1: Fire all demand-side agents in parallel.
    Each agent returns SourceRef objects + raw comments for mining."""

    query = _normalize_query(state["query"])
    cost = state.get("cost", CostBreakdown())
    config = state.get("config")
    skip_platforms = set(config.skip_platforms if config else [])
    events = []

    layer_started = time.perf_counter()
    events.append(AgentEvent(event="layer_start", layer="demand_side", message="Starting demand-side signal collection").to_dict())

    # Run all agents in parallel
    async def run_web():
        if "web" in skip_platforms:
            return [], []
        events.append(AgentEvent(event="agent_start", layer="demand_side", agent="WebSearch", message="Searching Tavily + Exa").to_dict())
        try:
            results = await web_search(query, max_results=10)
            events.append(AgentEvent(event="agent_complete", layer="demand_side", agent="WebSearch", message=f"Found {len(results)} web sources").to_dict())
            return results, []
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            events.append(AgentEvent(event="agent_error", layer="demand_side", agent="WebSearch", message=str(e)).to_dict())
            return [], []

    async def run_reddit():
        if "reddit" in skip_platforms:
            return [], []
        events.append(AgentEvent(event="agent_start", layer="demand_side", agent="Reddit", message="Searching Reddit posts + comments").to_dict())
        try:
            reddit_batches = await asyncio.gather(
                search_reddit(query, max_results=8, sort="top", cost_tracker=cost),
                search_reddit(query, max_results=8, sort="controversial", cost_tracker=cost),
                search_reddit(query, max_results=8, sort="new", max_age_days=7, cost_tracker=cost),
                return_exceptions=True,
            )
            posts = []
            fallback_posts = []
            seen_urls = set()
            for batch in reddit_batches:
                if isinstance(batch, Exception):
                    logger.warning(f"Reddit search batch failed: {batch}")
                    continue
                for post in batch:
                    if post.url in seen_urls:
                        continue
                    seen_urls.add(post.url)
                    if _is_relevant_source(post, query):
                        posts.append(post)
                    else:
                        fallback_posts.append(post)
            if not posts:
                posts = fallback_posts[:5]
            posts = sorted(posts, key=lambda p: p.relevance_score or 0.0, reverse=True)[:10]
            # Mine comments from top posts
            comments = []
            for post in posts[:5]:  # Top 5 posts
                permalink = post.url.replace("https://reddit.com", "")
                if permalink:
                    try:
                        post_comments = await fetch_reddit_comments(permalink, limit=50)
                        comments.extend(post_comments)
                    except Exception:
                        pass
            events.append(AgentEvent(event="agent_complete", layer="demand_side", agent="Reddit", message=f"Found {len(posts)} posts, {len(comments)} comments").to_dict())
            return posts, comments
        except Exception as e:
            logger.error(f"Reddit search failed: {e}")
            events.append(AgentEvent(event="agent_error", layer="demand_side", agent="Reddit", message=str(e)).to_dict())
            return [], []

    async def run_youtube():
        if "youtube" in skip_platforms:
            return [], []
        events.append(AgentEvent(event="agent_start", layer="demand_side", agent="YouTube", message="Searching YouTube videos + comments").to_dict())
        try:
            videos = await search_youtube(query, max_results=10)
            comments = []
            for vid in videos[:5]:
                video_id = _extract_video_id(vid.url)
                if video_id:
                    try:
                        vid_comments = await fetch_youtube_comments(video_id, limit=50, cost_tracker=cost)
                        comments.extend(vid_comments)
                    except Exception:
                        pass
            events.append(AgentEvent(event="agent_complete", layer="demand_side", agent="YouTube", message=f"Found {len(videos)} videos, {len(comments)} comments").to_dict())
            return videos, comments
        except Exception as e:
            logger.error(f"YouTube search failed: {e}")
            events.append(AgentEvent(event="agent_error", layer="demand_side", agent="YouTube", message=str(e)).to_dict())
            return [], []

    async def run_hn():
        if "hackernews" in skip_platforms or "hn" in skip_platforms:
            return [], []
        events.append(AgentEvent(event="agent_start", layer="demand_side", agent="HackerNews", message="Searching Hacker News (Algolia)").to_dict())
        try:
            stories = await search_hackernews(query, max_results=10)
            comments = []
            for story in stories[:3]:
                story_id = str(story.engagement.get("object_id") or "")
                if not story_id and "id=" in story.url:
                    story_id = story.url.split("id=")[-1]
                if story_id:
                    try:
                        hn_comments = await fetch_hn_comments(story_id, limit=50)
                        comments.extend(hn_comments)
                    except Exception:
                        pass
            events.append(AgentEvent(event="agent_complete", layer="demand_side", agent="HackerNews", message=f"Found {len(stories)} stories, {len(comments)} comments").to_dict())
            return stories, comments
        except Exception as e:
            logger.error(f"HN search failed: {e}")
            events.append(AgentEvent(event="agent_error", layer="demand_side", agent="HackerNews", message=str(e)).to_dict())
            return [], []

    async def run_paa():
        if "paa" in skip_platforms:
            return [], []
        events.append(AgentEvent(event="agent_start", layer="demand_side", agent="PAA", message="Fetching People Also Ask + autocomplete").to_dict())
        try:
            paa_results = await search_paa(query, max_results=10, cost_tracker=cost)
            autocomplete = await search_autocomplete(query, max_results=10)
            autocomplete_sources = [
                SourceRef(
                    title=suggestion,
                    url=f"https://www.google.com/search?q={suggestion.replace(' ', '+')}",
                    snippet=suggestion,
                    platform="paa",
                    engagement={"type": "autocomplete"},
                    relevance_score=0.6,
                    source_agent="PAAAgent",
                )
                for suggestion in autocomplete
            ]
            events.append(AgentEvent(event="agent_complete", layer="demand_side", agent="PAA", message=f"Found {len(paa_results)} PAA questions, {len(autocomplete)} autocomplete").to_dict())
            return paa_results + autocomplete_sources, []
        except Exception as e:
            message = _friendly_tool_error(e)
            logger.error(f"PAA search failed: {message}")
            events.append(AgentEvent(event="agent_error", layer="demand_side", agent="PAA", message=message).to_dict())
            return [], []

    async def run_supadata():
        if "supadata" in skip_platforms:
            return [], []
        events.append(AgentEvent(event="agent_start", layer="demand_side", agent="Supadata", message="Fetching video transcripts").to_dict())
        try:
            sources, transcript_chunks = await search_supadata_transcripts(query, max_results=5, cost_tracker=cost)
            events.append(AgentEvent(
                event="agent_complete",
                layer="demand_side",
                agent="Supadata",
                message=f"Found {len(sources)} transcripts, {len(transcript_chunks)} chunks",
            ).to_dict())
            return sources, transcript_chunks
        except Exception as e:
            message = _friendly_tool_error(e)
            logger.error(f"Supadata search failed: {message}")
            events.append(AgentEvent(event="agent_error", layer="demand_side", agent="Supadata", message=message).to_dict())
            return [], []

    # Fire all in parallel
    results = await asyncio.gather(
        run_web(), run_reddit(), run_youtube(), run_hn(), run_paa(), run_supadata(),
        return_exceptions=True,
    )

    all_sources = []
    all_comments = []
    for r in results:
        if isinstance(r, tuple):
            sources, comments = r
            all_sources.extend(sources)
            all_comments.extend(comments)
        elif isinstance(r, Exception):
            logger.error(f"Agent failed: {r}")

    layer_complete = AgentEvent(
        event="layer_complete", layer="demand_side",
        message=f"Collected {len(all_sources)} sources, {len(all_comments)} comments from {len(set(s.platform for s in all_sources))} platforms",
    ).to_dict()
    layer_complete["duration_seconds"] = round(time.perf_counter() - layer_started, 2)
    events.append(layer_complete)

    return {
        "sources": all_sources,
        "comments_raw": all_comments,
        "events": events,
        "cost": cost,
    }


def _extract_video_id(url: str) -> str:
    """Extract YouTube video ID from URL."""
    match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else ""


def _normalize_query(query: str) -> str:
    normalized = re.sub(r"\bv\s*/\s*s\b|\bversus\b", " vs ", query, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _is_relevant_source(source: SourceRef, query: str) -> bool:
    terms = _important_terms(query)
    if not terms:
        return True
    text = f"{source.title} {source.snippet}".lower()
    matches = sum(1 for term in terms if term in text)
    if matches >= min(2, len(terms)):
        return True
    return bool({"ai", "robot", "robotic", "robotics", "automation"} & terms) and matches >= 1


def _important_terms(query: str) -> set[str]:
    normalized = re.sub(r"[^a-zA-Z0-9\s-]", " ", query.lower())
    stopwords = {
        "the", "and", "for", "with", "from", "into", "that", "this", "human", "humans",
        "versus", "against", "will", "are", "can", "how", "why",
    }
    synonyms = {
        "ai": {"ai", "artificial", "intelligence"},
        "robotic": {"robotic", "robotics", "robot"},
        "robotics": {"robotic", "robotics", "robot"},
        "saas": {"saas", "software"},
    }
    terms = {part for part in normalized.split() if len(part) > 2 and part not in stopwords and part != "vs"}
    expanded = set(terms)
    for term in terms:
        expanded.update(synonyms.get(term, set()))
    return expanded


def _friendly_tool_error(error: Exception) -> str:
    """Unwrap retry/http errors so UI events show actionable messages."""
    if isinstance(error, RetryError):
        error = error.last_attempt.exception()
    if isinstance(error, httpx.HTTPStatusError):
        body = error.response.text[:240].replace("\n", " ")
        return f"HTTP {error.response.status_code}: {body}"
    if isinstance(error, httpx.ConnectError):
        return "Connection failed. Check network/DNS/firewall access to the provider API."
    return str(error)
