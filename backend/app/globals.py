"""Global product configuration and cached runtime state.

Section A: Static constants representing product decisions. These are values
that are the same across all environments but may be tuned as the product
evolves. Environment-varying settings (API keys, DB URL, feature flags)
remain in config.py.

Section B: Cached profile state loaded from the database at startup and
refreshed on profile save. Provides synchronous access to timezone and
profile fields without requiring a database call.
"""

from typing import Any
from zoneinfo import ZoneInfo


# ── Section A: Static Product Constants ────────────────────────────


# LLM — main agent
ANTHROPIC_MODEL = "claude-sonnet-4-6"
AGENT_MAX_TOOL_ROUNDS = 10
AGENT_DEFAULT_MAX_TOKENS = 16000
AGENT_DEFAULT_EFFORT = "medium"

# LLM — planner
PLANNER_MODEL = "claude-haiku-4-5-20251001"
PLANNER_MAX_TOKENS = 1024

# Tool selection (vector search)
TOOL_SELECTOR_TOP_K = 12
TOOL_SELECTOR_THRESHOLD = 0.40

# Embeddings
EMBEDDING_MODEL = "text-embedding-3-small"

# Cost tracking (Sonnet 4.6 pricing, per million tokens)
COST_PER_M_INPUT = 3.0
COST_PER_M_OUTPUT = 15.0  # also covers thinking tokens
COST_PER_M_CACHE_READ = 0.30
COST_PER_M_CACHE_WRITE = 3.75

# Google Calendar
CALENDAR_ASSISTANT_COLOR_ID = "9"  # Blueberry
CALENDAR_ASSISTANT_TAG = "[via Assistant]"

# Notifications
NOTIFICATION_POLL_SECONDS = 30

# Default timezone (fallback when user hasn't set one)
DEFAULT_TIMEZONE = "America/Los_Angeles"

# Scheduled job timing
MORNING_BRIEFING_DEFAULT_HOUR = 7
MORNING_BRIEFING_DEFAULT_MINUTE = 0
DEADLINE_WARNING_HOUR = 10
DEADLINE_WARNING_DAYS_AHEAD = 3
KEY_DATE_ALERT_HOUR = 9
KEY_DATE_ALERT_DAYS_AHEAD = 7


# ── Section B: Cached Profile State ───────────────────────────────

_profile_cache: dict[str, dict[str, Any]] | None = None
_user_tz: ZoneInfo | None = None


async def load_profile_cache(db) -> None:
    """Load (or reload) the profile cache from the database.

    Called once at app startup and again whenever the profile is saved.
    Uses a local import to avoid circular dependencies.
    """
    global _profile_cache, _user_tz

    from app.services.profile import get_current_profile

    _profile_cache = await get_current_profile(db)

    # Derive timezone from cached profile
    identity = _profile_cache.get("identity", {}).get("fields", {})
    tz_str = identity.get("timezone")
    if tz_str:
        try:
            _user_tz = ZoneInfo(tz_str)
        except (KeyError, ValueError):
            _user_tz = ZoneInfo(DEFAULT_TIMEZONE)
    else:
        _user_tz = ZoneInfo(DEFAULT_TIMEZONE)


def get_cached_timezone() -> ZoneInfo:
    """Return the user's timezone from cache, or the default."""
    return _user_tz or ZoneInfo(DEFAULT_TIMEZONE)


def get_cached_profile() -> dict[str, dict[str, Any]]:
    """Return the cached profile dict, or empty dict if not yet loaded."""
    return _profile_cache or {}
