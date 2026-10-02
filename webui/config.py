"""
config.py — web UI configuration, paths, and pipeline option catalogs.

All values are read from the environment (see .env) with safe defaults so the
app boots even before the user has filled everything in.
"""
from __future__ import annotations

import os
import secrets

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV_FILE = os.path.join(ROOT, ".env")

# ── Paths (kept in sync with publish.py so a web login == a CLI login) ────────
CLIENT_SECRET = os.path.join(ROOT, "client_secret.json")
# Separate OAuth client for the device-code flow (Settings -> "Connect via
# device code"). Google requires a client of type "TVs and Limited Input
# devices" for this grant -- a "Web application" client (CLIENT_SECRET above)
# is rejected by the device/code endpoint, hence the second file rather than
# reusing the same one.
CLIENT_SECRET_DEVICE = os.path.join(ROOT, "client_secret_device.json")
TOKEN_FILE = os.path.join(ROOT, "token.json")
# Separate token for the opt-in "Connect monetary analytics" flow (Settings)
# -- kept out of token.json entirely so the extra yt-analytics-monetary.readonly
# scope it carries is never silently required just to read token.json for
# ordinary uploads/analytics. See MONETARY_SCOPES below and youtube_oauth.py's
# monetary_* functions.
TOKEN_FILE_MONETARY = os.path.join(ROOT, "token_monetary.json")
UPLOAD_LOG = os.path.join(ROOT, "upload_log.json")
OUTPUT_DIR = os.path.join(ROOT, "output")
ASSETS_DIR = os.path.join(ROOT, "assets")
MUSIC_DIR = os.path.join(ROOT, "music")
VISUALS_DIR = os.path.join(ROOT, "visuals")
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

# Opt-in only (Settings -> "Connect monetary analytics"). Mirrors
# scripts/upload_youtube.py's MONETARY_SCOPES -- see that module for why this
# is a separate constant rather than folded into SCOPES. Used only by
# youtube_oauth.py's monetary_* functions, which write to TOKEN_FILE_MONETARY,
# never TOKEN_FILE.
MONETARY_SCOPES = SCOPES + [
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
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
# Separate callback path for the opt-in monetary-analytics consent (must be
# registered as its own "Authorized redirect URI" in Google Cloud Console
# alongside the main one -- shown in Settings next to the Connect button).
OAUTH_CALLBACK_PATH_MONETARY = "/youtube/monetary/callback"


def redirect_uri() -> str:
    base = PUBLIC_BASE_URL or f"http://localhost:{HTTP_PORT}"
    return f"{base}{OAUTH_CALLBACK_PATH}"


def redirect_uri_monetary() -> str:
    base = PUBLIC_BASE_URL or f"http://localhost:{HTTP_PORT}"
    return f"{base}{OAUTH_CALLBACK_PATH_MONETARY}"


# ── Server ────────────────────────────────────────────────────────────────────
HTTP_HOST = _env("WEBUI_HOST", "127.0.0.1")
HTTP_PORT = int(_env("WEBUI_PORT", "8080") or "8080")

# ── TLS (optional -- e.g. a Tailscale MagicDNS cert via `tailscale cert`) ──────
# Only used if both files exist; otherwise the app serves plain HTTP as before
# (the right choice behind a Cloudflare Tunnel or SSH port-forward, which
# terminate TLS themselves). Needed for Tailscale-only deployments because
# Google's OAuth "Web application" client type requires both a real domain
# (not a bare IP) *and* HTTPS for any non-localhost redirect URI.
SSL_CERTFILE = _env("WEBUI_SSL_CERTFILE")
SSL_KEYFILE = _env("WEBUI_SSL_KEYFILE")

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


def subgenre_choices() -> list[str]:
    """Sub-genre keys from config/genres/*.yaml, for the render dialogs' picker.

    Lazy-imported here (not a module-level constant) so this module stays
    import-light -- webui.config is imported at webui startup, well before
    any dialog renders, and scripts.genre_presets.load_all() (glob + YAML
    parse, no soundfont filesystem scan) should only be paid for when a
    dialog actually needs the list. Mirrors run.py's same lazy-import
    pattern for its --sub-genre choices.
    """
    from scripts.genre_presets import load_all
    return sorted(load_all().keys())


def is_configured() -> bool:
    """True once a password is set — otherwise we run in setup-warning mode."""
    return bool(WEBUI_PASSWORD)


# ── Render defaults (persisted to .env, read fresh each render dialog open) ───
DEFAULT_THEME = _env("DEFAULT_THEME", "random")
DEFAULT_DURATION = _env("DEFAULT_DURATION", "2 hours")
DEFAULT_PRIVACY = _env("DEFAULT_PRIVACY", "public")


# ── .env editing (Settings tab) ─────────────────────────────────────────────
# Changes here take effect on next `lofi-webui` restart -- the process only
# reads .env once at startup (see webui.py's load_dotenv() call). The UI makes
# that explicit rather than pretending a live reload happens.
def read_env_file() -> dict[str, str]:
    """Parse .env into {KEY: value}, ignoring comments/blank lines."""
    values: dict[str, str] = {}
    if not os.path.exists(ENV_FILE):
        return values
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip()
    return values


def write_env_value(key: str, value: str) -> None:
    """Update (or append) KEY=value in .env, preserving other lines/comments."""
    if "\n" in value or "\r" in value:
        # A newline in the value would inject extra, uncontrolled lines into .env
        # (e.g. a pasted multi-line value could silently add unrelated KEY=VALUE
        # entries). .env doesn't support multi-line values without quoting we
        # don't implement, so reject rather than corrupt.
        raise ValueError(f"{key}: value can't contain a newline")
    lines: list[str] = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            lines = f.readlines()
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == key or stripped.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}\n")
    with open(ENV_FILE, "w") as f:
        f.writelines(lines)
    os.chmod(ENV_FILE, 0o600)
