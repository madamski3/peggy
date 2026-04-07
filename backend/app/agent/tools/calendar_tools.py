"""Google Calendar tool definitions for the agent.

Thin handler functions that bridge between the orchestrator's (db, **kwargs)
calling convention and the google_calendar service module. Each handler
unpacks kwargs, calls the service, and returns a JSON-serializable dict.

Registered tools:
  - get_calendar_events  (READ_ONLY)  -- list events in a time range
  - create_calendar_event (LOW_STAKES) -- create an event, tagged as assistant-created
  - update_calendar_event (LOW_STAKES) -- partial update of an existing event
  - delete_calendar_event (HIGH_STAKES) -- irreversible deletion, requires confirmation
  - find_free_time        (READ_ONLY)  -- find gaps between events
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.services import google_calendar


# ── Handlers ──────────────────────────────────────────────────────


async def handle_get_calendar_events(db: AsyncSession, **kwargs: Any) -> dict:
    events = await google_calendar.list_events(
        db,
        time_min=kwargs["time_min"],
        time_max=kwargs["time_max"],
        max_results=kwargs.get("max_results", 20),
    )
    if isinstance(events, dict) and "error" in events:
        return events
    return {"events": events, "count": len(events)}


async def handle_create_calendar_event(db: AsyncSession, **kwargs: Any) -> dict:
    return await google_calendar.create_event(
        db,
        summary=kwargs["summary"],
        start=kwargs["start"],
        end=kwargs["end"],
        description=kwargs.get("description", ""),
        location=kwargs.get("location", ""),
        all_day=kwargs.get("all_day", False),
    )


async def handle_update_calendar_event(db: AsyncSession, **kwargs: Any) -> dict:
    event_id = kwargs["event_id"]
    update_fields = {}
    for key in ("summary", "start", "end", "description", "location"):
        if key in kwargs:
            update_fields[key] = kwargs[key]
    return await google_calendar.update_event(db, event_id, **update_fields)


async def handle_delete_calendar_event(db: AsyncSession, **kwargs: Any) -> dict:
    return await google_calendar.delete_event(db, kwargs["event_id"])


async def handle_find_free_time(db: AsyncSession, **kwargs: Any) -> dict:
    slots = await google_calendar.find_free_time(
        db,
        time_min=kwargs["time_min"],
        time_max=kwargs["time_max"],
        duration_minutes=kwargs.get("duration_minutes", 30),
    )
    return {"free_slots": slots, "count": len(slots)}


# ── Tool Registrations ───────────────────────────────────────────


register_tool(ToolDefinition(
    name="get_calendar_events",
    description="List Google Calendar events within a time range.",
    embedding_text=(
        "calendar: get_calendar_events — list, view, check, show calendar events, "
        "meetings, appointments for today, tomorrow, this week, a date range. "
        "What's on my calendar? Do I have any meetings? Am I free Thursday? "
        "What does my schedule look like?"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "time_min": {"type": "string", "description": "ISO 8601 datetime."},
            "time_max": {"type": "string", "description": "ISO 8601 datetime."},
            "max_results": {"type": "integer"},
        },
        "required": ["time_min", "time_max"],
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_calendar_events,
    category="calendar",
))


register_tool(ToolDefinition(
    name="create_calendar_event",
    description="Create a Google Calendar event, tagged as assistant-created.",
    embedding_text=(
        "calendar: create_calendar_event — create, add, schedule, book a calendar event, "
        "meeting, appointment, block time. Put this on my calendar. "
        "Schedule a meeting with John at 3pm. Block off Friday afternoon."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "start": {"type": "string", "description": "ISO 8601 datetime or date for all-day."},
            "end": {"type": "string", "description": "ISO 8601 datetime or date for all-day."},
            "description": {"type": "string"},
            "location": {"type": "string"},
            "all_day": {"type": "boolean"},
        },
        "required": ["summary", "start", "end"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_create_calendar_event,
    category="calendar",
))


register_tool(ToolDefinition(
    name="update_calendar_event",
    description="Update fields on an existing Google Calendar event.",
    embedding_text=(
        "calendar: update_calendar_event — change, move, reschedule, rename, edit "
        "a calendar event. Move my 3pm meeting to 4pm. Change the location."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "event_id": {"type": "string"},
            "summary": {"type": "string"},
            "start": {"type": "string", "description": "ISO 8601 datetime."},
            "end": {"type": "string", "description": "ISO 8601 datetime."},
            "description": {"type": "string"},
            "location": {"type": "string"},
        },
        "required": ["event_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_update_calendar_event,
    category="calendar",
))


register_tool(ToolDefinition(
    name="delete_calendar_event",
    description="Delete a Google Calendar event (irreversible).",
    embedding_text=(
        "calendar: delete_calendar_event — delete, remove, cancel a calendar event "
        "or meeting. Remove that appointment. Cancel the meeting."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "event_id": {"type": "string"},
        },
        "required": ["event_id"],
    },
    tier=ActionTier.HIGH_STAKES,
    handler=handle_delete_calendar_event,
    category="calendar",
))


register_tool(ToolDefinition(
    name="find_free_time",
    description="Find free time slots between calendar events.",
    embedding_text=(
        "calendar: find_free_time — find free time, open slots, availability, gaps "
        "in my schedule. When am I free? Find a 2-hour block this week. "
        "What time works for a meeting?"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "time_min": {"type": "string", "description": "ISO 8601 datetime."},
            "time_max": {"type": "string", "description": "ISO 8601 datetime."},
            "duration_minutes": {"type": "integer", "description": "Minimum slot length in minutes (default: 30)."},
        },
        "required": ["time_min", "time_max"],
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_find_free_time,
    category="calendar",
))
