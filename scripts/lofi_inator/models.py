"""Data models for the lofi-inator pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


def _slugify(s: str) -> str:
    """'Shape of You!' → 'shape-of-you'"""
    s = s.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s.strip())
    s = re.sub(r"-+", "-", s)
    return s[:80]


@dataclass(frozen=True)
class SongInfo:
    title: str
    artist: str
    source: str       # "spotify" | "lastfm" | "youtube_music"
    chart_rank: int
    artist_slug: str = ""
    title_slug: str = ""
    spotify_id: str | None = None
    lastfm_url: str | None = None

    def __post_init__(self) -> None:
        # Populate slugs if not provided (frozen — use object.__setattr__)
        if not self.artist_slug:
            object.__setattr__(self, "artist_slug", _slugify(self.artist))
        if not self.title_slug:
            object.__setattr__(self, "title_slug", _slugify(self.title))


@dataclass(frozen=True)
class SpotifyFeatures:
    tempo: float       # BPM
    key: int           # 0=C, 1=C#, ... 11=B (Pitch Class)
    mode: int          # 1=major, 0=minor
    energy: float      # 0.0-1.0
    valence: float     # 0.0-1.0 (sad→happy)
    danceability: float  # 0.0-1.0


@dataclass(frozen=True)
class MidiDNA:
    """
    Normalized musical parameters derived from a mainstream song.
    Keys map 1:1 to the `params` dict that generate_music_gemini.build_midi() reads,
    plus source metadata fields (ignored by build_midi via params.get() defaults).
    """
    # Source metadata (ignored by build_midi)
    source_title: str
    source_artist: str
    original_bpm: float
    dna_source: str    # "midi_parse" | "spotify_features" | "text_heuristic" | "groq_derive" | "fallback"

    # Params that build_midi() reads directly
    bpm: int           # lofi BPM = original * 0.67-0.73, clamped [62, 92]
    key: str           # "Am","Dm","Em","Gm","Cm","C","G","F"
    progression: int   # 0-30, index into PROGRESSIONS
    swing: float       # 0.62-0.70
    mood: str
    melody_density: str   # "sparse" | "medium" (build_midi reads as "density")
    melody_scale: str     # "pent"|"dorian"|"major_pent"|"major"|"lydian"|"mixo"|"phryg"
    bass_walking: bool
    drum_energy: str      # "low" | "medium" | "high"
    sub_genre: str        # one of _SUBGENRE_CONFIG keys
    drum_pattern_a: int
    drum_pattern_b: int

    # Markov chain extracted from scraped MIDI (None when DNA came from Spotify/Groq/fallback)
    # Keys are pitch-class ints (0-127); values are lists of successor pitch classes.
    # Use to generate Markov-influenced melodies that echo the source song's interval feel.
    markov_melody_nodes: dict | None = None


@dataclass(frozen=True)
class LofiCoverSEO:
    title: str
    description: str
    tags: list
    ref_id: str        # "lofi-inator:{artist_slug}:{title_slug}"
    artist: str
    song_title: str
    duration: str
    privacy: str = "public"
    category_id: str = "10"
    made_for_kids: bool = False
    theme: str = ""
