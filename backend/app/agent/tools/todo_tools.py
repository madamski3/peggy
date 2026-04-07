"""Todo tool definitions for the agent.

Todos are the unified productivity object — they can be backlog items,
scheduled calendar blocks, or parent items with children for decomposition.

Registered tools:
  - get_todos           (READ_ONLY)  -- query todos by status/priority/deadline/tags/schedule
  - create_todo         (LOW_STAKES) -- add a new todo (backlog or scheduled)
  - update_todo         (LOW_STAKES) -- partial update of todo fields
  - complete_todo       (LOW_STAKES) -- mark done, cascades up/down
  - cancel_todo         (LOW_STAKES) -- cancel, deletes calendar event
  - get_todo_detail     (READ_ONLY)  -- full todo with all its children
  - create_sub_todos    (HIGH_STAKES)-- create multiple children under a parent
  - reschedule_todo     (LOW_STAKES) -- move to new time, sync calendar
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.services import todos as todo_service


# ── Handlers ──────────────────────────────────────────────────────


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
    result = await todo_service.complete_todo(
        db,
        kwargs["todo_id"],
        actual_duration_minutes=kwargs.get("actual_duration_minutes"),
        completion_notes=kwargs.get("completion_notes"),
    )
    if result is None:
        return {"error": "Todo not found"}
    return result


async def handle_cancel_todo(db: AsyncSession, **kwargs: Any) -> dict:
    result = await todo_service.cancel_todo(db, kwargs["todo_id"])
    if result is None:
        return {"error": "Todo not found"}
    return result


async def handle_get_todo_detail(db: AsyncSession, **kwargs: Any) -> dict:
    result = await todo_service.get_todo_detail(db, kwargs["todo_id"])
    if result is None:
        return {"error": "Todo not found"}
    return result


async def handle_create_sub_todos(db: AsyncSession, **kwargs: Any) -> dict:
    results = await todo_service.create_child_todos_batch(
        db, kwargs["parent_todo_id"], kwargs["children"]
    )
    return {"children": results, "count": len(results)}


async def handle_reschedule_todo(db: AsyncSession, **kwargs: Any) -> dict:
    result = await todo_service.reschedule_todo(
        db,
        kwargs["todo_id"],
        new_scheduled_start=kwargs.get("new_scheduled_start"),
        new_scheduled_end=kwargs.get("new_scheduled_end"),
    )
    if result is None:
        return {"error": "Todo not found"}
    return result


# ── Tool Definitions ─────────────────────────────────────────────

register_tool(ToolDefinition(
    name="get_todos",
    description="Get todos, optionally filtered by status, priority, schedule, or date.",
    embedding_text=(
        "todo: get_todos — list, view, check, show todos, backlog items, projects, "
        "scheduled items, agenda. What's on my todo list? Show my backlog. "
        "What do I need to do? What's on my agenda today? What tasks are scheduled? "
        "Any high-priority items? What are my active projects?"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "filters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["backlog", "scheduled", "completed", "cancelled"]},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                    "deadline_before": {"type": "string", "description": "ISO datetime."},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "scheduled_date": {"type": "string", "description": "ISO date. Returns todos scheduled on this day."},
                    "date_range": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string"},
                            "end": {"type": "string"},
                        },
                        "required": ["start", "end"],
                    },
                    "parent_todo_id": {"type": "string", "description": "UUID. Returns children of this todo."},
                    "is_scheduled": {"type": "boolean", "description": "True = has scheduled times, False = backlog only."},
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
    description=(
        "Create a new todo. If scheduled_start and scheduled_end are provided, "
        "it becomes 'scheduled' with a calendar event created automatically. "
        "Otherwise it starts as 'backlog'."
    ),
    embedding_text=(
        "todo: create_todo — create, add, new todo, backlog item, project, goal, "
        "schedule, calendar. Add this to my todo list. I need to remember to do X. "
        "Create a todo for grocery shopping. Schedule Y for 2pm tomorrow. "
        "Put Z on my calendar."
    ),
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
            "scheduled_start": {"type": "string", "description": "ISO datetime. If provided with scheduled_end, creates a scheduled todo with calendar event."},
            "scheduled_end": {"type": "string", "description": "ISO datetime."},
        },
        "required": ["title"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_create_todo,
    category="todo",
))

register_tool(ToolDefinition(
    name="update_todo",
    description="Update fields on an existing todo. Changing scheduled times syncs the calendar event.",
    embedding_text=(
        "todo: update_todo — edit, change, modify, update a todo's title, description, "
        "priority, deadline, tags, status, schedule. Change the priority to urgent. "
        "Update the deadline. Add a tag. Move this to 4pm."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string"},
            "fields": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {"type": "string", "enum": ["backlog", "scheduled", "completed", "cancelled"]},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                    "deadline": {"type": "string"},
                    "target_date": {"type": "string"},
                    "preferred_window": {"type": "string"},
                    "estimated_duration_minutes": {"type": "integer"},
                    "energy_level": {"type": "string", "enum": ["low", "medium", "high"]},
                    "location": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                    "scheduled_start": {"type": "string"},
                    "scheduled_end": {"type": "string"},
                    "actual_duration_minutes": {"type": "integer"},
                    "completion_notes": {"type": "string"},
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
    description=(
        "Mark a todo as completed. Cancels any unfinished children. "
        "If all siblings of a parent are done, the parent auto-completes too."
    ),
    embedding_text=(
        "todo: complete_todo — complete, finish, done, mark todo as completed. "
        "I finished that project. Mark grocery shopping as done. That task is done."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string"},
            "actual_duration_minutes": {"type": "integer"},
            "completion_notes": {"type": "string"},
        },
        "required": ["todo_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_complete_todo,
    category="todo",
))

register_tool(ToolDefinition(
    name="cancel_todo",
    description="Cancel a todo. Deletes its calendar event if one exists.",
    embedding_text=(
        "todo: cancel_todo — cancel, remove, delete a todo or scheduled item. "
        "Cancel that. I don't need to do that anymore. Remove it from my calendar."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string"},
        },
        "required": ["todo_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_cancel_todo,
    category="todo",
))

register_tool(ToolDefinition(
    name="get_todo_detail",
    description="Get full details of a todo including all its children.",
    embedding_text=(
        "todo: get_todo_detail — view todo details, children, sub-items for a "
        "specific todo. Show me the details of that project. What sub-items are under this todo?"
    ),
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
    name="create_sub_todos",
    description="Create multiple child todos under a parent (requires confirmation). Calendar events are created automatically for children with scheduled times.",
    embedding_text=(
        "todo: create_sub_todos — create multiple sub-items at once, batch schedule, "
        "plan several work blocks for a project. Break this todo into steps across the week."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "parent_todo_id": {"type": "string"},
            "children": {
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
        "required": ["parent_todo_id", "children"],
    },
    tier=ActionTier.HIGH_STAKES,
    handler=handle_create_sub_todos,
    category="todo",
))

register_tool(ToolDefinition(
    name="reschedule_todo",
    description="Reschedule a todo to a new time. Increments deferred count and syncs calendar.",
    embedding_text=(
        "todo: reschedule_todo — defer, postpone, push back, reschedule a todo to later. "
        "I'll do that tomorrow instead. Push this to next week. Move it to 4pm."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "todo_id": {"type": "string"},
            "new_scheduled_start": {"type": "string", "description": "ISO datetime."},
            "new_scheduled_end": {"type": "string", "description": "ISO datetime."},
        },
        "required": ["todo_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_reschedule_todo,
    category="todo",
))
