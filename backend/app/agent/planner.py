"""LLM-based planner for structured plan generation.

Lightweight Haiku call that produces:
  - plan: a structured {goal, steps} the main agent should work through
  - effort: recommended thinking effort level
  - components: optional prompt sections to activate
  - tool_names: tools the main agent will likely need (shadow-mode in Phase 3)

The plan is injected into the system prompt via the `plan` component; the
main agent calls the `advance_to_step` tool to signal progress against the
plan so the UI can render live step-by-step progress.

The planner system prompt is built lazily on first use because it embeds a
catalog generated from the tool registry, which is only fully populated
once tool modules have imported.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache

import anthropic
from pydantic import BaseModel

from app.agent.client import get_client
from app.agent.context import build_conversation_messages

# Importing the tools package triggers @tool registrations — must happen
# before get_tool_catalog_for_planner() runs, since the catalog reads
# TOOL_REGISTRY. Safe: tool modules don't import back from planner.
import app.agent.tools  # noqa: F401, E402

from app.agent.tools.registry import get_tool_catalog_for_planner  # noqa: E402
from app.globals import PLANNER_MAX_TOKENS, PLANNER_MODEL
from app.observability.langfuse_client import (
    anthropic_usage_to_langfuse,
    trace_observation,
)
from app.prompts.composer import ActiveComponent
from app.schemas.agent import TurnPlan

logger = logging.getLogger(__name__)

_PLANNER_PROMPT_TEMPLATE = """\
You are a planner for a personal assistant. Your job is to analyze the user's \
message and conversation context, then produce a short plan the main assistant \
will work through and pick the tools it will likely need.

## Available tools

The main assistant has access to the tools below, grouped by category. Pick \
the ones you expect it to need for this turn — err on the side of including \
a tool if you're not sure, since omitting one the agent needs is worse than \
including an extra. A meta tool the agent uses to track plan progress is \
always available; you don't need to list it.

{tool_catalog}

## Output Format
Respond with a JSON object (no markdown fences, no extra text):

{{
  "plan": {{
    "goal": "one sentence framing what the user wants",
    "steps": ["step 1 in plain prose", "step 2 ...", ...]
  }},
  "effort": "low|medium|high",
  "components": [],
  "tool_names": ["tool_name_1", "tool_name_2", ...]
}}

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

**tool_names**: The exact tool names from the catalog above that the assistant \
is likely to need. Include read-only lookup tools you expect will be needed for \
context, plus any write tools required to fulfill the request. Omit the meta \
progress tool — it's always available. Use exact names (e.g. "create_todo", \
not "create todo"). For trivial conversational replies, an empty list is fine.
"""


@lru_cache(maxsize=1)
def get_planner_system_prompt() -> str:
    """Build the planner system prompt with the live tool catalog.

    Cached because the registry is populated once at import time and stable
    for the rest of the process lifetime.
    """
    return _PLANNER_PROMPT_TEMPLATE.format(tool_catalog=get_tool_catalog_for_planner())


@lru_cache(maxsize=1)
def get_planner_prompt_id() -> str:
    """Hex SHA-256 of the rendered planner prompt — used for component versioning."""
    return hashlib.sha256(get_planner_system_prompt().encode("utf-8")).hexdigest()


# Backward-compatible module-level alias for code that imports PLANNER_PROMPT_ID.
# Lazy via __getattr__ so tool registry can populate before this evaluates.
def __getattr__(name: str):
    if name == "PLANNER_PROMPT_ID":
        return get_planner_prompt_id()
    if name == "_PLANNER_SYSTEM_PROMPT":
        return get_planner_system_prompt()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def planner_component() -> ActiveComponent:
    """Return the planner system prompt as a versioned ActiveComponent.

    Used by the orchestrator to upsert the planner prompt into the
    prompt_components table and tag the planner's llm_calls row.
    """
    return ActiveComponent(
        name="planner",
        id=get_planner_prompt_id(),
        raw_text=get_planner_system_prompt(),
        type="planner",
    )


class PlannerResult(BaseModel):
    """Structured output from the planner LLM."""

    plan: TurnPlan = TurnPlan()
    effort: str = "medium"
    components: list[str] = []
    tool_names: list[str] = []


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
    system_prompt = get_planner_system_prompt()
    prompt_id = get_planner_prompt_id()

    try:
        client = get_client()
        with trace_observation(
            name="planner",
            as_type="generation",
            model=PLANNER_MODEL,
            input={"system": system_prompt, "messages": messages},
            metadata={"planner_prompt_id": prompt_id},
        ) as gen:
            response = await client.messages.create(
                model=PLANNER_MODEL,
                max_tokens=PLANNER_MAX_TOKENS,
                system=system_prompt,
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
