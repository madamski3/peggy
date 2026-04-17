"""Agent orchestrator -- the core of the application.

This is the most important file in the backend. It implements the full
agent loop that turns a user message into a ChatResponse:

  A. Context assembly  -- build the system prompt with relevant data
  B. Message building   -- prepend conversation history, append user message
  C. Tool-use loop      -- call Claude, execute tool calls, feed results back
                           (up to agent_max_tool_rounds iterations)
  D. Response parsing   -- extract spoken_summary / structured_payload from
                           Claude's final text output
  E. Interaction logging -- persist to the interactions table
  F. Commit and return

The loop has a safety mechanism: each tool has an ActionTier. HIGH_STAKES
tools (e.g. batch task creation, calendar deletion) cause the loop to halt
early and return a ConfirmationRequired response. The frontend shows an
Approve/Reject card, and if the user approves, the original message is
re-sent with a confirmation_id to resume execution.

Streaming: the orchestrator accepts an optional status_callback coroutine.
When provided, it emits progress messages during the agent loop so the
SSE endpoint can stream real-time status updates to the frontend.
"""

import asyncio
import json
import logging
import re
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.client import call_llm
from app.agent.context import assemble_context, build_conversation_messages, detect_intents
from app.agent.planner import PlannerResult, run_planner
from app.agent.tools.registry import (
    ActionTier,
    TOOL_REGISTRY,
    classify_action,
    get_tool_schemas_for_names,
)
from app.agent.tool_selector import select_tools
from app.globals import AGENT_MAX_TOOL_ROUNDS
from app.prompts.composer import compose_prompt
from app.schemas.agent import (
    ActionTaken,
    ChatResponse,
    ConfirmationRequired,
)
from app.services.conversations import (
    backfill_llm_call_interaction_id,
    get_session_history,
    log_interaction,
    log_llm_call,
)

logger = logging.getLogger(__name__)

# Ensure tool modules are imported so TOOL_REGISTRY is populated
import app.agent.tools  # noqa: F401

# Type alias for the optional streaming status callback
StatusCallback = Callable[[str], Coroutine[Any, Any, None]]

# Friendly labels for tool names in status messages
_TOOL_STATUS_LABELS: dict[str, str] = {
    "get_todos": "Checking your todos",
    "get_calendar_events": "Looking at your calendar",
    "find_free_time": "Finding free time slots",
    "create_todo": "Creating a todo",
    "update_todo": "Updating a todo",
    "create_sub_todos": "Breaking down into sub-tasks",
    "execute_daily_plan": "Scheduling your day",
    "get_recent_emails": "Checking your email",
    "search_emails": "Searching your email",
    "search_profile": "Looking up your profile",
    "add_profile_fact": "Saving to your profile",
    "wiki_search": "Searching your wiki",
    "write_wiki_page": "Updating wiki",
    "get_current_weather": "Checking the weather",
    "get_weather_forecast": "Getting the forecast",
    "create_list": "Creating a list",
    "search_conversations": "Searching past conversations",
    "set_reminder": "Setting a reminder",
}


def _tool_status_label(tool_name: str) -> str:
    """Get a user-friendly status label for a tool call."""
    return _TOOL_STATUS_LABELS.get(tool_name, f"Running {tool_name.replace('_', ' ')}")


async def run_agent_loop(
    user_message: str,
    session_id: uuid.UUID | None,
    db: AsyncSession,
    confirmation_id: uuid.UUID | None = None,
    channel: str = "chat",
    status_callback: StatusCallback | None = None,
) -> ChatResponse:
    """Run the full agent loop: context → LLM → tools → response.

    Args:
        user_message: The user's natural language input.
        session_id: Optional session UUID for conversation continuity.
        db: Async database session.
        confirmation_id: If provided, executes the cached HIGH_STAKES tool call
            directly without re-running the LLM.
        channel: Interaction channel — "chat" for user-initiated, "proactive"
            for scheduler-triggered invocations.
        status_callback: Optional async function that receives status strings
            during the agent loop. Used by the SSE endpoint for streaming.

    Returns:
        A ChatResponse with spoken_summary, structured_payload, actions, etc.
    """
    session_id = session_id or uuid.uuid4()

    # ── Fast path: confirmation approval ──
    # When the user approves a HIGH_STAKES action, execute the cached tool call
    # directly instead of re-running the LLM (which is non-deterministic).
    if confirmation_id is not None:
        return await _execute_confirmed_action(db, session_id, user_message, confirmation_id)

    # ── Step A: Context Assembly ──
    context = await assemble_context(db, user_message, session_id)

    # ── Step A.1: Load conversation history (planner needs it) ──
    conversation_history = None
    if session_id:
        history = await get_session_history(db, session_id, limit=3)
        if history:
            conversation_history = history

    # ── Step A.2: Run planner + tool selector in parallel ──
    plan, tool_selection = await asyncio.gather(
        run_planner(user_message, conversation_history),
        select_tools(user_message, conversation_history),
    )
    if plan.raw_response:
        await log_llm_call(db, session_id, 0, plan.raw_response)
    logger.info(f"Planner: effort={plan.result.effort}, components={plan.result.components}")

    if status_callback:
        await status_callback("Thinking...")

    selected_tool_names = tool_selection.selected

    # Force-include channel-specific tools that the vector selector may miss
    _CHANNEL_REQUIRED_TOOLS: dict[str, set[str]] = {
        "wiki_review": {
            "write_wiki_page", "update_wiki_index", "wiki_search",
            "add_profile_fact", "search_profile",
        },
    }
    if channel in _CHANNEL_REQUIRED_TOOLS:
        selected_tool_names |= _CHANNEL_REQUIRED_TOOLS[channel]

    ranked_scores = sorted(tool_selection.scores.items(), key=lambda x: x[1], reverse=True)
    logger.debug(f"Tool selector scores: {ranked_scores}")
    selected_with_scores = [
        (name, score) for name, score in ranked_scores if name in selected_tool_names
    ]
    logger.info(f"Tool selector: {selected_with_scores}")

    # ── Step A.3: Compose system prompt from relevant components ──
    context["strategy"] = plan.result.strategy
    system_prompt = compose_prompt(
        context=context,
        planner_components=plan.result.components,
        channel=channel,
    )

    # ── Step B: Build messages ──
    messages = build_conversation_messages(user_message, conversation_history)
    turn_start = len(messages)  # index where this turn's messages begin

    # ── Step C: Tool-use loop ──
    # Each round: send messages to Claude -> if Claude returns tool_use, execute
    # the tool and append the result to messages -> repeat. If Claude returns
    # end_turn (i.e. it's done calling tools), extract the final text and break.
    actions_taken: list[ActionTaken] = []
    tool_schemas = get_tool_schemas_for_names(selected_tool_names)
    tool_names_for_llm = sorted(t["name"] for t in tool_schemas)
    logger.info(f"Tools for LLM: {tool_names_for_llm}")
    tools_meta = {
        "selected": sorted(selected_tool_names),
        "scores": ranked_scores,
    }
    final_text = ""

    for round_num in range(AGENT_MAX_TOOL_ROUNDS):
        logger.info(f"Agent loop round {round_num + 1}")

        # Emit "composing" status on subsequent rounds (after tool results)
        if status_callback and round_num > 0:
            await status_callback("Composing response...")

        response = await call_llm(
            messages=messages,
            system=system_prompt,
            tools=tool_schemas,
            effort=plan.result.effort,
        )

        await log_llm_call(db, session_id, round_num + 1, response, tools=tools_meta)

        # Check if Claude refused the request
        if response.stop_reason == "refusal":
            final_text = _extract_text(response.content) or "I'm not able to help with that request."
            break

        # Check if Claude is done (final text response)
        if response.stop_reason == "end_turn":
            # Extract text from content blocks
            final_text = _extract_text(response.content)
            break

        # Process tool calls
        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tier = classify_action(tool_name)

                    logger.info(f"Tool call: {tool_name} (tier={tier.value})")

                    # Emit status for the tool being called
                    if status_callback:
                        await status_callback(f"{_tool_status_label(tool_name)}...")

                    # HIGH_STAKES check — halt and request confirmation
                    if tier == ActionTier.HIGH_STAKES:
                        description = _describe_action(tool_name, tool_input)
                        chat_response = ChatResponse(
                            spoken_summary=_build_confirmation_summary(tool_name, tool_input),
                            confirmation_required=ConfirmationRequired(
                                tool_name=tool_name,
                                tool_args=tool_input,
                                description=description,
                            ),
                            actions_taken=actions_taken,
                            session_id=session_id,
                        )
                        # Log the confirmation interaction before returning
                        await _log_and_commit(
                            db, session_id, user_message, chat_response, actions_taken, channel,
                            planner_result=plan.result,
                        )
                        return chat_response

                    # Execute the tool
                    try:
                        handler = TOOL_REGISTRY[tool_name].handler
                        result = await handler(db, **tool_input)
                    except Exception as e:
                        logger.error(f"Tool {tool_name} failed: {e}")
                        result = {"error": str(e)}

                    # Build tool result for Anthropic
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })

                    # Track non-read-only actions
                    if tier != ActionTier.READ_ONLY:
                        actions_taken.append(ActionTaken(
                            tool_name=tool_name,
                            tool_args=tool_input,
                            result_summary=_summarize_result(tool_name, result),
                        ))
                elif block.type == "text":
                    # Claude may emit text alongside tool calls
                    pass

            # Append the assistant's response and tool results for the next round
            messages.append({"role": "assistant", "content": _serialize_content(response.content)})
            messages.append({"role": "user", "content": tool_results})
        else:
            # Unexpected stop reason — extract what we can
            final_text = _extract_text(response.content)
            break
    else:
        # Exhausted max rounds
        logger.warning(f"Agent loop hit max rounds ({AGENT_MAX_TOOL_ROUNDS})")
        final_text = _extract_text(response.content) if response else ""

    # Append the final assistant response so the chain is complete
    if response and response.content:
        messages.append({"role": "assistant", "content": _serialize_content(response.content)})

    # Extract this turn's messages (excluding replayed history)
    turn_messages = messages[turn_start:]

    # ── Step D: Response Builder ──
    # Claude is instructed to output a JSON object with spoken_summary,
    # structured_payload, and follow_up_suggestions. _build_response tries to
    # parse that JSON; if parsing fails, the raw text becomes spoken_summary.
    chat_response = _build_response(final_text, actions_taken, session_id)

    # ── Step E+F: Log and commit ──
    await _log_and_commit(
        db, session_id, user_message, chat_response, actions_taken, channel,
        message_chain=turn_messages,
        planner_result=plan.result,
    )
    return chat_response


async def _execute_confirmed_action(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_message: str,
    confirmation_id: uuid.UUID,
) -> ChatResponse:
    """Execute a previously-confirmed HIGH_STAKES tool call directly.

    Looks up the most recent interaction in the session that has a
    confirmation_required field, extracts the cached tool_name and tool_args,
    and executes the tool without re-running the LLM.
    """
    # Find the pending confirmation from session history
    history = await get_session_history(db, session_id, limit=10)
    pending_tool_name = None
    pending_tool_args = None

    for turn in reversed(history):
        resp = turn.get("assistant_response", {})
        conf = resp.get("confirmation_required") if isinstance(resp, dict) else None
        if conf and str(conf.get("confirmation_id")) == str(confirmation_id):
            pending_tool_name = conf["tool_name"]
            pending_tool_args = conf["tool_args"]
            break

    if not pending_tool_name:
        logger.warning(f"No pending confirmation found for id={confirmation_id}")
        return ChatResponse(
            spoken_summary="I couldn't find the action to confirm. Could you try again?",
            session_id=session_id,
        )

    # Execute the cached tool call
    logger.info(f"Executing confirmed tool: {pending_tool_name}")
    actions_taken: list[ActionTaken] = []

    try:
        handler = TOOL_REGISTRY[pending_tool_name].handler
        result = await handler(db, **pending_tool_args)
    except Exception as e:
        logger.error(f"Confirmed tool {pending_tool_name} failed: {e}")
        result = {"error": str(e)}

    if "error" in result:
        summary = f"Something went wrong: {result['error']}"
    else:
        summary = _summarize_result(pending_tool_name, result)

    actions_taken.append(ActionTaken(
        tool_name=pending_tool_name,
        tool_args=pending_tool_args,
        result_summary=_summarize_result(pending_tool_name, result),
    ))

    # Build a friendly spoken summary
    if "error" not in result:
        spoken = f"Done! {summary}."
    else:
        spoken = summary

    chat_response = ChatResponse(
        spoken_summary=spoken,
        actions_taken=actions_taken,
        session_id=session_id,
    )

    await _log_and_commit(db, session_id, user_message, chat_response, actions_taken)
    return chat_response


async def _log_and_commit(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_message: str,
    chat_response: ChatResponse,
    actions_taken: list[ActionTaken],
    channel: str = "chat",
    message_chain: list[dict[str, Any]] | None = None,
    planner_result: PlannerResult | None = None,
) -> None:
    """Log the interaction and commit the transaction."""
    if planner_result:
        parsed_intent = planner_result.model_dump_json()
    else:
        parsed_intent = ",".join(sorted(detect_intents(user_message))) or None

    try:
        interaction = await log_interaction(
            db,
            session_id=session_id,
            channel=channel,
            user_message=user_message,
            parsed_intent=parsed_intent,
            assistant_response=chat_response.model_dump(mode="json"),
            actions_taken=[a.model_dump() for a in actions_taken],
            message_chain=message_chain,
        )
        await backfill_llm_call_interaction_id(db, session_id, interaction.id)
    except Exception as e:
        logger.error(f"Failed to log interaction: {e}")

    await db.commit()


# ── Internal helpers ──────────────────────────────────────────────


def _extract_text(content: list) -> str:
    """Extract text from Anthropic content blocks, skipping thinking blocks."""
    parts = []
    for block in content:
        if block.type == "text":
            parts.append(block.text)
    return "\n".join(parts)


def _serialize_content(content: list) -> list[dict]:
    """Serialize Anthropic content blocks for the messages list."""
    serialized = []
    for block in content:
        if block.type == "thinking":
            serialized.append({
                "type": "thinking",
                "thinking": block.thinking,
                "signature": block.signature,
            })
        elif block.type == "text":
            serialized.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            serialized.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
    return serialized


def _build_response(
    final_text: str,
    actions_taken: list[ActionTaken],
    session_id: uuid.UUID,
) -> ChatResponse:
    """Parse Claude's final text into a ChatResponse.

    Tries to extract JSON from the text. Falls back to using the
    entire text as spoken_summary.
    """
    parsed = _try_parse_response_json(final_text)

    if parsed:
        return ChatResponse(
            spoken_summary=parsed.get("spoken_summary", final_text.strip()),
            structured_payload=parsed.get("structured_payload"),
            actions_taken=actions_taken,
            follow_up_suggestions=parsed.get("follow_up_suggestions", []),
            session_id=session_id,
        )

    # Fallback: treat the whole text as spoken_summary
    return ChatResponse(
        spoken_summary=final_text.strip() or "I've completed the requested actions.",
        actions_taken=actions_taken,
        session_id=session_id,
    )


def _try_parse_response_json(text: str) -> dict | None:
    """Try to extract a JSON response object from Claude's text.

    Looks for JSON in markdown code fences first, then tries raw parse.
    """
    if not text:
        return None

    # Try markdown code fence extraction
    pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try raw JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    return None


def _describe_action(tool_name: str, tool_args: dict) -> str:
    """Generate a human-readable description of a pending action."""
    if tool_name == "create_sub_todos":
        children = tool_args.get("children", [])
        return f"Create {len(children)} scheduled items for this todo."
    if tool_name == "execute_daily_plan":
        events = tool_args.get("events", [])
        proposed = [e for e in events if e.get("proposed")]
        return f"Schedule {len(proposed)} todos and add them to your calendar."
    if tool_name == "delete_calendar_event":
        return "Delete this event from your Google Calendar (irreversible)."
    return f"Execute {tool_name} with the provided arguments."


def _build_confirmation_summary(tool_name: str, tool_args: dict) -> str:
    """Build a spoken summary for a confirmation request."""
    if tool_name == "create_sub_todos":
        children = tool_args.get("children", [])
        titles = [c.get("title", "untitled") for c in children[:3]]
        preview = ", ".join(titles)
        if len(children) > 3:
            preview += f", and {len(children) - 3} more"
        return f"I'd like to create {len(children)} items: {preview}. Should I go ahead?"
    if tool_name == "execute_daily_plan":
        events = tool_args.get("events", [])
        lines = []
        for ev in events:
            if ev.get("proposed"):
                start = ev.get("scheduled_start", "")
                time_str = start[11:16] if len(start) > 16 else start
                lines.append(f"  \u2022 {time_str} \u2014 {ev.get('title', 'untitled')}")
        preview = "\n".join(lines[:8])
        if len(lines) > 8:
            preview += f"\n  ... and {len(lines) - 8} more"
        return f"Here's the plan I'd like to lock in:\n{preview}\n\nShall I go ahead?"
    return "I need your confirmation before proceeding with this action."


def _summarize_result(tool_name: str, result: dict) -> str:
    """Generate a brief summary of a tool execution result."""
    if "error" in result:
        return f"Error: {result['error']}"

    if tool_name == "create_todo":
        return f"Created todo: {result.get('title', 'untitled')}"
    if tool_name == "complete_todo":
        return f"Completed todo: {result.get('title', 'untitled')}"
    if tool_name == "cancel_todo":
        return f"Cancelled todo: {result.get('title', 'untitled')}"
    if tool_name == "reschedule_todo":
        return f"Rescheduled todo: {result.get('title', 'untitled')}"
    if tool_name == "create_sub_todos":
        return f"Created {result.get('count', 0)} sub-items"
    if tool_name == "set_reminder":
        return f"Reminder set: {result.get('title', 'untitled')} at {result.get('remind_at', '?')}"
    if tool_name == "create_list":
        return f"Created list: {result.get('name', 'untitled')}"
    if tool_name == "add_list_item":
        return f"Added item: {result.get('name', 'untitled')}"
    if tool_name == "complete_list_item":
        return f"Completed item: {result.get('name', 'untitled')}"
    if tool_name == "bulk_complete_list_items":
        return f"Completed {result.get('completed_count', 0)} items"
    if tool_name == "add_profile_fact":
        return f"Added fact: {result.get('category', '?')}.{result.get('key', '?')}"
    if tool_name == "update_profile_fact":
        return f"Updated fact: {result.get('category', '?')}.{result.get('key', '?')}"
    if tool_name == "create_calendar_event":
        return f"Created calendar event: {result.get('summary', 'untitled')}"
    if tool_name == "update_calendar_event":
        return f"Updated calendar event: {result.get('summary', 'untitled')}"
    if tool_name == "delete_calendar_event":
        return "Deleted calendar event"
    if tool_name == "find_free_time":
        return f"Found {result.get('count', 0)} free time slots"
    if tool_name == "execute_daily_plan":
        return f"Scheduled {result.get('items_created', 0)} items and created {result.get('events_created', 0)} calendar events"

    return f"Executed {tool_name}"
