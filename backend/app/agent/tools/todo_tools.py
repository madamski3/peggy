"""Todo tool definitions for the agent.

Todos are the unified productivity object — they can be backlog items,
scheduled calendar blocks, or parent items with children for decomposition.

Registered tools:
  - get_todos           (READ_ONLY)  -- query todos by status/priority/deadline/tags/schedule
  - create_todo         (LOW_STAKES) -- add a new todo (backlog or scheduled)
  - update_todo         (LOW_STAKES) -- update fields, complete, cancel, or reschedule
  - get_todo_detail     (READ_ONLY)  -- full todo with all its children
  - create_sub_todos    (HIGH_STAKES)-- create multiple children under a parent
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

    # Route "backlog" status to the dedicated send_to_backlog service,
    # which clears schedule, deletes calendar event, and increments deferred_count.
    if fields.get("status") == "backlog":
        result = await todo_service.send_to_backlog(
            db, todo_id, notes=fields.get("completion_notes"),
        )
        if result is None:
            return {"error": "Todo not found"}
        return result

    result = await todo_service.update_todo(db, todo_id, fields)
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
        "Put Z on my calendar. Block off Friday afternoon. "
        "Schedule a meeting with John at 3pm. Book a calendar event."
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
            "scheduled_end": {"type": "string", "description": "ISO datetime. Required if scheduled_start is provided."},
        },
        "required": ["title"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_create_todo,
    category="todo",
))

register_tool(ToolDefinition(
    name="update_todo",
    description=(
        "Update fields on an existing todo. Handles all status transitions: "
        "setting status to 'completed' cascades completion to children, deletes "
        "calendar events, and auto-completes parent if all siblings are done. "
        "Setting status to 'cancelled' deletes the calendar event. "
        "Setting status to 'backlog' clears the schedule, deletes the calendar "
        "event, and moves the todo back to the backlog. "
        "Changing scheduled times on an already-scheduled todo tracks it as a reschedule. "
        "Calendar events sync automatically with schedule changes."
    ),
    embedding_text=(
        "todo: update_todo — edit, change, modify, update a todo's title, description, "
        "priority, deadline, tags, status, schedule. Change the priority to urgent. "
        "Update the deadline. Add a tag. Move this to 4pm. "
        "Complete, finish, done, mark todo as completed. I finished that project. "
        "Mark grocery shopping as done. That task is done. "
        "Cancel, remove, I don't need to do that anymore. "
        "Reschedule, defer, postpone, push back to later. "
        "I'll do that tomorrow instead. Push this to next week. "
        "Move to backlog, unschedule, push this back, defer this, "
        "remove from schedule, take this off the calendar."
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

