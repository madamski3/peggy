"""Centralized timezone utilities.

Single source of truth for resolving the user's timezone and producing
timezone-aware datetimes. All code that needs "now" or "today" in the
user's local time should use this module instead of constructing
datetimes directly.

The user's timezone is stored as a ProfileFact (category="identity",
key="timezone"). If not set, falls back to settings.default_timezone.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings


async def get_user_tz(db: AsyncSession) -> ZoneInfo:
    """Resolve the user's timezone from the database.

    Queries active ProfileFacts for the timezone setting. Falls back
    to settings.default_timezone if not configured.
    """
    # Import here to avoid circular dependency (profile -> embeddings -> ...)
    from app.services.profile import get_active_facts

    facts = await get_active_facts(db)
    return user_tz_from_facts(facts)


def user_tz_from_facts(facts: list) -> ZoneInfo:
    """Extract timezone from an already-loaded list of ProfileFact objects.

    Use this when facts are already in memory (e.g. context assembly)
    to avoid a redundant DB query.
    """
    for fact in facts:
        if fact.key == "timezone" and fact.value:
            return ZoneInfo(fact.value)
    return ZoneInfo(settings.default_timezone)


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
