"""LLM factory for CrewAI agents.

CrewAI's `LLM` wraps litellm. Anthropic models go through the
`anthropic/<model-id>` provider prefix. Server-default key (v1); per backend-dys.md
BYOK via Vault lands in v2.
"""

from __future__ import annotations

from crewai import LLM

from app.config import settings


def anthropic_llm(temperature: float = 0.5) -> LLM:
    """Return a CrewAI LLM bound to Anthropic + server-default key.

    Raises if ANTHROPIC_API_KEY is missing — agents should never silently
    swap providers.
    """
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured. Set it in backend/.env."
        )
    return LLM(
        model=f"anthropic/{settings.ANTHROPIC_MODEL}",
        api_key=settings.ANTHROPIC_API_KEY,
        temperature=temperature,
    )
