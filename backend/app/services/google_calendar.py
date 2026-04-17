"""Google Calendar API integration.

Wraps the synchronous Google API client in asyncio.to_thread() for
async compatibility. Each API call builds a fresh service object
to avoid thread-safety issues.

This module handles two concerns:
  1. Token management -- load/save/refresh OAuth credentials from the
     credentials table. Tokens are auto-persisted after each API call
     in case the SDK refreshed them.
  2. Calendar operations -- list, create, update, delete events, and
     find free time slots. Events created by the assistant are tagged
     with a specific color (blueberry) and a "[via Assistant]" marker
     in the description so they can be distinguished from user-created events.

The auth router (routers/auth.py) handles the initial OAuth flow and
calls save_google_credentials() to store the tokens.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.globals import CALENDAR_ASSISTANT_COLOR_ID, CALENDAR_ASSISTANT_TAG, get_cached_timezone
from app.models.tables import Credential
from app.services.timezone import parse_dt

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
]
SERVICE_KEY = "google_calendar"


# ── Token Management ────────────────────────────────────────────


async def get_google_credentials(db: AsyncSession) -> Credentials | None:
    """Load Google OAuth credentials from the database."""
    result = await db.execute(
        select(Credential).where(Credential.service == SERVICE_KEY)
    )
    row = result.scalar_one_or_none()
    if not row:
        return None

    token_data = row.token_data
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=token_data.get("scopes", SCOPES),
    )
    return creds


async def save_google_credentials(db: AsyncSession, creds: Credentials) -> None:
    """Upsert Google OAuth credentials to the database."""
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }

    result = await db.execute(
        select(Credential).where(Credential.service == SERVICE_KEY)
    )
    row = result.scalar_one_or_none()

    if row:
        row.token_data = token_data
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(Credential(service=SERVICE_KEY, token_data=token_data))

    await db.flush()


async def is_connected(db: AsyncSession) -> bool:
    """Check if Google Calendar credentials exist."""
    result = await db.execute(
        select(Credential.id).where(Credential.service == SERVICE_KEY)
    )
    return result.scalar_one_or_none() is not None


# ── API Client ──────────────────────────────────────────────────


def _build_service(creds: Credentials):
    """Build a Google Calendar API service object (synchronous)."""
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _normalize_event(event: dict) -> dict:
    """Convert a raw Google Calendar event to a clean dict."""
    start = event.get("start", {})
    end = event.get("end", {})

    is_all_day = "date" in start
    start_str = start.get("date") or start.get("dateTime", "")
    end_str = end.get("date") or end.get("dateTime", "")

    description = event.get("description", "")
    is_assistant = (
        event.get("colorId") == CALENDAR_ASSISTANT_COLOR_ID
        or CALENDAR_ASSISTANT_TAG in description
    )

    return {
        "id": event.get("id", ""),
        "summary": event.get("summary", "(No title)"),
        "start": start_str,
        "end": end_str,
        "is_all_day": is_all_day,
        "location": event.get("location", ""),
        "description": description,
        "is_assistant_created": is_assistant,
        "status": event.get("status", ""),
    }


# ── Calendar ID Resolution ─────────────────────────────────────


async def _resolve_calendar_id(db: AsyncSession) -> str:
    """Return the primary email as calendar ID, or the configured default."""
    from app.services.profile import get_primary_email

    email = await get_primary_email(db)
    return email or settings.google_calendar_id


# ── Calendar Operations ─────────────────────────────────────────


async def list_events(
    db: AsyncSession,
    time_min: str,
    time_max: str,
    max_results: int = 50,
) -> list[dict] | dict:
    """List calendar events in a time range."""
    creds = await get_google_credentials(db)
    if not creds:
        return []

    calendar_id = await _resolve_calendar_id(db)

    def _fetch(cal_id: str):
        service = _build_service(creds)
        result = service.events().list(
            calendarId=cal_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return result.get("items", [])

    try:
        raw_events = await asyncio.to_thread(_fetch, calendar_id)
    except Exception as exc:
        if calendar_id != settings.google_calendar_id:
            logger.error(
                "Calendar API call failed for configured primary email '%s': %s",
                calendar_id, exc,
            )
            return {
                "error": (
                    f"Calendar API rejected the configured primary email ({calendar_id}). "
                    "Please verify the Primary email on your Profile page matches "
                    "the Google account you authenticated with."
                )
            }
        raise

    # The Google SDK may have silently refreshed the access token during the
    # API call. Persist it so subsequent calls don't need to refresh again.
    if creds.token:
        await save_google_credentials(db, creds)

    return [_normalize_event(e) for e in raw_events]


async def create_event(
    db: AsyncSession,
    summary: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
    all_day: bool = False,
) -> dict:
    """Create a calendar event. Tags it as assistant-created."""
    creds = await get_google_credentials(db)
    if not creds:
        return {"error": "Google Calendar not connected. Visit /api/auth/google to connect."}

    calendar_id = await _resolve_calendar_id(db)

    # Tag description
    tagged_description = f"{description}\n{CALENDAR_ASSISTANT_TAG}".strip() if description else CALENDAR_ASSISTANT_TAG

    body: dict = {
        "summary": summary,
        "description": tagged_description,
        "colorId": CALENDAR_ASSISTANT_COLOR_ID,
    }

    if location:
        body["location"] = location

    if all_day:
        body["start"] = {"date": start}
        body["end"] = {"date": end}
    else:
        body["start"] = {"dateTime": start, "timeZone": str(get_cached_timezone())}
        body["end"] = {"dateTime": end, "timeZone": str(get_cached_timezone())}

    def _create(cal_id: str):
        service = _build_service(creds)
        return service.events().insert(
            calendarId=cal_id,
            body=body,
        ).execute()

    try:
        raw = await asyncio.to_thread(_create, calendar_id)
    except Exception as exc:
        if calendar_id != settings.google_calendar_id:
            logger.error(
                "Calendar API call failed for configured primary email '%s': %s",
                calendar_id, exc,
            )
            return {
                "error": (
                    f"Calendar API rejected the configured primary email ({calendar_id}). "
                    "Please verify the Primary email on your Profile page matches "
                    "the Google account you authenticated with."
                )
            }
        raise

    if creds.token:
        await save_google_credentials(db, creds)

    return _normalize_event(raw)


async def update_event(
    db: AsyncSession,
    event_id: str,
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
    location: str | None = None,
) -> dict:
    """Update fields on an existing calendar event."""
    creds = await get_google_credentials(db)
    if not creds:
        return {"error": "Google Calendar not connected. Visit /api/auth/google to connect."}

    calendar_id = await _resolve_calendar_id(db)

    def _update(cal_id: str):
        service = _build_service(creds)
        # Fetch current event first
        event = service.events().get(
            calendarId=cal_id,
            eventId=event_id,
        ).execute()

        if summary is not None:
            event["summary"] = summary
        if description is not None:
            event["description"] = description
        if location is not None:
            event["location"] = location
        if start is not None:
            if "date" in event.get("start", {}):
                event["start"] = {"date": start}
            else:
                event["start"] = {"dateTime": start, "timeZone": str(get_cached_timezone())}
        if end is not None:
            if "date" in event.get("end", {}):
                event["end"] = {"date": end}
            else:
                event["end"] = {"dateTime": end, "timeZone": str(get_cached_timezone())}

        return service.events().update(
            calendarId=cal_id,
            eventId=event_id,
            body=event,
        ).execute()

    try:
        raw = await asyncio.to_thread(_update, calendar_id)
    except Exception as exc:
        if calendar_id != settings.google_calendar_id:
            logger.error(
                "Calendar API call failed for configured primary email '%s': %s",
                calendar_id, exc,
            )
            return {
                "error": (
                    f"Calendar API rejected the configured primary email ({calendar_id}). "
                    "Please verify the Primary email on your Profile page matches "
                    "the Google account you authenticated with."
                )
            }
        raise

    if creds.token:
        await save_google_credentials(db, creds)

    return _normalize_event(raw)


async def delete_event(db: AsyncSession, event_id: str) -> dict:
    """Delete a calendar event."""
    creds = await get_google_credentials(db)
    if not creds:
        return {"error": "Google Calendar not connected. Visit /api/auth/google to connect."}

    calendar_id = await _resolve_calendar_id(db)

    def _delete(cal_id: str):
        service = _build_service(creds)
        service.events().delete(
            calendarId=cal_id,
            eventId=event_id,
        ).execute()

    try:
        await asyncio.to_thread(_delete, calendar_id)
    except Exception as exc:
        if calendar_id != settings.google_calendar_id:
            logger.error(
                "Calendar API call failed for configured primary email '%s': %s",
                calendar_id, exc,
            )
            return {
                "error": (
                    f"Calendar API rejected the configured primary email ({calendar_id}). "
                    "Please verify the Primary email on your Profile page matches "
                    "the Google account you authenticated with."
                )
            }
        raise

    if creds.token:
        await save_google_credentials(db, creds)

    return {"deleted": True, "event_id": event_id}


async def find_free_time(
    db: AsyncSession,
    time_min: str,
    time_max: str,
    duration_minutes: int = 30,
) -> list[dict] | dict:
    """Find free time slots of at least `duration_minutes` in a time range."""
    creds = await get_google_credentials(db)
    if not creds:
        return []

    calendar_id = await _resolve_calendar_id(db)

    def _query_freebusy(cal_id: str):
        service = _build_service(creds)
        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "timeZone": str(get_cached_timezone()),
            "items": [{"id": cal_id}],
        }
        result = service.freebusy().query(body=body).execute()
        busy = result.get("calendars", {}).get(cal_id, {}).get("busy", [])
        return busy

    try:
        busy = await asyncio.to_thread(_query_freebusy, calendar_id)
    except Exception as exc:
        if calendar_id != settings.google_calendar_id:
            logger.error(
                "Calendar API call failed for configured primary email '%s': %s",
                calendar_id, exc,
            )
            return {
                "error": (
                    f"Calendar API rejected the configured primary email ({calendar_id}). "
                    "Please verify the Primary email on your Profile page matches "
                    "the Google account you authenticated with."
                )
            }
        raise

    if creds.token:
        await save_google_credentials(db, creds)

    # Convert to datetime objects
    range_start = parse_dt(time_min)
    range_end = parse_dt(time_max)
    min_duration = timedelta(minutes=duration_minutes)

    busy_periods = []
    for b in busy:
        busy_periods.append((
            parse_dt(b["start"]),
            parse_dt(b["end"]),
        ))

    # Sort busy periods
    busy_periods.sort(key=lambda x: x[0])

    # Find gaps
    free_slots = []
    current = range_start
    for busy_start, busy_end in busy_periods:
        if busy_start > current:
            gap = busy_start - current
            if gap >= min_duration:
                free_slots.append({
                    "start": current.isoformat(),
                    "end": busy_start.isoformat(),
                    "duration_minutes": int(gap.total_seconds() / 60),
                })
        if busy_end > current:
            current = busy_end

    # Check trailing gap
    if range_end > current:
        gap = range_end - current
        if gap >= min_duration:
            free_slots.append({
                "start": current.isoformat(),
                "end": range_end.isoformat(),
                "duration_minutes": int(gap.total_seconds() / 60),
            })

    return free_slots
