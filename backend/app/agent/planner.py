"""LLM-based planner for strategy generation.

Lightweight Haiku call that produces:
  - strategy: natural-language approach guidance injected into the system prompt
  - effort: recommended thinking effort level

Tool selection is handled separately by tool_selector.py (vector search).
The planner focuses purely on strategy — what approach the main LLM should
take, injected via the {{ strategy }} variable in system_v2.yaml.
"""

import json
import logging
from dataclasses import dataclass, field

import anthropic
from pydantic import BaseModel

from app.agent.client import get_client
from app.agent.context import build_conversation_messages
logger = logging.getLogger(__name__)

_PLANNER_MODEL = "claude-haiku-4-5-20251001"
_PLANNER_MAX_TOKENS = 1024

_PLANNER_SYSTEM_PROMPT = """\
You are a strategy planner for a personal assistant. Your job is to analyze the \
user's message and conversation context, then decide what approach the assistant \
should take.

The assistant has access to tools for: calendar, todos/tasks, email, lists, \
personal profile/knowledge, daily planning, and conversation history. Tool \
selection is handled automatically — you only need to provide strategy.

## Output Format
Respond with a JSON object (no markdown fences, no extra text):

{
  "strategy": "2-5 sentences of approach guidance...",
  "effort": "low|medium|high",
  "components": []
}

## Field Instructions

**strategy**: Concise guidance for the main assistant — what to do, in what \
order, and what to prioritize. This is context and direction, not a rigid \
script. The assistant has its own judgment and tool-calling ability; your \
strategy helps it start on the right track. Focus on the *what* and *why*, \
not the exact tool calls.

**effort**: Recommended thinking effort for the main assistant.
- "low": Simple lookups or single-domain queries (e.g. "what's on my calendar?")
- "medium": Standard tasks involving a few tool calls (e.g. "create a todo for X")
- "high": Complex multi-step planning or reasoning across multiple domains

**components**: Select which prompt components the assistant needs for this turn. \
Only include what's relevant — omit the rest. For simple queries, return an empty list.
Available components:
- "daily_planning": User wants to plan their day, review their daily plan, or schedule their agenda
- "schedule_overview": User is asking about their schedule, calendar, or what's coming up
"""


class PlannerResult(BaseModel):
    """Structured output from the planner LLM."""

    strategy: str
    effort: str = "medium"
    components: list[str] = []


@dataclass
class PlannerOutput:
    """Wraps the parsed planner result with the raw API response for logging."""

    result: PlannerResult
    raw_response: anthropic.types.Message | None = field(default=None, repr=False)


def _fallback() -> PlannerOutput:
    """Return a safe fallback when the planner fails."""
    return PlannerOutput(
        result=PlannerResult(strategy="", effort="medium"),
        raw_response=None,
    )


async def run_planner(
    user_message: str,
    conversation_history: list[dict] | None,
) -> PlannerOutput:
    """Run the planner LLM to produce routing decisions.

    Args:
        user_message: The current user message.
        conversation_history: Recent session history (same format as the
            main agent loop uses), or None.

    Returns:
        PlannerOutput with parsed result and raw API response.
    """
    messages = build_conversation_messages(user_message, conversation_history)

    try:
        client = get_client()
        response = await client.messages.create(
            model=_PLANNER_MODEL,
            max_tokens=_PLANNER_MAX_TOKENS,
            system=_PLANNER_SYSTEM_PROMPT,
            messages=messages,
        )
    except Exception as e:
        logger.warning(f"Planner API call failed: {e}")
        return _fallback()

    # Extract text from response
    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text

    # Strip markdown code fences if present
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped[3:]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()

    # Parse JSON output
    try:
        data = json.loads(stripped)
        result = PlannerResult(**data)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"Planner response parse failed: {e} — raw: {text[:200]}")
        return PlannerOutput(
            result=PlannerResult(strategy="", effort="medium"),
            raw_response=response,
        )

    return PlannerOutput(result=result, raw_response=response)
