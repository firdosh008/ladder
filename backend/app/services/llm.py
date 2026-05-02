"""LLM factories.

Two construction paths, both routed through this module so BYOK in v2 has
exactly one swap point (per backend-dys.md):

  • `anthropic_llm()` — CrewAI LLM (litellm under the hood). Used when the
    agent runs inside a CrewAI Crew.
  • `anthropic_client()` — raw Anthropic AsyncAnthropic SDK client. Used when
    we need features CrewAI's prompt-based wrapper can't deliver — most
    importantly Anthropic's structured outputs (grammar-constrained JSON).

CrewAI's `output_pydantic` is prompted JSON: the schema is injected into
the system prompt and the model is asked nicely. That's good enough for
small/flat schemas (Script/Outline/ResearchIdeas) but unreliable for large
nested ones (the scene `SceneSkeleton` was failing ~every run because the
model dropped the top-level `elements` array). Use `anthropic_client()`
+ `output_format={"type":"json_schema",...}` for those.
"""

from __future__ import annotations

from anthropic import AsyncAnthropic
from crewai import LLM

from app.config import settings

ANTHROPIC_STRUCTURED_OUTPUTS_BETA = "structured-outputs-2025-11-13"


def _require_key() -> str:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured. Set it in backend/.env."
        )
    return settings.ANTHROPIC_API_KEY


def anthropic_llm(temperature: float = 0.5, *, model: str | None = None) -> LLM:
    """CrewAI LLM bound to Anthropic + server-default key.

    ``model`` overrides the default ``settings.ANTHROPIC_MODEL`` when an
    individual agent needs a specific tier (e.g. the visual agent runs
    on Sonnet 4.6 even when the global default is Haiku).
    """
    return LLM(
        model=f"anthropic/{model or settings.ANTHROPIC_MODEL}",
        api_key=_require_key(),
        temperature=temperature,
    )


def anthropic_client() -> AsyncAnthropic:
    """Raw Anthropic SDK client — use for structured outputs / vision /
    anything CrewAI's prompted-JSON LLM wrapper can't express."""
    return AsyncAnthropic(api_key=_require_key())
