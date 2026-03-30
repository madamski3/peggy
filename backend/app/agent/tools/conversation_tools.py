"""Conversation tool definitions for the agent.

Gives the agent the ability to search past interactions and retrieve
recent conversation history. Both are READ_ONLY.

Registered tools:
  - search_conversations      -- text search (ILIKE) on past user messages
  - get_recent_conversations  -- last N interactions for general context
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.services import conversations as convo_service


# ── Handlers ──────────────────────────────────────────────────────


async def handle_search_conversations(db: AsyncSession, **kwargs: Any) -> dict:
    results = await convo_service.search_conversations(
        db,
        query=kwargs["query"],
        date_range=kwargs.get("date_range"),
    )
    return {"conversations": results, "count": len(results)}


async def handle_get_recent_conversations(db: AsyncSession, **kwargs: Any) -> dict:
    n = kwargs.get("n", 5)
    results = await convo_service.get_recent_conversations(db, n=n)
    return {"conversations": results, "count": len(results)}


# ── Tool Definitions ─────────────────────────────────────────────

register_tool(ToolDefinition(
    name="search_conversations",
    description="Search past conversation history by text content. Use when the user references something they said before.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search text to find in past messages."},
            "date_range": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "ISO datetime start."},
                    "end": {"type": "string", "description": "ISO datetime end."},
                },
            },
        },
        "required": ["query"],
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_search_conversations,
))

register_tool(ToolDefinition(
    name="get_recent_conversations",
    description="Get the most recent conversation interactions. Use for context about what was recently discussed.",
    input_schema={
        "type": "object",
        "properties": {
            "n": {"type": "integer", "description": "Number of recent interactions to return. Default: 5."},
        },
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_recent_conversations,
))
