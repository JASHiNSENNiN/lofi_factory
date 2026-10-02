"""
trend_research.py — YouTube trend snapshot for lo-fi content generation.

Pipeline:
  1. YouTube Data API  — search trending lofi videos (last 14 days, top view count)
                         fetch full details: titles, tags, view counts, durations
  2. Keyword rules     — derive a suggested theme and music hints from the titles
  3. Cache to assets/  — 6-hour TTL so we don't hammer APIs every run
"""

import os
import json
import datetime
import re

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(ROOT, "assets", "trend_cache.json")
CACHE_TTL  = 6 * 3600   # seconds
MAX_HISTORY = 500       # cap on stored snapshots -- oldest trimmed first

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"), override=False)
except ImportError:
    pass

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def _season() -> str:
    month = datetime.datetime.now(datetime.timezone.utc).month
    if month in (3, 4, 5):  return "spring"
    if month in (6, 7, 8):  return "summer"
    if month in (9, 10, 11): return "autumn"
    return "winter"

def _load_history() -> list[dict]:
    """
    Load assets/trend_cache.json as an append-only list of dated snapshots,
    oldest first. Back-compat: an older single-snapshot dict on disk (the
    pre-history overwrite format) is wrapped into a one-element list rather
    than discarded. Returns [] if missing/unreadable.
    """
    if not os.path.exists(CACHE_FILE):
        return []
    try:
        with open(CACHE_FILE) as f:
            raw = json.load(f)
    except Exception:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [raw]
    return []


def _save_history(history: list[dict]) -> None:
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(history[-MAX_HISTORY:], f, indent=2, ensure_ascii=False)


def compute_trend_deltas(history: list[dict] | None = None) -> dict | None:
    """
    Compare the two most recent trend snapshots and return competitor
    view-count deltas, so competitor performance can be tracked over time
    instead of only ever seeing the latest overwritten snapshot.

    Matches competitor videos between snapshots by exact title (their video
    IDs aren't tracked, since fetch_yt_trending() only keeps title/channel/
    views/tags/duration — title is the best available join key across
    independent search-result snapshots). Videos that only appear in one of
    the two snapshots are skipped from per-video deltas (nothing to diff)
    but still count toward each snapshot's total.

    Returns None if fewer than 2 snapshots exist yet. Otherwise:
        {"date_prev", "date_latest",
         "total_views_prev", "total_views_latest",
         "delta_total", "delta_pct",
         "per_video": [{"title", "prev_views", "latest_views", "delta"}, ...]}
        (per_video sorted by largest positive delta first)
    """
    if history is None:
        history = _load_history()
    if len(history) < 2:
        return None

    prev, latest = history[-2], history[-1]

    def _video_map(snap: dict) -> dict[str, int]:
        return {
            v.get("title", ""): int(v.get("views", 0) or 0)
            for v in snap.get("yt_videos", [])
            if v.get("title")
        }

    prev_map = _video_map(prev)
    latest_map = _video_map(latest)

    per_video = []
    for title, latest_views in latest_map.items():
        if title in prev_map:
            per_video.append({
                "title": title,
                "prev_views": prev_map[title],
                "latest_views": latest_views,
                "delta": latest_views - prev_map[title],
            })
    per_video.sort(key=lambda r: -r["delta"])

    total_prev = sum(prev_map.values())
    total_latest = sum(latest_map.values())
    delta_total = total_latest - total_prev
    delta_pct = (delta_total / total_prev) if total_prev else None

    return {
        "date_prev":          prev.get("fetched_at", "")[:10],
        "date_latest":        latest.get("fetched_at", "")[:10],
        "total_views_prev":   total_prev,
        "total_views_latest": total_latest,
        "delta_total":        delta_total,
        "delta_pct":          delta_pct,
        "per_video":          per_video,
    }


def _seasonal_keywords() -> list[str]:
    m = datetime.datetime.now(datetime.timezone.utc).month
    # Map academic + cultural calendar to search spikes
    calendar = {
        1:  ["new year focus", "january reset", "winter study session"],
        2:  ["february lofi", "late winter study", "valentine mood lofi"],
        3:  ["spring break study", "march exam season", "spring dawn lofi"],
        4:  ["finals week lofi", "april exam music", "spring study beats"],
        5:  ["exam season lofi", "may finals music", "graduation study mix"],
        6:  ["summer lofi", "june chill beats", "summer night study"],
        7:  ["summer study lofi", "july lofi playlist", "hot night lofi"],
        8:  ["back to school lofi", "august study music", "summer ending lofi"],
        9:  ["back to school lofi", "september study session", "autumn lofi"],
        10: ["october lofi", "autumn study", "halloween lofi", "cozy fall beats"],
        11: ["november study grind", "autumn lofi", "late semester beats"],
        12: ["winter study lofi", "december finals", "christmas lofi", "year end lofi"],
    }
    return calendar.get(m, ["lofi study music"])


# ── Source 1: YouTube Data API ────────────────────────────────────────────────

def fetch_yt_trending(max_results: int = 20) -> list[dict]:
    """
    Search YouTube for trending lofi videos published in the past 14 days.
    Returns list of {title, channel, views, tags, duration_label}.
    """
    if not YOUTUBE_API_KEY:
        return []
    try:
        from googleapiclient.discovery import build
        yt    = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        # Search with multiple queries to capture different sub-niches.
        # NOTE: videoDuration='long' combined with publishedAfter returns 0 results
        # from the YouTube API — filter by duration in post-processing instead.
        queries = [
            f"lofi hip hop study music {datetime.datetime.now().year}",
            "lofi beats to relax study to",
            "chill lofi beats study focus",
            "lofi music sleep study",
        ]
        video_ids = []
        for q in queries:
            # Try with date filter first; fall back without it if empty
            for kwargs in [
                {"publishedAfter": since},
                {},  # fallback: no date filter (broader pool)
            ]:
                res = yt.search().list(
                    q=q, part="snippet", type="video",
                    order="viewCount",
                    videoCategoryId="10",   # Music category only
                    maxResults=max_results // len(queries) + 2,
                    **kwargs,
                ).execute()
                ids = [i["id"]["videoId"] for i in res.get("items", [])]
                if ids:
                    video_ids += ids
                    break  # got results — don't fall back

        if not video_ids:
            return []

        # Fetch full details for all videos
        details = yt.videos().list(
            id=",".join(dict.fromkeys(video_ids[:50])),  # dedupe, preserve order
            part="snippet,statistics,contentDetails",
        ).execute()

        results = []
        for item in details.get("items", []):
            snip  = item["snippet"]
            stats = item.get("statistics", {})
            dur   = item.get("contentDetails", {}).get("duration", "")
            views = int(stats.get("viewCount", 0))
            dur_label = _parse_duration(dur)
            # Skip shorts / very short clips (< 20 min) — not lo-fi study format
            dur_m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", dur)
            if dur_m:
                h_part = int(dur_m.group(1) or 0)
                m_part = int(dur_m.group(2) or 0)
                if h_part == 0 and m_part < 20:
                    continue
            results.append({
                "title":    snip.get("title", ""),
                "channel":  snip.get("channelTitle", ""),
                "views":    views,
                "tags":     snip.get("tags", [])[:10],
                "duration": dur_label,
            })

        # Sort by view count descending
        return sorted(results, key=lambda x: x["views"], reverse=True)[:15]

    except Exception as ex:
        print(f"  [Trends/YT] fetch failed: {ex}")
        return []


def _parse_duration(iso_dur: str) -> str:
    """Convert PT1H23M45S → '1 hour', 'nnm', etc."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_dur)
    if not m:
        return "unknown"
    h, mins = int(m.group(1) or 0), int(m.group(2) or 0)
    if h >= 8:   return "8+ hours"
    if h >= 4:   return "4+ hours"
    if h >= 3:   return "3 hours"
    if h >= 2:   return "2 hours"
    if h >= 1:   return f"{h} hour" + ("s" if h > 1 else "") + (f" {mins}m" if mins else "")
    return f"{mins} min"


# ── Thumbnail theme suggestion ────────────────────────────────────────────────

_VALID_THEMES = [
    "cozy_rain", "midnight_cafe", "purple_dusk", "amber_night", "winter_snow",
    "autumn_study", "spring_dawn", "neon_tokyo", "summer_lofi", "blue_hour",
    "forest_rain", "sakura_night", "vaporwave", "lofi_house",
]

_THEME_KEYWORD_MAP: list[tuple[list[str], str]] = [
    (["neon", "city", "tokyo", "urban", "night city"],          "neon_tokyo"),
    (["vaporwave", "aesthetic", "retro", "synthwave"],          "vaporwave"),
    (["sakura", "cherry"],                                      "sakura_night"),
    (["spring"],                                                "spring_dawn"),
    (["winter", "snow", "cold"],                               "winter_snow"),
    (["autumn", "fall", "october"],                            "autumn_study"),
    (["summer", "beach", "tropical"],                          "summer_lofi"),
    (["jazz", "cafe", "coffee", "midnight"],                   "midnight_cafe"),
    (["forest", "nature", "green"],                            "forest_rain"),
    (["rain", "storm", "rainy"],                               "cozy_rain"),
]

_SEASON_THEME_BIAS: dict[str, list[str]] = {
    "spring": ["spring_dawn", "sakura_night"],
    "winter": ["winter_snow", "midnight_cafe"],
}


def suggest_thumbnail_theme(snapshot: dict) -> str:
    """
    Suggest a thumbnail theme name based on keyword signals in the trend snapshot.
    Checks the first 5 trending_titles.
    Returns one of the valid theme names from _VALID_THEMES.
    """
    titles       = snapshot.get("trending_titles", [])[:5]
    season       = snapshot.get("season", "")
    combined     = " ".join(titles)
    combined_low = combined.lower()

    for keywords, theme in _THEME_KEYWORD_MAP:
        if any(kw in combined_low for kw in keywords):
            return theme

    # Season bias as final tiebreaker before default
    for bias_theme in _SEASON_THEME_BIAS.get(season, []):
        if bias_theme in _VALID_THEMES:
            return bias_theme

    return "cozy_rain"


_TITLE_BENEFIT_VOCAB = ["study", "focus", "relax", "sleep", "chill", "unwind"]


def extract_title_benefit_signals(snapshot: dict, top_k: int = 3) -> list[str]:
    """Rank the benefit-keyword vocabulary (study/focus/relax/sleep/chill/
    unwind) by frequency in this week's real scraped competitor titles
    (snapshot['trending_titles']), so generated titles can lean toward
    whichever benefit words are actually resonating right now instead of a
    static uniform sample. Falls back to the static vocabulary order if no
    trend data exists yet or none of the vocabulary appears in it.
    """
    text = " ".join(snapshot.get("trending_titles", [])).lower()
    if not text:
        return _TITLE_BENEFIT_VOCAB[:top_k]
    counts = {w: text.count(w) for w in _TITLE_BENEFIT_VOCAB}
    if not any(counts.values()):
        return _TITLE_BENEFIT_VOCAB[:top_k]
    ranked = sorted(_TITLE_BENEFIT_VOCAB, key=lambda w: -counts[w])
    return ranked[:top_k]


# ── Music style hints ─────────────────────────────────────────────────────────

_MOOD_FROM_SEASON: dict[str, str] = {
    "spring": "uplifting",
    "summer": "uplifting",
    "autumn": "melancholic",
    "winter": "cozy",
}

_MUSIC_HINT_RULES: list[tuple[list[str], dict]] = [
    (["phonk"],                    {"subgenre": "lofi phonk",   "bpm_hint": "80-90"}),
    (["jazz", "bossa"],            {"subgenre": "lofi jazz",    "bpm_hint": "70-85"}),
    (["ambient", "sleep", "deep"], {"subgenre": "ambient lofi", "bpm_hint": "60-75"}),
    (["study", "focus", "work"],   {"subgenre": "study lofi",   "bpm_hint": "75-85"}),
]


def _extract_music_hints(snapshot: dict) -> dict:
    """
    Derive {bpm_hint, mood, subgenre} from trending_titles + season.
    """
    combined  = " ".join(snapshot.get("trending_titles", [])).lower()
    season    = snapshot.get("season", "")

    subgenre = "lofi hip hop"
    bpm_hint = "75-90"
    for keywords, attrs in _MUSIC_HINT_RULES:
        if any(kw in combined for kw in keywords):
            subgenre = attrs["subgenre"]
            bpm_hint = attrs["bpm_hint"]
            break

    mood = _MOOD_FROM_SEASON.get(season, "cozy")
    return {"bpm_hint": bpm_hint, "mood": mood, "subgenre": subgenre}


# ── Main entry point ──────────────────────────────────────────────────────────

def get_trend_snapshot(force_refresh: bool = False) -> dict:
    """
    Returns a TrendSnapshot dict (the *latest* snapshot), backed by an
    append-only history of dated snapshots in assets/trend_cache.json
    (see _load_history()/_save_history()/compute_trend_deltas()) so
    competitor video performance can be tracked over time instead of only
    ever seeing whatever the most recent run overwrote. Still cached for
    CACHE_TTL seconds -- a fresh-enough call just returns the latest
    snapshot without appending a new one.

    Keys:
      trending_titles   list[str]   — top-performing lofi titles (past 14 days)
      trending_tags     list[str]   — aggregated popular tags
      yt_videos         list[dict]  — full {title, channel, views, tags, duration}
                                      rows behind trending_titles (kept for
                                      compute_trend_deltas() view-count tracking)
      season            str         — current season
      seasonal_keywords list[str]   — month-specific search spikes
      fetched_at        str         — ISO timestamp
    """
    history = _load_history()

    # Return latest cached snapshot if fresh enough
    if not force_refresh and history:
        cached = history[-1]
        try:
            fetched_raw = cached.get("fetched_at", "2000-01-01T00:00:00+00:00")
            fetched_dt  = datetime.datetime.fromisoformat(fetched_raw)
            if fetched_dt.tzinfo is None:
                fetched_dt = fetched_dt.replace(tzinfo=datetime.timezone.utc)
            age = datetime.datetime.now(datetime.timezone.utc).timestamp() - fetched_dt.timestamp()
            if age < CACHE_TTL:
                print(f"  [Trends] using cached snapshot ({int(age/60)}m old)")
                return cached
        except Exception:
            pass

    print("  [Trends] fetching real-time trend data...")
    season      = _season()
    seasonal_kw = _seasonal_keywords()

    # Parallel fetch — YouTube Data API first (most reliable)
    yt_videos = fetch_yt_trending(max_results=20)
    trending_titles = [v["title"] for v in yt_videos]

    # Aggregate tags from trending videos — lofi-relevant terms only
    _LOFI_TAG_ALLOW = {
        "lofi", "lo-fi", "lo fi", "chill", "study", "focus", "ambient",
        "jazz", "beats", "hip hop", "relax", "sleep", "rain", "chillhop",
        "vaporwave", "phonk", "bossa", "neo soul", "bedroom", "instrumental",
        "playlist", "2025", "2026", "aesthetic", "night", "music",
    }
    tag_counts: dict[str, int] = {}
    for v in yt_videos:
        for t in v.get("tags", []):
            tl = t.lower()
            if any(kw in tl for kw in _LOFI_TAG_ALLOW):
                tag_counts[tl] = tag_counts.get(tl, 0) + 1
    trending_tags = [t for t, _ in sorted(tag_counts.items(), key=lambda x: -x[1])][:20]

    # Duration distribution in trending
    dur_dist: dict[str, int] = {}
    for v in yt_videos:
        d = v.get("duration", "unknown")
        dur_dist[d] = dur_dist.get(d, 0) + 1

    snapshot = {
        "trending_titles":    trending_titles,
        "trending_tags":      trending_tags,
        "trending_duration":  dur_dist,
        "yt_videos":          yt_videos,      # full rows incl. view counts -- see compute_trend_deltas()
        "season":             season,
        "seasonal_keywords":  seasonal_kw,
        "fetched_at":         _now_iso(),
    }

    snapshot["suggested_theme"] = suggest_thumbnail_theme(snapshot)
    snapshot["music_hints"]     = _extract_music_hints(snapshot)

    # Append to history on disk (not overwrite) so competitor performance
    # can be tracked snapshot-over-snapshot -- see compute_trend_deltas().
    history.append(snapshot)
    _save_history(history)
    print(f"  [Trends] snapshot saved ({len(trending_titles)} videos, season={season}, "
          f"history={len(history)})")
    return snapshot


if __name__ == "__main__":
    snap = get_trend_snapshot(force_refresh=True)
    print("\n=== TREND SNAPSHOT ===")
    print(f"Season: {snap['season']}")
    print(f"Seasonal keywords: {snap['seasonal_keywords']}")
    print(f"\nTop trending titles ({len(snap['trending_titles'])}):")
    for t in snap["trending_titles"][:10]:
        print(f"  • {t[:80]}")
    print(f"\nTop tags: {snap['trending_tags'][:10]}")
