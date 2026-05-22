"""LLM wrapper — unified interface for Anthropic, OpenAI, Gemini with cost tracking."""

from __future__ import annotations

import logging
from typing import Any

from research_agent.config import settings
from research_agent.models import CostBreakdown

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (input / output) — May 2026
MODEL_PRICING = {
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
    "claude-3-5-haiku-20241022": (0.80, 4.0),
    "claude-3-5-haiku-latest": (0.80, 4.0),
    "claude-opus-4-1-20250805": (15.0, 75.0),
    "claude-opus-4-20250514": (15.0, 75.0),
    "gpt-5-mini": (0.25, 2.0),
    "gemini-2.5-flash-preview-04-17": (0.10, 0.40),
    "text-embedding-3-small": (0.02, 0.0),
}

# Global clients for connection reuse
_anthropic_client = None
_openai_client = None


async def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        import os
        from anthropic import AsyncAnthropic
        # Prevent global DeepSeek configuration from intercepting the Anthropic client
        if "ANTHROPIC_BASE_URL" in os.environ:
            del os.environ["ANTHROPIC_BASE_URL"]
        _anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


async def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


async def llm_call(
    prompt: str,
    system: str = "",
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    cost_tracker: CostBreakdown | None = None,
    cost_layer: str = "",
) -> str:
    """Unified LLM call — routes to the right provider based on model name."""
    model = model or settings.synthesis_model

    if model.startswith("claude"):
        return await _anthropic_call(prompt, system, model, temperature, max_tokens, cost_tracker, cost_layer)
    elif model.startswith("gpt") or model.startswith("o"):
        return await _openai_call(prompt, system, model, temperature, max_tokens, cost_tracker, cost_layer)
    elif model.startswith("gemini"):
        return await _gemini_call(prompt, system, model, temperature, max_tokens, cost_tracker, cost_layer)
    else:
        # Default to Anthropic
        return await _anthropic_call(prompt, system, model, temperature, max_tokens, cost_tracker, cost_layer)


async def _anthropic_call(
    prompt: str, system: str, model: str, temperature: float,
    max_tokens: int, cost_tracker: CostBreakdown | None, cost_layer: str,
) -> str:
    client = await _get_anthropic_client()
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    resp = await client.messages.create(**kwargs)
    text = resp.content[0].text

    # Track cost
    if cost_tracker:
        input_tokens = resp.usage.input_tokens
        output_tokens = resp.usage.output_tokens
        pricing = MODEL_PRICING.get(model, (3.0, 15.0))
        cost = (input_tokens * pricing[0] + output_tokens * pricing[1]) / 1_000_000
        cost_tracker.add_cost(cost_layer, f"llm:{model}", model, cost)

    return text


async def _openai_call(
    prompt: str, system: str, model: str, temperature: float,
    max_tokens: int, cost_tracker: CostBreakdown | None, cost_layer: str,
) -> str:
    client = await _get_openai_client()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = resp.choices[0].message.content or ""

    if cost_tracker and resp.usage:
        pricing = MODEL_PRICING.get(model, (0.25, 2.0))
        cost = (resp.usage.prompt_tokens * pricing[0] + resp.usage.completion_tokens * pricing[1]) / 1_000_000
        cost_tracker.add_cost(cost_layer, f"llm:{model}", model, cost)

    return text


async def _gemini_call(
    prompt: str, system: str, model: str, temperature: float,
    max_tokens: int, cost_tracker: CostBreakdown | None, cost_layer: str,
) -> str:
    import google.generativeai as genai

    genai.configure(api_key=settings.google_api_key)
    gen_model = genai.GenerativeModel(
        model_name=model,
        system_instruction=system if system else None,
    )
    resp = await gen_model.generate_content_async(
        prompt,
        generation_config=genai.GenerationConfig(temperature=temperature, max_output_tokens=max_tokens),
    )
    text = resp.text or ""

    if cost_tracker and hasattr(resp, "usage_metadata"):
        # Use actual tokens from Gemini metadata if available
        input_tokens = resp.usage_metadata.prompt_token_count
        output_tokens = resp.usage_metadata.candidates_token_count
        pricing = MODEL_PRICING.get(model, (0.10, 0.40))
        cost = (input_tokens * pricing[0] + output_tokens * pricing[1]) / 1_000_000
        cost_tracker.add_cost(cost_layer, f"llm:{model}", model, cost)
    elif cost_tracker:
        # Fallback estimate
        input_tokens = len(prompt.split()) * 1.3
        output_tokens = len(text.split()) * 1.3
        pricing = MODEL_PRICING.get(model, (0.10, 0.40))
        cost = (input_tokens * pricing[0] + output_tokens * pricing[1]) / 1_000_000
        cost_tracker.add_cost(cost_layer, f"llm:{model}", model, cost)

    return text
