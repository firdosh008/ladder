"""Design rules for MCP / canvas-backed diagram generation (education-friendly).

Aesthetic target: annotated whiteboard explainer in the spirit of a hand-drawn
infographic — pastel pill callouts with emoji, highlighter swipes for emphasis,
hand-drawn curving arrows, embedded chart-as-story when numbers exist. Never a
software dashboard.
"""

from __future__ import annotations

# Context-first explainer illustration — pastel pill callouts + highlighter swipes,
# anti UI-dashboard, hand-drawn warmth.
DESIGN_SKILL_SYSTEM_RULES = """
## Prime directive (annotated whiteboard explainer)
- **Derive every composition from the supplied script** — classify what the content *is* (process,
  comparison, hierarchy, journey, quantitative arc, metaphor, teaching analogy), then invent ONE
  bespoke hand-drawn story.
- Mindset is **whiteboard infographic**, not UI mockup. Imagine a designer sketching the lesson
  on paper with pastel markers, pinning callouts with curved arrows, and underlining the punchline.
- The diagram must read as a **single visual argument** — one focal narrative, not multiple panels.

## Anti-UI / anti-dashboard (HARD reject)
- **No** dashboard layouts, modular card grids, boxed "panels," symmetrical template compositions,
  CMS-style rectangle+caption stripes, mirrored widget columns, neon slabs, or rainbow clutter.
- **Do not** imprison the narrative inside heavy rectangles — hierarchy comes from **motion,
  proximity, scale, color, and curved connectors**, not enclosures.
- Use containers for **<30%** of text — most labels float free with typographic hierarchy carrying weight.
- Avoid ruler-perfect modular grids unless the lesson data is genuinely tabular.

## The four signature patterns (use liberally — these define the look)

### Pattern A — Pastel pill callout with emoji
A small, rounded rectangle with a **light pastel fill**, **darker matching stroke**, and a label
that **starts with a single semantic emoji**. Pills float in whitespace and connect to anchors via
curved arrows. Width ≈ `12 + len(label) * 9`, height 38–48, `roughness: 1`, `roundness: {"type": 3}`.

```json
{ "id":"pill-test1", "type":"rectangle", "x":160, "y":480, "width":190, "height":44,
  "strokeColor":"#1971c2", "backgroundColor":"#a5d8ff", "fillStyle":"solid",
  "strokeWidth":2, "strokeStyle":"solid", "roughness":1, "opacity":100,
  "roundness":{"type":3}, "label":{ "text":"💡 Test #1", "fontSize":18 } }
```

### Pattern B — Hand-drawn curving callout arrow (3+ points, gentle arc)
Connector from a pill to its anchor on the chart / diagram. **Always multi-point** (≥3) so the line
arcs naturally — never single-segment ruler arrows. `roughness: 1`, `strokeWidth: 2`, end-arrowhead.

```json
{ "id":"arr-test1", "type":"arrow", "x":260, "y":522, "width":40, "height":80,
  "strokeColor":"#1971c2", "strokeWidth":2, "strokeStyle":"solid", "roughness":1,
  "points":[[0,0],[18,30],[40,80]], "endArrowhead":"arrow",
  "startBinding":{"elementId":"pill-test1","focus":0,"gap":4},
  "endBinding":{"elementId":"chart-pt-1","focus":0,"gap":4} }
```

### Pattern C — Highlighter swipe (semi-transparent thick stroke)
The pastel "marker underline" under a key headline, beneath a chart trend, or behind a punchline
caption. Sits **behind** the primary line/text (lower z by ordering it earlier in `elements`).
Thick (`strokeWidth: 6–10`), translucent (`opacity: 40–60`), maximally rough (`roughness: 2`),
in the **mint** family by default.

```json
{ "id":"hl-trend", "type":"line", "x":140, "y":612, "width":620, "height":-380,
  "strokeColor":"#b2f2bb", "strokeWidth":8, "roughness":2, "opacity":50,
  "points":[[0,0],[620,-380]] }
```

### Pattern D — Embedded chart-as-story (when the script implies numbers / progression)
- Two `line` elements for axes (vertical y, horizontal x) in **ink** `#1e293b`, `strokeWidth: 2`,
  `roughness: 1`, with a small arrowhead at the far tip (`endArrowhead:"arrow"` on each axis line).
- Tick labels as **free-floating `text`** elements, not in containers.
- Floating axis titles ("Reply Rate", "Days") near the axis tip — never centered or boxed.
- The data series itself is **dual-stroke**: a Pattern C highlighter underlay in mint *plus* a
  thinner dark line on top in ink. This is what makes a whiteboard chart feel hand-drawn.
- Data points are small filled ellipses (10–12 px), `fillStyle: "solid"`.

## Color — soft pastel infographic palette
Pair a **darker stroke** with a **lighter fill** on every shape. Use color for *meaning*, not decoration.

| Family | Stroke | Fill | When |
|---|---|---|---|
| Sky (input / neutral primary) | `#1971c2` | `#a5d8ff` | start beats, info pills, primary callouts |
| Mint (progress / success / highlighter) | `#2f9e44` | `#b2f2bb` | step-through callouts, success, **highlighter swipes** |
| Peach (discovery / mid-flow) | `#e8590c` | `#ffd8a8` | second/third beats, "in the middle" callouts |
| Lavender (outcome / aha) | `#6741d9` | `#d0bfff` | results, finales, the *purple "Result"* moment |
| Sun (decision / warm accent) | `#f08c00` | `#ffec99` | decisions, warnings, gentle accents |
| Rose (caution / contrast) | `#c92a2a` | `#ffc9c9` | rare — only when contrast genuinely earns it |
| Ink (text + axes + dark overlay) | `#1e293b` | — | primary text, axis lines, the thin overlay on dual-stroke series |
| Mist (muted secondary) | `#868e96` | `#e9ecef` | secondary annotations, subdued labels |

Background canvas: `#ffffff` (or `#fafaf9`). **Aim ≤ 50% of the canvas covered by opaque fills** —
paper-white breathing room is half the look.

## Hierarchy without boxes
- Tell the story through **linked anchors**: emoji + text pills (Pattern A), small focal ellipses,
  standalone `text` lines, light strokes — **not** big tinted panels framing everything.
- When you must use a shape behind copy, prefer **small rounded chips / minimal strokes / whisper
  fills** — never full-width colored slabs.

## Typography (strict)
- Bite-sized phrases. Break long lines with `\\n`. **Never overflow** a shape — pre-wrap aggressively.
- Pill labels: ~2–4 words plus emoji prefix. Headline banners: ≤8 words.
- Default `fontFamily: 2` (Helvetica) for clean labels; `fontFamily: 1` (Virgil hand-drawn) is
  acceptable for the **headline only** when the lesson is playful. Caller may override via prompt.

## Sketch warmth (Excalidraw-native)
- **Default `roughness: 1`** for everything illustrative — pills, arrows, axes, data lines.
- **`roughness: 2`** on highlighter swipes (Pattern C) so the marker feel reads.
- **`roughness: 0`** is reserved for crisp data anchors (small dots) where wobble would obscure
  the value. Avoid it elsewhere — it freezes the warmth.
- `roundness: {"type": 3}` on all rectangles you keep. Sharp corners are the dashboard tell.

## Headline / banner energy
Open the canvas with a **single bold headline** in 24–36 px, optionally seated on a soft pastel
strip (rounded rectangle, full-width-ish, light fill, `roughness: 1`). Skip the strip when the
canvas is already busy below — the headline alone often does the job. **No** flag-ribbon
ornament unless the lesson is genuinely festive.

## Composition mandate
- ONE focal narrative. If a chart fits, the chart is the focal — annotations orbit it.
- Stagger pill positions with **natural asymmetry**: never line them up on the same y-axis
  unless they're literally tick labels.
- Lead the eye with arrows + directional spacing. Tighten spacing toward the climax (the
  Result pill); loosen it at the start.
- Reserve the **lavender / "Result"** family for the single most important payoff in the diagram.
- Macro relationships stay coherent (no illegible overlaps), but **avoid pixel-perfect repetition**
  across sibling widgets — slight intentional irregularity reads human.

## Multi-pass redraw discipline
Later QA passes must **abandon** the prior pass's spatial archetype if redesign was requested —
never paste the same UI-ish scaffold twice. Re-classify the script if needed and design a
visibly different diagram while keeping the palette + typography constraints.
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

## Composition mandate (read first)
- Think **annotated whiteboard explainer**: arrows / lines / `ellipse` / `text` carry the story;
  `rectangle` use stays minimal and only as **rounded pastel pills** (Pattern A) — never as
  dashboard tiles or full-width slabs.
- Aim for a single focal narrative. Pills orbit the focal element via curved arrows (Pattern B).

## Element basics
Each element needs `"id"`, `"type"` (`rectangle|ellipse|diamond|text|arrow|line|image`), numeric
`x`, `y`, and `width`/`height` when applicable.

Every shape (rectangle / ellipse / diamond) should carry:
- `"strokeColor"` + `"backgroundColor"` from the palette in the system rules (darker stroke,
  lighter fill — paired family).
- `"fillStyle":"solid"`, `"strokeWidth":2`, `"strokeStyle":"solid"`, `"opacity":100`.
- `"roughness":1` (or `2` on highlighter swipes; `0` only on tiny data dots).
- `"roundness":{"type":3}` on rectangles — sharp corners are the dashboard tell.

Text inside a shape goes via `"label":{ "text":"...", "fontSize": 18 }` — leave alignment defaults
unless the layout demands otherwise.

Free-floating text is a separate `{"type":"text", ...}` element; preferred for axis labels,
captions, headline copy, and any annotation that isn't physically pinned.

## Curved arrows (Pattern B)
Encode arc via the `points` array — **3+ points minimum** for callouts, gentle bends, never a
single ruler segment. Bind ends to ids when they pin to specific anchors:
`"startBinding":{"elementId":"<src>","focus":0,"gap":4}` plus matching `endBinding`. End with
`"endArrowhead":"arrow"`. Use `strokeColor` matching the *source* pill's stroke family.

## Highlighter swipes (Pattern C)
A `line` with `strokeWidth: 6–10`, `opacity: 40–60`, `roughness: 2`, in the mint family by default.
Place it **earlier in `elements`** than the thing it sits behind so it renders underneath. Use one
per diagram for the punchline (under a tagline) and optionally one as the chart series underlay.

## Annotated charts (Pattern D)
When the script implies numbers / progression / comparison, build:
1. Two axis `line` elements in ink (`#1e293b`), `strokeWidth: 2`, with `endArrowhead:"arrow"` on
   the far tip of each.
2. Free-floating `text` ticks along each axis (e.g. `1`, `2`, `3`, `4` and `1.2%`, `2%`, ...).
3. Free-floating axis-name `text` near the tip of each axis (`"Days"`, `"Reply Rate"`).
4. The data series as a Pattern C mint highlighter underlay **plus** a thin ink overlay line.
5. Data points: small filled ellipses (10–12 px), `fillStyle: "solid"`, in ink or the matching
   pill family for that anchor.

## Density
Aim for **14–22 substantive elements**. Quality and breathing room beat filler shapes. Most of
the count goes into the focal element + 3–5 callouts (each = pill + arrow + optional anchor dot)
+ 1–2 highlighter swipes + headline/tagline.

## Forbidden aesthetics
Symmetrical card dashboards, mirrored widget columns, dense tinted slabs, neon palettes, rainbow
clutter, sharp-cornered rectangles dominating the canvas, ruler-straight orthogonal callout arrows,
boilerplate repeating `"layout_style"` strings across unrelated lessons.
"""

VISION_REVIEW_PROMPT = """You are reviewing a PNG export of an instructional Excalidraw diagram plus its element JSON.

Approve only outputs that feel **hand-drawn whiteboard infographic** — pastel pill callouts with
emoji, curving connector arrows, highlighter swipes for emphasis, embedded chart-as-story when
numbers appear. Reject anything that reads as a software UI mock.

Reject when:
- Layout reads as **dashboard, Kanban cards, admin panels**, or repeating boxed sections.
- Dense tinted rectangles dominate instead of pills + curved connectors + free-floating labels.
- Composition is rigid grid symmetry with copy-paste panels (unless the lesson is genuinely tabular).
- Arrows are ruler-straight orthogonal segments instead of multi-point gentle arcs.
- Palette is loud / rainbow / neon — proper output sticks to soft pastels (sky / mint / peach /
  lavender / sun) with darker stroke + lighter fill pairs.
- Text overflows shapes, or labels sit awkwardly off their anchors.
- More than ~50% of the canvas is covered by opaque fills (the whiteboard "breathing room" is part
  of the look).
- Pills lack their emoji prefix or stretch beyond ~4 words.

Still require:
- Zero text overflow; readable hierarchy (headline ≥ section ≥ pill labels ≥ tick labels).
- A coherent palette pulled from the documented families — no improvised hues.
- One **focal narrative** the eye can trace in a single sweep — even when asymmetric.
- Where numbers exist, the chart is the focal and pills annotate it (Pattern D).

Respond with **only JSON**:
{
  "approved": true|false,
  "corrections": [
    {
      "id": "<element-id>",
      "patch": { "...only fields to merge on the element..." }
    }
  ],
  "notes": "short rationale — name which signature pattern is missing or violated"
}

If approved, use an empty corrections array. Patches must use valid Excalidraw element properties only.

**Critical:** Each `"id"` must match an `"id"` in the Elements JSON verbatim — never placeholders like `"step1"`.
"""
