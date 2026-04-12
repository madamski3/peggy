"""FastAPI application entry point.

Creates the app, configures CORS (allow all origins for Tailscale access),
and registers all routers under the /api prefix. Uvicorn runs this as
app.main:app.

Also starts APScheduler on startup with:
  - Notification poller (every 30s) for reminder delivery
  - Morning briefing (daily cron)
  - Deadline warning scanner (daily cron)
  - Key date alerts (daily cron)
"""

import logging
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import async_session_maker
from app.globals import (
    DEADLINE_WARNING_HOUR,
    KEY_DATE_ALERT_HOUR,
    MORNING_BRIEFING_DEFAULT_HOUR,
    MORNING_BRIEFING_DEFAULT_MINUTE,
    NOTIFICATION_POLL_SECONDS,
    get_cached_timezone,
    load_profile_cache,
)
from app.routers import auth, chat, health, people, planning, profile, todos
from app.services.notifications import process_due_notifications
from app.services.scheduled_jobs import (
    deadline_warning_scan,
    key_date_alerts,
    morning_briefing,
)

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load profile cache (includes timezone) so cron jobs fire at local time
    async with async_session_maker() as db:
        await load_profile_cache(db)
    user_tz = get_cached_timezone()
    logger.info("Scheduler using timezone: %s", user_tz)

    # Startup
    scheduler.add_job(
        process_due_notifications,
        "interval",
        seconds=NOTIFICATION_POLL_SECONDS,
        args=[async_session_maker],
        id="notification_poller",
    )
    if settings.morning_briefing_enabled:
        scheduler.add_job(
            morning_briefing,
            CronTrigger(
                hour=MORNING_BRIEFING_DEFAULT_HOUR,
                minute=MORNING_BRIEFING_DEFAULT_MINUTE,
                timezone=user_tz,
            ),
            args=[async_session_maker],
            id="morning_briefing",
        )
    if settings.deadline_warning_enabled:
        scheduler.add_job(
            deadline_warning_scan,
            CronTrigger(hour=DEADLINE_WARNING_HOUR, minute=0, timezone=user_tz),
            args=[async_session_maker],
            id="deadline_warning",
        )
    if settings.key_date_alert_enabled:
        scheduler.add_job(
            key_date_alerts,
            CronTrigger(hour=KEY_DATE_ALERT_HOUR, minute=0, timezone=user_tz),
            args=[async_session_maker],
            id="key_date_alerts",
        )
    scheduler.start()
    logger.info("Scheduler started (notification poll + %d proactive jobs)",
                sum([settings.morning_briefing_enabled,
                     settings.deadline_warning_enabled,
                     settings.key_date_alert_enabled]))
    yield
    # Shutdown
    scheduler.shutdown()
    logger.info("Notification scheduler stopped")


app = FastAPI(
    title="Personal Assistant API",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(people.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(todos.router, prefix="/api")
app.include_router(planning.router, prefix="/api")
