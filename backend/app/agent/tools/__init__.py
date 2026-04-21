"""Agent tools package.

Importing this package causes all tool modules to execute their
register_tool() calls, populating the global TOOL_REGISTRY. The
orchestrator imports this package at startup to ensure all tools
are available before the first LLM call.
"""

from app.agent.tools import (  # noqa: F401
    calendar_tools,
    conversation_tools,
    gmail_tools,
    list_tools,
    meta_tools,
    planning_tools,
    profile_tools,
    reminder_tools,
    todo_tools,
    weather_tools,
    wiki_tools,
)
