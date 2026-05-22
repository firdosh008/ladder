"""Verification layer with structured claim triage and source-backed checks."""

from __future__ import annotations

import logging
import re

from research_agent.graph import ResearchState
from research_agent.models import AgentEvent, CostBreakdown, SourceRef
from research_agent.tools.web_search import web_search

logger = logging.getLogger(__name__)


async def verification_node(state: ResearchState) -> dict:
    """Verify material factual claims in the winning thesis."""
    events = [AgentEvent(event="layer_start", layer="verification", message="Running tiered fact-checking").to_dict()]
    cost = state.get("cost", CostBreakdown())
    thesis = state.get("winning_thesis")

    if not thesis or not thesis.statement:
        events.append(AgentEvent(event="layer_complete", layer="verification", message="No thesis to verify").to_dict())
        return {"verified": False, "verification_notes": [], "events": events, "cost": cost}

    events.append(AgentEvent(event="agent_start", layer="verification", agent="ClaimTriage",
                             message="Triaging claims for verification priority").to_dict())

    claims = [thesis.statement] + thesis.supporting_points
    sources = state.get("sources", [])
    notes = []

    for claim in claims:
        note = _triage_claim(claim)
        if not note["material"] or note["claim_type"] == "opinion":
            note.update({
                "verdict": "not_required",
                "evidence_urls": [],
                "note": "Opinion or non-material framing; verification not required.",
            })
            notes.append(note)
            continue

        evidence = _find_source_evidence(claim, sources, note["claim_type"])
        if not evidence and note["claim_type"] in {"statistic", "factual_assertion"}:
            try:
                fallback_sources = await web_search(claim, max_results=3)
                evidence = _find_source_evidence(claim, fallback_sources, note["claim_type"])
            except Exception as e:
                logger.warning(f"Verification fallback search failed: {e}")

        if evidence:
            note.update({
                "verdict": "verified",
                "evidence_urls": [source.url for source in evidence[:3]],
                "note": "Found supporting source evidence with semantic/token overlap.",
            })
        else:
            note.update({
                "verdict": "unverifiable",
                "evidence_urls": [],
                "note": "No supporting source evidence found for a material factual claim.",
            })
        notes.append(note)

    high_risk_failures = [
        note for note in notes
        if note["material"] and note["verdict"] in {"unverifiable", "false"} and note["risk"] in {"high", "medium"}
    ]
    verified = not high_risk_failures

    events.append(AgentEvent(event="agent_complete", layer="verification", agent="ClaimTriage",
                             message=f"Verification: {'PASSED' if verified else 'NEEDS REVIEW'}").to_dict())
    events.append(AgentEvent(event="layer_complete", layer="verification",
                             message=f"Fact-checking {'passed' if verified else 'flagged issues'}").to_dict())

    return {"verified": verified, "verification_notes": notes, "events": events, "cost": cost}


def _triage_claim(claim: str) -> dict:
    claim_type = _claim_type(claim)
    material = claim_type != "opinion" and len(claim.split()) >= 6
    risk = "low"
    if claim_type in {"statistic", "attributed_quote"}:
        risk = "high"
    elif claim_type == "factual_assertion":
        risk = "medium"

    return {
        "claim": claim,
        "claim_type": claim_type,
        "material": material,
        "definitive": claim_type != "opinion",
        "risk": risk,
    }


def _claim_type(claim: str) -> str:
    lowered = claim.lower()
    if re.search(r"\b\d+(\.\d+)?\s*(%|percent|x|k|m|b|million|billion)?\b", lowered):
        return "statistic"
    if '"' in claim or "'" in claim or re.search(r"\b(said|according to|reported by|wrote|claimed)\b", lowered):
        return "attributed_quote"
    if re.search(r"\b(is|are|was|were|will|has|have|causes|drives|increases|decreases|leads to)\b", lowered):
        return "factual_assertion"
    return "opinion"


def _find_source_evidence(claim: str, sources: list[SourceRef], claim_type: str) -> list[SourceRef]:
    claim_tokens = _tokens(claim)
    if not claim_tokens:
        return []

    evidence = []
    claim_numbers = set(re.findall(r"\d+(?:\.\d+)?", claim))
    for source in sources:
        haystack = f"{source.title} {source.snippet}".lower()
        source_tokens = _tokens(haystack)
        overlap = len(claim_tokens & source_tokens) / max(len(claim_tokens), 1)

        if claim_type == "statistic" and claim_numbers:
            source_numbers = set(re.findall(r"\d+(?:\.\d+)?", haystack))
            if not claim_numbers & source_numbers:
                continue

        if claim_type == "attributed_quote" and source.platform == "web" and overlap < 0.45:
            continue

        if overlap >= 0.35:
            evidence.append(source)

    return evidence


def _tokens(text: str) -> set[str]:
    stopwords = {
        "the", "a", "an", "and", "or", "but", "to", "of", "in", "for", "on", "with",
        "that", "this", "it", "is", "are", "was", "were", "be", "as", "by", "from",
    }
    return {
        token for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in stopwords
    }
