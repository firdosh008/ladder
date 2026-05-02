"""``run_visual_build`` — three-agent canvas generation for a studio session.

Public API::

    async for event in run_visual_build(context, steer_note=None):
        await ws.send_json(event)

The flow:

  1. Ensure the local Excalidraw canvas (Express + Vite) is up — boots Node
     subprocess once via :func:`app.services.excalidraw_canvas.ensure_canvas_running`.
  2. Open the MCP stdio adapter once for the whole run via
     ``mcp_excalidraw_tools(tool_names=ALL_VISUAL_MCP_TOOLS)``. Slice the
     11-tool surface per-agent so each per-agent API request stays under
     Anthropic's 16 union-typed-parameter cap.
  3. **Planner kickoff** → free-text build plan. No drawing tools.
  4. **Drawer kickoff** with the plan injected → executes on the canvas.
  5. **Critic loop** up to ``VISUAL_REFINE_MAX_ITERS`` cycles:
       a. Critic kickoff → screenshots + audits → ``VERDICT: PASS|FIX``.
       b. PASS → break. FIX → re-kickoff drawer with critic notes.
  6. Final stretch: pull ``export_scene`` (defence-in-depth re-persist if
     the critic skipped it), emit ``scene_ready`` + ``persisted`` +
     ``usage`` + ``complete``.

Every run wraps in :func:`log_usage` per HANDOFF.md §3 #8 — non-negotiable
for billing once BYOK lands. Token usage is summed across all per-Crew
``streaming.result.token_usage`` values.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator

from crewai import Crew, Process, Task

from app.agents.visual.agent import (
    CRITIC_AGENT_KEY,
    DRAWER_AGENT_KEY,
    PLANNER_AGENT_KEY,
    build_critic_agent,
    build_drawer_agent,
    build_planner_agent,
)
from app.agents.visual.context import SessionContext
from app.agents.visual.mcp import (
    ALL_VISUAL_MCP_TOOLS,
    CRITIC_MCP_TOOLS,
    DRAWER_MCP_TOOLS,
    PLANNER_MCP_TOOLS,
    mcp_excalidraw_tools,
)
from app.config import settings
from app.deps import user_client
from app.services import excalidraw_canvas

log = logging.getLogger(__name__)


# Anthropic Sonnet 4.6 list pricing (USD per 1M tokens). Same numbers used
# by the studio crew; consolidate when real billing lands.
_PRICE_IN_PER_MTOK = 3.0
_PRICE_OUT_PER_MTOK = 15.0


# ─── Task description builders ────────────────────────────────────────────


def _planner_task_description(
    context: SessionContext, steer_note: str | None
) -> str:
    base = (
        "Produce the build plan for this studio session's whiteboard. "
        "Read the script + outline + brand palette first, then output a "
        "single plain-text plan with sections: (1) DEPTH, (2) STRUCTURE, "
        "(3) SECTIONS, (4) HARD CONSTRAINTS. Be opinionated and concrete "
        "— the drawer agent will execute exactly what you write.\n\n"
        "Workflow:\n"
        "  1. ``get_script_and_outline`` — source of truth.\n"
        "  2. ``get_brand_palette``       — brand color tokens.\n"
        "  3. (Optional) ``search_founder_knowledge`` — only if a prior "
        "framing would meaningfully sharpen the plan.\n"
        "  4. (Optional) ``describe_scene`` / ``query_elements`` — only "
        "if you suspect the canvas is non-empty (e.g. a refine pass).\n"
        "  5. Write the plan. Do NOT call any drawing tools — you don't "
        "have any."
    )
    if steer_note:
        base += (
            "\n\nFOUNDER STEER NOTE — apply on top of the above:\n"
            f"  > {steer_note.strip()[:1200]}\n"
        )
    return base


def _drawer_initial_task_description(plan_brief: str) -> str:
    return (
        "Execute this plan on the live Excalidraw canvas. Build "
        "section-by-section using ``batch_create_elements``. Arrows MUST "
        "bind to shape ids on both ends. Brand color (when present) goes "
        "on hero / accent shapes only.\n\n"
        "If the canvas is non-empty and the plan calls for a fresh start, "
        "``clear_canvas`` first. Otherwise add to existing state.\n\n"
        "End your turn with a 1-2 sentence summary of what you drew. Do "
        "NOT call ``persist_scene_artifact`` — the critic does that on "
        "PASS. Do NOT screenshot — the critic audits visually.\n\n"
        "── PLAN ─────────────────────────────────────────────\n"
        f"{plan_brief.strip()}\n"
        "─────────────────────────────────────────────────────"
    )


def _drawer_refine_task_description(plan_brief: str, critic_notes: str) -> str:
    return (
        "Apply the critic's fixups to the canvas. The plan is unchanged "
        "from your prior pass — these notes are surgical edits.\n\n"
        "Edit pattern is **delete + batch_create**: for each REPLACE "
        "fixup, ``delete_element`` the old id then ``batch_create_elements`` "
        "with the new shape. For DELETE, just ``delete_element``. For ADD, "
        "``batch_create_elements`` only.\n\n"
        "End your turn with a 1-2 sentence summary of what you changed.\n\n"
        "── ORIGINAL PLAN ────────────────────────────────────\n"
        f"{plan_brief.strip()}\n"
        "── CRITIC NOTES ─────────────────────────────────────\n"
        f"{critic_notes.strip()}\n"
        "─────────────────────────────────────────────────────"
    )


def _critic_task_description() -> str:
    return (
        "Audit the canvas the drawer just produced. Run the audit "
        "checklist (arrow binding, spatial hierarchy, brand discipline, "
        "label sanity, outline coverage). Take at least one screenshot "
        "via ``get_canvas_screenshot`` — your vision is load-bearing.\n\n"
        "If everything passes, call ``persist_scene_artifact`` with the "
        "full scene JSON (use ``export_scene`` to obtain it) THEN emit:\n"
        "    VERDICT: PASS\n"
        "    <one-sentence summary>\n\n"
        "If anything fails, do NOT persist. Emit:\n"
        "    VERDICT: FIX\n"
        "    1. <DELETE|REPLACE|ADD> ...\n"
        "    2. ...\n"
        "Be specific about element ids — the drawer will execute your "
        "notes verbatim."
    )


# ─── Per-kickoff streaming + token aggregation ────────────────────────────


async def _run_kickoff(
    crew: Crew,
    agent_key: str,
    *,
    token_acc: dict[str, int],
) -> AsyncIterator[dict[str, Any]]:
    """Run one Crew kickoff and yield wire events tagged with ``agent_key``.

    All chunks from a single sequential single-task kickoff are from one
    agent, so we can tag them deterministically without inspecting the
    chunk's role (which CrewAI doesn't always populate for streamed
    text deltas).

    Aggregates token usage into ``token_acc`` after the stream completes.
    Captures the full text output and pushes it onto ``crew._final_text``
    so the orchestrator can parse it (e.g. the critic's VERDICT line).
    """
    streaming = await crew.akickoff()

    text_buffer = ""
    full_text = ""
    emitted_tool_calls: set[str] = set()
    seen_task_index = -1

    async for chunk in streaming:
        task_index = int(getattr(chunk, "task_index", 0) or 0)
        if task_index != seen_task_index:
            if seen_task_index >= 0:
                yield {
                    "type": "task_complete",
                    "agent": agent_key,
                    "preview": text_buffer.strip()[-240:],
                }
                text_buffer = ""
            seen_task_index = task_index

        chunk_type = getattr(chunk, "chunk_type", None)
        chunk_type_name = (
            getattr(chunk_type, "value", chunk_type)
            if chunk_type is not None
            else "text"
        )

        if chunk_type_name == "tool_call":
            tc = getattr(chunk, "tool_call", None)
            if tc is None:
                continue
            tool_id = str(
                getattr(tc, "tool_id", "")
                or f"{agent_key}:{getattr(tc, 'index', 0)}"
            )
            if tool_id in emitted_tool_calls:
                continue
            emitted_tool_calls.add(tool_id)
            yield {
                "type": "tool_call",
                "agent": agent_key,
                "tool": getattr(tc, "tool_name", None) or "unknown",
                "arguments": getattr(tc, "arguments", "") or "",
            }
            continue

        content = getattr(chunk, "content", "") or ""
        if content:
            text_buffer = (text_buffer + content)[-4000:]
            full_text += content
            yield {
                "type": "text_delta",
                "agent": agent_key,
                "content": content,
            }

    if seen_task_index >= 0:
        yield {
            "type": "task_complete",
            "agent": agent_key,
            "preview": text_buffer.strip()[-240:],
        }

    # Aggregate token usage from this kickoff's CrewOutput.
    crew_result = getattr(streaming, "result", None)
    metrics = getattr(crew_result, "token_usage", None) if crew_result else None
    if metrics is not None:
        token_acc["input"] += int(getattr(metrics, "prompt_tokens", 0) or 0)
        token_acc["output"] += int(getattr(metrics, "completion_tokens", 0) or 0)

    # Stash full text on the crew for the orchestrator. ``Crew`` is a
    # Pydantic model with arbitrary attribute assignment allowed; we use
    # a private-ish name to avoid colliding with framework fields.
    try:
        setattr(crew, "_ladder_final_text", full_text)
    except Exception:
        # If pydantic validation rejects it, fall back to a side channel.
        pass


# ─── VERDICT parsing ──────────────────────────────────────────────────────


def _parse_critic_verdict(text: str) -> tuple[str, str]:
    """Return ``(verdict, notes)``. ``verdict`` is ``"PASS"`` or ``"FIX"``.

    Defaults to ``"FIX"`` with the full text as notes if no verdict line
    is found — defensive: a critic that didn't follow the protocol means
    we should not silently persist a possibly-broken canvas.
    """
    if not text:
        return "FIX", "(critic produced no output)"
    # Look for the last VERDICT line — the critic may include the format
    # template earlier in its scratchpad.
    lines = text.splitlines()
    verdict_idx = -1
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip().upper().startswith("VERDICT:"):
            verdict_idx = i
            break
    if verdict_idx < 0:
        return "FIX", text.strip()[-3000:]
    verdict_line = lines[verdict_idx].strip().upper()
    if "PASS" in verdict_line:
        return "PASS", "\n".join(lines[verdict_idx:]).strip()
    # Anything else (FIX, FAIL, etc.) → take everything from the verdict
    # line forward as the notes block.
    return "FIX", "\n".join(lines[verdict_idx:]).strip()


# ─── MCP scene export + persistence (defence-in-depth) ────────────────────


async def _export_scene_via_mcp(mcp_tools: list[Any]) -> dict[str, Any] | None:
    """Call the MCP ``export_scene`` tool and return its parsed JSON payload."""
    candidates = ("export_scene", "get_scene", "describe_scene")
    by_name = {getattr(t, "name", "?"): t for t in mcp_tools}
    for name in candidates:
        tool = by_name.get(name)
        if tool is None:
            continue
        try:
            runner = getattr(tool, "run", None) or getattr(tool, "_run", None)
            if runner is None:
                continue
            raw = await asyncio.to_thread(runner)
        except Exception as e:
            log.warning("MCP %s failed: %s", name, e)
            continue
        return _coerce_scene_json(raw)
    log.warning("no MCP scene-export tool found; returning empty scene")
    return None


def _coerce_scene_json(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        if "elements" in raw:
            return raw
        for v in raw.values():
            if isinstance(v, dict) and "elements" in v:
                return v
            if isinstance(v, str):
                parsed = _try_parse_json(v)
                if parsed and "elements" in parsed:
                    return parsed
        return None
    if isinstance(raw, str):
        parsed = _try_parse_json(raw)
        if parsed and "elements" in parsed:
            return parsed
        return None
    return None


def _try_parse_json(s: str) -> dict[str, Any] | None:
    try:
        out = json.loads(s)
        return out if isinstance(out, dict) else None
    except (TypeError, ValueError):
        return None


async def _next_artifact_version(
    jwt: str, session_id: str, artifact_type: str
) -> int:
    client = await user_client(jwt)
    resp = (
        await client.from_("artifacts")
        .select("version")
        .eq("session_id", session_id)
        .eq("type", artifact_type)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    if resp.data:
        return int(resp.data[0]["version"]) + 1
    return 1


async def _persist_scene(
    user_id: str, jwt: str, session_id: str, scene: dict[str, Any]
) -> str:
    client = await user_client(jwt)
    version = await _next_artifact_version(jwt, session_id, "excalidraw")
    el_count = len(scene.get("elements") or [])
    summary = f"Visual agent diagram — {el_count} elements (v{version})."
    inserted = (
        await client.from_("artifacts")
        .insert(
            {
                "user_id": user_id,
                "session_id": session_id,
                "type": "excalidraw",
                "version": version,
                "content_text": summary,
                "content_json": scene,
            }
        )
        .execute()
    )
    if not inserted.data:
        raise RuntimeError("excalidraw artifact insert returned no row")
    return str(inserted.data[0]["id"])


async def _ensure_canvas_ready() -> None:
    vendor: Path | None = None
    raw = settings.EXCALIDRAW_VENDOR_ROOT.strip()
    if raw:
        vendor = Path(raw)
    await excalidraw_canvas.ensure_canvas_running(
        vendor=vendor,
        http_base=settings.EXCALIDRAW_HTTP_URL,
        autostart=settings.EXCALIDRAW_CANVAS_AUTOSTART,
    )


# ─── Crew construction helpers ────────────────────────────────────────────


def _make_crew(agent, task: Task) -> Crew:
    return Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        stream=True,
        verbose=False,
    )


def _slice_mcp(mcp_tools: list[Any], names: frozenset[str]) -> list[Any]:
    return [t for t in mcp_tools if getattr(t, "name", "") in names]


def _final_text(crew: Crew) -> str:
    return str(getattr(crew, "_ladder_final_text", "") or "")


# ─── Public API ───────────────────────────────────────────────────────────


async def run_visual_build(
    context: SessionContext,
    *,
    steer_note: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream wire events for one visual build, finalising with persistence.

    Event types emitted (matches HANDOFF.md §11):
      agent_start    — visual_planner / visual_drawer / visual_critic
                       kickoff
      tool_call      — every MCP / backend tool an agent invokes
      text_delta     — narrative reasoning between tool calls
      task_complete  — a per-agent kickoff finished
      scene_ready    — final scene JSON pulled from the canvas
      persisted      — { scene_artifact_id }
      usage          — { token_usage } (summed across all kickoffs)
      complete       — { cost_usd }
      error          — terminal failure message
    """
    from app.services.usage import log_usage

    function_name = "visual_build_crew"
    model_name = settings.VISUAL_AGENT_ANTHROPIC_MODEL
    refine_cap = settings.VISUAL_REFINE_MAX_ITERS
    token_acc = {"input": 0, "output": 0}

    async with log_usage(
        user_id=context.user_id,
        function_name=function_name,
        model=model_name,
        provider="anthropic",
    ) as entry:
        try:
            await _ensure_canvas_ready()
        except Exception as e:
            log.exception("excalidraw canvas failed to boot")
            yield {"type": "error", "message": f"canvas boot failed: {e}"}
            return

        try:
            with mcp_excalidraw_tools(
                tool_names=ALL_VISUAL_MCP_TOOLS
            ) as mcp_tools:
                planner_mcp = _slice_mcp(mcp_tools, PLANNER_MCP_TOOLS)
                drawer_mcp = _slice_mcp(mcp_tools, DRAWER_MCP_TOOLS)
                critic_mcp = _slice_mcp(mcp_tools, CRITIC_MCP_TOOLS)

                # ── Planner ──────────────────────────────────────────
                yield {"type": "agent_start", "agent": PLANNER_AGENT_KEY}
                planner = build_planner_agent(context, planner_mcp)
                planner_task = Task(
                    description=_planner_task_description(context, steer_note),
                    expected_output=(
                        "A plain-text build plan with DEPTH / STRUCTURE / "
                        "SECTIONS / HARD CONSTRAINTS sections. No JSON."
                    ),
                    agent=planner,
                )
                planner_crew = _make_crew(planner, planner_task)
                async for ev in _run_kickoff(
                    planner_crew, PLANNER_AGENT_KEY, token_acc=token_acc
                ):
                    yield ev
                plan_brief = _final_text(planner_crew)
                if not plan_brief.strip():
                    yield {
                        "type": "error",
                        "message": "planner produced empty plan — aborting",
                    }
                    return

                # ── Drawer (initial pass) ────────────────────────────
                yield {"type": "agent_start", "agent": DRAWER_AGENT_KEY}
                drawer = build_drawer_agent(context, drawer_mcp)
                drawer_task = Task(
                    description=_drawer_initial_task_description(plan_brief),
                    expected_output=(
                        "A 1-2 sentence summary of what was drawn on the "
                        "canvas. Never a JSON dump."
                    ),
                    agent=drawer,
                )
                drawer_crew = _make_crew(drawer, drawer_task)
                async for ev in _run_kickoff(
                    drawer_crew, DRAWER_AGENT_KEY, token_acc=token_acc
                ):
                    yield ev

                # ── Critic ↔ Drawer refine loop ──────────────────────
                verdict = "FIX"
                refine_iter = 0
                while refine_iter < refine_cap:
                    yield {"type": "agent_start", "agent": CRITIC_AGENT_KEY}
                    critic = build_critic_agent(context, critic_mcp)
                    critic_task = Task(
                        description=_critic_task_description(),
                        expected_output=(
                            "Either ``VERDICT: PASS`` + one-line summary "
                            "(after persisting), or ``VERDICT: FIX`` + "
                            "numbered fixup list."
                        ),
                        agent=critic,
                    )
                    critic_crew = _make_crew(critic, critic_task)
                    async for ev in _run_kickoff(
                        critic_crew, CRITIC_AGENT_KEY, token_acc=token_acc
                    ):
                        yield ev
                    critic_text = _final_text(critic_crew)
                    verdict, notes = _parse_critic_verdict(critic_text)
                    if verdict == "PASS":
                        break
                    refine_iter += 1
                    if refine_iter >= refine_cap:
                        # Last iteration was a FIX; we're out of budget.
                        log.info(
                            "visual refine cap reached (%d) — shipping with "
                            "outstanding critic notes",
                            refine_cap,
                        )
                        break
                    # Re-kickoff the drawer with the critic's notes. Reuse
                    # the agent + tools but a fresh Task + Crew.
                    yield {"type": "agent_start", "agent": DRAWER_AGENT_KEY}
                    drawer = build_drawer_agent(context, drawer_mcp)
                    drawer_task = Task(
                        description=_drawer_refine_task_description(
                            plan_brief, notes
                        ),
                        expected_output=(
                            "A 1-2 sentence summary of what was changed. "
                            "Never a JSON dump."
                        ),
                        agent=drawer,
                    )
                    drawer_crew = _make_crew(drawer, drawer_task)
                    async for ev in _run_kickoff(
                        drawer_crew, DRAWER_AGENT_KEY, token_acc=token_acc
                    ):
                        yield ev

                # ── Final stretch ────────────────────────────────────
                final_scene = await _export_scene_via_mcp(list(mcp_tools))
                if final_scene is None:
                    yield {
                        "type": "error",
                        "message": (
                            "agents finished but no scene was produced "
                            "on the canvas."
                        ),
                    }
                    return

                yield {"type": "scene_ready", "scene": final_scene}

                # Defence-in-depth re-persist: the critic on PASS already
                # called persist_scene_artifact, but if we exited the loop
                # without a PASS (refine cap) or the critic skipped the
                # tool, persist now. Versioning is monotonic so a duplicate
                # write is harmless.
                try:
                    artifact_id = await _persist_scene(
                        context.user_id,
                        context.jwt,
                        context.session_id,
                        final_scene,
                    )
                    yield {"type": "persisted", "scene_artifact_id": artifact_id}
                except Exception as e:
                    log.exception("persist excalidraw artifact failed")
                    yield {
                        "type": "error",
                        "message": f"persist failed: {e}",
                    }
                    return

                # Roll up token usage from all per-Crew streamings.
                entry.input_tokens = token_acc["input"]
                entry.output_tokens = token_acc["output"]
                entry.cost_usd = round(
                    (entry.input_tokens / 1_000_000) * _PRICE_IN_PER_MTOK
                    + (entry.output_tokens / 1_000_000) * _PRICE_OUT_PER_MTOK,
                    6,
                )

                yield {
                    "type": "usage",
                    "token_usage": {
                        "input": entry.input_tokens,
                        "output": entry.output_tokens,
                        "cost_usd": entry.cost_usd,
                    },
                }
                yield {"type": "complete", "cost_usd": entry.cost_usd}
        except RuntimeError as e:
            log.warning("MCP adapter setup failed: %s", e)
            yield {"type": "error", "message": str(e)}
            return
        except Exception as e:
            log.exception("visual build failed unexpectedly")
            yield {"type": "error", "message": f"visual build failed: {e}"}


__all__ = ["run_visual_build"]
