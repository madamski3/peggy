"""LLM-based planner for structured plan generation.

Lightweight Haiku call that produces:
  - plan: a structured {goal, steps} the main agent should work through
  - effort: recommended thinking effort level
  - components: optional prompt sections to activate

The plan is injected into the system prompt via the `plan` component; the
main agent calls the `advance_to_step` tool to signal progress against the
plan so the UI can render live step-by-step progress.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field

import anthropic
from pydantic import BaseModel

from app.agent.client import get_client
from app.agent.context import build_conversation_messages
from app.globals import PLANNER_MAX_TOKENS, PLANNER_MODEL
from app.observability.langfuse_client import (
    anthropic_usage_to_langfuse,
    trace_observation,
)
from app.prompts.composer import ActiveComponent
from app.schemas.agent import TurnPlan

logger = logging.getLogger(__name__)

_PLANNER_SYSTEM_PROMPT = """\
You are a planner for a personal assistant. Your job is to analyze the user's \
message and conversation context, then produce a short plan the main assistant \
will work through.

The assistant has access to tools for: calendar, todos/tasks, email, lists, \
personal profile/knowledge, daily planning, and conversation history. Tool \
selection is handled automatically — you only need to produce the plan.

## Output Format
Respond with a JSON object (no markdown fences, no extra text):

{
  "plan": {
    "goal": "one sentence framing what the user wants",
    "steps": ["step 1 in plain prose", "step 2 ...", ...]
  },
  "effort": "low|medium|high",
  "components": []
}

## Field Instructions

**plan.goal**: A single sentence capturing what the user is trying to accomplish \
overall. This orients the assistant.

**plan.steps**: An ordered list of high-level, natural-language steps the \
assistant should work through. Keep steps at the "what and why" altitude, not \
the "which tool call" altitude — the assistant has its own judgment and knows \
which tools to use. Aim for 1–5 steps; simple requests may have just one.

Good step: "Clarify which institution administers each 401k plan."
Good step: "Create Todos for each step of the rollover process."
Bad step: "Call the search_profile tool with query='401k'."

For trivial requests ("what time is it?"), a single-step plan like \
["Answer the question directly"] is fine. Do not pad.

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

PLANNER_PROMPT_ID = hashlib.sha256(_PLANNER_SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def planner_component() -> ActiveComponent:
    """Return the planner system prompt as a versioned ActiveComponent.

    Used by the orchestrator to upsert the planner prompt into the
    prompt_components table and tag the planner's llm_calls row.
    """
    return ActiveComponent(
        name="planner",
        id=PLANNER_PROMPT_ID,
        raw_text=_PLANNER_SYSTEM_PROMPT,
        type="planner",
    )


class PlannerResult(BaseModel):
    """Structured output from the planner LLM."""

    plan: TurnPlan = TurnPlan()
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
        result=PlannerResult(plan=TurnPlan(), effort="medium"),
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
        with trace_observation(
            name="planner",
            as_type="generation",
            model=PLANNER_MODEL,
            input={"system": _PLANNER_SYSTEM_PROMPT, "messages": messages},
            metadata={"planner_prompt_id": PLANNER_PROMPT_ID},
        ) as gen:
            response = await client.messages.create(
                model=PLANNER_MODEL,
                max_tokens=PLANNER_MAX_TOKENS,
                system=_PLANNER_SYSTEM_PROMPT,
                messages=messages,
            )
            if gen is not None:
                gen.update(
                    output=response.content,
                    usage_details=anthropic_usage_to_langfuse(response.usage),
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
            result=PlannerResult(plan=TurnPlan(), effort="medium"),
            raw_response=response,
        )

    return PlannerOutput(result=result, raw_response=response)
