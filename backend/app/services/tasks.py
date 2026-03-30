"""Task service layer -- CRUD operations for the Task model.

Tasks are scheduled work blocks linked to a parent Todo. The agent creates
tasks when it decomposes a todo into time-blocked work (e.g. "study for exam"
becomes three 1-hour study sessions).

Key behaviors:
  - create_tasks_batch() creates multiple tasks at once and sets the parent
    todo to "active" status
  - complete_task() auto-completes the parent todo if all sibling tasks are
    now completed/cancelled
  - defer_task() reschedules and increments a deferred_count, which the agent
    can use to detect procrastination patterns
  - cancel_task() is a soft delete (status = "cancelled")

Called by the agent tools (task_tools.py).
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Task, Todo
from app.services.serialization import model_to_dict


async def get_tasks(db: AsyncSession, filters: dict[str, Any] | None = None) -> list[dict]:
    """Query tasks with optional filters.

    Supported filters:
        - status: str
        - todo_id: str (UUID)
        - scheduled_date: str (ISO date — matches tasks scheduled on that day)
        - date_range: dict with 'start' and 'end' (ISO datetimes)
    """
    filters = filters or {}
    query = select(Task)

    if "status" in filters:
        query = query.where(Task.status == filters["status"])
    if "todo_id" in filters:
        query = query.where(Task.todo_id == _parse_uuid(filters["todo_id"]))
    if "scheduled_date" in filters:
        day = datetime.fromisoformat(filters["scheduled_date"]).date()
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=timezone.utc)
        query = query.where(
            and_(
                Task.scheduled_start >= day_start,
                Task.scheduled_start <= day_end,
            )
        )
    if "date_range" in filters:
        dr = filters["date_range"]
        query = query.where(Task.scheduled_start >= datetime.fromisoformat(dr["start"]))
        query = query.where(Task.scheduled_start <= datetime.fromisoformat(dr["end"]))

    query = query.order_by(Task.scheduled_start.asc().nullslast(), Task.position.asc().nullslast())
    result = await db.execute(query)
    return [model_to_dict(t) for t in result.scalars().all()]


async def create_task(db: AsyncSession, **kwargs: Any) -> dict:
    """Create a single task linked to a todo."""
    task = Task(
        todo_id=_parse_uuid(kwargs["todo_id"]),
        title=kwargs["title"],
        description=kwargs.get("description"),
        scheduled_start=_parse_dt(kwargs.get("scheduled_start")),
        scheduled_end=_parse_dt(kwargs.get("scheduled_end")),
        estimated_duration_minutes=kwargs.get("estimated_duration_minutes"),
        position=kwargs.get("position"),
        status="scheduled",
        created_by="assistant",
    )
    db.add(task)
    await db.flush()
    return model_to_dict(task)


async def create_tasks_batch(
    db: AsyncSession, todo_id: str | uuid.UUID, tasks_data: list[dict[str, Any]]
) -> list[dict]:
    """Create multiple tasks for a todo in one transaction.

    Also sets the parent todo status to 'active'.
    """
    tid = _parse_uuid(todo_id)

    # Update parent todo status
    result = await db.execute(select(Todo).where(Todo.id == tid))
    todo = result.scalar_one_or_none()
    if todo is None:
        raise ValueError(f"Todo {todo_id} not found")
    todo.status = "active"
    todo.updated_at = datetime.now(timezone.utc)

    created = []
    for i, td in enumerate(tasks_data):
        task = Task(
            todo_id=tid,
            title=td["title"],
            description=td.get("description"),
            scheduled_start=_parse_dt(td.get("scheduled_start")),
            scheduled_end=_parse_dt(td.get("scheduled_end")),
            estimated_duration_minutes=td.get("estimated_duration_minutes"),
            position=td.get("position", i),
            status="scheduled",
            created_by="assistant",
        )
        db.add(task)
        created.append(task)

    await db.flush()
    return [model_to_dict(t) for t in created]


async def update_task(
    db: AsyncSession, task_id: str | uuid.UUID, fields: dict[str, Any]
) -> dict | None:
    """Partial update of a task's mutable fields."""
    task = await _get_task(db, task_id)
    if task is None:
        return None

    updatable = {
        "title", "description", "scheduled_start", "scheduled_end",
        "estimated_duration_minutes", "status", "position",
    }
    for key, value in fields.items():
        if key in updatable:
            if key in ("scheduled_start", "scheduled_end"):
                value = _parse_dt(value)
            setattr(task, key, value)

    task.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return model_to_dict(task)


async def complete_task(
    db: AsyncSession,
    task_id: str | uuid.UUID,
    actual_duration_minutes: int | None = None,
    completion_notes: str | None = None,
) -> dict | None:
    """Mark a task as completed. Auto-completes parent todo if all siblings are done."""
    task = await _get_task(db, task_id)
    if task is None:
        return None

    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    task.updated_at = datetime.now(timezone.utc)
    if actual_duration_minutes is not None:
        task.actual_duration_minutes = actual_duration_minutes
    if completion_notes is not None:
        task.completion_notes = completion_notes

    await db.flush()

    # Check if all sibling tasks are done -> auto-complete parent todo.
    # This is the cascading completion behavior: when the last task for a
    # todo is completed, the todo itself becomes completed automatically.
    siblings = await db.execute(
        select(Task).where(Task.todo_id == task.todo_id)
    )
    all_tasks = list(siblings.scalars().all())
    if all(t.status in ("completed", "cancelled") for t in all_tasks):
        todo_result = await db.execute(select(Todo).where(Todo.id == task.todo_id))
        todo = todo_result.scalar_one_or_none()
        if todo and todo.status != "completed":
            todo.status = "completed"
            todo.updated_at = datetime.now(timezone.utc)
            await db.flush()

    return model_to_dict(task)


async def defer_task(
    db: AsyncSession,
    task_id: str | uuid.UUID,
    new_scheduled_start: str | datetime | None = None,
    new_scheduled_end: str | datetime | None = None,
) -> dict | None:
    """Reschedule a task and increment its deferred count."""
    task = await _get_task(db, task_id)
    if task is None:
        return None

    task.deferred_count += 1
    if new_scheduled_start is not None:
        task.scheduled_start = _parse_dt(new_scheduled_start)
    if new_scheduled_end is not None:
        task.scheduled_end = _parse_dt(new_scheduled_end)
    task.updated_at = datetime.now(timezone.utc)

    await db.flush()
    return model_to_dict(task)


async def cancel_task(db: AsyncSession, task_id: str | uuid.UUID) -> dict | None:
    """Soft-cancel a task."""
    task = await _get_task(db, task_id)
    if task is None:
        return None

    task.status = "cancelled"
    task.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return model_to_dict(task)


# ── Internal helpers ──────────────────────────────────────────────


async def _get_task(db: AsyncSession, task_id: str | uuid.UUID) -> Task | None:
    result = await db.execute(select(Task).where(Task.id == _parse_uuid(task_id)))
    return result.scalar_one_or_none()


def _parse_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
