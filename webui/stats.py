"""
stats.py — real channel + library data for the Studio dashboard.

Pulls live channel statistics from the YouTube API (cached) and assembles a
"library" by joining the per-render thumbnails in assets/ with upload_log.json.
"""
from __future__ import annotations

import glob
import json
import os
import re
import time
from datetime import datetime

from . import config

_THUMB_RE = re.compile(r"^thumb_(?P<theme>.+)_(?P<date>\d{8})_(?P<time>\d{6})$")

# ── Channel statistics (cached) ───────────────────────────────────────────────
_cache: dict = {"at": 0.0, "data": None}
_TTL = 120


def channel_stats(force: bool = False) -> dict:
    """{title, subs, views, videos} — cached for 2 min. Safe/no-throw."""
    now = time.time()
    if not force and _cache["data"] and now - _cache["at"] < _TTL:
        return _cache["data"]
    data = {"title": None, "subs": None, "views": None, "videos": None, "ok": False}
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        if not os.path.exists(config.TOKEN_FILE):
            return data
        creds = Credentials.from_authorized_user_file(config.TOKEN_FILE, config.SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        yt = build("youtube", "v3", credentials=creds)
        r = yt.channels().list(part="snippet,statistics", mine=True).execute()
        it = (r.get("items") or [{}])[0]
        st = it.get("statistics", {})
        data = {
            "title": it.get("snippet", {}).get("title"),
            "subs": int(st.get("subscriberCount", 0)),
            "views": int(st.get("viewCount", 0)),
            "videos": int(st.get("videoCount", 0)),
            "ok": True,
        }
    except Exception:
        pass
    _cache.update(at=now, data=data)
    return data


# ── Library (thumbnails ⋈ upload_log) ─────────────────────────────────────────
def _parse_thumb(path: str) -> dict | None:
    stem = os.path.splitext(os.path.basename(path))[0]
    m = _THUMB_RE.match(stem)
    if not m:
        return None
    try:
        dt = datetime.strptime(m["date"] + m["time"], "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return {"theme": m["theme"], "dt": dt, "thumb": path}


def _log_index() -> list[dict]:
    if not os.path.exists(config.UPLOAD_LOG):
        return []
    try:
        data = json.load(open(config.UPLOAD_LOG))
    except Exception:
        return []
    entries = data if isinstance(data, list) else data.get("entries", [])
    out = []
    for e in entries:
        vf = e.get("video_file") or ""
        m = re.search(r"(\d{8})_(\d{6})", vf) or re.search(r"(\d{8})_(\d{6})",
                                                            e.get("timestamp", ""))
        dt = None
        if m:
            try:
                dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            except ValueError:
                dt = None
        out.append({"dt": dt, "title": e.get("title"), "url": e.get("url"),
                    "video_id": e.get("video_id")})
    return out


def library(limit: int = 24) -> list[dict]:
    """
    Newest-first render cards: {theme, dt, thumb, title, url, video_id, when}.
    Thumbnails are matched to uploads by closest timestamp (±120s).
    """
    thumbs = [t for t in (_parse_thumb(p)
              for p in glob.glob(os.path.join(config.ASSETS_DIR, "thumb_*.jpg"))) if t]
    thumbs.sort(key=lambda t: t["dt"], reverse=True)
    logs = _log_index()

    cards = []
    for t in thumbs[:limit]:
        match = None
        best = 120
        for e in logs:
            if not e["dt"]:
                continue
            delta = abs((e["dt"] - t["dt"]).total_seconds())
            if delta <= best:
                best, match = delta, e
        cards.append({
            "theme": t["theme"].replace("_", " "),
            "dt": t["dt"],
            "thumb": t["thumb"],
            "thumb_name": os.path.basename(t["thumb"]),
            "title": (match or {}).get("title") or t["theme"].replace("_", " "),
            "url": (match or {}).get("url"),
            "video_id": (match or {}).get("video_id"),
            "when": t["dt"].strftime("%b %d, %Y"),
        })
    return cards


def fmt_count(n: int | None) -> str:
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)
