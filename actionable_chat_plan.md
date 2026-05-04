# Actionable Chat Architecture Plan

## Current Problem
Right now, the Chat agent (`run_chat_stream`) is a pure conversation agent. It receives the context (script, outline, scene) and generates a text-based response. Even when instructed to "add a scene," it just outputs markdown describing the Excalidraw JSON changes. 
Furthermore, the user raised a concern about excessive database writes.

## The Goal
1. **Functional Application:** The AI should execute changes rather than just talking about them.
2. **Visual Feedback:** The UI should highlight that a change occurred (e.g., updating the scene on the left, rendering a "Applied changes" pill in the chat).
3. **Write Optimization:** We must avoid saving to the database continuously during the streaming process to reduce cost and latency.

## Architecture: Client-Side Patching with Debounced DB Sync

To achieve "only the final save to be saved in the database", we will decouple the **AI execution** from the **Database persistence**.

### Step 1: Backend Tool Calling (`crew.py`)
Instead of just streaming text, we will equip the Anthropic client with specific tools:
- `apply_scene_diff(elements_to_add, elements_to_modify, elements_to_remove)`
- `update_script_section(section_index, new_content)`

When Claude decides to modify the scene, it will stream a `tool_use` block instead of a text block. The backend will parse this and yield a special WebSocket event:
```json
{
  "type": "tool_call",
  "name": "apply_scene_diff",
  "arguments": { ... }
}
```

### Step 2: Frontend State Patching (`ChatPanel.tsx` & `StudioScriptStream.tsx`)
The `ChatPanel` listens to the WebSocket. When it receives a `tool_call` event:
1. It does **not** hit the backend database.
2. It calls a new function passed via props (e.g., `onPatchScene(diff)`) which updates the local React state (`state.scene`).
3. This instantly re-renders the left pane (Scene Preview) so the user sees the change happening in real-time.
4. The chat message array gets a special local message: `{"role": "assistant", "content": "Applied Excalidraw layout updates."}` with a UI highlight.

### Step 3: Optimized Persistence (The "Final Save")
Since the left panel's state is now "dirty" (different from the database), we need to save it. We have two options, both of which solve the "costly DB calls" issue:

**Approach A: End-of-Turn DB Save (Recommended)**
The frontend keeps track of the patched scene in memory. When the WebSocket stream `[DONE]` event fires (meaning the AI has completely finished its turn), the frontend fires a single `PATCH /api/studio-sessions/{id}/artifact` request to persist the newly patched scene to the database.
- *Why it's good:* Zero DB writes during the stream. Exactly 1 DB write per successful chat interaction.

**Approach B: Explicit "Commit" Button**
The chat panel shows an "Unsaved changes" indicator. The user must explicitly click "Save Changes" to push the modified `scene` back to the database.
- *Why it's good:* Complete user control, 100% guarantees no unwanted DB writes. 

## Implementation Steps
1. **Update `run_chat_stream` (Backend):** Add the `tools` parameter to the Anthropic call. Map `tool_use` delta chunks to WebSocket events.
2. **Update `ChatPanel` (Frontend):** Catch `tool_call` events. Render them as system-action UI pills rather than text bubbles.
3. **Create `applySceneDiff` Utility (Frontend):** A helper function that takes the AI's JSON diff and merges it into the local `Scene` object.
4. **Implement Persistence Strategy:** Add the single-shot save trigger (either end-of-turn or manual commit button).
