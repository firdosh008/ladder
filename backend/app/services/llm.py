"""LLM factories.

Two construction paths, both routed through this module so BYOK in v2
has exactly one swap point (per backend-dys.md):

  • `anthropic_llm()`    — CrewAI ``LLM`` (litellm under the hood). Used
                           for every agent that runs inside a CrewAI
                           Crew.
  • `anthropic_client()` — raw Anthropic AsyncAnthropic SDK client. Used
                           for features CrewAI's prompted-JSON wrapper
                           can't deliver — most importantly Anthropic's
                           grammar-constrained structured outputs.

CrewAI's `output_pydantic` is prompted JSON: the schema is injected into
the system prompt and the model is asked nicely. That's good enough for
small/flat schemas (Script/Outline/ResearchIdeas) but unreliable for large
nested ones (the scene `SceneSkeleton` was failing ~every run because the
model dropped the top-level `elements` array). Use `anthropic_client()`
+ `output_format={"type":"json_schema",...}` for those.

One tool-schema patch lives here (applied at module import via
``_install_tool_schema_patches``). It hooks
``crewai.utilities.agent_utils.convert_tools_to_openai_schema`` because
that's the single chokepoint every CrewAI LLM provider feeds tool defs
through:

  **Strict-mode strip.** CrewAI 1.14.2 hardcodes ``"strict": True`` on
  every tool. Anthropic caps strict tools at 20/request; the visual
  agent's MCP toolkit blows past that. We don't need
  grammar-constrained tool calls — CrewAI's own retry catches malformed
  ones — so we drop the ``strict`` flag and the Anthropic provider
  falls back to its non-strict path.

A second patch — stripping null variants from optional tool parameters
to dodge Anthropic's 16-union cap — was tried (2026-05-02) and reverted.
The strip got us under the cap, but the agent kept emitting literal
``null`` for optional fields and the MCP server's Zod validators
rejected the calls. The 16-union cap is now solved upstream by splitting
the visual agent into three role-scoped agents (planner / drawer /
critic) so each per-agent API request has fewer optional params and
stays under the cap naturally — see ``app/agents/visual/build.py``.
"""

from __future__ import annotations

import logging
from typing import Any

from anthropic import AsyncAnthropic
from crewai import LLM

from app.config import settings

ANTHROPIC_STRUCTURED_OUTPUTS_BETA = "structured-outputs-2025-11-13"

log = logging.getLogger(__name__)


def _install_tool_schema_patches() -> None:
    """Install the strict-off workaround on CrewAI's tool conversion.

    See module docstring for the full rationale. The patch hooks
    ``convert_tools_to_openai_schema`` because that's the only chokepoint
    every provider — litellm-wrapped or native — flows through before
    tools reach the wire.

    Rebinding caveat: CrewAI consumers like
    ``crewai.agents.crew_agent_executor`` import the symbol with
    ``from … import convert_tools_to_openai_schema``, which copies the
    function reference into the consumer's namespace at import time.
    Reassigning ``agent_utils.convert_tools_to_openai_schema`` alone
    leaves those copies pointing at the original — silently. We have
    to walk ``sys.modules`` and rebind every consumer that already
    grabbed a reference. (Verified the hard way 2026-05-02 — the patch
    "worked" in unit tests but not under the live agent path.)

    Idempotent under repeated imports: the wrapper carries a marker
    attribute and short-circuits if it's already installed.
    """
    import sys

    from crewai.utilities import agent_utils

    if getattr(
        agent_utils.convert_tools_to_openai_schema, "_ladder_patched", False
    ):
        return

    original = agent_utils.convert_tools_to_openai_schema

    def _patched(*args: Any, **kwargs: Any):
        result = original(*args, **kwargs)
        # The function returns ``(openai_tools, available_functions, name_map)``;
        # be defensive in case CrewAI changes the shape downstream.
        openai_tools = result[0] if isinstance(result, tuple) else result
        if isinstance(openai_tools, list):
            for tool in openai_tools:
                fn = tool.get("function") if isinstance(tool, dict) else None
                if not isinstance(fn, dict):
                    continue
                # Drop strict — Anthropic caps strict tools at 20/req. The
                # Anthropic provider does ``bool(func_info.get("strict"))``,
                # so popping the key makes that False without touching
                # OpenAI/Google providers that read ``strict`` differently.
                fn.pop("strict", None)
        return result

    _patched._ladder_patched = True  # type: ignore[attr-defined]

    # Rebind at the source module …
    agent_utils.convert_tools_to_openai_schema = _patched
    # … and at every importer that already grabbed a copy. Iterate over
    # a snapshot of values: importing CrewAI submodules above may have
    # mutated sys.modules.
    rebound = 0
    for mod in list(sys.modules.values()):
        if mod is None or mod is agent_utils:
            continue
        existing = getattr(mod, "convert_tools_to_openai_schema", None)
        if existing is original:
            try:
                setattr(mod, "convert_tools_to_openai_schema", _patched)
                rebound += 1
            except (AttributeError, TypeError):
                # Some modules forbid attribute assignment (e.g. C-extension
                # modules); skip those — they won't have re-imported a
                # pure-Python helper anyway.
                continue
    log.info(
        "patched convert_tools_to_openai_schema: strict=off "
        "(rebound in %d consumer module(s))",
        rebound,
    )


_install_tool_schema_patches()


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
