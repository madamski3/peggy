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
    description=(
        "List recent emails from the user's inbox. Returns subject, sender, "
        "date, snippet, and unread status. Use this to check what's new in "
        "the user's inbox or to find a specific recent email."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "max_results": {
                "type": "integer",
                "description": "Maximum number of emails to return (default: 10)",
            },
            "query": {
                "type": "string",
                "description": "Optional Gmail search query to filter results (e.g. 'is:unread', 'from:amazon')",
            },
        },
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_recent_emails,
    category="email",
))


register_tool(ToolDefinition(
    name="get_email_detail",
    description=(
        "Get the full content of a specific email by its message ID. "
        "Returns subject, from, to, date, and the plain text body. "
        "Use this after listing emails to read one in full."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "message_id": {
                "type": "string",
                "description": "The Gmail message ID (from get_recent_emails or search_emails)",
            },
        },
        "required": ["message_id"],
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_email_detail,
    category="email",
))


register_tool(ToolDefinition(
    name="search_emails",
    description=(
        "Search the user's emails using Gmail search syntax. "
        "Supports queries like 'from:amazon subject:shipping', "
        "'is:unread', 'after:2026/03/01', 'has:attachment', etc."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Gmail search query (same syntax as the Gmail search bar)",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (default: 10)",
            },
        },
        "required": ["query"],
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_search_emails,
    category="email",
))
