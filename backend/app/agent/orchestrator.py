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
"""

import json
import logging
import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.client import call_llm
from app.agent.context import INTENT_SIGNALS, assemble_context, build_conversation_messages
from app.agent.tools.registry import (
    ActionTier,
    TOOL_REGISTRY,
    classify_action,
    get_all_tool_schemas,
)
from app.config import settings
from app.prompts.loader import render_prompt
from app.schemas.agent import (
    ActionTaken,
    ChatResponse,
    ConfirmationRequired,
)
from app.services.conversations import get_session_history, log_interaction

logger = logging.getLogger(__name__)

# Ensure tool modules are imported so TOOL_REGISTRY is populated
import app.agent.tools  # noqa: F401


async def run_agent_loop(
    user_message: str,
    session_id: uuid.UUID | None,
    db: AsyncSession,
    confirmation_id: uuid.UUID | None = None,
) -> ChatResponse:
    """Run the full agent loop: context → LLM → tools → response.

    Args:
        user_message: The user's natural language input.
        session_id: Optional session UUID for conversation continuity.
        db: Async database session.
        confirmation_id: If provided, executes the cached HIGH_STAKES tool call
            directly without re-running the LLM.

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
    system_prompt = render_prompt(settings.system_prompt_version, context)

    # ── Step B: Build messages ──
    # Load session history for conversation continuity
    conversation_history = None
    if session_id:
        history = await get_session_history(db, session_id, limit=5)
        if history:
            conversation_history = history

    messages = build_conversation_messages(user_message, conversation_history)

    # ── Step C: Tool-use loop ──
    # Each round: send messages to Claude -> if Claude returns tool_use, execute
    # the tool and append the result to messages -> repeat. If Claude returns
    # end_turn (i.e. it's done calling tools), extract the final text and break.
    actions_taken: list[ActionTaken] = []
    tool_schemas = get_all_tool_schemas()
    final_text = ""

    for round_num in range(settings.agent_max_tool_rounds):
        logger.info(f"Agent loop round {round_num + 1}")

        response = await call_llm(
            messages=messages,
            system=system_prompt,
            tools=tool_schemas,
        )

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
                            db, session_id, user_message, chat_response, actions_taken,
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
        logger.warning(f"Agent loop hit max rounds ({settings.agent_max_tool_rounds})")
        final_text = _extract_text(response.content) if response else ""

    # ── Step D: Response Builder ──
    # Claude is instructed to output a JSON object with spoken_summary,
    # structured_payload, and follow_up_suggestions. _build_response tries to
    # parse that JSON; if parsing fails, the raw text becomes spoken_summary.
    chat_response = _build_response(final_text, actions_taken, session_id)

    # ── Step E+F: Log and commit ──
    await _log_and_commit(db, session_id, user_message, chat_response, actions_taken)
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
) -> None:
    """Log the interaction and commit the transaction."""
    lower_msg = user_message.lower()
    detected_intents = ",".join(sorted(
        s for s, keywords in INTENT_SIGNALS.items()
        if any(kw in lower_msg for kw in keywords)
    )) or None

    try:
        await log_interaction(
            db,
            session_id=session_id,
            channel="chat",
            user_message=user_message,
            parsed_intent=detected_intents,
            assistant_response=chat_response.model_dump(mode="json"),
            actions_taken=[a.model_dump() for a in actions_taken],
        )
    except Exception as e:
        logger.error(f"Failed to log interaction: {e}")

    await db.commit()


# ── Internal helpers ──────────────────────────────────────────────


def _extract_text(content: list) -> str:
    """Extract text from Anthropic content blocks."""
    parts = []
    for block in content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts)


def _serialize_content(content: list) -> list[dict]:
    """Serialize Anthropic content blocks for the messages list."""
    serialized = []
    for block in content:
        if block.type == "text":
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
    if tool_name == "create_tasks_batch":
        tasks = tool_args.get("tasks", [])
        return f"Create {len(tasks)} scheduled tasks for this todo."
    if tool_name == "execute_daily_plan":
        items = tool_args.get("plan_items", [])
        total_tasks = sum(len(i.get("tasks", [])) for i in items)
        return f"Create {total_tasks} tasks across {len(items)} todos and add them to your calendar."
    if tool_name == "delete_calendar_event":
        return "Delete this event from your Google Calendar (irreversible)."
    return f"Execute {tool_name} with the provided arguments."


def _build_confirmation_summary(tool_name: str, tool_args: dict) -> str:
    """Build a spoken summary for a confirmation request."""
    if tool_name == "create_tasks_batch":
        tasks = tool_args.get("tasks", [])
        titles = [t.get("title", "untitled") for t in tasks[:3]]
        preview = ", ".join(titles)
        if len(tasks) > 3:
            preview += f", and {len(tasks) - 3} more"
        return f"I'd like to create {len(tasks)} tasks: {preview}. Should I go ahead?"
    if tool_name == "execute_daily_plan":
        items = tool_args.get("plan_items", [])
        lines = []
        for item in items:
            for t in item.get("tasks", []):
                start = t.get("scheduled_start", "")
                time_str = start[11:16] if len(start) > 16 else start
                lines.append(f"  \u2022 {time_str} \u2014 {t.get('title', 'untitled')}")
        preview = "\n".join(lines[:8])
        total = sum(len(i.get("tasks", [])) for i in items)
        if total > 8:
            preview += f"\n  ... and {total - 8} more"
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
    if tool_name == "create_todo_with_task":
        return f"Created todo with task: {result.get('title', 'untitled')}"
    if tool_name == "create_task":
        return f"Created task: {result.get('title', 'untitled')}"
    if tool_name == "complete_task":
        return f"Completed task: {result.get('title', 'untitled')}"
    if tool_name == "defer_task":
        return f"Deferred task: {result.get('title', 'untitled')}"
    if tool_name == "cancel_task":
        return f"Cancelled task: {result.get('title', 'untitled')}"
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
        return f"Created {result.get('tasks_created', 0)} tasks and {result.get('events_created', 0)} calendar events"

    return f"Executed {tool_name}"
