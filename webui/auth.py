"""
auth.py — single-password gate for the whole app.

The panel controls a live YouTube channel and is exposed publicly through a
Cloudflare Tunnel, so every route except the login page itself is locked behind
a session check. Uses NiceGUI's ``app.storage.user`` (signed session cookie).
"""
from __future__ import annotations

import hmac
import os
import time

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from nicegui import app

from . import config

# Paths reachable without a session. Everything else redirects to /login.
UNRESTRICTED = {"/login", "/robots.txt"}

# Local screenshot/dev escape hatch — NEVER set this in production.
DEV_OPEN = os.environ.get("WEBUI_DEV_OPEN") == "1"


def check_password(candidate: str) -> bool:
    if not config.WEBUI_PASSWORD:
        return False
    # Constant-time compare on bytes: compare_digest() raises TypeError for
    # non-ASCII str arguments, which used to turn into a 500 error.
    return hmac.compare_digest(candidate.encode("utf-8"),
                               config.WEBUI_PASSWORD.encode("utf-8"))


# ── Brute-force protection ───────────────────────────────────────────────────
# The panel is reachable from the internet through the Cloudflare tunnel and
# guarded by one shared password, so failed attempts are rate-limited per
# client and globally (a distributed guesser gets locked out too).
PER_CLIENT_MAX_FAILURES = 5
PER_CLIENT_WINDOW_SECS = 15 * 60
GLOBAL_MAX_FAILURES = 30
GLOBAL_WINDOW_SECS = 60 * 60
LOCKOUT_SECS = 15 * 60

_failures: dict[str, list[float]] = {}
_locked_until: dict[str, float] = {}
_GLOBAL = "*"


def client_id(request) -> str:
    """Client address, using Cloudflare's header when behind the tunnel
    (every request otherwise appears to come from 127.0.0.1)."""
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) or "unknown"
    # cloudflared connects from this machine. Anyone else could put any
    # address in the header and get a fresh lockout counter per attempt.
    if host in ("127.0.0.1", "::1", "localhost"):
        headers = getattr(request, "headers", {}) or {}
        forwarded = headers.get("cf-connecting-ip")
        if forwarded:
            return forwarded.strip()
    return host


def _recent(key: str, window: float, now: float) -> list[float]:
    times = [t for t in _failures.get(key, []) if now - t < window]
    _failures[key] = times
    return times


# Clients that have logged in successfully recently. The global lockout
# stops distributed guessing, but on its own it let anyone lock the owner
# out with 30 bad guesses; clients known to have the password skip it.
TRUSTED_CLIENT_SECS = 30 * 24 * 3600
_trusted: dict[str, float] = {}


def lockout_remaining(client: str, now: float | None = None) -> float:
    """Seconds until this client may try again (0 if not locked)."""
    now = time.time() if now is None else now
    own = _locked_until.get(client, 0.0) - now
    trusted = now - _trusted.get(client, -1e18) < TRUSTED_CLIENT_SECS
    global_wait = 0.0 if trusted else _locked_until.get(_GLOBAL, 0.0) - now
    return max(0.0, own, global_wait)


def record_failure(client: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    for key, window, limit in ((client, PER_CLIENT_WINDOW_SECS, PER_CLIENT_MAX_FAILURES),
                               (_GLOBAL, GLOBAL_WINDOW_SECS, GLOBAL_MAX_FAILURES)):
        times = _recent(key, window, now)
        times.append(now)
        if len(times) >= limit:
            _locked_until[key] = now + LOCKOUT_SECS
            _failures[key] = []


def record_success(client: str, now: float | None = None) -> None:
    _failures.pop(client, None)
    _locked_until.pop(client, None)
    _trusted[client] = time.time() if now is None else now


def _password_fingerprint() -> str:
    """Changes whenever WEBUI_PASSWORD does, so changing the password ends
    every existing session instead of leaving them logged in forever."""
    key = (config.STORAGE_SECRET or "").encode("utf-8")
    return hmac.new(key, (config.WEBUI_PASSWORD or "").encode("utf-8"), "sha256").hexdigest()[:32]


def _session_valid(storage) -> bool:
    return (bool(storage.get("authenticated", False))
            and hmac.compare_digest(str(storage.get("pw_fp", "")), _password_fingerprint()))


def is_authenticated() -> bool:
    try:
        return _session_valid(app.storage.user)
    except Exception:
        return False


def login(remember_path: str | None = None) -> None:
    app.storage.user["authenticated"] = True
    app.storage.user["pw_fp"] = _password_fingerprint()


def logout() -> None:
    app.storage.user["authenticated"] = False


class AuthMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated users to /login for every non-public route."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not DEV_OPEN and not _session_valid(app.storage.user):
            if (
                not path.startswith("/_nicegui")        # framework internals
                and not path.startswith("/static")
                and path not in UNRESTRICTED
            ):
                app.storage.user["referrer_path"] = path
                response = RedirectResponse("/login")
                response.headers["X-Robots-Tag"] = "noindex, nofollow"
                return response
        response = await call_next(request)
        # A private control panel behind a public tunnel: never in search results.
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response


def install(app_) -> None:
    app_.add_middleware(AuthMiddleware)
