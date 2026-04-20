"""Google Calendar tool definitions for the agent.

Registered tools:
  - get_calendar_events  (READ_ONLY)  -- list events in a time range
  - update_calendar_event (LOW_STAKES) -- partial update of an existing event
  - delete_calendar_event (HIGH_STAKES) -- irreversible deletion, requires confirmation
  - find_free_time        (READ_ONLY)  -- find gaps between events

Calendar events are created automatically when todos are scheduled (via
todo_tools.create_todo with scheduled_start/scheduled_end). These tools
handle read/update/delete of existing events, including non-assistant events.
"""

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, tool
from app.services import google_calendar


class GetCalendarEventsInput(BaseModel):
    time_min: str = Field(..., description="ISO 8601 datetime.")
    time_max: str = Field(..., description="ISO 8601 datetime.")
    max_results: int = 20


class UpdateCalendarEventInput(BaseModel):
    event_id: str
    summary: str | None = None
    start: str | None = Field(None, description="ISO 8601 datetime.")
    end: str | None = Field(None, description="ISO 8601 datetime.")
    description: str | None = None
    location: str | None = None


class DeleteCalendarEventInput(BaseModel):
    event_id: str


class FindFreeTimeInput(BaseModel):
    time_min: str = Field(..., description="ISO 8601 datetime.")
    time_max: str = Field(..., description="ISO 8601 datetime.")
    duration_minutes: int = Field(
        30, description="Minimum slot length in minutes (default: 30)."
    )


@tool(
    tier=ActionTier.READ_ONLY,
    category="calendar",
    embedding_text=(
        "calendar: get_calendar_events — list, view, check, show calendar events, "
        "meetings, appointments for today, tomorrow, this week, a date range. "
        "What's on my calendar? Do I have any meetings? Am I free Thursday? "
        "What does my schedule look like?"
    ),
)
async def get_calendar_events(db: AsyncSession, input: GetCalendarEventsInput) -> dict:
    """List Google Calendar events within a time range."""
    events = await google_calendar.list_events(
        db,
        time_min=input.time_min,
        time_max=input.time_max,
        max_results=input.max_results,
    )
    if isinstance(events, dict) and "error" in events:
        return events
    return {"events": events, "count": len(events)}


@tool(
    tier=ActionTier.LOW_STAKES,
    category="calendar",
    embedding_text=(
        "calendar: update_calendar_event — change, move, reschedule, rename, edit "
        "a calendar event. Move my 3pm meeting to 4pm. Change the location."
    ),
)
async def update_calendar_event(db: AsyncSession, input: UpdateCalendarEventInput) -> dict:
    """Update fields on an existing Google Calendar event."""
    # exclude_unset preserves the original "only pass keys the LLM provided" behavior
    update_fields = input.model_dump(exclude_unset=True, exclude={"event_id"})
    return await google_calendar.update_event(db, input.event_id, **update_fields)


@tool(
    tier=ActionTier.HIGH_STAKES,
    category="calendar",
    embedding_text=(
        "calendar: delete_calendar_event — delete, remove, cancel a calendar event "
        "or meeting. Remove that appointment. Cancel the meeting."
    ),
)
async def delete_calendar_event(db: AsyncSession, input: DeleteCalendarEventInput) -> dict:
    """Delete a Google Calendar event (irreversible)."""
    return await google_calendar.delete_event(db, input.event_id)


@tool(
    tier=ActionTier.READ_ONLY,
    category="calendar",
    embedding_text=(
        "calendar: find_free_time — find free time, open slots, availability, gaps "
        "in my schedule. When am I free? Find a 2-hour block this week. "
        "What time works for a meeting?"
    ),
)
async def find_free_time(db: AsyncSession, input: FindFreeTimeInput) -> dict:
    """Find free time slots between calendar events."""
    slots = await google_calendar.find_free_time(
        db,
        time_min=input.time_min,
        time_max=input.time_max,
        duration_minutes=input.duration_minutes,
    )
    if isinstance(slots, dict) and "error" in slots:
        return slots
    return {"free_slots": slots, "count": len(slots)}
