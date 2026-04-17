"""Calendar router -- REST endpoints for the frontend calendar view."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import google_calendar

router = APIRouter(prefix="/calendar", tags=["calendar"])

ASSISTANT_EVENT_COLOR = "#4285f4"


def _to_fullcalendar(event: dict) -> dict:
    is_assistant = event.get("is_assistant_created", False)
    out = {
        "id": event.get("id", ""),
        "title": event.get("summary", "(No title)"),
        "start": event.get("start", ""),
        "end": event.get("end", ""),
        "allDay": event.get("is_all_day", False),
        "extendedProps": {
            "location": event.get("location", ""),
            "description": event.get("description", ""),
            "isAssistantCreated": is_assistant,
            "status": event.get("status", ""),
        },
    }
    if is_assistant:
        out["color"] = ASSISTANT_EVENT_COLOR
    return out


@router.get("/events")
async def list_events(
    start: str = Query(..., description="ISO8601 start bound"),
    end: str = Query(..., description="ISO8601 end bound"),
    db: AsyncSession = Depends(get_db),
):
    creds = await google_calendar.get_google_credentials(db)
    if not creds:
        return {"connected": False, "events": []}

    result = await google_calendar.list_events(db, start, end, max_results=250)
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])

    return {
        "connected": True,
        "events": [_to_fullcalendar(e) for e in result],
    }
