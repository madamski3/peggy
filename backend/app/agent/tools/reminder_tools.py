"""Reminder tool definitions for the agent.

Registered tools:
  - set_reminder (LOW_STAKES) -- create a todo + task + push notification
"""

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.services.notifications import schedule_notification
from app.services.todos import create_todo_with_task


async def handle_set_reminder(db: AsyncSession, **kwargs: Any) -> dict:
    """Create a todo + task + scheduled push notification in one atomic call.

    This is the "remind me" workflow: the todo tracks what needs doing,
    the task anchors it to a time, and the notification triggers delivery
    via ntfy when the time arrives (picked up by APScheduler's poll loop).
    """
    remind_at = kwargs["remind_at"]
    title = kwargs["title"]
    description = kwargs.get("description")

    # Parse remind_at to datetime
    if isinstance(remind_at, str):
        remind_at_dt = datetime.fromisoformat(remind_at)
    else:
        remind_at_dt = remind_at

    # Create todo + task
    result = await create_todo_with_task(
        db,
        title=title,
        description=description,
        scheduled_start=kwargs["remind_at"],
        scheduled_end=kwargs["remind_at"],
        estimated_duration_minutes=kwargs.get("estimated_duration_minutes", 5),
    )

    # Schedule push notification linked to the task
    task_id = result["task"]["id"]
    notification = await schedule_notification(
        db,
        task_id=task_id,
        title=f"Reminder: {title}",
        body=description or title,
        send_at=remind_at_dt,
    )
    result["notification"] = notification
    result["remind_at"] = kwargs["remind_at"]
    return result


register_tool(ToolDefinition(
    name="set_reminder",
    description=(
        "Set a reminder for the user. Creates a todo, a scheduled task, and "
        "a push notification at the specified time — all in one call. Use this "
        "when the user says 'remind me to [X] at [time]'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "What to remind the user about (e.g. 'Call the vet')",
            },
            "remind_at": {
                "type": "string",
                "description": "ISO 8601 datetime for when to send the reminder (e.g. '2026-03-29T15:00:00-07:00')",
            },
            "description": {
                "type": "string",
                "description": "Optional additional details for the reminder",
            },
            "estimated_duration_minutes": {
                "type": "integer",
                "description": "Estimated duration in minutes (default: 5)",
            },
        },
        "required": ["title", "remind_at"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_set_reminder,
))
