---
name: ladder-design-system
description: Apply the Ladder Content OS visual design system — colors, typography, components, spacing, dark mode, and UI patterns. Use this skill whenever the user asks to build, style, theme, or review any UI component for Ladder Content OS or any Ladder product, including buttons, cards, inputs, pills, chat panels, kanban cards, the three-zone duration slider, empty states, error states, or contextual hints. Also trigger when the user mentions "Cinnabar," "Jet," "Sienna," "Sea Salt," Ladder brand colors, Playfair Display, SF Pro, JetBrains Mono, or references the Ladder aesthetic (dense dev-tool, Linear/Vercel/Cursor-like). Trigger even on indirect requests like "style this component," "make it match our brand," "apply our theme," or "dark mode treatment" — assume Ladder Content OS context unless told otherwise. Stack target: Next.js + Tailwind + shadcn/ui, but the tokens work anywhere.
---

# Ladder Content OS — Design System

**Aesthetic target:** dense, precise developer tool. Linear, Vercel dashboard, Cursor. **Not a marketing app.** Every element must earn its place.

**Dark mode is the default.** Always use CSS variables in component styles. Never hardcode hex values in component files.

---

## Color Tokens

| Token | Hex | Role | Usage |
|---|---|---|---|
| `--cinnabar` | `#E8442A` | Primary brand | Primary CTAs, active nav states, brand accent, section border rules. Dominant — ~60% of visual weight on primary surfaces. Use boldly on primary actions. |
| `--jet` | `#3D3D3D` | Primary text | Primary text, structural elements, body copy. |
| `--sienna` | `#8B4A3A` | Accent | Hover states on Cinnabar elements, secondary accent, gradient endpoints, destructive button fills. |
| `--sea-salt` | `#F7EDE2` | Warm surface | Callouts, selected states in light mode. |
| `--gray-surface` | `#F5F5F5` | Neutral surface | Input backgrounds, card surfaces, alternating table rows. |
| `--gray-border` | `#CCCCCC` | Borders | All borders and dividers. 1px only. Never thicker — except the 3px Cinnabar brand accent rule under H2 headings. |
| `--gray-text` | `#6B6B6B` | Secondary text | Metadata, timestamps, helper text, placeholder text. |
| `--white` | `#FFFFFF` | Light bg / dark text | Light mode background, text on dark surfaces. |
| `--night` | `#0E0E0E` | Dark bg | Dark mode background. **Default mode.** Deep, not pure black. |

### Dark mode mappings (default)

- `--night` replaces `--white` for backgrounds
- `--white` replaces `--jet` for primary text
- `--gray-surface` becomes `#2A2A2A` in dark mode
- Borders stay `--gray-border` but at 15–20% opacity in dark mode

### Drop-in CSS variable sheet

```css
/* globals.css */
:root {
  --cinnabar: #E8442A;
  --cinnabar-hover: #C83820;
  --jet: #3D3D3D;
  --jet-hover: #555555;
  --sienna: #8B4A3A;
  --sea-salt: #F7EDE2;
  --gray-surface: #F5F5F5;
  --gray-border: #CCCCCC;
  --gray-text: #6B6B6B;
  --white: #FFFFFF;
  --night: #0E0E0E;
}

[data-theme="dark"] {
  --bg: var(--night);
  --bg-surface: #2A2A2A;
  --text-primary: var(--white);
  --text-secondary: var(--gray-text);
  --border: rgba(204, 204, 204, 0.18);
}

[data-theme="light"] {
  --bg: var(--white);
  --bg-surface: var(--gray-surface);
  --text-primary: var(--jet);
  --text-secondary: var(--gray-text);
  --border: var(--gray-border);
}

/* Dark mode is the default — set on <html> unless user overrides in Settings. */
html { color-scheme: dark; }
html[data-theme="light"] { color-scheme: light; }
```

### Tailwind config snippet

```ts
// tailwind.config.ts
import type { Config } from "tailwindcss";

export default {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cinnabar: {
          DEFAULT: "var(--cinnabar)",
          hover: "var(--cinnabar-hover)",
        },
        jet: {
          DEFAULT: "var(--jet)",
          hover: "var(--jet-hover)",
        },
        sienna: "var(--sienna)",
        "sea-salt": "var(--sea-salt)",
        "gray-surface": "var(--gray-surface)",
        "gray-border": "var(--gray-border)",
        "gray-text": "var(--gray-text)",
        night: "var(--night)",
      },
      fontFamily: {
        display: ['"Playfair Display"', "serif"],
        sans: ['"SF Pro Display"', '"SF Pro Text"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      borderRadius: {
        DEFAULT: "8px",
        card: "12px",
      },
    },
  },
} satisfies Config;
```

---

## Typography

| Font + weight | Size | Usage |
|---|---|---|
| Playfair Display 700 | 36px | **H1** page titles. Maximum one per screen. |
| Playfair Display 700 | 28px | **H2** section headings + 3px Cinnabar bottom border. |
| SF Pro Display 600 | 22px | **H3** subsections in Cinnabar. |
| SF Pro Display 600 | 18px | Card titles in Jet. |
| SF Pro Text 400 | 15px | Body copy. `line-height: 1.6`. |
| SF Pro Text 400 | 13px | Labels, metadata, timestamps. |
| SF Pro Text 600 | 14px | Button labels, CTA text. |
| JetBrains Mono 400 | 13px | Code blocks, data values, file references, API strings. |

**H2 always gets the 3px Cinnabar bottom border:**

```tsx
<h2 className="font-display font-bold text-[28px] pb-2 border-b-[3px] border-cinnabar">
  Section heading
</h2>
```

---

## Spacing and Layout

- **Base unit:** 4px. All spacing is a multiple: `4 · 8 · 12 · 16 · 24 · 32 · 48 · 64`.
- **Max content width:** 1440px.
- **Studio layout:** full viewport width, **no max-width constraint.**
- Internal content padding: 24px on all main surfaces.

---

## Components

### Buttons

| Variant | Fill | Text | Radius | Hover |
|---|---|---|---|---|
| **Primary** | `--cinnabar` | white | 8px | darken to `#C83820` |
| **Secondary** | `--jet` | white | 8px | lighten to `#555` |
| **Ghost** | transparent | `--jet` with 1px Jet border | 8px | `--gray-surface` bg |
| **Destructive** | `--sienna` | white | 8px | darker Sienna |

Typography on all buttons: SF Pro Text 600, 14px.

**Absolute rules:**
- No gradients.
- No drop shadows.
- Solid fills only.

```tsx
// Primary button pattern
<button className="bg-cinnabar hover:bg-cinnabar-hover text-white
                   font-sans font-semibold text-sm px-4 py-2 rounded-lg
                   transition-colors">
  Make this video →
</button>
```

### Cards

- 1px `--gray-border` border
- 12px border-radius
- 20px internal padding
- **Hover:** 3px `--cinnabar` left border accent. Background unchanged.
- **No drop shadow at rest.**

```tsx
<div className="border border-gray-border rounded-card p-5
                hover:border-l-[3px] hover:border-l-cinnabar
                transition-colors">
  {/* card content */}
</div>
```

### Inputs

- `--gray-surface` background.
- No border at rest.
- 1px `--cinnabar` border on focus. **No glow.**
- Label above input: SF Pro Text 14px 600, `--jet` color.
- Placeholder: `--gray-text` color.

```tsx
<label className="block">
  <span className="text-sm font-semibold text-jet mb-1 block">Brand name</span>
  <input
    className="w-full bg-gray-surface rounded px-3 py-2
               border border-transparent focus:border-cinnabar
               focus:outline-none transition-colors
               placeholder:text-gray-text"
    placeholder="e.g. Ladder"
  />
</label>
```

### Editable Pills (Studio header)

Used for output type, brand, and duration pills in the Studio header.

- `rounded-full`, 12px SF Pro Text 500
- 12% opacity background of the accent color, full-color text
- Tap opens inline dropdown **directly below the pill**. Never a modal.
- **Locked pills** (e.g. duration for content-extracted ideas): grey-out with lock icon. Non-tappable.

```tsx
<button className="rounded-full text-xs font-medium px-3 py-1
                   bg-cinnabar/12 text-cinnabar hover:bg-cinnabar/20
                   transition-colors">
  Excalidraw
</button>
```

### AI Chat Panel

- Always visible in the Studio. **Never collapsed.**
- Minimum width 280px, default 35% of Studio width.
- Resizable via drag handle on the panel divider.
- **User messages:** right-aligned, Cinnabar tint background (`bg-cinnabar/10`).
- **Assistant messages:** left-aligned, `--gray-surface` background.
- Image attachments: displayed as thumbnail in the message bubble.

### Three-Zone Duration Slider

**Custom component. Not a standard HTML range input.** Three zones with subtle Cinnabar tint (lightest → full):

```
Short              Medium             Long
5-10 min           15-25 min          30-60 min
Tight concept      Full walkthrough   Deep dive
```

- Drag handle snaps to zone midpoints: **8 / 20 / 45** min.
- "Custom" text link below opens a number input for exact minutes.
- **Locked state** (content-extracted ideas): slider greyed out with lock icon. Non-interactive.

### Contextual Intelligence Hints

Small, inline, dismissable. **Never modals, never notifications, never a separate panel.**

Examples you'll build:
- "You covered a similar angle in *[video title]* — reference it or take a different approach?"
- "This topic is performing 4.2x above average in adjacent niches this week." (badge on opportunity score)
- "Your audience typically responds well to numbered frameworks. This script uses narrative — intentional?"
- "You have not covered this angle before — it is a gap in your topic territory."

Styling: 13px gray text with a small Cinnabar icon, inline dismiss button, no background.

---

## Empty States — Never Blank Boxes

Every empty state gets a purposeful treatment. No blank white rectangles.

| State | Treatment |
|---|---|
| `/make` — no ideas | Option 1 card dimmed with arrow pointing to Option 2. Not an error message. |
| `/videos` — no ideas | Ideas column: "Generate ideas to fill your pipeline. [Make a Video →]" |
| `/videos` — YouTube not connected | Published column: connection prompt card. Never hidden. |
| Studio — before stream starts | Script area: "Writing your script..." with a gentle pulse. Not a blank box. |
| Library — no sources | My Sources tab: forwarding alias box is the primary visual element. |
| Library — no insights | "Your insights appear here after your first idea generation." |
| Settings — no brands | "Add your first brand to get started." with add form pre-opened. |

---

## Error and Loading States

| Scenario | Behaviour |
|---|---|
| `stream_script` fails mid-stream | "Something went wrong at *[section name]*." Retry button resumes from the last complete section. |
| `build_scene` fails | "Scene generation failed." Try again button. **Outline preserved** — user never loses the approved outline. |
| Excalidraw URL fails to open | "Download .excalidraw file" fallback link appears. |
| Slow connection (>15s) | "Taking longer than expected..." with progress indicator for what has completed. |
| API key not configured | Function button greyed out. Tooltip: "Add [Provider] API key in Settings > Models." |
| Screenshot too large | Inline warning in chat: "Image too large. Please screenshot a smaller section." (Max 4MB enforced.) |

---

## Non-Negotiables (the "never do this" list)

- ❌ No gradients on buttons or surfaces.
- ❌ No drop shadows at rest.
- ❌ No hardcoded hex values in component files — always use CSS variables.
- ❌ No border thicker than 1px, except the 3px Cinnabar accent rule under H2 and the 3px Cinnabar left border on card hover.
- ❌ No modal dropdowns for pills — inline only.
- ❌ No decorative emoji in UI chrome. Text labels only.
- ❌ No more than one H1 per screen.
- ❌ No glow or shadow effects on focused inputs — just the 1px Cinnabar border.

---

## shadcn/ui notes

When installing shadcn components, override the default palette to Ladder tokens. The shadcn defaults use `primary`, `secondary`, `accent` CSS variables — map them:

```css
:root {
  --primary: var(--cinnabar);
  --primary-foreground: var(--white);
  --secondary: var(--jet);
  --secondary-foreground: var(--white);
  --accent: var(--sea-salt);
  --accent-foreground: var(--jet);
  --destructive: var(--sienna);
  --destructive-foreground: var(--white);
  --muted: var(--gray-surface);
  --muted-foreground: var(--gray-text);
  --border: var(--gray-border);
  --input: var(--gray-surface);
  --ring: var(--cinnabar);
  --background: var(--white);
  --foreground: var(--jet);
  --card: var(--white);
  --card-foreground: var(--jet);
  --popover: var(--white);
  --popover-foreground: var(--jet);
  --radius: 0.5rem;
}

[data-theme="dark"] {
  --background: var(--night);
  --foreground: var(--white);
  --card: #1A1A1A;
  --card-foreground: var(--white);
  --popover: #1A1A1A;
  --popover-foreground: var(--white);
  --muted: #2A2A2A;
  --muted-foreground: var(--gray-text);
  --border: rgba(204, 204, 204, 0.18);
  --input: #2A2A2A;
}
```

After installing a shadcn component, grep for leftover `text-slate-*`, `bg-zinc-*`, `border-neutral-*` and replace with Ladder tokens. shadcn's default palette does not match Ladder.

---

## Quick reference — common patterns

**Primary CTA in a card:**
```tsx
<div className="border border-gray-border rounded-card p-5 bg-night">
  <h3 className="font-sans font-semibold text-lg text-white mb-2">
    Pick from your ideas
  </h3>
  <p className="text-sm text-gray-text mb-4">
    7 ideas ready · sorted by opportunity score
  </p>
  <button className="bg-cinnabar hover:bg-cinnabar-hover text-white
                     font-semibold text-sm px-4 py-2 rounded-lg">
    Browse ideas →
  </button>
</div>
```

**Section heading with Cinnabar underline:**
```tsx
<h2 className="font-display font-bold text-[28px] text-white
               pb-2 mb-6 border-b-[3px] border-cinnabar inline-block">
  My Videos
</h2>
```

**Opportunity score badge (Cinnabar if >80):**
```tsx
<span className={cn(
  "font-mono text-xs font-semibold px-2 py-0.5 rounded",
  score > 80 ? "bg-cinnabar text-white" : "bg-gray-surface text-jet"
)}>
  {score}
</span>
```

**Inline contextual hint:**
```tsx
<div className="flex items-start gap-2 text-[13px] text-gray-text py-2">
  <Sparkle className="w-3.5 h-3.5 text-cinnabar mt-0.5 flex-shrink-0" />
  <p className="flex-1">
    You covered a similar angle in <em>Why AI agents fail</em> — reference it?
  </p>
  <button className="text-gray-text hover:text-jet">×</button>
</div>
```