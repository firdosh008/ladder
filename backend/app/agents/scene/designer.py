"""Element designer — direct Anthropic call with structured outputs.

This step used to be a CrewAI Task with `output_pydantic=SceneSkeleton`, which
is prompted JSON. The model dropped the top-level `elements` array on a large
fraction of runs and failed validation. We replaced it with Anthropic's
grammar-constrained `output_format` so the schema is enforced at sampling
time — the model literally cannot emit tokens that violate `SceneSkeleton`.

The planner still runs as a CrewAI agent (its schema is small + flat and
benefits from CrewAI's streaming). The designer is one-shot non-streaming
because (a) the artifact is structural, not narrative — there's nothing
useful to stream visually, and (b) Anthropic's structured-outputs streaming
ergonomics are more involved and not needed for our UX.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from anthropic import APIError, APIStatusError
from pydantic import ValidationError

from app.agents.scene.skeleton_scene_cleanup import (
    enforce_brand_dominance,
    enforce_font_family,
    enforce_readable_colors,
    repair_arrow_bindings,
    sync_canvas_from_layout,
    wrap_scene_text_elements,
)
from app.agents.scene.skeleton_text_layout import repack_rect_body_text_below_labels
from app.agents.scene.tasks import _outline_dump, _script_full
from app.config import settings
from app.models.db import (
    IdeaSlice,
    Outline,
    SceneLayout,
    SceneSkeleton,
    Script,
    UserProfileSlice,
)
from app.services.llm import (
    ANTHROPIC_STRUCTURED_OUTPUTS_BETA,
    anthropic_client,
)

log = logging.getLogger(__name__)


def _profile_block(profile: UserProfileSlice) -> str:
    parts = [
        f"Founder: {profile.display_name or 'unknown'}",
        f"Positioning: {profile.positioning or 'not specified'}",
        f"Audience: {profile.audience or 'not specified'}",
    ]
    if profile.things_to_avoid:
        parts.append(f"Things to avoid: {profile.things_to_avoid}")
    return "\n".join(parts)


def _idea_block(idea: IdeaSlice) -> str:
    parts = [f"Title: {idea.title}"]
    if idea.idea_type:
        parts.append(f"Idea type: {idea.idea_type}")
    if idea.rationale:
        parts.append(f"Rationale: {idea.rationale}")
    return "\n".join(parts)


def _layout_block(layout: SceneLayout) -> str:
    lines = [
        f"Canvas: {layout.canvas_width} × {layout.canvas_height}",
        f"Background: {layout.background_color}",
        f"Flow: {layout.flow_direction}",
        "Frames:",
    ]
    for f in layout.frames:
        lines.append(
            f"  {f.number}. [{f.kind}] {f.label} — "
            f"x={f.x} y={f.y} w={f.width} h={f.height}"
        )
        if f.description:
            lines.append(f"     intent: {f.description}")
    return "\n".join(lines)


_DEFAULT_BRAND_COLOR = "#E8442A"

# Excalidraw built-in fontFamily integers; rendered names/styles per Excalidraw
# 0.18.x source: 1=Virgil, 2=Helvetica (sans/Arial-like), 3=Cascadia (mono),
# 5=Excalifont (default hand-drawn), 6=Nunito (rounded), 7=Lilita One (display),
# 8=Comic Shanns, 9=Liberation Sans.
_FONT_FAMILY_NOTE = {
    1: "Virgil (hand-drawn, Excalidraw classic)",
    2: "Helvetica (clean sans — renders as system Arial / Helvetica / SF on macOS)",
    3: "Cascadia (monospace)",
    5: "Excalifont (hand-drawn default)",
    6: "Nunito (rounded sans)",
    7: "Lilita One (bold display)",
    8: "Comic Shanns (handwriting)",
    9: "Liberation Sans (neutral sans)",
}


def _system_prompt(brand_color: str, font_family: int | None) -> str:
    font_clause = ""
    if font_family is not None:
        note = _FONT_FAMILY_NOTE.get(font_family, "Excalidraw built-in")
        font_clause = (
            f"\n  • Set `fontFamily: {font_family}` on EVERY `text` element AND on "
            f"`label.text`-bearing shapes (so the bound caption inherits it). "
            f"Font: {note}. Do not vary the family across elements."
        )
    return _build_system_prompt(brand_color, font_clause)


def _build_system_prompt(brand_color: str, font_clause: str) -> str:
    return f"""You produce ExcalidrawElementSkeleton JSON. The host app inflates your output via convertToExcalidrawElements() — your field names map 1:1 to that API.

Per-frame element rules (use the frame's `kind`):
  • title    — one centered rectangle (filled {brand_color} bg, white label) holding the frame label.
  • flow     — 2-4 rectangles connected by arrows showing the sequence; each rectangle labelled with its step.
  • table    — 2-column grid of rectangles (e.g. 'Wrong' vs 'Right'); 4-6 cells with a header row.
  • decision — diamond at top, 2-3 rectangles below, arrows from the diamond labelled with the branch condition.
  • architecture — stacked rectangles (layers) with thin arrows between them.
  • checklist — 3-6 small ellipses (bullets) with a text element next to each.
  • cta / diagram — pick the closest of the above.

Hard rules:
  • **Icons:** Prefix **every** shape `label.text` and every prominent standalone `type:text` heading with **one** Unicode emoji (single grapheme) that matches the idea — e.g. ⚡ 💡 ✅ 🎯 📌 🔑 🚀 📊 🧭 ✨ — so the board reads icon-forward like a polished slide deck.
  • **Citations:** When you put a statistic, percentage, or attributed finding onto a shape label or text element, you MUST preserve the `[source:N]` citation tag from the script verbatim. Example — shape label: '📊 73% struggle with pricing [source:3]'. Example — text element: 'McKinsey: AI adoption tripled since 2022 [source:7]'. Never strip [source:N] tags — the viewer needs to know where data came from.
  • Every shape stays strictly inside its frame's bounding box (use the planner's x/y/width/height as a hard clamp). At least 24px internal padding.
  • Every element has a unique stable string id ('f1-box', 'arrow-1-2', etc).
  • Arrows reference start/end via {{id: '<element-id>'}}. Referenced ids MUST exist and MUST point only to rectangle, diamond, or ellipse elements — NEVER bind arrow endpoints to type:text (broken arrows / inverted geometry).
  • Style: roughness=1, strokeWidth=2. Canvas is **white (#FFFFFF)** — standalone type:text MUST use strokeColor='#1F2937' (dark grey — readable body copy). Arrow and line shafts MUST use strokeColor='#1F2937'. **Brand color '{brand_color}' is the DOMINANT fill on this board** — at least ~60-70% of rectangle/diamond/ellipse shapes (across title, flow, decision, table, architecture frames) MUST use fillStyle='solid' with backgroundColor='{brand_color}' and strokeColor='#FFFFFF' so bound labels render in white on the brand fill. Leave roughly 1 in 3 shapes per frame as wireframe (no fill) with strokeColor='#1F2937' for visual rhythm — do not paint every shape. Title/cta cards ALWAYS use the brand fill. Wireframe rectangles/diamonds use strokeColor='#1F2937'. Never use #FFFFFF / white / near-white strokeColor on unfilled shapes or on type:text — invisible on white.
  • Text elements use the `text` field (not `label`). Shape elements with bound captions use `label.text`.
  • Shape labels are SHORT titles (≤48 chars, single line — Excalidraw centers them in the shape). For multi-line content, paragraphs, or bullet lists, use a separate `type: "text"` element **below the title strip**: `x = rect.x + 12`, `y = rect.y + 40`, `width = rect.width - 24`, `height` filling the rest of the card — never center that body at the rectangle's midpoint (it overlaps the bound label). Never cram long copy into `label.text`.
  • **Body `type:text`:** give each block a **realistic `width`** (≥180px for paragraphs). Long sentences must either use explicit newline characters (`\\n`) between lines **or** rely on that width — the app reflows single-line blobs to ~12–56 chars per line. Set `height` generously when you expect multiple lines (≥ `line_count × fontSize × 1.25`).
  • Width and height for every rectangle, diamond, ellipse, and similar shape must be **positive** (greater than zero). Never use negative width or height — reposition with `x`/`y` instead of flipping signs.
  • Add ONE text element near the top of the canvas with the video title (use the first outline label).
  • Aim for 12-40 elements total — vary shape sizes by importance, never produce a uniform grid.{font_clause}"""


_UNSUPPORTED_SCHEMA_KEYS = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "pattern",
    "format",
    "not",
    "if",
    "then",
    "else",
    "default",
}


def _clean_schema(node: Any) -> Any:
    """Adapt a Pydantic-emitted JSON Schema to Anthropic's structured-outputs
    grammar compiler:

      • Strip keywords the compiler rejects (numeric/string bounds, formats,
        defaults). Pydantic re-validates server-side as defence in depth.
      • Force every `object` node to set `additionalProperties: false`
        explicitly — Anthropic 400s without it ("For 'object' type,
        'additionalProperties' must be explicitly set to false").
    """
    if isinstance(node, dict):
        cleaned = {
            k: _clean_schema(v)
            for k, v in node.items()
            if k not in _UNSUPPORTED_SCHEMA_KEYS
        }
        if cleaned.get("type") == "object":
            cleaned["additionalProperties"] = False
        return cleaned
    if isinstance(node, list):
        return [_clean_schema(v) for v in node]
    return node


def _scene_skeleton_schema() -> dict[str, Any]:
    return _clean_schema(SceneSkeleton.model_json_schema())


_STRUCTURED_RETRIES = 2  # 3 attempts total, with 1.5s + 4s backoff
_FALLBACK_REPAIR_ATTEMPTS = 1  # one self-correction pass on prompted JSON


def _truncate_to_caps(payload: Any) -> Any:
    """Walk a SceneSkeleton payload and clip any over-cap strings to the
    relevant Pydantic max_length. Anthropic's grammar compiler doesn't
    enforce maxLength, so models occasionally over-run on labels/text. We
    salvage rather than fail — a truncated scene is better than a 500."""
    if not isinstance(payload, dict):
        return payload
    notes = payload.get("notes")
    if isinstance(notes, str) and len(notes) > 4000:
        payload["notes"] = notes[:4000]
    elements = payload.get("elements")
    if isinstance(elements, list):
        for el in elements:
            if not isinstance(el, dict):
                continue
            t = el.get("text")
            if isinstance(t, str) and len(t) > 4000:
                el["text"] = t[:4000]
            label = el.get("label")
            if isinstance(label, dict):
                lt = label.get("text")
                if isinstance(lt, str) and len(lt) > 2000:
                    label["text"] = lt[:2000]
            eid = el.get("id")
            if isinstance(eid, str) and len(eid) > 64:
                el["id"] = eid[:64]
    return payload


_ELEM_DIM_MAX = 8000.0


def _sanitize_scene_geometry(payload: Any) -> Any:
    """Coerce illegal dimensions Anthropic occasionally emits (-width, mega-h).

    Excalidraw skeleton uses non-negative extents; negatives fail Pydantic
    ``Field(ge=0)``. We salvage with ``abs`` + cap so a run does not die on
    one bad number (common when structured outputs fall back to plain JSON).
    """
    if not isinstance(payload, dict):
        return payload
    elements = payload.get("elements")
    if not isinstance(elements, list):
        return payload
    fixed = 0
    for el in elements:
        if not isinstance(el, dict):
            continue
        for dim in ("width", "height"):
            if dim not in el:
                continue
            raw = el[dim]
            try:
                fv = float(raw)
            except (TypeError, ValueError):
                continue
            if fv < 0 or fv > _ELEM_DIM_MAX:
                el[dim] = min(_ELEM_DIM_MAX, abs(fv))
                fixed += 1
    if fixed:
        log.warning(
            "designer salvaged %d negative/out-of-cap width/height value(s)",
            fixed,
        )
    return payload


def _validate_with_salvage(payload: Any) -> SceneSkeleton:
    """Try strict validation; on length errors, truncate and retry once."""
    if isinstance(payload, dict):
        _sanitize_scene_geometry(payload)
        _truncate_to_caps(payload)
    try:
        return SceneSkeleton.model_validate(payload)
    except ValidationError as e:
        # Only attempt salvage if every error is a length cap. Real shape
        # mismatches (missing fields, wrong types) should still raise.
        if not all(err["type"].endswith("_too_long") for err in e.errors()):
            raise
        log.warning(
            "designer payload exceeded length caps on %d field(s); truncating",
            len(e.errors()),
        )
        if isinstance(payload, dict):
            _sanitize_scene_geometry(payload)
            _truncate_to_caps(payload)
        return SceneSkeleton.model_validate(payload)


def _finalize_skeleton(
    skeleton: SceneSkeleton,
    layout: SceneLayout,
    brand_color: str | None = None,
    font_family: int | None = None,
) -> SceneSkeleton:
    """Deterministic cleanup after the model (geometry, brand, contrast, arrows).

    Order matters:
      1. canvas + text geometry (no color/font work)
      2. ``enforce_brand_dominance`` paints unfilled shapes with the brand
         color BEFORE contrast fix runs — that way ``enforce_readable_colors``
         flips bound-label strokes to white on the freshly-painted dark fills.
      3. ``enforce_font_family`` stamps the picker selection on every text
         element + bound label so the user-chosen font is guaranteed.
    """
    sk = sync_canvas_from_layout(skeleton, layout)
    sk = repack_rect_body_text_below_labels(sk, layout)
    sk = wrap_scene_text_elements(sk)
    sk = enforce_brand_dominance(sk, brand_color)
    sk = enforce_readable_colors(sk)
    sk = enforce_font_family(sk, font_family)
    sk = repair_arrow_bindings(sk)
    return sk


def _is_overloaded(err: APIError) -> bool:
    """True if the error is the transient grammar-compiler / overload class."""
    if isinstance(err, APIStatusError) and err.status_code in (429, 503, 529):
        return True
    body = getattr(err, "body", None) or {}
    err_obj = (body or {}).get("error", {}) if isinstance(body, dict) else {}
    if err_obj.get("type") in {"overloaded_error", "rate_limit_error"}:
        return True
    msg = str(err)
    return "overloaded" in msg.lower() or "grammar compilation" in msg.lower()


def _is_schema_too_complex(err: APIError) -> bool:
    """Anthropic structured-outputs grammar rejects oversized / intricate JSON Schema."""
    body = getattr(err, "body", None) or {}
    msg = ""
    if isinstance(body, dict):
        eo = body.get("error")
        if isinstance(eo, dict):
            msg = str(eo.get("message") or "")
    blob = (msg + " " + str(err)).lower()
    return "schema is too complex" in blob


def _extract_text(response: Any) -> str:
    block = next(
        (b for b in response.content if getattr(b, "type", None) == "text"),
        None,
    )
    if block is None:
        raise RuntimeError("designer returned no text block")
    return block.text


def _extract_json(text: str) -> str:
    """Some responses wrap JSON in ```json fences or add prose around it.
    Pull out the first {...} blob; falls back to the raw text."""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1)
    obj = re.search(r"\{.*\}", text, re.DOTALL)
    return obj.group(0) if obj else text


async def _structured_attempt(
    client: Any,
    schema: dict[str, Any],
    user_prompt: str,
    system_prompt: str,
) -> Any:
    return await client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=8192,
        temperature=0.25,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        extra_headers={"anthropic-beta": ANTHROPIC_STRUCTURED_OUTPUTS_BETA},
        extra_body={
            "output_format": {"type": "json_schema", "schema": schema}
        },
    )


async def _prompted_attempt(
    client: Any,
    user_prompt: str,
    system_prompt: str,
    repair_hint: str | None = None,
) -> Any:
    """Fallback when the structured-outputs grammar compiler is unavailable.
    Same system prompt, no `output_format`, asks for raw JSON. We post-validate
    with Pydantic and optionally self-correct once."""
    sys_with_schema = (
        system_prompt
        + "\n\nReturn ONE JSON object matching this schema (no prose, no fences):\n"
        + json.dumps(SceneSkeleton.model_json_schema(), separators=(",", ":"))
    )
    messages: list[dict[str, str]] = [{"role": "user", "content": user_prompt}]
    if repair_hint:
        messages.append({"role": "user", "content": repair_hint})
    return await client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=8192,
        temperature=0.25,
        system=sys_with_schema,
        messages=messages,
    )


async def run_designer(
    profile: UserProfileSlice,
    idea: IdeaSlice,
    layout: SceneLayout,
    script: Script,
    outline: Outline,
    brand_color: str | None = None,
    font_family: int | None = None,
) -> tuple[SceneSkeleton, int, int]:
    """Generate the SceneSkeleton.

    Strategy:
      1. Anthropic structured outputs (grammar-constrained) — preferred when
         ``SCENE_DESIGNER_STRUCTURED_OUTPUTS`` is on (default). On 400
         "Schema is too complex" we fall through immediately to prompted JSON.
      2. Retry on transient overload (`overloaded_error`, 503, 529).
      3. Fall back to prompted JSON with Pydantic post-validation and one
         self-correction pass if structured outputs stays unavailable.

    `brand_color` (optional 7-char hex) is interpolated into the system
    prompt as the primary accent color for filled cards + accent strokes.
    Falls back to the PRD default cinnabar when None.

    Returns (skeleton, input_tokens, output_tokens). Raises only when every
    path is exhausted.
    """
    client = anthropic_client()
    system_prompt = _system_prompt(
        brand_color or _DEFAULT_BRAND_COLOR, font_family
    )

    user_prompt = (
        f"{_profile_block(profile)}\n\n"
        f"{_idea_block(idea)}\n\n"
        f"Approved scene layout:\n{_layout_block(layout)}\n\n"
        f"Outline beats:\n{_outline_dump(outline)}\n\n"
        f"Script (approved talking points — reuse these phrases + citations):\n{_script_full(script)}\n\n"
        "Return a SceneSkeleton with at least 12 elements that fills every "
        "frame in the layout above. Match each frame's kind. Labels MUST "
        "match the frame labels verbatim — that's how screenshot-to-edit "
        "later locates them."
    )

    # 1 + 2: structured outputs with retry on transient overload (unless gated off).
    last_structured_error: APIError | None = None
    if settings.SCENE_DESIGNER_STRUCTURED_OUTPUTS:
        schema = _scene_skeleton_schema()
        for attempt in range(_STRUCTURED_RETRIES + 1):
            try:
                response = await _structured_attempt(
                    client, schema, user_prompt, system_prompt
                )
                payload = json.loads(_extract_text(response))
                skeleton = _finalize_skeleton(
                    _validate_with_salvage(payload),
                    layout,
                    brand_color=brand_color or _DEFAULT_BRAND_COLOR,
                    font_family=font_family,
                )
                usage = response.usage
                return (
                    skeleton,
                    int(getattr(usage, "input_tokens", 0) or 0),
                    int(getattr(usage, "output_tokens", 0) or 0),
                )
            except APIError as e:
                if _is_schema_too_complex(e):
                    log.warning(
                        "structured outputs rejected SceneSkeleton schema as too complex — "
                        "falling back to prompted JSON: %s",
                        e,
                    )
                    last_structured_error = e
                    break
                if _is_overloaded(e) and attempt < _STRUCTURED_RETRIES:
                    backoff = 1.5 * (2 ** attempt)
                    log.warning(
                        "structured outputs overloaded (attempt %d/%d), "
                        "backing off %.1fs: %s",
                        attempt + 1, _STRUCTURED_RETRIES + 1, backoff, e,
                    )
                    await asyncio.sleep(backoff)
                    last_structured_error = e
                    continue
                if _is_overloaded(e):
                    log.warning(
                        "structured outputs still overloaded after %d retries — "
                        "falling back to prompted JSON: %s",
                        _STRUCTURED_RETRIES, e,
                    )
                    last_structured_error = e
                    break
                raise RuntimeError(f"designer API call failed: {e}") from e
            except (json.JSONDecodeError, ValidationError) as e:
                # Should be ~impossible with grammar-constrained sampling. If it
                # ever happens, surface it loudly rather than masking — the schema
                # cleaner is probably wrong.
                raise RuntimeError(
                    f"designer returned invalid payload from structured outputs: {e}"
                ) from e
    else:
        log.info(
            "scene designer skipping structured outputs "
            "(SCENE_DESIGNER_STRUCTURED_OUTPUTS=false); using prompted JSON path."
        )

    # 3: prompted-JSON fallback with one repair pass.
    repair_hint: str | None = None
    last_error: Exception | None = last_structured_error
    for attempt in range(_FALLBACK_REPAIR_ATTEMPTS + 1):
        try:
            response = await _prompted_attempt(
                client, user_prompt, system_prompt, repair_hint
            )
            text = _extract_text(response)
            payload = json.loads(_extract_json(text))
            skeleton = _finalize_skeleton(_validate_with_salvage(payload), layout)
            usage = response.usage
            log.info("designer succeeded via prompted-JSON fallback")
            return (
                skeleton,
                int(getattr(usage, "input_tokens", 0) or 0),
                int(getattr(usage, "output_tokens", 0) or 0),
            )
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            repair_hint = (
                "Your previous response was rejected by validation: "
                f"{e}\nReturn ONLY the corrected SceneSkeleton JSON (no prose, "
                "no fences). The top-level object MUST include `elements` "
                "with at least 2 ExcalidrawElementSkeleton items."
            )
            log.warning(
                "prompted-JSON attempt %d/%d failed validation: %s",
                attempt + 1, _FALLBACK_REPAIR_ATTEMPTS + 1, e,
            )
        except APIError as e:
            raise RuntimeError(f"designer fallback API call failed: {e}") from e

    raise RuntimeError(
        f"designer exhausted all retries (structured + fallback): {last_error}"
    )
