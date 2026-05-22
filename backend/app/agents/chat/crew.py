from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator
from uuid import UUID

from app.config import settings
from app.models.db import IdeaSlice, UserProfileSlice
from app.services.llm import anthropic_client
from app.services.usage import log_usage

def _clean_base64(data_url: str) -> tuple[str, str]:
    if data_url.startswith("data:"):
        match = re.match(r"data:(image/[a-zA-Z0-9\-\+]+);base64,(.*)", data_url)
        if match:
            return match.group(1), match.group(2)
    return "image/jpeg", data_url

async def run_chat_stream(
    user_id: UUID,
    profile: UserProfileSlice,
    idea: IdeaSlice | None,
    session: dict[str, Any],
    script: dict[str, Any] | None,
    outline: dict[str, Any] | None,
    scene: dict[str, Any] | None,
    history: list[dict[str, Any]],
    message: str,
    mode: str,
    image_base64: str | None,
    skill_content: str | None,
) -> AsyncIterator[dict[str, Any]]:
    client = anthropic_client()
    
    system_prompt = f"""You are Sharpen, the AI video studio assistant for Ladder Content OS.
You help the user refine their video script, outline, and scene designs.

CRITICAL RULE: You have access to editing tools (patch_script, patch_outline, patch_scene).
When the user asks you to make a change, you MUST call the appropriate tool to execute it.
NEVER just describe what you would change — always actually apply the edit via a tool call.
You may include a brief conversational message alongside your tool calls, but the tool calls
are mandatory — the user expects the changes to appear in their UI immediately.

Current Request Mode: {mode}

WHEN MODE IS "text" (no screenshot provided):
- The user is editing written content. Call patch_script to edit script sections, or
  patch_outline to edit outline beats. These are your primary tools.
- Only use patch_scene if the user EXPLICITLY mentions the canvas, drawing, diagram,
  layout, or Excalidraw by name.
- For adding content between existing items: replace the item at the target index and
  adjust subsequent items' indices. The full section/item must be provided.

WHEN MODE IS "screenshot" (user pasted an image):
- The image is a screenshot of their current Excalidraw canvas.
- Use patch_scene to surgically edit the canvas elements based on what the user describes.
- Match elements by their text labels and positions visible in the screenshot.
- If you cannot confidently identify an element, ask the user for its exact label text.
"""


    if profile:
        system_prompt += f"\n\nUser Profile:\n{profile.model_dump_json(exclude_none=True)}"
        
    if idea:
        system_prompt += f"\n\nIdea Context:\n{idea.model_dump_json(exclude_none=True)}"
        
    if script:
        # Avoid dumping huge JSON directly if we can just stringify compactly
        system_prompt += f"\n\nCurrent Script:\n{json.dumps(script.get('content_json') or script, separators=(',', ':'))}"
        
    if outline:
        system_prompt += f"\n\nCurrent Outline:\n{json.dumps(outline.get('content_json') or outline, separators=(',', ':'))}"
        
    if scene:
        # Scene can be huge, we'll try to provide elements concisely if needed, or just full JSON
        scene_json = scene.get('content_json') or scene
        elements = scene_json.get('elements', [])
        slim_scene = {"canvas_width": scene_json.get("canvas_width"), "canvas_height": scene_json.get("canvas_height"), "elements_count": len(elements), "elements": elements}
        system_prompt += f"\n\nCurrent Scene:\n{json.dumps(slim_scene, separators=(',', ':'))}"
        
    if skill_content:
        system_prompt += f"\n\nInjected Skill Context (Pay strict attention to this):\n{skill_content}"
        
    messages = []
    
    for h in history:
        messages.append({
            "role": h["role"],
            "content": h["content"]
        })
        
    user_content: list[dict[str, Any]] = []
    if image_base64:
        media_type, data = _clean_base64(image_base64)
        user_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": data,
            }
        })
        
    user_content.append({
        "type": "text",
        "text": message
    })
    
    messages.append({
        "role": "user",
        "content": user_content
    })
    
    tools = [
        {
            "name": "patch_scene",
            "description": "Applies a surgical JSON diff to the current Excalidraw scene elements. Use this to perform edits on the scene canvas when requested.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "upsert_elements": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "A list of scene elements to insert or modify. Match the existing element JSON schema. Must include 'id', 'type', 'x', 'y', 'width', 'height'."
                    },
                    "remove_element_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "A list of element IDs to delete from the canvas."
                    }
                },
                "required": ["upsert_elements", "remove_element_ids"]
            }
        },
        {
            "name": "patch_script",
            "description": "Replaces a script section at the given index. Use for text-mode edits to existing sections.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "section_index": {"type": "integer"},
                    "new_section": {
                        "type": "object",
                        "description": "The new script section to replace the old one. Must match the schema: { heading, duration_min, talking_points, transition }"
                    }
                },
                "required": ["section_index", "new_section"]
            }
        },
        {
            "name": "insert_script_section",
            "description": "Inserts a new script section at the given index, shifting subsequent sections down. Use when the user asks to ADD content between existing sections.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "section_index": {"type": "integer", "description": "The position to insert at (0-based). Insert shifts the current section at this index and all following sections down."},
                    "new_section": {
                        "type": "object",
                        "description": "The new script section to insert. Must match the schema: { heading, duration_min, talking_points, transition }"
                    }
                },
                "required": ["section_index", "new_section"]
            }
        },
        {
            "name": "remove_script_section",
            "description": "Removes a script section at the given index. Use when the user asks to DELETE or cut a section.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "section_index": {"type": "integer", "description": "The index of the section to remove (0-based)."}
                },
                "required": ["section_index"]
            }
        },
        {
            "name": "patch_outline",
            "description": "Replaces an outline item at the given index. Use for text-mode edits to existing outline beats.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "item_index": {"type": "integer", "description": "The index of the outline item to replace (0-based)."},
                    "new_item": {
                        "type": "object",
                        "description": "The new outline item to replace the old one. Must match the schema: { number, label, beat }"
                    }
                },
                "required": ["item_index", "new_item"]
            }
        },
        {
            "name": "insert_outline_item",
            "description": "Inserts a new outline item at the given index, shifting subsequent items down. Use when the user asks to ADD a beat between existing ones.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "item_index": {"type": "integer", "description": "The position to insert at (0-based). Insert shifts the current item at this index and all following items down."},
                    "new_item": {
                        "type": "object",
                        "description": "The new outline item to insert. Must match the schema: { number, label, beat }"
                    }
                },
                "required": ["item_index", "new_item"]
            }
        },
        {
            "name": "remove_outline_item",
            "description": "Removes an outline item at the given index. Use when the user asks to DELETE a beat.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "item_index": {"type": "integer", "description": "The index of the item to remove (0-based)."}
                },
                "required": ["item_index"]
            }
        }
    ]
    
    async with log_usage(
        user_id=user_id,
        function_name="chat_stream",
        model=settings.ANTHROPIC_MODEL,
        provider="anthropic",
    ) as entry:
        stream = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            tools=tools,
            stream=True,
        )
        
        current_tool_name = None
        current_tool_json = ""
        
        async for chunk in stream:
            if chunk.type == "content_block_start" and chunk.content_block.type == "tool_use":
                current_tool_name = chunk.content_block.name
                current_tool_json = ""
            elif chunk.type == "content_block_delta":
                if chunk.delta.type == "text_delta":
                    yield {
                        "type": "text_delta",
                        "agent": "chat",
                        "content": chunk.delta.text,
                    }
                elif chunk.delta.type == "input_json_delta":
                    current_tool_json += chunk.delta.partial_json
            elif chunk.type == "content_block_stop":
                if current_tool_name:
                    try:
                        args = json.loads(current_tool_json)
                        yield {
                            "type": "tool_call",
                            "agent": "chat",
                            "name": current_tool_name,
                            "arguments": args,
                        }
                    except json.JSONDecodeError:
                        pass
                    current_tool_name = None
                    current_tool_json = ""
            elif chunk.type == "message_start":
                entry.input_tokens = chunk.message.usage.input_tokens
            elif chunk.type == "message_delta":
                entry.output_tokens = chunk.usage.output_tokens
                
        # Estimate cost (e.g. Claude Haiku 3.5 pricing or whatever model)
        _PRICE_IN_PER_MTOK = 0.25 # adjust if using sonnet
        _PRICE_OUT_PER_MTOK = 1.25
        entry.cost_usd = round(
            (entry.input_tokens / 1_000_000) * _PRICE_IN_PER_MTOK + 
            (entry.output_tokens / 1_000_000) * _PRICE_OUT_PER_MTOK, 6
        )
        
        yield {
            "type": "usage",
            "token_usage": {
                "input": entry.input_tokens,
                "output": entry.output_tokens,
                "cost_usd": entry.cost_usd,
            }
        }
