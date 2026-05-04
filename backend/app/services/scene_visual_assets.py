"""Post-process Excalidraw scenes: AI-generated imagery + optional remote URLs.

Thumbnails are diagram-oriented (slide / flow-chart style prompts). Placement
defaults to **inside each planner frame** aligned to a notional grid column;
set ``SCENE_IMAGE_PLACEMENT=canvas_bottom_strip`` for the legacy bottom row.
"""

from __future__ import annotations

import base64
import logging
import time
from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI

from app.agents.scene.skeleton_scene_cleanup import sort_elements_paint_order
from app.config import settings
from app.models.db import (
    IdeaSlice,
    Outline,
    SceneFrame,
    SceneLayout,
    SceneSkeleton,
    SceneSkeletonElement,
)

log = logging.getLogger(__name__)

_MAX_REMOTE_BYTES = 2 * 1024 * 1024
_MAX_SCENE_ELEMENTS = 240


def _mime_from_data_url(data_url: str) -> str:
    head = data_url.split(",", 1)[0].lower()
    if "image/jpeg" in head or "image/jpg" in head:
        return "image/jpeg"
    if "image/webp" in head:
        return "image/webp"
    if "image/gif" in head:
        return "image/gif"
    return "image/png"


def _parse_remote_url_list() -> list[str]:
    raw = (settings.SCENE_REMOTE_IMAGE_URLS or "").strip()
    if not raw:
        return []
    out: list[str] = []
    for part in raw.split(","):
        u = part.strip()
        if u.startswith("https://"):
            out.append(u)
    return out


def _build_prompts(idea: IdeaSlice, outline: Outline, count: int) -> list[str]:
    """Prompts optimized for **diagram / instructor-slide** assets, not stock photos."""
    base = (idea.title or "video").strip()
    prompts: list[str] = []
    items = list(outline.items)[:count]

    style_rules = (
        "Visual style: clean instructor slide or textbook diagram — NOT a photograph, "
        "NOT a generic keyword illustration, NOT decorative artwork unrelated to teaching. "
        "Flat vector / infographic: rounded rectangles or cards, thin arrows or dotted "
        "flow lines, 3–4 clear steps or zones arranged left-to-right OR top-to-bottom. "
        "High contrast, generous whitespace, simple icons ok. "
        "Learning goal: viewer should grasp the *relationships* (sequence, cause→effect, "
        "before/after, pipeline) at a glance. "
        "Do NOT fill with paragraph text; at most one single large word OR step numbers "
        "(1-2-3) if needed — otherwise empty labeled shapes only. "
        "Aspect: landscape composition filling the frame width like a PowerPoint diagram pane."
    )

    for it in items:
        beat = (it.beat or "")[:280]
        section = (it.label or "").strip() or "Section"
        prompts.append(
            f"Topic / series: {base}. Slide section focus: {section}. "
            f"Teaching intent / beat to visualize (diagram this): {beat}. "
            + style_rules
        )

    while len(prompts) < count:
        prompts.append(
            f"Topic: {base}. Create one more slide-style learning diagram in the same rules. "
            + style_rules
        )
    return prompts[:count]


def _openai_image_generate_kwargs(prompt: str) -> dict:
    """Build ``images.generate`` kwargs per model (quality/size differ by family)."""
    model = (settings.OPENAI_IMAGE_MODEL or "dall-e-3").strip()
    p = prompt[:3900]
    q_raw = (settings.OPENAI_IMAGE_QUALITY or "hd").strip().lower()
    size_override = (settings.OPENAI_IMAGE_SIZE or "").strip()

    if model.startswith("dall-e-3"):
        if size_override in {"1024x1024", "1792x1024", "1024x1792"}:
            size = size_override
        elif settings.SCENE_IMAGE_LANDSCAPE_FOR_DIAGRAMS:
            size = "1792x1024"
        else:
            size = "1024x1024"
        qual = q_raw if q_raw in {"standard", "hd"} else "hd"
        return {
            "model": model,
            "prompt": p,
            "n": 1,
            "size": size,
            "quality": qual,
            "response_format": "b64_json",
        }

    if model.startswith("dall-e-2"):
        return {
            "model": model,
            "prompt": p,
            "n": 1,
            "size": "1024x1024",
            "response_format": "b64_json",
        }

    if model.startswith("gpt-image"):
        if size_override:
            size = size_override
        elif settings.SCENE_IMAGE_LANDSCAPE_FOR_DIAGRAMS:
            size = "1536x1024"
        else:
            size = "1024x1024"
        if q_raw in {"high", "medium", "low", "auto"}:
            qual: str = q_raw
        elif q_raw in {"hd", "best"}:
            qual = "high"
        elif q_raw == "standard":
            qual = "medium"
        elif q_raw == "low":
            qual = "low"
        else:
            qual = "high"
        # GPT Image models return b64_json by default; omit response_format.
        return {"model": model, "prompt": p, "n": 1, "size": size, "quality": qual}

    # Unknown model: minimal portable request.
    kwargs: dict = {
        "model": model,
        "prompt": p,
        "n": 1,
        "size": size_override or "1024x1024",
        "response_format": "b64_json",
    }
    if model.startswith("dall-e"):
        kwargs["quality"] = q_raw if q_raw in {"standard", "hd"} else "standard"
    return kwargs


async def _openai_generate_png_urls(prompts: list[str]) -> list[str]:
    assert settings.OPENAI_API_KEY
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    urls: list[str] = []
    for prompt in prompts:
        kwargs = _openai_image_generate_kwargs(prompt)
        resp = await client.images.generate(**kwargs)
        row = resp.data[0]
        b64 = getattr(row, "b64_json", None)
        if not b64:
            continue
        urls.append(f"data:image/png;base64,{b64}")
    return urls


async def _fetch_remote_image(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost"):
        return None
    async with httpx.AsyncClient(timeout=35.0, follow_redirects=True) as client:
        try:
            r = await client.get(url)
        except Exception as e:
            log.warning("remote image fetch failed %s: %s", url, e)
            return None
        if r.status_code != 200:
            return None
        ct = r.headers.get("content-type", "").split(";")[0].strip().lower()
        if ct not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
            return None
        if len(r.content) > _MAX_REMOTE_BYTES:
            log.warning("remote image too large, skipping: %s", url)
            return None
        b64 = base64.standard_b64encode(r.content).decode("ascii")
        return f"data:{ct};base64,{b64}"


def _max_slots_for_skeleton(skeleton: SceneSkeleton) -> int:
    room = _MAX_SCENE_ELEMENTS - len(skeleton.elements)
    return max(0, min(room, settings.SCENE_AI_IMAGE_COUNT))


def _scatter_rects_in_canvas(
    skeleton: SceneSkeleton,
    n: int,
    *,
    img_side: float = 160.0,
    pad: float = 18.0,
    margin: float = 32.0,
) -> list[tuple[float, float, float, float]]:
    """Up to ``n`` non-overlapping image rects inside existing canvas bounds.

    Builds occupied rects from current elements, scans a coarse grid of
    candidate positions, returns those that don't collide. Used for the MCP
    canvas path where there are no planner frames — images get tucked into
    whatever empty space the diagram left behind.
    """
    cw = float(skeleton.canvas_width)
    ch = float(skeleton.canvas_height)
    step = img_side + 24.0

    occupied: list[tuple[float, float, float, float]] = []
    for el in skeleton.elements:
        ex = float(el.x)
        ey = float(el.y)
        ew = float(el.width or 0)
        eh = float(el.height or 0)
        occupied.append((ex - pad, ey - pad, ex + ew + pad, ey + eh + pad))

    def collides(rx0: float, ry0: float, rx1: float, ry1: float) -> bool:
        for ox0, oy0, ox1, oy1 in occupied:
            if rx0 < ox1 and rx1 > ox0 and ry0 < oy1 and ry1 > oy0:
                return True
        return False

    out: list[tuple[float, float, float, float]] = []
    y = margin
    while y + img_side <= ch - margin and len(out) < n:
        x = margin
        while x + img_side <= cw - margin and len(out) < n:
            if not collides(x, y, x + img_side, y + img_side):
                out.append((x, y, img_side, img_side))
                occupied.append(
                    (x - pad, y - pad, x + img_side + pad, y + img_side + pad)
                )
            x += step
        y += step
    return out


def _embed_scattered_in_canvas(
    skeleton: SceneSkeleton,
    data_urls: list[str],
) -> SceneSkeleton:
    """Place images into empty regions of the existing canvas; overflow → strip."""
    rects = _scatter_rects_in_canvas(skeleton, len(data_urls))
    if not rects:
        return _embed_bottom_strip(skeleton, data_urls)

    placed = data_urls[: len(rects)]
    overflow = data_urls[len(rects) :]

    ts = int(time.time() * 1000)
    files = dict(skeleton.files or {})
    new_elements = list(skeleton.elements)

    for i, (data_url, rect) in enumerate(zip(placed, rects)):
        x, y, img_w, img_h = rect
        fid = f"ladder-hero-{i}-{ts}"
        mime = _mime_from_data_url(data_url)
        files[fid] = {
            "mimeType": mime,
            "id": fid,
            "dataURL": data_url,
            "created": ts,
        }
        new_elements.append(
            SceneSkeletonElement(
                id=f"hero-{i}-{ts}",
                type="image",
                x=x,
                y=y,
                width=img_w,
                height=img_h,
                fileId=fid,
            )
        )

    note_tail = (
        f" Embedded {len(placed)} diagram thumbnails (AI/remote) "
        "scattered into empty canvas regions."
    )
    notes = (skeleton.notes or "") + note_tail
    if len(notes) > 4000:
        notes = notes[:4000]

    sk = skeleton.model_copy(
        update={"elements": new_elements, "files": files, "notes": notes}
    )
    if overflow:
        sk = _embed_bottom_strip(
            sk,
            overflow,
            placement_note=" Additional hero thumbnails along bottom strip.",
        )
    else:
        sk = sort_elements_paint_order(sk)
    return sk


def _frame_anchor_image_rect(frame: SceneFrame, cols: int) -> tuple[float, float, float, float]:
    """Size like one column in an N-column row (e.g. 3 text cells + 1 diagram cell).

    Anchored bottom-right of the frame content area, vertically centered on the
    lower-middle band where slide bodies usually sit.
    """
    pad = 14.0
    inner_w = max(48.0, frame.width - 2 * pad)
    inner_h = max(48.0, frame.height - 2 * pad)
    gutter = 10.0
    ncols = max(3, min(8, cols))
    slot_w = max(88.0, (inner_w - gutter * (ncols - 1)) / float(ncols))
    img_w = slot_w
    img_h = min(max(slot_w * 1.06, 96.0), inner_h * 0.52)

    x = frame.x + frame.width - pad - img_w
    row_anchor_y = frame.y + pad + inner_h * 0.44
    y = row_anchor_y - img_h / 2.0

    x = max(frame.x + pad, min(x, frame.x + frame.width - pad - img_w))
    y = max(frame.y + pad, min(y, frame.y + frame.height - pad - img_h))
    return x, y, img_w, img_h


def _embed_bottom_strip(
    skeleton: SceneSkeleton,
    data_urls: list[str],
    *,
    placement_note: str = " Embedded hero thumbnails (AI/remote) along bottom strip.",
) -> SceneSkeleton:
    cw = float(skeleton.canvas_width)
    ch = float(skeleton.canvas_height)
    n = len(data_urls)
    # Strip layout: slightly larger tiles for diagram previews.
    img_side = min(300.0, max(148.0, cw / float(n + 2)))

    max_bottom = 0.0
    for el in skeleton.elements:
        max_bottom = max(max_bottom, el.y + el.height)

    needed_h = max_bottom + 40.0 + img_side + 36.0
    if needed_h > ch:
        skeleton = skeleton.model_copy(
            update={"canvas_height": min(4800, max(int(ch), int(needed_h)))}
        )
        ch = float(skeleton.canvas_height)

    margin_x = 56.0
    spare_width = cw - 2 * margin_x - n * img_side
    gap = spare_width / max(1.0, float(n - 1)) if n > 1 else 56.0

    base_y = max_bottom + 40.0
    if base_y + img_side > ch - 24.0:
        base_y = ch - img_side - 28.0
    base_y = max(32.0, base_y)

    files = dict(skeleton.files or {})
    new_elements = list(skeleton.elements)
    ts = int(time.time() * 1000)

    for i, data_url in enumerate(data_urls):
        fid = f"ladder-hero-{i}-{ts}"
        x = margin_x + float(i) * (img_side + gap)
        x = min(x, cw - margin_x - img_side)

        mime = _mime_from_data_url(data_url)
        files[fid] = {
            "mimeType": mime,
            "id": fid,
            "dataURL": data_url,
            "created": ts,
        }
        new_elements.append(
            SceneSkeletonElement(
                id=f"hero-{i}-{ts}",
                type="image",
                x=x,
                y=base_y,
                width=img_side,
                height=img_side,
                fileId=fid,
            )
        )

    note_tail = placement_note
    notes = (skeleton.notes or "") + note_tail
    if len(notes) > 4000:
        notes = notes[:4000]

    out = skeleton.model_copy(update={"elements": new_elements, "files": files, "notes": notes})
    # Designer already sorted paint order; appended images must merge into tiers
    # (shapes/images under arrows under text), not stay on top of everything.
    return sort_elements_paint_order(out)


def _embed_visual_images(
    skeleton: SceneSkeleton,
    layout: SceneLayout | None,
    data_urls: list[str],
) -> SceneSkeleton:
    """Place thumbnails inside matching planner frames, or fall back to bottom strip."""
    if settings.SCENE_IMAGE_PLACEMENT == "canvas_bottom_strip":
        return _embed_bottom_strip(skeleton, data_urls)

    frames = list(layout.frames) if layout and layout.frames else []
    if not frames:
        return _embed_scattered_in_canvas(skeleton, data_urls)

    ts = int(time.time() * 1000)
    files = dict(skeleton.files or {})
    new_elements = list(skeleton.elements)
    strip_overflow: list[str] = []

    for i, data_url in enumerate(data_urls):
        if i >= len(frames):
            strip_overflow.append(data_url)
            continue

        f = frames[i]
        x, y, img_w, img_h = _frame_anchor_image_rect(
            f, settings.SCENE_IMAGE_FRAME_GRID_COLUMNS
        )

        fid = f"ladder-hero-{i}-{ts}"
        mime = _mime_from_data_url(data_url)
        files[fid] = {
            "mimeType": mime,
            "id": fid,
            "dataURL": data_url,
            "created": ts,
        }
        new_elements.append(
            SceneSkeletonElement(
                id=f"hero-{i}-{ts}",
                type="image",
                x=x,
                y=y,
                width=img_w,
                height=img_h,
                fileId=fid,
            )
        )

    note_tail = (
        " Embedded diagram thumbnails (AI/remote): grid-column width inside each "
        "outline frame (see SCENE_IMAGE_FRAME_GRID_COLUMNS)."
    )
    notes = (skeleton.notes or "") + note_tail
    if len(notes) > 4000:
        notes = notes[:4000]

    sk = skeleton.model_copy(update={"elements": new_elements, "files": files, "notes": notes})
    if strip_overflow:
        sk = _embed_bottom_strip(
            sk,
            strip_overflow,
            placement_note=" Additional hero thumbnails along bottom strip.",
        )
    else:
        sk = sort_elements_paint_order(sk)
    return sk


async def enrich_scene_visuals(
    skeleton: SceneSkeleton,
    idea: IdeaSlice,
    outline: Outline,
    layout: SceneLayout | None = None,
) -> SceneSkeleton:
    """Attach up to ``SCENE_AI_IMAGE_COUNT`` images without rerunning layout."""
    log.warning(
        "[IMAGE-GEN] enter: elements=%d layout=%s key_set=%s gen_enabled=%s slots_cfg=%d",
        len(skeleton.elements),
        "present" if layout else "None",
        bool(settings.OPENAI_API_KEY),
        settings.SCENE_IMAGE_GEN_ENABLED,
        settings.SCENE_AI_IMAGE_COUNT,
    )
    max_slots = _max_slots_for_skeleton(skeleton)
    if max_slots <= 0:
        log.warning("[IMAGE-GEN] skip: max_slots=0 (canvas full or count=0)")
        return skeleton

    prompts = _build_prompts(idea, outline, max_slots)
    data_urls: list[str] = []

    if settings.OPENAI_API_KEY and settings.SCENE_IMAGE_GEN_ENABLED:
        log.warning(
            "[IMAGE-GEN] calling OpenAI: model=%s n=%d",
            settings.OPENAI_IMAGE_MODEL or "dall-e-3",
            max_slots,
        )
        try:
            data_urls.extend(await _openai_generate_png_urls(prompts))
            log.warning("[IMAGE-GEN] openai returned %d images", len(data_urls))
        except Exception as e:
            log.warning(
                "[IMAGE-GEN] OpenAI image generation FAILED: %s: %s",
                type(e).__name__,
                e,
            )
    else:
        log.warning(
            "[IMAGE-GEN] openai skipped: key=%s enabled=%s",
            bool(settings.OPENAI_API_KEY),
            settings.SCENE_IMAGE_GEN_ENABLED,
        )

    for url in _parse_remote_url_list():
        if len(data_urls) >= max_slots:
            break
        remote = await _fetch_remote_image(url)
        if remote:
            data_urls.append(remote)

    data_urls = data_urls[:max_slots]
    if not data_urls:
        log.warning("[IMAGE-GEN] no data urls produced — returning unenriched skeleton")
        return skeleton

    log.warning(
        "[IMAGE-GEN] embedding %d image(s) via %s",
        len(data_urls),
        "frame_anchor" if layout and layout.frames else "scatter_in_canvas",
    )
    return _embed_visual_images(skeleton, layout, data_urls)
