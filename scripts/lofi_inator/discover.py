"""
Song discovery: query trending mainstream songs from multiple chart sources.
Priority: Spotify Global Top 50 → Last.fm chart.getTopTracks → YouTube music trending.
"""

from __future__ import annotations

import html as _html
import json
import os
import re
import time
from typing import Any

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
except ImportError:
    pass

from .models import SongInfo, _slugify

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CACHE_FILE = os.path.join(ROOT, "assets", "song_harvest_cache.json")
TOKEN_CACHE = os.path.join(ROOT, "assets", "spotify_token_cache.json")

# Spotify API endpoints
# Note: curated playlist access and /audio-features were removed in Spotify's Nov 2024 API changes.
# We now discover trending songs via popularity-ranked search across current-year releases.
_SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
_SPOTIFY_BASE = "https://api.spotify.com/v1"

# Search queries to find trending mainstream songs (rotated to get variety)
_SPOTIFY_TRENDING_QUERIES = [
    "tag:new",
    "year:2025-2026",
    "genre:pop year:2025-2026",
    "genre:hip-hop year:2025-2026",
    "genre:r&b year:2025-2026",
]

_LASTFM_BASE = "http://ws.audioscrobbler.com/2.0/"

# Cache TTL: 6 hours (same as trend_research.py)
_CACHE_TTL = 6 * 3600


class SpotifyUnavailableError(Exception):
    pass


class LastfmUnavailableError(Exception):
    pass


# ─── Public API ────────────────────────────────────────────────────────────────

def get_trending_songs(limit: int = 10) -> list[SongInfo]:
    """
    Fetch mainstream songs from charts in priority order.
    Returns deduplicated list (by artist_slug:title_slug), up to `limit`.
    Falls back gracefully through all sources.
    """
    songs: list[SongInfo] = []
    seen: set[str] = set()

    for fetch_fn in (_fetch_spotify_top50, _fetch_lastfm_top, _fetch_youtube_music_trending):
        try:
            batch = fetch_fn(limit * 2)
            for s in batch:
                key = f"{s.artist_slug}:{s.title_slug}"
                if key not in seen:
                    seen.add(key)
                    songs.append(s)
                if len(songs) >= limit:
                    break
        except (SpotifyUnavailableError, LastfmUnavailableError) as e:
            print(f"  [discover] {fetch_fn.__name__} unavailable: {e}")
        except Exception as e:
            print(f"  [discover] {fetch_fn.__name__} error: {e}")

        if len(songs) >= limit:
            break

    print(f"[discover] Found {len(songs)} songs from charts")
    return songs[:limit]


# ─── Spotify ───────────────────────────────────────────────────────────────────

def _get_spotify_token() -> str:
    """Spotify Client Credentials flow — no user OAuth needed for public playlists."""
    client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        raise SpotifyUnavailableError("SPOTIFY_CLIENT_ID/SECRET not set in .env")

    # Check token cache
    if os.path.exists(TOKEN_CACHE):
        try:
            with open(TOKEN_CACHE, encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("expires_at", 0) > time.time() + 60:
                return cached["access_token"]
        except Exception:
            pass

    resp = requests.post(
        _SPOTIFY_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=10,
    )
    if resp.status_code != 200:
        raise SpotifyUnavailableError(f"Spotify token request failed: {resp.status_code}")

    data = resp.json()
    token = data["access_token"]
    expires_at = time.time() + data.get("expires_in", 3600) - 60

    os.makedirs(os.path.dirname(TOKEN_CACHE), exist_ok=True)
    with open(TOKEN_CACHE, "w", encoding="utf-8") as f:
        json.dump({"access_token": token, "expires_at": expires_at}, f)

    return token


def _fetch_spotify_top50(limit: int) -> list[SongInfo]:
    """Fetch trending songs via popularity-ranked search (replaces curated playlist,
    which was removed in Spotify's November 2024 API changes)."""
    token = _get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}

    all_tracks: list[dict] = []
    seen_ids: set[str] = set()

    for query in _SPOTIFY_TRENDING_QUERIES:
        resp = requests.get(
            f"{_SPOTIFY_BASE}/search",
            headers=headers,
            params={"q": query, "type": "track", "limit": 50, "market": "US"},
            timeout=10,
        )
        if resp.status_code != 200:
            raise SpotifyUnavailableError(f"Spotify search {resp.status_code}: {resp.text[:200]}")

        for track in resp.json().get("tracks", {}).get("items", []):
            if not track or track.get("id") in seen_ids:
                continue
            seen_ids.add(track["id"])
            all_tracks.append(track)

        if len(all_tracks) >= limit * 3:
            break

    # Sort by popularity descending — highest charting songs first
    all_tracks.sort(key=lambda t: t.get("popularity", 0), reverse=True)

    songs = []
    for rank, track in enumerate(all_tracks, start=1):
        title = _html.unescape(track.get("name", ""))
        artists = track.get("artists", [])
        artist = _html.unescape(artists[0]["name"]) if artists else ""
        if not title or not artist:
            continue
        songs.append(SongInfo(
            title=title,
            artist=artist,
            source="spotify",
            chart_rank=rank,
            spotify_id=track.get("id"),
        ))
        if len(songs) >= limit:
            break

    print(f"  [discover/spotify] {len(songs)} songs from popularity-ranked search")
    return songs


def get_spotify_features(song: SongInfo) -> "SpotifyFeatures | None":
    """Fetch audio analysis features for a single Spotify track."""
    from .models import SpotifyFeatures

    if not song.spotify_id:
        return None
    try:
        token = _get_spotify_token()
    except SpotifyUnavailableError:
        return None

    try:
        resp = requests.get(
            f"{_SPOTIFY_BASE}/audio-features/{song.spotify_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 403:
            # /audio-features restricted since Spotify Nov 2024 API changes — fall back to Groq
            return None
        if resp.status_code != 200:
            return None
        data = resp.json()
        return SpotifyFeatures(
            tempo=float(data.get("tempo", 100)),
            key=int(data.get("key", 0)),
            mode=int(data.get("mode", 0)),
            energy=float(data.get("energy", 0.5)),
            valence=float(data.get("valence", 0.5)),
            danceability=float(data.get("danceability", 0.5)),
        )
    except Exception as e:
        print(f"  [discover/spotify_features] {e}")
        return None


# ─── Last.fm ───────────────────────────────────────────────────────────────────

def _fetch_lastfm_top(limit: int) -> list[SongInfo]:
    api_key = os.getenv("LASTFM_API_KEY", "")
    if not api_key:
        raise LastfmUnavailableError("LASTFM_API_KEY not set in .env")

    resp = requests.get(
        _LASTFM_BASE,
        params={
            "method": "chart.getTopTracks",
            "api_key": api_key,
            "format": "json",
            "limit": min(limit, 50),
        },
        timeout=10,
    )
    if resp.status_code != 200:
        raise LastfmUnavailableError(f"Last.fm API {resp.status_code}")

    tracks = resp.json().get("tracks", {}).get("track", [])
    songs = []
    for rank, track in enumerate(tracks, start=1):
        title = _html.unescape(track.get("name", ""))
        artist = _html.unescape(track.get("artist", {}).get("name", ""))
        lastfm_url = track.get("url", "")
        if not title or not artist:
            continue
        songs.append(SongInfo(
            title=title,
            artist=artist,
            source="lastfm",
            chart_rank=rank,
            lastfm_url=lastfm_url,
        ))

    print(f"  [discover/lastfm] {len(songs)} songs from Last.fm chart")
    return songs


# ─── YouTube Music Trending (no extra API key) ─────────────────────────────────

def _fetch_youtube_music_trending(limit: int) -> list[SongInfo]:
    yt_key = os.getenv("YOUTUBE_API_KEY", "")
    if not yt_key:
        raise Exception("YOUTUBE_API_KEY not set")

    # Search YouTube for official music videos (as a proxy for trending songs)
    import datetime
    published_after = (
        datetime.datetime.utcnow() - datetime.timedelta(days=30)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    resp = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "q": "official music video 2026",
            "type": "video",
            "videoCategoryId": "10",  # Music
            "order": "viewCount",
            "maxResults": min(limit * 3, 50),
            "publishedAfter": published_after,
            "key": yt_key,
        },
        timeout=10,
    )
    if resp.status_code != 200:
        raise Exception(f"YouTube API {resp.status_code}")

    items = resp.json().get("items", [])
    songs = []
    rank = 1
    for item in items:
        title_raw = _html.unescape(item["snippet"].get("title", ""))
        parsed = _parse_yt_music_title(title_raw)
        if parsed:
            artist, title = parsed
            # Skip if either part is empty or suspiciously short
            if not artist.strip() or not title.strip() or len(artist) < 2 or len(title) < 2:
                continue
            songs.append(SongInfo(
                title=title.strip(),
                artist=artist.strip(),
                source="youtube_music",
                chart_rank=rank,
            ))
            rank += 1
        if len(songs) >= limit:
            break

    print(f"  [discover/youtube] {len(songs)} songs from YouTube music trending")
    return songs


def _parse_yt_music_title(raw: str) -> tuple[str, str] | None:
    """
    Parse YouTube music video title: "Artist - Song Title (Official Video)"
    Returns (artist, title) or None if format unrecognized.
    """
    # Strip common bracket suffixes like (Official Video), [Lyric Video], etc.
    raw = re.sub(
        r"\s*[\(\[](official|lyric|music|video|audio|hd|4k|mv)[^\)\]]*[\)\]]",
        "", raw, flags=re.IGNORECASE,
    ).strip()
    raw = re.sub(r"\s*\|.*$", "", raw).strip()

    # Standard YouTube music format is "Artist - Title" (hyphen-minus, spaces)
    # This is the dominant format for official music channels.
    for sep in (" - ", " – ", " — "):
        if sep in raw:
            parts = [p.strip() for p in raw.split(sep, 1)]
            if len(parts) == 2 and parts[0] and parts[1]:
                # Assume first part is artist — most common YouTube Music format.
                # Imprecise when title comes first (e.g. "Song Title - Artist"),
                # but Spotify/Last.fm are the primary sources with structured data.
                return (parts[0], parts[1])

    return None
