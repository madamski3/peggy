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
  - HIGH_STAKES: batch operations or destructive actions (e.g. create_tasks_batch,
    delete_calendar_event) -- the orchestrator pauses and asks the user to confirm
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Coroutine

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


# Global tool registry — populated by tool module imports
TOOL_REGISTRY: dict[str, ToolDefinition] = {}


def register_tool(tool: ToolDefinition) -> None:
    """Register a tool definition into the global registry."""
    TOOL_REGISTRY[tool.name] = tool


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
