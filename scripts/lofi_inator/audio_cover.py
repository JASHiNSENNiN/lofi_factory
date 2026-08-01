"""
audio_cover.py — Download original song and make a lofi version.

Pipeline:
  yt-dlp YouTube search → download WAV → asetrate slowdown → apply_lofi_fx → music/track_lofi_00.wav

Called by pipeline._process_song() before MIDI generation.
Returns path to track_lofi_00.wav or None (triggers MIDI fallback).
"""
from __future__ import annotations

import os
import subprocess
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
MUSIC_DIR = os.path.join(ROOT, "music")

# 85% speed + pitch — vinyl-slowed effect (both pitch and tempo drop together)
_SLOW_RATIO = 0.85


def make_audio_cover(song, dna) -> str | None:
    """
    Download original song from YouTube, slow it, apply lofi FX chain.
    Returns path to music/track_lofi_00.wav, or None if download fails.
    """
    print(f"  [audio_cover] Searching YouTube: {song.artist} — {song.title}")
    raw = _download_audio(song)
    if raw is None:
        return None

    slowed = None
    try:
        slowed = _slow_audio(raw)
        lofi_out = os.path.join(MUSIC_DIR, "track_lofi_00.wav")
        os.makedirs(MUSIC_DIR, exist_ok=True)
        from scripts.generate_music_gemini import apply_lofi_fx
        apply_lofi_fx(slowed, lofi_out, sub_genre=dna.sub_genre, bpm=dna.bpm, energy=dna.drum_energy)
        print(f"  [audio_cover] Lofi version ready")
        return lofi_out
    except Exception as e:
        print(f"  [audio_cover] Processing failed: {e}")
        return None
    finally:
        for path in filter(None, [raw, slowed]):
            try:
                os.unlink(path)
            except OSError:
                pass


def _download_audio(song) -> str | None:
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        print("  [audio_cover] yt-dlp not installed — pip install yt-dlp")
        return None

    import yt_dlp

    from scripts.ytdlp_util import download_opts, have_cookies

    query = f"{song.artist} - {song.title} official audio"
    tmp_dir = tempfile.mkdtemp()
    out_template = os.path.join(tmp_dir, "%(id)s.%(ext)s")

    ydl_opts = download_opts(out_template, audio_codec="wav")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"ytsearch1:{query}"])
        wavs = [os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir) if f.endswith(".wav")]
        return wavs[0] if wavs else None
    except Exception as e:
        hint = "" if have_cookies() else (
            " — server IPs are bot-gated; upload a cookies.txt in the web UI "
            "Settings tab (or set YTDLP_COOKIES) to enable downloads"
        )
        print(f"  [audio_cover] Download error: {e}{hint}")
        return None


def _slow_audio(input_wav: str) -> str:
    """asetrate slowdown — lowers pitch + tempo together (vinyl-slowed effect)."""
    out = input_wav.replace(".wav", "_slowed.wav")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", input_wav,
            "-af", f"asetrate=44100*{_SLOW_RATIO},aresample=44100",
            "-ar", "44100",
            out,
        ],
        check=True,
        capture_output=True,
    )
    return out
