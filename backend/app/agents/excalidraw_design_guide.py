"""Design rules for MCP / canvas-backed diagram generation (education-friendly)."""

from __future__ import annotations

# Consolidated from excalidraw-skill style guidance + product requirements.
DESIGN_SKILL_SYSTEM_RULES = """
## Audience & language
- Use plain language; avoid jargon unless the lesson script already uses it.
- Support Hindi / Hinglish / mixed metadata: keep Unicode as-is; never strip diacritics.

## Visual language
- Use tasteful emoji as icons where they clarify meaning (🎯 goals, 📋 checklist, ⚠️ caveat).
- For linear lessons, put step numbers inside **small circles** (ellipse elements) paired with captions.

## Typography & boxes
- Prefer fontFamily **2** (Helvetica / normal) for professional lessons unless user asks otherwise.
- Title ~28–32px; section labels ~20–22px; body inside shapes ~14–18px.
- **Center** label text visually inside rectangles and ellipses (`textAlign` is handled client-side,
  but keep labels short (2–6 words per line) and stack with \\n instead of ultra-wide lines).
- Never let text spill outside its frame: widen/tall the shape or split copy across multiple text elements.
- Minimum box for text with a label: ~200×72; increase width for long Latin or Indic strings.

## Palette (cohesive educational look)
- **Primary accent (orange stroke / warm fills)**: stroke `#f08c00`, light fill `#ffec99`.
- **Secondary (neutral cards)**: fill `#e9ecef`, stroke `#868e96`.
- **Tertiary / success highlights**: stroke `#2f9e44`, fill `#b2f2bb`.
- Use at most three fill families per diagram + white/transparent background.
- Canvas background: `#ffffff` or very light neutral.

## Geometry & layout
- Snap to a 50px grid for `x` / `y` positions and spacing multiples of 50 between major blocks.
- Vary layouts: **flowchart**, **timeline**, **hub-and-spoke**, **two-column contrast**, **matrix (2×2)** —
  pick one that matches the script; avoid generic uniform grids unless the content is tabular.
- Use `roughness: 0` for teaching slides; arrows solid for main flow, dashed only for optional/aside paths.
- Bind arrows to shapes where possible (`start`/`end` ids) so the MCP server can compute geometry.

## Quality bar
- Keep consistent vertical rhythm; align siblings to the same `x` or `y`.
- Leave whitespace: do not cover more than ~60% of the canvas with filled shapes.
"""

DIAGRAM_JSON_INSTRUCTIONS = """
Return **only valid JSON** (no markdown fences) with this shape:
{
  "layout_style": "flowchart|timeline|radial|matrix|two_column|hierarchical",
  "canvas_width": 1600,
  "canvas_height": 900,
  "background_color": "#ffffff",
  "elements": [ ... Excalidraw-style element objects ... ]
}

Each element must include: "id", "type" (rectangle|ellipse|diamond|text|arrow|line|image),
numeric "x", "y", and when applicable "width", "height".
For rectangles/ellipses/diamonds with captions, prefer a concise "label": {"text": "..."}.
For standalone text rows, use type "text" with "text": "...".

Arrows may use `"start": {"id": "..."}, "end": {"id": "..."}` in addition to `points`.

Minimum **6** meaningful elements for a lesson scene (excluding pure decorations), at least **2** rectangles.
"""

VISION_REVIEW_PROMPT = """You are reviewing a PNG export of an Excalidraw teaching diagram plus the element JSON.

Decide if the diagram is visually acceptable for learners. Focus on:
- Text overflow outside frames
- Misalignment (ragged columns, uneven spacing)
- Illegibly small fonts
- Clashing colors (too many hues)
- Broken flow (orphan shapes, overlapping labels)

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

If approved, use an empty corrections array. Patches must use the same property names as Excalidraw elements
(width, height, x, y, fontSize, text, label, strokeColor, backgroundColor, points, etc.).

**Critical:** Each `"id"` in corrections MUST be copied **verbatim** from an `"id"` field in the Elements JSON you were given (same spelling and casing).
Never invent semantic placeholders like `"step1"` / `"step2"` — those will fail the canvas API if they are not real ids in that JSON.
"""
