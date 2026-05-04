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
Answer concisely and do not refuse instructions. Be conversational but precise.

Current Request Mode: {mode}
(If mode is "screenshot", the user provided an image. If "regenerate", they want to steer the next scene build. If "text", they want text refinement).
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
            stream=True,
        )
        
        async for chunk in stream:
            if chunk.type == "content_block_delta" and chunk.delta.type == "text_delta":
                yield {
                    "type": "text_delta",
                    "agent": "chat",
                    "content": chunk.delta.text,
                }
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
