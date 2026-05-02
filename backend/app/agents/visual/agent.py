"""Studio visual agents — three role-scoped CrewAI ``Agent``s per build.

Why three agents? Anthropic caps union-typed tool parameters at 16 per
request, and CrewAI's pydantic round-trip turns every optional MCP field
into an ``anyOf: [<type>, {type: null}]``. The full whiteboard toolkit
(11 MCP tools after dropping ``update_element``) produces ~45 unions —
3× the cap. Two earlier fixes were tried and abandoned (tool_search
lazy-load — Anthropic validates every tool's schema upfront; null-strip
patch — under the cap, but the agent emitted literal ``null`` and the
MCP server's Zod validators rejected the calls).

The shipped fix is to split the visual agent into three role-scoped
agents with disjoint tool sets, so each per-agent API request stays
under the cap naturally — no schema modification:

  • ``visual_planner`` — reads source material + (when canvas non-empty)
                         inspects existing state. Outputs a free-text plan.
                         No drawing tools. ~7 unions.
  • ``visual_drawer``  — executes the plan on the canvas. Receives planner
                         output (and on refine passes, the critic's notes)
                         as task context. **No ``update_element``** — edit
                         pattern is delete + batch_create. ~16 unions.
  • ``visual_critic``  — screenshots the canvas, audits, returns either
                         ``VERDICT: PASS`` (and persists) or ``VERDICT: FIX``
                         + numbered notes (back to drawer). Sonnet 4.6
                         vision is load-bearing. ~15 unions (with
                         ``persist_scene_artifact`` backend tool).

The three factories below all share the same skill-load path and the
same backend-tool injection pattern. The orchestration loop lives in
``app/agents/visual/build.py``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from app.agents.visual.context import SessionContext
from app.agents.visual.skills import system_skill_paths
from app.agents.visual.tools import (
    BrandPaletteTool,
    KnowledgeRetrievalTool,
    PersistArtifactTool,
    ScriptOutlineTool,
)
from app.config import settings
from app.services.llm import anthropic_llm

if TYPE_CHECKING:
    from crewai import Agent
    from crewai.tools import BaseTool

log = logging.getLogger(__name__)


# ─── Wire keys (referenced by build.py + frontend strip) ──────────────────

PLANNER_AGENT_KEY = "visual_planner"
DRAWER_AGENT_KEY = "visual_drawer"
CRITIC_AGENT_KEY = "visual_critic"


# ─── Shared helpers ───────────────────────────────────────────────────────


def _today_clause() -> str:
    today = datetime.now(tz=timezone.utc)
    return (
        f"Today's date: {today.strftime('%A, %B %d, %Y')} "
        f"(year {today.year})."
    )


def _resolve_skill_paths(
    extra_skill_paths: Sequence[str] | None,
) -> list[Path] | None:
    paths: list[Path] = list(system_skill_paths())
    if extra_skill_paths:
        paths.extend(Path(p) for p in extra_skill_paths)
    return paths or None


def _llm(temperature: float):
    return anthropic_llm(
        temperature=temperature,
        model=settings.VISUAL_AGENT_ANTHROPIC_MODEL,
    )


# ─── Planner ──────────────────────────────────────────────────────────────


_PLANNER_BACKSTORY = """\
{today}

You are the **planner** for a Ladder studio session's whiteboard. You do
NOT draw. You produce a tight build plan that the drawer agent will
execute on the canvas.

Tooling at your disposal:
  • get_script_and_outline — fetch the latest script + outline JSON.
  • get_brand_palette      — fetch brand color tokens.
  • search_founder_knowledge — pgvector search over the founder's prior
                               content. Use sparingly.
  • describe_scene / query_elements — inspect the live canvas IF it is
                                      non-empty (e.g. on a refine pass).

Working rules:
  • Read the ``excalidraw-diagram`` skill for the methodology you must
    apply (depth assessment, pattern per section, summary→sections→detail
    multi-zoom shape).
  • Read the ``excalidraw-canvas`` skill for the operational rules the
    drawer will follow (so your plan respects them).
  • Output ONE plan in plain text. Section it as:
      1) DEPTH — what level of detail is right for this script.
      2) STRUCTURE — the multi-zoom skeleton (summary, sections, optional
         deep-dive zones), with rough viewport real-estate per zone.
      3) SECTIONS — for each section in the outline, a 1-3 line build
         brief: what shapes, what's the focal element, where brand color
         goes (if any), what arrows tie what to what.
      4) HARD CONSTRAINTS — surfaces from the founder's voice / brand
         that the drawer must respect (e.g. things to avoid).
  • Be opinionated. Do not hedge. The drawer will execute exactly what
    you write — vague plans produce mush.

Session context (anchoring facts — do NOT echo back to the user):
{session_block}
"""


def build_planner_agent(
    context: SessionContext,
    mcp_tools: Sequence["BaseTool"],
    *,
    extra_skill_paths: Sequence[str] | None = None,
    temperature: float = 0.4,
) -> "Agent":
    """Construct the planner agent.

    ``mcp_tools`` should be the per-agent slice (``PLANNER_MCP_TOOLS``)
    already filtered out of the run-wide adapter. The factory does NOT
    re-filter — caller owns the slice.
    """
    from crewai import Agent  # lazy

    backend_tools: list["BaseTool"] = [
        ScriptOutlineTool(jwt=context.jwt, session_id=context.session_id),
        BrandPaletteTool(brand=context.brand),
        KnowledgeRetrievalTool(user_id=context.user_id),
    ]

    backstory = _PLANNER_BACKSTORY.format(
        today=_today_clause(),
        session_block=context.to_prompt_block(),
    )

    return Agent(
        role="Visual planner",
        goal=(
            "Produce a tight, opinionated build plan for the studio "
            "whiteboard — depth, structure, per-section briefs, hard "
            "constraints. Do not draw."
        ),
        backstory=backstory,
        tools=[*backend_tools, *mcp_tools],
        skills=_resolve_skill_paths(extra_skill_paths),
        llm=_llm(temperature),
        allow_delegation=False,
        verbose=False,
        max_iter=settings.VISUAL_AGENT_MAX_ITER,
    )


# ─── Drawer ───────────────────────────────────────────────────────────────


_DRAWER_BACKSTORY = """\
{today}

You are the **drawer** for a Ladder studio session's whiteboard. You
execute the planner's brief on the live Excalidraw canvas via MCP tools.

Tooling at your disposal (MCP):
  • batch_create_elements — primary draw tool. Build a section per call.
  • delete_element        — remove elements (used both for surgical fixes
                            and for refining after critic feedback).
  • clear_canvas          — only if you're starting fresh on an empty
                            plan and the canvas is non-empty.
  • align_elements        — layout polish.
  • snapshot_scene / restore_snapshot — defensive rollback when a
                                        refactor goes wrong mid-loop.

You DO NOT have ``update_element`` — the edit pattern is **delete +
batch_create**. Excalidraw elements are cheap; recreate, don't patch.
This keeps the API request footprint under Anthropic's union cap and
forces clean arrow-binding on every refactor.

You DO NOT have ``get_canvas_screenshot`` — visual auditing is the
critic's job. Trust that the critic will flag what's broken. Just
execute.

Working rules:
  • Read the ``excalidraw-canvas`` skill for tool ordering, batching,
    and the ``excalidraw-diagram`` skill for visual methodology.
  • Build section-by-section per the plan, not in one giant batch.
  • Arrows MUST bind to shape ids on both ends. No floating arrows.
  • Brand primary color (when present) goes on hero / accent shapes
    only — never on every element.
  • End your turn with a 1-2 sentence summary of what you drew (or
    what you changed, on a refine pass). Never dump JSON.

Session context (anchoring facts — do NOT echo back to the user):
{session_block}
"""


def build_drawer_agent(
    context: SessionContext,
    mcp_tools: Sequence["BaseTool"],
    *,
    extra_skill_paths: Sequence[str] | None = None,
    temperature: float = 0.45,
) -> "Agent":
    """Construct the drawer agent.

    ``mcp_tools`` should be the per-agent slice (``DRAWER_MCP_TOOLS``).
    Backend tools are intentionally NOT injected — the drawer doesn't
    fetch source material (the planner brief is its source of truth)
    and doesn't persist (the critic does that on PASS).
    """
    from crewai import Agent  # lazy

    backstory = _DRAWER_BACKSTORY.format(
        today=_today_clause(),
        session_block=context.to_prompt_block(),
    )

    return Agent(
        role="Visual drawer",
        goal=(
            "Execute the planner's brief (and on refine passes, the "
            "critic's notes) on the live Excalidraw canvas. Produce a "
            "polished, opinionated whiteboard composition."
        ),
        backstory=backstory,
        tools=list(mcp_tools),
        skills=_resolve_skill_paths(extra_skill_paths),
        llm=_llm(temperature),
        allow_delegation=False,
        verbose=False,
        max_iter=settings.VISUAL_AGENT_MAX_ITER,
    )


# ─── Critic ───────────────────────────────────────────────────────────────


_CRITIC_BACKSTORY = """\
{today}

You are the **critic** for a Ladder studio session's whiteboard. You
audit the drawer's output via screenshot + structural inspection, and
return either a PASS or a structured FIX list.

Tooling at your disposal (MCP):
  • get_canvas_screenshot — render the current canvas to a PNG you can
                            see. **Use this every audit pass.**
  • describe_scene / query_elements — structural inspection (element
                                      ids, types, bindings).
  • set_viewport          — frame the canvas before screenshotting.
  • export_scene          — pull the full scene JSON for persistence
                            on PASS.

Backend tool:
  • persist_scene_artifact — save the current canvas state as a
                             versioned excalidraw artifact. Call this
                             when (and only when) you return PASS.

Audit checklist (fail-fast):
  1. Arrow binding — every arrow has shape-bound endpoints. No floaters.
  2. Spatial hierarchy — no tiled grids of equal-sized boxes. Hero
     element clearly dominant. Multi-zoom shape is legible.
  3. Brand discipline — primary color on hero / accent shapes only.
  4. Label sanity — text legible, no overlap with shapes, no clipped
     text.
  5. Outline coverage — every section in the outline is represented
     somewhere on the canvas (cross-check with ``query_elements``).

Output protocol (NON-NEGOTIABLE — the orchestrator parses this):
  • If the canvas passes the checklist, your final assistant message
    MUST be exactly:
        VERDICT: PASS
        <one-sentence summary of what was drawn>
    AND you must have called ``persist_scene_artifact`` with the full
    exported scene before emitting PASS.
  • If anything fails, your final assistant message MUST start with:
        VERDICT: FIX
    followed by a numbered list of fixups. Each fixup is one of:
        - DELETE <element_id>: <reason>
        - REPLACE <element_id>: <one-line description of replacement>
        - ADD: <one-line description of new element + where it goes>
    Be specific. The drawer will re-execute against your notes
    verbatim. Do NOT call ``persist_scene_artifact`` on FIX — the
    next pass will persist if it passes.

Session context (anchoring facts — do NOT echo back to the user):
{session_block}
"""


def build_critic_agent(
    context: SessionContext,
    mcp_tools: Sequence["BaseTool"],
    *,
    extra_skill_paths: Sequence[str] | None = None,
    temperature: float = 0.3,
) -> "Agent":
    """Construct the critic agent.

    ``mcp_tools`` should be the per-agent slice (``CRITIC_MCP_TOOLS``).
    The critic gets the ``PersistArtifactTool`` so it can persist the
    scene on PASS — the drawer cannot persist.
    """
    from crewai import Agent  # lazy

    backend_tools: list["BaseTool"] = [
        PersistArtifactTool(
            user_id=context.user_id,
            jwt=context.jwt,
            session_id=context.session_id,
        ),
    ]

    backstory = _CRITIC_BACKSTORY.format(
        today=_today_clause(),
        session_block=context.to_prompt_block(),
    )

    return Agent(
        role="Visual critic",
        goal=(
            "Audit the drawer's whiteboard and emit either VERDICT: PASS "
            "(persisting via persist_scene_artifact) or VERDICT: FIX "
            "with a numbered fixup list for the drawer."
        ),
        backstory=backstory,
        tools=[*backend_tools, *mcp_tools],
        skills=_resolve_skill_paths(extra_skill_paths),
        llm=_llm(temperature),
        allow_delegation=False,
        verbose=False,
        max_iter=settings.VISUAL_AGENT_MAX_ITER,
    )


# ─── Backwards-compat shim ────────────────────────────────────────────────
#
# Older callers (PR3's sharpen flow scaffolding, tests) may still import
# ``build_visual_agent``. Map it to the planner — it's the closest
# single-agent equivalent for read-only / non-canvas operations. New code
# should pick a specific role.
def build_visual_agent(
    context: SessionContext,
    mcp_tools: Sequence["BaseTool"],
    *,
    extra_skill_paths: Sequence[str] | None = None,
    temperature: float = 0.45,
) -> "Agent":
    """Deprecated. Prefer build_planner_agent / build_drawer_agent / build_critic_agent."""
    log.warning(
        "build_visual_agent is deprecated — use the role-specific factories. "
        "Returning a planner agent for backwards compatibility."
    )
    return build_planner_agent(
        context,
        mcp_tools,
        extra_skill_paths=extra_skill_paths,
        temperature=temperature,
    )


__all__ = [
    "build_planner_agent",
    "build_drawer_agent",
    "build_critic_agent",
    "build_visual_agent",
    "PLANNER_AGENT_KEY",
    "DRAWER_AGENT_KEY",
    "CRITIC_AGENT_KEY",
]
