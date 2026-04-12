"""Centralized timezone utilities.

Single source of truth for resolving the user's timezone and producing
timezone-aware datetimes. All code that needs "now" or "today" in the
user's local time should use this module instead of constructing
datetimes directly.

The user's timezone is cached at startup from ProfileFacts (category="identity",
key="timezone"). If not set, falls back to globals.DEFAULT_TIMEZONE.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.globals import DEFAULT_TIMEZONE, get_cached_timezone


async def get_user_tz(db=None) -> ZoneInfo:
    """Resolve the user's timezone from cache.

    Returns the cached timezone (loaded at startup and refreshed on
    profile save). The db parameter is kept for backward compatibility
    but is no longer used.
    """
    return get_cached_timezone()


def user_tz_from_facts(facts: list) -> ZoneInfo:
    """Extract timezone from an already-loaded list of ProfileFact objects.

    Use this when facts are already in memory (e.g. context assembly)
    to avoid a redundant DB query.
    """
    for fact in facts:
        if fact.key == "timezone" and fact.value:
            return ZoneInfo(fact.value)
    return ZoneInfo(DEFAULT_TIMEZONE)


def now_in_user_tz(tz: ZoneInfo) -> datetime:
    """Get the current datetime in the user's timezone."""
    return datetime.now(tz)


def parse_dt(value: str | datetime | None) -> datetime | None:
    """Parse a datetime string or pass through a datetime object.

    Ensures the result is always timezone-aware. If the input string
    has no timezone info, it is assumed to be in UTC.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
