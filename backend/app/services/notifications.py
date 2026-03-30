"""Notification scheduling and delivery via ntfy.

Handles the full notification lifecycle:
  1. schedule_notification() — inserts a row into scheduled_notifications
  2. process_due_notifications() — polls for due notifications, sends via ntfy,
     marks them sent. Called by APScheduler on an interval.

All push delivery goes through ntfy (simple HTTP POST). The ntfy container
runs on the Docker network and is reachable at the configured base URL.
"""

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.tables import ScheduledNotification
from app.services.serialization import model_to_dict

logger = logging.getLogger(__name__)


async def schedule_notification(
    db: AsyncSession,
    task_id: str,
    title: str,
    body: str,
    send_at: datetime,
) -> dict:
    """Create a scheduled notification linked to a task."""
    notification = ScheduledNotification(
        task_id=task_id,
        title=title,
        body=body,
        send_at=send_at,
    )
    db.add(notification)
    await db.flush()
    return model_to_dict(notification)


async def get_pending_notifications(db: AsyncSession) -> list[ScheduledNotification]:
    """Get all unsent notifications whose send_at has passed."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(ScheduledNotification)
        .where(ScheduledNotification.sent.is_(False))
        .where(ScheduledNotification.send_at <= now)
        .order_by(ScheduledNotification.send_at)
    )
    return list(result.scalars().all())


async def mark_sent(db: AsyncSession, notification_id) -> None:
    """Mark a notification as sent."""
    await db.execute(
        update(ScheduledNotification)
        .where(ScheduledNotification.id == notification_id)
        .values(sent=True, sent_at=datetime.now(timezone.utc))
    )


async def send_ntfy(title: str, body: str) -> bool:
    """Send a push notification via ntfy. Returns True on success."""
    url = f"{settings.ntfy_base_url}/{settings.ntfy_topic}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                content=body,
                headers={
                    "Title": title,
                    "Priority": "high",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info("Sent ntfy notification: %s", title)
            return True
    except Exception:
        logger.exception("Failed to send ntfy notification: %s", title)
        return False


async def process_due_notifications(session_factory: async_sessionmaker) -> None:
    """Poll for due notifications, send them, and mark as sent.

    Called by APScheduler on an interval. Creates its own DB session
    since it runs outside of FastAPI's request lifecycle.
    """
    async with session_factory() as db:
        pending = await get_pending_notifications(db)
        if not pending:
            return

        logger.info("Processing %d due notification(s)", len(pending))
        for notification in pending:
            success = await send_ntfy(notification.title, notification.body)
            if success:
                await mark_sent(db, notification.id)

        await db.commit()
