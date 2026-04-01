"""Anthropic API client wrapper.

Thin layer over the Anthropic SDK. Provides a lazy-initialized singleton
and a single `call_llm` function that the orchestrator calls on every
round of the tool-use loop. The model, API key, and max-tool-rounds are
all pulled from app.config.settings.

This file has no business logic -- it exists to keep the Anthropic SDK
import and configuration in one place.
"""

import anthropic
from anthropic import AsyncAnthropic

from app.config import settings

_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    """Get or create the Anthropic async client singleton."""
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def call_llm(
    messages: list[dict],
    system: str,
    tools: list[dict],
    max_tokens: int = 16000,
    effort: str | None = "medium",
) -> anthropic.types.Message:
    """Call the Anthropic Messages API with tool definitions.

    Args:
        messages: Conversation history in Anthropic message format
        system: System prompt text
        tools: Tool definitions in Anthropic format
        max_tokens: Maximum tokens in the response
        effort: Thinking effort level ("low", "medium", "high") or None to disable

    Returns:
        The Anthropic Message response object
    """
    client = get_client()

    kwargs: dict = dict(
        model=settings.anthropic_model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        tools=tools,
    )

    if effort is not None:
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": effort}

    return await client.messages.create(**kwargs)
