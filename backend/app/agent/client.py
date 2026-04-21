"""Anthropic API client wrapper.

Thin layer over the Anthropic SDK. Provides a lazy-initialized singleton
and a single `call_llm` function that the orchestrator calls on every
round of the tool-use loop. The model, API key, and max-tool-rounds are
all pulled from app.config.settings.

Prompt caching strategy:
  - Breakpoint 1: end of system prompt (stable within a single agent loop)
  - Breakpoint 2: end of tool definitions (stable within a single agent loop)
  - Breakpoint 3: end of the last message before the current round's new
    content — so each round cache-hits on all previous rounds' messages.
"""

import copy
import logging

import anthropic
from anthropic import AsyncAnthropic

from app.config import settings
from app.globals import AGENT_DEFAULT_EFFORT, AGENT_DEFAULT_MAX_TOKENS, ANTHROPIC_MODEL

logger = logging.getLogger(__name__)

_client: AsyncAnthropic | None = None

# Anthropic-executed server tools. These don't run in our orchestrator — the API
# fetches results and returns them inline as server_tool_use / web_*_tool_result
# blocks in the same response. Appended to every request so the model can always
# reach for them when the user asks about current, external, or procedural facts.
_SERVER_TOOLS: list[dict] = [
    {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 5,
    },
    {
        "type": "web_fetch_20250910",
        "name": "web_fetch",
        "max_uses": 5,
        "citations": {"enabled": True},
        "max_content_tokens": 50000,
    },
]


def get_client() -> AsyncAnthropic:
    """Get or create the Anthropic async client singleton."""
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _with_cache_control(messages: list[dict]) -> list[dict]:
    """Add a cache breakpoint to the last message's last content block.

    Returns a shallow copy of the list with only the last message modified,
    so we don't mutate the caller's message history.
    """
    if not messages:
        return messages

    messages = list(messages)  # shallow copy of the list
    last_msg = copy.deepcopy(messages[-1])  # deep copy only the last message

    content = last_msg.get("content")
    if isinstance(content, str):
        # Convert plain string to content block format
        last_msg["content"] = [
            {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
        ]
    elif isinstance(content, list) and content:
        # Add cache_control to the last block in the list
        content[-1] = {**content[-1], "cache_control": {"type": "ephemeral"}}

    messages[-1] = last_msg
    return messages


async def call_llm(
    messages: list[dict],
    system: str,
    tools: list[dict],
    max_tokens: int = AGENT_DEFAULT_MAX_TOKENS,
    effort: str | None = AGENT_DEFAULT_EFFORT,
) -> anthropic.types.Message:
    """Call the Anthropic Messages API with tool definitions.

    Applies prompt caching breakpoints to:
      1. The system prompt (stable across all rounds within one agent loop)
      2. The last tool definition (stable across all rounds)
      3. The last message (grows each round — cache previous rounds' content)

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

    # Breakpoint 1: system prompt
    cached_system = [
        {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
    ]

    # Breakpoint 2: last tool definition. Server tools are appended last so the
    # cache breakpoint lands on a stable entry (server tool defs never vary by
    # request, unlike the intent-filtered client tools).
    cached_tools = list(tools) + _SERVER_TOOLS
    if cached_tools:
        cached_tools[-1] = {**cached_tools[-1], "cache_control": {"type": "ephemeral"}}

    # Breakpoint 3: last message (previous round's content)
    cached_messages = _with_cache_control(messages)

    kwargs: dict = dict(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=cached_system,
        messages=cached_messages,
        tools=cached_tools,
    )

    if effort is not None:
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": effort}

    response = await client.messages.create(**kwargs)

    # Log cache performance
    usage = response.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    if cache_read or cache_creation:
        logger.info(
            f"Cache: {cache_read} read, {cache_creation} written, "
            f"{usage.input_tokens} uncached input"
        )

    return response
