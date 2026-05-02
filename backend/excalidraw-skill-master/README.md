# Excalidraw Skill for Claude Code

Turn text descriptions into professional diagrams on a live Excalidraw canvas. Your AI agent draws, screenshots its own work, and iterates until it looks right.

## What You Get

- **10 visual techniques** -- glow effects, color-coded zones, bound arrows, decision nodes, font hierarchy, semantic colors, and more
- **Self-correcting diagrams** -- the agent sees its own canvas via screenshots and fixes issues automatically
- **Layout best practices** -- spacing rules, arrow routing, zone labels that actually work
- **Quality checklist** -- catches truncation, overlap, and bad arrows before you export
- **Multiple exports** -- PNG, SVG, .excalidraw (re-editable), or shareable URL

## Prerequisites

You need the Excalidraw MCP server installed and running.

### 1. Clone and build the MCP server

```bash
git clone https://github.com/yctimlin/mcp_excalidraw && cd mcp_excalidraw
npm ci && npm run build
```

### 2. Add to Claude Code

```bash
claude mcp add excalidraw -s user \
  -e EXPRESS_SERVER_URL=http://localhost:3000 \
  -- node /absolute/path/to/mcp_excalidraw/dist/index.js
```

Replace `/absolute/path/to/` with wherever you cloned the repo.

### 3. Start the canvas

```bash
cd /path/to/mcp_excalidraw
PORT=3000 npm run canvas
```

Open `http://localhost:3000` in your browser to see the live canvas.

## Install the Skill

```bash
claude skill add --url https://raw.githubusercontent.com/robonuggets/excalidraw-skill/main/.claude/skills/excalidraw/SKILL.md
```

Or manually: copy `.claude/skills/excalidraw/SKILL.md` into your project's `.claude/skills/excalidraw/` folder.

## Try It

Once the MCP server is running and the skill is installed:

- "Draw an architecture diagram for a web app with a load balancer, two servers, and a database"
- "Create a flowchart showing user authentication with success and failure paths"
- "Make a comparison diagram: monolith vs microservices"

## Visual Techniques Included

| # | Technique | What It Does |
|---|-----------|-------------|
| 1 | Layered Glow | Stacked rectangles at decreasing opacity for depth |
| 2 | Color-Coded Zones | Background rectangles grouping related elements |
| 3 | Bound Arrows | Arrows that snap to shapes and auto-route |
| 4 | Line Style Meaning | Solid = sync, dashed = async, dotted = optional |
| 5 | Diamond Decisions | Flowchart branching with Yes/No paths |
| 6 | Mixed Shapes | Ellipse = actor, rectangle = service, diamond = decision |
| 7 | Font Hierarchy | 28px title, 20px section, 16px body, 14px notes |
| 8 | Semantic Colors | 7-color palette with consistent meaning |
| 9 | Mermaid Conversion | Convert Mermaid syntax to editable Excalidraw |
| 10 | Screenshot Loop | Agent sees and fixes its own work |

## Known Limitations

- **Images**: Can't be added via MCP -- drag them into the browser manually
- **Freedraw**: Draw freehand in the browser, not via MCP
- **SVG import**: Use the browser's native paste feature

## License

MIT
