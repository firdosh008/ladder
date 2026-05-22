"""Adapter layer: transforms standalone MCP ResearchResult into Ladder IdeaDraft[].

Uses Anthropic's structured outputs to generate 4-6 video ideas based on the
MCP's winning thesis, supply gaps, and founder's knowledge graph.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from anthropic import APIStatusError

from app.config import settings
from app.models.db import ResearchIdeas, UserProfileSlice
from app.services.llm import ANTHROPIC_STRUCTURED_OUTPUTS_BETA, anthropic_client

log = logging.getLogger(__name__)

# Same schema as ResearchIdeas Pydantic model
_IDEAS_SCHEMA = {
    "type": "object",
    "properties": {
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 500},
                    "rationale": {"type": ["string", "null"]},
                    "idea_type": {
                        "type": ["string", "null"],
                        "enum": ["systems", "framework", "pitch", "case_study", "null"],
                    },
                    "opportunity_score": {"type": ["integer", "null"], "minimum": 0, "maximum": 100},
                    "outlier_score": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
                    "why_now": {"type": ["string", "null"], "maxLength": 280},
                    "suggested_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["title", "rationale", "idea_type", "opportunity_score", "why_now"],
                "additionalProperties": False,
            },
            "minItems": 1,
            "maxItems": 8,
        },
    },
    "required": ["ideas"],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = """\
You are an elite video producer generating compelling YouTube ideas for a specific creator.
You have been given a comprehensive research report (including a winning thesis, supply gaps, and unmet audience asks) from a powerful research agent.

Your job is to translate this research into 4 to 6 distinct video ideas (IdeaDrafts) tailored to the creator's profile.

EACH IDEA MUST:
1. Attack the thesis from a different angle (e.g. one systems-focused, one case_study, etc.).
2. Exploit the identified "supply gaps" (what other videos are missing).
3. Directly answer the "unmet asks" (what the audience is begging for in comments).
4. Feel native to the creator's voice and positioning.

Keep 'target_duration_min' in mind: a 5-minute video idea needs a sharp, narrow focus. A 30-minute idea needs a comprehensive, deep-dive structure.
"""

def _duration_brief(target: int) -> str:
    if target <= 5:
        return "Scope for a short, punchy 5-minute video. Needs a single sharp hook and fast payoff."
    if target <= 12:
        return "Scope for a standard 10-minute video. Needs 3-4 solid points and good pacing."
    if target <= 25:
        return "Scope for a deep-dive 20-minute video. Needs comprehensive breakdown, examples, and nuance."
    return "Scope for a long-form 30+ minute masterclass. Needs exhaustive detail and multiple case studies."


def _format_mcp_result(mcp: dict[str, Any]) -> str:
    parts = []
    
    thesis = mcp.get("winning_thesis")
    if thesis:
        parts.append(f"WINNING THESIS:\n{thesis.get('statement', '')}")
        pts = "\n- ".join(thesis.get("supporting_points", []))
        if pts:
            parts.append(f"SUPPORTING POINTS:\n- {pts}")
            
    supply = mcp.get("supply_side_report", {})
    gaps = supply.get("gaps", [])
    if gaps:
        parts.append("SUPPLY GAPS (What's missing in current content):")
        for g in gaps:
            parts.append(f"- [{g.get('gap_type', 'gap')}] {g.get('description', '')}")
            
    unmet = mcp.get("unmet_asks", [])
    if unmet:
        parts.append("UNMET AUDIENCE ASKS (What people want):")
        for u in unmet:
            if u.get("unmet_ask"):
                parts.append(f"- {u.get('theme', '')} (Freq: {u.get('frequency', 0)})")
                
    return "\n\n".join(parts)


def _format_profile(profile: UserProfileSlice) -> str:
    return (
        f"Positioning: {profile.positioning or 'None'}\n"
        f"Audience: {profile.audience or 'None'}\n"
        f"Voice: {profile.voice or 'None'}\n"
        f"Avoid: {profile.things_to_avoid or 'None'}"
    )


def _parse_content(content: list[Any]) -> str:
    """Extract text from Anthropic response content blocks."""
    for block in content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "") or ""
        if isinstance(block, dict) and block.get("type") == "text":
            return block.get("text", "") or ""
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            return text
    return ""


async def transform_mcp_to_ladder_ideas(
    mcp_result: dict[str, Any],
    profile: UserProfileSlice,
    topic: str,
    target_duration_min: int,
    knowledge_context: str | None,
) -> tuple[ResearchIdeas, dict[str, int]]:
    """Convert an MCP ResearchResult to Ladder ResearchIdeas using Claude."""
    
    client = anthropic_client()
    
    mcp_text = _format_mcp_result(mcp_result)
    profile_text = _format_profile(profile)
    duration_text = _duration_brief(target_duration_min)
    kg_text = knowledge_context or "(No prior knowledge retrieved)"
    
    user_prompt = f"""\
TOPIC: {topic}
TARGET RUNTIME: {target_duration_min} minutes ({duration_text})

CREATOR PROFILE:
{profile_text}

FOUNDER KNOWLEDGE (Incorporate this if relevant to the topic):
{kg_text}

MCP RESEARCH REPORT:
{mcp_text}

Generate 4-6 video ideas based on this research and profile.
"""

    try:
        resp = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=4096,
            temperature=0.7,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            extra_headers={"anthropic-beta": ANTHROPIC_STRUCTURED_OUTPUTS_BETA},
            extra_body={
                "output_format": {"type": "json_schema", "schema": _IDEAS_SCHEMA}
            },
        )
    except APIStatusError as e:
        if e.status_code == 400 and "schema" in str(e).lower():
            log.warning("Structured outputs unavailable for idea formatting, falling back")
            return await _transform_prompted(user_prompt)
        raise

    raw = _parse_content(resp.content)
    if not raw or not raw.strip():
        return await _transform_prompted(user_prompt)
        
    try:
        result = json.loads(raw) if isinstance(raw, str) else raw
        parsed = ResearchIdeas.model_validate(result)
    except (json.JSONDecodeError, TypeError, Exception) as e:
        log.warning("Failed to parse structured ideas: %s — falling back", e)
        return await _transform_prompted(user_prompt)
        
    usage = {
        "input_tokens": getattr(resp.usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(resp.usage, "output_tokens", 0) or 0,
    }
    
    return parsed, usage


async def _transform_prompted(user_prompt: str) -> tuple[ResearchIdeas, dict[str, int]]:
    """Fallback when JSON schema fails."""
    client = anthropic_client()
    
    system = (
        _SYSTEM_PROMPT
        + "\n\nCRITICAL: Return ONLY a JSON object. No markdown fences. No prose. "
        "JSON shape must precisely match:\n"
        '{"ideas": [{"title": "...", "rationale": "...", "idea_type": "systems|framework|pitch|case_study", "opportunity_score": 85, "outlier_score": 5.5, "why_now": "...", "suggested_tags": ["..."]}]}'
    )
    
    resp = await client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=4096,
        temperature=0.7,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )
    
    raw = _parse_content(resp.content)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
    try:
        result = json.loads(cleaned) if isinstance(cleaned, str) else cleaned
        parsed = ResearchIdeas.model_validate(result)
    except Exception as e:
        raise RuntimeError(f"Failed to parse prompted ideas JSON: {e}")
        
    usage = {
        "input_tokens": getattr(resp.usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(resp.usage, "output_tokens", 0) or 0,
    }
    
    return parsed, usage
