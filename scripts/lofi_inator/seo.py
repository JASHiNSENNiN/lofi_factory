"""
Cover-specific SEO generation for lofi-inator videos.
Generates song-attributed titles, descriptions, chapters, and tags.
"""

from __future__ import annotations

import datetime
import random

from .models import LofiCoverSEO, MidiDNA, SongInfo
from .registry import build_ref_id

# Title patterns — {title}, {artist}, {dur} are template vars
# Patterns without {dur} are used for "single" mode
_COVER_TITLE_PATTERNS_SHORT = [
    "{title} but it's 3am · lofi",
    "lofi hip hop · {title} slowed + reverb",
    "{title} but the beat dropped and everything got quieter · lofi",
    "{title} · lofi cover",
    "{artist} — {title} · lo-fi",
    "what if {title} was a lofi beat",
]

_COVER_TITLE_PATTERNS_LONG = [
    "{title} if you heard it from a café window · lofi {dur}",
    "{title} · {artist} lofi cover — {dur}",
    "what if {title} was a lofi beat · {dur}",
    "{title} slowed to 3am speed · lofi — {dur}",
    "{title} (lofi remix) — study & chill {dur}",
    "{artist} — {title} · lo-fi version {dur}",
    "lofi cover of {title} · for late nights — {dur}",
]

# Combined pool (used when duration is not "single")
_COVER_TITLE_PATTERNS = _COVER_TITLE_PATTERNS_SHORT + _COVER_TITLE_PATTERNS_LONG

_DESCRIPTION_HOOKS = [
    "Some songs just hit different when they're slowed down.",
    "Take a song you know. Now put it through a lofi filter. Now it's 3am.",
    "This is what {title} sounds like when the night gets quiet.",
    "The original is great. This version is for 2am.",
    "What if {title} grew up listening to J Dilla?",
    "Slowed, filtered, and left out in the rain.",
]

_CHAPTER_LABELS = [
    "signal found",
    "deep focus",
    "midnight filter",
    "slow burn",
    "the long version",
    "still going",
    "just one more loop",
]


def generate_cover_seo(
    song: SongInfo,
    midi_dna: MidiDNA,
    duration: str,
    theme: str,
) -> LofiCoverSEO:
    """Generate full SEO metadata for a lofi cover video."""
    ref_id = build_ref_id(song.artist_slug, song.title_slug)
    dur_short = _compact_duration(duration)
    is_single = duration == "single"

    title = _build_title(song, dur_short, is_single=is_single)
    description = _build_description(song, midi_dna, duration, title, ref_id)
    tags = _build_tags(song, midi_dna)

    return LofiCoverSEO(
        title=title,
        description=description,
        tags=tags,
        ref_id=ref_id,
        artist=song.artist,
        song_title=song.title,
        duration=duration,
        theme=theme,
    )


def _build_title(song: SongInfo, dur_short: str, is_single: bool = False) -> str:
    pool = _COVER_TITLE_PATTERNS_SHORT if is_single else _COVER_TITLE_PATTERNS
    pattern = random.choice(pool)
    title = pattern.format(
        title=song.title,
        artist=song.artist,
        dur=dur_short,
    )
    # Hard cap 80 chars — truncate song title if needed
    if len(title) <= 80:
        return title

    # Trim song.title to fit
    overhead = len(title) - len(song.title)
    max_song_len = max(10, 80 - overhead)
    short_title = song.title[:max_song_len].rstrip()
    return pattern.format(title=short_title, artist=song.artist, dur=dur_short)[:80]


def _build_description(
    song: SongInfo,
    midi_dna: MidiDNA,
    duration: str,
    video_title: str,
    ref_id: str,
) -> str:
    hook = random.choice(_DESCRIPTION_HOOKS).format(title=song.title)
    mood = midi_dna.mood
    duration_display = "lofi cover" if duration == "single" else duration

    chapters = _build_chapters(duration)
    chapters_str = "\n".join(f"{ts} — {label}" for ts, label in chapters)

    lines = [
        f"lofi cover of '{song.title}' by {song.artist} · lo-fi hip hop · {duration_display}",
        "",
        hook,
        f"lo-fi hip hop · {duration_display} · a softer version of something you already love.",
        f"{mood}",
        "",
        "⏱ CHAPTERS",
        chapters_str,
        "",
        "─────────────────────────────────────",
        "🔔 New lo-fi covers weekly — subscribe if this found you at the right time",
        "👍 Like if this hit different",
        "💬 Drop the song you want covered next in the comments",
        "",
        "Instrumental reinterpretation — freshly composed and synthesized. No audio from the original recording.",
        "",
        f"#lofi #lofihiphop #{song.title_slug.replace('-', '')[:25]} #{song.artist_slug.replace('-', '')[:20]}lofi #studymusic",
        "",
        ref_id,
    ]
    return "\n".join(lines)[:4900]


def _build_chapters(duration: str) -> list[tuple[str, str]]:
    """Generate timestamp chapters based on video duration."""
    if duration == "single":
        return [("0:00", "lofi cover")]
    duration_map = {
        "30 min": 1800, "45 min": 2700, "1 hour": 3600, "90 min": 5400,
        "2 hours": 7200, "3 hours": 10800, "4 hours": 14400,
        "8 hours": 28800, "10 hours": 36000, "all night": 28800,
    }
    total_secs = duration_map.get(duration, 7200)

    if total_secs <= 2700:
        count = 4
    elif total_secs <= 5400:
        count = 5
    elif total_secs <= 10800:
        count = 6
    else:
        count = 7

    labels = random.sample(_CHAPTER_LABELS, min(count, len(_CHAPTER_LABELS)))
    labels[0] = _CHAPTER_LABELS[0]  # always start with "signal found"

    chapters = []
    for i, label in enumerate(labels):
        secs = int(i * total_secs / len(labels))
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        ts = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        chapters.append((ts, label))

    return chapters


def _build_tags(song: SongInfo, midi_dna: MidiDNA) -> list[str]:
    """Build 12-tag list: song-specific + broad lofi anchors."""
    title_lower = song.title.lower()
    artist_lower = song.artist.lower()

    tags = [
        f"{title_lower} lofi",
        f"{artist_lower} lofi",
        f"{title_lower} slowed",
        f"{artist_lower} cover",
        "lofi hip hop",
        "lofi covers",
        "slowed reverb",
        "study music",
        "lofi beats 2026",
        "mainstream lofi cover",
        midi_dna.sub_genre.replace("_", " "),
        "chillhop",
    ]

    # Dedup while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    # Trim to fit YouTube 500-char tag limit
    while unique and sum(len(t) for t in unique) + len(unique) - 1 > 500:
        unique.pop()

    return unique[:12]


def _compact_duration(duration: str) -> str:
    """'2 hours' → '2hr', '90 min' → '90min', 'single' → ''"""
    if duration == "single":
        return ""
    return duration.replace(" hours", "hr").replace(" hour", "hr").replace(" min", "min")
