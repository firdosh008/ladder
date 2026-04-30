"""Rasterize a SceneSkeleton preview for multimodal critique (deterministic Pillow path)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as e:
    Image = ImageDraw = ImageFont = None  # type: ignore[assignment]
    _PIL_ERR = e
else:
    _PIL_ERR = None

from app.models.db import SceneSkeleton


_MAX_DIM_PX = 1800


def render_scene_to_image(scene_json: SceneSkeleton | dict[str, Any]) -> Path:
    """Write a PNG raster of skeleton geometry ( rects + terse text stubs ).

    This is intentionally lighter than `@excalidraw/excalidraw`'s full inflate but
    matches box positions faithfully for geometric / visual QA.
    """

    if Image is None:
        raise RuntimeError(f"Pillow (Pillow) missing: {_PIL_ERR}. Install pillow.")

    if isinstance(scene_json, dict):
        scene = SceneSkeleton.model_validate(scene_json)
    else:
        scene = scene_json

    cw = int(scene.canvas_width)
    ch = int(scene.canvas_height)
    sf = min(1.0, float(_MAX_DIM_PX) / max(cw, ch, 1))
    iw, ih = max(480, int(cw * sf)), max(420, int(ch * sf))
    bg = scene.background_color or "#1A1A2E"
    rgb = _hex_to_rgb(bg)
    img = Image.new("RGB", (iw, ih), rgb)
    dr = ImageDraw.Draw(img)

    font = ImageFont.load_default()
    elems = sorted(scene.elements, key=lambda e: (e.type, e.y, e.x))

    for el in elems:
        if el.type == "rectangle":
            x1 = el.x * sf
            y1 = el.y * sf
            x2 = (el.x + el.width) * sf
            y2 = (el.y + el.height) * sf
            stroke = _hex_to_rgb(el.strokeColor or "#E8E8E8")
            fill = _hex_to_rgb(el.backgroundColor) if el.backgroundColor else None
            dr.rectangle((x1, y1, x2, y2), outline=stroke, width=2, fill=fill)
            cap = el.label.text if el.label else ""
            if cap:
                dr.text((x1 + 8, y1 + 6), cap[:80], fill=(250, 250, 250), font=font)
        elif el.type == "text":
            if el.text:
                dr.text(
                    (el.x * sf + 6, el.y * sf + 6),
                    el.text.replace("\n", " ")[:200],
                    fill=(238, 238, 240),
                    font=font,
                )
        elif el.type == "arrow":
            xe, ye = el.x * sf, el.y * sf
            stroke = _hex_to_rgb(el.strokeColor or "#FF9955")
            dr.line(
                (xe, ye, xe + 36 * sf, ye + 20 * sf),
                fill=stroke,
                width=2,
            )
        elif el.type == "image":
            x1 = el.x * sf
            y1 = el.y * sf
            x2 = (el.x + el.width) * sf
            y2 = (el.y + el.height) * sf
            dr.rectangle((x1, y1, x2, y2), outline=(180, 180, 200), width=1)

    fd, path = tempfile.mkstemp(prefix="diagram_", suffix=".png")
    os.close(fd)
    out = Path(path)
    img.save(out, format="PNG", optimize=True)
    return out


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    s = (h or "#ffffff").strip()
    if not s.startswith("#"):
        s = f"#{s}"
    if len(s) >= 9:
        s = s[:7]
    hx = s[1:]
    try:
        r = int(hx[0:2], 16)
        g = int(hx[2:4], 16)
        b = int(hx[4:6], 16)
    except (IndexError, ValueError):
        r, g, b = 26, 26, 46
    return (r, g, b)
