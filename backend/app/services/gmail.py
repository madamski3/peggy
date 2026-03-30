"""Gmail API integration (read-only).

Wraps the synchronous Google API client in asyncio.to_thread() for
async compatibility, following the same pattern as google_calendar.py.

Reuses OAuth credentials from the google_calendar module (same credential
row in the database — both services share a single Google OAuth token).

The assistant never sends email — all tools are READ_ONLY.
"""

import asyncio
import base64
import logging
from email.utils import parseaddr

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.google_calendar import get_google_credentials, save_google_credentials

logger = logging.getLogger(__name__)


def _build_service(creds: Credentials):
    """Build a Gmail API service object (synchronous)."""
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _get_header(headers: list[dict], name: str) -> str:
    """Extract a header value from Gmail message headers."""
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _short_sender(from_header: str) -> str:
    """Extract a short display name from a From header."""
    name, addr = parseaddr(from_header)
    return name if name else addr


def _extract_body_text(payload: dict) -> str:
    """Extract plain text body from a Gmail message payload.

    Handles both simple messages (body directly on payload) and
    multipart messages (body in nested parts).
    """
    # Simple message with body directly
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    # Multipart — search for text/plain part
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        # Nested multipart
        if part.get("parts"):
            result = _extract_body_text(part)
            if result:
                return result

    return ""


def _normalize_email_summary(msg: dict) -> dict:
    """Convert a Gmail message (metadata format) to a clean summary dict."""
    headers = msg.get("payload", {}).get("headers", [])
    label_ids = msg.get("labelIds", [])

    from_header = _get_header(headers, "From")

    return {
        "id": msg.get("id", ""),
        "thread_id": msg.get("threadId", ""),
        "subject": _get_header(headers, "Subject") or "(No subject)",
        "from": from_header,
        "from_short": _short_sender(from_header),
        "date": _get_header(headers, "Date"),
        "snippet": msg.get("snippet", ""),
        "is_unread": "UNREAD" in label_ids,
        "labels": label_ids,
    }


# ── Public API ─────────────────────────────────────────────────


async def list_emails(
    db: AsyncSession,
    max_results: int = 10,
    query: str | None = None,
    label: str = "INBOX",
) -> list[dict] | dict:
    """List recent emails from the user's inbox.

    Args:
        db: Async database session.
        max_results: Maximum number of emails to return.
        query: Optional Gmail search query (same syntax as Gmail search bar).
        label: Label to filter by (default: INBOX).

    Returns:
        List of email summary dicts, or error dict if not connected.
    """
    creds = await get_google_credentials(db)
    if not creds:
        return {"error": "Gmail not connected. Visit /api/auth/google to connect."}

    def _fetch():
        service = _build_service(creds)

        # List message IDs
        list_kwargs = {
            "userId": "me",
            "maxResults": max_results,
            "labelIds": [label],
        }
        if query:
            list_kwargs["q"] = query

        result = service.users().messages().list(**list_kwargs).execute()
        message_ids = result.get("messages", [])

        # Fetch metadata for each message
        emails = []
        for msg_ref in message_ids:
            msg = service.users().messages().get(
                userId="me",
                id=msg_ref["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            emails.append(_normalize_email_summary(msg))

        return emails

    emails = await asyncio.to_thread(_fetch)

    if creds.token:
        await save_google_credentials(db, creds)

    return emails


async def get_email_detail(db: AsyncSession, message_id: str) -> dict:
    """Get the full content of a specific email.

    Args:
        db: Async database session.
        message_id: Gmail message ID.

    Returns:
        Dict with subject, from, to, date, body (plain text), and snippet.
    """
    creds = await get_google_credentials(db)
    if not creds:
        return {"error": "Gmail not connected. Visit /api/auth/google to connect."}

    def _fetch():
        service = _build_service(creds)
        return service.users().messages().get(
            userId="me",
            id=message_id,
            format="full",
        ).execute()

    msg = await asyncio.to_thread(_fetch)

    if creds.token:
        await save_google_credentials(db, creds)

    headers = msg.get("payload", {}).get("headers", [])
    body = _extract_body_text(msg.get("payload", {}))

    # Truncate very long emails to avoid blowing up the LLM context
    if len(body) > 3000:
        body = body[:3000] + "\n\n[... truncated]"

    return {
        "id": msg.get("id", ""),
        "thread_id": msg.get("threadId", ""),
        "subject": _get_header(headers, "Subject") or "(No subject)",
        "from": _get_header(headers, "From"),
        "to": _get_header(headers, "To"),
        "date": _get_header(headers, "Date"),
        "body": body,
        "snippet": msg.get("snippet", ""),
        "labels": msg.get("labelIds", []),
    }


async def search_emails(
    db: AsyncSession,
    query: str,
    max_results: int = 10,
) -> list[dict] | dict:
    """Search emails using Gmail's search syntax.

    Args:
        db: Async database session.
        query: Gmail search query (e.g. "from:amazon subject:shipping").
        max_results: Maximum number of results.

    Returns:
        List of email summary dicts matching the query.
    """
    return await list_emails(db, max_results=max_results, query=query)
