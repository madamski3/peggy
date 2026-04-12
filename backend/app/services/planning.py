"""Planning service -- orchestrates daily plan execution.

Schedules todos and creates calendar events for approved daily plan
events.  Called by the planning router after the user approves the
proposed plan.

Reuses:
  - app.services.todos.update_todo  (schedule + calendar sync per todo)
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import todos as todo_service

logger = logging.getLogger(__name__)


async def execute_daily_plan(
    db: AsyncSession, approved_events: list[dict[str, Any]]
) -> dict:
    """Execute approved daily plan events: schedule todos + create calendar events.

    Args:
        db: Async database session.
        approved_events: List of flat event dicts, each with:
            - todo_id (str | None): UUID of the todo to schedule (None for calendar-only)
            - title (str): Event title
            - scheduled_start (str): ISO8601 start time
            - scheduled_end (str): ISO8601 end time
            - proposed (bool): Whether this was a new proposal

    Returns:
        Summary dict with todos_scheduled and calendar_events_created.
    """
    todos_scheduled = 0
    calendar_events_created = 0

    for event in approved_events:
        todo_id = event.get("todo_id")
        if not todo_id:
            continue

        result = await todo_service.update_todo(db, todo_id, {
            "scheduled_start": event["scheduled_start"],
            "scheduled_end": event["scheduled_end"],
            "status": "scheduled",
        })

        if result:
            todos_scheduled += 1
            if result.get("calendar_event_id"):
                calendar_events_created += 1

    return {
        "todos_scheduled": todos_scheduled,
        "calendar_events_created": calendar_events_created,
    }
