"""``BuildVisualFlow`` — one-shot canvas generation for a studio session.

Public API::

    async for event in run_visual_build(context, steer_note=None):
        await ws.send_json(event)

The flow:

  1. Ensure the local Excalidraw canvas (Express + Vite) is up — boots Node
     subprocess once via :func:`app.services.excalidraw_canvas.ensure_canvas_running`.
  2. Open the MCP stdio adapter (``mcp_excalidraw_tools()``) for the duration
     of this run; the agent gets the full 26-tool MCP surface plus our four
     backend tools.
  3. Build a single CrewAI ``Agent`` + ``Task`` + ``Crew(stream=True)`` and
     stream chunks → wire events (``agent_start`` / ``tool_call`` /
     ``text_delta`` / ``task_complete``).
  4. Pull the final canvas state from MCP (``export_scene``) and persist it
     as a versioned ``excalidraw`` artifact via the user-scoped client (RLS
     enforced — never service-role here).
  5. Emit ``scene_ready`` + ``persisted`` + ``complete`` (matches the event
     protocol in HANDOFF.md §11).

Every run wraps in :func:`log_usage` per HANDOFF.md §3 #8 — non-negotiable
for billing once BYOK lands.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator

from crewai import Agent, Crew, Process, Task

from app.agents.visual.agent import build_visual_agent
from app.agents.visual.context import SessionContext
from app.agents.visual.mcp import mcp_excalidraw_tools
from app.config import settings
from app.deps import user_client
from app.services import excalidraw_canvas

log = logging.getLogger(__name__)


# Anthropic Sonnet 4.6 list pricing (USD per 1M tokens).
# Same numbers used by the studio crew; consolidate when real billing lands.
_PRICE_IN_PER_MTOK = 3.0
_PRICE_OUT_PER_MTOK = 15.0


_AGENT_KEY = "visual_director"


def _agent_key(role: str | None) -> str | None:
    """Map CrewAI's role label back to a stable wire key.

    The visual flow only has one agent so anything non-empty maps to
    ``visual_director``. Mirrors the research/studio crews' naming pattern
    so the frontend's ``AGENT_LABELS`` map can pick it up unchanged.
    """
    if not role:
        return None
    return _AGENT_KEY


def _build_task_description(context: SessionContext, steer_note: str | None) -> str:
    """Compose the single Task prompt the agent runs against.

    The methodology lives in the skills (verbatim-injected by CrewAI). This
    prompt is just the *job for this turn* — keep it terse so we don't fight
    the skills for context budget.
    """
    base = (
        "Build a polished, opinionated Excalidraw whiteboard for this "
        "studio session. Use the live MCP canvas tools — read the "
        "`excalidraw-canvas` skill for tool ordering and the "
        "`excalidraw-diagram` skill for visual methodology before you "
        "start.\n\n"
        "Workflow (NON-NEGOTIABLE):\n"
        "  1. `clear_canvas` only if the canvas is non-empty AND you are "
        "starting fresh.\n"
        "  2. `get_script_and_outline` to read the current source of "
        "truth. Do NOT trust the system-prompt summary alone — the user "
        "may have edited the outline since this run started.\n"
        "  3. `get_brand_palette` to read the brand color tokens.\n"
        "  4. Plan the composition mentally: depth assessment, pattern per "
        "section, summary→sections→detail multi-zoom shape.\n"
        "  5. Build section-by-section with `batch_create_elements`. After "
        "each section, `set_viewport` (fit-to-content) and "
        "`get_canvas_screenshot`. Audit the screenshot. Fix what you see.\n"
        "  6. When you are confident the composition is clean, "
        "`describe_scene` once for a final structural check.\n"
        "  7. Call `persist_scene_artifact` with the FULL exported scene "
        "(use the MCP `export_scene` tool to get it). Pass a one-line note "
        "summarising the diagram.\n\n"
        "Hard rules:\n"
        "  • Arrows MUST bind to shape ids on both ends. No floating "
        "arrows.\n"
        "  • No tiled grids of equal-sized boxes. Organic spatial "
        "hierarchy only.\n"
        "  • Brand primary color (when present) goes on hero / accent "
        "shapes, never on every element.\n"
        "  • Do NOT regenerate from scratch on every retry — surgical "
        "edits via `update_element` / `delete_element` beat full "
        "rebuilds.\n"
    )

    if steer_note:
        base += (
            "\nFOUNDER STEER NOTE — apply on top of the above:\n"
            f"  > {steer_note.strip()[:1200]}\n"
        )

    return base


async def _export_scene_via_mcp(mcp_tools: list[Any]) -> dict[str, Any] | None:
    """Call the MCP ``export_scene`` tool and return its parsed JSON payload.

    The MCP server's ``export_scene`` returns the full Excalidraw envelope —
    elements + appState + files — which is exactly what we persist as the
    next artifact version. Robust against tool naming drift across upstream
    versions: also accepts ``get_scene`` / ``describe_scene`` if available.
    """
    candidates = ("export_scene", "get_scene", "describe_scene")
    by_name = {getattr(t, "name", "?"): t for t in mcp_tools}
    for name in candidates:
        tool = by_name.get(name)
        if tool is None:
            continue
        try:
            # CrewAI BaseTool wraps `_run` — use the public `run` if exposed,
            # else fall back to `_run` so we work across versions.
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
    """Best-effort parse of an MCP tool result into a scene dict.

    MCP tools typically return a string (often JSON, sometimes wrapped in
    a small envelope). We accept dicts as-is, parse strings, and tolerate
    upstream wrapping like ``{"content": "<json>"}``.
    """
    if isinstance(raw, dict):
        if "elements" in raw:
            return raw
        # Some MCP wrappers nest the payload — pull the first dict child
        # that looks like a scene.
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
    user_id: str,
    jwt: str,
    session_id: str,
    scene: dict[str, Any],
) -> str:
    """Insert a versioned ``excalidraw`` artifact. Returns the artifact id."""
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
    """Lazy-boot the Express canvas if FastAPI lifespan failed to start it.

    Production path is the lifespan in ``main.py``; this is the safety net
    when the dev server was started without the canvas (e.g. Node missing
    on first try) and the user kicks off a build later.
    """
    vendor: Path | None = None
    raw = settings.EXCALIDRAW_VENDOR_ROOT.strip()
    if raw:
        vendor = Path(raw)
    await excalidraw_canvas.ensure_canvas_running(
        vendor=vendor,
        http_base=settings.EXCALIDRAW_HTTP_URL,
        autostart=settings.EXCALIDRAW_CANVAS_AUTOSTART,
    )


# ─── Public API ───────────────────────────────────────────────────────────


async def run_visual_build(
    context: SessionContext,
    *,
    steer_note: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream wire events for one visual build, finalising with persistence.

    Event types emitted (matches HANDOFF.md §11):
      agent_start    — visual_director kickoff
      tool_call      — every MCP / backend tool the agent invokes
      text_delta     — narrative reasoning between tool calls
      task_complete  — the single build task finished
      scene_ready    — final scene JSON pulled from the canvas
      persisted      — { scene_artifact_id }
      usage          — { token_usage }
      complete       — { cost_usd }
      error          — terminal failure message
    """
    # Lazy import — avoid forcing usage_log + service_client at module import
    # time when this module is read for type hints elsewhere.
    from app.services.usage import log_usage

    # Cap the model name so the usage_log row reflects what the visual
    # agent actually spoke to, not the global default.
    function_name = "visual_build_crew"
    model_name = settings.VISUAL_AGENT_ANTHROPIC_MODEL

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
            with mcp_excalidraw_tools() as mcp_tools:
                yield {"type": "agent_start", "agent": _AGENT_KEY}

                async for event in _stream_build_crew(
                    context, mcp_tools, steer_note, entry
                ):
                    yield event
        except RuntimeError as e:
            # Most common cause: vendored mcp_excalidraw not built yet.
            log.warning("MCP adapter setup failed: %s", e)
            yield {"type": "error", "message": str(e)}
            return
        except Exception as e:
            log.exception("visual build failed unexpectedly")
            yield {"type": "error", "message": f"visual build failed: {e}"}


async def _stream_build_crew(
    context: SessionContext,
    mcp_tools: list[Any],
    steer_note: str | None,
    entry: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Inner generator — kicks off the crew and yields wire events."""
    agent: Agent = build_visual_agent(context, mcp_tools)

    task = Task(
        description=_build_task_description(context, steer_note),
        expected_output=(
            "A finished Excalidraw whiteboard composition on the live "
            "canvas (verified via at least one screenshot loop), persisted "
            "as a versioned excalidraw artifact via the persist tool. "
            "Final assistant message is a 1-2 sentence summary of what was "
            "drawn — never a JSON dump."
        ),
        agent=agent,
    )

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        stream=True,
        verbose=False,
    )

    streaming = await crew.akickoff()

    current_task_index = -1
    text_buffer = ""
    emitted_tool_calls: set[str] = set()

    async for chunk in streaming:
        agent_role = getattr(chunk, "agent_role", "") or ""
        agent_key = _agent_key(agent_role) or _AGENT_KEY
        task_index = int(getattr(chunk, "task_index", 0) or 0)

        if task_index != current_task_index:
            if current_task_index >= 0:
                yield {
                    "type": "task_complete",
                    "agent": _AGENT_KEY,
                    "preview": text_buffer.strip()[-240:],
                }
                text_buffer = ""
            current_task_index = task_index

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
            yield {
                "type": "text_delta",
                "agent": agent_key,
                "content": content,
            }

    if current_task_index >= 0:
        yield {
            "type": "task_complete",
            "agent": _AGENT_KEY,
            "preview": text_buffer.strip()[-240:],
        }

    # Pull the final canvas state. The agent should have already called
    # persist_scene_artifact, but we still emit `scene_ready` for the UI's
    # live preview (and re-persist if the agent skipped it — defence in
    # depth, never silently drop a successful build).
    final_scene = await _export_scene_via_mcp(list(mcp_tools))
    if final_scene is None:
        # The canvas server is up; agent just never produced anything.
        yield {
            "type": "error",
            "message": "agent finished but no scene was produced on the canvas.",
        }
        return

    yield {"type": "scene_ready", "scene": final_scene}

    # Best-effort: re-persist if the agent didn't (idempotent — versioning
    # increments). Failure to persist is fatal for the run; the UI can't
    # hydrate without an artifact.
    try:
        artifact_id = await _persist_scene(
            context.user_id, context.jwt, context.session_id, final_scene
        )
        yield {"type": "persisted", "scene_artifact_id": artifact_id}
    except Exception as e:
        log.exception("persist excalidraw artifact failed")
        yield {"type": "error", "message": f"persist failed: {e}"}
        return

    # Token usage: CrewAI's streaming.result has token_usage when the run
    # completes cleanly. Pull it for the usage_log row.
    crew_result = getattr(streaming, "result", None)
    metrics = getattr(crew_result, "token_usage", None) if crew_result else None
    if metrics is not None:
        entry.input_tokens = int(getattr(metrics, "prompt_tokens", 0) or 0)
        entry.output_tokens = int(getattr(metrics, "completion_tokens", 0) or 0)
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


__all__ = ["run_visual_build"]
