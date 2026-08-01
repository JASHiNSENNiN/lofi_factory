"""
ytdlp_util.py — shared yt-dlp option builders + cookie handling.

Why this exists
---------------
YouTube bot-gates datacenter/server IPs ("Sign in to confirm you're not a bot").
There is no single workaround that fits every call site, so we split by need:

* Metadata-only searches (trending scrape) use ``flat_search_opts()`` which sets
  ``extract_flat=True``. Flat extraction never touches each video's player API,
  so it sidesteps the bot gate entirely — works on a bare server, no cookies.

* Real downloads (audio cover) must hit the player API, which IS gated on server
  IPs. ``download_opts()`` therefore wires in modern player clients and an
  optional cookies file. Drop a Netscape-format ``cookies.txt`` next to the repo
  (or point ``YTDLP_COOKIES`` at one — the web UI uploads it there) and downloads
  start working again.

Cookie file resolution order:
  1. $YTDLP_COOKIES (explicit path)
  2. <repo root>/cookies.txt
"""
from __future__ import annotations

import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_COOKIES = os.path.join(ROOT, "cookies.txt")

# Player clients that are most resilient to YouTube's 2026 bot gate. 'tv' and the
# safari/mobile web clients avoid the heaviest PO-token enforcement of the
# default desktop web client.
_PLAYER_CLIENTS = ["tv", "web_safari", "mweb", "android"]

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def cookies_path() -> str | None:
    """Return a usable cookies.txt path, or None if none is configured."""
    explicit = os.environ.get("YTDLP_COOKIES", "").strip()
    if explicit and os.path.isfile(explicit):
        return explicit
    if os.path.isfile(DEFAULT_COOKIES):
        return DEFAULT_COOKIES
    return None


def have_cookies() -> bool:
    return cookies_path() is not None


def _apply_common(opts: dict) -> dict:
    """Inject player clients, UA and cookies into a base opts dict (in place)."""
    opts.setdefault("extractor_args", {}).setdefault(
        "youtube", {}
    )["player_client"] = _PLAYER_CLIENTS
    opts.setdefault("http_headers", {})["User-Agent"] = _UA
    cookies = cookies_path()
    if cookies:
        opts["cookiefile"] = cookies
    return opts


def flat_search_opts(**extra) -> dict:
    """
    Options for metadata-only YouTube searches.

    ``extract_flat=True`` returns search-result metadata (title, channel,
    view_count, duration) WITHOUT resolving each video's player — so it is not
    bot-gated and needs no cookies. Use for trend scraping.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": True,
    }
    # Flat extraction doesn't hit the player, so player_client/cookies are moot,
    # but a UA never hurts.
    opts.setdefault("http_headers", {})["User-Agent"] = _UA
    opts.update(extra)
    return opts


def download_opts(out_template: str, *, audio_codec: str = "wav", **extra) -> dict:
    """
    Options for actually downloading audio. Wires in resilient player clients
    and a cookies file (if available) to beat the bot gate on server IPs.
    """
    opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": audio_codec}
        ],
    }
    _apply_common(opts)
    opts.update(extra)
    return opts
