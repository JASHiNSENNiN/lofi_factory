"""
stream_live.py — Lo-fi Factory Live Stream
===========================================
Streams the lo-fi radio interface indefinitely to YouTube Live via RTMP.

Differences from file-based assemble:
  - No duration limit — runs until Ctrl+C
  - Visual loops forever (-stream_loop -1)
  - Music playlist loops forever (-stream_loop -1 on concat list)
  - CBR encode (YouTube RTMP requires constant bitrate)
  - ultrafast preset (real-time encoding on low-end hardware)
  - No audio fade-out
  - Output is FLV over RTMP, not MP4
  - Auto-reconnects on dropout with exponential backoff

Usage:
  # Stream key from environment variable (recommended)
  export YT_STREAM_KEY="xxxx-xxxx-xxxx-xxxx-xxxx"
  python scripts/stream_live.py

  # Or pass directly (visible in process list — less safe)
  python scripts/stream_live.py --key xxxx-xxxx-xxxx-xxxx-xxxx

  # With a specific theme and visual
  python scripts/stream_live.py --theme neon_tokyo
  python scripts/stream_live.py --visual visuals/bg_neon_tokyo_20240101.mp4

  # Test locally (no RTMP — writes to stream_test.mp4 for 60 seconds)
  python scripts/stream_live.py --test

Process supervision:
  This module's own reconnect loop (stream()) only recovers from ffmpeg
  dying or the RTMP connection dropping — it does NOT recover from the
  Python process itself crashing (e.g. an unhandled exception outside the
  reconnect loop, an OOM kill). Run it under a process supervisor with
  auto-restart (systemd `Restart=always`, pm2, supervisord, a Docker
  restart policy) so a crash of this script gets restarted from the
  outside; this file assumes that layer exists, it doesn't provide it.

Alerting:
  Set LOFI_STREAM_ALERT_WEBHOOK to a Slack/Discord-compatible incoming
  webhook URL to get pinged after repeated reconnect failures (opt-in,
  unset by default — see _send_alert()).
"""

import os
import re
import sys
import json
import signal
import subprocess
import threading
import time
import glob
import random
import argparse
import tempfile
import shutil

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load .env so stream key is available when running standalone
_env = os.path.join(ROOT, ".env")
if os.path.exists(_env):
    try:
        from dotenv import load_dotenv
        load_dotenv(_env, override=False)
    except ImportError:
        pass
MUSIC_DIR   = os.path.join(ROOT, "music")
VISUALS_DIR = os.path.join(ROOT, "visuals")
OUTPUT_DIR  = os.path.join(ROOT, "output")

# YouTube RTMP ingest
YT_RTMP_BASE = "rtmp://a.rtmp.youtube.com/live2"

# Optional disconnect alerting — opt-in only (same pattern as LOFI_LLM_FAILSAFE):
# unset by default, so a fresh checkout never makes an outbound network call it
# wasn't explicitly configured for. Any webhook that accepts a JSON POST with a
# "text" field works (Slack/Discord-compatible incoming webhook URL).
_ALERT_WEBHOOK       = os.environ.get("LOFI_STREAM_ALERT_WEBHOOK", "")
_ALERT_AFTER_ATTEMPTS = 5    # first alert once reconnects have failed this many times in a row
_ALERT_REPEAT_EVERY   = 10   # then re-alert every N more attempts if still down


def _send_alert(message: str) -> None:
    """Best-effort webhook ping — must never let an alerting failure affect
    the stream itself, so every failure mode here is swallowed silently."""
    if not _ALERT_WEBHOOK:
        return
    try:
        import requests
        requests.post(_ALERT_WEBHOOK, json={"text": f"[lofi-factory] {message}"}, timeout=5)
    except Exception:
        pass

# EQ zone geometry — 720p-proportional (2/3 of 1080p values).
# Stream processes entirely at 720p: scale happens FIRST in filtergraph,
# so EQ bars are generated at 720p size to match the scaled canvas.
# Original 1080p values: X=30, Y=600, W=1860, H=410
_EQ_X = 20
_EQ_Y = 400
_EQ_W = 1240
_EQ_H = 273

# Theme gradient colours (same as assemble_video.py)
_THEME_EQ_GRAD = {
    "cozy_rain":     ((80,  210, 255), (20,  60,  140)),
    "midnight_cafe": ((60,  240, 210), (15,  75,  100)),
    "purple_dusk":   ((195, 80,  255), (70,  20,  120)),
    "amber_night":   ((255, 195, 55),  (140, 70,  10)),
    "winter_snow":   ((165, 215, 255), (40,  80,  165)),
    "autumn_study":  ((255, 145, 35),  (140, 55,  5)),
    "spring_dawn":   ((255, 148, 195), (120, 40,  100)),
    "neon_tokyo":    ((255, 40,  195), (80,  8,   80)),
    "summer_lofi":   ((80,  235, 148), (15,  95,  48)),
    "blue_hour":     ((55,  145, 255), (10,  40,  140)),
    "forest_rain":   ((55,  215, 138), (8,   80,  35)),
    "sakura_night":  ((255, 148, 215), (115, 35,  105)),
    # New subgenre themes
    "vaporwave":      ((255, 60,  220), (100, 10,  100)),
    "lofi_house":     ((40,  180, 255), (10,  50,  140)),
    "lofi_classical": ((220, 185, 80),  (100, 80,  20)),
    "bedroom_pop":    ((255, 180, 140), (140, 80,  60)),
    "lofi_rnb":       ((255, 160, 60),  (140, 70,  10)),
}
_DEFAULT_EQ_GRAD = ((0, 200, 255), (0, 60, 140))

# Theme-matched ambient noise: (noise_color, amplitude, lpf_hz)
_THEME_AMBIENT = {
    "cozy_rain":     ("pink",  0.007, 550),
    "forest_rain":   ("pink",  0.008, 450),
    "winter_snow":   ("white", 0.003, 2500),
    "midnight_cafe": ("brown", 0.005, 750),
    "amber_night":   ("brown", 0.004, 700),
    "purple_dusk":   ("brown", 0.003, 800),
    "blue_hour":     ("pink",  0.004, 900),
    "neon_tokyo":    ("white", 0.003, 1400),
    "autumn_study":  ("brown", 0.004, 680),
    "spring_dawn":   ("pink",  0.005, 2200),
    "summer_lofi":   ("pink",  0.005, 2600),
    "sakura_night":  ("pink",  0.003, 950),
    # New subgenre themes
    "vaporwave":      ("brown", 0.004, 700),   # warm hazy nostalgia
    "lofi_house":     ("white", 0.003, 1200),  # urban, crisp
    "lofi_classical": ("brown", 0.002, 600),   # refined, minimal
    "bedroom_pop":    ("pink",  0.004, 2000),  # indie, airy
    "lofi_rnb":       ("brown", 0.005, 600),   # soulful, warm low-end
}
_DEFAULT_AMBIENT = ("brown", 0.003, 800)

# ── Helpers ───────────────────────────────────────────────────────────────────

def find_visual(theme_name=None, prefer_path=None, random_pick=False):
    if prefer_path and os.path.exists(prefer_path):
        return prefer_path
    pattern = f"bg_{theme_name}*.mp4" if theme_name else "bg_*.mp4"
    files = [f for f in glob.glob(os.path.join(VISUALS_DIR, pattern))
             if "_graded720" not in f]
    if not files:
        return None
    if random_pick and len(files) > 1:
        return random.choice(files)
    return max(files, key=os.path.getmtime)


def build_visual_list(tmp_dir, theme_name):
    """
    Pre-grade all theme visuals and write an ffmpeg concat playlist.
    Returns playlist path if multiple visuals found, else None (caller uses single path).
    Pre-grading is cached — only runs once per source file.

    Fast-start: already-cached visuals are used immediately; uncached visuals are
    pre-graded in a background thread and added to the playlist when ready.
    """
    pattern = f"bg_{theme_name}*.mp4" if theme_name else "bg_*.mp4"
    raw_files = [f for f in glob.glob(os.path.join(VISUALS_DIR, pattern))
                 if "_graded720" not in f]
    if not raw_files:
        return None

    # Split into instantly-available (cached) vs needs pre-grading
    cached, to_grade = [], []
    for f in raw_files:
        base = os.path.splitext(f)[0] + "_graded720.mp4"
        if os.path.exists(base) and os.path.getmtime(base) >= os.path.getmtime(f):
            cached.append(base)
        else:
            to_grade.append(f)

    graded = list(cached)

    if not graded:
        if not to_grade:
            return None
        # No cache at all — must block on the first visual so stream can start
        try:
            graded.append(pregrade_visual(to_grade.pop(0)))
        except Exception as e:
            print(f"  [stream] Pre-grade failed: {e}")
            return None

    if len(graded) <= 1 and not to_grade:
        return None  # single visual only — caller loops it directly

    list_path = os.path.join(tmp_dir, "visual_playlist.txt")

    def _write_playlist():
        shuffled = list(graded)
        random.shuffle(shuffled)
        with open(list_path, "w") as fh:
            for p in shuffled:
                fh.write(f"file '{os.path.abspath(p)}'\n")

    _write_playlist()
    print(f"  Visual playlist: {len(graded)} background(s) ready"
          + (f", {len(to_grade)} pre-grading in background" if to_grade else " (all cached)"))

    # Grade remaining visuals in background; update playlist when each finishes
    if to_grade:
        def _bg_grade():
            for f in to_grade:
                try:
                    g = pregrade_visual(f)
                    graded.append(g)
                    _write_playlist()
                    print(f"\n  [stream] Visual added to playlist: {os.path.basename(g)}")
                except Exception as e:
                    print(f"\n  [stream] BG pre-grade failed for {os.path.basename(f)}: {e}")
        threading.Thread(target=_bg_grade, daemon=True).start()

    return list_path


def build_music_list(tmp_dir):
    """Write an ffmpeg concat list from all music files in music/, shuffled.
    Returns (list_path, ordered_tracks) — tracks list is used by monitor thread."""
    exts = ("*.mp3", "*.wav", "*.flac", "*.ogg")
    files = []
    for ext in exts:
        # Exclude sidecar files
        files.extend(f for f in glob.glob(os.path.join(MUSIC_DIR, ext))
                     if not f.endswith(".meta.json"))
    if not files:
        raise FileNotFoundError(
            f"No music files found in {MUSIC_DIR}\n"
            "Generate tracks first: python run.py --skip-upload --skip-visual\n"
            "Or drop .mp3/.wav files into the music/ folder."
        )
    random.shuffle(files)
    list_path = os.path.join(tmp_dir, "stream_playlist.txt")
    with open(list_path, "w") as f:
        for p in files:
            f.write(f"file '{os.path.abspath(p)}'\n")
    print(f"  Playlist: {len(files)} track(s) (looping forever)")
    return list_path, files


def parse_track_meta(track_path):
    """Read sidecar .meta.json; fall back to cleaned filename."""
    meta_path = track_path + ".meta.json"
    if os.path.exists(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    name = os.path.splitext(os.path.basename(track_path))[0]
    name = re.sub(r'^track_lofi_\d+_?', '', name).strip('_').replace('_', ' ').title()
    return {"title": name or "lofi dreams", "genre": "lo-fi hip hop"}


def _get_track_duration(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip())
    except Exception:
        return 300.0


def _start_track_monitor(tracks, stop_event, on_track_change=None):
    """Background thread: cycles through tracks indefinitely, updating now-playing files.
    Reloads the track list from MUSIC_DIR after each full pass so newly generated
    tracks appear in the title rotation without restarting the stream.
    on_track_change(title, genre) is called each time a new track starts."""
    def _run():
        current = list(tracks)
        while not stop_event.is_set():
            if not current:
                time.sleep(5)
                continue
            for track_path in current:
                if stop_event.is_set():
                    return
                meta = parse_track_meta(track_path)
                print(f"\n  [now playing] {meta['title']}  ({meta['genre']})")
                if on_track_change:
                    try:
                        on_track_change(meta["title"], meta["genre"])
                    except Exception:
                        pass
                dur = _get_track_duration(track_path)
                elapsed = 0.0
                while elapsed < dur and not stop_event.is_set():
                    time.sleep(0.5)
                    elapsed += 0.5
            # Reload from disk after each full pass — picks up new bg-gen tracks
            exts = ("*.mp3", "*.wav", "*.flac", "*.ogg")
            fresh = []
            for ext in exts:
                fresh.extend(f for f in glob.glob(os.path.join(MUSIC_DIR, ext))
                             if not f.endswith(".meta.json"))
            if fresh:
                random.shuffle(fresh)
                current = fresh
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def _start_playlist_refresher(playlist_path, stop_event):
    """Background thread: rewrites the concat playlist every 60s to include newly generated tracks.
    ffmpeg's -reload 1 on the concat demuxer picks up the updated file at the next EOF."""
    def _run():
        while not stop_event.is_set():
            for _ in range(60):
                if stop_event.is_set():
                    return
                time.sleep(1)
            exts = ("*.mp3", "*.wav", "*.flac", "*.ogg")
            files = []
            for ext in exts:
                files.extend(f for f in glob.glob(os.path.join(MUSIC_DIR, ext))
                             if not f.endswith(".meta.json"))
            if files:
                random.shuffle(files)
                try:
                    with open(playlist_path, "w") as fh:
                        for p in files:
                            fh.write(f"file '{os.path.abspath(p)}'\n")
                    print(f"\n  [playlist] Refreshed: {len(files)} track(s)")
                except Exception as e:
                    print(f"\n  [playlist] Refresh error: {e}")
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


_BG_GEN_MAX_TRACKS  = 150  # prune oldest beyond this many to prevent disk fill
_RADIO_MIN_TRACKS   = 10   # minimum tracks before stream starts — ensures variety on day 1


def _prune_old_tracks():
    """Delete oldest tracks beyond _BG_GEN_MAX_TRACKS — called after each generation."""
    exts = ("*.mp3", "*.wav", "*.flac", "*.ogg")
    files = []
    for ext in exts:
        files.extend(f for f in glob.glob(os.path.join(MUSIC_DIR, ext))
                     if not f.endswith(".meta.json"))
    if len(files) <= _BG_GEN_MAX_TRACKS:
        return
    files.sort(key=os.path.getmtime)  # oldest first
    to_delete = files[:len(files) - _BG_GEN_MAX_TRACKS]
    for path in to_delete:
        try:
            os.remove(path)
            meta = path + ".meta.json"
            if os.path.exists(meta):
                os.remove(meta)
        except Exception:
            pass
    print(f"\n  [bg-gen] Pruned {len(to_delete)} old track(s) (keeping newest {_BG_GEN_MAX_TRACKS})")


def _warmup_music_library(concept_hint=None):
    """
    Block until music/ has at least _RADIO_MIN_TRACKS files.
    Generates tracks inline (not in a thread) so the stream only starts
    once there's real variety — like a radio station spinning up its library.
    """
    exts = ("*.mp3", "*.wav", "*.flac", "*.ogg")

    def _count():
        n = 0
        for ext in exts:
            n += len([f for f in glob.glob(os.path.join(MUSIC_DIR, ext))
                      if not f.endswith(".meta.json")])
        return n

    current = _count()
    if current >= _RADIO_MIN_TRACKS:
        return

    print(f"\n  [radio] Library has {current} track(s) — warming up to {_RADIO_MIN_TRACKS} before stream starts...")
    try:
        sys.path.insert(0, ROOT)
        from scripts.generate_music_gemini import generate_track
    except ImportError:
        print("  [radio] Cannot import generate_music_gemini — skipping warm-up")
        return

    idx = 0
    while _count() < _RADIO_MIN_TRACKS:
        try:
            print(f"  [radio] Generating warm-up track {idx + 1}/{_RADIO_MIN_TRACKS}...")
            generate_track(idx, concept_hint=concept_hint)
        except Exception as e:
            print(f"  [radio] Warm-up track {idx} failed: {e}")
        idx += 1

    print(f"  [radio] Library ready: {_count()} track(s) — starting stream\n")


def _start_bg_music_gen(stop_event, concept_hint=None):
    """Background thread: continuously generates new tracks while stream runs.
    Prunes oldest tracks beyond _BG_GEN_MAX_TRACKS to prevent disk fill on long runs."""
    def _run():
        try:
            sys.path.insert(0, ROOT)
            from scripts.generate_music_gemini import generate_track
        except ImportError:
            print("  [bg-gen] Could not import generate_music_gemini — skipping background generation")
            return

        idx = 10  # start at index 10 to avoid overwriting pre-generated 00-04
        while not stop_event.is_set():
            try:
                print(f"\n  [bg-gen] Generating track {idx:02d}...")
                generate_track(idx, concept_hint=concept_hint)
                idx += 1
                _prune_old_tracks()
                # Generation itself takes 1-3 min — no artificial pause needed
            except Exception as e:
                print(f"  [bg-gen] Error generating track {idx}: {e}")
                # Wait before retry
                for _ in range(60):
                    if stop_event.is_set():
                        return
                    time.sleep(1)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def pregrade_visual(visual_path):
    """
    Pre-apply scale + color grade to the visual file once, offline.
    The stream filtergraph then only does EQ overlay — no per-frame video work.
    Cached as  <original>_graded720.mp4  alongside the source file.
    """
    base    = os.path.splitext(visual_path)[0]
    graded  = base + "_graded720.mp4"
    src_mtime = os.path.getmtime(visual_path)
    if os.path.exists(graded) and os.path.getmtime(graded) >= src_mtime:
        print(f"  [stream] Pre-graded visual cached: {os.path.basename(graded)}")
        return graded

    print("  [stream] Pre-grading visual to 720p (one-time, ~30s)...")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning",
        "-i", visual_path,
        "-vf", (
            "scale=1280:720:flags=lanczos,"
            "colorbalance=rs=0.08:gs=0.04:bs=-0.05,"
            "eq=contrast=1.06:saturation=0.88,"
            "vignette=angle=0.628"        # full quality grade baked in
        ),
        "-c:v", "libx264", "-preset", "fast", "-crf", "16",
        "-an", "-y", graded,
    ]
    subprocess.run(cmd, check=True)
    print(f"  [stream] Pre-graded: {os.path.basename(graded)}")
    return graded


def build_eq_filtergraph(theme_name):
    """
    EQ filtergraph for live stream.
    Visual input [0:v] is already 720p + fully graded (via pregrade_visual).
    Real-time work: EQ bars from audio + dynamic now-playing title overlay.
    """
    top, bot = _THEME_EQ_GRAD.get(theme_name or "", _DEFAULT_EQ_GRAD)
    tr, tg, tb = top
    br, bg, bb = bot
    geq_r = f"'{tr}+({br}-{tr})*Y/H'"
    geq_g = f"'{tg}+({bg}-{tg})*Y/H'"
    geq_b = f"'{tb}+({bb}-{tb})*Y/H'"

    a_color, a_amp, a_lpf = _THEME_AMBIENT.get(theme_name or "", _DEFAULT_AMBIENT)

    return ";".join([
        # Visual is pre-graded 720p — pass through unchanged
        "[0:v]null[vgraded]",
        # Split music audio: one copy for EQ visualiser, one for ambient mix
        "[1:a]asplit=2[a_eq][a_mix]",
        # EQ bars generated from audio at 720p-proportional size (1240×273)
        (f"[a_eq]showfreqs=s={_EQ_W}x{_EQ_H}:mode=bar:fscale=log:ascale=sqrt"
         f":win_func=hann:averaging=1:colors=ffffff[eq_raw]"),
        # Colour gradient for EQ bars
        f"color=c=black:s={_EQ_W}x{_EQ_H}:r=24[blank]",
        f"[blank]geq=r={geq_r}:g={geq_g}:b={geq_b}[grad]",
        "[eq_raw][grad]blend=all_mode=multiply[eq_col]",
        # Key out black background, set alpha, overlay onto video
        "[eq_col]colorkey=0x000000:similarity=0.13:blend=0.06[eq_key]",
        "[eq_key]format=rgba,colorchannelmixer=aa=0.92[eq_final]",
        # Overlay EQ bars onto pre-graded 720p visual
        f"[vgraded][eq_final]overlay={_EQ_X}:{_EQ_Y}:format=auto[vout]",
        # Ambient audio: theme-matched noise mixed at inaudible-but-felt level
        f"[2:a]lowpass=f={a_lpf}[ambient]",
        "[a_mix][ambient]amix=inputs=2:weights='1 0.09':duration=first[aout]",
    ])


# ── Stderr health monitor ─────────────────────────────────────────────────────
# ffmpeg writes progress using \r (carriage return), not \n.
# readline() blocks until \n — it misses progress entirely.
# Solution: read raw bytes in chunks, split on both \r and \n.

_STALL_TIMEOUT = 30   # seconds without any ffmpeg output before killing


def _monitor_stderr(proc, stop_event, last_output_time):
    """
    Background thread — reads ffmpeg stderr byte-chunks.
    Updates last_output_time[] so watchdog can detect stalls.
    Prints progress in-place; errors on new lines.
    """
    buf = b""
    while not stop_event.is_set():
        try:
            chunk = proc.stderr.read(512)
        except Exception:
            break
        if not chunk:
            break
        buf += chunk
        last_output_time[0] = time.time()
        parts = re.split(b"[\r\n]", buf)
        buf = parts[-1]   # keep incomplete line
        for raw in parts[:-1]:
            line = raw.strip().decode("utf-8", errors="replace")
            if not line:
                continue
            if "fps=" in line or "speed=" in line or "bitrate=" in line:
                print(f"\r  [enc] {line[:120]}", end="", flush=True)
            elif any(k in line.lower() for k in
                     ("error", "failed", "refused", "timeout", "broken pipe", "connection")):
                print(f"\n  [ffmpeg] {line}")
    try:
        proc.stderr.read()
    except Exception:
        pass


# ── Single stream attempt ─────────────────────────────────────────────────────

def stream_once(visual_path, playlist_path, rtmp_url, theme_name=None, test_secs=None,
                tracks=None, title_updater=None, visual_playlist_path=None):
    """
    Launch one ffmpeg stream attempt.
    Returns ffmpeg exit code (0 = clean, non-zero = error/dropout).
    Includes watchdog: kills process if encoder stalls for >30s.
    tracks: ordered list of music file paths for the monitor thread.
    visual_playlist_path: if set, cycles through multiple pre-graded visuals.
    """
    # Pre-grade single visual if no playlist (cached — runs once per file)
    if not visual_playlist_path:
        visual_path = pregrade_visual(visual_path)
    fg = build_eq_filtergraph(theme_name)
    a_color, a_amp, _a_lpf = _THEME_AMBIENT.get(theme_name or "", _DEFAULT_AMBIENT)

    # Start now-playing monitor thread + playlist refresher
    monitor_stop = threading.Event()
    on_track_change = title_updater.set_track if title_updater else None
    if tracks:
        _start_track_monitor(tracks, monitor_stop, on_track_change=on_track_change)
    _start_playlist_refresher(playlist_path, monitor_stop)

    cmd = [
        "ffmpeg",
        # ── Global options — MUST come before all inputs ───────────────────────
        "-hide_banner",
        "-loglevel",      "warning",   # suppress info spam
        "-stats",                       # show progress (fps/speed) even at warning level
        "-filter_threads", "4",         # filtergraph thread pool — more cores for EQ+drawtext
        # ── Input 0: visual (single loop or cycling playlist) ────────────────
        "-stream_loop", "-1",
        *(["-f", "concat", "-safe", "0"] if visual_playlist_path else []),
        "-re",
        "-i", visual_playlist_path if visual_playlist_path else visual_path,
        # ── Input 1: music playlist (looped forever) ──────────────────────────
        # Note: no -reload flag — not supported in ffmpeg 8+. The playlist
        # refresher thread rewrites the file every 60s; ffmpeg picks it up on
        # reconnect or when stream_loop restarts the sequence.
        "-stream_loop", "-1",
        "-f", "concat", "-safe", "0",
        "-i", playlist_path,
        # ── Input 2: ambient noise (lavfi — runs for 24h, stream reconnects anyway) ──
        "-f", "lavfi", "-i", f"anoisesrc=d=86400:c={a_color}:a={a_amp}",
        # ── EQ + overlay + ambient mix filtergraph ─────────────────────────────
        "-filter_complex", fg,
        "-map", "[vout]",
        "-map", "[aout]",
        # ── Video encode — true CBR for stable YouTube RTMP ───────────────────
        "-c:v",        "libx264",
        "-profile:v",  "high",          # H.264 High profile — YouTube requirement
        "-level:v",    "4.1",           # Level 4.1 — handles 720p@60/1080p@30
        "-preset",     "ultrafast",     # minimum encoder CPU for i3-class hardware
        "-r",          "15",            # 15fps — lo-fi visual is near-static; halves encoder load
        "-b:v",        "2500k",         # YouTube 720p@15fps recommended bitrate
        "-minrate",    "2500k",         # CBR: minrate == bitrate == maxrate
        "-maxrate",    "2500k",
        "-bufsize",    "5000k",         # VBV buffer = 2× bitrate
        "-pix_fmt",    "yuv420p",       # required for broad decoder compatibility
        "-g",          "30",            # keyframe every 2s @ 15fps (YouTube ≤2s requirement)
        "-keyint_min", "30",
        "-sc_threshold", "0",           # no scene-cut keyframes — consistent GOP
        # nal-hrd=cbr: pads NAL stream to enforce CBR
        # force-cfr=1: constant frame rate
        # threads=2: libx264 ignores ffmpeg's -threads; 2 threads on i3-7100U
        "-x264-params", "nal-hrd=cbr:force-cfr=1:threads=4",
        # ── Audio encode ──────────────────────────────────────────────────────
        "-c:a",  "aac",
        "-b:a",  "160k",
        "-ar",   "48000",              # 48kHz — YouTube preferred sample rate
        "-ac",   "2",
    ]

    if test_secs:
        cmd += ["-t", str(test_secs)]
        output = os.path.join(OUTPUT_DIR, "stream_test.mp4")
        cmd += ["-f", "mp4", output]
        print(f"\n[STREAM TEST] Writing {test_secs}s to {output}")
    else:
        cmd += ["-f", "flv", rtmp_url]
        print(f"\n[STREAM] Pushing to YouTube... (Ctrl+C to stop)")

    last_output_time = [time.time()]
    stop_event = threading.Event()
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)
    monitor = threading.Thread(
        target=_monitor_stderr,
        args=(proc, stop_event, last_output_time),
        daemon=True,
    )
    monitor.start()

    try:
        while True:
            ret = proc.poll()
            if ret is not None:
                break
            # Watchdog: kill if stalled (no stderr output for _STALL_TIMEOUT seconds)
            if not test_secs:
                stalled = time.time() - last_output_time[0]
                if stalled > _STALL_TIMEOUT:
                    print(f"\n[STREAM] Encoder stalled {stalled:.0f}s — killing...")
                    proc.kill()
                    proc.wait()
                    break
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n[STREAM] Interrupted.")
        global _user_interrupted
        _user_interrupted = True
        stop_event.set()
        proc.terminate()
        proc.wait()
        return 0   # clean exit — do not reconnect
    finally:
        stop_event.set()
        monitor_stop.set()
        # Ensure ffmpeg process is always reaped — prevents zombie/leak on exception
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
                proc.wait()

    print()  # newline after in-place progress line

    if test_secs and proc.returncode == 0:
        print(f"[STREAM TEST] Done: {output}")

    return proc.returncode


# ── Stream with auto-reconnect ────────────────────────────────────────────────

_user_interrupted = False

def _set_interrupted(sig, frame):
    global _user_interrupted
    _user_interrupted = True

def stream(visual_path, playlist_path, rtmp_url, theme_name=None, test_secs=None,
           tracks=None, concept_hint=None, yt_setup_fn=None):
    """
    Run stream with automatic reconnection on dropout.
    Stream runs indefinitely — music generates in background while streaming.
    Exponential backoff: 5s, 10s, 20s, 40s, 60s (capped).
    Ctrl+C / SIGTERM stops reconnection immediately.

    yt_setup_fn: callable() -> yt_info dict.  Called ONCE at session start to create
                 (or reuse) a YouTube broadcast.  On dropout, ffmpeg reconnects to the
                 same RTMP URL — YouTube keeps the broadcast live while the encoder is
                 temporarily disconnected (same as 24/7 lo-fi channels / subathons).
    """
    global _user_interrupted
    _user_interrupted = False

    signal.signal(signal.SIGTERM, _set_interrupted)

    # Import YT manager once (may not be available)
    _yt_mgr = None
    if yt_setup_fn:
        try:
            sys.path.insert(0, ROOT)
            import scripts.youtube_live_manager as _yt_mgr
        except Exception as e:
            print(f"  [yt-api] Could not import youtube_live_manager: {e}")

    # Start background music generation (runs until Ctrl+C)
    bg_gen_stop = threading.Event()
    _start_bg_music_gen(bg_gen_stop, concept_hint=concept_hint)
    print("  [bg-gen] Background music generation started")

    # ── Create ONE broadcast for the entire session ───────────────────────────
    # On dropout, reconnect to the SAME RTMP URL — YouTube keeps the broadcast
    # live while the encoder is temporarily disconnected, so viewers never lose
    # the stream link (same principle as 24/7 lo-fi channels and subathons).
    current_rtmp  = rtmp_url
    title_updater = None
    active_bid    = None
    active_yt     = None
    stream_id     = None

    if _yt_mgr and yt_setup_fn:
        try:
            yt_info = yt_setup_fn()
            fresh_url = yt_info.get("rtmp_url", "")
            if fresh_url:
                current_rtmp = fresh_url
            active_yt = yt_info.get("youtube")
            active_bid = yt_info.get("broadcast_id")
            stream_id  = yt_info.get("stream_id")
            sched      = yt_info.get("scheduled_start")
            if active_yt and active_bid:
                title_updater = _yt_mgr.LiveTitleUpdater(active_yt, active_bid, sched)
                # Transition to live once ffmpeg connects (background thread)
                _yt_mgr.transition_to_live_async(active_yt, active_bid, stream_id)
        except Exception as e:
            print(f"  [yt-api] Broadcast setup failed: {e} — using fallback RTMP")

    if not test_secs and not current_rtmp:
        print("[STREAM] ERROR: No RTMP URL available — cannot stream.")
        print("  Auth setup:  python scripts/upload_youtube.py --auth")
        print("  Or set:      export YT_STREAM_KEY='xxxx-xxxx-xxxx-xxxx'")
        return

    attempt          = 0
    current_visual   = visual_path
    current_playlist = playlist_path
    current_tracks   = list(tracks) if tracks else []
    session_tmp      = None

    # Build visual playlist (pre-grades all theme backgrounds, cycles them)
    vis_tmp = tempfile.mkdtemp(prefix="lofi_vis_")
    visual_playlist = build_visual_list(vis_tmp, theme_name)

    try:
        while not _user_interrupted:
            exit_code = stream_once(
                current_visual, current_playlist, current_rtmp,
                theme_name, test_secs, tracks=current_tracks,
                title_updater=title_updater,
                visual_playlist_path=visual_playlist,
            )

            # Test mode or user interrupt — don't retry
            if test_secs or _user_interrupted:
                break

            if exit_code == 0:
                print("\n[STREAM] Clean exit. Restarting...")
            else:
                attempt += 1
                delay = min(5 * (2 ** (attempt - 1)), 60)
                print(f"\n[STREAM] Connection lost (exit={exit_code}). "
                      f"Reconnecting in {delay}s... (attempt {attempt}, Ctrl+C to stop)")
                if attempt == _ALERT_AFTER_ATTEMPTS or (
                    attempt > _ALERT_AFTER_ATTEMPTS
                    and (attempt - _ALERT_AFTER_ATTEMPTS) % _ALERT_REPEAT_EVERY == 0
                ):
                    _send_alert(f"stream has failed to reconnect {attempt} times in a row "
                                f"(last exit code {exit_code}) — still retrying")
                for _ in range(delay):
                    if _user_interrupted:
                        break
                    try:
                        time.sleep(1)
                    except KeyboardInterrupt:
                        _user_interrupted = True
                        break
                if _user_interrupted:
                    break

            if _user_interrupted:
                break

            # Rebuild music playlist to pick up new bg-gen tracks
            # Visual playlist is fixed (visuals don't generate during stream)
            if session_tmp:
                shutil.rmtree(session_tmp, ignore_errors=True)
            session_tmp = tempfile.mkdtemp(prefix="lofi_stream_")
            current_playlist, current_tracks = build_music_list(session_tmp)
            if not visual_playlist:
                # Single-visual fallback: rotate to a different file on reconnect
                new_visual = find_visual(theme_name, random_pick=True)
                if new_visual:
                    current_visual = new_visual
                    print(f"  [stream] New visual: {os.path.basename(current_visual)}")
            attempt = 0
    finally:
        bg_gen_stop.set()
        shutil.rmtree(vis_tmp, ignore_errors=True)
        if session_tmp:
            shutil.rmtree(session_tmp, ignore_errors=True)
        if title_updater:
            title_updater.stop()
        # End broadcast only on deliberate stop — not on reconnect
        if _yt_mgr and active_yt and active_bid:
            _yt_mgr.end_broadcast(active_yt, active_bid)

    if _user_interrupted:
        print("[STREAM] Stopped by user.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ALL_THEMES = [
        "cozy_rain", "midnight_cafe", "purple_dusk", "amber_night",
        "winter_snow", "autumn_study", "spring_dawn", "neon_tokyo",
        "summer_lofi", "blue_hour", "forest_rain", "sakura_night",
    ]

    parser = argparse.ArgumentParser(description="Lo-fi Factory — Live Stream to YouTube")
    parser.add_argument("--key", default=None,
                        help="YouTube stream key (default: $YT_STREAM_KEY env var)")
    parser.add_argument("--theme", choices=ALL_THEMES, default=None,
                        help="Visual theme (default: auto-detect from most recent visual)")
    parser.add_argument("--visual", default=None,
                        help="Path to a specific visual .mp4 (default: most recent in visuals/)")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: encode 60s to output/stream_test.mp4 instead of streaming")
    args = parser.parse_args()

    # Resolve visual + theme before anything else
    visual_path = find_visual(args.theme, prefer_path=args.visual)
    if not visual_path:
        print("ERROR: No visual found.\n"
              "  Generate one first: python run.py --skip-music --skip-upload\n"
              f"  Or drop a bg_*.mp4 file into {VISUALS_DIR}/")
        sys.exit(1)

    theme_name = args.theme
    if not theme_name:
        for t in ALL_THEMES:
            if t in os.path.basename(visual_path):
                theme_name = t
                break

    # Build YouTube setup callable — called before every stream attempt so a
    # fresh broadcast is created each time (handles YouTube's 12-hour limit).
    yt_setup_fn  = None
    fallback_rtmp = ""
    if not args.test:
        try:
            sys.path.insert(0, ROOT)
            from scripts.youtube_live_manager import setup_live_stream as _yt_setup
            _theme_cap = theme_name
            _key_cap   = args.key
            def yt_setup_fn():
                return _yt_setup(theme_name=_theme_cap, stream_key_override=_key_cap)
        except Exception as e:
            print(f"  [yt-api] Cannot load youtube_live_manager: {e}")

        if not yt_setup_fn:
            # Pure stream-key fallback (no API)
            stream_key = args.key or os.environ.get("YT_STREAM_KEY", "")
            if not stream_key:
                print("ERROR: No YouTube credentials found.\n"
                      "  Auth setup:  python scripts/upload_youtube.py --auth\n"
                      "  Or set:      export YT_STREAM_KEY='xxxx-xxxx-xxxx-xxxx'\n"
                      "  Or test:     python scripts/stream_live.py --test")
                sys.exit(1)
            fallback_rtmp = f"{YT_RTMP_BASE}/{stream_key}"

    print("=" * 60)
    print("  LO-FI FACTORY — LIVE STREAM")
    print(f"  Visual:  {os.path.basename(visual_path)}")
    print(f"  Theme:   {theme_name or '(unknown)'}")
    if args.test:
        print("  Output:  TEST — local file (60s)")
    elif yt_setup_fn:
        print("  Output:  YouTube Live (API-managed broadcast)")
    else:
        print("  Output:  YouTube Live (stream key only)")
    print("=" * 60)

    # Ensure there's a full variety pool before going live — skip for test mode
    if not args.test:
        _warmup_music_library()

    tmp_dir = tempfile.mkdtemp(prefix="lofi_stream_")
    try:
        playlist_path, tracks = build_music_list(tmp_dir)
        stream(
            visual_path=visual_path,
            playlist_path=playlist_path,
            rtmp_url=fallback_rtmp,
            theme_name=theme_name,
            test_secs=60 if args.test else None,
            tracks=tracks,
            yt_setup_fn=yt_setup_fn,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    main()
