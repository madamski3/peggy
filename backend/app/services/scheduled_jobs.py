"""Scheduled job definitions for proactive behaviors.

Each function is called by APScheduler on a cron schedule. Jobs create
their own DB sessions via the session factory since they run outside
of FastAPI's request lifecycle.

Job types:
  - morning_briefing: Agent invocation — LLM generates a daily summary
  - deadline_warning_scan: Agent invocation — LLM nudges about approaching deadlines
  - key_date_alerts: Simple notification — no LLM, pre-formatted birthday/anniversary alerts
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.models.tables import Person
from app.services.notifications import send_ntfy
from app.services.proactive import invoke_agent_proactively
from app.services.timezone import get_user_tz
from app.services.todos import get_todos

logger = logging.getLogger(__name__)


async def morning_briefing(session_factory: async_sessionmaker) -> None:
    """Generate and send a morning briefing via push notification.

    Invokes the full agent loop with a synthetic message so the LLM can
    check calendar, tasks, deadlines, and emails to produce a summary.
    """
    logger.info("Running morning briefing job")

    response = await invoke_agent_proactively(
        session_factory,
        "Generate a morning briefing for the user. Check today's calendar, "
        "pending tasks, upcoming deadlines, and recent emails. Summarize the "
        "day ahead in 2-4 concise sentences suitable for a push notification.",
    )

    if response and response.get("spoken_summary"):
        await send_ntfy(
            title="Good morning! Here's your day",
            body=response["spoken_summary"],
        )
        logger.info("Morning briefing sent")
    else:
        logger.warning("Morning briefing produced no response")


async def deadline_warning_scan(session_factory: async_sessionmaker) -> None:
    """Scan for todos with approaching deadlines and nudge the user.

    Only triggers if there are backlog todos with deadlines within the
    configured horizon that have no tasks scheduled yet.
    """
    logger.info("Running deadline warning scan")

    async with session_factory() as db:
        user_tz = await get_user_tz(db)
        now = datetime.now(user_tz)

        horizon = now + timedelta(days=settings.deadline_warning_days_ahead)
        deadline_str = horizon.strftime("%Y-%m-%d")

        approaching = await get_todos(db, {
            "status": "backlog",
            "deadline_before": deadline_str,
            "has_scheduled_tasks": False,
        })

    if not approaching:
        logger.info("No approaching deadlines found")
        return

    # Build a summary of approaching deadlines for the agent
    lines = []
    for todo in approaching:
        title = todo.get("title", "untitled")
        deadline = todo.get("deadline", "?")
        priority = todo.get("priority", "medium")
        lines.append(f"- {title} (deadline: {deadline}, priority: {priority})")
    todo_summary = "\n".join(lines)

    response = await invoke_agent_proactively(
        session_factory,
        f"The following todos have approaching deadlines but no tasks "
        f"scheduled yet:\n{todo_summary}\n\n"
        f"Generate a brief nudge for the user (2-3 sentences, suitable for "
        f"a push notification). Be specific about what needs attention.",
    )

    if response and response.get("spoken_summary"):
        await send_ntfy(
            title=f"{len(approaching)} deadline(s) approaching",
            body=response["spoken_summary"],
        )
        logger.info("Deadline warning sent for %d todo(s)", len(approaching))


async def key_date_alerts(session_factory: async_sessionmaker) -> None:
    """Check for upcoming birthdays and anniversaries, send simple alerts.

    No LLM call — formats notifications directly from People records.
    """
    logger.info("Running key date alerts scan")

    async with session_factory() as db:
        user_tz = await get_user_tz(db)
        today = datetime.now(user_tz).date()

        horizon = today + timedelta(days=settings.key_date_alert_days_ahead)

        # Load all people with key_dates
        result = await db.execute(
            select(Person).where(Person.key_dates.isnot(None))
        )
        people = result.scalars().all()

    alerts = []
    for person in people:
        key_dates = person.key_dates or {}
        for label, date_str in key_dates.items():
            try:
                # Parse the date (expecting YYYY-MM-DD or MM-DD format)
                if len(date_str) == 10:  # YYYY-MM-DD
                    dt = datetime.strptime(date_str, "%Y-%m-%d").date()
                elif len(date_str) == 5:  # MM-DD
                    dt = datetime.strptime(f"{today.year}-{date_str}", "%Y-%m-%d").date()
                else:
                    continue

                # Check this year's occurrence
                this_year = dt.replace(year=today.year)
                if this_year < today:
                    this_year = dt.replace(year=today.year + 1)

                days_until = (this_year - today).days
                if 0 <= days_until <= settings.key_date_alert_days_ahead:
                    if days_until == 0:
                        timing = "today"
                    elif days_until == 1:
                        timing = "tomorrow"
                    else:
                        timing = f"in {days_until} days ({this_year.strftime('%B %d')})"
                    alerts.append(f"{person.name}'s {label} is {timing}")
            except (ValueError, TypeError):
                continue

    if not alerts:
        logger.info("No upcoming key dates found")
        return

    body = "\n".join(f"• {a}" for a in alerts)
    await send_ntfy(
        title=f"{len(alerts)} upcoming date(s)",
        body=body,
    )
    logger.info("Key date alerts sent: %d", len(alerts))
