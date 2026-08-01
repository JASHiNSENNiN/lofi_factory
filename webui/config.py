"""
config.py — web UI configuration, paths, and pipeline option catalogs.

All values are read from the environment (see .env) with safe defaults so the
app boots even before the user has filled everything in.
"""
from __future__ import annotations

import os
import secrets

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ── Paths (kept in sync with publish.py so a web login == a CLI login) ────────
CLIENT_SECRET = os.path.join(ROOT, "client_secret.json")
TOKEN_FILE = os.path.join(ROOT, "token.json")
COOKIES_FILE = os.path.join(ROOT, "cookies.txt")
UPLOAD_LOG = os.path.join(ROOT, "upload_log.json")
OUTPUT_DIR = os.path.join(ROOT, "output")
ASSETS_DIR = os.path.join(ROOT, "assets")
PYTHON = os.path.join(ROOT, "venv", "bin", "python")
if not os.path.exists(PYTHON):  # fall back to whatever runs us
    import sys

    PYTHON = sys.executable

# Same scopes publish.py uses — token.json must satisfy both.
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# ── App auth ──────────────────────────────────────────────────────────────────
# The app is exposed publicly via Cloudflare Tunnel, so a password is mandatory.
WEBUI_PASSWORD = _env("WEBUI_PASSWORD")
# storage_secret signs session cookies; generated per-boot if unset (logs out on
# restart). Set WEBUI_SECRET in .env for stable sessions.
STORAGE_SECRET = _env("WEBUI_SECRET") or secrets.token_urlsafe(32)

# ── OAuth (web redirect flow) ─────────────────────────────────────────────────
# Public origin the user reaches through the Cloudflare Tunnel, e.g.
# https://lofi.example.com — the Google redirect URI is derived from it.
PUBLIC_BASE_URL = _env("PUBLIC_BASE_URL").rstrip("/")
OAUTH_CALLBACK_PATH = "/youtube/callback"


def redirect_uri() -> str:
    base = PUBLIC_BASE_URL or f"http://localhost:{HTTP_PORT}"
    return f"{base}{OAUTH_CALLBACK_PATH}"


# ── Server ────────────────────────────────────────────────────────────────────
HTTP_HOST = _env("WEBUI_HOST", "127.0.0.1")
HTTP_PORT = int(_env("WEBUI_PORT", "8080") or "8080")

# ── Pipeline option catalogs (mirror run.py / publish.py) ─────────────────────
THEMES = [
    "random", "cozy_rain", "midnight_cafe", "purple_dusk", "amber_night",
    "winter_snow", "autumn_study", "spring_dawn", "neon_tokyo", "summer_lofi",
    "blue_hour", "forest_rain", "sakura_night", "vaporwave", "lofi_house",
    "lofi_classical", "bedroom_pop", "lofi_rnb",
]
DURATIONS = ["1 hour", "2 hours", "3 hours", "all night"]
PRIVACY = ["public", "unlisted", "private"]
STREAM_QUALITY = ["720p15", "720p", "1080p", "1080p60"]


def is_configured() -> bool:
    """True once a password is set — otherwise we run in setup-warning mode."""
    return bool(WEBUI_PASSWORD)
