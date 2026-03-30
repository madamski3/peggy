"""OAuth authentication routes for external service integrations.

Implements the Google Calendar OAuth 2.0 flow:
  1. GET /api/auth/google       -- redirects to Google consent screen
  2. GET /api/auth/google/callback -- receives the authorization code,
     exchanges it for tokens, stores them in the credentials table
  3. GET /api/auth/google/status -- checks if credentials exist (used by frontend)

PKCE code_verifier is packed into the state query parameter so it survives
the redirect round-trip (acceptable for a single-user app). Once tokens are
stored, the google_calendar service module handles refresh automatically.
"""

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from google_auth_oauthlib.flow import Flow
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.google_calendar import (
    SCOPES,
    is_connected,
    save_google_credentials,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_client_config() -> dict:
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }


@router.get("/google")
async def google_auth_start():
    """Redirect the user to Google's consent screen."""
    if not settings.google_client_id or not settings.google_client_secret:
        return HTMLResponse(
            "<h3>Google Calendar not configured</h3>"
            "<p>Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your .env file.</p>",
            status_code=500,
        )

    flow = Flow.from_client_config(
        _build_client_config(),
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    # Encode the code_verifier into the state so we can recover it in the callback.
    # The google-auth library auto-generates a PKCE code_verifier and attaches it
    # to the flow object, but that object is lost between requests.
    code_verifier = flow.code_verifier
    if code_verifier:
        # Replace the state parameter in the URL with one that includes the verifier
        packed = json.dumps({"state": state, "cv": code_verifier})
        import urllib.parse

        parsed = urllib.parse.urlparse(auth_url)
        params = urllib.parse.parse_qs(parsed.query)
        params["state"] = [packed]
        new_query = urllib.parse.urlencode(params, doseq=True)
        auth_url = urllib.parse.urlunparse(parsed._replace(query=new_query))

    return RedirectResponse(auth_url)


@router.get("/google/callback")
async def google_auth_callback(
    code: str = Query(...),
    state: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """Receive the authorization code from Google and exchange it for tokens."""
    flow = Flow.from_client_config(
        _build_client_config(),
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )

    # Recover code_verifier from state if present
    code_verifier = None
    try:
        packed = json.loads(state)
        code_verifier = packed.get("cv")
    except (json.JSONDecodeError, TypeError):
        pass

    flow.fetch_token(code=code, code_verifier=code_verifier)
    creds = flow.credentials

    await save_google_credentials(db, creds)
    await db.commit()

    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head><title>Connected</title></head>
    <body style="font-family: system-ui; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f9fafb;">
        <div style="text-align: center;">
            <div style="font-size: 3rem; margin-bottom: 0.5rem;">&#9989;</div>
            <h2 style="color: #16a34a; margin: 0 0 0.5rem;">Google Calendar connected!</h2>
            <p style="color: #6b7280;">You can close this tab and return to the assistant.</p>
        </div>
    </body>
    </html>
    """)


@router.get("/google/status")
async def google_auth_status(db: AsyncSession = Depends(get_db)):
    """Check if Google Calendar is connected."""
    connected = await is_connected(db)
    return {"connected": connected}
