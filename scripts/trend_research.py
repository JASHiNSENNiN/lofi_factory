"""
trend_research.py — Real-time YouTube + AI trend snapshot for lo-fi content generation.

Pipeline:
  1. YouTube Data API  — search trending lofi videos (last 14 days, top view count)
                         fetch full details: titles, tags, view counts, durations
  2. Gemini 2.0 Flash  — Google Search grounding for what's resonating right now
                         (graceful fallback when quota exhausted)
  3. Groq analysis     — extract patterns + emotional themes from trending data
  4. Cache to assets/  — 6-hour TTL so we don't hammer APIs every run

Result: TrendSnapshot injected into concept + title generators for truly live content.
"""

import os
import json
import datetime
import random
import re

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(ROOT, "assets", "trend_cache.json")
CACHE_TTL  = 6 * 3600   # seconds

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"), override=False)
except ImportError:
    pass

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
GEMINI_KEY      = os.getenv("GEMINI_API_KEY")
GEMINI_BACKUP   = os.getenv("GEMINI_API_KEY_BACKUP")
GROQ_KEY        = os.getenv("GROQ_API_KEY")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def _season() -> str:
    month = datetime.datetime.now(datetime.timezone.utc).month
    if month in (3, 4, 5):  return "spring"
    if month in (6, 7, 8):  return "summer"
    if month in (9, 10, 11): return "autumn"
    return "winter"

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
            "lofi hip hop study music 2026",
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


# ── Source 1b: yt-dlp scraping ───────────────────────────────────────────────

def fetch_yt_dlp_trending(max_results: int = 15) -> list[dict]:
    """
    Scrape metadata from YouTube search using yt-dlp (no download).
    Returns list of {title, channel, views, duration, thumbnail_url, description_snippet}.
    Falls back to [] on any failure.
    """
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return []

    try:
        from scripts.ytdlp_util import flat_search_opts

        # extract_flat=True: pulls search-result metadata without resolving each
        # video's player API, which dodges YouTube's "confirm you're not a bot"
        # gate on server IPs. We only need title/channel/views here anyway.
        ydl_opts = flat_search_opts()
        results = []
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"ytsearch{max_results}:lofi hip hop study music",
                download=False,
            )
            entries = (info or {}).get("entries") or []
            for entry in entries:
                if not entry:
                    continue
                results.append({
                    "title":               entry.get("title", ""),
                    "channel":             entry.get("channel") or entry.get("uploader", ""),
                    "views":               entry.get("view_count") or 0,
                    "duration":            entry.get("duration_string") or entry.get("duration") or "",
                    "thumbnail_url":       entry.get("thumbnail", ""),
                    "description_snippet": (entry.get("description") or "")[:200],
                })
        return results
    except Exception as ex:
        print(f"  [Trends/yt-dlp] fetch failed: {ex}")
        return []


# ── Source 2: Gemini with Google Search grounding ─────────────────────────────

def fetch_gemini_trends() -> str | None:
    """
    Use Gemini 2.0 Flash with Google Search grounding to discover what's trending.
    Returns a short insight string, or None on failure/quota exhaustion.
    """
    for key in [GEMINI_KEY, GEMINI_BACKUP]:
        if not key:
            continue
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=key)
            resp   = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=(
                    f"Today is {datetime.datetime.now(datetime.timezone.utc).strftime('%B %d, %Y')}. "
                    "Search YouTube and the web for what lofi/study music is trending RIGHT NOW. "
                    "Focus on: (1) top-performing title patterns, (2) trending moods or aesthetics, "
                    "(3) specific activities or scenarios viewers are searching for, "
                    "(4) any cultural moments (season, events, memes) driving searches. "
                    "Be specific and concise — 150 words max. No fluff."
                ),
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.3,
                ),
            )
            return resp.text.strip()
        except Exception as ex:
            if "429" in str(ex) or "QUOTA" in str(ex).upper():
                continue  # try backup key
            print(f"  [Trends/Gemini] {ex}")
            return None
    return None   # both keys exhausted


# ── Source 3: Groq pattern analysis ──────────────────────────────────────────

def _groq_analyze_trends(trending_titles: list[str], season: str, seasonal_kw: list[str]) -> str | None:
    """
    Feed Groq the real trending titles and ask it to extract patterns + gaps.
    Returns a concise insight string (injected into concept prompt).
    """
    if not GROQ_KEY or not trending_titles:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_KEY)
        titles_block = "\n".join(f"  • {t}" for t in trending_titles[:12])
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            messages=[{"role": "user", "content": f"""
You are a YouTube lofi channel strategist. Here are the top-performing lofi videos uploaded in the last 14 days:

{titles_block}

It's currently {season} ({datetime.datetime.now(datetime.timezone.utc).strftime('%B %Y')}).
Seasonal search spikes: {', '.join(seasonal_kw[:4])}.

In 120 words max, answer:
1. What emotional patterns are working? (e.g. "late night struggle", "cozy autumn nostalgia")
2. What title structures are performing? (e.g. "scenario + duration", "japanese aesthetic + activity")
3. What GAPS exist — what ISN'T being made that listeners are probably searching for?
4. One specific concept that would be fresh and on-trend right now.

Be specific and actionable. No generic advice.
"""}],
        )
        return resp.choices[0].message.content.strip()
    except Exception as ex:
        print(f"  [Trends/Groq] {ex}")
        return None


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
    Checks the first 5 trending_titles, groq_analysis, and gemini_insight.
    Returns one of the valid theme names from _VALID_THEMES.
    """
    titles       = snapshot.get("trending_titles", [])[:5]
    groq_text    = snapshot.get("groq_analysis") or ""
    gemini_text  = snapshot.get("gemini_insight") or ""
    season       = snapshot.get("season", "")
    combined     = " ".join(titles) + " " + groq_text + " " + gemini_text
    combined_low = combined.lower()

    for keywords, theme in _THEME_KEYWORD_MAP:
        if any(kw in combined_low for kw in keywords):
            return theme

    # Season bias as final tiebreaker before default
    for bias_theme in _SEASON_THEME_BIAS.get(season, []):
        if bias_theme in _VALID_THEMES:
            return bias_theme

    return "cozy_rain"


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
    Derive {bpm_hint, mood, subgenre} from groq_analysis + trending_titles + season.
    """
    groq_text = snapshot.get("groq_analysis") or ""
    titles    = " ".join(snapshot.get("trending_titles", []))
    combined  = (groq_text + " " + titles).lower()
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
    Returns a TrendSnapshot dict, cached for CACHE_TTL seconds.

    Keys:
      trending_titles   list[str]   — top-performing lofi titles (past 14 days)
      trending_tags     list[str]   — aggregated popular tags
      gemini_insight    str|None    — Gemini search grounding summary
      groq_analysis     str|None    — Groq strategic analysis
      season            str         — current season
      seasonal_keywords list[str]   — month-specific search spikes
      fetched_at        str         — ISO timestamp
    """
    # Return cached snapshot if fresh enough
    if not force_refresh and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                cached = json.load(f)
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

    # yt-dlp supplemental scrape — deduplicate against API titles
    yt_dlp_videos = fetch_yt_dlp_trending(max_results=15)
    _existing_titles_lower = {t.lower() for t in trending_titles}
    for v in yt_dlp_videos:
        if v["title"].lower() not in _existing_titles_lower:
            trending_titles.append(v["title"])
            _existing_titles_lower.add(v["title"].lower())

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

    # Gemini/Groq trend commentary — opt-in failsafe only (LOFI_LLM_FAILSAFE=1).
    # suggest_thumbnail_theme()/_extract_music_hints() below already derive real
    # signal directly from the scraped trending_titles via keyword-rule matching,
    # so these are pure enrichment, not required for the pipeline to function.
    gemini_insight = None
    groq_analysis = None
    if os.getenv("LOFI_LLM_FAILSAFE") == "1":
        gemini_insight = fetch_gemini_trends()
        if gemini_insight:
            print(f"  [Trends] Gemini insight: {gemini_insight[:80]}...")

        groq_analysis = _groq_analyze_trends(trending_titles, season, seasonal_kw)
        if groq_analysis:
            print(f"  [Trends] Groq analysis complete")

    snapshot = {
        "trending_titles":    trending_titles,
        "trending_tags":      trending_tags,
        "trending_duration":  dur_dist,
        "yt_dlp_videos":      yt_dlp_videos,
        "gemini_insight":     gemini_insight,
        "groq_analysis":      groq_analysis,
        "season":             season,
        "seasonal_keywords":  seasonal_kw,
        "fetched_at":         _now_iso(),
    }

    snapshot["suggested_theme"] = suggest_thumbnail_theme(snapshot)
    snapshot["music_hints"]     = _extract_music_hints(snapshot)

    # Cache to disk
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    print(f"  [Trends] snapshot saved ({len(trending_titles)} videos, season={season})")
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
    if snap.get("groq_analysis"):
        print(f"\n=== GROQ ANALYSIS ===\n{snap['groq_analysis']}")
    if snap.get("gemini_insight"):
        print(f"\n=== GEMINI INSIGHT ===\n{snap['gemini_insight']}")
