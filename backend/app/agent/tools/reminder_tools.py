"""Reminder tool definitions for the agent.

Registered tools:
  - set_reminder (LOW_STAKES) -- create a todo + push notification
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.services.notifications import schedule_notification
from app.services.timezone import parse_dt
from app.services.todos import create_todo


async def handle_set_reminder(db: AsyncSession, **kwargs: Any) -> dict:
    """Create a scheduled todo + push notification in one atomic call.

    This is the "remind me" workflow: the todo tracks what needs doing
    (with a scheduled time), and the notification triggers delivery
    via ntfy when the time arrives (picked up by APScheduler's poll loop).
    """
    remind_at = kwargs["remind_at"]
    title = kwargs["title"]
    description = kwargs.get("description")

    remind_at_dt = parse_dt(remind_at)

    # Create scheduled todo
    result = await create_todo(
        db,
        title=title,
        description=description,
        scheduled_start=kwargs["remind_at"],
        scheduled_end=kwargs["remind_at"],
        estimated_duration_minutes=kwargs.get("estimated_duration_minutes", 5),
    )

    # Schedule push notification linked to the todo
    notification = await schedule_notification(
        db,
        todo_id=result["id"],
        title=f"Reminder: {title}",
        body=description or title,
        send_at=remind_at_dt,
    )
    result["notification"] = notification
    result["remind_at"] = kwargs["remind_at"]
    return result


register_tool(ToolDefinition(
    name="set_reminder",
    description="Set a reminder with push notification at a specific time.",
    embedding_text=(
        "reminder: set_reminder — remind me, set a reminder, alert me, notification "
        "at a specific time. Remind me to call mom at 3pm. Alert me at 5pm to leave."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "remind_at": {"type": "string", "description": "ISO 8601 datetime with timezone."},
            "description": {"type": "string"},
            "estimated_duration_minutes": {"type": "integer"},
        },
        "required": ["title", "remind_at"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_set_reminder,
    category="todo",
))
