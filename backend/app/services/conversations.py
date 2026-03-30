"""Conversation service layer -- search, retrieval, and logging for interactions.

Every chat exchange is persisted as an Interaction row. This module provides:
  - search_conversations() -- full-text ILIKE search on user messages
  - get_recent_conversations() -- last N interactions (any session)
  - get_session_history() -- interactions for a specific session (for multi-turn context)
  - log_interaction() -- persist a new interaction after the agent loop completes

The orchestrator calls get_session_history() during context assembly to load
prior turns, and calls log_interaction() after generating a response.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Interaction
from app.services.serialization import model_to_dict


async def search_conversations(
    db: AsyncSession,
    query: str,
    date_range: dict[str, str] | None = None,
) -> list[dict]:
    """Search interactions by text content (ILIKE on user_message).

    Args:
        query: Search string
        date_range: Optional dict with 'start' and 'end' ISO datetime strings
    """
    pattern = f"%{query}%"
    stmt = select(Interaction).where(
        Interaction.user_message.ilike(pattern)
    )

    if date_range:
        if "start" in date_range:
            stmt = stmt.where(Interaction.created_at >= datetime.fromisoformat(date_range["start"]))
        if "end" in date_range:
            stmt = stmt.where(Interaction.created_at <= datetime.fromisoformat(date_range["end"]))

    stmt = stmt.order_by(Interaction.created_at.desc()).limit(20)
    result = await db.execute(stmt)
    return [model_to_dict(i) for i in result.scalars().all()]


async def get_recent_conversations(db: AsyncSession, n: int = 5) -> list[dict]:
    """Return the last N interactions, most recent first."""
    result = await db.execute(
        select(Interaction)
        .order_by(Interaction.created_at.desc())
        .limit(n)
    )
    rows = list(result.scalars().all())
    # Return in chronological order (oldest first) for conversation context
    rows.reverse()
    return [model_to_dict(i) for i in rows]


async def get_session_history(
    db: AsyncSession, session_id: uuid.UUID, limit: int = 10
) -> list[dict]:
    """Return interactions for a specific session, chronological order."""
    result = await db.execute(
        select(Interaction)
        .where(Interaction.session_id == session_id)
        .order_by(Interaction.created_at.asc())
        .limit(limit)
    )
    return [model_to_dict(i) for i in result.scalars().all()]


async def log_interaction(
    db: AsyncSession,
    session_id: uuid.UUID,
    channel: str,
    user_message: str,
    parsed_intent: str | None,
    assistant_response: dict[str, Any] | None,
    actions_taken: list[dict[str, Any]] | None,
) -> Interaction:
    """Persist an interaction to the log."""
    interaction = Interaction(
        session_id=session_id,
        channel=channel,
        user_message=user_message,
        parsed_intent=parsed_intent,
        assistant_response=assistant_response,
        actions_taken=actions_taken,
    )
    db.add(interaction)
    await db.flush()
    return interaction
