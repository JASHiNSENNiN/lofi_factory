"""
publish.py — Lo-fi Factory  |  YouTube Upload & Live Stream Manager
=====================================================================
Standalone script for all YouTube publishing.  Completely separate from
run.py — use this after the pipeline has produced a video.

SUBCOMMANDS
  upload          Upload the latest (or specified) video as a regular upload
  live            Stream ONE existing video for a fixed duration (panel-
                  controlled, no auto-reconnect). For an indefinite 24/7
                  auto-reconnecting radio stream instead, use
                  `python run.py --stream` (scripts/stream_live.py).
  end             End an active live broadcast
  status          Show all active/upcoming broadcasts
  schedule        Schedule a future live broadcast (no stream yet)
  auto-service    Control the lofi-auto timer: a daily render+upload run
                  (default: midnight, configurable, 6h minimum interval —
                  see deploy/lofi-auto.timer / deploy/lofi-auto.service)

SETUP (one-time)
  1. Google Cloud Console → New Project
  2. Enable "YouTube Data API v3"
  3. Create OAuth 2.0 credentials  (Desktop application)
  4. Download → save as  lofi_factory/client_secret.json
  5. python publish.py --auth          (opens browser, saves token.json)

USAGE EXAMPLES
  python publish.py upload
  python publish.py upload --video output/lofi_XYZ.mp4 --title "Custom Title"
  python publish.py upload --privacy unlisted

  python publish.py live
  python publish.py live --video output/lofi_XYZ.mp4 --quality 720p15
  python publish.py live --title "lo-fi beats 24/7 🌙" --duration 14400

  python publish.py status
  python publish.py end
  python publish.py end --broadcast-id abc123

  python publish.py rename "new title here"
  python publish.py rename "new title" --broadcast-id abc123

  python publish.py auto-service status
  python publish.py auto-service schedule --start 0 --every-hours 6   # midnight, then every 6h
  python publish.py auto-service run-now
  python publish.py auto-service logs

DEPENDENCIES
  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
"""

import os
import re
import sys
import json
import time
import signal
import argparse
import glob
import subprocess
import datetime
import threading

import auto_service

ROOT         = os.path.dirname(os.path.abspath(__file__))
STATE_FILE   = os.path.join(ROOT, "live_state.json")   # persists active broadcast info
UPLOAD_LOG   = os.path.join(ROOT, "upload_log.json")

RTMP_BASE = "rtmp://a.rtmp.youtube.com/live2"

# ffmpeg quality presets for live streaming
# 720p15: recommended for free VPS (halves encode work vs 30fps, 1/4 pixels vs 1080p)
STREAM_PRESETS = {
    "720p15":   {"res": "1280x720",  "vb": "1500k", "buf": "3000k", "fps": 15, "x264_preset": "superfast"},
    "720p":     {"res": "1280x720",  "vb": "2500k", "buf": "5000k", "fps": 30, "x264_preset": "veryfast"},
    "1080p":    {"res": "1920x1080", "vb": "4500k", "buf": "9000k", "fps": 30, "x264_preset": "veryfast"},
    "1080p60":  {"res": "1920x1080", "vb": "6000k", "buf": "12000k","fps": 60, "x264_preset": "veryfast"},
}

# ── AUTH ────────────────────────────────────────────────────────────────────
# Delegates to scripts/upload_youtube.py — the OAuth flow used identically by
# run.py, scripts/analytics.py, scripts/stream_live.py and
# scripts/youtube_live_manager.py. Kept as a thin wrapper here so existing
# `get_youtube()` call sites throughout this file don't need to change.

def get_youtube():
    from scripts.upload_youtube import get_authenticated_service
    return get_authenticated_service()


# ── HELPERS ─────────────────────────────────────────────────────────────────

MIN_UPLOAD_SECS = 600   # refuse uploads shorter than 10 minutes by default


def find_latest(directory: str, pattern: str) -> str | None:
    files = sorted(glob.glob(os.path.join(directory, pattern)),
                   key=os.path.getmtime, reverse=True)
    return files[0] if files else None


def get_video_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def find_latest_valid_video(min_secs: float = MIN_UPLOAD_SECS) -> str | None:
    """Newest finished render that's at least min_secs long. Files touched in
    the last 10 minutes are skipped (a render may still be writing them), and
    nothing is deleted."""
    candidates = sorted(
        glob.glob(os.path.join(ROOT, "output", "lofi_*.mp4")),
        key=os.path.getmtime, reverse=True,
    )
    for path in candidates:
        if time.time() - os.path.getmtime(path) < 600:
            continue
        if get_video_duration(path) >= min_secs:
            return path
        print(f"  [upload] Skipping unreadable or short video: {os.path.basename(path)}")
    return None


def paired_asset(pattern: str, video_path: str) -> str | None:
    """The asset (seo_*.json / thumb_*.jpg) made in the same run as video_path:
    the newest one written before the video was finished. A/B alternates
    (*_alt.jpg) are never picked."""
    video_mtime = os.path.getmtime(video_path)
    candidates = [p for p in glob.glob(os.path.join(ROOT, "assets", pattern))
                  if not p.endswith("_alt.jpg") and os.path.getmtime(p) <= video_mtime + 60]
    return max(candidates, key=os.path.getmtime) if candidates else None


def load_seo(seo_path: str | None) -> dict:
    path = seo_path or find_latest(os.path.join(ROOT, "assets"), "seo_*.json")
    if not path or not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def append_upload_log(entry: dict):
    from scripts.fileutil import append_json_list
    append_json_list(UPLOAD_LOG, entry)


_live_state_lock = threading.Lock()   # guards live_state.json across threads


def save_live_state(data: dict):
    from scripts.fileutil import atomic_write_json
    with _live_state_lock:
        atomic_write_json(STATE_FILE, data)


def load_live_state() -> dict | None:
    with _live_state_lock:
        if not os.path.exists(STATE_FILE):
            return None
        with open(STATE_FILE) as f:
            try:
                return json.load(f)
            except Exception:
                return None


def clear_live_state():
    with _live_state_lock:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)


def format_duration(secs: int) -> str:
    h = secs // 3600
    m = (secs % 3600) // 60
    if h:
        return f"{h}h {m}m" if m else f"{h}h"
    return f"{m}m"


def parse_interval(spec: str) -> float:
    """Parse a loop interval like '90s', '45m', '6h', '2d', or a bare number of seconds."""
    s = str(spec).strip().lower()
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if s and s[-1] in units and s[:-1]:
        try:
            return float(s[:-1]) * units[s[-1]]
        except ValueError:
            pass
    try:
        return float(s)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid interval {spec!r} — use e.g. '90s', '45m', '6h', '2d', or a number of seconds"
        )


def _sleep_until_next_loop(tag: str, interval_secs: float):
    print(f"[{tag}] Sleeping {format_duration(int(interval_secs))} until next run "
          f"(Ctrl-C to stop)...")
    time.sleep(interval_secs)


# ── AUTO (generate + upload) ────────────────────────────────────────────────

# Unattended `auto` runs (systemd timer, no one present to watch/cancel) size
# their own duration dynamically instead of drawing from a fixed pool.
# History: first a hardcoded [1,2,3 hour] cap (2026-08-16, after an
# unconstrained pick drew "8 hours" and wedged the box for 23+ hours), then
# tightened to [45min,1hour] once a real run showed this box's encode only
# manages ~0.57x realtime -- but that number was itself just a guess baked
# into a constant, no different in kind from the mistake it was fixing.
# Confirmed 2026-08-17 the box can flip between VAAPI/software paths and
# real speed drifts with filter-chain complexity/load, so ANY hardcoded
# speed constant goes stale. Now fully dynamic: scripts/assemble_video.py
# measures and persists the real encode speed from every run's own ffmpeg
# -stats output (assets/.encode_speed_history.json), and _pick_auto_duration
# below reads that plus the *live* systemd TimeoutStartSec to compute
# whatever the biggest duration is that this box can actually finish right
# now -- self-corrects automatically if the box gets faster/slower/busier,
# no more manual re-tuning of a constant every time reality changes.
AUTO_FALLBACK_DURATION = "30 min"   # forced tier after repeated failures, below
AUTO_FALLBACK_AFTER_FAILURES = 2
# Time for everything except the final encode: the visual loop, SEO,
# thumbnail and upload (fixed), plus music generation, which grows with the
# number of tracks a duration needs (assemble_video.tracks_for_duration).
_AUTO_BASE_OVERHEAD_SECS = 1500
_AUTO_SECS_PER_TRACK = 60      # wall time per track with 3 parallel workers
_AUTO_SAFETY_FACTOR = 0.75     # use at most this share of the systemd timeout

_AUTO_STATE_FILE = os.path.join(ROOT, "assets", ".auto_run_state.json")


def _load_auto_state() -> dict:
    try:
        with open(_AUTO_STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"consecutive_failures": 0}


def _save_auto_state(state: dict) -> None:
    from scripts.fileutil import atomic_write_json
    atomic_write_json(_AUTO_STATE_FILE, state)


def _record_auto_result(success: bool) -> None:
    state = _load_auto_state()
    state["consecutive_failures"] = 0 if success else state.get("consecutive_failures", 0) + 1
    _save_auto_state(state)


def _live_timeout_start_secs(default: int = 14400) -> int:
    """The *actual currently-configured* TimeoutStartSec for lofi-auto.service,
    read live from systemd rather than assumed -- so this stays correct even
    if the unit file's timeout is ever re-tuned without touching this file.
    Falls back to `default` if systemd can't be queried (e.g. running outside
    the deploy, or in a test)."""
    try:
        out = subprocess.run(
            ["systemctl", "--user", "show", "lofi-auto.service", "-p", "TimeoutStartUSec"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        # Format is "TimeoutStartUSec=4h" / "...=1min 30s" / "...=infinity" etc.
        val = out.split("=", 1)[1] if "=" in out else ""
        if not val or val == "infinity":
            return default
        secs = 0
        for num, unit in re.findall(r"(\d+)(h|min|s|ms|us)", val):
            secs += int(num) * {"h": 3600, "min": 60, "s": 1, "ms": 0, "us": 0}[unit]
        return secs or default
    except Exception:
        return default


def _dynamic_max_safe_duration() -> str:
    """The biggest duration tier this box can actually finish encoding
    within the live systemd timeout, given its own real recently-measured
    encode speed -- see the module comment above AUTO_FALLBACK_DURATION."""
    from scripts.assemble_video import (DURATION_MAP, estimated_encode_speed,
                                        _vaapi_available, tracks_for_duration)
    speed = estimated_encode_speed(used_vaapi=_vaapi_available())
    budget = _live_timeout_start_secs() * _AUTO_SAFETY_FACTOR

    def needed(secs: int) -> float:
        return (_AUTO_BASE_OVERHEAD_SECS
                + tracks_for_duration(secs) * _AUTO_SECS_PER_TRACK
                + secs / max(speed, 0.01))

    tiers = sorted(
        ((label, secs) for label, secs in DURATION_MAP.items()
         if label != "all night"),
        key=lambda kv: kv[1],
    )
    fitting = [label for label, secs in tiers if needed(secs) <= budget]
    chosen = fitting[-1] if fitting else tiers[0][0]  # smallest tier as last resort
    print(f"[AUTO] Dynamic duration: measured speed {speed:.2f}x, "
          f"budget {budget / 60:.0f}min → picked {chosen!r}")
    return chosen


def _pick_auto_duration() -> str:
    """Duration for an unattended `auto` run: the biggest tier this box's
    own recently-measured encode speed says it can actually finish within
    the live timeout, or the single lightest tier after
    AUTO_FALLBACK_AFTER_FAILURES consecutive auto-run failures -- a real
    degrade-gracefully fallback rather than repeatedly re-computing a
    budget that's already been failing for some other reason."""
    state = _load_auto_state()
    if state.get("consecutive_failures", 0) >= AUTO_FALLBACK_AFTER_FAILURES:
        print(f"[AUTO] {state['consecutive_failures']} consecutive failures — "
              f"falling back to {AUTO_FALLBACK_DURATION} until a run succeeds.")
        return AUTO_FALLBACK_DURATION
    return _dynamic_max_safe_duration()


def _run_auto_once(args) -> bool:
    """Run the full generation pipeline then upload the result once. Returns True on success."""
    import glob as _glob

    output_dir = os.path.join(ROOT, "output")
    assets_dir = os.path.join(ROOT, "assets")

    # Snapshot existing files so we can identify what's NEW after generation
    before_videos = set(_glob.glob(os.path.join(output_dir, "lofi_*.mp4")))
    before_seo    = set(_glob.glob(os.path.join(assets_dir, "seo_*.json")))
    # The A/B alternate (thumb_*_alt.jpg) is written after the primary, so it
    # must be excluded here or "newest thumbnail" picks it as the primary.
    def _primary_thumbs():
        return {p for p in _glob.glob(os.path.join(assets_dir, "thumb_*.jpg"))
                if not p.endswith("_alt.jpg")}
    before_thumbs = _primary_thumbs()

    run_script = os.path.join(ROOT, "run.py")
    duration = getattr(args, "duration", None) or _pick_auto_duration()
    cmd = [sys.executable, run_script, "--skip-upload", "--duration", duration]
    if getattr(args, "theme", None):
        cmd += ["--theme", args.theme]
    if getattr(args, "sub_genre", None):
        cmd += ["--sub-genre", args.sub_genre]
    if getattr(args, "mood", None):
        cmd += ["--mood", args.mood]
    music_v2 = getattr(args, "music_v2", None)
    if music_v2 is True:
        cmd += ["--music-v2"]
    elif music_v2 is False:
        cmd += ["--no-music-v2"]

    print("[AUTO] Running generation pipeline (full — new music, visual, SEO, thumbnail)...")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("[AUTO] Generation failed — aborting upload")
        _record_auto_result(success=False)
        if not getattr(args, "loop", False):
            sys.exit(result.returncode)
        return False

    # Find the files that are new (didn't exist before the run)
    new_videos = set(_glob.glob(os.path.join(output_dir, "lofi_*.mp4"))) - before_videos
    new_seo    = set(_glob.glob(os.path.join(assets_dir, "seo_*.json")))    - before_seo
    new_thumbs = _primary_thumbs() - before_thumbs

    if not new_videos:
        print("[AUTO] No new video was created — aborting to avoid re-uploading old content.")
        _record_auto_result(success=False)
        if not getattr(args, "loop", False):
            sys.exit(1)
        return False

    # Pick newest among new files (should only be one)
    new_video = max(new_videos, key=os.path.getmtime)
    new_seo_f = max(new_seo,    key=os.path.getmtime) if new_seo    else None
    new_thumb = max(new_thumbs, key=os.path.getmtime) if new_thumbs else None

    print(f"\n[AUTO] Uploading newly generated video: {os.path.basename(new_video)}")
    upload_args = argparse.Namespace(
        video=new_video,
        seo=new_seo_f,
        thumb=new_thumb,
        title=getattr(args, "title", None),
        privacy=getattr(args, "privacy", None),
        schedule_at=getattr(args, "schedule_at", None),
        force=False,
    )
    try:
        cmd_upload(upload_args)
    except Exception:
        _record_auto_result(success=False)
        raise
    _record_auto_result(success=True)
    from scripts.cleanup import cleanup_after_upload
    cleanup_after_upload(ROOT, new_video)
    return True


def cmd_auto(args):
    if not getattr(args, "loop", False):
        _run_auto_once(args)
        return

    interval = parse_interval(args.interval)
    print(f"[AUTO] Looping forever — new video every {format_duration(int(interval))} "
          f"(Ctrl-C to stop)")
    while True:
        try:
            _run_auto_once(args)
        except Exception as e:
            print(f"[AUTO] Iteration failed: {e}")
        _sleep_until_next_loop("AUTO", interval)


# ── AUTO-SERVICE (control the standalone lofi-auto.service loop) ────────────

def cmd_auto_service(args):
    action = args.action

    if action == "status":
        st = auto_service.status()
        if not st["installed"]:
            print("[AUTO-SERVICE] lofi-auto.timer is not installed on this host.")
            print("               Run: bash deploy/setup.sh")
            return
        print(f"[AUTO-SERVICE] timer {'ARMED' if st['active'] else 'STOPPED'}"
              f"  (start at boot: {'yes' if st['enabled'] else 'no'})")
        print(f"               schedule: every {st['every_hours']}h, "
              f"starting {st['start_hour']:02d}:00")
        if st["next_run"]:
            print(f"               next run:  {st['next_run']}")
        if st["last_run"]:
            print(f"               last run:  {st['last_run']}")
        print(f"               running now: {'yes' if st['running_now'] else 'no'}")
        return

    if action == "schedule":
        cur_hour, cur_every = auto_service.get_schedule()
        start_hour = args.start if args.start is not None else cur_hour
        every_hours = args.every_hours if args.every_hours is not None else cur_every
        try:
            auto_service.set_schedule(start_hour, every_hours)
        except ValueError as e:
            print(f"[AUTO-SERVICE] error: {e}")
            sys.exit(1)
        print(f"[AUTO-SERVICE] schedule set: every {every_hours}h, starting {start_hour:02d}:00")
        return

    if action == "logs":
        os.execvp("journalctl", auto_service.logs_cmd(n=args.lines, follow=not args.no_follow))

    actions = {
        "start":    auto_service.start,
        "stop":     auto_service.stop,
        "enable":   lambda: auto_service.set_enabled(True),
        "disable":  lambda: auto_service.set_enabled(False),
        "run-now":  auto_service.run_now,
    }
    try:
        actions[action]()
    except RuntimeError as e:
        print(f"[AUTO-SERVICE] error: {e}")
        sys.exit(1)
    print(f"[AUTO-SERVICE] {action} ok.")


# ── DASHBOARD ───────────────────────────────────────────────────────────────

# ── SHORTS (repurpose a long-form video into a vertical Short) ──────────────

def cmd_shorts(args):
    """Delegates to scripts/generate_shorts.py's run_pipeline()."""
    from scripts.generate_shorts import run_pipeline

    youtube = None
    if not args.save_only:
        youtube = get_youtube()

    print(f"\n[shorts] video={args.video or 'latest'}  window={args.window_secs}s  "
          f"save_only={args.save_only}")

    result = run_pipeline(
        video_path=args.video,
        seo_path=args.seo,
        out_path=args.out,
        window_secs=args.window_secs,
        upload=not args.save_only,
        privacy=args.privacy,
        title_override=args.title,
        youtube=youtube,
        crosspost_platforms=args.crosspost,
    )

    print(f"\n[shorts] Clip: {result['clip_path']}")
    print(f"  Highlight window: {result['window']['start_sec']}s - {result['window']['end_sec']}s")
    print(f"  Title: {result['metadata']['title']}")
    if result["uploaded"]:
        print(f"  ✓ Uploaded: {result['url']}")
    else:
        print("  Not uploaded (--save-only)")
    if result["crosspost"]:
        print(f"  Cross-post: {result['crosspost']}")


# ── CHANNEL STATS (YPP progress) ────────────────────────────────────────────

def cmd_stats(args):
    """Pull channel stats and YPP progress from YouTube Data API."""
    youtube = get_youtube()

    # Channel statistics
    ch = youtube.channels().list(part="snippet,statistics", mine=True).execute()
    if not ch.get("items"):
        print("[STATS] No channel found for this account.")
        return

    info  = ch["items"][0]
    stats = info["statistics"]
    name  = info["snippet"]["title"]

    subs       = int(stats.get("subscriberCount", 0))
    views      = int(stats.get("viewCount",       0))
    vid_count  = int(stats.get("videoCount",      0))

    # YPP thresholds
    SUB_GOAL    = 1_000
    HOUR_GOAL   = 4_000
    # Watch hours require Analytics API (separate scope); estimate from views × avg session
    # For lofi, avg session ~45 min (0.75h). This is an estimate.
    est_watch_h = int(views * 0.75)

    sub_pct    = min(subs / SUB_GOAL * 100, 100)
    watch_pct  = min(est_watch_h / HOUR_GOAL * 100, 100)
    ypp_ready  = subs >= SUB_GOAL and est_watch_h >= HOUR_GOAL

    print(f"\n{'='*50}")
    print(f"  Channel: {name}")
    print(f"{'='*50}")
    print(f"  Subscribers:  {subs:,}  (need {SUB_GOAL:,} for YPP) — {sub_pct:.1f}%")
    print(f"  Total views:  {views:,}")
    print(f"  Videos:       {vid_count}")
    print(f"  Est. watch h: ~{est_watch_h:,}h  (need {HOUR_GOAL:,}h) — {watch_pct:.1f}%")
    print(f"{'='*50}")

    if ypp_ready:
        print("  ✅ YPP ELIGIBLE — Apply at youtube.com/monetization")
    else:
        subs_needed  = max(SUB_GOAL - subs, 0)
        hours_needed = max(HOUR_GOAL - est_watch_h, 0)
        print(f"  ⏳ Need ~{subs_needed:,} more subs + ~{hours_needed:,}h watch time")
        if subs_needed == 0:
            print("     Subscribers: ✅  |  Watch hours: focus here!")
        elif hours_needed == 0:
            print("     Watch hours: ✅  |  Subscribers: focus here!")

    # Recent uploads performance
    if vid_count > 0:
        recent = youtube.search().list(
            part="snippet", forMine=True, type="video",
            order="date", maxResults=5,
        ).execute()
        if recent.get("items"):
            print("\n  Recent uploads:")
            vid_ids = [i["id"]["videoId"] for i in recent["items"]]
            vdetail = youtube.videos().list(
                part="snippet,statistics", id=",".join(vid_ids)
            ).execute()
            for v in vdetail.get("items", []):
                title  = v["snippet"]["title"][:55]
                vviews = int(v["statistics"].get("viewCount", 0))
                likes  = int(v["statistics"].get("likeCount", 0))
                print(f"    {vviews:>6,} views  {likes:>4,} likes  {title}")

    print()


# ── ANALYTICS (per-video CTR + pillar feedback loop) ─────────────────────────

def cmd_analytics(args):
    """Sync YouTube Analytics per-video and optionally report or swap thumbnails."""
    if ROOT not in sys.path:
        sys.path.append(ROOT)
    from scripts.analytics import sync_analytics, report, swap_low_ctr_thumbnails

    data = sync_analytics()
    if args.report:
        report(data)
    if args.swap_thumbs:
        swap_low_ctr_thumbnails(data)


# Playlist auto-add on upload is handled by scripts.upload_youtube.upload_video()
# (shared with run.py/analytics.py/stream_live.py/etc — see cmd_upload above).


def cmd_playlist(args):
    """Create, list, or assign playlists. Playlist IDs auto-stored in upload log."""
    if not args.playlist_cmd:
        print("Usage: python publish.py playlist [list|create|add]")
        print("  list              — show all channel playlists with IDs")
        print("  create <title>    — create a new playlist")
        print("  add <vid> <pl>    — add video ID to playlist ID")
        return

    youtube = get_youtube()

    if args.playlist_cmd == "list":
        resp = youtube.playlists().list(
            part="snippet,contentDetails", mine=True, maxResults=50
        ).execute()
        items = resp.get("items", [])
        if not items:
            print("No playlists found.")
            return
        print(f"\n[PLAYLISTS] {len(items)} found:\n")
        for p in items:
            pid   = p["id"]
            title = p["snippet"]["title"]
            count = p["contentDetails"]["itemCount"]
            print(f"  {pid}  ({count:>3} videos)  {title}")
        print("\n  Add IDs to .env, e.g.: YT_PLAYLIST_ACTIVITY=PLxxx  (pillar-based -- see "
              "scripts/playlist_curation.py; legacy YT_PLAYLIST_STUDY/YT_PLAYLIST_SLEEP "
              "still work as a fallback)")

    elif args.playlist_cmd == "create":
        # Gated behind --confirm-create: playlist creation is channel-visible
        # and irreversible-ish (deleting one loses its curation), so it never
        # happens as a side effect -- see
        # scripts.playlist_curation.create_playlist_if_confirmed.
        from scripts.playlist_curation import create_playlist_if_confirmed
        created = create_playlist_if_confirmed(
            youtube, args.title, description=args.description or "",
            privacy=args.privacy or "public", confirm=args.confirm_create,
        )
        if created is None:
            print("[PLAYLIST] Not created -- pass --confirm-create to actually create a "
                  "channel-visible playlist on YouTube.")
            return
        print(f"[PLAYLIST] Created: {created['id']}  '{created['title']}'")
        print(f"  Add to .env, e.g.: YT_PLAYLIST_ACTIVITY={created['id']}")

    elif args.playlist_cmd == "add":
        youtube.playlistItems().insert(
            part="snippet",
            body={"snippet": {
                "playlistId": args.playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": args.video_id},
            }},
        ).execute()
        print(f"[PLAYLIST] Added {args.video_id} → {args.playlist_id}")


# ── UPLOAD ──────────────────────────────────────────────────────────────────

def cmd_upload(args):
    youtube = get_youtube()

    # Resolve video — auto-delete corrupt files; regenerate if nothing valid remains
    if args.video:
        video_path = args.video
        if not os.path.exists(video_path):
            print(f"[ERROR] File not found: {video_path}")
            sys.exit(1)
    else:
        video_path = find_latest_valid_video()
        if not video_path:
            print("[ERROR] No finished video in output/. Render one first: python run.py --skip-upload")
            sys.exit(1)

    # Pair the SEO file and thumbnail with this video, not with whatever is newest.
    args.seo = args.seo or paired_asset("seo_*.json", video_path)
    args.thumb = args.thumb or paired_asset("thumb_*.jpg", video_path)

    # Already-uploaded guard — check YouTube by ref_id embedded in description.
    # Immune to: title collisions, different devices, cross-machine runs.
    # Handles: deleted videos (ref gone → allow re-upload), API errors (fail open).
    if not getattr(args, "force", False):
        _seo_check = load_seo(args.seo)
        _ref_id    = _seo_check.get("ref_id", "")
        if _ref_id:
            try:
                print("[UPLOAD] Checking YouTube for duplicate (by ref_id)...")
                # Step 1: list recent 50 channel videos by date
                _search = youtube.search().list(
                    part="id", forMine=True, type="video",
                    maxResults=50, order="date",
                ).execute()
                _vid_ids = [i["id"]["videoId"] for i in _search.get("items", [])]
                if _vid_ids:
                    # Step 2: fetch descriptions in one batch call
                    _vresp = youtube.videos().list(
                        part="snippet", id=",".join(_vid_ids),
                    ).execute()
                    for _v in _vresp.get("items", []):
                        if _ref_id in _v["snippet"].get("description", ""):
                            _vid_url = f"https://www.youtube.com/watch?v={_v['id']}"
                            print(f"[UPLOAD] Already on YouTube: {_vid_url}")
                            print(f"  Title: {_v['snippet']['title']}")
                            print("  Use --force to upload again.")
                            sys.exit(0)
                print("[UPLOAD] No duplicate found — proceeding.")
            except Exception as _e:
                # Fail open: API errors must never block a legitimate upload
                print(f"[UPLOAD] Duplicate check failed ({_e}) — proceeding with upload.")

    # Duration guard (skip when --force passed)
    if not getattr(args, "force", False):
        dur = get_video_duration(video_path)
        if dur < MIN_UPLOAD_SECS:
            print(f"[ERROR] Video is only {dur:.0f}s ({dur/60:.1f} min). Use --force to upload anyway.")
            sys.exit(1)

    thumb_path = args.thumb
    seo        = dict(load_seo(args.seo))

    # CLI overrides on top of the SEO file
    if args.title:
        seo["title"] = args.title
    if args.privacy:
        seo["privacy"] = args.privacy
    if not seo.get("title"):
        print("[ERROR] No SEO file found for this video and no --title given; "
              "refusing to upload with placeholder metadata.")
        sys.exit(1)
    seo.setdefault("description", "Lo-fi beats.")
    seo.setdefault("tags", ["lofi", "chillhop", "study music"])

    # Scheduled publish: --schedule-at sets privacyStatus=private + publishAt
    schedule_at = getattr(args, "schedule_at", None)
    if schedule_at:
        # Normalise to RFC3339 UTC format required by YouTube API
        schedule_at = schedule_at.replace("+00:00", "").rstrip("Z")
        if "T" not in schedule_at:
            print("[ERROR] --schedule-at must be ISO format: 2026-05-16T20:00:00")
            sys.exit(1)
        schedule_at = schedule_at + ".000Z"

    print(f"\n[UPLOAD] {os.path.basename(video_path)}")
    print(f"  Title:   {seo['title']}")
    print(f"  Privacy: {'private (scheduled)' if schedule_at else seo.get('privacy', 'public')}")
    print(f"  Tags:    {', '.join(seo['tags'][:6])}...")

    from scripts.upload_youtube import upload_video
    video_id, url = upload_video(youtube, video_path, seo, thumb_path, publish_at=schedule_at)

    # Log
    append_upload_log({
        "type":             "upload",
        "video_id":         video_id,
        "url":              url,
        "title":                    seo["title"],
        "title_variants":           seo.get("title_variants", [seo["title"]]),
        "title_variant_strategies": seo.get("title_variant_strategies", []),
        "title_chosen_idx":         seo.get("title_chosen_idx", 0),
        "title_chosen_strategy":    seo.get("title_chosen_strategy"),
        "pillar":           seo.get("pillar", ""),
        "concept":          seo.get("concept", ""),
        "seo_ref":          seo.get("ref_id", ""),
        "video_file":       os.path.basename(video_path),
        # Composition-selection feedback — see scripts/analytics.py's
        # sub_genre_weights()/bpm_bucket_weights()/engine_weights(). Defaults
        # keep this from crashing on an older-format seo dict.
        "sub_genre":        seo.get("sub_genre", ""),
        "bpm":              seo.get("bpm"),
        "music_engine":     seo.get("music_engine") or "v1",
        # Which thumbnail actually got uploaded -- needed so
        # analytics.swap_low_ctr_thumbnails() can find the matching
        # thumb_*_alt.jpg by exact name instead of guessing.
        "thumb_file":       os.path.basename(thumb_path) if thumb_path else None,
        # Actual measured length, not just the requested --duration label --
        # feeds analytics.duration_weights() so duration choice can eventually
        # be informed by watch-time performance the same way pillar choice is.
        "duration_secs":    get_video_duration(video_path),
        "timestamp":        datetime.datetime.now(datetime.timezone.utc).isoformat(),
        # Present only for --schedule-at uploads (privacyStatus=private +
        # publishAt) -- lets the webui Calendar page (webui/app.py's
        # view_calendar) distinguish "already public" from "scheduled to go
        # public later" without re-deriving it from privacy alone.
        "scheduled_at":     schedule_at,
    })

    print(f"\n✓ Upload complete: {url}")
    return video_id, url


# ── AUTO TITLE ──────────────────────────────────────────────────────────────

def _generate_live_title() -> str:
    """
    Generate a unique live broadcast title using the SEO concept engine.
    Hard 30s timeout — if APIs hang, falls back to default immediately.
    Returns empty string on any failure (caller uses its own fallback).
    """
    import concurrent.futures

    def _inner():
        sys.path.insert(0, ROOT)
        from scripts.generate_seo import pick_concept, build_title

        trends = None
        try:
            from scripts.trend_research import get_trend_snapshot
            trends = get_trend_snapshot()
        except Exception:
            pass

        concept = pick_concept(trends)
        title = build_title(concept, "all night")
        return title.replace("all night", "24/7 live").strip()[:100]

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(_inner)
        try:
            return future.result(timeout=30)
        except concurrent.futures.TimeoutError:
            print("  [auto-title] Timed out after 30s — using default title")
            return ""
        except Exception as e:
            print(f"  [auto-title] Failed ({e}) — using default title")
            return ""


# ── MIDNIGHT REFRESH ─────────────────────────────────────────────────────────

def _generate_live_description(concept: dict) -> str:
    """Build a personalized live-stream description from a concept dict."""
    try:
        from scripts.generate_seo import _build_setting_story, DESCRIPTION_HOOKS, TAGS_DURATION
        import random

        city   = concept.get("city") or ""
        time_l = concept.get("time_label", "")
        mood   = concept.get("mood_line", "chill")

        # Build context dict matching the keys build_description() uses
        concept_ctx = dict(concept)
        concept_ctx["city_phrase"] = f"Somewhere in {city}" if city else "wherever you are"
        concept_ctx["time_phrase"] = time_l if time_l else "late"
        concept_ctx["duration"]    = "all night"

        # DESCRIPTION_HOOKS is a list of format string templates
        hook_template = random.choice(DESCRIPTION_HOOKS)
        try:
            hook = hook_template.format(**concept_ctx)
        except KeyError:
            hook = mood

        story    = _build_setting_story(concept_ctx)
        # Use 'all night' pool (space-separated, not underscore)
        tag_pool = TAGS_DURATION.get("all night", TAGS_DURATION.get("10 hours", []))
        tags     = " ".join(random.sample(tag_pool, min(8, len(tag_pool)))) if tag_pool else ""

        parts = [hook, story, "🎵 lo-fi beats • 24/7 live stream"]
        if tags:
            parts.append(tags)
        return "\n\n".join(parts)

    except Exception as e:
        print(f"  [midnight] description build failed ({e}) — using generic")
        return "lo-fi beats • chill music to study, work, and relax • 24/7 live"


def _do_midnight_refresh(broadcast_id: str):
    """Generate a fresh title + description and push it to the live broadcast."""
    try:
        from scripts.generate_seo import pick_concept, build_title
        from scripts.youtube_live_manager import get_youtube_service
        # save_live_state / load_live_state are defined in publish.py itself

        youtube = get_youtube_service()
        if not youtube:
            print("  [midnight] No YouTube credentials — skipping refresh")
            return

        trends = None
        try:
            from scripts.trend_research import get_trend_snapshot
            trends = get_trend_snapshot()
        except Exception:
            pass

        concept = pick_concept(trends)
        title   = build_title(concept, "all night")
        title   = title.replace("all night", "24/7 live").strip()[:100]
        description = _generate_live_description(concept)

        # scheduledStartTime is required by the update API
        resp  = youtube.liveBroadcasts().list(part="snippet", id=broadcast_id).execute()
        items = resp.get("items", [])
        if not items:
            print("  [midnight] Broadcast not found — skipping refresh")
            return
        scheduled_start = items[0]["snippet"]["scheduledStartTime"]

        youtube.liveBroadcasts().update(
            part="snippet",
            body={
                "id": broadcast_id,
                "snippet": {
                    "title":              title,
                    "description":        description,
                    "scheduledStartTime": scheduled_start,
                },
            }
        ).execute()

        state = load_live_state()
        if state and state.get("broadcast_id") == broadcast_id:
            state["title"] = title
            save_live_state(state)

        print(f"  [midnight] Broadcast refreshed → \"{title}\"")

    except Exception as e:
        print(f"  [midnight] Refresh failed: {e}")


def _midnight_refresh_loop(broadcast_id: str):
    """Daemon thread: sleeps until 00:00:05 then refreshes title + description."""
    while True:
        now           = datetime.datetime.now(datetime.timezone.utc)
        next_midnight = (now + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=5, microsecond=0
        )
        sleep_secs = (next_midnight - now).total_seconds()
        print(f"  [midnight] Next refresh in {sleep_secs/3600:.1f}h  "
              f"({next_midnight.strftime('%Y-%m-%d %H:%M')})")
        time.sleep(sleep_secs)
        try:
            _do_midnight_refresh(broadcast_id)
        except Exception as e:
            print(f"  [midnight] Refresh failed (stream continues): {e}")


# ── LIVE ────────────────────────────────────────────────────────────────────

def _create_broadcast(youtube, title: str, description: str,
                      scheduled_start: str, privacy: str) -> tuple[str, str]:
    """Create a LiveBroadcast. Returns (broadcast_id, broadcast_title)."""
    body = {
        "snippet": {
            "title":              title,
            "description":        description,
            "scheduledStartTime": scheduled_start,
        },
        "status": {
            "privacyStatus":          privacy,
            "selfDeclaredMadeForKids": False,
        },
        "contentDetails": {
            "enableAutoStart": True,
            "enableAutoStop":  True,
            "enableDvr":       True,
            "recordFromStart": True,
            "latencyPreference": "ultraLow",
        },
    }
    resp = youtube.liveBroadcasts().insert(part="snippet,status,contentDetails",
                                           body=body).execute()
    return resp["id"], resp["snippet"]["title"]


def _create_stream(youtube, title: str) -> tuple[str, str]:
    """Create a LiveStream. Returns (stream_id, stream_key)."""
    body = {
        "snippet": {"title": title},
        "cdn": {
            "frameRate":    "30fps",
            "ingestionType": "rtmp",
            "resolution":   "1080p",
        },
    }
    resp = youtube.liveStreams().insert(part="snippet,cdn", body=body).execute()
    stream_id  = resp["id"]
    stream_key = resp["cdn"]["ingestionInfo"]["streamName"]
    return stream_id, stream_key


def _bind_broadcast(youtube, broadcast_id: str, stream_id: str):
    youtube.liveBroadcasts().bind(
        id=broadcast_id, part="id,contentDetails",
        streamId=stream_id
    ).execute()


def _wait_for_stream_active(youtube, stream_id: str, timeout: int = 120):
    """Poll until stream status is 'active' (ffmpeg is sending data)."""
    print("  Waiting for stream to go active", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp   = youtube.liveStreams().list(part="status", id=stream_id).execute()
        if not resp.get("items"):
            time.sleep(5)
            continue
        status = resp["items"][0]["status"]["streamStatus"]
        if status == "active":
            print(" ✓")
            return True
        print(".", end="", flush=True)
        time.sleep(5)
    print(" [TIMEOUT]")
    return False


def _transition_broadcast(youtube, broadcast_id: str, target_status: str):
    youtube.liveBroadcasts().transition(
        broadcastStatus=target_status,
        id=broadcast_id,
        part="id,status"
    ).execute()


def _start_ffmpeg_stream(video_path: str, stream_key: str, preset: dict) -> subprocess.Popen:
    """Launch ffmpeg to loop video → RTMP. Returns the Popen object."""
    rtmp_url = f"{RTMP_BASE}/{stream_key}"
    cmd = [
        "ffmpeg",
        "-re",
        "-stream_loop", "-1",          # loop forever
        "-i", video_path,
        # Video — no -tune zerolatency (disables B-frames, wastes bandwidth on pre-recorded loops)
        "-c:v", "libx264",
        "-preset", preset["x264_preset"],
        "-b:v", preset["vb"],
        "-maxrate", preset["vb"],
        "-bufsize", preset["buf"],
        "-pix_fmt", "yuv420p",
        "-g", str(preset["fps"] * 2),   # keyframe every 2s
        "-r", str(preset["fps"]),
        "-vf", f"fps={preset['fps']},scale={preset['res']}",
        # Audio
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-ac", "2",
        # Output
        "-f", "flv",
        rtmp_url,
    ]
    # stderr → log file (not PIPE — unread pipes deadlock when buffer fills ~10 min)
    log_path = os.path.join(ROOT, "ffmpeg_stream.log")
    log_f    = open(log_path, "w")
    print(f"  Streaming → {rtmp_url[:50]}...")
    print(f"  ffmpeg log: {log_path}")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log_f)
    except FileNotFoundError:
        log_f.close()
        print("[ERROR] ffmpeg not found — install: sudo apt install ffmpeg")
        sys.exit(1)
    except Exception as e:
        log_f.close()
        print(f"[ERROR] Failed to start ffmpeg: {e}")
        sys.exit(1)
    proc._log_file = log_f   # stored so _end_broadcast can close it
    return proc


def cmd_live(args):
    """
    Stream ONE existing finished video, looped, for a fixed --duration via the
    YouTube Broadcast API. Owns its own broadcast lifecycle and live_state.json
    schema (including ffmpeg_pid) that `publish.py end` and the web panel
    directly depend on to monitor/kill the stream — this is intentionally NOT
    delegated to scripts/stream_live.py, which is a different tool: an
    indefinite, auto-reconnecting 24/7 stream that continuously generates new
    music in the background (used by `run.py --stream`). If ffmpeg drops here,
    the broadcast ends rather than reconnecting — use stream_live.py for that.
    """
    youtube = get_youtube()

    # Resolve files
    video_path = args.video or find_latest(os.path.join(ROOT, "output"), "lofi_*.mp4")
    seo        = load_seo(args.seo)
    preset     = STREAM_PRESETS.get(args.quality, STREAM_PRESETS["720p15"])

    if not video_path or not os.path.exists(video_path):
        print("[ERROR] No video found. Run run.py first, or pass --video path/to/video.mp4")
        sys.exit(1)

    if args.title:
        title = args.title
    else:
        print("  Generating broadcast title...")
        title = (_generate_live_title()
                 or seo.get("title")
                 or "lo-fi beats • 24/7 chill music 🌙")
    description = seo.get("description", "Cozy lo-fi music streaming 24/7.")
    privacy     = args.privacy or "public"

    # Scheduled start = now (or +30s for buffer)
    now_utc = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=30)
    scheduled_start = now_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    print("\n[LIVE] Setting up broadcast...")
    print(f"  Title:   {title}")
    print(f"  Video:   {os.path.basename(video_path)}")
    print(f"  Quality: {args.quality}")
    print(f"  Privacy: {privacy}")

    # 1. Create broadcast
    broadcast_id, broadcast_title = _create_broadcast(
        youtube, title, description, scheduled_start, privacy)
    print(f"  Broadcast created: {broadcast_id}")

    # 2. Create stream
    stream_id, stream_key = _create_stream(youtube, f"lofi_stream_{broadcast_id[:8]}")
    print(f"  Stream created:    {stream_id}")

    # 3. Bind
    _bind_broadcast(youtube, broadcast_id, stream_id)
    print("  Bound broadcast ↔ stream")

    # 4. Start ffmpeg
    ffmpeg_proc = _start_ffmpeg_stream(video_path, stream_key, preset)

    # 5. Wait for stream to go active, then transition to live
    active = _wait_for_stream_active(youtube, stream_id, timeout=300)
    if not active:
        print("[WARN] Stream not active after 5 min — check ffmpeg & stream key")
        print("       Attempting transition anyway...")

    try:
        _transition_broadcast(youtube, broadcast_id, "testing")
        time.sleep(5)
        _transition_broadcast(youtube, broadcast_id, "live")
        print("  ✓ Broadcast is LIVE")
    except Exception as e:
        print(f"  [ERROR] Transition failed: {e}")
        print("          Check YouTube Studio — broadcast may need manual start")
        print("          Manage: https://studio.youtube.com/channel/broadcast")

    watch_url = f"https://www.youtube.com/watch?v={broadcast_id}"
    manage_url = "https://studio.youtube.com/channel/broadcast"
    print(f"\n  Watch:  {watch_url}")
    print(f"  Manage: {manage_url}")

    # Persist state
    state = {
        "broadcast_id": broadcast_id,
        "stream_id":    stream_id,
        "stream_key":   stream_key,
        "ffmpeg_pid":   ffmpeg_proc.pid,
        "title":        title,
        "video_file":   os.path.basename(video_path),
        "watch_url":    watch_url,
        "started_at":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    save_live_state(state)

    # Start midnight title + description refresh (daemon — exits when stream ends)
    t_refresh = threading.Thread(
        target=_midnight_refresh_loop,
        args=(broadcast_id,),
        daemon=True,
        name="midnight-refresh",
    )
    t_refresh.start()
    print("  Midnight refresh scheduled (title + description updates at 00:00 daily)")

    # Log
    append_upload_log({
        "type":         "live",
        "broadcast_id": broadcast_id,
        "url":          watch_url,
        "title":        title,
        "video_file":   os.path.basename(video_path),
        "timestamp":    datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })

    # Monitor until Ctrl+C or duration exceeded
    max_secs = args.duration or (24 * 3600)   # default 24h
    print(f"\n  Streaming... (max {format_duration(max_secs)} | Ctrl+C to end cleanly)")

    def _shutdown(sig=None, frame=None):
        print("\n\n[LIVE] Ending broadcast...")
        _end_broadcast(youtube, broadcast_id, ffmpeg_proc)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    deadline = time.time() + max_secs
    while time.time() < deadline:
        ret = ffmpeg_proc.poll()
        if ret is not None:
            print(f"\n[LIVE] ffmpeg exited (code {ret}) — ending broadcast")
            _end_broadcast(youtube, broadcast_id, ffmpeg_proc)
            return
        # Heartbeat every 5 min: refresh token + check broadcast status
        time.sleep(300)
        try:
            resp   = youtube.liveBroadcasts().list(part="status", id=broadcast_id).execute()
            status = resp["items"][0]["status"]["lifeCycleStatus"] if resp["items"] else "unknown"
            _started = datetime.datetime.fromisoformat(state["started_at"])
            if _started.tzinfo is None:
                _started = _started.replace(tzinfo=datetime.timezone.utc)
            elapsed = format_duration(int(time.time() - _started.timestamp()))
            print(f"  [{elapsed}] Status: {status}")
        except Exception:
            pass

    print("\n[LIVE] Duration limit reached — ending broadcast")
    _end_broadcast(youtube, broadcast_id, ffmpeg_proc)


def _end_broadcast(youtube, broadcast_id: str, ffmpeg_proc: subprocess.Popen | None = None):
    """Transition broadcast to complete and kill ffmpeg."""
    if ffmpeg_proc and ffmpeg_proc.poll() is None:
        ffmpeg_proc.terminate()
        try:
            ffmpeg_proc.wait(timeout=10)
        except Exception:
            ffmpeg_proc.kill()
        print("  ffmpeg stopped.")
    # Close log file handle stored by _start_ffmpeg_stream
    if ffmpeg_proc and hasattr(ffmpeg_proc, '_log_file'):
        try:
            ffmpeg_proc._log_file.close()
        except Exception:
            pass

    try:
        _transition_broadcast(youtube, broadcast_id, "complete")
        print(f"  Broadcast {broadcast_id} → complete.")
    except Exception as e:
        print(f"  [WARN] Could not transition to complete: {e}")

    clear_live_state()


def _is_ffmpeg(pid: int) -> bool:
    """Guard against PID reuse: only signal a PID that is still ffmpeg."""
    try:
        with open(f"/proc/{pid}/comm", encoding="utf-8") as f:
            return f.read().strip() == "ffmpeg"
    except OSError:
        return False


def cmd_end(args):
    broadcast_id = args.broadcast_id

    # If no ID given, load from state file
    if not broadcast_id:
        state = load_live_state()
        if not state:
            print("[ERROR] No active broadcast found. Pass --broadcast-id explicitly.")
            print("  To list broadcasts: python publish.py status")
            sys.exit(1)
        broadcast_id = state["broadcast_id"]
        ffmpeg_pid   = state.get("ffmpeg_pid")
        print(f"[END] Ending broadcast {broadcast_id}  (from state file)")

        # Stop the local encoder first, so it stops even when YouTube is
        # unreachable or the token has expired.
        if ffmpeg_pid and _is_ffmpeg(ffmpeg_pid):
            try:
                os.kill(ffmpeg_pid, signal.SIGTERM)
                print(f"  Stopped ffmpeg PID {ffmpeg_pid}")
            except ProcessLookupError:
                pass   # already dead
    else:
        print(f"[END] Ending broadcast {broadcast_id}")

    try:
        _transition_broadcast(get_youtube(), broadcast_id, "complete")
        print("  Broadcast ended.")
    except (Exception, SystemExit) as e:
        print(f"  [WARN] Couldn't mark the broadcast complete on YouTube ({e}); "
              "YouTube ends it on its own once the stream stops.")

    clear_live_state()
    print("  Done.")


# ── STATUS ───────────────────────────────────────────────────────────────────

def cmd_status(args):
    youtube = get_youtube()

    print("\n[STATUS] Active / upcoming broadcasts\n")
    for broadcast_filter in ["active", "upcoming"]:
        resp = youtube.liveBroadcasts().list(
            part="snippet,status,contentDetails",
            broadcastStatus=broadcast_filter,
            maxResults=10,
        ).execute()
        items = resp.get("items", [])
        if not items:
            print(f"  No {broadcast_filter} broadcasts.")
            continue
        print(f"  {broadcast_filter.upper()}:")
        for item in items:
            bid   = item["id"]
            title = item["snippet"]["title"]
            stat  = item["status"]["lifeCycleStatus"]
            start = item["snippet"].get("scheduledStartTime", "")
            url   = f"https://www.youtube.com/watch?v={bid}"
            print(f"    [{bid}] {title}")
            print(f"           Status: {stat}  |  Start: {start}")
            print(f"           {url}")
        print()

    # Local state
    state = load_live_state()
    if state:
        print("  LOCAL STATE (live_state.json):")
        print(f"    Broadcast: {state['broadcast_id']}")
        print(f"    Title:     {state['title']}")
        print(f"    Video:     {state['video_file']}")
        print(f"    Started:   {state['started_at']}")
        print(f"    Watch:     {state['watch_url']}")
        pid = state.get("ffmpeg_pid")
        if pid:
            alive = os.path.exists(f"/proc/{pid}")
            print(f"    ffmpeg:    PID {pid} {'(running)' if alive else '(not running)'}")
    print()


# ── DELETE ───────────────────────────────────────────────────────────────────

def cmd_delete(args):
    youtube = get_youtube()
    video_id = args.video_id
    # Confirm before deleting
    if not args.yes:
        print(f"  About to permanently delete video: https://youtu.be/{video_id}")
        confirm = input("  Type 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            print("  Cancelled.")
            return
    youtube.videos().delete(id=video_id).execute()
    print(f"  Deleted: {video_id}")


# ── RENAME ───────────────────────────────────────────────────────────────────

def cmd_rename(args):
    youtube = get_youtube()

    broadcast_id = args.broadcast_id
    if not broadcast_id:
        state = load_live_state()
        if not state:
            print("[ERROR] No active broadcast found. Pass --broadcast-id explicitly.")
            print("  To list broadcasts: python publish.py status")
            sys.exit(1)
        broadcast_id = state["broadcast_id"]

    new_title = args.title

    # Fetch current broadcast to get scheduledStartTime (required by update API)
    try:
        resp = youtube.liveBroadcasts().list(
            part="snippet", id=broadcast_id
        ).execute()
        items = resp.get("items", [])
        if not items:
            print(f"[ERROR] Broadcast {broadcast_id} not found.")
            sys.exit(1)
        scheduled_start = items[0]["snippet"].get("scheduledStartTime", "")
    except Exception as e:
        print(f"[ERROR] Could not fetch broadcast: {e}")
        sys.exit(1)

    # Update title
    try:
        youtube.liveBroadcasts().update(
            part="snippet",
            body={
                "id": broadcast_id,
                "snippet": {
                    "title": new_title[:100],
                    "scheduledStartTime": scheduled_start,
                },
            }
        ).execute()
    except Exception as e:
        print(f"[ERROR] Rename failed: {e}")
        sys.exit(1)

    print(f"[RENAME] Broadcast {broadcast_id}")
    print(f"  Title → {new_title[:100]}")

    # Update local state file if present
    state = load_live_state()
    if state and state.get("broadcast_id") == broadcast_id:
        state["title"] = new_title[:100]
        save_live_state(state)


# ── LOG ──────────────────────────────────────────────────────────────────────

def cmd_log(args):
    if not os.path.exists(UPLOAD_LOG):
        print("No upload log yet.")
        return
    with open(UPLOAD_LOG) as f:
        log = json.load(f)
    n = args.tail or len(log)
    print(f"\n[LOG] Last {n} entries\n")
    for entry in log[-n:]:
        ts   = entry.get("timestamp", "")[:16]
        kind = entry.get("type", "upload").upper()
        url  = entry.get("url", "")
        title = entry.get("title", "")
        print(f"  {ts}  [{kind}]  {title}")
        print(f"           {url}")
    print()


# ── SCHEDULE (future live) ────────────────────────────────────────────────────

def cmd_schedule(args):
    youtube = get_youtube()
    seo     = load_seo(args.seo)

    title       = args.title or seo.get("title", "lo-fi beats • 24/7 🌙")
    description = seo.get("description", "Cozy lo-fi music.")
    privacy     = args.privacy or "public"

    # Parse scheduled time
    if args.at:
        # Expect ISO format like "2026-03-22T20:00:00" (local → UTC assumed)
        scheduled_start = args.at + ".000Z"
    else:
        # Default: 1 hour from now
        future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        scheduled_start = future.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    print("\n[SCHEDULE] Creating scheduled broadcast")
    print(f"  Title:  {title}")
    print(f"  Start:  {scheduled_start}")
    print(f"  Privacy: {privacy}")

    broadcast_id, broadcast_title = _create_broadcast(
        youtube, title, description, scheduled_start, privacy)
    stream_id, stream_key = _create_stream(youtube, f"lofi_stream_{broadcast_id[:8]}")
    _bind_broadcast(youtube, broadcast_id, stream_id)

    watch_url = f"https://www.youtube.com/watch?v={broadcast_id}"
    print(f"\n  Broadcast scheduled: {broadcast_id}")
    print(f"  Watch URL:           {watch_url}")
    print("  Stream key saved to live_state.json")
    print("\n  When ready to go live:")
    print("    python publish.py live --video <video.mp4>  (will use saved stream key)")

    save_live_state({
        "broadcast_id": broadcast_id,
        "stream_id":    stream_id,
        "stream_key":   stream_key,
        "ffmpeg_pid":   None,
        "title":        title,
        "video_file":   None,
        "watch_url":    watch_url,
        "scheduled_at": scheduled_start,
        "started_at":   None,
    })

    append_upload_log({
        "type":         "scheduled",
        "broadcast_id": broadcast_id,
        "url":          watch_url,
        "title":        title,
        "scheduled_at": scheduled_start,
        "timestamp":    datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })


# ── ENTRY POINT ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="publish.py",
        description="Lo-fi Factory — YouTube Upload & Live Stream Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--auth", action="store_true",
                        help="Run OAuth flow and save token (run once after setup)")

    sub = parser.add_subparsers(dest="cmd", metavar="COMMAND")

    # ── auto ─────────────────────────────────────────────────────
    p_auto = sub.add_parser("auto", help="Generate a fresh video then upload to YouTube")
    p_auto.add_argument("--theme",       default=None, help="Visual theme (default: random)")
    p_auto.add_argument("--duration",    default=None, help='Video duration e.g. "2 hours" (default: run.py default)')
    p_auto.add_argument("--title",       default=None, help="Override video title")
    p_auto.add_argument("--privacy",     choices=["public", "unlisted", "private"], default=None)
    p_auto.add_argument("--schedule-at", dest="schedule_at", default=None,
                        help="Schedule publish UTC ISO: 2026-05-16T17:00:00 "
                             "(Tue-Thu 17:00 UTC = noon EST is optimal for study music)")
    p_auto.add_argument("--loop", action="store_true",
                        help="Keep generating+uploading forever, sleeping --interval between runs")
    p_auto.add_argument("--interval", default="6h",
                        help="Sleep between loop iterations, e.g. '90m', '6h', '2d' (default: 6h). "
                             "Only used with --loop")
    # Composition overrides, forwarded straight through to the run.py subprocess
    # call in _run_auto_once() -- kept in sync with run.py's own --sub-genre/
    # --mood/--music-v2 flags so the webui's "Render + Upload" path (which
    # shells out to `publish.py auto`) can expose the same controls as
    # "Render only" (which shells out to run.py directly).
    p_auto.add_argument("--sub-genre",   dest="sub_genre", default=None,
                        help="Force a specific sub-genre (default: auto). See config/genres/.")
    p_auto.add_argument("--mood",        default=None,
                        help="Free-text mood/concept phrase override for the music generator")
    p_auto.add_argument("--music-v2",    dest="music_v2", action=argparse.BooleanOptionalAction,
                        default=None,
                        help="Use the experimental v2 composer (default: v1)")

    # ── upload ───────────────────────────────────────────────────
    p_up = sub.add_parser("upload", help="Upload video as a regular YouTube video")
    p_up.add_argument("--video",   help="Path to video file (default: latest in output/)")
    p_up.add_argument("--seo",     help="Path to SEO JSON (default: latest in assets/)")
    p_up.add_argument("--thumb",   help="Path to thumbnail (default: latest in assets/)")
    p_up.add_argument("--title",   help="Override video title")
    p_up.add_argument("--privacy", choices=["public", "unlisted", "private"],
                      default=None, help="Privacy setting (default: from SEO or public)")
    p_up.add_argument("--force", action="store_true",
                      help=f"Skip minimum-duration check ({MIN_UPLOAD_SECS//60}min)")
    p_up.add_argument("--schedule-at", dest="schedule_at", default=None,
                      help="Schedule publish time UTC ISO: 2026-05-16T17:00:00 "
                           "Optimal slots (UTC): Tue-Thu 17:00 (noon EST), "
                           "Sun 18:00 (1pm EST study-music peak). "
                           "Upload 3h before peak so YouTube indexes first.")

    # ── live ─────────────────────────────────────────────────────
    p_live = sub.add_parser("live", help="Stream ONE existing finished video for a fixed "
                             "duration via the YouTube Broadcast API, web-panel-controlled "
                             "(no auto-reconnect on dropout). For an indefinite, "
                             "auto-reconnecting 24/7 radio stream with continuous background "
                             "music generation, use 'python run.py --stream' or "
                             "'python scripts/stream_live.py' instead.")
    p_live.add_argument("--video",    help="Path to video file (default: latest in output/)")
    p_live.add_argument("--seo",      help="Path to SEO JSON")
    p_live.add_argument("--title",    help="Override broadcast title")
    p_live.add_argument("--privacy",  choices=["public", "unlisted", "private"],
                        default=None)
    p_live.add_argument("--quality",  choices=list(STREAM_PRESETS), default="720p15",
                        help="Stream quality preset (default: 720p15 — recommended for VPS)")
    p_live.add_argument("--duration", type=int, default=None,
                        help="Max stream duration in seconds (default: 86400 = 24h)")

    # ── end ──────────────────────────────────────────────────────
    p_end = sub.add_parser("end", help="End the active live broadcast")
    p_end.add_argument("--broadcast-id", default=None,
                       help="Broadcast ID (default: from live_state.json)")

    # ── status ───────────────────────────────────────────────────
    sub.add_parser("status", help="List active/upcoming broadcasts")

    # ── schedule ─────────────────────────────────────────────────
    p_sch = sub.add_parser("schedule", help="Schedule a future live broadcast")
    p_sch.add_argument("--at",      help="Start time in UTC ISO format: 2026-03-22T20:00:00")
    p_sch.add_argument("--title",   help="Broadcast title")
    p_sch.add_argument("--seo",     help="SEO JSON path")
    p_sch.add_argument("--privacy", choices=["public", "unlisted", "private"], default=None)

    # ── rename ───────────────────────────────────────────────────
    p_ren = sub.add_parser("rename", help="Rename the active live broadcast")
    p_ren.add_argument("title", help="New broadcast title")
    p_ren.add_argument("--broadcast-id", default=None,
                       help="Broadcast ID (default: from live_state.json)")

    # ── delete ───────────────────────────────────────────────────
    p_del = sub.add_parser("delete", help="Delete a YouTube video by ID")
    p_del.add_argument("video_id", help="YouTube video ID to delete")
    p_del.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

    # ── log ──────────────────────────────────────────────────────
    p_log = sub.add_parser("log", help="Show upload/live history")
    p_log.add_argument("--tail", type=int, default=10, help="Number of entries to show")

    # ── stats ─────────────────────────────────────────────────────
    sub.add_parser("stats", help="Show channel stats and YPP monetization progress")

    # ── analytics ─────────────────────────────────────────────────
    p_anl = sub.add_parser("analytics", help="Sync per-video CTR/impressions from YouTube Analytics")
    p_anl.add_argument("--report",      action="store_true", help="Print CTR table by pillar after sync")
    p_anl.add_argument("--swap-thumbs", dest="swap_thumbs", action="store_true",
                       help="Swap thumbnails for videos with CTR below 70%% of channel average")


    # ── shorts ───────────────────────────────────────────────────
    p_shorts = sub.add_parser(
        "shorts",
        help="Repurpose a long-form video into a vertical YouTube Short "
             "(auto-picks a peak-energy highlight window)",
    )
    p_shorts.add_argument("--video", default=None, help="Source video (default: latest in output/)")
    p_shorts.add_argument("--seo", default=None, help="SEO JSON to derive title/description/tags from")
    p_shorts.add_argument("--out", default=None, help="Output path for the vertical clip")
    p_shorts.add_argument("--window-secs", dest="window_secs", type=float, default=58.0,
                          help="Clip length in seconds (default: 58 -- keep <=60 for Shorts)")
    p_shorts.add_argument("--title", default=None, help="Override the Short's title")
    p_shorts.add_argument("--privacy", choices=["public", "unlisted", "private"], default=None)
    p_shorts.add_argument("--save-only", action="store_true",
                          help="Render the vertical clip locally without uploading")
    p_shorts.add_argument("--crosspost", nargs="*", default=None, metavar="PLATFORM",
                          help="Attempt cross-posting to these platforms after upload "
                               "(requires CROSSPOST_ENABLED=1 -- off/not-implemented by default, "
                               "see scripts/generate_shorts.py's crosspost() docstring)")

    # ── playlist ─────────────────────────────────────────────────
    p_pl = sub.add_parser("playlist", help="Create, list, or add-to playlists")
    pl_sub = p_pl.add_subparsers(dest="playlist_cmd", metavar="ACTION")
    pl_sub.add_parser("list", help="List all channel playlists with their IDs")
    p_pl_create = pl_sub.add_parser("create", help="Create a new playlist")
    p_pl_create.add_argument("title", help="Playlist title")
    p_pl_create.add_argument("--description", default=None)
    p_pl_create.add_argument("--privacy", choices=["public", "unlisted", "private"], default="public")
    p_pl_create.add_argument("--confirm-create", dest="confirm_create", action="store_true",
                             help="Required: actually create the playlist on YouTube (channel-"
                                  "visible). Without this flag, nothing is created.")
    p_pl_add = pl_sub.add_parser("add", help="Add a video to a playlist manually")
    p_pl_add.add_argument("video_id", help="YouTube video ID")
    p_pl_add.add_argument("playlist_id", help="Playlist ID (PLxxx...)")

    # ── auto-service ─────────────────────────────────────────────
    p_asvc = sub.add_parser(
        "auto-service",
        help="Control the lofi-auto timer (daily render+upload; default: midnight)",
    )
    p_asvc.add_argument(
        "action",
        choices=["status", "start", "stop", "enable", "disable", "run-now", "schedule", "logs"],
        help="start/stop/enable/disable act on the timer (the schedule); "
             "run-now triggers an immediate one-off run; schedule changes the timing",
    )
    p_asvc.add_argument("--start", type=int, default=None, metavar="HOUR",
                        help="For 'schedule': hour of day (0-23) for the first run (default: 0 = midnight)")
    p_asvc.add_argument("--every-hours", type=int, default=None,
                        choices=auto_service.VALID_INTERVALS,
                        help="For 'schedule': hours between runs — must evenly divide 24 "
                             "so runs land on a predictable schedule (default: 24 = once daily)")
    p_asvc.add_argument("--lines", type=int, default=200,
                        help="Lines of history for 'logs' (default: 200)")
    p_asvc.add_argument("--no-follow", action="store_true",
                        help="For 'logs': print history and exit instead of following")

    args = parser.parse_args()

    if args.auth:
        get_youtube()
        print("[AUTH] Authentication complete.")
        return

    if not args.cmd:
        parser.print_help()
        return

    dispatch = {
        "auto":          cmd_auto,
        "auto-service":  cmd_auto_service,
        "upload":        cmd_upload,
        "live":          cmd_live,
        "end":           cmd_end,
        "status":        cmd_status,
        "schedule":      cmd_schedule,
        "rename":        cmd_rename,
        "delete":        cmd_delete,
        "log":           cmd_log,
        "stats":         cmd_stats,
        "analytics":     cmd_analytics,
        "playlist":      cmd_playlist,
        "shorts":        cmd_shorts,
    }
    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
