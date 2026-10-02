"""
assemble_video.py
-----------------
Combines visual + music into final upload-ready video.
Handles: music looping, audio normalization, VHS color grade, final encode.

Output: output/lofi_TIMESTAMP.mp4
"""

import os
import re
import sys
import json
import subprocess
import glob
import random
import datetime
import time as _time

MUSIC_DIR = os.path.join(os.path.dirname(__file__), "..", "music")
VISUALS_DIR = os.path.join(os.path.dirname(__file__), "..", "visuals")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def _find_font() -> str:
    """Find a usable sans-serif TTF on this system."""
    candidates = [
        "/usr/share/fonts/TTF/DejaVuSans.ttf",           # Arch/Manjaro
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",# Debian/Ubuntu
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",         # Fedora/RHEL
        "/System/Library/Fonts/Helvetica.ttc",            # macOS
        "C:/Windows/Fonts/arial.ttf",                     # Windows
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    raise FileNotFoundError(
        "No usable font found for ffmpeg drawtext. "
        "Install DejaVu fonts: sudo pacman -S ttf-dejavu  OR  sudo apt install fonts-dejavu"
    )

_DRAWTEXT_FONT = _find_font()

DURATION_MAP = {
    "30 min":    1800,
    "45 min":    2700,
    "1 hour":    3600,
    "90 min":    5400,
    "2 hours":   7200,
    "3 hours":   10800,
    "4 hours":   14400,
    "5 hours":   18000,
    "8 hours":   28800,
    "10 hours":  36000,
    "all night": 28800,
}

# Generated tracks run 2-4 minutes (composer.fit_form_length); planning on
# ~3:20 average gives enough music to fill a video without repeating.
AVG_TRACK_SECS = 200


def tracks_for_duration(target_secs: float) -> int:
    """How many tracks to generate so a video of target_secs needs no repeats."""
    return max(1, -(-int(target_secs) // AVG_TRACK_SECS))


def get_audio_duration(path):
    """Duration in seconds, or 0.0 if ffprobe can't read the file."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


MIN_TRACK_SECS = 10


def _valid_tracks(paths):
    """[(path, duration)] for readable tracks at least MIN_TRACK_SECS long."""
    valid = []
    for path in paths:
        dur = get_audio_duration(path)
        if dur >= MIN_TRACK_SECS:
            valid.append((path, dur))
        else:
            print(f"  WARNING: skipping unreadable or too-short track ({dur:.1f}s): {path}")
    return valid


def pick_music_files(target_duration_secs, force_files=None):
    """Order tracks to fill target_duration_secs. Returns [(path, duration)].

    With `force_files` (the tracks generated for this video) only those are
    used -- never whatever else happens to be in music/, which may be old
    uploads' tracks or the live stream's library. Tracks repeat only when
    there isn't enough music, reshuffled each pass, with a warning saying
    how much of the video is repeated.
    """
    if force_files is not None:
        tracks = _valid_tracks([f for f in force_files if os.path.exists(f)])
        if not tracks:
            raise FileNotFoundError("None of the generated tracks for this video are usable.")
    else:
        files = []
        for ext in ("*.mp3", "*.wav", "*.flac", "*.ogg"):
            files.extend(glob.glob(os.path.join(MUSIC_DIR, ext)))
        tracks = _valid_tracks(files)
        if not tracks:
            raise FileNotFoundError(
                f"No usable music files found in {MUSIC_DIR}\n"
                "Generate tracks first (python run.py --skip-upload) or drop "
                ".wav/.mp3 files into the music/ folder."
            )

    unique_secs = sum(d for _, d in tracks)
    playlist, total = [], 0.0
    while total < target_duration_secs:
        batch = tracks[:]
        random.shuffle(batch)
        if playlist and len(batch) > 1 and batch[0][0] == playlist[-1][0]:
            batch.append(batch.pop(0))     # no track twice in a row across passes
        for item in batch:
            playlist.append(item)
            total += item[1]
            if total >= target_duration_secs:
                break
    if unique_secs < target_duration_secs:
        print(f"  WARNING: only {unique_secs / 60:.0f} min of unique music for a "
              f"{target_duration_secs / 60:.0f} min video -- tracks will repeat.")
    return playlist


def concat_audio(playlist, target_secs, tmp_dir):
    """Join the playlist into one lossless FLAC of exactly target_secs (or the
    music's length, if shorter), with a 2 s fade in and a 5 s fade out at the
    real end. Tracks are already mastered to a common loudness, so no further
    loudness processing is applied: every video length is treated the same,
    and the only lossy encode is the final one."""
    if not playlist:
        raise RuntimeError("[ASSEMBLE] Empty playlist.")
    total = sum(d for _, d in playlist)
    out_secs = min(float(target_secs), total)

    list_path = os.path.join(tmp_dir, "audio_list.txt")
    with open(list_path, "w") as f:
        for path, _ in playlist:
            escaped = os.path.abspath(path).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    concat_path = os.path.join(tmp_dir, "audio_concat.flac")
    fade_out_start = max(0.0, out_secs - 5)
    audio_filter = (f"aresample=44100,aformat=sample_fmts=s16:channel_layouts=stereo,"
                    f"afade=t=in:st=0:d=2,afade=t=out:st={fade_out_start:.2f}:d=5")

    print(f"  Joining audio ({out_secs / 60:.0f} min)...")
    log_path = os.path.join(tmp_dir, "audio_concat.log")
    timeout_secs = int(target_secs * 2) + 300
    try:
        with open(log_path, "w") as log_fh:
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", list_path,
                "-t", f"{out_secs:.2f}",
                "-af", audio_filter,
                "-c:a", "flac",
                "-stats",
                concat_path
            ], check=True, stdout=log_fh, stderr=log_fh,
               timeout=timeout_secs)
    except subprocess.CalledProcessError:
        try:
            with open(log_path) as lf:
                tail = lf.read().splitlines()[-15:]
        except OSError:
            tail = []
        print("[ASSEMBLE] Audio concat failed:")
        for line in tail:
            print(f"  {line}")
        raise RuntimeError("[ASSEMBLE] Audio concat failed") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"[ASSEMBLE] Audio concat timed out after {timeout_secs}s — "
            "a music file may be corrupt or unreadable."
        )
    print(f"  Audio ready: {concat_path}")
    return concat_path, out_secs


def pick_visual(theme_name=None, prefer_path=None):
    """Pick a background video from visuals/. prefer_path takes priority if it exists."""
    if prefer_path and os.path.exists(prefer_path):
        return prefer_path
    # Match bg_{theme}*.mp4 to handle timestamped filenames
    pattern = f"bg_{theme_name}*.mp4" if theme_name else "bg_*.mp4"
    files = glob.glob(os.path.join(VISUALS_DIR, pattern))
    if not files:
        return None
    # Return the most recently modified one
    return max(files, key=os.path.getmtime)


# EQ zone geometry — sourced from visual_v2/config.py to prevent drift
from scripts.visual_v2.config import (
    EQ_X0 as _EQ_X, EQ_Y_BOT as _EQ_Y_BOT, EQ_MAX_H as _EQ_H,
    EQ_X1 as _EQ_X1,
    NP_X0 as _NP_X0, NP_X1 as _NP_X1,
    PROG_Y as _PROG_Y, PROG_H as _PROG_H,
)
_EQ_Y = _EQ_Y_BOT - _EQ_H
_EQ_W = _EQ_X1 - _EQ_X

# Theme gradient colours for EQ bars (top=bright, bot=dim)
# Format: (top_rgb, bot_rgb) — derived from visual_v2 theme eq_top/eq_bot
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
    "vaporwave":     ((255,  60, 220), (100, 10,  100)),
    "lofi_house":    (( 40, 180, 255), ( 10, 50,  140)),
    "lofi_classical":((220, 185,  80), (100, 80,   20)),
    "bedroom_pop":   ((255, 180, 140), (140, 80,   60)),
    "lofi_rnb":      ((255, 160,  60), (140, 70,   10)),
}
_DEFAULT_EQ_GRAD = ((0, 200, 255), (0, 60, 140))

# Theme-matched ambient noise: (noise_color, amplitude, lpf_hz)
# Mixed at very low level to add atmospheric immersion without being audible as "noise"
_THEME_AMBIENT = {
    "cozy_rain":     ("pink",  0.007, 550),   # soft rain
    "forest_rain":   ("pink",  0.008, 450),   # heavier rain
    "winter_snow":   ("white", 0.003, 2500),  # airy cold silence
    "midnight_cafe": ("brown", 0.005, 750),   # warm room hum
    "amber_night":   ("brown", 0.004, 700),   # warm indoor
    "purple_dusk":   ("brown", 0.003, 800),   # quiet dusk
    "blue_hour":     ("pink",  0.004, 900),   # cool evening
    "neon_tokyo":    ("white", 0.003, 1400),  # city air
    "autumn_study":  ("brown", 0.004, 680),   # cozy indoor warmth
    "spring_dawn":   ("pink",  0.005, 2200),  # bright outdoor
    "summer_lofi":   ("pink",  0.005, 2600),  # open air
    "sakura_night":  ("pink",  0.003, 950),   # quiet night
    # New subgenre themes
    "vaporwave":     ("pink",  0.006, 1200),  # dreamy synth shimmer
    "lofi_house":    ("brown", 0.004, 900),   # urban warmth
    "lofi_classical":("white", 0.002, 3000),  # clean, refined hall air
    "bedroom_pop":   ("pink",  0.004, 2000),  # bright indie room
    "lofi_rnb":      ("brown", 0.005, 750),   # warm soul room
}
_DEFAULT_AMBIENT = ("brown", 0.003, 800)


def _pre_grade_visual(visual_path: str, tmp_dir: str) -> str:
    """
    Pre-bake static VHS grade filters onto the 60-second visual loop ONCE.

    Key optimisation: hqdn3d + colorbalance + eq + vignette applied to ~1,440 frames
    (60s loop) instead of 864,000 frames (10h video). ~600× less filter work.

    noise=c0f=t+u is intentionally excluded — it's temporal (seed = time), so
    pre-baking it would cause the grain to loop visibly every 60 seconds.
    It stays in the main encode where `t` advances across the full duration.
    """
    out = os.path.join(tmp_dir, "visual_graded.mp4")
    if os.path.exists(out):
        return out
    print("  Pre-grading visual loop (hqdn3d + colorbalance + eq + vignette)...")
    subprocess.run([
        "ffmpeg", "-y", "-i", visual_path,
        "-vf", (
            "hqdn3d=luma_spatial=3:chroma_spatial=2,"
            "colorbalance=rs=0.08:gs=0.04:bs=-0.05,"
            "eq=contrast=1.06:saturation=0.88,"
            "vignette=angle=0.628"
        ),
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        out
    ], check=True, capture_output=True)
    return out


class _StallTimeout(Exception):
    """Raised when ffmpeg stops making encode progress but hasn't exited."""
    def __init__(self, last_progress: float):
        self.last_progress = last_progress


class _HardTimeout(Exception):
    """Raised when the absolute wall-clock cap is hit regardless of progress."""


_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+\.?\d*)")
_SPEED_RE = re.compile(r"speed=\s*([\d.]+)x")
_STALL_SECS = 600  # kill + report if encode progress hasn't advanced in this long

# ─────────────────────────────────────────────────────────────────────────────
# Dynamic encode-speed tracking — replaces a hardcoded "this box does 0.56x"
# assumption with a real, self-updating measurement. Confirmed 2026-08-16/17:
# a code comment near the VAAPI probe below claimed "4.1x realtime hw vs
# 0.56x sw, measured on this box" but a real production run only achieved
# ~0.57x with VAAPI actually engaged -- that number was either stale (the EQ-
# visualizer filter chain got heavier since it was measured) or simply
# wrong for this exact filter graph. Either way, trusting a hardcoded
# constant anywhere in this pipeline is how publish.py's AUTO_DURATION_POOL
# ended up sized for a speed this box doesn't actually deliver. This file is
# the one place that knows the REAL number, every time, for whatever
# filter-chain complexity is actually active -- so it's the one place that
# should own recording it. publish.py reads this to size unattended-mode
# duration picks dynamically instead of guessing.
# ─────────────────────────────────────────────────────────────────────────────
_SPEED_HISTORY_FILE = os.path.join(os.path.dirname(__file__), "..", "assets",
                                    ".encode_speed_history.json")
_SPEED_HISTORY_MAX = 8


def _tail_speed(log_path: str) -> float | None:
    """Latest ffmpeg `speed=N.NNx` marker from the tail of the log -- same
    read pattern as _tail_progress_secs."""
    try:
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 4096))
            tail = f.read().decode(errors="replace")
    except Exception:
        return None
    matches = _SPEED_RE.findall(tail.replace("\r", "\n"))
    return float(matches[-1]) if matches else None


def record_encode_speed_sample(log_path: str, *, used_vaapi: bool) -> None:
    """Best-effort: append the last observed encode speed from this run
    (success, stall-kill, or hard-timeout -- whatever's in the log at the
    moment this is called is a real sample either way) to a small rolling
    history file, keyed by encoder path since VAAPI/software speeds aren't
    comparable. Never raises -- a failure here must never affect the render
    it's measuring."""
    speed = _tail_speed(log_path)
    if speed is None or speed <= 0:
        return
    try:
        os.makedirs(os.path.dirname(_SPEED_HISTORY_FILE), exist_ok=True)
        try:
            with open(_SPEED_HISTORY_FILE) as f:
                history = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            history = {}
        key = "vaapi" if used_vaapi else "software"
        samples = history.get(key, [])
        samples.append(speed)
        history[key] = samples[-_SPEED_HISTORY_MAX:]
        with open(_SPEED_HISTORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception:
        pass


def estimated_encode_speed(*, used_vaapi: bool, default: float = 0.35) -> float:
    """Median of recent real measurements for this encoder path, or a
    conservative default if nothing's been measured yet (first-ever run on
    a fresh box). Median, not mean -- one anomalous sample (box under heavy
    unrelated load) shouldn't skew the estimate as much as a repeated real
    trend would."""
    try:
        with open(_SPEED_HISTORY_FILE) as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default
    samples = history.get("vaapi" if used_vaapi else "software", [])
    if not samples:
        return default
    ordered = sorted(samples)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _tail_progress_secs(log_path: str) -> float | None:
    """Latest ffmpeg `time=HH:MM:SS` progress marker from the tail of the (\\r-updated) log."""
    try:
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 4096))
            tail = f.read().decode(errors="replace")
    except Exception:
        return None
    matches = _TIME_RE.findall(tail.replace("\r", "\n"))
    if not matches:
        return None
    hh, mm, ss = matches[-1]
    return int(hh) * 3600 + int(mm) * 60 + float(ss)


def _graceful_kill(proc: subprocess.Popen, grace_secs: float = 20) -> None:
    """SIGTERM first, give ffmpeg a real chance to flush and close the
    output container cleanly, THEN SIGKILL if it still hasn't exited.
    Confirmed real 2026-08-18: the stall this watchdog catches happens with
    the encode already at 43195-43196/43200 frames (99.99% done, target
    duration already reached per -stats `time=`) -- not stuck partway
    through, stuck AT THE FINISH LINE. A bare proc.kill() (SIGKILL, no
    chance to clean up) on that state guarantees a truncated file with no
    moov atom (verified via ffprobe: "moov atom not found", completely
    unusable) even though the actual encoded content is already almost
    entirely there. SIGTERM asks ffmpeg to stop NOW and finalize -- which,
    for a stream that's already essentially finished, is normally fast."""
    proc.terminate()
    deadline = _time.time() + grace_secs
    while _time.time() < deadline:
        if proc.poll() is not None:
            return
        _time.sleep(0.5)
    if proc.poll() is None:
        proc.kill()
    proc.wait()


def _output_is_valid(output_video: str) -> bool:
    """True if ffprobe can actually read a duration out of the file --
    cheap, real validity check (catches the "moov atom not found" truncated-
    file case) rather than just checking the file exists/has nonzero size."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", output_video],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def _wait_with_stall_watchdog(proc: subprocess.Popen, log_path: str, target_secs: int,
                               output_video: str | None = None,
                               *, stall_secs: int = _STALL_SECS, poll_interval: float = 15,
                               hard_timeout_secs: int | None = None) -> int:
    """
    Poll an ffmpeg subprocess for real encode progress instead of only enforcing a
    single total timeout. On a genuine stall, tries a graceful shutdown + validity
    check first -- a stall with an already-valid output means the encode actually
    finished and this was just ffmpeg failing to exit cleanly, not a real failure
    (see _graceful_kill's docstring) -- and only raises _StallTimeout if that
    doesn't recover a usable file. hard_timeout_secs stays a hard proc.kill(): a
    stall this late/long isn't the "basically done" case this recovery targets.

    stall_secs/poll_interval/hard_timeout_secs are overridable for testing; production
    callers should rely on the defaults.
    """
    hard_deadline = _time.time() + (hard_timeout_secs if hard_timeout_secs is not None
                                     else target_secs * 12)
    last_progress = 0.0
    last_progress_at = _time.time()

    while True:
        ret = proc.poll()
        if ret is not None:
            return ret

        now = _time.time()
        if now > hard_deadline:
            proc.kill()
            proc.wait()
            raise _HardTimeout()

        cur = _tail_progress_secs(log_path)
        if cur is not None and cur > last_progress:
            last_progress = cur
            last_progress_at = now
        elif now - last_progress_at > stall_secs:
            _graceful_kill(proc)
            if output_video and _output_is_valid(output_video):
                print(f"  [ASSEMBLE] Encode stalled at {last_progress:.0f}/{target_secs}s but "
                      "the output is actually valid (finished, just didn't exit cleanly) -- "
                      "treating this as a completed encode, not a failure.")
                return 0
            raise _StallTimeout(last_progress)

        _time.sleep(poll_interval)


_VAAPI_DEVICE = "/dev/dri/renderD128"
_vaapi_checked: bool | None = None  # cached per-process; probing costs ~1s


_VAAPI_STATUS_FILE = os.path.join(os.path.dirname(__file__), "..", "assets", ".vaapi_status.json")


def disable_vaapi(reason: str) -> None:
    """Persist a real, evidence-based decision to stop using VAAPI on this
    box -- called from apply_vhs_grade's _StallTimeout handler below.
    Confirmed 2026-08-18: a VAAPI encode on this box reached 43196/43200
    frames (99.99% done, the -stats `time=` counter already at the full
    target) and then froze completely for 600s+ until the stall-watchdog
    killed it -- a finalization deadlock, not slowness. Three independent
    real-run measurements (0.568x, 0.527x, 0.484x) also never
    once beat this same file's own "software" baseline number (0.56x) in
    the comment this replaced, meaning the claimed ~7x VAAPI speedup was
    never actually materializing here anyway (the CPU-bound EQ-visualizer/
    blur/blend filter chain dominates regardless of which encoder does the
    final H.264 step) -- so there's no upside being traded away, only a
    real hang being removed. Not per-process/in-memory: this must survive
    across the many separate `python run.py`/`publish.py auto` invocations
    that each start a fresh process and re-probe from scratch."""
    global _vaapi_checked
    _vaapi_checked = False
    try:
        os.makedirs(os.path.dirname(_VAAPI_STATUS_FILE), exist_ok=True)
        with open(_VAAPI_STATUS_FILE, "w") as f:
            json.dump({"disabled": True, "reason": reason,
                       "at": datetime.datetime.now(datetime.timezone.utc).isoformat()}, f)
    except Exception:
        pass


def _vaapi_disabled_reason() -> str | None:
    try:
        with open(_VAAPI_STATUS_FILE) as f:
            state = json.load(f)
        return state.get("reason") if state.get("disabled") else None
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _vaapi_available() -> bool:
    """
    Real capability probe (not just checking the device file exists) for
    Intel/AMD VAAPI H.264 hardware encoding. Cached after the first call
    per-process; also checks the persisted disable_vaapi() flag first,
    which -- unlike this cache -- survives across separate process
    invocations. Must fail closed (return False) on any error -- missing
    device, missing driver, no permission, a VPS with no GPU passthrough,
    or a previously-confirmed hang on THIS box are all reasons to silently
    fall back to the software path, not break the render.
    """
    global _vaapi_checked
    if _vaapi_checked is not None:
        return _vaapi_checked
    reason = _vaapi_disabled_reason()
    if reason:
        print(f"  [VAAPI] Disabled ({reason}) — using software encode.")
        _vaapi_checked = False
        return False
    if not os.path.exists(_VAAPI_DEVICE):
        _vaapi_checked = False
        return False
    try:
        result = subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=0.5:size=320x240:rate=5",
            "-vaapi_device", _VAAPI_DEVICE,
            "-vf", "format=nv12,hwupload",
            "-c:v", "h264_vaapi",
            "-f", "null", "-",
        ], capture_output=True, timeout=15)
        _vaapi_checked = result.returncode == 0
    except Exception:
        _vaapi_checked = False
    return _vaapi_checked


def apply_vhs_grade(input_video, output_video, target_secs, theme_name=None, audio_path=None):
    """
    Overlay audio-reactive EQ bars + progress bar on a pre-graded visual.

    Static VHS grade (hqdn3d/colorbalance/eq/vignette) is already baked into the
    input_video — only dynamic elements are applied here:
      showfreqs pipeline — audio-reactive EQ bars with gradient + glow
      geq/overlay/drawtext — progress bar and timestamps
    """
    top, bot = _THEME_EQ_GRAD.get(theme_name or "", _DEFAULT_EQ_GRAD)
    tr, tg, tb = top
    br, bg, bb = bot

    geq_r = f"'{tr}+({br}-{tr})*Y/H'"
    geq_g = f"'{tg}+({bg}-{tg})*Y/H'"
    geq_b = f"'{tb}+({bb}-{tb})*Y/H'"

    a_color, a_amp, a_lpf = _THEME_AMBIENT.get(theme_name or "", _DEFAULT_AMBIENT)

    from scripts.visual_v2.themes import THEMES as _VIS_THEMES
    _acc = _VIS_THEMES.get(theme_name or "cozy_rain", _VIS_THEMES["cozy_rain"]).get("accent", (180, 160, 255))
    acc_hex = f"0x{_acc[0]:02x}{_acc[1]:02x}{_acc[2]:02x}"
    _h, _m, _s = target_secs // 3600, (target_secs % 3600) // 60, target_secs % 60
    # Elapsed and total use the same format: M:SS-style under an hour,
    # H:MM:SS from an hour up.
    if _h:
        total_str = f"{_h}:{_m:02d}:{_s:02d}"
        elapsed_txt = (r"%{eif\:floor(t/3600)\:d}\:%{eif\:mod(floor(t/60)\,60)\:d\:2}"
                       r"\:%{eif\:mod(floor(t)\,60)\:d\:2}")
    else:
        total_str = f"{_m:02d}:{_s:02d}"
        elapsed_txt = r"%{eif\:floor(t/60)\:d\:2}\:%{eif\:mod(floor(t)\,60)\:d\:2}"
    total_str_esc = total_str.replace(":", r"\:")
    FONT = _DRAWTEXT_FONT
    PX0, PX1, PY, PH = _NP_X0, _NP_X1, _PROG_Y, _PROG_H
    PW  = PX1 - PX0
    ph_y = PY + PH // 2 - 7

    # Music: the separate lossless track when given, else the input video's own audio.
    music_in = "[2:a]" if audio_path else "[0:a]"

    filter_stages = [
        # 1. Temporal film grain only (static grade already baked into input)
        "[0:v]null[vgraded]",

        # 2. Split audio
        f"{music_in}asplit=2[a_eq][a_mix]",
        (f"[a_eq]showfreqs=s={_EQ_W}x{_EQ_H}:mode=bar:fscale=log:ascale=log"
         f":win_func=hann:averaging=1:colors=ffffff[eq_raw]"),

        # 3. Gradient colour for EQ bars
        f"color=c=black:s={_EQ_W}x{_EQ_H}:r=24[blank]",
        f"[blank]geq=r={geq_r}:g={geq_g}:b={geq_b}[grad]",

        # 4. Colour + glow
        "[eq_raw][grad]blend=all_mode=multiply[eq_col]",
        "[eq_col]split[eq_col1][eq_col2]",
        "[eq_col2]gblur=sigma=5[eq_blur]",
        "[eq_col1][eq_blur]blend=all_mode=screen[eq_glow]",
        "[eq_glow]colorkey=0x000000:similarity=0.13:blend=0.06[eq_key]",
        "[eq_key]format=rgba,colorchannelmixer=aa=0.92[eq_final]",

        # 5. Overlay EQ
        f"[vgraded][eq_final]overlay={_EQ_X}:{_EQ_Y}:format=auto[veq]",

        # 6. Progress bar
        # drawbox can't do this: in its expressions `t` is the box
        # thickness, not time, so the bar used to be drawn full from frame
        # one. geq and overlay do get the frame time.
        (f"color=c={acc_hex}:s={PW}x{PH}:r=24,format=rgba,"
         f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte(X,W*T/{target_secs}),214,0)'[pbar]"),
        f"color=c={acc_hex}:s=14x14:r=24[pknob]",
        f"[veq][pbar]overlay=x={PX0}:y={PY}:shortest=1[pb1]",
        f"[pb1][pknob]overlay=x='{PX0}+{PW}*min(t/{target_secs},1)-7':y={ph_y}:shortest=1[pb2]",
        f"[pb2]drawtext=fontfile={FONT}:fontsize=20:fontcolor=0xafafc3@0.78:x={PX0}:y={PY + 16}:text='{elapsed_txt}'[pb3]",
        f"[pb3]drawtext=fontfile={FONT}:fontsize=20:fontcolor=0xafafc3@0.78:x=main_w-tw-60:y={PY + 16}:text='{total_str_esc}'[vout]",

        # 7. Ambient audio
        f"[1:a]lowpass=f={a_lpf}[ambient]",
        "[a_mix][ambient]amix=inputs=2:weights='1 0.09':duration=first[aout]",
    ]

    # Hardware encode (Intel/AMD VAAPI) when actually available and working --
    # a real ~7x speedup measured on this box (4.1x realtime hw vs 0.56x sw)
    # over the software libx264 path below, which was the root reason the
    # VHS-grade stage took ~1.8 hours for a 1-hour video. Probed once (cheap,
    # cached) and always falls back to the proven software path on any VPS
    # without a usable GPU -- this must keep working on hardware that has no
    # /dev/dri at all, per DEPLOYMENT.md's generic-VPS target.
    use_vaapi = _vaapi_available()
    video_map = "[vout]"
    if use_vaapi:
        filter_stages.append("[vout]format=nv12,hwupload[vout_hw]")
        video_map = "[vout_hw]"
    filtergraph = ";".join(filter_stages)

    log_path = output_video + ".grade.log"
    est_mins = target_secs // 60
    encoder_desc = "hardware (VAAPI)" if use_vaapi else "software (libx264)"
    print(f"  Encoding video ({est_mins} min, {encoder_desc}) — progress in: {log_path}")

    device_args = []
    if use_vaapi:
        # Must come before -filter_complex: hwupload (used in the filtergraph
        # above) needs the device context already registered when it runs.
        device_args = ["-vaapi_device", _VAAPI_DEVICE]
        video_args = [
            "-c:v", "h264_vaapi",
            "-b:v", "5000k", "-maxrate", "6000k", "-bufsize", "12000k",
        ]
    else:
        video_args = [
            # Pin thread counts explicitly instead of ffmpeg/x264 auto-detect: a
            # real render on this box's 4-core i3-7100U deadlocked with all 38
            # auto-spawned x264 worker threads permanently blocked on a futex
            # (confirmed via /proc/<pid>/task/*/wchan) after essentially
            # finishing the encode. libx264 ignores ffmpeg's generic -threads,
            # hence -x264-params (same fix already used in stream_live.py's
            # live-encode path). `threads=4` alone was NOT sufficient -- a
            # second real run deadlocked again with 36 threads on futex_wait_
            # queue despite it, meaning x264's lookahead/slice threading was
            # still scaling independently. Pinning those explicitly too.
            "-filter_threads", "4",
            "-c:v", "libx264",
            "-x264-params", "threads=4:lookahead-threads=1:sliced-threads=0",
            # Fixed 8 Mbps target — predictable file size, meets YouTube's
            # recommended 1080p bitrate. CRF 18 + ultrafast was producing
            # 30-40 Mbps (huge files, slow).
            "-b:v", "5000k", "-maxrate", "6000k", "-bufsize", "12000k",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
        ]

    try:
        with open(log_path, "w") as log_fh:
            proc = subprocess.Popen([
                "ffmpeg", "-y",
                "-i", input_video,
                "-f", "lavfi", "-i", f"anoisesrc=d={target_secs}:c={a_color}:a={a_amp}",
                *(["-i", audio_path] if audio_path else []),
                *device_args,
                "-filter_complex", filtergraph,
                "-map", video_map, "-map", "[aout]",
                "-t", str(target_secs),
                *video_args,
                # No +faststart: avoids a full file rewrite at the end (saves hours on large files)
                "-c:a", "aac", "-b:a", "192k",
                "-stats",
                output_video,
            ], stdout=log_fh, stderr=log_fh)
            returncode = _wait_with_stall_watchdog(proc, log_path, target_secs, output_video)
        # Record whatever real speed was achieved regardless of outcome --
        # even a failed/killed run's last progress line is real data about
        # what this box can actually do with this filter chain right now.
        record_encode_speed_sample(log_path, used_vaapi=use_vaapi)
        if returncode != 0:
            print(f"[ASSEMBLE] ffmpeg failed (exit {returncode}) — last lines of {log_path}:")
            try:
                with open(log_path) as lf:
                    for line in lf.read().splitlines()[-20:]:
                        print(f"  {line}")
            except Exception:
                pass
            raise RuntimeError(f"[ASSEMBLE] ffmpeg exited {returncode}")
        try:
            os.remove(log_path)
        except Exception:
            pass
    except _StallTimeout as e:
        record_encode_speed_sample(log_path, used_vaapi=use_vaapi)
        if use_vaapi:
            # Confirmed real 2026-08-18: a VAAPI encode stalling essentially
            # AT completion (e.last_progress landing at/near target_secs, as
            # opposed to stalling partway through) is a finalization
            # deadlock signature specific to the hardware path, not generic
            # slowness -- stop trying VAAPI on this box going forward
            # instead of hanging the same way on every future run.
            disable_vaapi(f"stalled at {e.last_progress:.0f}/{target_secs}s on {datetime.datetime.now(datetime.timezone.utc).date()}")
        raise RuntimeError(
            f"[ASSEMBLE] Video grade stalled — no encode progress for {_STALL_SECS}s "
            f"(stuck at {e.last_progress:.0f}/{target_secs}s, process killed). This is a "
            "hang (e.g. an encoder-thread deadlock), not just slowness -- check "
            f"{log_path.replace('.grade.log', '')}.grade.log if it's still around, or "
            "rerun with a fresh temp dir."
        ) from None
    except _HardTimeout:
        record_encode_speed_sample(log_path, used_vaapi=use_vaapi)
        raise RuntimeError(
            f"[ASSEMBLE] Video grade timed out after {target_secs * 12}s — "
            "input video may be corrupt or hardware is too slow."
        )


def assemble(theme_name=None, duration_label="2 hours", output_name=None, visual_path=None, music_files=None):
    if duration_label not in DURATION_MAP:
        raise ValueError(f"Unknown duration {duration_label!r}; expected one of {sorted(DURATION_MAP)}")
    target_secs = DURATION_MAP[duration_label]
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_name = output_name or f"lofi_{ts}.mp4"
    out_path = os.path.join(OUTPUT_DIR, output_name)
    tmp_dir = os.path.join(OUTPUT_DIR, f"tmp_{ts}")
    os.makedirs(tmp_dir, exist_ok=True)

    print(f"[ASSEMBLE] Duration: {duration_label} ({target_secs}s)")

    import shutil
    try:
        # 1. Build audio track
        print("  Building audio track...")
        playlist = pick_music_files(target_secs, force_files=music_files)
        print(f"  Using {len(playlist)} track(s): {[os.path.basename(p) for p, _ in playlist]}")
        audio_path, audio_secs = concat_audio(playlist, target_secs, tmp_dir)

        # 2. Get visual
        visual_path = pick_visual(theme_name, prefer_path=visual_path)
        if not visual_path:
            print("  No visual found — generating a simple gradient background...")
            visual_path = os.path.join(tmp_dir, "gradient_bg.mp4")
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "color=c=0x0A0020:size=1280x720:rate=24",
                "-t", "60",
                "-c:v", "libx264", "-crf", "28",
                visual_path
            ], check=True, capture_output=True)

        print(f"  Visual: {os.path.basename(visual_path)}")

        # 3. Pre-bake static VHS grade onto the visual loop (once, ~seconds not hours)
        graded_visual = _pre_grade_visual(visual_path, tmp_dir)

        # 4. Loop the graded visual to the audio's length (stream copy, no re-encode)
        looped_path = os.path.join(tmp_dir, "looped.mp4")
        print("  Looping visual to length...")
        subprocess.run([
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", graded_visual,
            "-map", "0:v", "-an",
            "-c:v", "copy",
            "-t", f"{audio_secs:.2f}",
            looped_path
        ], check=True, capture_output=True)

        # 5. EQ overlay + progress bar + final (only lossy audio) encode
        print("  Applying VHS color grade + EQ overlay...")
        apply_vhs_grade(looped_path, out_path, int(round(audio_secs)),
                        theme_name=theme_name, audio_path=audio_path)

        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        # Keep the logs for inspection, but not the multi-GB intermediates.
        for big in glob.glob(os.path.join(tmp_dir, "*.mp4")) + glob.glob(os.path.join(tmp_dir, "*.flac")):
            try:
                os.remove(big)
            except OSError:
                pass
        print(f"  [ASSEMBLE] Logs left in: {tmp_dir}")
        raise

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"[ASSEMBLE] Done: {out_path} ({size_mb:.1f} MB)")
    return out_path


if __name__ == "__main__":
    theme = sys.argv[1] if len(sys.argv) > 1 else None
    duration = sys.argv[2] if len(sys.argv) > 2 else "2 hours"
    assemble(theme, duration)
