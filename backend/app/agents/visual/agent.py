"""Studio visual agent — single CrewAI ``Agent`` reused by both flows.

One agent definition, two flows:

  • ``BuildVisualFlow``   — one-shot kickoff: "build the diagram from
                            script + outline + brand context"
  • ``SharpenChatFlow``   — long-lived chat: refine text · screenshot-to-edit
                            · regenerate scene; multi-turn with HITL

Both flows construct the agent via :func:`build_visual_agent`, passing in
the live MCP tool list (from :func:`app.agents.visual.mcp.mcp_excalidraw_tools`)
and the loaded :class:`SessionContext`. Tool-call streaming and event
emission are owned by the flow, not by this factory.
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


# ─── Backstory ────────────────────────────────────────────────────────────

# The skills carry the heavy methodology — keep this terse. Anything written
# here multiplies token cost on every turn; anything written in a SKILL.md
# multiplies once per skill load.
_BACKSTORY_TEMPLATE = """\
{today}

You are the visual director for a Ladder studio session. You drive a live
Excalidraw whiteboard (via MCP tools) for a founder-operator who is making
a video. The script and outline already exist; your job is to translate them
into a clean, opinionated whiteboard composition — and then refine it across
the conversation as the founder reacts.

Tooling at your disposal:
  • MCP canvas tools (12 — focused build set):
      batch_create_elements, update_element, delete_element,
      query_elements, describe_scene, get_canvas_screenshot,
      align_elements, clear_canvas, set_viewport,
      snapshot_scene, restore_snapshot, export_scene.
  • get_script_and_outline — fetch the latest script + outline JSON.
  • get_brand_palette — fetch the brand color tokens for this session.
  • search_founder_knowledge — pgvector search over the founder's prior
    content. Use sparingly; only when prior framings would help.
  • persist_scene_artifact — save a versioned snapshot of the canvas.

Working rules:
  • Read the skills carefully — they aren't decoration. The methodology and
    canvas-operations skills tell you exactly how to draw and how to use the
    MCP tools efficiently.
  • Build section-by-section, not in one giant batch. Screenshot after each
    section. Fix what you see.
  • Arrows MUST bind to shape ids on both ends. No floating arrows.
  • Brand color (when present) goes on hero / accent shapes only.
  • End every successful run with set_viewport (fit-to-content) and
    persist_scene_artifact.

Session context (anchoring facts — do NOT echo back to the user):
{session_block}
"""


def _today_clause() -> str:
    today = datetime.now(tz=timezone.utc)
    return (
        f"Today's date: {today.strftime('%A, %B %d, %Y')} "
        f"(year {today.year})."
    )


# ─── Factory ──────────────────────────────────────────────────────────────


def build_visual_agent(
    context: SessionContext,
    mcp_tools: Sequence["BaseTool"],
    *,
    extra_skill_paths: Sequence[str] | None = None,
    temperature: float = 0.45,
) -> "Agent":
    """Construct the studio visual agent for a single WS session.

    Parameters
    ----------
    context :
        Result of :func:`load_session_context`. Held alongside the tools so
        they can fetch current state without re-hitting Supabase per turn.
    mcp_tools :
        Tool list from the active ``mcp_excalidraw_tools()`` context manager.
        The agent merges these with the four backend tools below.
    extra_skill_paths :
        Optional per-turn skills (e.g. user-uploaded ``skill_files``). PR1
        passes None — the dropdown wires up in PR3.
    temperature :
        Sampling temperature for the bound LLM. 0.45 matches the previous
        diagram service; bump for "regenerate scene" if outputs feel rigid.
    """
    from crewai import Agent  # lazy

    backend_tools: list["BaseTool"] = [
        ScriptOutlineTool(jwt=context.jwt, session_id=context.session_id),
        BrandPaletteTool(brand=context.brand),
        KnowledgeRetrievalTool(user_id=context.user_id),
        PersistArtifactTool(
            user_id=context.user_id,
            jwt=context.jwt,
            session_id=context.session_id,
        ),
    ]

    skill_paths: list[Path] = list(system_skill_paths())
    if extra_skill_paths:
        skill_paths.extend(Path(p) for p in extra_skill_paths)
    skill_paths_arg: list[Path] | None = skill_paths if skill_paths else None

    backstory = _BACKSTORY_TEMPLATE.format(
        today=_today_clause(),
        session_block=context.to_prompt_block(),
    )

    return Agent(
        role="Studio visual director",
        goal=(
            "Translate the founder's script + outline into a polished, "
            "opinionated Excalidraw whiteboard, refining iteratively across "
            "the conversation. Stay non-sycophantic, push back on weak "
            "framings, preserve the founder's voice."
        ),
        backstory=backstory,
        tools=[*backend_tools, *mcp_tools],
        skills=skill_paths_arg,
        llm=anthropic_llm(
            temperature=temperature,
            model=settings.VISUAL_AGENT_ANTHROPIC_MODEL,
        ),
        allow_delegation=False,
        verbose=False,
        # MCP tool loops can run hot — give the agent enough headroom for
        # batch-create + screenshot-fix cycles without running the canvas
        # off a cliff.
        max_iter=settings.VISUAL_AGENT_MAX_ITER,
    )


__all__ = ["build_visual_agent"]
