"""Daily planning tool definitions for the agent.

Provides the execute_daily_plan tool, which atomically creates child
todos with calendar events for an entire daily plan in one confirmation step.

Registered tools:
  - execute_daily_plan  (HIGH_STAKES) -- create child todos + calendar events for a full daily plan
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.services import planning as planning_service


async def handle_execute_daily_plan(db: AsyncSession, **kwargs: Any) -> dict:
    return await planning_service.execute_daily_plan(db, kwargs["plan_items"])


register_tool(ToolDefinition(
    name="execute_daily_plan",
    description="Execute a daily plan: create scheduled child todos with calendar events for multiple parent todos (requires confirmation).",
    embedding_text=(
        "planning: execute_daily_plan — execute, run, activate a daily plan, "
        "batch schedule todos and create calendar events for the day. Plan my day. "
        "Schedule all my todos for today. Create a daily schedule."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "plan_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "todo_id": {"type": "string"},
                        "tasks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                    "scheduled_start": {"type": "string"},
                                    "scheduled_end": {"type": "string"},
                                    "estimated_duration_minutes": {"type": "integer"},
                                },
                                "required": ["title", "scheduled_start", "scheduled_end"],
                            },
                        },
                        "create_calendar_events": {"type": "boolean"},
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
