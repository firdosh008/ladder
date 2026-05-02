"""Studio scene websocket path — live MCP canvas diagramming."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator
from uuid import UUID

from app.config import settings
from app.models.db import IdeaSlice, Outline, Script, UserProfileSlice, SceneSkeleton
from app.services import excalidraw_canvas
from app.services.diagram_service import DiagramService
from app.services.scene_visual_assets import enrich_scene_visuals
from app.services.usage import log_usage

log = logging.getLogger(__name__)

_PRICE_IN_PER_MTOK = 1.0
_PRICE_OUT_PER_MTOK = 5.0


def _bill(input_tokens: int, output_tokens: int) -> float:
    return round(
        (input_tokens / 1_000_000) * _PRICE_IN_PER_MTOK
        + (output_tokens / 1_000_000) * _PRICE_OUT_PER_MTOK,
        6,
    )


def compose_scene_brief(
    *,
    idea: IdeaSlice,
    outline: Outline,
    script: Script,
    profile: UserProfileSlice,
) -> str:
    lines: list[str] = [
        "# Lesson idea",
        f"Title: {idea.title}",
        "",
        "## Audience context",
        f"- Voice: {profile.voice or 'friendly educator'}",
        f"- Audience: {profile.audience or 'general learners'}",
        "",
        "## Outline beats",
    ]
    for item in outline.items:
        lines.append(f"{item.number}. **{item.label}** — {item.beat}")
    lines.extend(["", "## Script talking points"])
    for sec in script.sections:
        lines.append(f"### {sec.heading} (~{sec.duration_min} min)")
        for tp in sec.talking_points:
            lines.append(f"- {tp}")
        if sec.transition:
            lines.append(f"_Bridge: {sec.transition}_")
    return "\n".join(lines)


async def run_scene_mcp_diagram(
    user_id: UUID,
    profile: UserProfileSlice,
    idea: IdeaSlice,
    outline: Outline,
    script: Script,
    brand_color: str | None = None,
    font_family: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Mirror ``run_scene_build`` wire events while drawing on the MCP canvas."""

    await excalidraw_canvas.ensure_canvas_running(
        vendor=None,
        http_base=settings.EXCALIDRAW_HTTP_URL,
        autostart=settings.EXCALIDRAW_CANVAS_AUTOSTART,
    )

    brief = compose_scene_brief(
        idea=idea, outline=outline, script=script, profile=profile
    )

    svc = DiagramService(canvas_base_url=settings.EXCALIDRAW_HTTP_URL)

    yield {"type": "agent_start", "agent": "diagram_agent"}

    skeleton_dict: dict[str, Any] | None = None
    last_iterations = 1

    async with log_usage(
        user_id=user_id,
        function_name="scene_build_mcp_canvas",
        model=settings.DIAGRAM_ANTHROPIC_MODEL,
        provider="anthropic",
    ) as entry:
        async for ev in svc.stream_diagram_generation(
            brief,
            wait_for_live_viewer_seconds=120.0,
            brand_color=brand_color,
            font_family=font_family,
            max_iterations=settings.DIAGRAM_MAX_ITERATIONS,
        ):
            et = ev.get("type")
            if et == "_diagram_result":
                skeleton_dict = ev.get("scene")
                last_iterations = int(ev.get("iterations") or 1)
                tok = ev.get("token_usage") or {}
                entry.input_tokens = int(tok.get("input") or 0)
                entry.output_tokens = int(tok.get("output") or 0)
                entry.cost_usd = _bill(entry.input_tokens, entry.output_tokens)
                continue
            if et == "error":
                yield ev
                return
            yield ev

        if skeleton_dict is None:
            yield {
                "type": "error",
                "message": "MCP diagram finished without a scene payload",
            }
            return

        try:
            sk = SceneSkeleton.model_validate(skeleton_dict)
        except Exception as e:
            log.warning("SceneSkeleton coerce failed (%s) — returning raw dict", e)
            yield {"type": "scene_ready", "scene": skeleton_dict}
            yield {
                "type": "usage",
                "token_usage": {
                    "input": entry.input_tokens,
                    "output": entry.output_tokens,
                    "cost_usd": entry.cost_usd,
                },
            }
            return

        sk = await enrich_scene_visuals(sk, idea, outline, layout=None)

        yield {"type": "task_complete", "agent": "diagram_agent", "preview": ""}
        yield {
            "type": "diagram_complete",
            "iterations": last_iterations,
        }
        yield {"type": "scene_ready", "scene": sk.model_dump()}
        yield {
            "type": "usage",
            "token_usage": {
                "input": entry.input_tokens,
                "output": entry.output_tokens,
                "cost_usd": entry.cost_usd,
            },
        }
