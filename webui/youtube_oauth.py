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


# ── Monetary analytics (OPT-IN, separate scope + separate token file) ─────────
# YouTube Analytics revenue/RPM/CPM metrics require the
# yt-analytics-monetary.readonly scope, which config.SCOPES / the main login
# above deliberately do NOT request (see scripts/upload_youtube.py's
# MONETARY_SCOPES docstring). Everything below is a second, clearly-labeled
# consent flow the user must explicitly start from Settings -- it never runs
# as a side effect of the normal "Connect YouTube" button, and its token is
# written to a completely separate file (config.TOKEN_FILE_MONETARY) so it
# can be disconnected independently and never silently upgrades token.json's
# scopes.
#
# This reuses the exact same web-redirect Flow mechanics as the main login
# above (google-auth-oauthlib's Flow.from_client_secrets_file), just pointed
# at MONETARY_SCOPES and a second callback path -- incremental-auth style
# (Google's server treats a fresh consent request for a superset of scopes as
# a normal new grant; there's no special "incremental" API call needed, only
# a second explicit authorization_url()/consent round-trip, which is exactly
# what a truly opt-in second flow should look like anyway).
_pending_state_monetary: str | None = None


def monetary_status() -> dict:
    """Light, no-network connection status for the Settings 'Revenue & RPM' card."""
    info: dict = {
        "connected": False,
        "client_present": os.path.exists(config.CLIENT_SECRET),
        "redirect_uri": config.redirect_uri_monetary(),
        "scopes_ok": False,
    }
    if os.path.exists(config.TOKEN_FILE_MONETARY):
        try:
            tok = json.load(open(config.TOKEN_FILE_MONETARY))
            info["connected"] = bool(tok.get("refresh_token") or tok.get("token"))
            info["scopes_ok"] = set(config.MONETARY_SCOPES).issubset(set(tok.get("scopes", [])))
        except Exception:
            pass
    return info


def _monetary_flow():
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(
        config.CLIENT_SECRET, scopes=config.MONETARY_SCOPES,
    )
    flow.redirect_uri = config.redirect_uri_monetary()
    return flow


def monetary_authorization_url() -> str:
    """Build the Google consent URL for the monetary-scope opt-in and stash CSRF state."""
    global _pending_state_monetary
    flow = _monetary_flow()
    url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    _pending_state_monetary = state
    return url


def monetary_handle_callback(code: str, state: str | None) -> None:
    """Exchange the auth code for tokens and persist token_monetary.json (never token.json)."""
    global _pending_state_monetary
    if _pending_state_monetary and state and state != _pending_state_monetary:
        raise ValueError("OAuth state mismatch — please retry the login.")
    flow = _monetary_flow()
    flow.fetch_token(code=code)
    _write_token_monetary(flow.credentials)
    _pending_state_monetary = None


def _write_token_monetary(creds) -> None:
    fd = os.open(config.TOKEN_FILE_MONETARY, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(creds.to_json())


def monetary_disconnect() -> None:
    """Remove the stored monetary-scope token (sign out of revenue tracking only)."""
    try:
        os.remove(config.TOKEN_FILE_MONETARY)
    except FileNotFoundError:
        pass


# ── Device-code flow (no redirect_uri at all) ─────────────────────────────────
# For deployments where the redirect-based flow above can't work reliably --
# e.g. Tailscale-only with client-side MagicDNS problems, or any network where
# the browser doing the consent can't reach back to this box's exact public
# hostname. Google's device authorization grant (RFC 8628) sidesteps the whole
# redirect_uri requirement: the user visits a short, always-reachable Google
# URL (verification_url, normally google.com/device) on ANY device/network and
# types a short code -- no connection to this server needed for that step at
# all. This server just polls Google until the user finishes.
#
# Requires a *separate* OAuth client of type "TVs and Limited Input devices"
# in Google Cloud Console -- the existing Web application client is rejected
# by the device/code endpoint (confirmed by Google's own client-type
# restrictions on this grant).
_DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
_DEVICE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"


def device_client_status() -> dict:
    """Presence/type check for client_secret_device.json (Settings UI)."""
    present = os.path.exists(config.CLIENT_SECRET_DEVICE)
    ctype = None
    if present:
        try:
            data = json.load(open(config.CLIENT_SECRET_DEVICE))
            for key in ("installed", "web"):
                if key in data:
                    ctype = key
                    break
        except Exception:
            pass
    return {"present": present, "client_type": ctype}


def _device_client_id_secret() -> tuple[str, str]:
    data = json.load(open(config.CLIENT_SECRET_DEVICE))
    section = data.get("installed") or data.get("web")
    if not section:
        raise ValueError("client_secret_device.json has neither 'installed' nor 'web' key")
    return section["client_id"], section["client_secret"]


def device_flow_start() -> dict:
    """
    Kick off the device authorization grant. Returns
    {device_code, user_code, verification_url, interval, expires_in} for the
    UI to display and start polling with device_flow_poll().
    """
    import requests

    if not os.path.exists(config.CLIENT_SECRET_DEVICE):
        raise FileNotFoundError(
            "client_secret_device.json not uploaded -- create a 'TVs and Limited "
            "Input devices' OAuth client in Google Cloud Console and upload it "
            "in Settings first.")
    client_id, _secret = _device_client_id_secret()
    resp = requests.post(_DEVICE_CODE_URL, data={
        "client_id": client_id,
        "scope": " ".join(config.SCOPES),
    }, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    return {
        "device_code": body["device_code"],
        "user_code": body["user_code"],
        # Google's field is usually verification_url, occasionally
        # verification_uri depending on API version -- accept either.
        "verification_url": body.get("verification_url") or body.get("verification_uri"),
        "interval": body.get("interval", 5),
        "expires_in": body.get("expires_in", 1800),
    }


class DeviceFlowPending(Exception):
    """Raised by device_flow_poll while the user hasn't finished consenting yet."""


def device_flow_poll(device_code: str) -> None:
    """
    Check once whether the user has completed the device-code consent. Raises
    DeviceFlowPending if not done yet (caller should retry after `interval`
    seconds), or any other Exception on a real failure (expired, denied).
    On success, writes token.json exactly like the redirect flow does.
    """
    import requests

    client_id, client_secret = _device_client_id_secret()
    resp = requests.post(_DEVICE_TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "device_code": device_code,
        "grant_type": _DEVICE_GRANT_TYPE,
    }, timeout=15)
    body = resp.json()
    if resp.status_code == 200:
        from google.oauth2.credentials import Credentials

        creds = Credentials(
            token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            token_uri=_DEVICE_TOKEN_URL,
            client_id=client_id,
            client_secret=client_secret,
            scopes=config.SCOPES,
        )
        _write_token(creds)
        return
    error = body.get("error", "unknown_error")
    if error in ("authorization_pending", "slow_down"):
        raise DeviceFlowPending(error)
    raise RuntimeError(f"Device auth failed: {error} — {body.get('error_description', '')}")
