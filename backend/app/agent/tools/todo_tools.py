"""Todo tool definitions for the agent.

Todos are backlog items that may have zero or more scheduled tasks. The
agent uses these tools to manage the user's todo backlog.

Registered tools:
  - get_todos            (READ_ONLY)  -- query todos by status/priority/deadline/tags
  - create_todo          (LOW_STAKES) -- add a new backlog item
  - update_todo          (LOW_STAKES) -- partial update of todo fields
  - complete_todo        (LOW_STAKES) -- mark done, cancels any remaining tasks
  - get_todo_detail      (READ_ONLY)  -- full todo with all its tasks
  - create_todo_with_task (LOW_STAKES) -- shortcut: create a todo + single task atomically
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.services import todos as todo_service


# ── Handlers ──────────────────────────────────────────────────────
# Thin wrappers that accept (db, **kwargs) and return JSON-serializable dicts.


async def handle_get_todos(db: AsyncSession, **kwargs: Any) -> dict:
    filters = kwargs.get("filters", {})
    results = await todo_service.get_todos(db, filters)
    return {"todos": results, "count": len(results)}


async def handle_create_todo(db: AsyncSession, **kwargs: Any) -> dict:
    return await todo_service.create_todo(db, **kwargs)


async def handle_update_todo(db: AsyncSession, **kwargs: Any) -> dict:
    todo_id = kwargs.pop("todo_id")
    fields = kwargs.get("fields", kwargs)
    result = await todo_service.update_todo(db, todo_id, fields)
    if result is None:
        return {"error": "Todo not found"}
    return result


async def handle_complete_todo(db: AsyncSession, **kwargs: Any) -> dict:
    result = await todo_service.complete_todo(db, kwargs["todo_id"])
    if result is None:
        return {"error": "Todo not found"}
    return result


async def handle_get_todo_detail(db: AsyncSession, **kwargs: Any) -> dict:
    result = await todo_service.get_todo_detail(db, kwargs["todo_id"])
    if result is None:
        return {"error": "Todo not found"}
    return result


async def handle_create_todo_with_task(db: AsyncSession, **kwargs: Any) -> dict:
    return await todo_service.create_todo_with_task(db, **kwargs)


# ── Tool Definitions ─────────────────────────────────────────────

register_tool(ToolDefinition(
    name="get_todos",
    description="Get a filtered list of todos from the backlog. Use this to see what's on the user's plate.",
    input_schema={
        "type": "object",
        "properties": {
            "filters": {
                "type": "object",
                "description": "Optional filters to narrow results.",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status (backlog, active, completed, cancelled)."},
                    "priority": {"type": "string", "description": "Filter by priority (low, medium, high, urgent)."},
                    "deadline_before": {"type": "string", "description": "ISO datetime — return todos with deadline before this date."},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter by tags (match any)."},
                    "has_scheduled_tasks": {"type": "boolean", "description": "If true, only return todos that have scheduled tasks. If false, only unscheduled."},
                },
            },
        },
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_todos,
))

register_tool(ToolDefinition(
    name="create_todo",
    description="Create a new todo in the backlog. Use this when the user mentions something they need to do.",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short, actionable title for the todo."},
            "description": {"type": "string", "description": "Additional details or context."},
            "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"], "description": "Priority level. Default: medium."},
            "deadline": {"type": "string", "description": "ISO datetime for hard deadline, if any."},
            "target_date": {"type": "string", "description": "ISO datetime for soft target date."},
            "preferred_window": {"type": "string", "description": "Preferred time window (morning, afternoon, evening)."},
            "estimated_duration_minutes": {"type": "integer", "description": "Estimated time to complete in minutes."},
            "energy_level": {"type": "string", "enum": ["low", "medium", "high"], "description": "Energy level required."},
            "location": {"type": "string", "description": "Where this needs to be done (home, office, errands)."},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for categorization."},
            "parent_todo_id": {"type": "string", "description": "UUID of parent todo, if this is a sub-todo."},
        },
        "required": ["title"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_create_todo,
))

register_tool(ToolDefinition(
    name="update_todo",
    description="Update fields on an existing todo (title, priority, deadline, tags, etc.).",
    input_schema={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string", "description": "UUID of the todo to update."},
            "fields": {
                "type": "object",
                "description": "Fields to update.",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                    "deadline": {"type": "string"},
                    "target_date": {"type": "string"},
                    "preferred_window": {"type": "string"},
                    "estimated_duration_minutes": {"type": "integer"},
                    "energy_level": {"type": "string", "enum": ["low", "medium", "high"]},
                    "location": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                },
            },
        },
        "required": ["todo_id", "fields"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_update_todo,
))

register_tool(ToolDefinition(
    name="complete_todo",
    description="Mark a todo as completed. Any remaining unfinished tasks will be cancelled.",
    input_schema={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string", "description": "UUID of the todo to complete."},
        },
        "required": ["todo_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_complete_todo,
))

register_tool(ToolDefinition(
    name="get_todo_detail",
    description="Get full details of a specific todo, including all its tasks.",
    input_schema={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string", "description": "UUID of the todo."},
        },
        "required": ["todo_id"],
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_todo_detail,
))

register_tool(ToolDefinition(
    name="create_todo_with_task",
    description="Shortcut to create a todo and a single scheduled task simultaneously. Use for reminders or simple one-off items that need a specific time.",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Title for both the todo and the task."},
            "description": {"type": "string", "description": "Additional details."},
            "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
            "scheduled_start": {"type": "string", "description": "ISO datetime for when to start."},
            "scheduled_end": {"type": "string", "description": "ISO datetime for when it ends."},
            "estimated_duration_minutes": {"type": "integer"},
        },
        "required": ["title", "scheduled_start", "scheduled_end"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_create_todo_with_task,
))
