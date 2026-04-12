"""Todo service layer -- CRUD operations for the Todo model.

Todos are the unified productivity object. They can be:
  - Backlog items (no scheduled times)
  - Scheduled items (with scheduled_start/end and a calendar event)
  - Parent items (with child todos for decomposition)

Status lifecycle:
  backlog -> scheduled (when times are set or a child is scheduled)
         -> completed / cancelled

Key behaviors:
  - create_todo() starts in "backlog" unless scheduled times are provided
  - complete_todo() cascades down (cancels unfinished children) and up
    (auto-completes parent if all siblings are done)
  - _sync_calendar() ensures calendar events stay in sync with scheduling
  - _maybe_update_parent_status() propagates status changes up the hierarchy
  - create_child_todos_batch() creates multiple children under a parent
  - reschedule_todo() updates times + syncs calendar + increments deferred_count

Called by the agent tools (todo_tools.py) and REST routers.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tables import ScheduledNotification, Todo
from app.services.serialization import model_to_dict
from app.globals import get_cached_timezone
from app.services.timezone import parse_dt

logger = logging.getLogger(__name__)


async def get_todos(db: AsyncSession, filters: dict[str, Any] | None = None) -> list[dict]:
    """Query todos with optional filters.

    Supported filters:
        - status: str
        - priority: str
        - deadline_before: str (ISO datetime)
        - tags: list[str] (match any)
        - scheduled_date: str (ISO date — matches todos scheduled on that day)
        - date_range: dict with 'start' and 'end' (ISO datetimes)
        - parent_todo_id: str (UUID — children of a specific parent)
        - is_scheduled: bool (has scheduled_start or not)
    """
    filters = filters or {}
    query = select(Todo).options(selectinload(Todo.children))

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
    if "scheduled_date" in filters:
        user_tz = get_cached_timezone()
        day = parse_dt(filters["scheduled_date"]).date()
        day_start = datetime(day.year, day.month, day.day, tzinfo=user_tz)
        day_end = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=user_tz)
        query = query.where(
            and_(
                Todo.scheduled_start >= day_start,
                Todo.scheduled_start <= day_end,
            )
        )
    if "date_range" in filters:
        dr = filters["date_range"]
        query = query.where(Todo.scheduled_start >= parse_dt(dr["start"]))
        query = query.where(Todo.scheduled_start <= parse_dt(dr["end"]))
    if "parent_todo_id" in filters:
        query = query.where(Todo.parent_todo_id == _parse_uuid(filters["parent_todo_id"]))
    if "is_scheduled" in filters:
        if filters["is_scheduled"]:
            query = query.where(Todo.scheduled_start.isnot(None))
        else:
            query = query.where(Todo.scheduled_start.is_(None))

    # Order by scheduled_start when date filters are active, otherwise by created_at
    if any(k in filters for k in ("scheduled_date", "date_range")):
        query = query.order_by(Todo.scheduled_start.asc().nullslast(), Todo.position.asc().nullslast())
    else:
        query = query.order_by(Todo.created_at.desc())

    result = await db.execute(query)
    todos = list(result.scalars().unique().all())
    return [_todo_summary(t) for t in todos]


async def create_todo(db: AsyncSession, **kwargs: Any) -> dict:
    """Create a new todo. Starts as backlog unless scheduled times are provided."""
    has_schedule = kwargs.get("scheduled_start") and kwargs.get("scheduled_end")

    todo = Todo(
        title=kwargs["title"],
        description=kwargs.get("description"),
        status="scheduled" if has_schedule else "backlog",
        priority=kwargs.get("priority", "medium"),
        deadline=_parse_dt(kwargs.get("deadline")),
        target_date=_parse_dt(kwargs.get("target_date")),
        preferred_window=kwargs.get("preferred_window"),
        estimated_duration_minutes=kwargs.get("estimated_duration_minutes"),
        energy_level=kwargs.get("energy_level"),
        location=kwargs.get("location"),
        tags=kwargs.get("tags"),
        parent_todo_id=_parse_uuid(kwargs.get("parent_todo_id")),
        scheduled_start=_parse_dt(kwargs.get("scheduled_start")),
        scheduled_end=_parse_dt(kwargs.get("scheduled_end")),
        position=kwargs.get("position"),
        created_by="assistant",
    )
    db.add(todo)
    await db.flush()

    if has_schedule:
        await _sync_calendar(db, todo)

    if todo.parent_todo_id:
        await _maybe_update_parent_status(db, todo)

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
        "scheduled_start", "scheduled_end", "actual_duration_minutes",
        "completion_notes", "position", "deferred_count",
    }

    schedule_changed = False
    for key, value in fields.items():
        if key in updatable:
            if key in ("deadline", "target_date", "scheduled_start", "scheduled_end"):
                value = _parse_dt(value)
            if key in ("scheduled_start", "scheduled_end"):
                schedule_changed = True
            setattr(todo, key, value)

    todo.updated_at = datetime.now(timezone.utc)
    await db.flush()

    if schedule_changed:
        await _sync_calendar(db, todo)

    await _maybe_update_parent_status(db, todo)

    return model_to_dict(todo)


async def complete_todo(
    db: AsyncSession,
    todo_id: str | uuid.UUID,
    actual_duration_minutes: int | None = None,
    completion_notes: str | None = None,
) -> dict | None:
    """Mark a todo as completed. Cascades down and up."""
    result = await db.execute(
        select(Todo).options(selectinload(Todo.children)).where(Todo.id == _parse_uuid(todo_id))
    )
    todo = result.scalar_one_or_none()
    if todo is None:
        return None

    todo.status = "completed"
    todo.completed_at = datetime.now(timezone.utc)
    todo.updated_at = datetime.now(timezone.utc)

    if actual_duration_minutes is not None:
        todo.actual_duration_minutes = actual_duration_minutes
    if completion_notes is not None:
        todo.completion_notes = completion_notes

    # Cascade DOWN: cancel unfinished children
    for child in todo.children:
        if child.status not in ("completed", "cancelled"):
            child.status = "cancelled"
            child.updated_at = datetime.now(timezone.utc)
            if child.calendar_event_id:
                await _delete_calendar_event(db, child)

    # Delete calendar event for this todo if it has one
    if todo.calendar_event_id:
        await _delete_calendar_event(db, todo)

    await db.flush()

    # Cascade UP: auto-complete parent if all siblings are done
    await _maybe_update_parent_status(db, todo)

    return model_to_dict(todo)


async def cancel_todo(db: AsyncSession, todo_id: str | uuid.UUID) -> dict | None:
    """Cancel a todo. Deletes calendar event if exists, checks parent status."""
    todo = await _get_todo(db, todo_id)
    if todo is None:
        return None

    todo.status = "cancelled"
    todo.updated_at = datetime.now(timezone.utc)

    if todo.calendar_event_id:
        await _delete_calendar_event(db, todo)

    await db.flush()
    await _maybe_update_parent_status(db, todo)

    return model_to_dict(todo)


async def reschedule_todo(
    db: AsyncSession,
    todo_id: str | uuid.UUID,
    new_scheduled_start: str | datetime | None = None,
    new_scheduled_end: str | datetime | None = None,
) -> dict | None:
    """Reschedule a todo and increment its deferred count."""
    todo = await _get_todo(db, todo_id)
    if todo is None:
        return None

    todo.deferred_count += 1
    if new_scheduled_start is not None:
        todo.scheduled_start = _parse_dt(new_scheduled_start)
    if new_scheduled_end is not None:
        todo.scheduled_end = _parse_dt(new_scheduled_end)
    todo.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await _sync_calendar(db, todo)

    return model_to_dict(todo)


async def delete_todo(db: AsyncSession, todo_id: str | uuid.UUID) -> bool:
    """Hard-delete a todo, its children, and their notifications."""
    result = await db.execute(
        select(Todo).options(selectinload(Todo.children)).where(Todo.id == _parse_uuid(todo_id))
    )
    todo = result.scalar_one_or_none()
    if todo is None:
        return False

    # Recursively delete children
    for child in todo.children:
        await delete_todo(db, child.id)

    # Delete linked notifications
    notifs = await db.execute(
        select(ScheduledNotification).where(ScheduledNotification.todo_id == todo.id)
    )
    for notif in notifs.scalars().all():
        await db.delete(notif)

    # Detach other child todos (safety — should be deleted above, but handle
    # any that weren't eagerly loaded)
    remaining_children = await db.execute(
        select(Todo).where(Todo.parent_todo_id == todo.id)
    )
    for child in remaining_children.scalars().all():
        child.parent_todo_id = None

    await db.delete(todo)
    await db.flush()
    return True


async def get_todo_detail(db: AsyncSession, todo_id: str | uuid.UUID) -> dict | None:
    """Return a todo with all its children eagerly loaded."""
    result = await db.execute(
        select(Todo).options(selectinload(Todo.children)).where(Todo.id == _parse_uuid(todo_id))
    )
    todo = result.scalar_one_or_none()
    if todo is None:
        return None

    todo_dict = model_to_dict(todo)
    todo_dict["children"] = [model_to_dict(c) for c in todo.children]
    return todo_dict


async def create_child_todos_batch(
    db: AsyncSession,
    parent_todo_id: str | uuid.UUID,
    children_data: list[dict[str, Any]],
) -> list[dict]:
    """Create multiple child todos under a parent in one transaction.

    Sets the parent todo status to 'scheduled'.
    """
    pid = _parse_uuid(parent_todo_id)

    # Update parent status
    result = await db.execute(select(Todo).where(Todo.id == pid))
    parent = result.scalar_one_or_none()
    if parent is None:
        raise ValueError(f"Todo {parent_todo_id} not found")
    if parent.status == "backlog":
        parent.status = "scheduled"
        parent.updated_at = datetime.now(timezone.utc)

    created = []
    for i, cd in enumerate(children_data):
        has_schedule = cd.get("scheduled_start") and cd.get("scheduled_end")
        child = Todo(
            title=cd["title"],
            description=cd.get("description"),
            parent_todo_id=pid,
            status="scheduled" if has_schedule else "backlog",
            priority=cd.get("priority", "medium"),
            scheduled_start=_parse_dt(cd.get("scheduled_start")),
            scheduled_end=_parse_dt(cd.get("scheduled_end")),
            estimated_duration_minutes=cd.get("estimated_duration_minutes"),
            position=cd.get("position", i),
            created_by="assistant",
        )
        db.add(child)
        await db.flush()

        if has_schedule:
            await _sync_calendar(db, child)

        created.append(child)

    return [model_to_dict(c) for c in created]


# ── Internal helpers ──────────────────────────────────────────────


def _todo_summary(todo: Todo) -> dict:
    """Build a summary dict for a todo, including child count."""
    d = model_to_dict(todo)
    d["children_count"] = len(todo.children) if todo.children else 0
    d["completed_children_count"] = sum(
        1 for c in (todo.children or []) if c.status == "completed"
    )
    return d


async def _get_todo(db: AsyncSession, todo_id: str | uuid.UUID) -> Todo | None:
    result = await db.execute(select(Todo).where(Todo.id == _parse_uuid(todo_id)))
    return result.scalar_one_or_none()


async def _sync_calendar(db: AsyncSession, todo: Todo) -> None:
    """Ensure the todo's calendar event is in sync with its scheduled times.

    - Times present + no event → create event
    - Times present + event exists → update event
    - Times cleared + event exists → delete event
    """
    from app.services.google_calendar import create_event, update_event

    has_times = todo.scheduled_start and todo.scheduled_end

    if has_times and not todo.calendar_event_id:
        # Create new calendar event
        try:
            result = await create_event(
                db,
                summary=todo.title,
                start=todo.scheduled_start.isoformat(),
                end=todo.scheduled_end.isoformat(),
                description=todo.description or "",
            )
            if "error" not in result:
                todo.calendar_event_id = result.get("id")
                await db.flush()
        except Exception:
            logger.warning("Failed to create calendar event for todo %s", todo.id)

    elif has_times and todo.calendar_event_id:
        # Update existing calendar event
        try:
            await update_event(
                db,
                event_id=todo.calendar_event_id,
                summary=todo.title,
                start=todo.scheduled_start.isoformat(),
                end=todo.scheduled_end.isoformat(),
            )
        except Exception:
            logger.warning("Failed to update calendar event for todo %s", todo.id)

    elif not has_times and todo.calendar_event_id:
        await _delete_calendar_event(db, todo)


async def _delete_calendar_event(db: AsyncSession, todo: Todo) -> None:
    """Delete a todo's calendar event and clear the event_id."""
    from app.services.google_calendar import delete_event

    try:
        await delete_event(db, todo.calendar_event_id)
    except Exception:
        logger.warning("Failed to delete calendar event for todo %s", todo.id)
    todo.calendar_event_id = None
    await db.flush()


async def _maybe_update_parent_status(db: AsyncSession, todo: Todo) -> None:
    """Propagate status changes up the parent chain.

    Rules:
    - If a child is scheduled and parent is backlog → parent becomes scheduled
    - If all children are completed/cancelled → parent auto-completes
    """
    current = todo
    while current.parent_todo_id:
        parent_result = await db.execute(
            select(Todo).options(selectinload(Todo.children))
            .where(Todo.id == current.parent_todo_id)
        )
        parent = parent_result.scalar_one_or_none()
        if parent is None:
            break

        # Don't touch already-completed or cancelled parents
        if parent.status in ("completed", "cancelled"):
            break

        siblings = parent.children
        all_done = all(s.status in ("completed", "cancelled") for s in siblings)
        any_scheduled = any(s.status == "scheduled" for s in siblings)

        if all_done and siblings:
            parent.status = "completed"
            parent.completed_at = datetime.now(timezone.utc)
            parent.updated_at = datetime.now(timezone.utc)
            if parent.calendar_event_id:
                await _delete_calendar_event(db, parent)
        elif any_scheduled and parent.status == "backlog":
            parent.status = "scheduled"
            parent.updated_at = datetime.now(timezone.utc)
        else:
            break  # No change needed, stop walking up

        await db.flush()
        current = parent


def _parse_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)


_parse_dt = parse_dt
