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
from app.globals import (
    DEADLINE_WARNING_DAYS_AHEAD,
    KEY_DATE_ALERT_DAYS_AHEAD,
    get_cached_timezone,
)
from sqlalchemy import and_

from app.models.tables import Interaction, Person
from app.services import daily_plans, wiki as wiki_service
from app.services.notifications import send_ntfy
from app.services.proactive import invoke_agent_proactively
from app.services.serialization import model_to_dict
from app.services.todos import get_todos

logger = logging.getLogger(__name__)


async def morning_briefing(session_factory: async_sessionmaker) -> None:
    """Generate a daily plan proposal and send a notification with deep link.

    Invokes the full agent loop with a planning prompt. If the agent returns
    a structured daily_plan payload, it's saved as a draft proposal for the
    user to review in the /planning UI. The notification links to that page.
    """
    logger.info("Running morning briefing / daily plan job")

    response = await invoke_agent_proactively(
        session_factory,
        "Plan the user's day. Check today's calendar, scheduled todos, backlog "
        "todos (especially those with approaching deadlines or target dates), "
        "and find free time slots. Generate a daily plan proposal. Return a "
        "structured_payload with type 'daily_plan'. Also include a brief "
        "spoken_summary (2-3 sentences for a push notification).",
    )

    if not response or not response.get("spoken_summary"):
        logger.warning("Morning plan produced no response")
        return

    # Save the plan proposal if the agent returned a structured daily_plan
    payload = response.get("structured_payload")
    if isinstance(payload, dict) and payload.get("type") == "daily_plan":
        async with session_factory() as db:
            today = datetime.now(get_cached_timezone()).date()
            await daily_plans.save_proposal(
                db, today, payload, response.get("spoken_summary")
            )
            await db.commit()
        logger.info("Daily plan proposal saved for %s", today)

    await send_ntfy(
        title="Good morning! Here's your plan",
        body=response["spoken_summary"],
        click_url=f"{settings.frontend_base_url}/planning",
    )
    logger.info("Morning plan notification sent")


async def deadline_warning_scan(session_factory: async_sessionmaker) -> None:
    """Scan for todos with approaching deadlines and nudge the user.

    Only triggers if there are backlog todos with deadlines within the
    configured horizon that have no tasks scheduled yet.
    """
    logger.info("Running deadline warning scan")

    async with session_factory() as db:
        now = datetime.now(get_cached_timezone())

        horizon = now + timedelta(days=DEADLINE_WARNING_DAYS_AHEAD)
        deadline_str = horizon.strftime("%Y-%m-%d")

        approaching = await get_todos(db, {
            "status": "backlog",
            "deadline_before": deadline_str,
            "is_scheduled": False,
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
        f"The following todos have approaching deadlines and haven't been "
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
        today = datetime.now(get_cached_timezone()).date()

        horizon = today + timedelta(days=KEY_DATE_ALERT_DAYS_AHEAD)

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
                if 0 <= days_until <= KEY_DATE_ALERT_DAYS_AHEAD:
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


async def nightly_wiki_review(session_factory: async_sessionmaker) -> None:
    """Review today's conversations and compile knowledge into the personal wiki.

    Queries all interactions from today, formats them into a summary, and
    invokes the agent with the wiki_review channel to update wiki pages
    and extract ProfileFacts. After compilation, re-embeds all wiki pages.
    """
    logger.info("Running nightly wiki review")

    user_tz = get_cached_timezone()
    today = datetime.now(user_tz).date()
    day_start = datetime(today.year, today.month, today.day, tzinfo=user_tz)
    day_end = day_start + timedelta(days=1)

    # Query today's interactions
    async with session_factory() as db:
        result = await db.execute(
            select(Interaction)
            .where(and_(
                Interaction.created_at >= day_start,
                Interaction.created_at < day_end,
                Interaction.channel == "chat",
            ))
            .order_by(Interaction.created_at.asc())
        )
        interactions = result.scalars().all()

    if not interactions:
        logger.info("No interactions today, skipping wiki review")
        return

    # Format conversations for the LLM
    conversation_lines = []
    for ix in interactions:
        if ix.user_message:
            conversation_lines.append(f"User: {ix.user_message}")
        response = ix.assistant_response or {}
        if summary := response.get("spoken_summary"):
            conversation_lines.append(f"Assistant: {summary}")
        actions = response.get("actions_taken") or []
        if actions:
            action_names = [a.get("tool_name", "unknown") for a in actions]
            conversation_lines.append(f"  [Actions: {', '.join(action_names)}]")
        conversation_lines.append("")

    conversations_text = "\n".join(conversation_lines)

    # Read current wiki index
    index_entries = wiki_service.read_index()
    index_text = "\n".join(
        f"- {e['page_name']}: {e['summary']}" for e in index_entries
    ) if index_entries else "(wiki is empty — no pages yet)"

    synthetic_message = (
        f"Review today's conversations and update the personal wiki.\n\n"
        f"## Current wiki index\n{index_text}\n\n"
        f"## Today's conversations ({len(interactions)} interactions)\n"
        f"{conversations_text}"
    )

    # Invoke agent with wiki_review channel
    response = await invoke_agent_proactively(
        session_factory, synthetic_message, channel="wiki_review",
    )

    if not response:
        logger.warning("Wiki review produced no response")
        return

    # Re-embed all wiki pages after compilation
    async with session_factory() as db:
        count = await wiki_service.embed_pages(db)
        await db.commit()

    logger.info("Wiki review complete: %d pages embedded", count)
