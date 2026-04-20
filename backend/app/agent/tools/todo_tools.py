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

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, tool
from app.services import todos as todo_service


Status = Literal["backlog", "scheduled", "completed", "cancelled"]
Priority = Literal["low", "medium", "high", "urgent"]
Window = Literal["morning", "afternoon", "evening"]
EnergyLevel = Literal["low", "medium", "high"]


class DateRange(BaseModel):
    start: str
    end: str


class TodoFilters(BaseModel):
    status: Status | None = None
    priority: Priority | None = None
    deadline_before: str | None = Field(None, description="ISO datetime.")
    tags: list[str] | None = None
    scheduled_date: str | None = Field(
        None, description="ISO date. Returns todos scheduled on this day."
    )
    date_range: DateRange | None = None
    parent_todo_id: str | None = Field(
        None, description="UUID. Returns children of this todo."
    )
    is_scheduled: bool | None = Field(
        None, description="True = has scheduled times, False = backlog only."
    )


class GetTodosInput(BaseModel):
    filters: TodoFilters | None = None


class CreateTodoInput(BaseModel):
    title: str
    description: str | None = None
    priority: Priority | None = None
    deadline: str | None = Field(None, description="ISO datetime.")
    target_date: str | None = Field(None, description="ISO datetime, soft target.")
    preferred_window: Window | None = None
    estimated_duration_minutes: int | None = None
    energy_level: EnergyLevel | None = None
    location: str | None = None
    tags: list[str] | None = None
    parent_todo_id: str | None = Field(
        None, description="UUID of parent todo for sub-todos."
    )
    scheduled_start: str | None = Field(
        None,
        description=(
            "ISO datetime. If provided with scheduled_end, creates a "
            "scheduled todo with calendar event."
        ),
    )
    scheduled_end: str | None = Field(
        None, description="ISO datetime. Required if scheduled_start is provided."
    )


class UpdateTodoFields(BaseModel):
    title: str | None = None
    description: str | None = None
    status: Status | None = None
    priority: Priority | None = None
    deadline: str | None = None
    target_date: str | None = None
    preferred_window: str | None = None
    estimated_duration_minutes: int | None = None
    energy_level: EnergyLevel | None = None
    location: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    scheduled_start: str | None = None
    scheduled_end: str | None = None
    actual_duration_minutes: int | None = None
    completion_notes: str | None = None


class UpdateTodoInput(BaseModel):
    todo_id: str
    fields: UpdateTodoFields


class GetTodoDetailInput(BaseModel):
    todo_id: str


class SubTodo(BaseModel):
    title: str
    description: str | None = None
    scheduled_start: str | None = None
    scheduled_end: str | None = None
    estimated_duration_minutes: int | None = None


class CreateSubTodosInput(BaseModel):
    parent_todo_id: str
    children: list[SubTodo]


# ── Tool definitions ─────────────────────────────────────────────


@tool(
    tier=ActionTier.READ_ONLY,
    category="todo",
    embedding_text=(
        "todo: get_todos — list, view, check, show todos, backlog items, projects, "
        "scheduled items, agenda. What's on my todo list? Show my backlog. "
        "What do I need to do? What's on my agenda today? What tasks are scheduled? "
        "Any high-priority items? What are my active projects?"
    ),
)
async def get_todos(db: AsyncSession, input: GetTodosInput) -> dict:
    """Get todos, optionally filtered by status, priority, schedule, or date."""
    filters = input.filters.model_dump(exclude_none=True) if input.filters else {}
    results = await todo_service.get_todos(db, filters)
    return {"todos": results, "count": len(results)}


@tool(
    tier=ActionTier.LOW_STAKES,
    category="todo",
    embedding_text=(
        "todo: create_todo — create, add, new todo, backlog item, project, goal, "
        "schedule, calendar. Add this to my todo list. I need to remember to do X. "
        "Create a todo for grocery shopping. Schedule Y for 2pm tomorrow. "
        "Put Z on my calendar. Block off Friday afternoon. "
        "Schedule a meeting with John at 3pm. Book a calendar event."
    ),
)
async def create_todo(db: AsyncSession, input: CreateTodoInput) -> dict:
    """Create a new todo.

    If scheduled_start and scheduled_end are provided, it becomes 'scheduled'
    with a calendar event created automatically. Otherwise it starts as 'backlog'.
    """
    return await todo_service.create_todo(db, **input.model_dump(exclude_none=True))


@tool(
    tier=ActionTier.LOW_STAKES,
    category="todo",
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
)
async def update_todo(db: AsyncSession, input: UpdateTodoInput) -> dict:
    """Update fields on an existing todo.

    Handles all status transitions: setting status to 'completed' cascades
    completion to children, deletes calendar events, and auto-completes parent
    if all siblings are done. Setting status to 'cancelled' deletes the calendar
    event. Setting status to 'backlog' clears the schedule, deletes the calendar
    event, and moves the todo back to the backlog. Changing scheduled times on
    an already-scheduled todo tracks it as a reschedule. Calendar events sync
    automatically with schedule changes.
    """
    fields = input.fields.model_dump(exclude_none=True)

    if fields.get("status") == "backlog":
        result = await todo_service.send_to_backlog(
            db, input.todo_id, notes=fields.get("completion_notes"),
        )
        if result is None:
            return {"error": "Todo not found"}
        return result

    result = await todo_service.update_todo(db, input.todo_id, fields)
    if result is None:
        return {"error": "Todo not found"}
    return result


@tool(
    tier=ActionTier.READ_ONLY,
    category="todo",
    embedding_text=(
        "todo: get_todo_detail — view todo details, children, sub-items for a "
        "specific todo. Show me the details of that project. What sub-items are under this todo?"
    ),
)
async def get_todo_detail(db: AsyncSession, input: GetTodoDetailInput) -> dict:
    """Get full details of a todo including all its children."""
    result = await todo_service.get_todo_detail(db, input.todo_id)
    if result is None:
        return {"error": "Todo not found"}
    return result


@tool(
    tier=ActionTier.HIGH_STAKES,
    category="todo",
    embedding_text=(
        "todo: create_sub_todos — create multiple sub-items at once, batch schedule, "
        "plan several work blocks for a project. Break this todo into steps across the week."
    ),
)
async def create_sub_todos(db: AsyncSession, input: CreateSubTodosInput) -> dict:
    """Create multiple child todos under a parent.

    Requires confirmation. Calendar events are created automatically for
    children with scheduled times.
    """
    children = [c.model_dump(exclude_none=True) for c in input.children]
    results = await todo_service.create_child_todos_batch(
        db, input.parent_todo_id, children
    )
    return {"children": results, "count": len(results)}
