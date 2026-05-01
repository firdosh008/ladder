"""Post-process Excalidraw scenes: AI-generated imagery + optional remote URLs.

Thumbnails are generated via OpenAI Images when ``OPENAI_API_KEY`` is set.
Placement defaults to **inside each planner frame** (outline order); set
``SCENE_IMAGE_PLACEMENT=canvas_bottom_strip`` for the legacy bottom row.
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
from app.models.db import IdeaSlice, Outline, SceneLayout, SceneSkeleton, SceneSkeletonElement

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
    base = (idea.title or "video").strip()
    prompts: list[str] = []
    items = list(outline.items)[:count]
    for it in items:
        beat = (it.beat or "")[:220]
        prompts.append(
            f"Flat vector illustration for an educational slide. Topic: {base}. "
            f"Visual metaphor for: {it.label}. Context: {beat}. "
            "No letters or words in the image; bold shapes; soft gradients OK; "
            "professional thumbnail usable at small size."
        )
    while len(prompts) < count:
        prompts.append(
            f"Abstract professional illustration related to: {base}. "
            "No text; icon-like clarity; suitable as small hero image."
        )
    return prompts[:count]


def _openai_image_generate_kwargs(prompt: str) -> dict:
    """Build ``images.generate`` kwargs per model (quality/size differ by family)."""
    model = (settings.OPENAI_IMAGE_MODEL or "dall-e-3").strip()
    p = prompt[:3900]
    q_raw = (settings.OPENAI_IMAGE_QUALITY or "hd").strip().lower()
    size_override = (settings.OPENAI_IMAGE_SIZE or "").strip()

    if model.startswith("dall-e-3"):
        size = size_override if size_override in {
            "1024x1024",
            "1792x1024",
            "1024x1792",
        } else "1024x1024"
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
        size = size_override if size_override else "1024x1024"
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
    return max(0, min(room, settings.SCENE_AI_IMAGE_COUNT, 3))


def _embed_bottom_strip(
    skeleton: SceneSkeleton,
    data_urls: list[str],
    *,
    placement_note: str = " Embedded hero thumbnails (AI/remote) along bottom strip.",
) -> SceneSkeleton:
    cw = float(skeleton.canvas_width)
    ch = float(skeleton.canvas_height)
    n = len(data_urls)
    # Larger on-canvas footprint than before so downscaling from 1024² is less harsh.
    img_side = min(240.0, max(120.0, cw / float(n + 3)))

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
        return _embed_bottom_strip(skeleton, data_urls)

    ts = int(time.time() * 1000)
    files = dict(skeleton.files or {})
    new_elements = list(skeleton.elements)
    strip_overflow: list[str] = []

    for i, data_url in enumerate(data_urls):
        if i >= len(frames):
            strip_overflow.append(data_url)
            continue

        f = frames[i]
        pad = 14.0
        img_side = min(220.0, max(88.0, min(f.width, f.height) * 0.28))
        x = f.x + f.width - img_side - pad
        y = f.y + f.height - img_side - pad
        x = max(f.x + pad, min(x, f.x + f.width - img_side - pad))
        y = max(f.y + pad, min(y, f.y + f.height - img_side - pad))

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
                width=img_side,
                height=img_side,
                fileId=fid,
            )
        )

    note_tail = (
        " Embedded hero thumbnails (AI/remote) anchored to outline frames "
        "(bottom-right per frame)."
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
    max_slots = _max_slots_for_skeleton(skeleton)
    if max_slots <= 0:
        return skeleton

    prompts = _build_prompts(idea, outline, max_slots)
    data_urls: list[str] = []

    if settings.OPENAI_API_KEY and settings.SCENE_IMAGE_GEN_ENABLED:
        try:
            data_urls.extend(await _openai_generate_png_urls(prompts))
        except Exception as e:
            log.warning("OpenAI image generation failed (scene still usable): %s", e)

    for url in _parse_remote_url_list():
        if len(data_urls) >= max_slots:
            break
        remote = await _fetch_remote_image(url)
        if remote:
            data_urls.append(remote)

    data_urls = data_urls[:max_slots]
    if not data_urls:
        return skeleton

    return _embed_visual_images(skeleton, layout, data_urls)
