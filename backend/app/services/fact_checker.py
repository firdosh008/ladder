"""Fact-checker service — verifies AI-generated claims against research sources.

Uses Anthropic structured outputs (grammar-constrained JSON) for reliable claim
extraction and verdict assignment. Runs as a direct SDK call, NOT a CrewAI agent
— ~5x cheaper in tokens and ~3x faster.

Single public entry point: ``run_fact_check(text, sources, claim_types)``
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal

from anthropic import APIStatusError
from pydantic import BaseModel, Field

from app.config import settings
from app.providers import exa
from app.services.llm import ANTHROPIC_STRUCTURED_OUTPUTS_BETA, anthropic_client

log = logging.getLogger(__name__)

ClaimType = Literal[
    "statistic", "attributed_quote", "market_assertion",
    "historical_fact", "definitional", "other",
]
Verdict = Literal["verified", "contradicted", "unverifiable"]
ClaimImportance = Literal["core", "contextual"]


class FactClaim(BaseModel):
    """A single extractable factual assertion from generated content."""
    claim_text: str = Field(min_length=1, max_length=600)
    claim_type: ClaimType
    source_context: str = Field(
        default="",
        description="The 1-2 sentence context around the claim in the original text",
    )
    importance: ClaimImportance = Field(
        default="core",
        description="'core' = the script depends on this being true. 'contextual' = illustrative example or narrative color that doesn't need fact-checking.",
    )


class VerdictDetail(BaseModel):
    """A claim with its verification verdict."""
    claim: FactClaim
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    source_url: str | None = None
    supporting_text: str | None = None
    explanation: str = ""


class FactCheckReport(BaseModel):
    """Top-level verification report."""
    claims: list[VerdictDetail] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


# ── Schema for structured output ─────────────────────────────────────────────

_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_text": {
                        "type": "string",
                        "description": "The exact factual claim as it appears in the text",
                    },
                    "claim_type": {
                        "type": "string",
                        "enum": [
                            "statistic", "attributed_quote", "market_assertion",
                            "historical_fact", "definitional", "other",
                        ],
                    },
                    "source_context": {
                        "type": "string",
                        "description": "1-2 sentences of surrounding context from the original text",
                    },
                    "importance": {
                        "type": "string",
                        "enum": ["core", "contextual"],
                        "description": "'core' = the argument DEPENDS on this being true. 'contextual' = illustrative example, narrative color, hypothetical, or conversational number. IF UNSURE, use 'contextual'.",
                    },
                },
                "required": ["claim_text", "claim_type", "source_context", "importance"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["claims"],
    "additionalProperties": False,
}

_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_text": {"type": "string"},
                    "verdict": {
                        "type": "string",
                        "enum": ["verified", "contradicted", "unverifiable"],
                    },
                    "confidence": {
                        "type": "number",
                        "description": "0.0-1.0. Use <0.6 when uncertain.",
                    },
                    "source_url": {
                        "type": ["string", "null"],
                        "description": "URL of the source that backs the verdict. Required when verdict is 'verified'. Null otherwise.",
                    },
                    "supporting_text": {
                        "type": ["string", "null"],
                        "description": "Excerpt from source that supports or contradicts the claim.",
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Why this verdict was reached. For 'unverifiable', explain what was searched and why no match was found.",
                    },
                },
                "required": [
                    "claim_text", "verdict", "confidence",
                    "source_url", "supporting_text", "explanation",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}

# ── Prompt templates ─────────────────────────────────────────────────────────

_EXTRACT_SYSTEM = """\
You are a forensic fact-checker for a video script. Extract ONLY claims that are \
CENTRAL factual assertions — claims where the script's argument COLLAPSES if they \
are wrong. Every claim you extract costs real money to verify, so be surgical.

ASSIGN IMPORTANCE:
  "core" — The script's credibility depends on this being true.
    Example: "73% of startups fail within 5 years" (this IS the argument)
    Example: "McKinsey reports AI adoption grew 60%" (named-source stat)
  "contextual" — Illustrative, conversational, or rhetorical. The script still
    works even if the number is approximate. These do NOT need verification.
    Example: "You pay fifty bucks a month for Game Pass" (illustrative price example)
    Example: "Imagine running fourteen different SaaS tools" (hypothetical)
    Example: "It takes about five minutes to set up" (rough estimate)
    Example: "Companies spend hundreds of hours on this" (vague magnitude)

TWO-QUESTION TEST for every claim:
  1. Would the script be MATERIALLY WRONG if this number was incorrect?
  2. Is this claim presented as a DEFINITIVE FACT (not an example or estimate)?

  YES+YES → "core"
  Anything else → "contextual" or skip entirely.

EXTRACT ONLY "core" claims that:
  - Cite a specific study, report, or named source: "Gartner reports..."
  - Make a definite statistical assertion central to the argument
  - Assert a specific market size, growth rate, or numerical trend
  - Claim a precise historical fact with a date

SKIP ENTIRELY (return no claim):
  - Conversational examples: "you pay $X for Y", "think about it — 14 tools"
  - Hypotheticals: "imagine if...", "say you have..."
  - Rough estimates: "about X", "around Y", "hundreds of Z"
  - Generic pricing mentions used as narrative color
  - Rhetorical numbers that serve story flow, not factual assertion
  - Advice, opinions, how-to steps, meta-commentary
  - Qualitative claims without a specific verifiable number
  - Product names, tool mentions, feature lists

If unsure whether a claim is "core", mark it "contextual" or skip it. \
It is better to return 3 verified core claims than 15 contextual ones. \
Zero claims is a VALID and EXPECTED result — most scripts have few truly \
checkable core assertions."""

_EXTRACT_USER = """\
Extract every core factual claim from this video script content.
Only extract claims where the script's argument depends on the claim being true.
Skip conversational examples, rough estimates, and narrative color.

{text}"""

_VERIFY_SYSTEM = """\
You are a forensic fact-checker verifying claims against source evidence.

Different claim types need DIFFERENT evidence — match the claim type to the
right source platform:

CLAIM TYPE → EVIDENCE STANDARD:
  statistic          → web source with matching/similar numbers
  market_assertion   → web source confirming the market claim
  historical_fact    → web source confirming the historical event
  attributed_quote   → the named person/source MUST appear in the source.
                       A tweet by @expert IS valid evidence they said it.
                       A Reddit post by u/user IS valid evidence of their view.
  definitional       → low bar; common knowledge, any relevant source works
  other              → best effort against any source

SOURCE PLATFORM → WHAT IT CAN VERIFY:
  web       → statistics, research findings, market data, historical facts
  reddit    → community sentiment, user experiences, pain points (NOT statistics)
  youtube   → creator statements, visual trends (NOT market data)
  x         → individual opinions, hot-takes, expert statements (NOT statistics)
  instagram → cultural patterns, visual trends (NOT statistics)

For each claim, assign:
  verified — a source CONFIRMS the claim using the appropriate evidence standard.
    You MUST provide the source_url.
  contradicted — a source DIRECTLY CONTRADICTS the claim.
    You MUST provide the source_url and the contradictory text.
  unverifiable — no source confirms or contradicts. Set source_url null.
    Write what you would search for in the explanation.
    This is a statement about OUR SOURCES, not about the claim's truth.

MATCHING RULES:
  - Semantic equivalence counts: "73% fail" MATCHES "7 out of 10 don't survive"
  - Rounding is OK: "73%" matches "about 70%" or "roughly three quarters"
  - Same ballpark: "$50B market" matches "market valued at $48 billion"
  - For attributed_quote: the source URL + matching author/handle IS verification.
    The source snippet doesn't need the exact quote — same topic from same person counts.
  - For statistic: need a web source. A Reddit comment stating a number is NOT
    verification of that number — mark as unverifiable.
  - A source about the SAME TOPIC with a RELATED number is not automatically a
    contradiction — it may be a different study/year/methodology.

CONFIDENCE:
  - 0.9+ for exact matches (same number, same context)
  - 0.7-0.89 for near matches (same ballpark, different wording)
  - 0.5-0.69 for plausible but unconfirmed
  - <0.5 for guesses
  - If confidence < 0.6, always mark as unverifiable.

WHEN IN DOUBT: be conservative. "Unverifiable" means "we couldn't confirm this" —
it does NOT mean the claim is false."""

_VERIFY_USER = """\
CLAIMS TO VERIFY (type shown in brackets — use the right evidence standard per type):
{claims}

AVAILABLE SOURCES (platform shown in brackets — match platform to claim type):
{sources}

For each claim, return a verdict using the evidence standard that matches the claim type.
Cite source URLs verbatim."""


# ── Source snippet helpers ───────────────────────────────────────────────────


def _source_block(sources: list[dict[str, Any]]) -> str:
    """Format source list into a compact text block for the LLM prompt."""
    if not sources:
        return "(No research sources available — all claims will need Exa search)"

    lines: list[str] = []
    for i, s in enumerate(sources, 1):
        title = s.get("title") or "Untitled"
        url = s.get("url") or ""
        snippet = (s.get("snippet") or "")[:2000]
        platform = s.get("platform") or "web"
        lines.append(f"{i}. [{platform}] {title}\n   URL: {url}\n   Snippet: {snippet}")
    return "\n\n".join(lines)


def _claims_block(claims: list[FactClaim]) -> str:
    """Format claims for the verify prompt."""
    lines: list[str] = []
    for i, c in enumerate(claims, 1):
        lines.append(
            f"{i}. [{c.claim_type}] {c.claim_text}\n"
            f"   Context: {c.source_context}"
        )
    return "\n\n".join(lines)


# ── Main pipeline ────────────────────────────────────────────────────────────


async def _extract_claims(text: str) -> list[FactClaim]:
    """LLM call 1: extract checkable factual claims from text."""
    client = anthropic_client()

    try:
        resp = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=2048,
            temperature=0.1,
            system=_EXTRACT_SYSTEM,
            messages=[{
                "role": "user",
                "content": _EXTRACT_USER.format(text=text),
            }],
            extra_headers={"anthropic-beta": ANTHROPIC_STRUCTURED_OUTPUTS_BETA},
            extra_body={
                "output_format": {"type": "json_schema", "schema": _EXTRACT_SCHEMA}
            },
        )
    except APIStatusError as e:
        if e.status_code == 400 and "schema" in str(e).lower():
            log.warning("Structured outputs unavailable for claim extraction, falling back")
            return await _extract_claims_prompted(text)
        raise

    raw = _parse_content(resp.content)
    if not raw or not raw.strip():
        return []
    try:
        result = json.loads(raw) if isinstance(raw, str) else raw
        claims_data = result.get("claims") or []
        for c in claims_data:
            if isinstance(c, dict):
                if "claim" in c and "claim_text" not in c:
                    c["claim_text"] = c.pop("claim")
                if "type" in c and "claim_type" not in c:
                    c["claim_type"] = c.pop("type")
        return [FactClaim(**c) for c in claims_data]
    except (json.JSONDecodeError, TypeError):
        # DeepSeek and other non-Anthropic models ignore output_format and
        # return natural-language text. Fall back to prompted JSON path
        # which has a stronger "ONLY return JSON" system prompt.
        log.info("Structured output returned natural language — falling back to prompted JSON")
        return await _extract_claims_prompted(text)


async def _extract_claims_prompted(text: str) -> list[FactClaim]:
    """Prompted JSON extraction — works with any LLM (DeepSeek, OpenAI, etc)."""
    client = anthropic_client()
    prompt = (
        "You are a forensic fact-checker. Extract ONLY core factual claims — claims "
        "where the script's argument COLLAPSES if they are wrong.\n\n"
        "RULES:\n"
        "1. Return ONLY a JSON object. No markdown fences. No prose. No preamble.\n"
        "2. JSON shape:\n"
        '   {"claims": [{"claim_text": "...", "claim_type": "statistic", '
        '"source_context": "...", "importance": "core"}]}\n'
        "3. claim_text: the EXACT definitive assertion.\n"
        "4. claim_type: one of statistic, attributed_quote, market_assertion, historical_fact, definitional, other.\n"
        "5. source_context: 1-2 sentences around the claim in the original text.\n"
        "6. importance: 'core' = script depends on this being true. 'contextual' = illustrative example, rough estimate, conversational reference.\n"
        "7. SKIP: conversational examples ('you pay $X for Y'), rough estimates ('about X'), hypotheticals, opinions, product names.\n"
        "8. Only extract claims where being WRONG would invalidate the script's argument.\n"
        "9. Zero checkable core claims → return {\"claims\": []}.\n\n"
        "START YOUR RESPONSE WITH { AND END WITH }. NO OTHER TEXT."
    )
    resp = await client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=2048,
        temperature=0.1,
        system=prompt,
        messages=[{
            "role": "user",
            "content": _EXTRACT_USER.format(text=text),
        }],
    )
    raw = _parse_content(resp.content)
    if not raw or not raw.strip():
        return []
    # Strip markdown fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    try:
        result = json.loads(cleaned) if isinstance(cleaned, str) else cleaned
        claims_data = result.get("claims") or []
        for c in claims_data:
            if isinstance(c, dict):
                if "claim" in c and "claim_text" not in c:
                    c["claim_text"] = c.pop("claim")
                if "type" in c and "claim_type" not in c:
                    c["claim_type"] = c.pop("type")
        return [FactClaim(**c) for c in claims_data]
    except (json.JSONDecodeError, Exception) as e:
        log.warning("Failed to parse prompted claims: %s — raw: %s", e, str(raw)[:200])
        return []


async def _verify_claims(
    claims: list[FactClaim],
    sources: list[dict[str, Any]],
) -> list[VerdictDetail]:
    """LLM call 2: verify claims against source snippets."""
    if not claims:
        return []

    client = anthropic_client()
    user_content = _VERIFY_USER.format(
        claims=_claims_block(claims),
        sources=_source_block(sources),
    )

    try:
        resp = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=4096,
            temperature=0.1,
            system=_VERIFY_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
            extra_headers={"anthropic-beta": ANTHROPIC_STRUCTURED_OUTPUTS_BETA},
            extra_body={
                "output_format": {"type": "json_schema", "schema": _VERIFY_SCHEMA}
            },
        )
    except APIStatusError as e:
        if e.status_code == 400 and "schema" in str(e).lower():
            log.warning("Structured outputs unavailable for verification, falling back")
            return await _verify_claims_prompted(claims, sources)
        raise

    raw = _parse_content(resp.content)
    if not raw or not raw.strip():
        return await _verify_claims_prompted(claims, sources)
    try:
        result = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        log.info("Structured verification returned natural language — falling back to prompted JSON")
        return await _verify_claims_prompted(claims, sources)
    verdicts_data = result.get("verdicts") or []

    verdicts: list[VerdictDetail] = []
    for v in verdicts_data:
        claim_text = v.get("claim_text", "")
        matching_claim = next(
            (c for c in claims if c.claim_text == claim_text), None
        )
        verdicts.append(VerdictDetail(
            claim=matching_claim or FactClaim(
                claim_text=claim_text,
                claim_type="other",
                source_context="",
            ),
            verdict=v.get("verdict", "unverifiable"),
            confidence=v.get("confidence", 0.5),
            source_url=v.get("source_url"),
            supporting_text=v.get("supporting_text"),
            explanation=v.get("explanation", ""),
        ))
    return verdicts


async def _verify_claims_prompted(
    claims: list[FactClaim],
    sources: list[dict[str, Any]],
) -> list[VerdictDetail]:
    """Fallback: prompted JSON verification — works with any LLM."""
    client = anthropic_client()
    prompt = (
        _VERIFY_SYSTEM
        + "\n\nCRITICAL: Return ONLY a JSON object. No markdown fences. No prose. No preamble. "
        "Start with { and end with }.\n\n"
        "JSON shape: {\"verdicts\": [{\"claim_text\": \"...\", \"verdict\": \"verified|contradicted|unverifiable\", "
        "\"confidence\": 0.0, \"source_url\": null, \"supporting_text\": null, "
        "\"explanation\": \"...\"}]}"
    )
    resp = await client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=4096,
        temperature=0.1,
        system=prompt,
        messages=[{
            "role": "user",
            "content": _VERIFY_USER.format(
                claims=_claims_block(claims),
                sources=_source_block(sources),
            ),
        }],
    )
    raw = _parse_content(resp.content)
    if not raw or not raw.strip():
        return []
    # Strip markdown fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    try:
        result = json.loads(cleaned) if isinstance(cleaned, str) else cleaned
        verdicts_data = result.get("verdicts") or []
        verdicts: list[VerdictDetail] = []
        for v in verdicts_data:
            claim_text = v.get("claim_text", "")
            matching_claim = next(
                (c for c in claims if c.claim_text == claim_text), None
            )
            verdicts.append(VerdictDetail(
                claim=matching_claim or FactClaim(
                    claim_text=claim_text, claim_type="other", source_context="",
                ),
                verdict=v.get("verdict", "unverifiable"),
                confidence=v.get("confidence", 0.5),
                source_url=v.get("source_url"),
                supporting_text=v.get("supporting_text"),
                explanation=v.get("explanation", ""),
            ))
        return verdicts
    except (json.JSONDecodeError, Exception) as e:
        log.warning("Failed to parse prompted verdicts: %s", e)
        return []


async def _exa_fallback(
    verdicts: list[VerdictDetail],
) -> list[VerdictDetail]:
    """For unverifiable claims, run parallel Exa searches and re-verify."""
    unverifiable = [v for v in verdicts if v.verdict == "unverifiable"]
    if not unverifiable:
        return verdicts

    # Run parallel Exa searches for each unverifiable claim
    async def _search_one(v: VerdictDetail) -> tuple[VerdictDetail, list[dict[str, Any]]]:
        try:
            results = await exa.search(
                query=v.claim.claim_text[:200],
                num_results=3,
            )
            sources = [
                {
                    "title": r.title,
                    "url": r.url,
                    "snippet": (r.text or "")[:2000],
                    "platform": "web",
                }
                for r in results
            ]
        except Exception:
            log.warning("Exa search failed for claim: %s", v.claim.claim_text[:80])
            sources = []
        return v, sources

    tasks = [_search_one(v) for v in unverifiable]
    pairs = await asyncio.gather(*tasks)

    # Re-verify claims that got Exa results
    needs_recheck: list[tuple[VerdictDetail, list[dict[str, Any]]]] = [
        (v, srcs) for v, srcs in pairs if srcs
    ]
    if not needs_recheck:
        return verdicts

    claims_to_recheck = [v.claim for v, _ in needs_recheck]
    all_exa_sources: list[dict[str, Any]] = []
    for _, srcs in needs_recheck:
        all_exa_sources.extend(srcs)

    re_verdicts = await _verify_claims(claims_to_recheck, all_exa_sources)

    # Merge back
    verdict_map = {v.claim.claim_text: v for v in verdicts}
    for rv in re_verdicts:
        key = rv.claim.claim_text
        if key in verdict_map:
            verdict_map[key] = rv

    return list(verdict_map.values())


def _summarize(verdicts: list[VerdictDetail]) -> dict[str, int]:
    total = len(verdicts)
    verified = sum(1 for v in verdicts if v.verdict == "verified")
    contradicted = sum(1 for v in verdicts if v.verdict == "contradicted")
    unverifiable = sum(1 for v in verdicts if v.verdict == "unverifiable")
    return {
        "total": total,
        "verified": verified,
        "contradicted": contradicted,
        "unverifiable": unverifiable,
    }


# ── Public API ───────────────────────────────────────────────────────────────


async def run_fact_check(
    text: str,
    sources: list[dict[str, Any]] | None = None,
) -> FactCheckReport:
    """Verify factual claims in *text* against *sources* + Exa fallback.

    Only "core" claims (where the script's argument depends on them being true)
    go through verification. "contextual" claims (illustrative examples, narrative
    color) are included in the report but not fact-checked — they're not meant to
    be taken as definitive factual assertions.

    Args:
        text: The generated content to fact-check (script talking_points,
              idea rationale, scene element text, etc.)
        sources: Optional list of source dicts from research_snapshot.
                 Each dict should have: title, url, snippet, platform.

    Returns:
        FactCheckReport with all claims, verdicts, and summary counts.
    """
    if not text or not text.strip():
        return FactCheckReport(summary={"total": 0, "verified": 0, "contradicted": 0, "unverifiable": 0})

    source_list = sources or []

    # Stage 1: extract claims
    try:
        claims = await _extract_claims(text)
    except Exception:
        log.exception("Claim extraction failed")
        return FactCheckReport(summary={"total": 0, "verified": 0, "contradicted": 0, "unverifiable": 0})

    if not claims:
        return FactCheckReport(summary={"total": 0, "verified": 0, "contradicted": 0, "unverifiable": 0})

    # Split: only verify core claims. Contextual claims are illustrative
    # and don't need fact-checking (e.g. "you pay $50/mo for Game Pass").
    core_claims = [c for c in claims if c.importance == "core"]
    contextual_claims = [c for c in claims if c.importance == "contextual"]

    # Auto-mark contextual claims — they ARE the answer
    contextual_verdicts = [
        VerdictDetail(
            claim=c,
            verdict="unverifiable",
            confidence=0.0,
            explanation="Not fact-checked — this is an illustrative example or conversational reference, not a factual assertion that needs verification.",
        )
        for c in contextual_claims
    ]

    # Stage 2: verify core claims against sources
    core_verdicts: list[VerdictDetail] = []
    if core_claims:
        try:
            core_verdicts = await _verify_claims(core_claims, source_list)
        except Exception:
            log.exception("Claim verification failed")
            core_verdicts = [
                VerdictDetail(
                    claim=c,
                    verdict="unverifiable",
                    confidence=0.0,
                    explanation="Verification step failed — could not check sources",
                )
                for c in core_claims
            ]

    verdicts = core_verdicts + contextual_verdicts

    # Stage 3: Exa fallback for unverifiable CORE claims only
    if settings.EXA_API_KEY and any(
        v.verdict == "unverifiable" and v.claim.importance == "core"
        for v in verdicts
    ):
        try:
            verdicts = await _exa_fallback(verdicts)
        except Exception:
            log.exception("Exa fallback failed — returning source-only verdicts")

    return FactCheckReport(claims=verdicts, summary=_summarize(verdicts))


def _parse_content(content: list[Any]) -> str:
    """Extract text from Anthropic response content blocks."""
    for block in content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "") or ""
        if isinstance(block, dict) and block.get("type") == "text":
            return block.get("text", "") or ""
    # Fallback: first block with text attribute
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            return text
    return ""
