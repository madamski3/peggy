"""Context assembly for the agent loop.

This module is responsible for everything that happens *before* the LLM
is called: figuring out what the user is talking about, and loading the
right data to put into the system prompt.

The flow is:
  1. detect_intents() -- keyword-match the user's message to intent categories
  2. assemble_context() -- load profile facts (always), then conditionally
     load today's tasks, calendar, todo backlog, and lists based on intents
  3. build_conversation_messages() -- format prior session turns + new message
     into the Anthropic messages list

The orchestrator calls (2) and (3), then passes the results to the prompt
renderer and the LLM client respectively.
"""

import json
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.conversations import get_session_history
from app.services.lists import get_lists
from app.services.profile import get_active_facts
from app.services.serialization import model_to_dict
from app.services.tasks import get_tasks
from app.services.todos import get_todos


# ── Intent Detection ─────────────────────────────────────────────

INTENT_SIGNALS: dict[str, list[str]] = {
    "planning": [
        "plan my day", "plan tomorrow", "schedule", "what should i do",
        "what's on", "today's plan", "what do i have", "my day",
        "what's happening", "free time",
    ],
    "calendar": [
        "calendar", "meeting", "appointment", "event", "busy",
        "block time", "when am i free", "what's on my calendar",
    ],
    "todo": [
        "todo", "task", "i need to", "remind me", "don't forget",
        "add to my", "pick up", "backlog", "to-do", "to do list",
        "i have to", "i should", "i gotta",
    ],
    "list": [
        "grocery", "groceries", "shopping list", "packing list",
        "list", "what do i need", "add to the list",
    ],
    "financial": [
        "spending", "net worth", "budget", "how much", "finances",
        "money", "account", "balance", "transaction",
    ],
    "profile": [
        "my name", "about me", "i like", "i prefer", "remember that i",
        "my profile", "my preferences",
    ],
}


def detect_intents(message: str) -> set[str]:
    """Simple keyword matching for intent classification.

    Returns a set of detected intent signal names.
    The goal is to front-load likely-needed context; the LLM can
    always call tools for anything missing.
    """
    lower = message.lower()
    return {
        signal
        for signal, keywords in INTENT_SIGNALS.items()
        if any(kw in lower for kw in keywords)
    }


# ── Context Assembly ─────────────────────────────────────────────


async def assemble_context(
    db: AsyncSession,
    user_message: str,
    session_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Build the context dict for system prompt rendering.

    Always includes:
        - current_datetime, timezone
        - profile_summary (core facts)
        - recent conversation turns for the session

    Conditionally includes based on detected intents:
        - todays_tasks (planning)
        - todo_backlog (todo)
        - active_lists (list)
    """
    intents = detect_intents(user_message)

    # ── Resolve user timezone from profile facts ──
    # The timezone fact (identity.timezone) is set via the Profile page.
    # It determines what "now" means for time-dependent context like
    # "today's tasks" and "today's calendar".
    core_facts = await get_active_facts(db)
    user_tz_name = "America/Los_Angeles"
    for fact in core_facts:
        if fact.key == "timezone" and fact.value:
            user_tz_name = fact.value
            break
    user_tz = ZoneInfo(user_tz_name)
    now = datetime.now(user_tz)

    context: dict[str, Any] = {
        "current_datetime": now.strftime("%A, %B %d, %Y at %I:%M %p %Z"),
        "timezone": user_tz_name,
    }
    if core_facts:
        lines = []
        for fact in core_facts:
            lines.append(f"- **{fact.category}.{fact.key}**: {fact.value}")
        context["profile_summary"] = "\n".join(lines)
    else:
        context["profile_summary"] = "No profile information available yet."

    # ── Always: recent conversation history for session continuity ──
    if session_id:
        history = await get_session_history(db, session_id, limit=5)
        if history:
            turns = []
            for h in history:
                if h.get("user_message"):
                    turns.append(f"User: {h['user_message']}")
                if h.get("assistant_response"):
                    resp = h["assistant_response"]
                    summary = resp.get("spoken_summary", str(resp)) if isinstance(resp, dict) else str(resp)
                    turns.append(f"Assistant: {summary}")
            context["conversation_history"] = turns

    # ── Conditional: planning ──
    if "planning" in intents:
        today_str = now.strftime("%Y-%m-%d")
        tasks = await get_tasks(db, {"scheduled_date": today_str})
        if tasks:
            lines = []
            for t in tasks:
                start = t.get("scheduled_start", "unscheduled")
                lines.append(f"- [{t.get('status', '?')}] {t.get('title', '?')} (start: {start})")
            context["todays_tasks"] = "\n".join(lines)

    # ── Conditional: calendar ──
    if "planning" in intents or "calendar" in intents:
        try:
            from app.services.google_calendar import list_events as cal_list_events

            # Build today's time range in ISO format
            today_start = now.strftime("%Y-%m-%dT00:00:00Z")
            today_end = now.strftime("%Y-%m-%dT23:59:59Z")
            events = await cal_list_events(db, time_min=today_start, time_max=today_end)
            if events:
                lines = []
                for e in events:
                    time_str = e.get("start", "?") + " - " + e.get("end", "?")
                    tag = " [assistant]" if e.get("is_assistant_created") else ""
                    lines.append(f"- {e.get('summary', 'No title')} ({time_str}){tag}")
                context["todays_calendar"] = "\n".join(lines)
        except Exception:
            pass  # Calendar not connected or API error — skip silently

    # ── Conditional: todo ──
    if "todo" in intents or "planning" in intents:
        backlog = await get_todos(db, {"status": "backlog"})
        if backlog:
            lines = []
            for t in backlog:
                priority = t.get("priority", "medium")
                deadline = t.get("deadline", "none")
                lines.append(f"- [{priority}] {t.get('title', '?')} (deadline: {deadline})")
            context["todo_backlog"] = "\n".join(lines)

    # ── Conditional: lists ──
    if "list" in intents:
        lists = await get_lists(db, {"status": "active"})
        if lists:
            lines = []
            for lst in lists:
                lines.append(f"- {lst.get('name', '?')} ({lst.get('type', 'custom')}, {lst.get('pending_count', 0)} pending items)")
            context["active_lists"] = "\n".join(lines)

    return context


def build_conversation_messages(
    user_message: str,
    conversation_history: list[dict] | None = None,
) -> list[dict]:
    """Build the Anthropic messages list with conversation history.

    Prepends previous turns from the session, then appends the new user message.
    """
    messages: list[dict] = []

    if conversation_history:
        for turn in conversation_history:
            user_msg = turn.get("user_message")
            assistant_resp = turn.get("assistant_response")
            if user_msg:
                messages.append({"role": "user", "content": user_msg})
            if assistant_resp:
                summary = assistant_resp.get("spoken_summary", str(assistant_resp)) if isinstance(assistant_resp, dict) else str(assistant_resp)
                # Include structured_payload when present (e.g. daily plan
                # with todo IDs) so the LLM can reference it in follow-up turns
                payload = assistant_resp.get("structured_payload") if isinstance(assistant_resp, dict) else None
                if payload:
                    summary += f"\n\n[structured_payload: {json.dumps(payload)}]"
                messages.append({"role": "assistant", "content": summary})

    messages.append({"role": "user", "content": user_message})
    return messages
