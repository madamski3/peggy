"""Planning service -- orchestrates daily plan execution.

Combines task creation and calendar event creation into a single atomic
operation. Called by the execute_daily_plan tool after the user confirms
the proposed plan.

Reuses:
  - app.services.tasks.create_tasks_batch  (task creation per todo)
  - app.services.google_calendar.create_event  (GCal event creation)
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import tasks as task_service
from app.services import google_calendar

logger = logging.getLogger(__name__)


async def execute_daily_plan(
    db: AsyncSession, plan_items: list[dict[str, Any]]
) -> dict:
    """Execute a full daily plan: create tasks and optionally calendar events.

    Args:
        db: Async database session.
        plan_items: List of plan items, each with:
            - todo_id (str): UUID of the parent todo
            - tasks (list[dict]): Tasks to create (title, scheduled_start, scheduled_end, etc.)
            - create_calendar_events (bool): Whether to also create GCal events

    Returns:
        Summary dict with tasks_created, events_created, and details.
    """
    total_tasks = 0
    total_events = 0
    details: list[dict] = []

    for item in plan_items:
        todo_id = item["todo_id"]
        tasks_data = item.get("tasks", [])
        create_events = item.get("create_calendar_events", True)

        # Create tasks for this todo
        created_tasks = await task_service.create_tasks_batch(db, todo_id, tasks_data)
        total_tasks += len(created_tasks)

        item_detail: dict[str, Any] = {
            "todo_id": todo_id,
            "tasks_created": len(created_tasks),
            "events_created": 0,
        }

        # Create calendar events for each task (if requested and task has times)
        if create_events:
            for task_data in tasks_data:
                start = task_data.get("scheduled_start")
                end = task_data.get("scheduled_end")
                if start and end:
                    try:
                        result = await google_calendar.create_event(
                            db,
                            summary=task_data.get("title", "Untitled task"),
                            start=start,
                            end=end,
                            description=task_data.get("description", ""),
                        )
                        if "error" not in result:
                            total_events += 1
                            item_detail["events_created"] += 1
                        else:
                            logger.warning(f"Failed to create calendar event: {result['error']}")
                    except Exception as e:
                        logger.error(f"Calendar event creation failed: {e}")

        details.append(item_detail)

    return {
        "tasks_created": total_tasks,
        "events_created": total_events,
        "details": details,
    }
