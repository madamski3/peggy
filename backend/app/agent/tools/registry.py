"""Tool registry and action classification.

Central registry for all tools the agent can call. Each tool module
(todo_tools.py, calendar_tools.py, etc.) calls register_tool() at
import time to add itself to the global TOOL_REGISTRY dict.

The orchestrator uses this registry to:
  1. get_all_tool_schemas() -- serialize all tools into Anthropic's format
     for inclusion in the LLM call
  2. TOOL_REGISTRY[name].handler -- look up the async function to execute
  3. classify_action(name) -- determine if a tool call is read-only,
     low-stakes (auto-execute), or high-stakes (needs confirmation)

ActionTier is the safety classification:
  - READ_ONLY: queries data, no side effects (e.g. get_todos, get_calendar_events)
  - LOW_STAKES: creates/modifies data but is easily reversible (e.g. create_todo)
  - HIGH_STAKES: batch operations or destructive actions (e.g. create_sub_todos,
    delete_calendar_event) -- the orchestrator pauses and asks the user to confirm
"""

import inspect
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, Callable, Coroutine

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession


class ActionTier(str, Enum):
    READ_ONLY = "read_only"
    LOW_STAKES = "low_stakes"
    HIGH_STAKES = "high_stakes"


@dataclass
class ToolDefinition:
    """A registered tool that the agent can call."""

    name: str
    description: str
    input_schema: dict[str, Any]
    tier: ActionTier
    handler: Callable[..., Coroutine[Any, Any, Any]]
    category: str = "core"
    embedding_text: str = ""  # rich text for vector search; auto-generated if empty


# Global tool registry — populated by tool module imports
TOOL_REGISTRY: dict[str, ToolDefinition] = {}


def register_tool(tool: ToolDefinition) -> None:
    """Register a tool definition into the global registry."""
    TOOL_REGISTRY[tool.name] = tool


_EMPTY_INPUT_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


def _find_input_model(handler: Callable) -> type[BaseModel] | None:
    """Find a pydantic BaseModel in the handler's non-db parameters."""
    sig = inspect.signature(handler)
    for param in sig.parameters.values():
        ann = param.annotation
        if inspect.isclass(ann) and issubclass(ann, BaseModel):
            return ann
    return None


def tool(
    *,
    tier: ActionTier,
    category: str = "core",
    embedding_text: str = "",
    name: str | None = None,
    input_model: type[BaseModel] | None = None,
):
    """Register an async handler as a tool.

    The handler signature must be either ``(db)`` or ``(db, input: SomeModel)``.
    The input model is auto-detected from the type annotation when not given.
    JSON Schema is generated from the model; description comes from the
    handler's docstring (first paragraph).

    The registered handler is wrapped so the orchestrator can still call it
    as ``await handler(db, **tool_input)``. The wrapper validates the input
    against the pydantic model and returns ``{"error": ...}`` on failure,
    so the agent can self-correct.
    """

    def decorator(handler: Callable[..., Coroutine[Any, Any, Any]]):
        tool_name = name or handler.__name__
        doc = inspect.getdoc(handler) or ""
        description = doc.split("\n\n", 1)[0].strip()

        model = input_model or _find_input_model(handler)
        schema = model.model_json_schema() if model else _EMPTY_INPUT_SCHEMA

        @wraps(handler)
        async def wrapper(db: AsyncSession, **tool_input: Any) -> Any:
            if model is None:
                return await handler(db)
            try:
                validated = model(**tool_input)
            except ValidationError as e:
                return {"error": f"Invalid arguments for {tool_name}: {e.errors()}"}
            return await handler(db, validated)

        register_tool(ToolDefinition(
            name=tool_name,
            description=description,
            input_schema=schema,
            tier=tier,
            handler=wrapper,
            category=category,
            embedding_text=embedding_text,
        ))
        return wrapper

    return decorator


def get_all_tool_schemas() -> list[dict[str, Any]]:
    """Return all tools in Anthropic's tool definition format."""
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in TOOL_REGISTRY.values()
    ]


# Maps detected intents to the tool categories they unlock.
_INTENT_TOOL_CATEGORIES: dict[str, set[str]] = {
    "planning": {"planning", "calendar", "todo"},
    "calendar": {"calendar"},
    "todo": {"todo"},
    "list": {"list"},
    "email": {"email"},
    "profile": {"profile"},
    "financial": {"financial"},
    "conversation": {"conversation"},
}

# Compact descriptions of each tool category for the planner LLM.
CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "todo": (
        "Manage todos: create, update, complete, schedule, reschedule, and query. "
        "Todos can be backlog items or scheduled calendar blocks with automatic "
        "calendar sync. Supports hierarchy (parent/child) for decomposition."
    ),
    "calendar": (
        "Google Calendar: list events, update/delete events, find free time slots "
        "in a date range. Calendar events are created automatically when todos are scheduled."
    ),
    "planning": (
        "Daily planning: batch-schedule todos with calendar events for an entire "
        "day plan in one atomic operation."
    ),
    "list": (
        "Named lists (grocery, packing, custom): create lists, add/complete items, "
        "bulk operations."
    ),
    "email": "Gmail: read recent emails, get email details, search inbox. Read-only.",
    "profile": (
        "Personal knowledge base: semantic search, add, and update facts about the user "
        "(preferences, people/contacts, schedule, career, household, etc.)."
    ),
    "conversation": "Search past conversations and retrieve recent interaction history.",
}


def get_capability_manifest() -> str:
    """Return a formatted capability manifest for the planner LLM."""
    lines = []
    for category, description in CATEGORY_DESCRIPTIONS.items():
        lines.append(f"- {category}: {description}")
    return "\n".join(lines)


# Lightweight read-only tools sent when no intents are detected.
# Covers the most common domains so the model can answer ambiguous queries
# without loading all 35+ tool schemas.
_GENERAL_TOOLS: set[str] = {
    "get_todos",
    "get_calendar_events",
    "search_profile",
    "get_lists",
    "search_conversations",
    "get_recent_emails",
    "wiki_search",
}


def get_tool_schemas_for_intents(intents: set[str]) -> list[dict[str, Any]]:
    """Return tool schemas filtered by detected intents.

    Intent-specific tools are included when their category matches a
    detected intent. When no intents are detected, only a curated set
    of read-only general tools is sent instead of the full registry.
    """
    if not intents:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in TOOL_REGISTRY.values()
            if tool.name in _GENERAL_TOOLS
        ]

    categories: set[str] = set()
    for intent in intents:
        categories.update(_INTENT_TOOL_CATEGORIES.get(intent, set()))

    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in TOOL_REGISTRY.values()
        if tool.category in categories
    ]


def get_tool_schemas_for_categories(categories: set[str]) -> list[dict[str, Any]]:
    """Return tool schemas filtered by tool category names directly.

    Unlike get_tool_schemas_for_intents (which maps intent names to categories
    first), this accepts category names as-is. Used by the planner, which
    outputs category names directly.
    """
    if not categories:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in TOOL_REGISTRY.values()
            if tool.name in _GENERAL_TOOLS
        ]

    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in TOOL_REGISTRY.values()
        if tool.category in categories
    ]


def get_tool_schemas_for_names(tool_names: set[str]) -> list[dict[str, Any]]:
    """Return tool schemas for a specific set of tool names.

    Falls back to _GENERAL_TOOLS when the set is empty.
    """
    if not tool_names:
        tool_names = _GENERAL_TOOLS

    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for name in tool_names
        if (tool := TOOL_REGISTRY.get(name)) is not None
    ]


def classify_action(tool_name: str) -> ActionTier:
    """Look up the action tier for a tool by name."""
    tool = TOOL_REGISTRY.get(tool_name)
    if tool is None:
        # Unknown tools default to high-stakes for safety
        return ActionTier.HIGH_STAKES
    return tool.tier


def get_handler(tool_name: str) -> Callable | None:
    """Get the handler function for a tool."""
    tool = TOOL_REGISTRY.get(tool_name)
    return tool.handler if tool else None
