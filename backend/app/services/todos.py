"""Todo service layer -- CRUD operations for the Todo model.

Todos are the top-level backlog items. They can have zero or more child
Tasks (scheduled work blocks). The lifecycle is:
  backlog -> active (once tasks are created) -> completed / cancelled

Key behaviors:
  - create_todo() always starts in "backlog" status
  - complete_todo() cancels any remaining unfinished tasks
  - create_todo_with_task() is a convenience shortcut that creates both
    a todo and a single task atomically, going straight to "active" status
  - get_todos() supports rich filtering (status, priority, deadline, tags,
    has_scheduled_tasks)

Called by both the agent tools (todo_tools.py) and could be called by
future REST endpoints.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tables import Task, Todo
from app.services.serialization import model_to_dict
from app.services.timezone import parse_dt


async def get_todos(db: AsyncSession, filters: dict[str, Any] | None = None) -> list[dict]:
    """Query todos with optional filters.

    Supported filters:
        - status: str
        - priority: str
        - deadline_before: str (ISO datetime)
        - tags: list[str] (match any)
        - has_scheduled_tasks: bool
    """
    filters = filters or {}
    query = select(Todo).options(selectinload(Todo.tasks))

    if "status" in filters:
        query = query.where(Todo.status == filters["status"])
    if "priority" in filters:
        query = query.where(Todo.priority == filters["priority"])
    if "deadline_before" in filters:
        deadline = parse_dt(filters["deadline_before"])
        query = query.where(Todo.deadline <= deadline)
    if "tags" in filters:
        for tag in filters["tags"]:
            query = query.where(Todo.tags.contains([tag]))

    query = query.order_by(Todo.created_at.desc())
    result = await db.execute(query)
    todos = list(result.scalars().unique().all())

    # Post-filter: has_scheduled_tasks
    if "has_scheduled_tasks" in filters:
        want_tasks = filters["has_scheduled_tasks"]
        todos = [
            t for t in todos
            if (len(t.tasks) > 0) == want_tasks
        ]

    return [_todo_summary(t) for t in todos]


async def create_todo(db: AsyncSession, **kwargs: Any) -> dict:
    """Create a new todo in the backlog."""
    todo = Todo(
        title=kwargs["title"],
        description=kwargs.get("description"),
        status="backlog",
        priority=kwargs.get("priority", "medium"),
        deadline=_parse_dt(kwargs.get("deadline")),
        target_date=_parse_dt(kwargs.get("target_date")),
        preferred_window=kwargs.get("preferred_window"),
        estimated_duration_minutes=kwargs.get("estimated_duration_minutes"),
        energy_level=kwargs.get("energy_level"),
        location=kwargs.get("location"),
        tags=kwargs.get("tags"),
        parent_todo_id=_parse_uuid(kwargs.get("parent_todo_id")),
        created_by="assistant",
    )
    db.add(todo)
    await db.flush()
    return model_to_dict(todo)


async def update_todo(
    db: AsyncSession, todo_id: str | uuid.UUID, fields: dict[str, Any]
) -> dict | None:
    """Partial update of a todo's mutable fields."""
    todo = await _get_todo(db, todo_id)
    if todo is None:
        return None

    updatable = {
        "title", "description", "status", "priority", "deadline",
        "target_date", "preferred_window", "estimated_duration_minutes",
        "energy_level", "location", "tags", "notes",
    }
    for key, value in fields.items():
        if key in updatable:
            if key in ("deadline", "target_date"):
                value = _parse_dt(value)
            setattr(todo, key, value)

    todo.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return model_to_dict(todo)


async def complete_todo(db: AsyncSession, todo_id: str | uuid.UUID) -> dict | None:
    """Mark a todo as completed. Cancels any remaining unfinished tasks."""
    todo = await db.execute(
        select(Todo).options(selectinload(Todo.tasks)).where(Todo.id == _parse_uuid(todo_id))
    )
    todo = todo.scalar_one_or_none()
    if todo is None:
        return None

    todo.status = "completed"
    todo.updated_at = datetime.now(timezone.utc)

    # Cancel remaining unfinished tasks
    for task in todo.tasks:
        if task.status not in ("completed", "cancelled"):
            task.status = "cancelled"
            task.updated_at = datetime.now(timezone.utc)

    await db.flush()
    return model_to_dict(todo)


async def get_todo_detail(db: AsyncSession, todo_id: str | uuid.UUID) -> dict | None:
    """Return a todo with all its tasks eagerly loaded."""
    result = await db.execute(
        select(Todo).options(selectinload(Todo.tasks)).where(Todo.id == _parse_uuid(todo_id))
    )
    todo = result.scalar_one_or_none()
    if todo is None:
        return None

    todo_dict = model_to_dict(todo)
    todo_dict["tasks"] = [model_to_dict(t) for t in todo.tasks]
    return todo_dict


async def create_todo_with_task(db: AsyncSession, **kwargs: Any) -> dict:
    """Shortcut: create a todo + single task atomically. Todo goes to 'active' status.

    Also creates a Google Calendar event if the task has scheduled start/end times,
    so the user sees it on their calendar alongside other events.
    """
    todo = Todo(
        title=kwargs["title"],
        description=kwargs.get("description"),
        status="active",
        priority=kwargs.get("priority", "medium"),
        estimated_duration_minutes=kwargs.get("estimated_duration_minutes"),
        created_by="assistant",
    )
    db.add(todo)
    await db.flush()

    task = Task(
        todo_id=todo.id,
        title=kwargs["title"],
        scheduled_start=_parse_dt(kwargs.get("scheduled_start")),
        scheduled_end=_parse_dt(kwargs.get("scheduled_end")),
        estimated_duration_minutes=kwargs.get("estimated_duration_minutes"),
        status="scheduled",
        created_by="assistant",
    )
    db.add(task)
    await db.flush()

    todo_dict = model_to_dict(todo)
    todo_dict["task"] = model_to_dict(task)

    # Create a calendar event if the task has scheduled times
    start = kwargs.get("scheduled_start")
    end = kwargs.get("scheduled_end")
    if start and end and start != end:
        try:
            from app.services.google_calendar import create_event
            event_result = await create_event(
                db,
                summary=kwargs["title"],
                start=start,
                end=end,
                description=kwargs.get("description", ""),
            )
            if "error" not in event_result:
                todo_dict["calendar_event"] = event_result
        except Exception:
            pass  # Calendar not connected or API error — skip silently

    return todo_dict


# ── Internal helpers ──────────────────────────────────────────────


def _todo_summary(todo: Todo) -> dict:
    """Build a summary dict for a todo, including task count."""
    d = model_to_dict(todo)
    d["task_count"] = len(todo.tasks) if todo.tasks else 0
    d["completed_task_count"] = sum(
        1 for t in (todo.tasks or []) if t.status == "completed"
    )
    return d


async def _get_todo(db: AsyncSession, todo_id: str | uuid.UUID) -> Todo | None:
    result = await db.execute(select(Todo).where(Todo.id == _parse_uuid(todo_id)))
    return result.scalar_one_or_none()


def _parse_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)


_parse_dt = parse_dt
