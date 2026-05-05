"""Thumbnail generation crew.

Single-agent flow: builds a rich DALL-E prompt from the video title,
top talking points, brand color, and optional reference thumbnail style,
then calls the OpenAI image API to produce N variants.

Does NOT use CrewAI — this is a direct async generator that yields
AgentEvent-shaped dicts for the WebSocket route.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, AsyncGenerator

import httpx
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.config import settings
from app.models.db import IdeaSlice, Script

log = logging.getLogger(__name__)

_STORAGE_BUCKET = "excalidraw_scenes"

_REFERENCE_ANALYSIS_SYSTEM = """\
Analyze this YouTube thumbnail image for visual style. Describe concisely:
1. Composition (layout, subject placement, rule of thirds, symmetry)
2. Text placement (where, font style, size relative to frame, color contrast)
3. Color usage (dominant colors, palette mood, saturation level)
4. Overall mood and energy

IMPORTANT: Even if the reference contains human faces or people, note that the
final generated thumbnail MUST NOT include any faces or photorealistic people.
Focus your analysis on the graphic design elements (composition, typography,
color palette) that can be adapted to an abstract, face-free design.

Keep under 300 words. This analysis will be fed into an image generation prompt
that explicitly forbids human faces."""


def _resolve_image_model() -> str:
    raw = (settings.THUMBNAIL_IMAGE_MODEL or "").strip()
    return raw if raw else (settings.OPENAI_IMAGE_MODEL or "dall-e-3").strip()


def _top_talking_points(script: dict[str, Any], n: int = 3) -> list[str]:
    points: list[str] = []
    for sec in script.get("sections") or []:
        for tp in sec.get("talking_points") or []:
            s = str(tp).strip()
            if s:
                points.append(s)
            if len(points) >= n:
                return points
    return points


async def _analyze_reference_thumbnail(url: str) -> str | None:
    """Fetch a thumbnail URL and describe its visual style via Claude Vision."""
    if not settings.ANTHROPIC_API_KEY:
        log.warning("[THUMBNAIL] no ANTHROPIC_API_KEY — skipping reference analysis")
        return None

    # Fetch the image
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(url)
        if r.status_code != 200:
            log.warning("[THUMBNAIL] reference fetch failed: HTTP %s", r.status_code)
            return None
        ct = r.headers.get("content-type", "").split(";")[0].strip().lower()
        if ct not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
            log.warning("[THUMBNAIL] reference not an image: %s", ct)
            return None
        img_b64 = base64.standard_b64encode(r.content).decode("ascii")
    except Exception as e:
        log.warning("[THUMBNAIL] reference fetch error: %s", e)
        return None

    try:
        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        resp = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=512,
            system=_REFERENCE_ANALYSIS_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": ct,
                                "data": img_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Analyze this thumbnail's visual style per the system instructions.",
                        },
                    ],
                }
            ],
        )
        analysis = resp.content[0].text.strip()
        log.warning("[THUMBNAIL] reference analysis: %d chars", len(analysis))
        return analysis
    except Exception as e:
        log.warning("[THUMBNAIL] Claude vision analysis failed: %s", e)
        return None


def _build_thumbnail_prompt(
    title: str,
    talking_points: list[str],
    brand_color: str | None,
    reference_analysis: str | None,
    variant_seed: str,
) -> str:
    """Build an image prompt for a YouTube-style thumbnail.

    HARD CONSTRAINTS baked into every prompt:
    - NO human faces, portraits, or photorealistic people of any kind.
    - NO identifiable real persons, celebrities, or public figures.
    - Use abstract illustrations, typography, icons, geometric shapes,
      isometric diagrams, or stylized objects instead of humans.
    """
    color_hint = ""
    if brand_color:
        color_hint = (
            f"Use {brand_color} as the primary accent color for text, borders, "
            "and graphical elements. "
        )

    points_text = "\n".join(f"  - {p}" for p in talking_points)

    # Sanitize title — strip quotes and any potentially flagged phrasing
    safe_title = title.replace('"', "").replace("'", "").strip()

    base = (
        f"Professional YouTube thumbnail design for a educational video "
        f"about '{safe_title}'. "
        f"Key concepts:\n{points_text}\n\n"
        f"{color_hint}"
        f"Visual style: clean graphic-design composition with bold typography, "
        f"abstract geometric illustrations, and iconography. "
        f"Use isometric diagrams, stylized shapes, charts, or symbolic objects "
        f"to represent the concepts. "
        f"Strong color contrast, clear focal area for overlaid text. "
        f"IMPORTANT: NO human faces, NO people, NO photorealistic humans, "
        f"NO celebrities, NO portraits of any kind. "
        f"Use ONLY abstract art, typography, icons, and geometric designs. "
        f"Professional, educational tone. Clean and polished. "
        f"Creative direction: {variant_seed}."
    )

    if reference_analysis:
        base += (
            f"\n\nDesign reference (adapt visual style only — DO NOT include "
            f"any faces or people from the reference):\n{reference_analysis}\n\n"
            "Match the composition, typography approach, color palette, and energy "
            "of the reference while converting any human elements into abstract "
            "graphic representations. Adapt the style to this video's topic."
        )

    # Trim and add safety suffix
    prompt = base[:3800]
    prompt += (
        " Abstract educational design. No faces. No people. "
        "Graphic design with typography and icons only."
    )
    return prompt[:3900]


async def _generate_one_image(prompt: str) -> str | None:
    """Generate one image via OpenAI and return a data URL."""
    if not settings.OPENAI_API_KEY:
        return None

    model = _resolve_image_model()
    size_override = (settings.OPENAI_IMAGE_SIZE or "").strip()
    q_raw = (settings.OPENAI_IMAGE_QUALITY or "hd").strip().lower()

    # YouTube thumbnails are 16:9, prefer landscape sizes
    if model.startswith("dall-e-3"):
        size = size_override if size_override in {"1792x1024", "1024x1024", "1024x1792"} else "1792x1024"
        qual = q_raw if q_raw in {"standard", "hd"} else "hd"
        kwargs: dict[str, Any] = {
            "model": model,
            "prompt": prompt[:3900],
            "n": 1,
            "size": size,
            "quality": qual,
            "response_format": "b64_json",
        }
    elif model.startswith("gpt-image"):
        size = size_override if size_override else "1536x1024"
        if q_raw in {"high", "medium", "low", "auto"}:
            qual = q_raw
        elif q_raw in {"hd", "best"}:
            qual = "high"
        else:
            qual = "high"
        kwargs = {"model": model, "prompt": prompt[:3900], "n": 1, "size": size, "quality": qual}
    else:
        size = size_override or "1792x1024"
        kwargs = {
            "model": model,
            "prompt": prompt[:3900],
            "n": 1,
            "size": size,
            "response_format": "b64_json",
        }
        if model.startswith("dall-e"):
            kwargs["quality"] = q_raw if q_raw in {"standard", "hd"} else "standard"

    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.images.generate(**kwargs)
        row = resp.data[0]
        b64 = getattr(row, "b64_json", None)
        if b64:
            return f"data:image/png;base64,{b64}"
        log.warning("[THUMBNAIL] no b64_json in response")
        return None
    except Exception as e:
        err_str = str(e).lower()
        # Moderation block — retry with a maximally safe abstract prompt
        if "moderation" in err_str or "safety" in err_str or "blocked" in err_str:
            log.warning(
                "[THUMBNAIL] moderation block, retrying with safe abstract prompt"
            )
            safe_prompt = (
                "Clean professional YouTube thumbnail. Abstract geometric design "
                "with bold typography on a gradient background. Icons, shapes, "
                "and graphic elements only. Educational tech content. "
                "NO faces. NO people. NO humans. NO text that could be "
                "misinterpreted. Safe for all audiences. "
                "Professional brand design style."
            )[:3900]
            kwargs["prompt"] = safe_prompt
            try:
                resp2 = await client.images.generate(**kwargs)
                row2 = resp2.data[0]
                b64 = getattr(row2, "b64_json", None)
                if b64:
                    log.warning("[THUMBNAIL] safe retry succeeded")
                    return f"data:image/png;base64,{b64}"
            except Exception as e2:
                log.warning("[THUMBNAIL] safe retry also failed: %s", e2)
                return None
        log.warning("[THUMBNAIL] image generation failed: %s", e)
        return None


async def run_thumbnail(
    user_id: str,
    session_id: str,
    idea: IdeaSlice,
    script: Script,
    brand_color: str | None,
    reference_url: str | None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Generate thumbnail variants for a studio session.

    Yields AgentEvent-shaped dicts for the WebSocket route.
    Caller must handle persistence (storage upload + artifact insert).
    """
    yield {"type": "agent_start", "agent": "thumbnail_generator"}

    title = (idea.title or "Video").strip()
    points = _top_talking_points(
        script.model_dump() if hasattr(script, "model_dump") else script,
        n=3,
    )

    # Analyze reference if provided
    reference_analysis: str | None = None
    if reference_url:
        cleaned = reference_url.strip()
        if cleaned:
            yield {
                "type": "text_delta",
                "agent": "thumbnail_generator",
                "content": "Analyzing reference thumbnail style…\n",
            }
            reference_analysis = await _analyze_reference_thumbnail(cleaned)
            if reference_analysis:
                yield {
                    "type": "text_delta",
                    "agent": "thumbnail_generator",
                    "content": f"Reference analysis complete.\n",
                }

    # Build prompt + show it
    variants = [
        "Bold typography-forward design with geometric accent shapes and gradient background",
        "Split-panel layout with icon-driven visual metaphors and diagrammatic elements",
        "Minimal clean design with one central abstract graphic element and strong color contrast",
    ]
    count = settings.THUMBNAIL_IMAGE_COUNT

    yield {
        "type": "text_delta",
        "agent": "thumbnail_generator",
        "content": (
            f"Generating {count} thumbnail variants using {_resolve_image_model()}…\n"
            f"Title: {title}\n"
            f"Key points: {', '.join(points[:3])}\n"
            + (f"Brand color: {brand_color}\n" if brand_color else "")
            + (
                f"Reference style: {reference_url}\n"
                if reference_url
                else ""
            )
        ),
    }

    # Generate images
    data_urls: list[str] = []
    for i in range(count):
        variant_seed = variants[i] if i < len(variants) else f"unique creative approach #{i+1}"
        prompt = _build_thumbnail_prompt(
            title, points, brand_color, reference_analysis, variant_seed
        )
        yield {
            "type": "text_delta",
            "agent": "thumbnail_generator",
            "content": f"\nGenerating variant {i+1}/{count}…",
        }
        data_url = await _generate_one_image(prompt)
        if data_url:
            data_urls.append(data_url)
        else:
            yield {
                "type": "text_delta",
                "agent": "thumbnail_generator",
                "content": f" (variant {i+1} failed, continuing)\n",
            }

    if not data_urls:
        yield {
            "type": "error",
            "message": "All thumbnail variants failed to generate. Check your OpenAI API key and model configuration.",
        }
        return

    # Return data URLs + metadata — the WS route handles upload + persist
    yield {
        "type": "thumbnail_ready",
        "variants": [
            {
                "data_url": du,
                "width": 1792,
                "height": 1024,
                "index": i,
            }
            for i, du in enumerate(data_urls)
        ],
    }
