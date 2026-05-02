"""Studio visual agent — drives the live Excalidraw MCP canvas.

Two flows on top of one shared CrewAI agent:

  • ``flow_build``    — one-shot "build the diagram from script + outline"
  • ``flow_sharpen``  — long-lived chat loop (Refine text · Screenshot to edit
                        · Regenerate scene) anchored to a studio session.

PR1 (current): scaffolding only. The ``StudioVisualAgent`` factory, the four
backing tools (Knowledge, Brand, ScriptOutline, PersistArtifact), the MCP
adapter wiring, and the skill loader land here. The build/sharpen flows
and their WS routes ship in PR2/PR3 — see HANDOFF.md §5 for status.
"""

from __future__ import annotations

from app.agents.visual.build import run_visual_build

__all__ = ["run_visual_build"]
