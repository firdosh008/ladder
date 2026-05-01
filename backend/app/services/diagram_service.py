"""Claude agent loop controlling the live Excalidraw MCP canvas over HTTP."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import Any

import anthropic
import httpx

from app.config import settings
from app.services import excalidraw_http as ex_http
from app.services.excalidraw_http import ExcalidrawHttpError

log = logging.getLogger(__name__)

_DROP_SCENE_KEYS = frozenset({
    "createdAt",
    "updatedAt",
    "version",
    "syncedAt",
    "syncTimestamp",
    "source",
})

_SCENE_TOOL_NAMES = frozenset(
    {
        "diagram_clear_canvas",
        "diagram_batch_create_elements",
        "diagram_update_element",
        "diagram_delete_element",
        "diagram_describe_scene",
        "diagram_align_elements",
        "diagram_viewport_fit",
        "diagram_export_png_review",
        "diagram_finalize",
    },
)

_DIAGRAM_SYSTEM = """You operate the **live Excalidraw MCP canvas** for the product Ladder via HTTP tools.

You behave like an experienced facilitator drawing on a glass whiteboard: organic layout, conversational clarity, intentional hierarchy—not a cramped slide template.

Mandatory design rules:
- Absolutely avoid rigid grids, tiled columns of equal boxes, and “slide decks.” Use loose spatial hierarchy and natural spacing.
- Shapes overlap only when purposeful; prioritize readable flow (top-down or gently left-to-right) that a non‑technical stakeholder can skim in <20 seconds.
- Use emojis sparingly inside labels when they help intuition (⚠️ 🔁 💡 ✅); never emoji-spam.
- Arrows MUST bind to shapes (`start`/`end` with `{id: ...}` on arrows/line elements)—no floating unattached tails.
- Text must fully fit rectangles; widen shapes or shorten copy. Prefer two short lines vs one cramped line with overflow risk.
- Styling: soften edges (moderate strokeWidth ~1–2); mix roughness sparingly so it feels handmade, not mechanical.
- After major edits call `diagram_viewport_fit` so collaborators see everything.
- Call `diagram_export_png_review` to visually inspect spacing, truncation, overlaps, stray arrows—and iterate until visually clean—then finish with `diagram_finalize`.

Iterate: draft → screenshot review → tighten layout → finalize. Aim for thoughtful whiteboard realism, never engineering CAD."""


def _sanitize_element(el: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in el.items() if k not in _DROP_SCENE_KEYS}


def _element_bounds(el: dict[str, Any]) -> tuple[float, float, float, float]:
    x = float(el.get("x", 0))
    y = float(el.get("y", 0))
    w = float(el.get("width") or 0)
    h = float(el.get("height") or 0)
    if el.get("type") in ("arrow", "line"):
        pts = el.get("points")
        if isinstance(pts, list) and pts:
            xs: list[float] = []
            ys: list[float] = []
            for p in pts:
                if isinstance(p, (list, tuple)) and len(p) >= 2:
                    xs.append(float(p[0]))
                    ys.append(float(p[1]))
            if xs and ys:
                x_min = min(xs) + x
                y_min = min(ys) + y
                return x_min, y_min, max(xs) - min(xs), max(ys) - min(ys)
    return x, y, w if w > 0 else 280, h if h > 0 else 120


def _scene_payload_from_canvas(
    elements: list[dict[str, Any]], files: dict[str, Any]
) -> dict[str, Any]:
    if not elements:
        return {
            "canvas_width": 960,
            "canvas_height": 540,
            "background_color": "#FCFCFD",
            "elements": [],
            "files": files,
        }

    xmin = math.inf
    ymin = math.inf
    xmax = -math.inf
    ymax = -math.inf

    sanitized: list[dict[str, Any]] = []
    for el in elements:
        clean = _sanitize_element(dict(el))
        sanitized.append(clean)
        bx, by, bw, bh = _element_bounds(clean)
        r = bx + bw
        bot = by + bh
        xmin = min(xmin, bx)
        ymin = min(ymin, by)
        xmax = max(xmax, r)
        ymax = max(ymax, bot)

    pad_x, pad_y = 120.0, 120.0
    cw = int(max(900, xmax - xmin + pad_x * 2))
    ch = int(max(620, ymax - ymin + pad_y * 2))

    return {
        "canvas_width": cw,
        "canvas_height": ch,
        "background_color": "#FCFCFD",
        "elements": sanitized,
        "files": files,
    }


def _describe(elements: list[dict[str, Any]], limit: int = 240) -> str:
    rows: list[str] = []
    for el in elements[:limit]:
        eid = el.get("id", "?")
        typ = el.get("type", "?")
        bx, by, bw, bh = _element_bounds(el)
        lbl = ""
        lab = el.get("label")
        if isinstance(lab, dict) and lab.get("text"):
            lbl = str(lab["text"]).replace("\n", " ")
        txt = el.get("text")
        if not lbl and isinstance(txt, str) and txt.strip():
            lbl = txt.replace("\n", " ")
        if len(lbl) > 220:
            lbl = lbl[:217] + "…"
        start = None
        end = None
        s = el.get("start")
        e = el.get("end")
        if isinstance(s, dict):
            start = s.get("id")
        if isinstance(e, dict):
            end = e.get("id")
        bind = ""
        if typ in ("arrow", "line"):
            bind = f" start→{start} end→{end}"
        rows.append(
            f"- {str(eid)[:12]} [{typ}] @({bx:.0f},{by:.0f}) {bw:.0f}x{bh:.0f} '{lbl}'{bind}"
        )
    if len(elements) > limit:
        rows.append(f"...and {len(elements) - limit} more elements truncated")
    return "\n".join(rows) if rows else "(empty canvas)"


async def _align_elements_http(
    client: httpx.AsyncClient, *, element_ids: list[str], alignment: str
) -> dict[str, Any]:
    if len(element_ids) < 2:
        return {"ok": False, "error": "Need at least 2 ids to align"}

    loaded: list[dict[str, Any]] = []
    for eid in element_ids:
        try:
            res = await ex_http.element_get(client, eid)
            loaded.append(res["element"])
        except Exception as e:
            return {"ok": False, "error": f"missing element {eid}: {e}"}

    bxys = [_element_bounds(el) for el in loaded]
    alignment = alignment.strip().lower()
    if alignment not in {"left", "right", "center", "top", "bottom", "middle"}:
        return {"ok": False, "error": f"unsupported alignment `{alignment}`"}

    for el, box in zip(loaded, bxys, strict=False):
        etype = el.get("type") or "rectangle"
        if alignment == "left":
            tgt = min(b[0] for b in bxys)
            await ex_http.element_put(client, el["id"], {"x": tgt, "type": etype})
        elif alignment == "right":
            tgt_r = max(b[0] + b[2] for b in bxys)
            await ex_http.element_put(client, el["id"], {"x": tgt_r - box[2], "type": etype})
        elif alignment == "center":
            ctrs = [b[0] + b[2] / 2 for b in bxys]
            avg = sum(ctrs) / len(ctrs)
            await ex_http.element_put(client, el["id"], {"x": avg - box[2] / 2, "type": etype})
        elif alignment == "top":
            tgt = min(b[1] for b in bxys)
            await ex_http.element_put(client, el["id"], {"y": tgt, "type": etype})
        elif alignment == "bottom":
            tgt_b = max(b[1] + b[3] for b in bxys)
            await ex_http.element_put(client, el["id"], {"y": tgt_b - box[3], "type": etype})
        elif alignment == "middle":
            mids = [b[1] + b[3] / 2 for b in bxys]
            avg = sum(mids) / len(mids)
            await ex_http.element_put(client, el["id"], {"y": avg - box[3] / 2, "type": etype})

    return {"ok": True, "alignment": alignment, "count": len(element_ids)}


class DiagramService:
    """Generates diagrams by handing Claude MCP-equivalent REST tools."""

    def __init__(self, *, canvas_base_url: str | None = None) -> None:
        self._base = (canvas_base_url or settings.EXCALIDRAW_HTTP_URL).rstrip("/")

    def _tools_spec(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "diagram_clear_canvas",
                "description": "Delete every element — start blank before a new sketch.",
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "diagram_batch_create_elements",
                "description": "Create many primitives at once (recommended). Mirrors excalidraw/batch_create.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "elements": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Skeleton rows typed like Excalidraw MCP (rectangle/diamond/etc.)",
                        }
                    },
                    "required": ["elements"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "diagram_update_element",
                "description": "Patch a single existing element.",
                "input_schema": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}, "patch": {"type": "object"}},
                    "required": ["id", "patch"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "diagram_delete_element",
                "description": "Remove one element.",
                "input_schema": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                    "required": ["id"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "diagram_describe_scene",
                "description": (
                    "Cheap textual listing of bounding boxes/text — use before rewriting layout."
                ),
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "diagram_align_elements",
                "description": (
                    "Align a set of rectangles/text blocks (left/right/center/top/bottom/middle)."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "element_ids": {"type": "array", "items": {"type": "string"}},
                        "alignment": {
                            "type": "string",
                            "enum": [
                                "left",
                                "right",
                                "center",
                                "top",
                                "bottom",
                                "middle",
                            ],
                        },
                    },
                    "required": ["element_ids", "alignment"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "diagram_viewport_fit",
                "description": "Ask the embedded browser viewport to zoom/scroll-to-content.",
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "diagram_export_png_review",
                "description": (
                    "Render a PNG for visual QA; requires someone to have the canvas iframe open "
                    "(WebSocket viewer connected)."
                ),
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "diagram_finalize",
                "description": "Signal you are satisfied; optional short note summarizing the story.",
                "input_schema": {
                    "type": "object",
                    "properties": {"note": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
        ]

    async def _exec_tool(
        self,
        name: str,
        payload: dict[str, Any],
        client: httpx.AsyncClient,
    ) -> tuple[str, dict[str, Any]]:
        if name not in _SCENE_TOOL_NAMES:
            raise ExcalidrawHttpError(f"unknown tool {name}")

        try:
            if name == "diagram_clear_canvas":
                out = await ex_http.elements_clear(client)
                return json.dumps({"ok": True, **out})[:24000], {}

            if name == "diagram_batch_create_elements":
                els = payload.get("elements")
                if not isinstance(els, list):
                    return json.dumps({"ok": False, "error": "elements must be an array"}), {}
                data = await ex_http.elements_batch(client, els)  # type: ignore[arg-type]
                cnt = len(data.get("elements") or [])
                return json.dumps({"ok": True, "count": cnt})[:24000], {}

            if name == "diagram_update_element":
                eid = str(payload["id"])
                patch_raw = payload.get("patch")
                if not isinstance(patch_raw, dict):
                    return json.dumps({"ok": False, "error": "patch must be object"}), {}
                patch = dict(patch_raw)
                et = patch.get("type")
                if et is None:
                    try:
                        cur = await ex_http.element_get(client, eid)
                        et = cur["element"].get("type")
                    except Exception:
                        et = "rectangle"
                patch["type"] = et
                await ex_http.element_put(client, eid, patch)
                return json.dumps({"ok": True}), {}

            if name == "diagram_delete_element":
                eid = str(payload["id"])
                await ex_http.element_delete(client, eid)
                return json.dumps({"ok": True}), {}

            if name == "diagram_describe_scene":
                els, _ = await ex_http.elements_list(client)
                return json.dumps({"ok": True, "summary": _describe(els)})[:24000], {}

            if name == "diagram_align_elements":
                eids_raw = payload.get("element_ids")
                ids = [str(i) for i in eids_raw] if isinstance(eids_raw, list) else []
                align = str(payload.get("alignment", ""))
                res = await _align_elements_http(client, element_ids=ids, alignment=align)
                return json.dumps(res)[:24000], {}

            if name == "diagram_viewport_fit":
                vp = await ex_http.viewport_scroll_to_content(client)
                return json.dumps({"ok": vp.get("success", True), "detail": vp})[:24000], {}

            if name == "diagram_export_png_review":
                res = await ex_http.export_png(client)
                ok = bool(res.get("success"))
                if ok and isinstance(res.get("data"), str):
                    raw = res["data"]
                    png_b64 = raw.split(",", 1)[-1].strip()
                    return (
                        json.dumps({"ok": True, "detail": "PNG attached for your review."}),
                        {"_png_review_b64": png_b64},
                    )
                err = str(res.get("error") or "export failed")[:480]
                return json.dumps({"ok": False, "error": err}), {}

            if name == "diagram_finalize":
                note = payload.get("note") or ""
                return (
                    json.dumps({"ok": True, "finalized": True, "note": note}),
                    {"_finalized": True},
                )

        except ExcalidrawHttpError as e:
            log.warning("diagram tool HTTP error [%s]: %s", name, e)
            return json.dumps({"ok": False, "error": str(e)})[:24000], {}

        return json.dumps({"ok": False, "error": "unhandled tool branch"}), {}

    async def wait_for_browser_viewer(
        self,
        client: httpx.AsyncClient,
        *,
        seconds: float,
    ) -> bool:
        deadline = asyncio.get_running_loop().time() + seconds
        while asyncio.get_running_loop().time() < deadline:
            try:
                h = await ex_http.canvas_health_detail(client)
                ws = int(h.get("websocket_clients") or 0)
                if ws >= 1:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.35)
        return False

    async def generate_diagram(
        self,
        script: str,
        *,
        wait_for_live_viewer_seconds: float = 55.0,
    ) -> dict[str, Any]:
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is required for DiagramService.")
        trimmed = script.strip()
        if not trimmed or len(trimmed) > 80_000:
            raise ValueError("script must be 1–80k characters")

        claude = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        timeout = httpx.Timeout(240.0, connect=30.0)
        async with httpx.AsyncClient(base_url=self._base, timeout=timeout) as hc:
            had_viewer = True
            if wait_for_live_viewer_seconds and wait_for_live_viewer_seconds > 0:
                had_viewer = await self.wait_for_browser_viewer(
                    hc, seconds=wait_for_live_viewer_seconds
                )

            tools = self._tools_spec()

            messages: list[dict[str, Any]] = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Turn the following creator script/outline into ONE polished whiteboard "
                                "diagram on the synced canvas.\n\n"
                                f"———— SCRIPT ————\n{trimmed}\n———— END SCRIPT ————\n\n"
                                + (
                                    "The iframe viewer is CONNECTED — you may screenshot."
                                    if had_viewer
                                    else "**Warning:** no iframe/WebSocket viewer yet — "
                                    "`diagram_export_png_review` may fail until a browser opens "
                                    "http://127.0.0.1:3000 Still build the diagram for live sync."
                                )
                            ),
                        },
                    ],
                }
            ]

            rounds = settings.DIAGRAM_AGENT_MAX_TURNS
            finalized = False
            accumulated_tokens = 0

            for _ in range(rounds):
                resp = await claude.messages.create(
                    model=settings.DIAGRAM_ANTHROPIC_MODEL,
                    max_tokens=8096,
                    system=_DIAGRAM_SYSTEM,
                    tools=tools,
                    messages=messages,
                    temperature=0.45,
                )

                ts = getattr(resp, "usage", None)
                if ts is not None:
                    accumulated_tokens += int(getattr(ts, "input_tokens", 0) or 0) + int(
                        getattr(ts, "output_tokens", 0) or 0,
                    )

                tool_calls = []
                if resp.content:
                    for blk in resp.content:
                        blk_type = getattr(blk, "type", None)
                        if blk_type != "tool_use":
                            continue
                        tool_calls.append(
                            {
                                "id": getattr(blk, "id"),
                                "name": getattr(blk, "name"),
                                "input": getattr(blk, "input"),
                            },
                        )

                assistant_blocks_out: list[dict[str, Any]] = []
                for blk in resp.content or []:
                    blk_type = getattr(blk, "type", None)
                    if blk_type == "tool_use":
                        assistant_blocks_out.append(
                            {
                                "type": "tool_use",
                                "id": getattr(blk, "id"),
                                "name": getattr(blk, "name"),
                                "input": getattr(blk, "input"),
                            },
                        )
                    elif blk_type == "text":
                        assistant_blocks_out.append({"type": "text", "text": getattr(blk, "text", "")})

                messages.append({"role": "assistant", "content": assistant_blocks_out})

                if resp.stop_reason != "tool_use" or not tool_calls:
                    break

                user_followup: list[dict[str, Any]] = []

                for tc in tool_calls:
                    nm = tc["name"]
                    pin = tc["input"]
                    tid = tc["id"]
                    if not isinstance(pin, dict):
                        pin = {}
                    if nm not in _SCENE_TOOL_NAMES:
                        user_followup.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tid,
                                "content": [{"type": "text", "text": f"unsupported tool `{nm}`"}],
                            },
                        )
                        continue
                    txt, meta_extra = await self._exec_tool(nm, pin, hc)
                    if nm == "diagram_finalize" and meta_extra.get("_finalized"):
                        finalized = True
                        user_followup.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tid,
                                "content": [{"type": "text", "text": txt}],
                            },
                        )
                        continue
                    blocks: list[dict[str, Any]] = [{"type": "text", "text": txt}]
                    png_b64 = meta_extra.get("_png_review_b64")
                    if isinstance(png_b64, str) and png_b64:
                        blocks.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": png_b64,
                                },
                            },
                        )
                    user_followup.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tid,
                            "content": blocks,
                    },
                )

                messages.append({"role": "user", "content": user_followup})

                if finalized:
                    break

            els, _data = await ex_http.elements_list(hc)
            fin = await ex_http.files_list(hc)
            files_map = {}
            ff = fin.get("files") if isinstance(fin, dict) else None
            if isinstance(ff, dict):
                files_map = ff
            elif isinstance(ff, list):
                for frow in ff:
                    if isinstance(frow, dict) and frow.get("id"):
                        files_map[str(frow["id"])] = frow

            scene = _scene_payload_from_canvas(list(els), files_map)

            png_path = None
            png_b64_try: dict[str, Any] | None = None
            try:
                png_b64_try = await ex_http.export_png(hc)
            except Exception:
                png_b64_try = None

            png_bytes: bytes | None = None
            if png_b64_try and png_b64_try.get("success") and isinstance(
                png_b64_try.get("data"),
                str,
            ):
                import base64

                raw = png_b64_try["data"]
                bchunk = raw.split(",", 1)[-1].strip()
                png_bytes = base64.b64decode(bchunk.encode("ascii"))

            return {
                "scene": scene,
                "finalized_tool": finalized,
                "diagram_png_bytes": png_bytes,
                "tokens_est": accumulated_tokens,
                "websocket_ok": had_viewer,
            }


__all__ = ["DiagramService"]
