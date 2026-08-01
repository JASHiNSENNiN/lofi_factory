"""
youtube_oauth.py — in-browser Google OAuth (web redirect flow).

On success it writes ``token.json`` in the exact format ``publish.py`` reads, so
logging in through the web UI is identical to ``python publish.py --auth``.

Because the app is reached through a public Cloudflare Tunnel URL, the loopback
flow used by the CLI won't work — Google must redirect back to the public URL.
That requires a **Web application** OAuth client whose authorized redirect URI is
``<PUBLIC_BASE_URL>/youtube/callback`` (shown in the Settings tab).
"""
from __future__ import annotations

import json
import os

from . import config

# CSRF state for the in-flight authorization (single-user app → module scope is
# fine). Set when login starts, checked in the callback.
_pending_state: str | None = None


def _client_type() -> str | None:
    """Return 'web' / 'installed' / None depending on client_secret.json."""
    if not os.path.exists(config.CLIENT_SECRET):
        return None
    try:
        data = json.load(open(config.CLIENT_SECRET))
    except Exception:
        return None
    for key in ("web", "installed"):
        if key in data:
            return key
    return None


def status() -> dict:
    """Light, no-network connection status for the header/Settings UI."""
    ctype = _client_type()
    # A Desktop ("installed") client is perfectly fine for OAuth — it's what the
    # CLI loopback flow uses. It only can't do an in-browser redirect to a public
    # https URL. So a Web client is ONLY needed if you intend to re-authenticate
    # through the public tunnel (PUBLIC_BASE_URL set). On localhost the Desktop
    # client's loopback redirect works as-is.
    needs_web = ctype == "installed" and bool(config.PUBLIC_BASE_URL)
    info: dict = {
        "connected": False,
        "client_present": os.path.exists(config.CLIENT_SECRET),
        "client_type": ctype,
        "redirect_uri": config.redirect_uri(),
        "channel": None,
        "scopes_ok": False,
        "needs_web_client": needs_web,
    }
    if os.path.exists(config.TOKEN_FILE):
        try:
            tok = json.load(open(config.TOKEN_FILE))
            info["connected"] = bool(tok.get("refresh_token") or tok.get("token"))
            info["scopes_ok"] = set(config.SCOPES).issubset(set(tok.get("scopes", [])))
        except Exception:
            pass
    return info


def channel_title() -> str | None:
    """Fetch the connected channel's title (network call; best-effort)."""
    if not os.path.exists(config.TOKEN_FILE):
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(config.TOKEN_FILE, config.SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _write_token(creds)
        yt = build("youtube", "v3", credentials=creds)
        resp = yt.channels().list(part="snippet", mine=True).execute()
        items = resp.get("items") or []
        return items[0]["snippet"]["title"] if items else None
    except Exception:
        return None


def _flow():
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(
        config.CLIENT_SECRET, scopes=config.SCOPES,
    )
    flow.redirect_uri = config.redirect_uri()
    return flow


def authorization_url() -> str:
    """Build the Google consent URL and stash the CSRF state."""
    global _pending_state
    flow = _flow()
    url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    _pending_state = state
    return url


def handle_callback(code: str, state: str | None) -> None:
    """Exchange the auth code for tokens and persist token.json."""
    global _pending_state
    if _pending_state and state and state != _pending_state:
        raise ValueError("OAuth state mismatch — please retry the login.")
    flow = _flow()
    # Pass the code directly (not the full redirect URL): the app sees plain HTTP
    # internally behind Cloudflare's TLS termination, so an authorization_response
    # URL would trip oauthlib's https check. The code exchange itself is https.
    flow.fetch_token(code=code)
    _write_token(flow.credentials)
    _pending_state = None


def _write_token(creds) -> None:
    fd = os.open(config.TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(creds.to_json())


def disconnect() -> None:
    """Remove the stored token (sign out)."""
    try:
        os.remove(config.TOKEN_FILE)
    except FileNotFoundError:
        pass
