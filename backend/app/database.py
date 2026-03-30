"""Async SQLAlchemy database engine and session factory.

Creates a single async engine from the DATABASE_URL config setting. The
get_db() dependency yields a session per request (used by all routers).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Alias for use by background jobs (APScheduler) that create their own sessions
async_session_maker = async_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
