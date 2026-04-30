"""Adapt Pydantic JSON Schema for Anthropic structured outputs."""

from __future__ import annotations

from typing import Any

_UNSUPPORTED_KEYS = frozenset(
    {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "pattern",
        "format",
        "not",
        "if",
        "then",
        "else",
        "default",
    }
)


def clean_schema(node: Any) -> Any:
    if isinstance(node, dict):
        cleaned = {k: clean_schema(v) for k, v in node.items() if k not in _UNSUPPORTED_KEYS}
        if cleaned.get("type") == "object":
            cleaned["additionalProperties"] = False
        return cleaned
    if isinstance(node, list):
        return [clean_schema(v) for v in node]
    return node
