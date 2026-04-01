"""Context assembly for the agent loop.

This module is responsible for everything that happens *before* the LLM
is called: detecting intents and building the minimal context dict for
system prompt rendering.

The flow is:
  1. detect_intents() -- keyword-match the user's message to intent categories
  2. assemble_context() -- resolve datetime/timezone/user name, detect intents
  3. build_conversation_messages() -- format prior session turns + new message
     into the Anthropic messages list

All data (tasks, calendar, todos, lists, emails, profile) is fetched by
the agent via tool calls — NOT pre-loaded into the system prompt.
"""

import json
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.profile import get_active_facts


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
    "email": [
        "email", "emails", "gmail", "inbox", "message from",
        "mail", "unread", "shipping", "confirmation email",
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
    """Build the minimal context dict for system prompt rendering.

    Returns datetime, timezone, user name, and detected intents.
    All data (tasks, calendar, todos, etc.) is fetched by the agent
    via tool calls — not pre-loaded here.
    """
    intents = detect_intents(user_message)

    # Resolve user timezone and name from profile facts
    core_facts = await get_active_facts(db)
    user_tz_name = "America/Los_Angeles"
    user_name = None
    for fact in core_facts:
        if fact.key == "timezone" and fact.value:
            user_tz_name = fact.value
        if fact.key == "name" and fact.value:
            user_name = fact.value
    user_tz = ZoneInfo(user_tz_name)
    now = datetime.now(user_tz)

    return {
        "current_datetime": now.strftime("%A, %B %d, %Y at %I:%M %p %Z"),
        "timezone": user_tz_name,
        "user_name": user_name or "the user",
        "intents": intents,
    }


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
