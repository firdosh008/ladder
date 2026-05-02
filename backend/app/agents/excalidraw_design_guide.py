"""Design rules for MCP / canvas-backed diagram generation (education-friendly)."""

from __future__ import annotations

# Context-first + explainer illustration — avoid UI/dashboard aesthetics.
DESIGN_SKILL_SYSTEM_RULES = """
## Prime directive (explain like a human sketched it)
- **Derive every composition from the supplied script** — classify what the content *is*, then invent ONE bespoke
  visual story (whiteboard / magazine explainer energy), **not** a software wireframe or dashboard.
- Shift mindset from **UI layout generation → visual storytelling illustration**: fluid flow, personality, air.

## Anti-UI / anti-dashboard (critical)
- **Do not** build dashboard layouts, modular card grids, boxed “panels,” symmetrical template compositions, or
  repeated **rectangle + caption** stripes that read like a CMS block editor.
- **Do not** imprison the narrative inside heavy rectangles — hierarchy comes from **motion, proximity, scale,
  and connectors**, not enclosures.
- Avoid ruler-perfect modular grids unless the lesson data is explicitly tabular.

## Organic layout & flow
- Place elements with **natural asymmetry** and staggered rhythm — slight intentional irregularity reads human.
- Macro-relationships stay coherent (nothing sloppy overlaps illegibly), but **avoid pixel-perfect repetition**
  across sibling widgets.
- Lead the eye with **arrows and directional spacing** (progressive tightening / widening can imply tempo).

## Hand-crafted connector language
- Prefer **multi-point `arrow` / `line` paths** that bend or arc — gentle curves feel exploratory; reserve only
  occasional short orthogonal hops where clarity demands it (avoid mechanical CAD-style right-angle plumbing everywhere).
- Bind connectors where MCP expects ids when helpful — geometry still needs to survive canvas sync.

## Hierarchy without boxes
- Tell the story through **linked anchors**: icons/emoji callouts (🎯 📈 ⚠️ ✨ …), small focal ellipses,
  standalone `text` lines, light strokes — **not** big tinted panels framing everything.
- When you must use a shape behind copy, prefer **small rounded chips / minimal strokes / whisper fills**
  — never full-width colored slabs.

## Embedded graphs & trends (story-first)
- If numbers or progression appear in the script, weave **simple curves / stepped lines / axis hints** into the
  same narrative plane — graphs belong **inside** the illustration flow, not as a detached chart widget.

## Annotation-style labels
- Favor **floating labels** (compact text near connectors), soft ellipses, or pill-sized backgrounds pointing at ideas —
  explainer annotation energy, not form-field boxes.

## Typography (strict)
- Micro-copy only: bite-sized phrases; break with `\\n` — **no overflow**, no paragraphs trapped in shapes.
- Prefer fontFamily **2** unless caller overrides.

## Color — soft & purposeful
- **Primary accent**: orange `#f08c00` strokes with **light** fills `#ffec99` — use as accents, not dominators.
- **Secondary**: `#e9ecef` / `#868e96`.
- **Tertiary emphasis**: `#2f9e44` / `#b2f2bb`.
- Lots of **paper-white breathing room** — aim ≤ ~55% of canvas covered by opaque fills; airy beats dense.

## Sketch warmth (Excalidraw-native)
- Default **`roughness: 1`** on illustrative strokes/shapes for humane imperfection (still intentional).
  Structural ultra-minimal guides may use `roughness: 0` sparingly if contrast helps readability — avoid sterile freezing.

## Context-driven strategies (still bespoke — examples only)
Processes → flowing directional arcs; comparisons → asymmetric tension fields; networks → clustered organic linkage;
timelines → narrative drift — never clone prior unrelated silhouettes.

## Multi-pass redraw discipline
- Later QA passes must reinvent topology/spatial archetype — never paste the same UI-ish scaffold twice if redesign requested.
"""

DIAGRAM_JSON_INSTRUCTIONS = """
Return **only valid JSON** (no markdown fences) with this shape:
{
  "content_classification": "<structural read of the script — short phrase>",
  "visual_strategy": "<why this explainer composition fits — one sentence>",
  "layout_style": "<your bespoke label for THIS whiteboard sketch — not an enum>",
  "canvas_width": 1600,
  "canvas_height": 900,
  "background_color": "#ffffff",
  "elements": [ ... Excalidraw-style element objects ... ]
}

## Composition mandate
- Think **explainer illustration**: arrows/lines/`ellipse`/`text` carry the story; **`rectangle` use stays minimal**
  (thin ribbons, tiny chips — not dashboard tiles).

## Elements & curves
Each element needs `"id"`, `"type"` (`rectangle|ellipse|diamond|text|arrow|line|image`), numeric `x`, `y`,
and `width`/`height` when applicable.
- Encode curved flow via **`points`** arrays on arrows/lines (multiple segments / subtle bends).
- Optional sketch warmth: `"roughness": 1` on most shapes unless a crisp datum requires `0`.

Arrows may pair `"start": {"id": "..."}, "end": {"id": "..."}` with `points` when bindings help MCP geometry.

## Density
Roughly **12–26** substantive elements — prioritize connectors + annotations over enclosure count.

## Forbidden aesthetics
Symmetrical card dashboards, mirrored widget columns, neon slabs, rainbow clutter, boilerplate repeating `"layout_style"`.
"""

VISION_REVIEW_PROMPT = """You are reviewing a PNG export of an instructional Excalidraw diagram plus element JSON.

Approve only outputs that feel **hand-explained / editorial illustration**, not UI mocks.

Reject when:
- Layout reads as **dashboard, Kanban cards, admin panels**, or repeating boxed sections.
- Dense tinted rectangles dominate instead of flow + connectors.
- Composition is rigid grid symmetry with copy-paste panels (unless pure tabular lesson content).

Still require:
- Zero text overflow; readable hierarchy.
- Cohesive orange / gray / green storytelling palette without rainbow noise.
- Clear intuitive reading order via motion/proximity — even when asymmetric.

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

If approved, use an empty corrections array. Patches must use valid Excalidraw element properties only.

**Critical:** Each `"id"` must match an `"id"` in the Elements JSON verbatim — never placeholders like `"step1"`.
"""
