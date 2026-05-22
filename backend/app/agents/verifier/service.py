"""Verifier agent wrappers that emit WebSocket events.

Three async generators, one per content stage:

  run_idea_verification   — validates IdeaDraft rationale/why_now against research sources
  run_script_verification — validates Script talking_points against research_snapshot
  run_scene_verification  — cross-checks scene text against script + structure against outline

Each generator wraps the fact_checker service and emits typed events for the
WebSocket route handler to fan out to the frontend.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from anthropic import APIStatusError
from pydantic import BaseModel, Field

from app.models.db import Outline, SceneSkeleton, Script
from app.services.fact_checker import (
    FactCheckReport,
    VerdictDetail,
    _parse_content,
    run_fact_check,
)
from app.services.llm import ANTHROPIC_STRUCTURED_OUTPUTS_BETA, anthropic_client

log = logging.getLogger(__name__)




# ── Public generators ────────────────────────────────────────────────────────


async def run_idea_verification(
    ideas: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """Checkpoint 1: validate research idea rationale/why_now against sources."""
    yield {"type": "verifier_start", "agent": "fact_checker", "stage": "ideas"}

    text = _extract_idea_text(ideas)
    if not text.strip():
        yield {
            "type": "ideas_verification_ready",
            "report": FactCheckReport(
                summary={"total": 0, "verified": 0, "contradicted": 0, "unverifiable": 0}
            ).model_dump(),
        }
        return

    yield {"type": "verifier_claim_check", "stage": "ideas", "count": 0, "checked": 0}

    try:
        report = await run_fact_check(text, sources)
    except Exception:
        log.exception("Idea verification failed")
        yield {
            "type": "ideas_verification_ready",
            "report": FactCheckReport(
                summary={"total": 0, "verified": 0, "contradicted": 0, "unverifiable": 0}
            ).model_dump(),
        }
        return

    yield {"type": "verifier_claim_check", "stage": "ideas", "count": report.summary["total"], "checked": report.summary["total"]}

    yield {
        "type": "ideas_verification_ready",
        "report": report.model_dump(),
    }


async def run_script_verification(
    script: Script,
    sources: list[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """Checkpoint 2: validate script talking_points against research sources."""
    yield {"type": "verifier_start", "agent": "fact_checker", "stage": "script"}

    text = _extract_script_text(script)
    if not text.strip() or not sources:
        yield {
            "type": "script_verification_ready",
            "report": FactCheckReport(
                summary={"total": 0, "verified": 0, "contradicted": 0, "unverifiable": 0}
            ).model_dump(),
        }
        return

    yield {"type": "verifier_claim_check", "stage": "script", "count": 0, "checked": 0}

    try:
        report = await run_fact_check(text, sources)
    except Exception:
        log.exception("Script verification failed")
        yield {
            "type": "script_verification_ready",
            "report": FactCheckReport(
                summary={"total": 0, "verified": 0, "contradicted": 0, "unverifiable": 0}
            ).model_dump(),
        }
        return

    yield {"type": "verifier_claim_check", "stage": "script", "count": report.summary["total"], "checked": report.summary["total"]}

    yield {
        "type": "script_verification_ready",
        "report": report.model_dump(),
    }


