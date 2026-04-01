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
    description=(
        "List upcoming Google Calendar events within a time range. "
        "Returns event summaries, times, locations, and whether they were created by the assistant."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "time_min": {
                "type": "string",
                "description": "Start of time range in ISO 8601 format (e.g., 2026-03-28T00:00:00-04:00)",
            },
            "time_max": {
                "type": "string",
                "description": "End of time range in ISO 8601 format (e.g., 2026-03-28T23:59:59-04:00)",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of events to return (default: 20)",
            },
        },
        "required": ["time_min", "time_max"],
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_calendar_events,
    category="calendar",
))


register_tool(ToolDefinition(
    name="create_calendar_event",
    description=(
        "Create a new event on the user's Google Calendar. "
        "The event will be tagged as assistant-created with a distinct color. "
        "Use ISO 8601 datetime strings with timezone for start and end."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Event title",
            },
            "start": {
                "type": "string",
                "description": "Event start time in ISO 8601 format (e.g., 2026-03-28T12:00:00-04:00) or date (e.g., 2026-03-28) for all-day events",
            },
            "end": {
                "type": "string",
                "description": "Event end time in ISO 8601 format or date for all-day events",
            },
            "description": {
                "type": "string",
                "description": "Event description or notes",
            },
            "location": {
                "type": "string",
                "description": "Event location",
            },
            "all_day": {
                "type": "boolean",
                "description": "If true, create an all-day event using date strings (default: false)",
            },
        },
        "required": ["summary", "start", "end"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_create_calendar_event,
    category="calendar",
))


register_tool(ToolDefinition(
    name="update_calendar_event",
    description=(
        "Update an existing Google Calendar event. "
        "Only the fields provided will be updated; others remain unchanged."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "The Google Calendar event ID to update",
            },
            "summary": {
                "type": "string",
                "description": "New event title",
            },
            "start": {
                "type": "string",
                "description": "New start time in ISO 8601 format",
            },
            "end": {
                "type": "string",
                "description": "New end time in ISO 8601 format",
            },
            "description": {
                "type": "string",
                "description": "New event description",
            },
            "location": {
                "type": "string",
                "description": "New event location",
            },
        },
        "required": ["event_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_update_calendar_event,
    category="calendar",
))


register_tool(ToolDefinition(
    name="delete_calendar_event",
    description=(
        "Delete an event from the user's Google Calendar. "
        "This is irreversible — use with caution."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "The Google Calendar event ID to delete",
            },
        },
        "required": ["event_id"],
    },
    tier=ActionTier.HIGH_STAKES,
    handler=handle_delete_calendar_event,
    category="calendar",
))


register_tool(ToolDefinition(
    name="find_free_time",
    description=(
        "Find available time slots in the user's calendar within a given time range. "
        "Returns gaps of at least the specified duration between existing events."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "time_min": {
                "type": "string",
                "description": "Start of search range in ISO 8601 format",
            },
            "time_max": {
                "type": "string",
                "description": "End of search range in ISO 8601 format",
            },
            "duration_minutes": {
                "type": "integer",
                "description": "Minimum slot duration in minutes (default: 30)",
            },
        },
        "required": ["time_min", "time_max"],
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_find_free_time,
    category="calendar",
))
