"""Proactive agent invocation helper.

Provides a way to run the agent loop outside of an HTTP request context,
used by scheduled jobs (morning briefing, deadline warnings, etc.).

The key difference from a normal chat request: there is no real user message
or session. Instead, a synthetic system message is passed to the agent loop,
and the response is used for push notification content.
"""

import logging

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.orchestrator import run_agent_loop

logger = logging.getLogger(__name__)


async def invoke_agent_proactively(
    session_factory: async_sessionmaker,
    synthetic_message: str,
) -> dict | None:
    """Run the agent loop with a synthetic message and return the response.

    Creates its own DB session since this runs outside FastAPI's request
    lifecycle (called by APScheduler). Returns the ChatResponse as a dict,
    or None if the invocation fails.
    """
    try:
        async with session_factory() as db:
            response = await run_agent_loop(
                user_message=synthetic_message,
                session_id=None,
                db=db,
                channel="proactive",
            )
            return response.model_dump(mode="json")
    except Exception:
        logger.exception("Proactive agent invocation failed for: %s", synthetic_message[:80])
        return None
