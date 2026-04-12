"""Daily planning tool definitions for the agent.

Provides the execute_daily_plan tool, which schedules todos and creates
calendar events for an approved daily plan.

Registered tools:
  - execute_daily_plan  (HIGH_STAKES) -- schedule todos + create calendar events for a daily plan
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.services import planning as planning_service


async def handle_execute_daily_plan(db: AsyncSession, **kwargs: Any) -> dict:
    return await planning_service.execute_daily_plan(db, kwargs["events"])


register_tool(ToolDefinition(
    name="execute_daily_plan",
    description="Execute a daily plan: schedule todos and create calendar events for approved plan events (requires confirmation).",
    embedding_text=(
        "planning: execute_daily_plan — execute, run, activate a daily plan, "
        "batch schedule todos and create calendar events for the day. Plan my day. "
        "Schedule all my todos for today. Create a daily schedule."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "scheduled_start": {"type": "string"},
                        "scheduled_end": {"type": "string"},
                        "todo_id": {"type": ["string", "null"]},
                        "proposed": {"type": "boolean"},
                    },
                    "required": ["title", "scheduled_start", "scheduled_end", "todo_id", "proposed"],
                },
            },
        },
        "required": ["events"],
    },
    tier=ActionTier.HIGH_STAKES,
    handler=handle_execute_daily_plan,
    category="planning",
))
