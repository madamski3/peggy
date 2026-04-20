"""Reminder tool definitions for the agent.

Registered tools:
  - set_reminder (LOW_STAKES) -- create a todo + push notification
"""

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, tool
from app.services.notifications import schedule_notification
from app.services.timezone import parse_dt
from app.services.todos import create_todo as create_todo_service


class SetReminderInput(BaseModel):
    title: str
    remind_at: str = Field(..., description="ISO 8601 datetime with timezone.")
    description: str | None = None
    estimated_duration_minutes: int = 5


@tool(
    tier=ActionTier.LOW_STAKES,
    category="todo",
    embedding_text=(
        "reminder: set_reminder — remind me, set a reminder, alert me, notification "
        "at a specific time. Remind me to call mom at 3pm. Alert me at 5pm to leave."
    ),
)
async def set_reminder(db: AsyncSession, input: SetReminderInput) -> dict:
    """Set a reminder with push notification at a specific time.

    Creates a scheduled todo plus a push notification in one atomic call. The
    todo tracks what needs doing; the notification triggers delivery via ntfy
    when the scheduled time arrives.
    """
    remind_at_dt = parse_dt(input.remind_at)

    result = await create_todo_service(
        db,
        title=input.title,
        description=input.description,
        scheduled_start=input.remind_at,
        scheduled_end=input.remind_at,
        estimated_duration_minutes=input.estimated_duration_minutes,
    )

    notification = await schedule_notification(
        db,
        todo_id=result["id"],
        title=f"Reminder: {input.title}",
        body=input.description or input.title,
        send_at=remind_at_dt,
    )
    result["notification"] = notification
    result["remind_at"] = input.remind_at
    return result
