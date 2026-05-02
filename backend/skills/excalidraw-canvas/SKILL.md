---
name: excalidraw-canvas
description: Operational tips for driving the live Excalidraw MCP canvas — tool ordering, batching, snapshots, screenshots, viewport hygiene. Read this before the methodology skill.
metadata:
  author: ladder-content-os
  version: "1.0"
---

# Excalidraw MCP Canvas — Operational Tips

You are calling the `mcp_excalidraw` MCP server. The methodology lives in the `excalidraw-diagram` skill — that teaches you **what** to draw. This skill teaches you **how to use the tools well**.

## Tool selection cheat sheet

You have a focused build toolkit (12 MCP tools + 4 backend tools). The rest of the upstream MCP surface (`group_elements`, `lock_elements`, `create_from_mermaid`, `import_scene`, `export_to_image`, `read_diagram_guide`, etc.) is intentionally not exposed — drawing primitives and screenshot loops cover everything you need for a clean composition.

- `batch_create_elements` is your only create path. Always pass a coherent group of elements (≥3 typically). Don't fish for a single-shape create; there isn't one.
- `query_elements` finds elements by attribute (e.g. all rectangles whose text matches a label). Use it before `update_element` so you have the right id.
- `describe_scene` returns a cheap textual inventory (id, type, bbox, text) of everything on the canvas. Call this before you redraw or rearrange — it's the fastest way to know what you're working with without paying for a screenshot.
- `snapshot_scene` before any large rewrite. If the rewrite goes wrong, `restore_snapshot` is one call. This is cheap insurance.
- `set_viewport` (with the equivalent of "scroll to content" / "fit") after a major batch so anyone watching the canvas sees the whole composition, not the corner of it.
- `get_canvas_screenshot` is your visual feedback loop. Call it after each section or after a batch you're unsure about. Then look at the image and decide.

## Ordering rules

1. If you don't know the canvas state, `describe_scene` first.
2. If you're about to do a big change, `snapshot_scene` first.
3. Batch creates in groups, not one at a time.
4. After every batch, `set_viewport` so the screenshot will be readable.
5. Screenshot, audit, fix. Repeat until clean.
6. End with `set_viewport` one more time so the final canvas is centered for the user.

## Element discipline

- **Arrows MUST bind to shapes.** Every `arrow` element needs `start: {id: ...}` AND `end: {id: ...}` pointing at real element ids. Floating arrows are broken arrows.
- **Text fits its container.** If a label overflows, widen the rectangle or shorten the copy. Don't ship clipped text.
- **IDs are descriptive strings**: `trigger_rect`, `outcome_node`, `arrow_fanout_left`. The server preserves them. Don't use UUIDs.
- **No grid layouts.** No tiled columns of equal-sized boxes. The whole point of Excalidraw vs. PowerPoint is organic spatial hierarchy. If your composition starts looking like a slide, redraw.
- **Roughness 0 by default.** Roughness 1 only when the user wants a hand-drawn feel. Brand work is roughness 0.

## Avoid

- Don't call `clear_canvas` unless you have a confirmed reason (rebuilding from scratch, or the user said "start over"). Prefer surgical edits.
- Don't `delete_element` in a loop when one `clear_canvas` would do — but also don't `clear_canvas` when one `delete_element` would do. Match the surgery to the wound.
- Don't iterate forever. Most diagrams converge in 2–4 screenshot loops. If you've been at it for 10 turns, you're solving the wrong problem — `describe_scene` and rethink.
- Don't `export_scene` mid-loop. That's the final read step before persistence. Use `get_canvas_screenshot` for inspection.

## When the user is watching live

The canvas server broadcasts every change over WebSocket. If a user has the canvas open in their browser, they see your edits in real time. This means:
- Make your first batch *coherent* — even partial state should look intentional.
- If you're about to delete a lot, `snapshot_scene` so you can roll back if the user reacts badly.
- Don't rapid-fire `update_element` 50 times moving one shape around. Pick a position, set it once.

## When you're done

End with: `set_viewport` to fit content, then `export_scene` to read the full canvas state, then `persist_scene_artifact` (one of your backend tools) with that scene to write a versioned `excalidraw` artifact for this studio session. The conversational agent on top of you (`SharpenChatFlow`) will handle subsequent edits — you don't need to keep the canvas open after persistence.
