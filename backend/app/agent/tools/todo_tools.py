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
    description="Get todos from the backlog, optionally filtered.",
    input_schema={
        "type": "object",
        "properties": {
            "filters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["backlog", "active", "completed", "cancelled"]},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                    "deadline_before": {"type": "string", "description": "ISO datetime."},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "has_scheduled_tasks": {"type": "boolean"},
                },
            },
        },
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_todos,
    category="todo",
))

register_tool(ToolDefinition(
    name="create_todo",
    description="Create a new todo in the backlog.",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
            "deadline": {"type": "string", "description": "ISO datetime."},
            "target_date": {"type": "string", "description": "ISO datetime, soft target."},
            "preferred_window": {"type": "string", "enum": ["morning", "afternoon", "evening"]},
            "estimated_duration_minutes": {"type": "integer"},
            "energy_level": {"type": "string", "enum": ["low", "medium", "high"]},
            "location": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "parent_todo_id": {"type": "string", "description": "UUID of parent todo for sub-todos."},
        },
        "required": ["title"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_create_todo,
    category="todo",
))

register_tool(ToolDefinition(
    name="update_todo",
    description="Update fields on an existing todo.",
    input_schema={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string"},
            "fields": {
                "type": "object",
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
    category="todo",
))

register_tool(ToolDefinition(
    name="complete_todo",
    description="Mark a todo as completed; remaining tasks are cancelled.",
    input_schema={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string"},
        },
        "required": ["todo_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_complete_todo,
    category="todo",
))

register_tool(ToolDefinition(
    name="get_todo_detail",
    description="Get full details of a todo including all its tasks.",
    input_schema={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string"},
        },
        "required": ["todo_id"],
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_todo_detail,
    category="todo",
))

register_tool(ToolDefinition(
    name="create_todo_with_task",
    description="Create a todo and a single scheduled task atomically.",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
            "scheduled_start": {"type": "string", "description": "ISO datetime."},
            "scheduled_end": {"type": "string", "description": "ISO datetime."},
            "estimated_duration_minutes": {"type": "integer"},
        },
        "required": ["title", "scheduled_start", "scheduled_end"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_create_todo_with_task,
    category="todo",
))
