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

from app.agents.scene.tasks import _outline_dump, _script_summary
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


SYSTEM_PROMPT = """You produce ExcalidrawElementSkeleton JSON. The host app inflates your output via convertToExcalidrawElements() — your field names map 1:1 to that API.

Per-frame element rules (use the frame's `kind`):
  • title    — one centered rectangle (filled #E8442A bg, white label) holding the frame label.
  • flow     — 2-4 rectangles connected by arrows showing the sequence; each rectangle labelled with its step.
  • table    — 2-column grid of rectangles (e.g. 'Wrong' vs 'Right'); 4-6 cells with a header row.
  • decision — diamond at top, 2-3 rectangles below, arrows from the diamond labelled with the branch condition.
  • architecture — stacked rectangles (layers) with thin arrows between them.
  • checklist — 3-6 small ellipses (bullets) with a text element next to each.
  • cta / diagram — pick the closest of the above.

Hard rules:
  • Every shape stays strictly inside its frame's bounding box (use the planner's x/y/width/height as a hard clamp). At least 24px internal padding.
  • Every element has a unique stable string id ('f1-box', 'arrow-1-2', etc).
  • Arrows reference start/end via {id: '<element-id>'}. Referenced ids MUST exist in the same elements list.
  • Style: roughness=1, strokeWidth=2. Title/cta cards use fillStyle='solid' with backgroundColor='#E8442A'. Other shapes have no fill. strokeColor='#F5F5F5' on the dark canvas, '#E8442A' for accent strokes.
  • Text elements use the `text` field (not `label`). Shape elements with bound captions use `label.text`.
  • Shape labels are SHORT captions (≤80 chars, single line — they render inside the shape and overflow looks ugly). For multi-line content, paragraphs, or bullet lists, use a separate `text` element positioned next to the shape — never cram them into `label.text`.
  • Add ONE text element near the top of the canvas with the video title (use the first outline label).
  • Aim for 12-40 elements total — vary shape sizes by importance, never produce a uniform grid."""


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


def _validate_with_salvage(payload: Any) -> SceneSkeleton:
    """Try strict validation; on length errors, truncate and retry once."""
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
        return SceneSkeleton.model_validate(_truncate_to_caps(payload))


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
) -> Any:
    return await client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=8192,
        temperature=0.25,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        extra_headers={"anthropic-beta": ANTHROPIC_STRUCTURED_OUTPUTS_BETA},
        extra_body={
            "output_format": {"type": "json_schema", "schema": schema}
        },
    )


async def _prompted_attempt(
    client: Any,
    user_prompt: str,
    repair_hint: str | None = None,
) -> Any:
    """Fallback when the structured-outputs grammar compiler is unavailable.
    Same system prompt, no `output_format`, asks for raw JSON. We post-validate
    with Pydantic and optionally self-correct once."""
    sys_with_schema = (
        SYSTEM_PROMPT
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
) -> tuple[SceneSkeleton, int, int]:
    """Generate the SceneSkeleton.

    Strategy:
      1. Anthropic structured outputs (grammar-constrained) — preferred.
      2. Retry on transient overload (`overloaded_error`, 503, 529).
      3. Fall back to prompted JSON with Pydantic post-validation and one
         self-correction pass if structured outputs stays unavailable.

    Returns (skeleton, input_tokens, output_tokens). Raises only when every
    path is exhausted.
    """
    client = anthropic_client()
    schema = _scene_skeleton_schema()

    user_prompt = (
        f"{_profile_block(profile)}\n\n"
        f"{_idea_block(idea)}\n\n"
        f"Approved scene layout:\n{_layout_block(layout)}\n\n"
        f"Outline beats:\n{_outline_dump(outline)}\n\n"
        f"Script context (runtime sense):\n{_script_summary(script)}\n\n"
        "Return a SceneSkeleton with at least 12 elements that fills every "
        "frame in the layout above. Match each frame's kind. Labels MUST "
        "match the frame labels verbatim — that's how screenshot-to-edit "
        "later locates them."
    )

    # 1 + 2: structured outputs with retry on transient overload.
    last_overload: APIError | None = None
    for attempt in range(_STRUCTURED_RETRIES + 1):
        try:
            response = await _structured_attempt(client, schema, user_prompt)
            payload = json.loads(_extract_text(response))
            skeleton = _validate_with_salvage(payload)
            usage = response.usage
            return (
                skeleton,
                int(getattr(usage, "input_tokens", 0) or 0),
                int(getattr(usage, "output_tokens", 0) or 0),
            )
        except APIError as e:
            if _is_overloaded(e) and attempt < _STRUCTURED_RETRIES:
                backoff = 1.5 * (2 ** attempt)
                log.warning(
                    "structured outputs overloaded (attempt %d/%d), "
                    "backing off %.1fs: %s",
                    attempt + 1, _STRUCTURED_RETRIES + 1, backoff, e,
                )
                await asyncio.sleep(backoff)
                last_overload = e
                continue
            if _is_overloaded(e):
                log.warning(
                    "structured outputs still overloaded after %d retries — "
                    "falling back to prompted JSON: %s",
                    _STRUCTURED_RETRIES, e,
                )
                last_overload = e
                break
            raise RuntimeError(f"designer API call failed: {e}") from e
        except (json.JSONDecodeError, ValidationError) as e:
            # Should be ~impossible with grammar-constrained sampling. If it
            # ever happens, surface it loudly rather than masking — the schema
            # cleaner is probably wrong.
            raise RuntimeError(
                f"designer returned invalid payload from structured outputs: {e}"
            ) from e

    # 3: prompted-JSON fallback with one repair pass.
    repair_hint: str | None = None
    last_error: Exception | None = last_overload
    for attempt in range(_FALLBACK_REPAIR_ATTEMPTS + 1):
        try:
            response = await _prompted_attempt(client, user_prompt, repair_hint)
            text = _extract_text(response)
            payload = json.loads(_extract_json(text))
            skeleton = _validate_with_salvage(payload)
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
