"""Gmail tool definitions for the agent.

All tools are READ_ONLY — the assistant never modifies or sends emails.

Registered tools:
  - get_recent_emails  (READ_ONLY) -- list recent inbox emails
  - get_email_detail   (READ_ONLY) -- get full content of a specific email
  - search_emails      (READ_ONLY) -- search emails by query
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.services import gmail


async def handle_get_recent_emails(db: AsyncSession, **kwargs: Any) -> dict:
    results = await gmail.list_emails(
        db,
        max_results=kwargs.get("max_results", 10),
        query=kwargs.get("query"),
    )
    if isinstance(results, dict) and "error" in results:
        return results
    return {"emails": results, "count": len(results)}


async def handle_get_email_detail(db: AsyncSession, **kwargs: Any) -> dict:
    return await gmail.get_email_detail(db, kwargs["message_id"])


async def handle_search_emails(db: AsyncSession, **kwargs: Any) -> dict:
    results = await gmail.search_emails(
        db,
        query=kwargs["query"],
        max_results=kwargs.get("max_results", 10),
    )
    if isinstance(results, dict) and "error" in results:
        return results
    return {"emails": results, "count": len(results)}


register_tool(ToolDefinition(
    name="get_recent_emails",
    description="List recent emails from the inbox.",
    embedding_text=(
        "email: get_recent_emails — check, show, list recent emails, inbox, messages. "
        "Any new emails? Check my inbox. What emails did I get today?"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "max_results": {"type": "integer"},
            "query": {"type": "string", "description": "Gmail search query (e.g. 'is:unread', 'from:amazon')."},
        },
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_recent_emails,
    category="email",
))


register_tool(ToolDefinition(
    name="get_email_detail",
    description="Get the full content of an email by message ID.",
    embedding_text=(
        "email: get_email_detail — read, open, view full email content, message body. "
        "Show me that email. What did the email say? Read the message from John."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "message_id": {"type": "string"},
        },
        "required": ["message_id"],
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_email_detail,
    category="email",
))


register_tool(ToolDefinition(
    name="search_emails",
    description="Search emails using Gmail search syntax.",
    embedding_text=(
        "email: search_emails — search, find emails, look up messages from someone, "
        "about a topic. Find emails from Amazon. Search for the shipping confirmation."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Gmail search query."},
            "max_results": {"type": "integer"},
        },
        "required": ["query"],
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_search_emails,
    category="email",
))
