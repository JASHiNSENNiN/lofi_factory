"""
auth.py — single-password gate for the whole app.

The panel controls a live YouTube channel and is exposed publicly through a
Cloudflare Tunnel, so every route except the login page itself is locked behind
a session check. Uses NiceGUI's ``app.storage.user`` (signed session cookie).
"""
from __future__ import annotations

import hmac
import os

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from nicegui import app

from . import config

# Paths reachable without a session. Everything else redirects to /login.
UNRESTRICTED = {"/login"}

# Local screenshot/dev escape hatch — NEVER set this in production.
DEV_OPEN = os.environ.get("WEBUI_DEV_OPEN") == "1"


def check_password(candidate: str) -> bool:
    if not config.WEBUI_PASSWORD:
        return False
    # constant-time compare to avoid timing oracles
    return hmac.compare_digest(candidate, config.WEBUI_PASSWORD)


def is_authenticated() -> bool:
    try:
        return bool(app.storage.user.get("authenticated", False))
    except Exception:
        return False


def login(remember_path: str | None = None) -> None:
    app.storage.user["authenticated"] = True


def logout() -> None:
    app.storage.user["authenticated"] = False


class AuthMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated users to /login for every non-public route."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not DEV_OPEN and not app.storage.user.get("authenticated", False):
            if (
                not path.startswith("/_nicegui")        # framework internals
                and not path.startswith("/static")
                and path not in UNRESTRICTED
            ):
                app.storage.user["referrer_path"] = path
                return RedirectResponse("/login")
        return await call_next(request)


def install(app_) -> None:
    app_.add_middleware(AuthMiddleware)
