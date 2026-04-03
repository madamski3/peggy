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
    description="Get tasks, optionally filtered by status, date, or todo.",
    input_schema={
        "type": "object",
        "properties": {
            "filters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["scheduled", "in_progress", "completed", "cancelled"]},
                    "todo_id": {"type": "string"},
                    "scheduled_date": {"type": "string", "description": "ISO date."},
                    "date_range": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string"},
                            "end": {"type": "string"},
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
    description="Create a scheduled task linked to a todo.",
    input_schema={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "scheduled_start": {"type": "string", "description": "ISO datetime."},
            "scheduled_end": {"type": "string", "description": "ISO datetime."},
            "estimated_duration_minutes": {"type": "integer"},
            "position": {"type": "integer"},
        },
        "required": ["todo_id", "title"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_create_task,
    category="task",
))

register_tool(ToolDefinition(
    name="create_tasks_batch",
    description="Create multiple tasks for a todo at once (requires confirmation).",
    input_schema={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string"},
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "scheduled_start": {"type": "string"},
                        "scheduled_end": {"type": "string"},
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
    description="Update fields on an existing task.",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "fields": {
                "type": "object",
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
    description="Mark a task as completed; auto-completes parent todo if all tasks done.",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "actual_duration_minutes": {"type": "integer"},
            "completion_notes": {"type": "string"},
        },
        "required": ["task_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_complete_task,
    category="task",
))

register_tool(ToolDefinition(
    name="defer_task",
    description="Reschedule a task to a new time and increment deferred count.",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "new_scheduled_start": {"type": "string", "description": "ISO datetime."},
            "new_scheduled_end": {"type": "string", "description": "ISO datetime."},
        },
        "required": ["task_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_defer_task,
    category="task",
))

register_tool(ToolDefinition(
    name="cancel_task",
    description="Cancel a task (soft delete).",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
        },
        "required": ["task_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_cancel_task,
    category="task",
))
