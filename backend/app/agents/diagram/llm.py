"""Thin Anthropic structured-output helpers for diagram agents."""

from __future__ import annotations

import json
from typing import Any, TypeVar

from anthropic import APIError
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.services.llm import ANTHROPIC_STRUCTURED_OUTPUTS_BETA, anthropic_client

from .schema_clean import clean_schema

T = TypeVar("T", bound=BaseModel)


def _extract_text(response: Any) -> str:
    block = next(
        (b for b in response.content if getattr(b, "type", None) == "text"),
        None,
    )
    if block is None:
        raise RuntimeError("LLM returned no text block")
    return block.text


async def structured_json_call(
    system_prompt: str,
    user_prompt: str,
    model_cls: type[T],
    temperature: float = 0.35,
) -> tuple[T, int, int]:
    client = anthropic_client()
    schema = clean_schema(model_cls.model_json_schema())
    try:
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=8192,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            extra_headers={"anthropic-beta": ANTHROPIC_STRUCTURED_OUTPUTS_BETA},
            extra_body={"output_format": {"type": "json_schema", "schema": schema}},
        )
    except APIError as e:
        raise RuntimeError(f"diagram LLM call failed: {e}") from e
    raw = _extract_text(response)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"diagram JSON parse failed: {e}") from e
    try:
        out = model_cls.model_validate(payload)
    except ValidationError as e:
        raise RuntimeError(f"diagram schema validation failed: {e}") from e
    usage = response.usage
    return (
        out,
        int(getattr(usage, "input_tokens", 0) or 0),
        int(getattr(usage, "output_tokens", 0) or 0),
    )
