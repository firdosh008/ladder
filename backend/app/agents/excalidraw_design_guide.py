"""Design rules for MCP / canvas-backed diagram generation (education-friendly)."""

from __future__ import annotations

# Context-first illustration rules — templates discouraged; palette & typography locked.
DESIGN_SKILL_SYSTEM_RULES = """
## Prime directive (non-template design)
- **Derive every composition from the supplied script.** Classify what the content *is* (process,
  comparison, hierarchy, causal chain, timeline, network of relationships, quantitative trend,
  abstract metaphor, teaching analogy, etc.), then invent a **single bespoke visual strategy**
  matched to that classification.
- **Never** reach for a habitual pattern because it is easy (generic grids, evenly spaced identical boxes,
  boilerplate left-to-right pipeline diagrams, repeated card stacks). If two unrelated scripts produced
  similar silhouettes, you chose wrong.

## Context-driven visual strategies (examples — not presets)
Pick **one** coherent strategy implied by the script; combine primitives creatively rather than naming a template:
- **Processes / pipelines** → directional motion, branching, merges; emphasize sequence without cloning “Swimlane #3”.
- **Comparisons / tensions** → contrast through asymmetry, split focal regions, mirrored tension — not twin rectangles only.
- **Relationships / ecosystems** → clustered linkage, arcs between actors, weighted connectors — vary topology each time.
- **Hierarchies** → layered elevation, nesting, stepped descent — avoid toy org-chart clichés unless content demands it.
- **Timelines / progression** → spatial progression that fits the narrative arc (not always left→right ticks).
- **Abstract concepts** → metaphorical staging (journey, balance scale, funnel, bridge, terrain) grounded in the wording.

## Adaptive spatial composition
- Each diagram must feel **unique**: vary grouping density, asymmetric balance, radial vs linear emphasis,
  clustered islands vs sparse hero focal areas — justified by meaning, not decoration.
- Use grids **only** when tabular structure is intrinsic to the lesson; otherwise prefer intentional irregular rhythm.

## Visual storytelling (still grounded in primitives)
- Motion cues: arrows, tapered lines, curved connectors, emphasis strokes.
- Where appropriate: lightweight graph motifs (axes hints, segmented curves, annotated anchors).
- Emoji / icons only as **semantic anchors**, sparingly (🎯 ⚠️ ✅ 📈 🔗 …).

## Typography & containment (strict — never compromise)
- No clipped or overflowing text: enlarge shapes or split lines with `\\n`; short phrases inside shapes.
- Keep labels readable and visually centered within shapes.
- Prefer fontFamily **2** unless caller overrides (Studio).

## Locked palette (consistent branding)
- **Primary accent**: orange stroke `#f08c00`, soft fill `#ffec99`.
- **Secondary neutral**: fill `#e9ecef`, stroke `#868e96`.
- **Tertiary / positive emphasis**: stroke `#2f9e44`, fill `#b2f2bb`.
- Background `#ffffff` or very light neutral; cap saturated hues — harmony beats novelty colors.

## Execution polish
- `roughness: 0`; bind arrows/lines where MCP expects ids for geometry stability.
- Maintain macro alignment within intentionally chosen structure (clean joins even when layout is asymmetric).
- Leave intentional whitespace — avoid packing > ~60% of canvas with opaque fills.

## Multi-pass redraw discipline (when instructions mention multiple iterations)
- Later passes **must not** reuse the prior pass’s spatial archetype or connector topology if feedback asks for redesign.
- Treat each full redraw as a **fresh reinterpretation** of the same script with a visibly different composition.
"""

DIAGRAM_JSON_INSTRUCTIONS = """
Return **only valid JSON** (no markdown fences) with this shape:
{
  "content_classification": "<what the script is about structurally — one short phrase>",
  "visual_strategy": "<why this composition fits that classification — one sentence>",
  "layout_style": "<your own concise label for THIS diagram only — not from a fixed enum>",
  "canvas_width": 1600,
  "canvas_height": 900,
  "background_color": "#ffffff",
  "elements": [ ... Excalidraw-style element objects ... ]
}

## Elements
Each element needs `"id"`, `"type"` (`rectangle|ellipse|diamond|text|arrow|line|image`), numeric `x`, `y`,
and `width`/`height` when applicable.
- Combine rectangles sparingly with lines, arrows, ellipses, and standalone `text` for layered storytelling.
- Prefer concise `label`: `{ "text": "..." }` on shapes; dense captions use separate `text` elements when needed.

Arrows may include `"start": {"id": "..."}, "end": {"id": "..."}` alongside `points`.

## Density
Aim for roughly **12–28** substantive elements (guides + connectors count). Quality and clarity beat filler shapes.

## Forbidden shortcuts
Do **not** emit boilerplate enums like repeating `"layout_style":"flowchart"` across unrelated scripts unless the
classification truly warrants flow — vary `layout_style` strings to reflect the bespoke solution each time.
"""

VISION_REVIEW_PROMPT = """You are reviewing a PNG export of an instructional Excalidraw diagram plus element JSON.

Reject templated or repetitive-feeling output even when technically valid.

Checklist:
1. **Context fit** — Does spatial logic reflect the lesson content type (not a generic slide pattern)?
2. **Anti-template** — Avoid approving obviously repetitive compositions (uniform card grids, vanilla pipelines with no twist).
3. **Typography** — No overflow; readable hierarchy.
4. **Alignment craft** — Intentional structure feels deliberate (even if asymmetric).
5. **Palette** — Orange / gray / green families coherent; no rainbow noise.

Respond with **only JSON**:
{
  "approved": true|false,
  "corrections": [
    {
      "id": "<element-id>",
      "patch": { "...only fields to merge on the element..." }
    }
  ],
  "notes": "short rationale"
}

If approved, use an empty corrections array. Patches must use valid Excalidraw element property names only.

**Critical:** Each `"id"` in corrections MUST match an `"id"` in the Elements JSON verbatim.
Never invent placeholders like `"step1"` — canvas updates will fail.
"""
