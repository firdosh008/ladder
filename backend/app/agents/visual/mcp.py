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
from typing import TYPE_CHECKING, Iterator

from app.config import settings

if TYPE_CHECKING:
    # Heavy imports — keep them lazy so importing this module doesn't pull
    # the full CrewAI tool stack just for type-checking.
    from crewai.tools import BaseTool

log = logging.getLogger(__name__)


# ─── Build-tool whitelist ─────────────────────────────────────────────────
#
# Anthropic caps "strict" tools at 20 per request and CrewAI's Anthropic
# provider sends every tool we expose as strict. The vendored MCP server
# ships 26 tools; we add 4 backend tools; 30 tools blow the cap with a
# 400 invalid_request_error.
#
# This whitelist is the **build set** — the tools the visual agent
# actually needs to translate script + outline into a finished whiteboard
# and persist it. The dropped tools fall into three buckets:
#
#   • Methodology duplicates of skills we already inject — e.g.
#     ``read_diagram_guide`` (the ``excalidraw-diagram`` skill teaches the
#     same thing, verbatim).
#   • Inputs from outside the agent's purview — ``import_scene`` /
#     ``create_from_mermaid`` (the user can paste mermaid; the agent
#     should compose natively from the script).
#   • Niche layout helpers the agent can replicate with primitives —
#     ``group_elements`` / ``lock_elements`` / ``distribute_elements`` /
#     ``duplicate_elements``. Grouping/locking are human-editor concerns;
#     ``align_elements`` covers most layout polish.
#   • Redundant inspectors — ``get_element`` / ``get_resource`` (one-off
#     reads are covered by ``query_elements`` + ``describe_scene``).
#   • Output paths we don't use — ``export_to_image`` /
#     ``export_to_excalidraw_url`` (we persist via ``export_scene`` and
#     publish via our own ``POST .../scene/share`` route).
#   • ``create_element`` — the ``excalidraw-canvas`` skill explicitly
#     directs the agent to ``batch_create_elements`` instead.
#
# PR3's SharpenChatFlow may want a slightly different set (e.g. drop
# ``clear_canvas`` since sharpen is incremental). Parametrise then.
_BUILD_TOOL_NAMES: frozenset[str] = frozenset(
    {
        # Core CRUD on canvas elements.
        "batch_create_elements",
        "update_element",
        "delete_element",
        # Inspect (cheap structural read + visual feedback loop).
        "query_elements",
        "describe_scene",
        "get_canvas_screenshot",
        # Layout polish.
        "align_elements",
        # Fresh-start + viewport hygiene.
        "clear_canvas",
        "set_viewport",
        # Defensive rollback when a refactor goes wrong mid-loop.
        "snapshot_scene",
        "restore_snapshot",
        # Final read of canvas state for ``persist_scene_artifact``.
        "export_scene",
    }
)


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

    By default the list is filtered down to ``_BUILD_TOOL_NAMES`` (12 tools)
    so the total surface (12 MCP + 4 backend) stays under Anthropic's 20-
    strict-tool cap. Pass ``tool_names`` to override (e.g. PR3's sharpen
    flow may want a slightly different set).

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
        """Pre-flatten multi-type properties before delegating to CrewAI."""

        def adapt(self, func, mcp_tool):  # type: ignore[override]
            mcp_tool.inputSchema = _flatten_multitype_schema(
                deepcopy(mcp_tool.inputSchema)
            )
            return super().adapt(func, mcp_tool)

    whitelist: frozenset[str] = (
        frozenset(tool_names) if tool_names is not None else _BUILD_TOOL_NAMES
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


__all__ = ["mcp_excalidraw_tools"]
