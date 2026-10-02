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
from datetime import datetime, timedelta

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


# ── Per-video engagement (likes/comments, cached) ─────────────────────────────
_engagement_cache: dict = {}  # video_id -> {"at": float, "likes": int, "comments": int}
_ENGAGEMENT_TTL = 120


def video_engagement(video_ids: list[str], force: bool = False) -> dict[str, dict]:
    """{video_id: {likes, comments, views}} via one batched videos.list call
    (up to 50 ids per request, chunked if more). Cached per-id for 2 min;
    safe/no-throw -- missing ids on error just aren't included in the
    returned dict."""
    now = time.time()
    fresh = {vid: {"likes": v["likes"], "comments": v["comments"], "views": v.get("views", 0)}
             for vid, v in _engagement_cache.items()
             if not force and vid in video_ids and now - v["at"] < _ENGAGEMENT_TTL}
    stale = [v for v in video_ids if v not in fresh]
    if not stale:
        return fresh
    if not os.path.exists(config.TOKEN_FILE):
        return fresh
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(config.TOKEN_FILE, config.SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        yt = build("youtube", "v3", credentials=creds)
        for i in range(0, len(stale), 50):
            chunk = stale[i:i + 50]
            r = yt.videos().list(part="statistics", id=",".join(chunk)).execute()
            for item in r.get("items", []):
                st = item.get("statistics", {})
                entry = {
                    "likes": int(st.get("likeCount", 0) or 0),
                    "comments": int(st.get("commentCount", 0) or 0),
                    "views": int(st.get("viewCount", 0) or 0),
                }
                _engagement_cache[item["id"]] = {**entry, "at": now}
                fresh[item["id"]] = entry
    except Exception:
        pass
    return fresh


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


def _video_index() -> list[dict]:
    """Local rendered mp4s in output/, parsed for their embedded timestamp.

    Skips any video still being written by ffmpeg (scripts/assemble_video.py
    writes a sibling `<video>.mp4.grade.log` for the duration of the encode
    and deletes it on success) -- confirmed 2026-08-16: the render's SEO
    thumbnail is generated before the final assembly step, so the Library
    grid already had a real card for the in-progress video (matched by
    timestamp) while the mp4 itself had no moov atom yet -- unplayable,
    aborted requests, looked like the gallery's player was just broken.
    Excluding it here means that card falls back to thumbnail-only until
    the file is actually done, instead of offering a broken player."""
    out = []
    for path in glob.glob(os.path.join(config.OUTPUT_DIR, "*.mp4")):
        if os.path.exists(path + ".grade.log"):
            continue
        m = re.search(r"(\d{8})_(\d{6})", os.path.basename(path))
        if not m:
            continue
        try:
            dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            continue
        out.append({"dt": dt, "path": path, "name": os.path.basename(path)})
    return out


def _nearest(dt, candidates: list[dict], window_secs: int = 120) -> dict | None:
    best_delta, best = window_secs, None
    for c in candidates:
        if not c.get("dt"):
            continue
        delta = abs((c["dt"] - dt).total_seconds())
        if delta <= best_delta:
            best_delta, best = delta, c
    return best


def library(limit: int = 24) -> list[dict]:
    """
    Newest-first render cards: {theme, dt, thumb, title, url, video_id, video_file, when}.
    Thumbnails are matched to uploads and local mp4s by closest timestamp (±120s).
    """
    thumbs = [t for t in (_parse_thumb(p)
              for p in glob.glob(os.path.join(config.ASSETS_DIR, "thumb_*.jpg"))) if t]
    thumbs.sort(key=lambda t: t["dt"], reverse=True)
    logs = _log_index()
    videos = _video_index()

    cards = []
    for t in thumbs[:limit]:
        match = _nearest(t["dt"], logs)
        vid = _nearest(t["dt"], videos)
        cards.append({
            "theme": t["theme"].replace("_", " "),
            "dt": t["dt"],
            "thumb": t["thumb"],
            "thumb_name": os.path.basename(t["thumb"]),
            "title": (match or {}).get("title") or t["theme"].replace("_", " "),
            "url": (match or {}).get("url"),
            "video_id": (match or {}).get("video_id"),
            "video_file": (vid or {}).get("name"),
            "when": t["dt"].strftime("%b %d, %Y"),
        })
    return cards


# ── Audience retention (YouTube Analytics API) ─────────────────────────────────
def retention(video_id: str) -> list[dict] | None:
    """
    [{t: elapsed-video-ratio 0..1, pct: audience watch ratio}, ...] for one video,
    or None if unavailable (not connected, API error, or not enough view data yet).
    Uses the same yt-analytics.readonly scope already requested at login.
    """
    if not video_id or not os.path.exists(config.TOKEN_FILE):
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(config.TOKEN_FILE, config.SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        yta = build("youtubeAnalytics", "v2", credentials=creds)
        r = yta.reports().query(
            ids="channel==MINE",
            startDate="2005-01-01",
            endDate=datetime.utcnow().strftime("%Y-%m-%d"),
            metrics="audienceWatchRatio",
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_id}",
            sort="elapsedVideoTimeRatio",
        ).execute()
        rows = r.get("rows") or []
        if not rows:
            return None
        return [{"t": row[0], "pct": row[1]} for row in rows]
    except Exception:
        return None


# ── Comment listing + moderation (YouTube Data API v3) ─────────────────────────
# Comments change far more often than channel/engagement stats, so this gets a
# shorter TTL than the 120s _TTL above -- 60s keeps quota usage sane (one
# commentThreads.list call per video-detail-dialog-open, not per keystroke)
# while still feeling reasonably live to a moderator working through a queue.
_comments_cache: dict[str, dict] = {}  # video_id -> {"at": float, "data": [...]}
_COMMENTS_TTL = 60


def _yt_client(client=None):
    """Build (or pass through) an authenticated youtube#v3 client. Shared by
    the comment functions below -- same credentials/token.json/SCOPES as
    channel_stats()/video_engagement()/retention() above (no second auth
    path). `client` lets tests inject a fake client directly instead of
    mocking google internals."""
    if client is not None:
        return client
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(config.TOKEN_FILE, config.SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def _shape_comment(snippet: dict, comment_id: str) -> dict:
    return {
        "id": comment_id,
        "author": snippet.get("authorDisplayName", "?"),
        "author_avatar": snippet.get("authorProfileImageUrl"),
        "text": snippet.get("textDisplay", ""),
        "like_count": int(snippet.get("likeCount", 0) or 0),
        "published_at": snippet.get("publishedAt"),
        "moderation_status": snippet.get("moderationStatus", "published"),
    }


def _shape_thread(item: dict) -> dict:
    top = item["snippet"]["topLevelComment"]
    out = _shape_comment(top["snippet"], top["id"])
    out["reply_count"] = int(item["snippet"].get("totalReplyCount", 0) or 0)
    # commentThreads.list inlines up to 5 replies per thread when present --
    # good enough for the Library detail panel without a second API call per
    # thread. A thread with more replies than that just shows the first 5.
    replies_block = item.get("replies", {}).get("comments", [])
    out["replies"] = [_shape_comment(r["snippet"], r["id"]) for r in replies_block]
    return out


def list_comments(video_id: str, *, force: bool = False, client=None) -> list[dict] | None:
    """
    Top-level comments (with up to 5 inlined replies each) for one video, via
    commentThreads.list. Returns None if unavailable (not connected, comments
    disabled on the video, API error) -- distinct from [] (connected, zero
    comments). Cached per-video for 60s.
    """
    now = time.time()
    cached = _comments_cache.get(video_id)
    if not force and cached and now - cached["at"] < _COMMENTS_TTL:
        return cached["data"]
    if client is None and not os.path.exists(config.TOKEN_FILE):
        return None
    try:
        yt = _yt_client(client)
        out: list[dict] = []
        page_token = None
        while True:
            r = yt.commentThreads().list(
                part="snippet,replies",
                videoId=video_id,
                maxResults=100,
                textFormat="plainText",
                pageToken=page_token,
            ).execute()
            out.extend(_shape_thread(item) for item in r.get("items", []))
            page_token = r.get("nextPageToken")
            if not page_token or len(out) >= 500:  # sane cap on one dialog open
                break
    except Exception:
        return None
    _comments_cache[video_id] = {"at": now, "data": out}
    return out


_MODERATION_STATUSES = {"heldForReview", "published", "rejected"}


def set_comment_moderation(comment_id: str, status: str, *, client=None) -> bool:
    """comments.setModerationStatus -- status must be one of heldForReview/
    published/rejected. Returns True on success, False on any failure (bad
    status value, not connected, API error) -- never raises, matching this
    module's safe/no-throw convention."""
    if status not in _MODERATION_STATUSES:
        return False
    try:
        yt = _yt_client(client)
        yt.comments().setModerationStatus(id=comment_id, moderationStatus=status).execute()
        _comments_cache.clear()  # stale after a moderation action; cheap to just drop it all
        return True
    except Exception:
        return False


def reply_to_comment(parent_id: str, text: str, *, client=None) -> dict | None:
    """comments.insert a reply under parent_id. Returns the shaped new
    comment on success, None on failure."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        yt = _yt_client(client)
        r = yt.comments().insert(
            part="snippet",
            body={"snippet": {"parentId": parent_id, "textOriginal": text}},
        ).execute()
        _comments_cache.clear()
        return _shape_comment(r["snippet"], r["id"])
    except Exception:
        return None


def delete_comment(comment_id: str, *, client=None) -> bool:
    """comments.delete. Returns True on success, False on failure."""
    try:
        yt = _yt_client(client)
        yt.comments().delete(id=comment_id).execute()
        _comments_cache.clear()
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Edit an already-published video — title/description/tags/privacy, and
# regenerating + re-pushing its thumbnail. Confirmed 2026-08-16: nothing in
# this codebase could touch a video after upload at all (publish.py/
# upload_youtube.py only ever set these once, at upload time) -- the closest
# YT Studio feature (editing live content) had zero equivalent here, which
# also meant a thumbnail-generator bug fix couldn't reach anything already
# published without this.
# ─────────────────────────────────────────────────────────────────────────────
def get_video_details(video_id: str, *, client=None) -> dict | None:
    """Current snippet+status for one video, shaped for the edit dialog.
    None if the video doesn't exist / API call fails."""
    try:
        yt = _yt_client(client)
        r = yt.videos().list(part="snippet,status", id=video_id).execute()
        items = r.get("items") or []
        if not items:
            return None
        snippet, status = items[0]["snippet"], items[0]["status"]
        return {
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "tags": snippet.get("tags", []),
            "category_id": snippet.get("categoryId", "10"),
            "privacy": status.get("privacyStatus", "public"),
        }
    except Exception:
        return None


def update_video(video_id: str, *, title: str, description: str, tags: list[str],
                  privacy: str, category_id: str = "10", client=None) -> bool:
    """videos.update — the API requires the full snippet/status resource for
    any part being updated (not a partial patch), so callers must pass every
    field, not just the one that changed. Returns True on success."""
    try:
        yt = _yt_client(client)
        yt.videos().update(part="snippet,status", body={
            "id": video_id,
            "snippet": {
                "title": title[:100],
                "description": description[:4900],
                "tags": tags,
                "categoryId": category_id,
            },
            "status": {"privacyStatus": privacy},
        }).execute()
        return True
    except Exception:
        return False


def set_video_thumbnail(video_id: str, thumb_path: str, *, client=None) -> bool:
    """thumbnails.set — pushes a local jpg as the video's thumbnail."""
    try:
        from googleapiclient.http import MediaFileUpload
        yt = _yt_client(client)
        yt.thumbnails().set(videoId=video_id,
                             media_body=MediaFileUpload(thumb_path, mimetype="image/jpeg")).execute()
        return True
    except Exception:
        return False


def regenerate_thumbnail(video_id: str, title: str) -> str | None:
    """Re-run the (now-fixed) thumbnail generator for an already-published
    video, using the theme its original thumbnail was generated with (parsed
    from the existing thumb_<theme>_<ts>.jpg filename -- upload_log.json
    doesn't separately record theme) and its actual duration from
    upload_log.json, so a re-generated thumbnail matches what the video
    really is. Returns the new local file path, or None if no matching
    original thumbnail/duration could be found. Does not push to YouTube --
    call set_video_thumbnail() with the result to do that."""
    from . import data as _data
    entries = [e for e in _data.upload_history(limit=10_000) if e.get("video_id") == video_id]
    if not entries:
        return None
    entry = entries[0]
    thumb_file = entry.get("thumb_file") or ""
    m = re.match(r"^thumb_(?P<theme>.+)_\d{8}_\d{6}\.jpg$", thumb_file)
    if not m:
        return None
    theme_name = m.group("theme")

    duration_secs = entry.get("duration_secs")
    duration_label = "2 hours"
    if duration_secs:
        from scripts.assemble_video import DURATION_MAP
        duration_label = min(DURATION_MAP, key=lambda k: abs(DURATION_MAP[k] - duration_secs))

    from scripts.generate_thumbnail_cozy import generate_thumbnail
    from scripts.generate_seo import _SUBGENRE_TO_GENRE_LABEL
    genre = _SUBGENRE_TO_GENRE_LABEL.get(entry.get("sub_genre") or "", "")
    out_path, _ = generate_thumbnail(theme_name=theme_name, duration=duration_label,
                                     title=title, genre=genre)
    return out_path


# ── Traffic-source breakdown + subscriber growth (YouTube Analytics API) ──────
_traffic_cache: dict = {"at": 0.0, "data": None}
_subs_cache: dict = {"at": 0.0, "data": None}


def _analytics_client(client=None):
    if client is not None:
        return client
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(config.TOKEN_FILE, config.SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("youtubeAnalytics", "v2", credentials=creds)


def traffic_sources(days: int = 28, *, force: bool = False, client=None) -> list[dict] | None:
    """
    [{source, views, subs_gained}, ...] sorted by views desc, using the
    insightTrafficSourceType dimension over the last `days` days. None if
    unavailable. Cached 120s (same _TTL as channel_stats -- this is a
    channel-wide rollup, not something that needs comment-level freshness).
    """
    now = time.time()
    if not force and _traffic_cache["data"] is not None and now - _traffic_cache["at"] < _TTL:
        return _traffic_cache["data"]
    if client is None and not os.path.exists(config.TOKEN_FILE):
        return None
    try:
        yta = _analytics_client(client)
        end = datetime.utcnow().strftime("%Y-%m-%d")
        start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        r = yta.reports().query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics="views,subscribersGained",
            dimensions="insightTrafficSourceType",
            sort="-views",
        ).execute()
        rows = r.get("rows") or []
        out = [{"source": row[0], "views": int(row[1] or 0), "subs_gained": int(row[2] or 0)}
               for row in rows]
    except Exception:
        return None
    _traffic_cache.update(at=now, data=out)
    return out


def subscriber_growth(days: int = 90, *, force: bool = False, client=None) -> list[dict] | None:
    """
    [{date, gained, lost, net}, ...] time series over the last `days` days,
    from subscribersGained/subscribersLost. None if unavailable. Cached 120s.
    """
    now = time.time()
    if not force and _subs_cache["data"] is not None and now - _subs_cache["at"] < _TTL:
        return _subs_cache["data"]
    if client is None and not os.path.exists(config.TOKEN_FILE):
        return None
    try:
        yta = _analytics_client(client)
        end = datetime.utcnow().strftime("%Y-%m-%d")
        start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        r = yta.reports().query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics="subscribersGained,subscribersLost",
            dimensions="day",
            sort="day",
        ).execute()
        rows = r.get("rows") or []
        out = [{"date": row[0], "gained": int(row[1] or 0), "lost": int(row[2] or 0),
                "net": int(row[1] or 0) - int(row[2] or 0)} for row in rows]
    except Exception:
        return None
    _subs_cache.update(at=now, data=out)
    return out


# ── Revenue / RPM / CPM (opt-in monetary scope — see youtube_oauth.py) ────────
_revenue_cache: dict = {"at": 0.0, "data": None}


def revenue_available() -> bool:
    """Whether the user has completed the separate monetary-scope opt-in
    consent flow (Settings -> 'Connect monetary analytics'). Gates whether
    view_analytics() even attempts a revenue_stats() call."""
    return os.path.exists(config.TOKEN_FILE_MONETARY)


def revenue_stats(days: int = 28, *, force: bool = False, client=None) -> list[dict] | None:
    """
    [{date, revenue, ad_revenue, cpm, playback_cpm}, ...] daily time series
    using the yt-analytics-monetary.readonly-gated estimatedRevenue /
    estimatedAdRevenue / cpm / playbackBasedCpm metrics. Requires
    token_monetary.json (see revenue_available()) -- returns None without it,
    same as every other "not connected yet" case in this module. Uses
    TOKEN_FILE_MONETARY/MONETARY_SCOPES, NOT the regular token.json/SCOPES,
    so it never implicitly relies on (or requests) the monetary scope via the
    main login.
    """
    now = time.time()
    if not force and _revenue_cache["data"] is not None and now - _revenue_cache["at"] < _TTL:
        return _revenue_cache["data"]
    if client is None and not os.path.exists(config.TOKEN_FILE_MONETARY):
        return None
    try:
        if client is None:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            creds = Credentials.from_authorized_user_file(
                config.TOKEN_FILE_MONETARY, config.MONETARY_SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            yta = build("youtubeAnalytics", "v2", credentials=creds)
        else:
            yta = client
        end = datetime.utcnow().strftime("%Y-%m-%d")
        start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        r = yta.reports().query(
            ids="channel==MINE",
            startDate=start,
            endDate=end,
            metrics="estimatedRevenue,estimatedAdRevenue,cpm,playbackBasedCpm",
            dimensions="day",
            sort="day",
        ).execute()
        rows = r.get("rows") or []
        out = [{"date": row[0], "revenue": float(row[1] or 0), "ad_revenue": float(row[2] or 0),
                "cpm": float(row[3] or 0), "playback_cpm": float(row[4] or 0)} for row in rows]
    except Exception:
        return None
    _revenue_cache.update(at=now, data=out)
    return out


def fmt_count(n: int | None) -> str:
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


# ── Background refresh ───────────────────────────────────────────────────────
# Page builders read these cached calls synchronously. Refreshing them here,
# off the event loop and more often than their 120 s TTL, means a page load
# finds a warm cache instead of waiting on YouTube (which stalled every open
# panel). Without a token every call returns at once, so this costs nothing
# before YouTube is connected.
WARM_EVERY_SECS = 90


def warm_caches() -> None:
    for fn in (lambda: channel_stats(force=True),
               lambda: traffic_sources(force=True),
               lambda: subscriber_growth(force=True),
               lambda: revenue_stats(force=True) if revenue_available() else None):
        try:
            fn()
        except Exception:
            pass
    try:
        vids = [c["video_id"] for c in library(limit=200) if c.get("video_id")]
        if vids:
            video_engagement(vids, force=True)   # entries are replaced, never emptied
    except Exception:
        pass
