"""Planning service -- orchestrates daily plan execution.

Creates child todos (with calendar events) under parent todos for
an entire daily plan in a single atomic operation. Called by the
execute_daily_plan tool after the user confirms the proposed plan.

Reuses:
  - app.services.todos.create_child_todos_batch  (child todo creation per parent)
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import todos as todo_service

logger = logging.getLogger(__name__)


async def execute_daily_plan(
    db: AsyncSession, plan_items: list[dict[str, Any]]
) -> dict:
    """Execute a full daily plan: create child todos with calendar events.

    Args:
        db: Async database session.
        plan_items: List of plan items, each with:
            - todo_id (str): UUID of the parent todo
            - tasks (list[dict]): Children to create (title, scheduled_start, scheduled_end, etc.)
            - create_calendar_events (bool): Whether to also create GCal events
              (calendar events are now created automatically by _sync_calendar
              whenever a todo has scheduled times, so this flag is informational)

    Returns:
        Summary dict with items_created, events_created, and details.
    """
    total_items = 0
    details: list[dict] = []

    for item in plan_items:
        todo_id = item["todo_id"]
        children_data = item.get("tasks", [])

        created = await todo_service.create_child_todos_batch(db, todo_id, children_data)
        total_items += len(created)

        events_created = sum(1 for c in created if c.get("calendar_event_id"))
        details.append({
            "todo_id": todo_id,
            "items_created": len(created),
            "events_created": events_created,
        })

    total_events = sum(d["events_created"] for d in details)

    return {
        "items_created": total_items,
        "events_created": total_events,
        "details": details,
    }
