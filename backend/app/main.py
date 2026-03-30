"""FastAPI application entry point.

Creates the app, configures CORS (allow all origins for Tailscale access),
and registers all routers under the /api prefix. Uvicorn runs this as
app.main:app.

Also starts APScheduler on startup to poll for due notifications and
deliver them via ntfy.
"""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import async_session_maker
from app.routers import auth, chat, health, people, profile, tasks, todos
from app.services.notifications import process_due_notifications

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    scheduler.add_job(
        process_due_notifications,
        "interval",
        seconds=settings.notification_poll_seconds,
        args=[async_session_maker],
        id="notification_poller",
    )
    scheduler.start()
    logger.info("Notification scheduler started (poll every %ds)", settings.notification_poll_seconds)
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
app.include_router(tasks.router, prefix="/api")
