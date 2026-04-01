"""Task tool definitions for the agent.

Tasks are scheduled work blocks linked to a parent todo. The agent uses
these tools to schedule, reschedule, complete, and cancel tasks.

Registered tools:
  - get_tasks           (READ_ONLY)   -- query tasks by status/date/todo
  - create_task         (LOW_STAKES)  -- create one task for a todo
  - create_tasks_batch  (HIGH_STAKES) -- create multiple tasks at once (needs confirmation)
  - update_task         (LOW_STAKES)  -- partial update (reschedule, rename, etc.)
  - complete_task       (LOW_STAKES)  -- mark done; auto-completes parent todo if all siblings done
  - defer_task          (LOW_STAKES)  -- reschedule + increment deferred count
  - cancel_task         (LOW_STAKES)  -- soft-cancel (marks as cancelled, doesn't delete)
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.services import tasks as task_service


# ── Handlers ──────────────────────────────────────────────────────


async def handle_get_tasks(db: AsyncSession, **kwargs: Any) -> dict:
    filters = kwargs.get("filters", {})
    results = await task_service.get_tasks(db, filters)
    return {"tasks": results, "count": len(results)}


async def handle_create_task(db: AsyncSession, **kwargs: Any) -> dict:
    return await task_service.create_task(db, **kwargs)


async def handle_create_tasks_batch(db: AsyncSession, **kwargs: Any) -> dict:
    results = await task_service.create_tasks_batch(
        db, kwargs["todo_id"], kwargs["tasks"]
    )
    return {"tasks": results, "count": len(results)}


async def handle_update_task(db: AsyncSession, **kwargs: Any) -> dict:
    task_id = kwargs.pop("task_id")
    fields = kwargs.get("fields", kwargs)
    result = await task_service.update_task(db, task_id, fields)
    if result is None:
        return {"error": "Task not found"}
    return result


async def handle_complete_task(db: AsyncSession, **kwargs: Any) -> dict:
    result = await task_service.complete_task(
        db,
        kwargs["task_id"],
        actual_duration_minutes=kwargs.get("actual_duration_minutes"),
        completion_notes=kwargs.get("completion_notes"),
    )
    if result is None:
        return {"error": "Task not found"}
    return result


async def handle_defer_task(db: AsyncSession, **kwargs: Any) -> dict:
    result = await task_service.defer_task(
        db,
        kwargs["task_id"],
        new_scheduled_start=kwargs.get("new_scheduled_start"),
        new_scheduled_end=kwargs.get("new_scheduled_end"),
    )
    if result is None:
        return {"error": "Task not found"}
    return result


async def handle_cancel_task(db: AsyncSession, **kwargs: Any) -> dict:
    result = await task_service.cancel_task(db, kwargs["task_id"])
    if result is None:
        return {"error": "Task not found"}
    return result


# ── Tool Definitions ─────────────────────────────────────────────

register_tool(ToolDefinition(
    name="get_tasks",
    description="Get a filtered list of tasks. Use to see what's scheduled for a given day or for a specific todo.",
    input_schema={
        "type": "object",
        "properties": {
            "filters": {
                "type": "object",
                "description": "Optional filters.",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status (scheduled, in_progress, completed, cancelled)."},
                    "todo_id": {"type": "string", "description": "Filter by parent todo UUID."},
                    "scheduled_date": {"type": "string", "description": "ISO date — return tasks scheduled on this day."},
                    "date_range": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string", "description": "ISO datetime start."},
                            "end": {"type": "string", "description": "ISO datetime end."},
                        },
                        "required": ["start", "end"],
                    },
                },
            },
        },
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_tasks,
    category="task",
))

register_tool(ToolDefinition(
    name="create_task",
    description="Create a single scheduled task linked to a todo.",
    input_schema={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string", "description": "UUID of the parent todo."},
            "title": {"type": "string", "description": "Task title."},
            "description": {"type": "string", "description": "Additional details."},
            "scheduled_start": {"type": "string", "description": "ISO datetime for when to start."},
            "scheduled_end": {"type": "string", "description": "ISO datetime for when it ends."},
            "estimated_duration_minutes": {"type": "integer"},
            "position": {"type": "integer", "description": "Order position within the todo's tasks."},
        },
        "required": ["todo_id", "title"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_create_task,
    category="task",
))

register_tool(ToolDefinition(
    name="create_tasks_batch",
    description="Create multiple tasks for a todo at once. Use when decomposing a todo into scheduled work blocks. This is a high-stakes action — always present the plan to the user and get confirmation before calling this.",
    input_schema={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string", "description": "UUID of the parent todo."},
            "tasks": {
                "type": "array",
                "description": "List of tasks to create.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "scheduled_start": {"type": "string", "description": "ISO datetime."},
                        "scheduled_end": {"type": "string", "description": "ISO datetime."},
                        "estimated_duration_minutes": {"type": "integer"},
                    },
                    "required": ["title"],
                },
            },
        },
        "required": ["todo_id", "tasks"],
    },
    tier=ActionTier.HIGH_STAKES,
    handler=handle_create_tasks_batch,
    category="task",
))

register_tool(ToolDefinition(
    name="update_task",
    description="Update fields on an existing task (reschedule, change title, etc.).",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "UUID of the task to update."},
            "fields": {
                "type": "object",
                "description": "Fields to update.",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "scheduled_start": {"type": "string"},
                    "scheduled_end": {"type": "string"},
                    "estimated_duration_minutes": {"type": "integer"},
                    "status": {"type": "string"},
                    "position": {"type": "integer"},
                },
            },
        },
        "required": ["task_id", "fields"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_update_task,
    category="task",
))

register_tool(ToolDefinition(
    name="complete_task",
    description="Mark a task as completed. If all tasks for the parent todo are done, the todo is auto-completed too.",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "UUID of the task to complete."},
            "actual_duration_minutes": {"type": "integer", "description": "How long it actually took."},
            "completion_notes": {"type": "string", "description": "Notes about how it went."},
        },
        "required": ["task_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_complete_task,
    category="task",
))

register_tool(ToolDefinition(
    name="defer_task",
    description="Reschedule a task to a new time. Increments the deferred count for tracking.",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "UUID of the task to defer."},
            "new_scheduled_start": {"type": "string", "description": "New ISO datetime start."},
            "new_scheduled_end": {"type": "string", "description": "New ISO datetime end."},
        },
        "required": ["task_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_defer_task,
    category="task",
))

register_tool(ToolDefinition(
    name="cancel_task",
    description="Cancel a task (soft delete — marks as cancelled, does not remove).",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "UUID of the task to cancel."},
        },
        "required": ["task_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_cancel_task,
    category="task",
))
