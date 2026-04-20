"""Conversation tool definitions for the agent.

Gives the agent the ability to search past interactions and retrieve
recent conversation history. Both are READ_ONLY.

Registered tools:
  - search_conversations      -- text search (ILIKE) on past user messages
  - get_recent_conversations  -- last N interactions for general context
"""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, tool
from app.services import conversations as convo_service


class DateRange(BaseModel):
    start: str | None = None
    end: str | None = None


class SearchConversationsInput(BaseModel):
    query: str
    date_range: DateRange | None = None


class GetRecentConversationsInput(BaseModel):
    n: int = 5


@tool(
    tier=ActionTier.READ_ONLY,
    category="conversation",
    embedding_text=(
        "conversation: search_conversations — search, find past conversations, "
        "what did we talk about, previous chats. Did I ask about X before? "
        "What did you tell me about Y?"
    ),
)
async def search_conversations(db: AsyncSession, input: SearchConversationsInput) -> dict:
    """Search past conversations by text content."""
    date_range = input.date_range.model_dump(exclude_none=True) if input.date_range else None
    results = await convo_service.search_conversations(
        db, query=input.query, date_range=date_range,
    )
    return {"conversations": results, "count": len(results)}


@tool(
    tier=ActionTier.READ_ONLY,
    category="conversation",
    embedding_text=(
        "conversation: get_recent_conversations — recent chats, conversation history, "
        "what did we discuss recently. Show my recent conversations."
    ),
)
async def get_recent_conversations(db: AsyncSession, input: GetRecentConversationsInput) -> dict:
    """Get the most recent conversation interactions."""
    results = await convo_service.get_recent_conversations(db, n=input.n)
    return {"conversations": results, "count": len(results)}
