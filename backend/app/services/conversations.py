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
from typing import Any

import anthropic
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Interaction, LlmCall
from app.services.serialization import model_to_dict
from app.services.timezone import parse_dt

# Sonnet 4.6 pricing (per million tokens)
_COST_PER_M_INPUT = 3.0
_COST_PER_M_OUTPUT = 15.0  # also covers thinking tokens
_COST_PER_M_CACHE_READ = 0.30
_COST_PER_M_CACHE_WRITE = 3.75


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
            stmt = stmt.where(Interaction.created_at >= parse_dt(date_range["start"]))
        if "end" in date_range:
            stmt = stmt.where(Interaction.created_at <= parse_dt(date_range["end"]))

    stmt = stmt.order_by(Interaction.created_at.desc()).limit(20)
    result = await db.execute(stmt)
    _exclude_heavy = {"message_chain"}
    return [model_to_dict(i, exclude=_exclude_heavy) for i in result.scalars().all()]


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
    _exclude_heavy = {"message_chain"}
    return [model_to_dict(i, exclude=_exclude_heavy) for i in rows]


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
    message_chain: list[dict[str, Any]] | None = None,
) -> Interaction:
    """Persist an interaction to the log."""
    interaction = Interaction(
        session_id=session_id,
        channel=channel,
        user_message=user_message,
        parsed_intent=parsed_intent,
        assistant_response=assistant_response,
        actions_taken=actions_taken,
        message_chain=message_chain,
    )
    db.add(interaction)
    await db.flush()
    return interaction


async def log_llm_call(
    db: AsyncSession,
    session_id: uuid.UUID,
    round_number: int,
    response: anthropic.types.Message,
    tools: dict | None = None,
) -> LlmCall:
    """Persist metadata from a single LLM API call."""
    usage = response.usage
    input_tokens = usage.input_tokens
    output_tokens = usage.output_tokens
    thinking_tokens = getattr(usage, "thinking_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0

    cost = (
        input_tokens * _COST_PER_M_INPUT
        + cache_read * _COST_PER_M_CACHE_READ
        + cache_creation * _COST_PER_M_CACHE_WRITE
        + (output_tokens + thinking_tokens) * _COST_PER_M_OUTPUT
    ) / 1_000_000

    # Serialize the full API response for auditability.
    # Content blocks (thinking text, tool inputs) can be large, so we strip
    # thinking block text but keep everything else (citations, etc.).
    raw = response.model_dump(mode="json")
    for block in raw.get("content", []):
        if block.get("type") == "thinking":
            block["thinking"] = "[redacted]"

    llm_call = LlmCall(
        session_id=session_id,
        round_number=round_number,
        model=response.model,
        stop_reason=response.stop_reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
        estimated_cost_usd=round(cost, 6),
        raw_response=raw,
        tools=tools,
    )
    db.add(llm_call)
    await db.flush()
    return llm_call


async def backfill_llm_call_interaction_id(
    db: AsyncSession,
    session_id: uuid.UUID,
    interaction_id: uuid.UUID,
) -> None:
    """Link orphaned llm_calls rows to their interaction after it's created."""
    await db.execute(
        update(LlmCall)
        .where(LlmCall.session_id == session_id, LlmCall.interaction_id.is_(None))
        .values(interaction_id=interaction_id)
    )
