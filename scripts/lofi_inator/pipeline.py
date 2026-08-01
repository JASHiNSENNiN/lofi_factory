"""
lofi-inator main pipeline:
  discover trending songs → extract musical DNA → generate lofi cover → upload → playlist
"""

from __future__ import annotations

import dataclasses
import glob
import os
import random
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)

from .discover import get_trending_songs, get_spotify_features
from .extract import extract_song_dna
from .models import MidiDNA, SongInfo
from .registry import add_to_playlist, build_ref_id, get_or_create_playlist, is_already_done, mark_done
from .seo import generate_cover_seo

# Duration → music track count (matches run.py:DURATION_MUSIC_COUNT)
_DURATION_MUSIC_COUNT: dict[str, int] = {
    "single":   1,
    "30 min":   2, "45 min": 3, "1 hour": 4, "90 min": 6,
    "2 hours":  8, "3 hours": 12, "4 hours": 15, "8 hours": 25, "all night": 25,
}

# Sub-genre → visual theme affinity (best-effort mood match)
_SUBGENRE_THEME: dict[str, str] = {
    "dark_lofi":      "midnight_cafe",
    "lofi_phonk":     "midnight_cafe",
    "ambient":        "blue_hour",
    "piano_lofi":     "winter_snow",
    "lofi_classical": "autumn_study",
    "chill_beats":    "blue_hour",
    "morning_lofi":   "spring_dawn",
    "summer_vibes":   "summer_lofi",
    "city_pop":       "neon_tokyo",
    "nujabes":        "cozy_rain",
    "hip_hop_lofi":   "purple_dusk",
    "neo_soul":       "amber_night",
    "lofi_rnb":       "amber_night",
    "bedroom_pop":    "bedroom_pop",
    "lofi_house":     "lofi_house",
    "vaporwave":      "vaporwave",
    "bossa_lofi":     "sakura_night",
    "jazz_cafe":      "cozy_rain",
    "lofi_jazz":      "cozy_rain",
    "chillhop":       "cozy_rain",
    "cozy_cafe":      "cozy_rain",
    "anime_lofi":     "sakura_night",
    "study_lofi":     "autumn_study",
    "lo_fi_funk":     "neon_tokyo",
}

_DEFAULT_THEME = "cozy_rain"


def run_lofi_inator(
    limit: int = 5,
    theme: str | None = None,
    duration: str = "single",
    dry_run: bool = False,
    youtube=None,
) -> list[dict]:
    """
    Full lofi-inator pipeline for `limit` songs.
    Returns list of result dicts: {song, status, video_url?, error?}.
    """
    print(f"\n[lofi-inator] Discovering trending songs (limit={limit})...")
    songs = get_trending_songs(limit * 2)  # fetch extra to account for skips

    if not songs:
        print("[lofi-inator] No songs discovered — check your API keys in .env")
        return []

    processed = 0
    results: list[dict] = []

    for song in songs:
        if processed >= limit:
            break

        print(f"\n[lofi-inator] [{processed+1}/{limit}] Processing: {song.artist} — {song.title}")

        # ── Duplicate check ──────────────────────────────────────
        if is_already_done(song.artist_slug, song.title_slug, youtube if not dry_run else None):
            print(f"  Skipping (already uploaded)")
            results.append({"song": song, "status": "skipped"})
            continue

        try:
            result = _process_song(song, theme, duration, dry_run, youtube)
            results.append(result)
            if result["status"] in ("uploaded", "saved"):
                processed += 1
        except Exception as e:
            print(f"  [lofi-inator] ERROR processing '{song.title}': {e}")
            results.append({"song": song, "status": "failed", "error": str(e)})

    return results


def _process_song(
    song: SongInfo,
    forced_theme: str | None,
    duration: str,
    dry_run: bool,
    youtube,
) -> dict:
    # ── Musical DNA extraction ───────────────────────────────────
    print(f"  Fetching Spotify features...")
    spotify_feats = get_spotify_features(song)
    if spotify_feats:
        print(f"  Spotify: BPM={spotify_feats.tempo:.0f} key={spotify_feats.key} mode={spotify_feats.mode}")

    print(f"  Extracting musical DNA...")
    midi_dna = extract_song_dna(song, spotify_feats)
    print(f"  DNA: bpm={midi_dna.bpm} key={midi_dna.key} sub={midi_dna.sub_genre} src={midi_dna.dna_source}")

    visual_theme = forced_theme or _SUBGENRE_THEME.get(midi_dna.sub_genre, _DEFAULT_THEME)

    # ── SEO generation ───────────────────────────────────────────
    cover_seo = generate_cover_seo(song, midi_dna, duration, visual_theme)
    print(f"  Title: {cover_seo.title}")

    # ── Music generation ─────────────────────────────────────────
    _clear_music_dir()
    from scripts.lofi_inator.audio_cover import make_audio_cover
    audio_path = make_audio_cover(song, midi_dna)
    if not audio_path:
        raise RuntimeError(f"Audio download failed for '{song.artist} — {song.title}' — skipping.")
    wav_files = [audio_path]

    # ── Visual generation ────────────────────────────────────────
    print(f"  Rendering {visual_theme} visual...")
    from scripts.visual_v2 import generate_visual
    vis_secs = 60
    visual_path, actual_theme = generate_visual(
        theme_name=visual_theme,
        duration_secs=vis_secs,
        visual_seed=random.randint(0, 9999),
        track_title=cover_seo.title,
        genre=midi_dna.sub_genre.replace("_", " "),
        use_ai_bg=True,
        regen_bg=False,
    )

    # ── Thumbnail ────────────────────────────────────────────────
    print(f"  Generating thumbnail...")
    thumbnail_path = _generate_thumbnail(actual_theme, duration, cover_seo.title)

    # ── Video assembly ───────────────────────────────────────────
    print(f"  Assembling video ({duration})...")
    from scripts.assemble_video import assemble
    video_path = assemble(
        theme_name=actual_theme,
        duration_label=duration,
        visual_path=visual_path,
    )

    if dry_run:
        print(f"  [SAVE ONLY] Saved locally (skipping upload): {video_path}")
        return {"song": song, "status": "saved", "title": cover_seo.title,
                "theme": actual_theme, "dna": midi_dna, "video_path": video_path}

    # ── Upload ───────────────────────────────────────────────────
    print(f"  Uploading to YouTube...")
    seo_dict = _seo_to_dict(cover_seo)
    from scripts.upload_youtube import get_authenticated_service, upload_video
    if youtube is None:
        youtube = get_authenticated_service()
    video_id, video_url = upload_video(youtube, video_path, seo_dict, thumbnail_path)
    print(f"  Uploaded: {video_url}")

    # ── Playlist ─────────────────────────────────────────────────
    playlist_id = ""
    try:
        playlist_id = get_or_create_playlist(youtube)
        add_to_playlist(youtube, playlist_id, video_id)
    except Exception as e:
        print(f"  Warning: playlist update failed: {e}")

    # ── Mark done ────────────────────────────────────────────────
    mark_done(
        artist_slug=song.artist_slug,
        title_slug=song.title_slug,
        video_id=video_id,
        video_url=video_url,
        original_artist=song.artist,
        original_title=song.title,
        lofi_title=cover_seo.title,
        playlist_id=playlist_id,
        source=song.source,
        dna_source=midi_dna.dna_source,
    )

    return {"song": song, "status": "uploaded", "video_url": video_url, "video_id": video_id}


def _dna_to_params(midi_dna: MidiDNA) -> dict:
    """
    Convert MidiDNA to the params dict that build_midi() reads.
    MidiDNA.bpm is already the lofi BPM — maps to params['bpm'].
    Extra MidiDNA fields (source_title, etc.) are ignored by build_midi() via .get() defaults.
    """
    d = dataclasses.asdict(midi_dna)
    # Rename MidiDNA-specific keys to match build_midi expectations
    # dna_source, source_title, source_artist, original_bpm → ignored by build_midi
    return d


def _seo_to_dict(cover_seo) -> dict:
    """Convert LofiCoverSEO to the dict format that upload_video() expects."""
    return {
        "title": cover_seo.title,
        "description": cover_seo.description,
        "tags": cover_seo.tags,
        "category_id": cover_seo.category_id,
        "privacy": cover_seo.privacy,
        "made_for_kids": cover_seo.made_for_kids,
        "ref_id": cover_seo.ref_id,
        "theme": cover_seo.theme,
        "duration": cover_seo.duration,
    }


def _clear_music_dir() -> None:
    """Remove all audio files from music/ before generating cover tracks.
    Ensures only DNA-guided tracks are assembled (no leftover from prior sessions).
    Note: not safe to call if another pipeline is running concurrently.
    """
    music_dir = os.path.join(ROOT, "music")
    for ext in ("*.wav", "*.mp3", "*.flac", "*.ogg"):
        for f in glob.glob(os.path.join(music_dir, ext)):
            try:
                os.remove(f)
            except OSError:
                pass


def _generate_thumbnail(theme: str, duration: str, title: str) -> str | None:
    try:
        try:
            from scripts.generate_thumbnail_cozy import generate_thumbnail
        except ImportError:
            from scripts.generate_thumbnail import generate_thumbnail
        result = generate_thumbnail(theme, duration, title)
        # generate_thumbnail_cozy returns (path, title) tuple; fallback returns path str
        return result[0] if isinstance(result, tuple) else result
    except Exception as e:
        print(f"  Warning: thumbnail generation failed: {e}")
        return None
