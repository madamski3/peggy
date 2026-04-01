"""Daily planning tool definitions for the agent.

Provides the execute_daily_plan tool, which atomically creates tasks
and calendar events for an entire daily plan in one confirmation step.

Registered tools:
  - execute_daily_plan  (HIGH_STAKES) -- create tasks + calendar events for a full daily plan
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.services import planning as planning_service


async def handle_execute_daily_plan(db: AsyncSession, **kwargs: Any) -> dict:
    return await planning_service.execute_daily_plan(db, kwargs["plan_items"])


register_tool(ToolDefinition(
    name="execute_daily_plan",
    description=(
        "Execute a full daily plan: create scheduled tasks for multiple todos and "
        "add corresponding calendar events. Use this after presenting a proposed "
        "daily plan and receiving user confirmation. This is a high-stakes action — "
        "always present the plan first and wait for the user to approve."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "plan_items": {
                "type": "array",
                "description": "List of plan items, one per todo to schedule.",
                "items": {
                    "type": "object",
                    "properties": {
                        "todo_id": {
                            "type": "string",
                            "description": "UUID of the parent todo.",
                        },
                        "tasks": {
                            "type": "array",
                            "description": "Tasks to create for this todo.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                    "scheduled_start": {
                                        "type": "string",
                                        "description": "ISO 8601 datetime with timezone.",
                                    },
                                    "scheduled_end": {
                                        "type": "string",
                                        "description": "ISO 8601 datetime with timezone.",
                                    },
                                    "estimated_duration_minutes": {"type": "integer"},
                                },
                                "required": ["title", "scheduled_start", "scheduled_end"],
                            },
                        },
                        "create_calendar_events": {
                            "type": "boolean",
                            "description": "Whether to also create Google Calendar events for these tasks (default: true).",
                        },
                    },
                    "required": ["todo_id", "tasks"],
                },
            },
        },
        "required": ["plan_items"],
    },
    tier=ActionTier.HIGH_STAKES,
    handler=handle_execute_daily_plan,
    category="planning",
))
