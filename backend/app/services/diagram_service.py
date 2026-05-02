"""Iterative lesson-diagram generation against the local Excalidraw canvas HTTP API."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import string
from typing import Any, AsyncIterator

from app.agents.excalidraw_design_guide import (
    DESIGN_SKILL_SYSTEM_RULES,
    DIAGRAM_JSON_INSTRUCTIONS,
    VISION_REVIEW_PROMPT,
)
from app.config import settings
from app.models.db import SceneSkeleton
from app.services.excalidraw_http import ExcalidrawCanvasClient
from app.services.llm import anthropic_client

log = logging.getLogger(__name__)

_SERVER_FIELDS = frozenset({"createdAt", "updatedAt", "version"})
_EXCAL_ID_ALPHABET = string.ascii_lowercase + string.digits


def _random_excalidraw_like_id() -> str:
    return "".join(secrets.choice(_EXCAL_ID_ALPHABET) for _ in range(14))


def assign_fresh_element_ids(elements: list[dict[str, Any]]) -> None:
    """Give each element a unique id and rewrite binding references from LLM ids.

    Vision QA must PATCH elements by real canvas ids from ``get_all_elements``. LLMs often emit
    semantic ids like ``step1`` that never hit the wire; random ids reduce collisions and clarify
    that corrections must copy ids from the Elements JSON verbatim.
    """
    new_ids = [_random_excalidraw_like_id() for _ in elements]

    llm_to_assigned: dict[str, str] = {}
    for i, el in enumerate(elements):
        nid = new_ids[i]
        raw = el.get("id")
        if isinstance(raw, str) and raw.strip():
            llm_to_assigned.setdefault(raw.strip(), nid)

    def remap(old_ref: str) -> str:
        return llm_to_assigned.get(old_ref, old_ref)

    def rewrite_bindings(el: dict[str, Any]) -> None:
        sb = el.get("startBinding")
        if isinstance(sb, dict) and isinstance(sb.get("elementId"), str):
            sb["elementId"] = remap(sb["elementId"])
        eb = el.get("endBinding")
        if isinstance(eb, dict) and isinstance(eb.get("elementId"), str):
            eb["elementId"] = remap(eb["elementId"])
        bes = el.get("boundElements")
        if isinstance(bes, list):
            for be in bes:
                if isinstance(be, dict) and isinstance(be.get("id"), str):
                    be["id"] = remap(be["id"])
        st = el.get("start")
        if isinstance(st, dict) and isinstance(st.get("id"), str):
            st["id"] = remap(st["id"])
        en = el.get("end")
        if isinstance(en, dict) and isinstance(en.get("id"), str):
            en["id"] = remap(en["id"])

    for i, el in enumerate(elements):
        rewrite_bindings(el)
        el["id"] = new_ids[i]


def _response_text(message: Message) -> str:
    parts: list[str] = []
    for block in message.content:
        if block.type == "text":
            parts.append(block.text)
    return "".join(parts).strip()


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model did not return a JSON object")
    return json.loads(text[start : end + 1])


def _clean_server_element(el: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in el.items() if k not in _SERVER_FIELDS}


def _element_bounds(el: dict[str, Any]) -> tuple[float, float, float, float]:
    x = float(el.get("x", 0))
    y = float(el.get("y", 0))
    et = el.get("type")
    if et in ("arrow", "line") and el.get("points"):
        pts = el["points"]
        xs = [x + float(p[0]) for p in pts if isinstance(p, (list, tuple)) and len(p) >= 2]
        ys = [y + float(p[1]) for p in pts if isinstance(p, (list, tuple)) and len(p) >= 2]
        if xs and ys:
            return min(xs), min(ys), max(xs), max(ys)
    w = float(el.get("width") or 0)
    h = float(el.get("height") or 0)
    return x, y, x + w, y + h


def _bbox_canvas(elements: list[dict[str, Any]], *, default_w: int, default_h: int) -> tuple[int, int]:
    if not elements:
        return default_w, default_h
    min_x = min(_element_bounds(e)[0] for e in elements)
    min_y = min(_element_bounds(e)[1] for e in elements)
    max_x = max(_element_bounds(e)[2] for e in elements)
    max_y = max(_element_bounds(e)[3] for e in elements)
    pad = 120.0
    span_x = (max_x - min_x) + 2 * pad
    span_y = (max_y - min_y) + 2 * pad
    cw = int(min(4800, max(800, max(default_w, span_x))))
    ch = int(min(4800, max(600, max(default_h, span_y))))
    return cw, ch


def canvas_elements_to_scene_dict(
    elements: list[dict[str, Any]],
    *,
    canvas_width: int,
    canvas_height: int,
    background_color: str,
) -> dict[str, Any]:
    cleaned = [_clean_server_element(e) for e in elements]
    cw, ch = _bbox_canvas(cleaned, default_w=canvas_width, default_h=canvas_height)
    return {
        "canvas_width": cw,
        "canvas_height": ch,
        "background_color": background_color,
        "elements": cleaned,
        "notes": None,
        "files": None,
    }


class DiagramService:
    """Plan → draw on MCP canvas → vision QA loop → PNG export."""

    def __init__(self, canvas_base_url: str | None = None) -> None:
        self.canvas_base_url = (canvas_base_url or settings.EXCALIDRAW_HTTP_URL).rstrip("/")
        self._http = ExcalidrawCanvasClient(self.canvas_base_url)
        self.last_input_tokens = 0
        self.last_output_tokens = 0

    def _add_usage(self, message: Any) -> None:
        u = message.usage
        self.last_input_tokens += int(getattr(u, "input_tokens", 0) or 0)
        self.last_output_tokens += int(getattr(u, "output_tokens", 0) or 0)

    async def _draft_payload(
        self,
        script: str,
        *,
        brand_color: str | None,
        font_family: int | None,
        feedback_notes: list[str],
        layout_hint: str | None,
    ) -> dict[str, Any]:
        client = anthropic_client()
        parts: list[str] = [
            DESIGN_SKILL_SYSTEM_RULES,
            DIAGRAM_JSON_INSTRUCTIONS,
            "\n## Script to visualize\n",
            script.strip(),
        ]
        if layout_hint:
            parts.append(f"\nPreferred layout style: {layout_hint}\n")
        if brand_color:
            parts.append(
                f"\nBrand accent hex ( weave into strokes / fills, not neon overload ): {brand_color}\n"
            )
        if font_family is not None:
            parts.append(
                f"\nSet fontFamily={font_family} on every text-bearing element (type text or labels).\n"
            )
        if feedback_notes:
            parts.append("\n## Fix these issues from the previous iteration\n")
            parts.extend(f"- {n}\n" for n in feedback_notes if n)

        msg = await client.messages.create(
            model=settings.DIAGRAM_ANTHROPIC_MODEL,
            max_tokens=8192,
            temperature=0.35,
            system=(
                "You are an expert instructional diagram designer. "
                "Output ONLY JSON describing Excalidraw elements."
            ),
            messages=[{"role": "user", "content": "".join(parts)}],
        )
        self._add_usage(msg)
        payload = _extract_json_object(_response_text(msg))
        if not isinstance(payload.get("elements"), list):
            raise ValueError("Draft JSON missing elements[]")
        return payload

    async def _vision_review(
        self,
        png_base64: str,
        elements: list[dict[str, Any]],
    ) -> dict[str, Any]:
        client = anthropic_client()
        trimmed_elements = json.dumps(elements, ensure_ascii=False)[:140_000]
        msg = await client.messages.create(
            model=settings.DIAGRAM_ANTHROPIC_MODEL,
            max_tokens=2048,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": png_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": VISION_REVIEW_PROMPT + "\n\nElements JSON:\n" + trimmed_elements,
                        },
                    ],
                }
            ],
        )
        self._add_usage(msg)
        try:
            review = _extract_json_object(_response_text(msg))
        except Exception:
            log.warning("Vision QA returned non-JSON — approving draft.")
            return {"approved": True, "corrections": [], "notes": "parse_error"}
        return review

    async def _apply_corrections(
        self,
        corrections: list[dict[str, Any]],
        *,
        allowed_ids: frozenset[str],
    ) -> None:
        for item in corrections:
            el_id = item.get("id")
            patch = item.get("patch")
            if not el_id or not isinstance(patch, dict):
                continue
            sid = str(el_id)
            if sid not in allowed_ids:
                log.warning(
                    "Skipping correction for unknown element id %r (not on canvas). "
                    "Vision must use exact ids from the Elements JSON.",
                    sid,
                )
                continue
            try:
                await self._http.update_element(sid, patch)
            except Exception:
                log.warning("Failed to apply correction for %s", el_id, exc_info=True)

    async def generate_diagram(
        self,
        script: str,
        *,
        wait_for_live_viewer_seconds: float = 55.0,
        brand_color: str | None = None,
        font_family: int | None = None,
        max_iterations: int | None = None,
    ) -> dict[str, Any]:
        """Blocking entrypoint used by REST ``/generate-diagram``."""
        result: dict[str, Any] = {}
        async for event in self.stream_diagram_generation(
            script,
            wait_for_live_viewer_seconds=wait_for_live_viewer_seconds,
            brand_color=brand_color,
            font_family=font_family,
            max_iterations=max_iterations,
        ):
            et = event.get("type")
            if et == "error":
                raise RuntimeError(str(event.get("message") or "diagram generation failed"))
            if et == "_diagram_result":
                result = event
        if not result:
            raise RuntimeError("diagram generation produced no result")
        out = {k: v for k, v in result.items() if k != "type"}
        return out

    async def stream_diagram_generation(
        self,
        script: str,
        *,
        wait_for_live_viewer_seconds: float = 55.0,
        brand_color: str | None = None,
        font_family: int | None = None,
        max_iterations: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield UX events plus a terminal ``_diagram_result`` payload."""
        from app.services import excalidraw_canvas

        max_iter = max_iterations if max_iterations is not None else settings.DIAGRAM_MAX_ITERATIONS

        await excalidraw_canvas.wait_for_websocket_clients(
            self.canvas_base_url,
            timeout_s=wait_for_live_viewer_seconds,
            min_clients=1,
        )

        self.last_input_tokens = 0
        self.last_output_tokens = 0

        feedback: list[str] = []
        layouts_cycle = (
            "flowchart_left_right",
            "timeline_horizontal",
            "radial_hub",
            "two_column_contrast",
            "matrix_2x2",
            "hierarchical_top_down",
        )

        png_bytes: bytes | None = None
        scene_dict: dict[str, Any] | None = None
        used_iterations = 0

        yield {"type": "diagram_draft", "phase": "waiting_live_viewer"}

        try:
            for iteration in range(max_iter):
                layout_hint = layouts_cycle[iteration % len(layouts_cycle)]
                yield {
                    "type": "diagram_iteration",
                    "iteration": iteration + 1,
                    "phase": "draft",
                    "layout_hint": layout_hint,
                }

                payload = await self._draft_payload(
                    script,
                    brand_color=brand_color,
                    font_family=font_family,
                    feedback_notes=feedback,
                    layout_hint=layout_hint,
                )

                elements = payload["elements"]
                assign_fresh_element_ids(elements)
                bg = str(payload.get("background_color") or "#ffffff")
                cw = int(payload.get("canvas_width") or 1600)
                ch = int(payload.get("canvas_height") or 900)

                await self._http.clear_canvas()
                await self._http.batch_create_elements(elements)
                await asyncio.sleep(0.15)
                try:
                    await self._http.set_viewport(scroll_to_content=True)
                except Exception:
                    log.debug("viewport RPC skipped", exc_info=True)

                yield {
                    "type": "diagram_draft",
                    "phase": "drawn",
                    "iteration": iteration + 1,
                    "element_count": len(elements),
                }

                approved = False
                inner_passes = 3
                for _ in range(inner_passes):
                    yield {
                        "type": "diagram_iteration",
                        "iteration": iteration + 1,
                        "phase": "vision",
                    }
                    png_b64 = await self._http.export_image_png_base64()
                    current = await self._http.get_all_elements()
                    canvas_ids = frozenset(
                        str(e["id"])
                        for e in current
                        if isinstance(e, dict) and e.get("id") is not None
                    )
                    review = await self._vision_review(png_b64, current)
                    notes = str(review.get("notes") or "")
                    if review.get("approved"):
                        approved = True
                        png_bytes = await self._http.export_png_bytes()
                        scene_dict = canvas_elements_to_scene_dict(
                            current,
                            canvas_width=cw,
                            canvas_height=ch,
                            background_color=bg,
                        )
                        try:
                            SceneSkeleton.model_validate(scene_dict)
                        except Exception as exc:
                            log.warning("SceneSkeleton validation warning: %s", exc)
                        yield {"type": "diagram_iteration", "phase": "approved"}
                        break

                    corrections = review.get("corrections") or []
                    if isinstance(corrections, list) and corrections:
                        await self._apply_corrections(
                            corrections, allowed_ids=canvas_ids
                        )
                        await asyncio.sleep(0.12)
                        feedback.append(notes or "apply structural fixes")
                    else:
                        feedback.append(notes or "QA requested changes without patches")
                        break

                if approved:
                    used_iterations = iteration + 1
                    break

                feedback.append(f"Iteration {iteration + 1} still failing QA — redraw.")
                used_iterations = iteration + 1

            if scene_dict is None or png_bytes is None:
                current = await self._http.get_all_elements()
                png_bytes = await self._http.export_png_bytes()
                scene_dict = canvas_elements_to_scene_dict(
                    current,
                    canvas_width=1600,
                    canvas_height=900,
                    background_color="#ffffff",
                )
                try:
                    SceneSkeleton.model_validate(scene_dict)
                except Exception as exc:
                    log.warning("Final SceneSkeleton validation warning: %s", exc)

            if not used_iterations:
                used_iterations = max_iter

            yield {
                "type": "_diagram_result",
                "scene": scene_dict,
                "diagram_png_bytes": png_bytes,
                "iterations": used_iterations,
                "token_usage": {
                    "input": self.last_input_tokens,
                    "output": self.last_output_tokens,
                },
            }
        except Exception as e:
            log.exception("stream_diagram_generation failed")
            yield {"type": "error", "message": str(e)}
            return
