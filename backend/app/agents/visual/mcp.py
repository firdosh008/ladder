"""MCP adapter wiring for the vendored ``mcp_excalidraw`` server.

CrewAI's ``MCPServerAdapter`` (from ``crewai_tools``) speaks all three MCP
transports. We use stdio: spawn ``node dist/index.js`` from the vendored
checkout at ``backend/vendor/mcp_excalidraw``. That MCP server in turn talks
to the running canvas Express server via ``EXPRESS_SERVER_URL`` — we keep
the canvas alive separately via ``app.services.excalidraw_canvas``.

Architecture, top-down::

    StudioVisualAgent (CrewAI Agent)
        └─ tools = [*MCP stdio tools, …]
            └─ MCP server (Node stdio)
                └─ HTTP → http://127.0.0.1:3000  (Express canvas)
                    └─ WebSocket → browser viewer (real-time sync)

For local dev we spawn one canvas + one MCP adapter per WS connection, per
the architecture decision in 2026-05-02 cut-over plan (see HANDOFF.md §5).
Multi-tenant canvas isolation is an open item for hosted; not in scope here.

Schema-sanitisation note (added 2026-05-02 after first MCP boot attempt):
the upstream ``mcp_excalidraw`` server declares ``fontFamily`` (and may
declare other fields in future) with multi-type JSON Schema —
``type: ["string", "number"]``. CrewAI's strict
``crewai.utilities.pydantic_schema_utils.create_model_from_schema`` rejects
that with ``Unsupported JSON schema type: ['string', 'number']``. We bypass
``crewai_tools.MCPServerAdapter`` and use ``mcpadapt.MCPAdapt`` directly
with a tiny ``_SanitisingCrewAIAdapter`` subclass that flattens multi-type
properties to a single type before they reach CrewAI's converter. This is
preferable to patching the vendor checkout because it survives upstream
re-clones / re-builds and silently absorbs any future multi-type fields.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from app.config import settings

if TYPE_CHECKING:
    # Heavy imports — keep them lazy so importing this module doesn't pull
    # the full CrewAI tool stack just for type-checking.
    from crewai.tools import BaseTool

log = logging.getLogger(__name__)


# ─── Build-tool whitelist + per-agent slices ──────────────────────────────
#
# Anthropic caps "strict" tools at 20 per request AND union-typed parameters
# at 16 per request. CrewAI's Anthropic provider sends every tool we expose
# as strict and CrewAI's pydantic round-trip wraps every optional field in
# ``anyOf: [<type>, {type: null}]``. The vendored MCP server ships 26 tools
# with many optional fields each; even after trimming to a 12-tool build
# set we hit ~45 unions and bust the cap.
#
# Strict-off is patched globally in ``app/services/llm.py`` (covers the
# 20-tool cap). The 16-union cap is solved here by **splitting the visual
# agent into three role-scoped agents** and slicing the MCP tool list per
# agent so each per-agent API request stays under 16 unions naturally —
# no schema modification, no null-strip patches.
#
# Per-tool union counts (verified 2026-05-02 against vendor's schema):
#   batch_create_elements .... 16    (one per optional field per item)
#   query_elements ........... 7
#   set_viewport ............. 5
#   delete_element ........... 0
#   clear_canvas ............. 0
#   align_elements ........... 0
#   describe_scene ........... 0
#   get_canvas_screenshot .... 1
#   snapshot_scene / restore . 0 / 0
#   export_scene ............. 1
#
# ``update_element`` (14 unions) is **dropped** — the edit pattern is
# delete-and-recreate. Excalidraw elements are cheap; the critic returns
# a list of element ids to delete plus a list of new elements, and the
# drawer applies it via ``delete_element`` + ``batch_create_elements``.
# Sticking ``update_element`` on a 4th agent doesn't help: it'd still
# need ``query_elements`` (7) to know which id to target → 14+7 = 21,
# back over the cap. See HANDOFF.md §5 "Three-agent split".
#
# The dropped MCP tools (beyond ``update_element``) fall into these
# buckets, same as the prior single-agent build set:
#
#   • Methodology duplicates of skills we already inject — e.g.
#     ``read_diagram_guide`` (the ``excalidraw-diagram`` skill teaches the
#     same thing, verbatim).
#   • Inputs from outside the agent's purview — ``import_scene`` /
#     ``create_from_mermaid``.
#   • Niche layout helpers the agent can replicate with primitives —
#     ``group_elements`` / ``lock_elements`` / ``distribute_elements`` /
#     ``duplicate_elements``.
#   • Redundant inspectors — ``get_element`` / ``get_resource``.
#   • Output paths we don't use — ``export_to_image`` /
#     ``export_to_excalidraw_url``.
#   • ``create_element`` — the ``excalidraw-canvas`` skill directs the
#     agent to ``batch_create_elements`` instead.
#
# PR3's SharpenChatFlow may want a slightly different set; parametrise then.

#: Planner reads source material + (when canvas is non-empty) inspects
#: existing state. Outputs a free-text plan. No drawing tools. ~7 unions.
PLANNER_MCP_TOOLS: frozenset[str] = frozenset(
    {
        "describe_scene",
        "query_elements",
    }
)

#: Drawer executes the plan (and on refine passes, the critic's notes)
#: on the canvas. ``batch_create_elements`` alone is 16 unions, so the
#: rest of the drawer's tools must contribute 0 unions — they do.
DRAWER_MCP_TOOLS: frozenset[str] = frozenset(
    {
        "batch_create_elements",
        "delete_element",
        "clear_canvas",
        "align_elements",
        "snapshot_scene",
        "restore_snapshot",
    }
)

#: Critic screenshots the canvas, audits, returns VERDICT: PASS|FIX +
#: structured notes for the drawer. Sonnet 4.6 vision is load-bearing.
#: Includes ``export_scene`` so the critic can persist on PASS.
CRITIC_MCP_TOOLS: frozenset[str] = frozenset(
    {
        "get_canvas_screenshot",
        "describe_scene",
        "query_elements",
        "set_viewport",
        "export_scene",
    }
)

#: Union of all MCP tools used across the three agents — passed to the
#: ``mcp_excalidraw_tools()`` cm so we open ONE Node subprocess for the
#: whole run and slice the tool list per-agent.
ALL_VISUAL_MCP_TOOLS: frozenset[str] = (
    PLANNER_MCP_TOOLS | DRAWER_MCP_TOOLS | CRITIC_MCP_TOOLS
)

# Backwards-compat: some callers (and old tests) may still reference the
# pre-split name. Point both at the union.
_BUILD_TOOL_NAMES = ALL_VISUAL_MCP_TOOLS


def _vendor_root() -> Path:
    """Path to the cloned ``yctimlin/mcp_excalidraw`` checkout."""
    raw = settings.EXCALIDRAW_VENDOR_ROOT.strip()
    if raw:
        return Path(raw)
    # Default: backend/vendor/mcp_excalidraw (sibling of app/).
    return Path(__file__).resolve().parents[3] / "vendor" / "mcp_excalidraw"


def _mcp_entry_path() -> Path:
    """Absolute path to the MCP stdio entrypoint inside the vendor checkout.

    The yctimlin bundle exposes two entry points after ``npm run build``:
      • ``dist/server.js`` — Express + Vite canvas (port 3000); managed by
        ``services/excalidraw_canvas.py``.
      • ``dist/index.js``  — MCP stdio adapter; speaks to the canvas via
        ``EXPRESS_SERVER_URL``. THIS is what we spawn here.

    Override via ``MCP_EXCALIDRAW_ENTRY`` env (relative to the vendor root)
    if upstream renames the file.
    """
    rel = settings.MCP_EXCALIDRAW_ENTRY.strip() or "dist/index.js"
    return _vendor_root() / rel


def _stdio_params():  # type: ignore[no-untyped-def]
    """Build ``StdioServerParameters`` for the MCP adapter.

    Lazy import so the module is cheap to load when CrewAI tools aren't in
    use yet (e.g. running scripts that just need the rest of the app).
    """
    from mcp import StdioServerParameters  # type: ignore[import-not-found]

    entry = _mcp_entry_path()
    if not entry.is_file():
        raise RuntimeError(
            f"mcp_excalidraw stdio entry not found at {entry}. "
            "Clone the upstream repo into backend/vendor/mcp_excalidraw and "
            "run `npm ci && npm run build` before starting the agent."
        )

    # The MCP server reads EXPRESS_SERVER_URL to find the running canvas.
    # We always point at our managed canvas (settings.EXCALIDRAW_HTTP_URL).
    env = {
        **os.environ,
        "EXPRESS_SERVER_URL": settings.EXCALIDRAW_HTTP_URL,
    }
    return StdioServerParameters(
        command="node",
        args=[str(entry)],
        env=env,
    )


def _wrap_with_null_strip(func):
    """Return a wrapper around the MCP ``func`` that scrubs nulls first.

    mcpadapt invokes ``func(filtered_kwargs)`` with a single dict argument
    after its own (shallow) None-filter. We deep-clean that dict here so
    ``elements[i].text = null`` etc. never reaches the wire.

    Logs a single warning per call when scrubbing actually removed
    something so we can spot LLMs that are leaning hard on nulls — most
    of the time the agent should converge on omitting optional fields
    once it sees a few successful tool calls.
    """
    import functools

    @functools.wraps(func)
    def _scrubbed(arguments: dict | None = None, *args, **kwargs):
        if isinstance(arguments, dict):
            cleaned = _strip_nulls_recursive(arguments)
            if log.isEnabledFor(logging.DEBUG):
                # Cheap-ish: only count keys removed at top level for the
                # debug line. The full recursion happened either way.
                removed_top = [
                    k for k, v in arguments.items() if v is None
                ]
                if removed_top:
                    log.debug(
                        "mcp tool args: stripped null keys at top level: %s",
                        removed_top,
                    )
            return func(cleaned, *args, **kwargs)
        return func(arguments, *args, **kwargs)

    return _scrubbed


def _strip_nulls_recursive(value: Any) -> Any:
    """Drop dict keys whose values are ``None``, recursively into lists.

    Why we need this: CrewAI's pydantic round-trip on tool args turns every
    optional field into ``anyOf: [<type>, {type: null}]``. The LLM sees that
    the schema accepts null and obligingly fills every optional field with
    literal ``null``. The MCP server's Zod validators (in
    ``vendor/mcp_excalidraw/src/index.ts``) do NOT accept null for those
    fields and reject the entire call.

    ``mcpadapt`` ships a top-level filter (``crewai_adapter.py:_run``) that
    drops None values for properties whose *upstream* schema doesn't allow
    null, but it only inspects top-level kwargs — for
    ``batch_create_elements`` the args look like
    ``{"elements": [{"text": null, "fontSize": null, ...}]}``. The
    top-level ``elements`` key is a non-null list, so the filter waves it
    through with all the nested nulls intact, and the MCP server promptly
    rejects the call. We recurse to handle that.

    Side effects: dict-typed values are returned with None-valued keys
    removed (not present in output). List-typed values keep their length —
    we recurse into items but don't drop list slots. Scalars pass through.
    """
    if isinstance(value, dict):
        return {
            k: _strip_nulls_recursive(v)
            for k, v in value.items()
            if v is not None
        }
    if isinstance(value, list):
        # Don't drop None-valued list slots — that would shift indices and
        # break things like ``points`` (list of [x, y] pairs). Just recurse
        # into dict items.
        return [_strip_nulls_recursive(v) for v in value]
    return value


def _flatten_multitype_schema(schema: Any) -> Any:
    """Recursively rewrite ``type: [<one>, <two>, ...]`` to a single string type.

    JSON Schema permits a list-valued ``type`` to declare multiple acceptable
    primitive types for a single property. ``mcpadapt`` understands it,
    ``crewai`` does not (raises ``Unsupported JSON schema type: [...]`` from
    ``pydantic_schema_utils._json_schema_to_pydantic_type``). For our agent
    use-case we just need *something* the LLM can pass — picking the first
    non-null type preserves the most permissive interpretation while
    satisfying CrewAI. The MCP server's runtime accepts both forms via its
    own ``normalizeFontFamily()`` so narrowing here doesn't lose behaviour.

    Operates in-place on a deep-copied schema and returns the same object so
    callers can chain. Safe to call on any value (no-op for non-dict / list).
    """
    if isinstance(schema, dict):
        t = schema.get("type")
        if isinstance(t, list):
            primary: str | None = next(
                (x for x in t if isinstance(x, str) and x != "null"),
                None,
            )
            if primary is not None:
                schema["type"] = primary
            else:
                # All-null or empty — drop the key so CrewAI infers Any.
                schema.pop("type", None)
        for v in schema.values():
            _flatten_multitype_schema(v)
    elif isinstance(schema, list):
        for item in schema:
            _flatten_multitype_schema(item)
    return schema


@contextmanager
def mcp_excalidraw_tools(
    *,
    tool_names: frozenset[str] | set[str] | None = None,
) -> Iterator[list["BaseTool"]]:
    """Context manager yielding the live MCP tool list.

    Spawns the Node stdio server on entry, tears it down on exit. The yielded
    tools are CrewAI ``BaseTool`` instances bound to MCP tool names like
    ``batch_create_elements``, ``query_elements``, ``get_canvas_screenshot``.

    By default the list is filtered down to ``ALL_VISUAL_MCP_TOOLS`` (the
    union of planner / drawer / critic slices, 11 tools). The caller is
    expected to slice further per-agent — see ``app/agents/visual/build.py``.
    Pass ``tool_names`` to override entirely (e.g. PR3's sharpen flow may
    want a different superset).

    Usage::

        with mcp_excalidraw_tools() as mcp_tools:
            agent = build_visual_agent(...)  # adds *mcp_tools to agent.tools
            crew = Crew(agents=[agent], tasks=[...])
            ...

    Implementation note: we bypass ``crewai_tools.MCPServerAdapter`` and use
    ``mcpadapt.MCPAdapt`` directly with a sanitising adapter — see module
    docstring for the multi-type schema rationale.
    """
    # Lazy imports — ``crewai_tools`` may not be synced in dev environments
    # that only need the rest of the app, and we want a clean ImportError
    # rather than a module-import crash.
    from copy import deepcopy

    from crewai_tools.adapters.mcp_adapter import (  # type: ignore[import-not-found]
        CrewAIToolAdapter,
    )
    from mcpadapt.core import MCPAdapt  # type: ignore[import-not-found]

    params = _stdio_params()
    log.info("mcp_excalidraw stdio params: command=%s args=%s", params.command, params.args)

    class _SanitisingCrewAIAdapter(CrewAIToolAdapter):  # type: ignore[misc, valid-type]
        """Sanitise MCP tool args + schema before they hit CrewAI / the MCP server.

        Two responsibilities:

          1. **Schema flattening** — collapse upstream multi-type JSON Schema
             (``type: ["string", "number"]``) so CrewAI's strict pydantic
             converter accepts it.
          2. **Recursive null scrubbing** — drop None-valued dict keys at
             every depth before the kwargs reach the MCP server's Zod
             validators. mcpadapt's built-in filter only handles top-level
             kwargs; we need to recurse into list-of-dict args like
             ``batch_create_elements`` whose ``elements[i].text`` etc. arrive
             as null and get rejected.
        """

        def adapt(self, func, mcp_tool):  # type: ignore[override]
            mcp_tool.inputSchema = _flatten_multitype_schema(
                deepcopy(mcp_tool.inputSchema)
            )
            wrapped_func = _wrap_with_null_strip(func)
            return super().adapt(wrapped_func, mcp_tool)

    whitelist: frozenset[str] = (
        frozenset(tool_names) if tool_names is not None else ALL_VISUAL_MCP_TOOLS
    )

    adapter = MCPAdapt(params, _SanitisingCrewAIAdapter())
    tools = adapter.__enter__()
    try:
        filtered = [t for t in tools if t.name in whitelist]
        seen = {t.name for t in filtered}
        missing = whitelist - seen
        if missing:
            log.warning(
                "mcp_excalidraw whitelist references unknown tool(s): %s. "
                "Upstream may have renamed them — update _BUILD_TOOL_NAMES.",
                sorted(missing),
            )
        log.info(
            "mcp_excalidraw exposing %d/%d tools (filtered from %d): %s",
            len(filtered),
            len(whitelist),
            len(list(tools)),
            sorted(t.name for t in filtered),
        )
        yield filtered
    finally:
        adapter.__exit__(None, None, None)


__all__ = [
    "mcp_excalidraw_tools",
    "ALL_VISUAL_MCP_TOOLS",
    "PLANNER_MCP_TOOLS",
    "DRAWER_MCP_TOOLS",
    "CRITIC_MCP_TOOLS",
]
