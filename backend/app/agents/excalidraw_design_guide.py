"""Design rules for MCP / canvas-backed diagram generation (education-friendly).

Aesthetic target: annotated whiteboard explainer — pastel pill callouts with emoji,
highlighter swipes, hand-drawn curving arrows, embedded chart-as-story when numbers
exist. Teaching use case: **navigable multi-zone canvas** tuned for zoom-in / pan
storytelling (YouTube or live explanation), not a single compact screen-filling slug.

Never a software dashboard.
"""

from __future__ import annotations

# Teaching canvas + whiteboard warmth — zones, pan/zoom isolation, anti-template.
DESIGN_SKILL_SYSTEM_RULES = """
## Prime directive (navigable visual story canvas)
- Design the diagram as a **large, pannable canvas for teaching**. The presenter thinks:
  **“How will I explain this by zooming and panning section by section?”** — not “How do I fit
  everything onto one viewport?”
- **Derive every composition from the supplied script** — classify what the content *is* (process,
  comparison, hierarchy, journey, quantitative arc, metaphor, teaching analogy), then invent a
  **spatial story**: several distinct explanation zones, each readable on its own when zoomed in.
- Mindset stays **whiteboard infographic**, not UI mockup. Imagine a designer mapping the lesson
  across a wide sheet: pastel markers, curved arrows linking **zones**, callouts anchored inside
  each beat.
- The **macro narrative** arcs across zones along the axis the script dictates — **horizontal**,
  **vertical**, or **guided hybrid**. Each **micro
  beat** inside a zone is a complete miniature explanation — never a mirrored copy-paste of the zone
  before it.

## Mental model — three-phase design discipline (follow in order)

1. **Plan the full canvas.** List logical explanation sections from the script; assign each to a
   dedicated **spatial zone**. Pick the **global story axis from context** — **left→right**, **top→bottom**,
   or a **hybrid / Z-path** depending on what the content rewards (timeline or comparison sideways;
   procedural or stacked narrative downward; bends when the beats need it). **No habitual default:**
   whichever axis fits the script best wins. Declare it in **`navigation_flow`**. Reserve **neutral buffer space** between zones
   so zooming isolates one zone without neighbors crowding the frame.
2. **Fill each zone individually.** Inside a zone: rich but **light structure** — flows, miniature
   charts (Pattern D), pills, anchors — avoid heavy tinted panels framing the entire zone.
3. **Review for zoom clarity.** Pretend viewport ≈ **one zone at a time**; enforce **major-block gaps ≥ 2×
   the larger adjoining width or height**; expand coords if another beat’s ink would still peek in at a
   comfortable teaching zoom.

### Multi-zone canvas (critical)
- Divide the canvas into **multiple logical sections (zones)** — e.g. Intro / Context, Core Concept,
  Process / Flow, Example / Application, Summary / Insight — **only use labels that fit the script**.
- Zones must **not** overlap visually or conceptually (no ambiguous shared gutters where two stories
  collide).
- **Generous whitespace between zones** — superseded in strictness by **### Strict spacing between major
  blocks** below (follow that HARD rule whenever two beats sit beside or above/below each other).
- **Smooth navigation cues** between zones: multi-point arrows, light flow lines, numbering, or subtle
  “next beat” gestures — never rely on the viewer guessing reading order.

### Strict spacing between major blocks (zoom isolation — HARD, spacing only)

A **major block** is everything that belongs to one teaching beat: take its **axis-aligned bounding box**
(encompass shapes, arrows that are internal to that beat, titles, captions — omit connectors whose sole
purpose is linking *between* blocks; those live in the **gap**).

**Numeric rule:** For every pair of neighboring major blocks along the story axis:

- **Horizontal neighbors** (side-by-side): **edge-to-edge gap** ≥ **2 ×** the **larger width** of the
  two block widths (`max(width_left, width_right)`). Increase canvas width / shift coordinates; do **not**
  shrink inner content or change motif to “fake” clearance.
- **Vertical neighbors** (stacked): **edge-to-edge gap** ≥ **2 ×** the **larger height** of the two
  block heights (`max(height_upper, height_lower)`).

Treat “still seeing the edge” of another block at a comfortable teaching zoom as **failure** —
the gap targets **minimal zoom** to show **exactly one** major block cleanly.

**Placement:** Side-by-side blocks must **not** read as visually adjacent thumbnails; widen until the
mental zoom passes the check:

- Zoom mentally into one major block → any ink from another major block still visible → **push blocks
  apart** (same styling, farther apart).

Expand `canvas_width` / `canvas_height` as needed. This rule changes **coordinates and canvas size**
only — not illustration style or internal layout grammar inside a block.

### Spatial navigation flow
- Arrange zones along **one dominant direction or a deliberate hybrid**, chosen **for this script**
   (horizontal, vertical, or mixed). Match the metaphor: e.g. process pipelines or before/after often
   read well **horizontally**; step-by-step descent or layered stacks often **vertically**.
- Avoid always picking the same macro layout across unrelated prompts — vary **direction** when
   context calls for it, not for decoration alone.
- Inside each zone, use **controlled alignment** — rhythmic spacing and intentional alignments — but
  **avoid** ruler-perfect grids that repeat identically zone-to-zone, and avoid random scatter.
- **Visual focus control:** size hierarchy, directional arrows, and restrained color emphasis so
  attention lands on **one zone at a time** at teaching scale; the climax still earns **lavender /
  “Result”** where the script has a single payoff.

### Internal zone design
- Each zone should **feel complete on its own** when zoomed: a viewer sees the idea without needing
  the rest of the canvas immediately.
- Vary treatment **per zone** — different internal layout grammar (e.g. one zone flowchart-like,
  another comparison or small chart, another narrative strip). **Strictly avoid** identical
  box→text→box stripes repeated across zones, mirrored symmetry, or template panels.

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
You may anchor the canvas with **one** bold headline (24–36 px) in an intro zone — optionally on a
soft pastel strip (`roughness: 1`). Prefer **zonewise small titles** over one giant centered banner
when the lesson has several beats across a wide canvas. **No** flag-ribbon ornament unless the
lesson is genuinely festive.

## Anti — “AI generic”
- Ban **same internal layout photocopied** into every zone, identical pill grids, symmetrical
  duplication, or rhythmic box-text-box stripes marching across the sheet.
- Slight intentional irregularity *within* a zone reads human — but **between** zones prefer
  purposeful variety over random noise.

## Multi-pass redraw discipline
Later QA passes must **abandon** the prior pass's spatial archetype if redesign was requested —
never paste the same UI-ish scaffold twice. Re-classify the script if needed and design a
visibly different diagram while keeping the palette + typography constraints.
"""

DIAGRAM_JSON_INSTRUCTIONS = """
Return **only valid JSON** (no markdown fences) with this shape:
{
  "content_classification": "<structural read of the script — short phrase>",
  "visual_strategy": "<why this spatial story fits — cite zones + navigation>",
  "layout_style": "<your bespoke label for THIS teaching canvas — not an enum>",
  "navigation_flow": "<chosen for this script: horizontal L→R, vertical top→bottom, or hybrid — brief rationale>",
  "zone_plan": [
    { "id": "z1", "role": "<Intro|Core|Process|Example|Summary|...>", "summary": "<one line>" }
  ],
  "canvas_width": 3200,
  "canvas_height": 1400,
  "background_color": "#ffffff",
  "elements": [ ... Excalidraw-style element objects ... ]
}

`zone_plan` must align with how you actually placed content (ids are for your own coherence; keep
them short). If the script is extremely minimal, you may shrink to two zones — still keep **pan space**
between them.

## Composition mandate (read first)
- Think **teaching canvas**: multiple **non-overlapping** explanation zones spaced for **zoom isolation**.
- **Enforce strict inter-block spacing (HARD):** neighboring major-block bounding boxes obey **gap ≥ 2×
  larger lateral dimension**: horizontal neighbors use widths; stacked neighbors use heights. Extend
  `canvas_width` / `canvas_height`; do **not** compress inner design to cram more on screen — only
  increase separation between beats.
- **Plan coordinates** from your chosen **`navigation_flow`**: spread zones along **X** for horizontal
  stories, **Y** for vertical stacks, or both for hybrid paths. Place inter-zone arrows / flow cues in
  the **buffer**, not inside dense content clusters.
- Use **large `canvas_width` / `canvas_height`** when needed (often **≥ 2600×1200**; expand if five
  zones or complex flows). Bounding boxes may exceed typical slide sizes.
- Preserve the whiteboard vocabulary: arrows / lines / `ellipse` / `text` carry relationships;
  `rectangle` stays minimal — **rounded pastel pills** (Pattern A), never dashboard tiles.

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
Place it **earlier in `elements`** than the thing it sits behind so it renders underneath.

## Annotated charts (Pattern D)
When numbers / progression / comparison belong in **one zone**, build the chart there — axis lines,
dual-stroke series, elliptical points — pills annotate **that** focal, not a tiny unreadable postage
stamp squeezed for the whole canvas.

## Density
Scale element count with zone count — typically **≈ (6–14 elements per zone)** including connectors,
while staying within the caller's character/token budget (prefer fewer-richer primitives, lean JSON).
Quality, variety between zones, and **inter-zone whitespace** beat filler shapes.

## Quality check (self-validate before emit)
- Zooming toward any zone isolates it: neighbors do not dominate the periphery (**no stray ink** from an
  adjacent major block when framed for teaching).
- **Measure gaps:** consecutive major blocks respect **≥ 2×** the larger adjoining width or height —
  edge-to-edge, not centroid-to-centroid.
- Panning follows the declared **navigation_flow** naturally.
- No two zones use the **same structural template**.
- Reads as teaching tool / storyboard canvas, not a single crowded slide.

## Forbidden aesthetics
Symmetrical card dashboards, mirrored widget columns, dense tinted slabs, neon palettes, rainbow
clutter, sharp-cornered rectangles dominating the canvas, ruler-straight orthogonal callout arrows,
boilerplate repeating `"layout_style"` strings across unrelated lessons, **compressed stacking** that
forsakes lateral (or vertical) teaching space, **inter-block gaps** tighter than **2×** the larger block
extent along that axis — including layouts where “visually adjacent” blocks would share a zoom frame.
"""

VISION_REVIEW_PROMPT = """You are reviewing a PNG export of an instructional Excalidraw diagram plus its element JSON.

Approve outputs that serve **explainer/teaching cadence**: a **wide, navigable canvas** with
**multiple distinct explanation zones** spaced so a presenter could **zoom into one zone** at a time
and **pan** along the story (YouTube-style or live board). The look must stay **hand-drawn whiteboard
infographic** — pastel pill callouts with emoji where appropriate, curving connector arrows
(multi-point arcs), optional highlighter swipes, embedded chart-as-story when numbers justify it.

Reject when:
- The layout reads as **dashboard, Kanban cards, admin panels**, or repeating boxed modules — even if
  spread out.
- **Major-block spacing violates the HARD rule**: edge-to-edge gap between horizontally adjacent beats
  is **< 2× the larger width** of those beats, or between vertically stacked beats **< 2× the larger
  height**. Reject too if **mental teaching zoom** on one beat still shows meaningful ink from the next beat.
- Content is **over-compressed** or tightly clustered so adjacent explanation beats would appear in the
  same zoom frame without intent.
- **Zones overlap** or gutters are ambiguous — unclear which content belongs to which teaching beat.
- **Template repetition**: multiple sections with the same internal pattern (e.g. identical rows of
  boxes) without content-driven variation.
- Dense tinted rectangles dominate instead of pills + curved connectors + free-floating labels.
- Arrows are ruler-straight orthogonal segments instead of multi-point gentle arcs (for intentional
  callouts and flow).
- Palette is loud / rainbow / neon — proper output sticks to soft pastels (sky / mint / peach /
  lavender / sun) with darker stroke + lighter fill pairs.
- Text overflows shapes, or labels sit awkwardly off their anchors.
- More than ~50% of the canvas is covered by opaque fills (the whiteboard "breathing room" is part
  of the look).
- Pills that use emoji lack their emoji prefix or stretch beyond ~4 words.

Still require:
- Zero text overflow; readable hierarchy (headline / zone titles ≥ pills ≥ tick labels).
- A coherent palette pulled from the documented families — no improvised hues.
- A **macro story** the presenter can traverse spatially; each **zone** can stand alone when zoomed.
- Where numbers exist, the chart lives in an appropriate zone and pills annotate it (Pattern D).

Respond with **only JSON**:
{
  "approved": true|false,
  "corrections": [
    {
      "id": "<element-id>",
      "patch": { "...only fields to merge on the element..." }
    }
  ],
  "notes": "short rationale — teaching canvas + whiteboard aesthetic; cite zone isolation or violations"
}

If approved, use an empty corrections array. Patches must use valid Excalidraw element properties only.

**Critical:** Each `"id"` must match an `"id"` in the Elements JSON verbatim — never placeholders like `"step1"`.
"""
