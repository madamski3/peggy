"""Gmail tool definitions for the agent.

All tools are READ_ONLY — the assistant never modifies or sends emails.

Registered tools:
  - get_recent_emails  (READ_ONLY) -- list recent inbox emails
  - get_email_detail   (READ_ONLY) -- get full content of a specific email
  - search_emails      (READ_ONLY) -- search emails by query
"""

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, tool
from app.services import gmail


class GetRecentEmailsInput(BaseModel):
    max_results: int = 10
    query: str | None = Field(
        None, description="Gmail search query (e.g. 'is:unread', 'from:amazon')."
    )


class GetEmailDetailInput(BaseModel):
    message_id: str


class SearchEmailsInput(BaseModel):
    query: str = Field(..., description="Gmail search query.")
    max_results: int = 10


@tool(
    tier=ActionTier.READ_ONLY,
    category="email",
    embedding_text=(
        "email: get_recent_emails — check, show, list recent emails, inbox, messages. "
        "Any new emails? Check my inbox. What emails did I get today?"
    ),
)
async def get_recent_emails(db: AsyncSession, input: GetRecentEmailsInput) -> dict:
    """List recent emails from the inbox."""
    results = await gmail.list_emails(
        db, max_results=input.max_results, query=input.query,
    )
    if isinstance(results, dict) and "error" in results:
        return results
    return {"emails": results, "count": len(results)}


@tool(
    tier=ActionTier.READ_ONLY,
    category="email",
    embedding_text=(
        "email: get_email_detail — read, open, view full email content, message body. "
        "Show me that email. What did the email say? Read the message from John."
    ),
)
async def get_email_detail(db: AsyncSession, input: GetEmailDetailInput) -> dict:
    """Get the full content of an email by message ID."""
    return await gmail.get_email_detail(db, input.message_id)


@tool(
    tier=ActionTier.READ_ONLY,
    category="email",
    embedding_text=(
        "email: search_emails — search, find emails, look up messages from someone, "
        "about a topic. Find emails from Amazon. Search for the shipping confirmation."
    ),
)
async def search_emails(db: AsyncSession, input: SearchEmailsInput) -> dict:
    """Search emails using Gmail search syntax."""
    results = await gmail.search_emails(
        db, query=input.query, max_results=input.max_results,
    )
    if isinstance(results, dict) and "error" in results:
        return results
    return {"emails": results, "count": len(results)}
