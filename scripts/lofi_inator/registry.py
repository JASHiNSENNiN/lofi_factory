"""
Duplicate detection and YouTube playlist management for lofi-inator.

Duplicate check (two layers):
  1. Local assets/lofi_inator_log.json — O(1) dict lookup
  2. YouTube API scan of recent channel videos for embedded ref_id
     (same pattern as publish.py:cmd_upload lines 419-442)

Playlist: creates "lofi-inator 🎵" playlist once, stores ID in assets/.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
LOG_FILE      = os.path.join(ROOT, "assets", "lofi_inator_log.json")
PLAYLIST_FILE = os.path.join(ROOT, "assets", "lofi_inator_playlist.json")

_PLAYLIST_TITLE = "lofi-inator 🎵"
_PLAYLIST_DESC  = (
    "Your favorite mainstream songs, slowed down and filtered through a lo-fi lens. "
    "New covers added automatically — subscribe to hear what drops next."
)


# ─── Ref ID ────────────────────────────────────────────────────────────────────

def build_ref_id(artist_slug: str, title_slug: str) -> str:
    return f"lofi-inator:{artist_slug}:{title_slug}"


# ─── Duplicate check ───────────────────────────────────────────────────────────

def is_already_done(artist_slug: str, title_slug: str, youtube=None) -> bool:
    """
    Returns True if this song has already been uploaded.
    Layer 1 (fast): local log file.
    Layer 2 (slow): YouTube API description scan.
    """
    key = f"{artist_slug}:{title_slug}"

    # Layer 1: local log
    log = _load_log()
    if key in log:
        print(f"  [registry] Already in local log: {key}")
        return True

    # Layer 2: YouTube API (if authenticated service provided)
    if youtube is not None:
        ref_id = build_ref_id(artist_slug, title_slug)
        try:
            found = _scan_youtube_for_ref(youtube, ref_id)
            if found:
                print(f"  [registry] Found on YouTube (ref_id={ref_id}): {found}")
                # Backfill local log so future checks are fast
                _append_log(key, {
                    "video_url": f"https://www.youtube.com/watch?v={found}",
                    "video_id": found,
                    "source": "youtube_scan_backfill",
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                })
                return True
        except Exception as e:
            print(f"  [registry] YouTube scan error (proceeding): {e}")

    return False


def _scan_youtube_for_ref(youtube, ref_id: str) -> str | None:
    """
    Search recent 50 channel videos for ref_id embedded in description.
    Returns video_id if found, else None.
    Same logic as publish.py:cmd_upload() lines 419-442.
    """
    search_resp = youtube.search().list(
        part="id",
        forMine=True,
        type="video",
        maxResults=50,
        order="date",
    ).execute()

    vid_ids = [item["id"]["videoId"] for item in search_resp.get("items", [])]
    if not vid_ids:
        return None

    video_resp = youtube.videos().list(
        part="snippet",
        id=",".join(vid_ids),
    ).execute()

    for video in video_resp.get("items", []):
        desc = video["snippet"].get("description", "")
        if ref_id in desc:
            return video["id"]

    return None


# ─── Log management ────────────────────────────────────────────────────────────

def mark_done(
    artist_slug: str,
    title_slug: str,
    video_id: str,
    video_url: str,
    original_artist: str,
    original_title: str,
    lofi_title: str,
    playlist_id: str = "",
    source: str = "",
    dna_source: str = "",
) -> None:
    key = f"{artist_slug}:{title_slug}"
    entry = {
        "original_artist": original_artist,
        "original_title": original_title,
        "lofi_title": lofi_title,
        "video_id": video_id,
        "video_url": video_url,
        "playlist_id": playlist_id,
        "source": source,
        "dna_source": dna_source,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    _append_log(key, entry)
    print(f"  [registry] Marked done: {key} → {video_url}")


def _load_log() -> dict:
    if not os.path.exists(LOG_FILE):
        return {}
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _append_log(key: str, entry: dict) -> None:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    log = _load_log()
    log[key] = entry
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


# ─── Playlist management ───────────────────────────────────────────────────────

def get_or_create_playlist(youtube) -> str:
    """
    Return the lofi-inator playlist ID.
    Creates the playlist if it doesn't exist yet, saves ID to assets/.
    """
    # Check cached playlist ID
    if os.path.exists(PLAYLIST_FILE):
        try:
            with open(PLAYLIST_FILE, encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("playlist_id"):
                return meta["playlist_id"]
        except Exception:
            pass

    # Create new playlist
    resp = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": _PLAYLIST_TITLE,
                "description": _PLAYLIST_DESC,
                "defaultLanguage": "en",
            },
            "status": {"privacyStatus": "public"},
        },
    ).execute()

    playlist_id = resp["id"]
    print(f"  [registry] Created playlist '{_PLAYLIST_TITLE}': {playlist_id}")

    os.makedirs(os.path.dirname(PLAYLIST_FILE), exist_ok=True)
    with open(PLAYLIST_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "playlist_id": playlist_id,
            "title": _PLAYLIST_TITLE,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, f, indent=2)

    return playlist_id


def add_to_playlist(youtube, playlist_id: str, video_id: str) -> None:
    """Add a video to the lofi-inator playlist. Failure is non-fatal."""
    try:
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
        print(f"  [registry] Added {video_id} to playlist {playlist_id}")
    except Exception as e:
        print(f"  [registry] Warning — playlist add failed (video still uploaded): {e}")
