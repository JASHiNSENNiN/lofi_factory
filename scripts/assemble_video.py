"""
assemble_video.py
-----------------
Combines visual + music into final upload-ready video.
Handles: music looping, audio normalization, VHS color grade, final encode.

Output: output/lofi_TIMESTAMP.mp4
"""

import os
import sys
import subprocess
import glob
import random
import datetime

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
    "single":    270,     # ~4.5 min — one lofi track (lofi-inator single cover)
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


def get_audio_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True
    )
    try:
        return float(result.stdout.strip())
    except Exception:
        return 0


def pick_music_files(target_duration_secs, force_files=None):
    """Pick and concatenate music files to fill target duration."""
    if force_files:
        files = [f for f in force_files if os.path.exists(f)]
        if not files:
             print("  WARNING: Provided music_files not found. Falling back to folder scan.")
             files = []
    else:
        files = []

    if not files:
        exts = ("*.mp3", "*.wav", "*.flac", "*.ogg")
        for ext in exts:
            files.extend(glob.glob(os.path.join(MUSIC_DIR, ext)))

    if not files:
        raise FileNotFoundError(
            f"No music files found in {MUSIC_DIR}\n"
            "Run: python scripts/generate_music.py --mode mock\n"
            "Or drop your .mp3/.wav files into the music/ folder."
        )

    random.shuffle(files)

    # Build playlist until we exceed target duration
    playlist = []
    total = 0
    while total < target_duration_secs:
        prev_total = total
        for f in files:
            dur = get_audio_duration(f)
            playlist.append(f)
            total += dur
            if total >= target_duration_secs:
                break
        if total == prev_total:   # no progress — all durations 0 (corrupt files)
            break

    return playlist


def concat_audio(playlist, target_secs, tmp_dir):
    """Concatenate audio files via ffmpeg concat demuxer."""

    # Pre-validate each track with ffprobe; skip corrupt or too-short files.
    valid_playlist = []
    for track in playlist:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", track],
            capture_output=True, text=True
        )
        if probe.returncode != 0 or not probe.stdout.strip():
            print(f"  WARNING: skipping unreadable track (ffprobe error): {track}")
            continue
        try:
            dur = float(probe.stdout.strip())
        except ValueError:
            print(f"  WARNING: skipping track with unparseable duration: {track}")
            continue
        if dur < 10:
            print(f"  WARNING: skipping track shorter than 10 s ({dur:.1f} s): {track}")
            continue
        valid_playlist.append(track)

    if not valid_playlist:
        raise RuntimeError("[ASSEMBLE] No valid audio tracks remain after pre-validation.")

    list_path = os.path.join(tmp_dir, "audio_list.txt")
    with open(list_path, "w") as f:
        for p in valid_playlist:
            f.write(f"file '{os.path.abspath(p)}'\n")

    concat_path = os.path.join(tmp_dir, "audio_concat.mp3")

    # loudnorm requires a full two-pass analysis — unusably slow for long videos.
    # dynaudnorm is single-pass but adds buffered processing overhead that compounds
    # badly at >1 hour scale. Tracks are already normalised at generation time, so
    # for >1 hour sessions just apply the fade; skip dynaudnorm entirely.
    if target_secs > 3600:
        audio_filter = f"afade=t=out:st={target_secs - 5}:d=5"
    elif target_secs > 1800:
        audio_filter = (
            f"afade=t=out:st={target_secs - 5}:d=5,"
            "dynaudnorm=f=150:g=15:p=0.95"
        )
    else:
        audio_filter = (
            f"afade=t=out:st={target_secs - 5}:d=5,"
            "loudnorm=I=-14:LRA=11:TP=-1"
        )

    est_mins = target_secs // 60
    print(f"  Mixing audio ({est_mins} min) — this may take a few minutes...")

    log_path = os.path.join(tmp_dir, "audio_concat.log")
    timeout_secs = target_secs * 6
    try:
        with open(log_path, "w") as log_fh:
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", list_path,
                "-t", str(target_secs),
                "-af", audio_filter,
                "-c:a", "libmp3lame", "-b:a", "192k",
                "-stats",
                concat_path
            ], check=True, stdout=log_fh, stderr=log_fh,
               timeout=timeout_secs)
    except subprocess.CalledProcessError as e:
        try:
            with open(log_path) as lf:
                tail = lf.read().splitlines()[-15:]
        except Exception:
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
    return concat_path


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


def apply_vhs_grade(input_video, output_video, target_secs, theme_name=None):
    """
    Overlay audio-reactive EQ bars + progress bar on a pre-graded visual.

    Static VHS grade (hqdn3d/colorbalance/eq/vignette) is already baked into the
    input_video — only dynamic elements are applied here:
      noise    — temporal film grain (seed varies with t, no loop artifact)
      showfreqs pipeline — audio-reactive EQ bars with gradient + glow
      drawbox/drawtext — progress bar and timestamps
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
    total_str     = f"{_h}:{_m:02d}:{_s:02d}"
    total_str_esc = total_str.replace(":", r"\:")
    FONT = _DRAWTEXT_FONT
    PX0, PX1, PY, PH = _NP_X0, _NP_X1, _PROG_Y, _PROG_H
    PW  = PX1 - PX0
    ph_y = PY + PH // 2 - 7

    filtergraph = ";".join([
        # 1. Temporal film grain only (static grade already baked into input)
        "[0:v]noise=c0s=8:c0f=t+u[vgraded]",

        # 2. Split audio
        "[0:a]asplit=2[a_eq][a_mix]",
        (f"[a_eq]showfreqs=s={_EQ_W}x{_EQ_H}:mode=bar:fscale=log:ascale=sqrt"
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
        f"[veq]drawbox=x={PX0}:y={PY}:w='min({PW}*t/{target_secs},{PW})':h={PH}:color={acc_hex}@0.84:t=fill[pb1]",
        f"[pb1]drawbox=x='min({PX0}+{PW}*t/{target_secs},{PX1})-7':y={ph_y}:w=14:h=14:color={acc_hex}:t=fill[pb2]",
        f"[pb2]drawtext=fontfile={FONT}:fontsize=20:fontcolor=0xafafc3@0.78:x={PX0}:y={PY + 16}:text='%{{pts\\:hms}}'[pb3]",
        f"[pb3]drawtext=fontfile={FONT}:fontsize=20:fontcolor=0xafafc3@0.78:x=main_w-tw-60:y={PY + 16}:text='{total_str_esc}'[vout]",

        # 7. Ambient audio
        f"[1:a]lowpass=f={a_lpf}[ambient]",
        "[a_mix][ambient]amix=inputs=2:weights='1 0.09':duration=first[aout]",
    ])

    log_path = output_video + ".grade.log"
    est_mins = target_secs // 60
    print(f"  Encoding video ({est_mins} min) — progress in: {log_path}")

    try:
        with open(log_path, "w") as log_fh:
            subprocess.run([
                "ffmpeg", "-y",
                "-i", input_video,
                "-f", "lavfi", "-i", f"anoisesrc=d={target_secs}:c={a_color}:a={a_amp}",
                "-filter_complex", filtergraph,
                "-map", "[vout]", "-map", "[aout]",
                "-t", str(target_secs),
                "-c:v", "libx264",
                # Fixed 8 Mbps target — predictable file size, meets YouTube's recommended
                # 1080p bitrate. CRF 18 + ultrafast was producing 30-40 Mbps (huge files, slow).
                "-b:v", "8000k", "-maxrate", "10000k", "-bufsize", "20000k",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                # No +faststart: avoids a full file rewrite at the end (saves hours on large files)
                "-c:a", "aac", "-b:a", "192k",
                "-stats",
                output_video,
            ], check=True, stdout=log_fh, stderr=log_fh,
               timeout=target_secs * 4)
        try:
            os.remove(log_path)
        except Exception:
            pass
    except subprocess.CalledProcessError as e:
        print(f"[ASSEMBLE] ffmpeg failed (exit {e.returncode}) — last lines of {log_path}:")
        try:
            with open(log_path) as lf:
                for line in lf.read().splitlines()[-20:]:
                    print(f"  {line}")
        except Exception:
            pass
        raise RuntimeError(f"[ASSEMBLE] ffmpeg exited {e.returncode}") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"[ASSEMBLE] Video grade timed out after {target_secs * 4}s — "
            "input video may be corrupt or hardware is too slow."
        )


def assemble(theme_name=None, duration_label="2 hours", output_name=None, visual_path=None, music_files=None):
    target_secs = DURATION_MAP.get(duration_label, 7200)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
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
        print(f"  Using {len(playlist)} track(s): {[os.path.basename(p) for p in playlist]}")
        audio_path = concat_audio(playlist, target_secs, tmp_dir)


        # 2. Get visual
        visual_path = pick_visual(theme_name, prefer_path=visual_path)
        if not visual_path:
            print("  No visual found — generating a simple gradient background...")
            visual_path = os.path.join(tmp_dir, "gradient_bg.mp4")
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=0x0A0020:size=1280x720:rate=24",
                "-t", str(target_secs),
                "-c:v", "libx264", "-crf", "28",
                visual_path
            ], check=True, capture_output=True)

        print(f"  Visual: {os.path.basename(visual_path)}")

        # 3. Pre-bake static VHS grade onto the visual loop (once, ~seconds not hours)
        graded_visual = _pre_grade_visual(visual_path, tmp_dir)

        # 4. Merge pre-graded visual + audio (loop visual to fill duration)
        merged_path = os.path.join(tmp_dir, "merged.mp4")
        print("  Merging audio + video...")
        subprocess.run([
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", graded_visual,
            "-i", audio_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "copy",
            "-t", str(target_secs),
            "-shortest",
            merged_path
        ], check=True, capture_output=True)

        # 4. Apply VHS color grade + equalizer overlay + final encode
        print("  Applying VHS color grade + EQ overlay...")
        apply_vhs_grade(merged_path, out_path, target_secs, theme_name=theme_name)

        # Clean up only on success — on failure, leave tmp dir for inspection
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        print(f"  [ASSEMBLE] Temp files left in: {tmp_dir}")
        raise

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"[ASSEMBLE] Done: {out_path} ({size_mb:.1f} MB)")
    return out_path


if __name__ == "__main__":
    theme = sys.argv[1] if len(sys.argv) > 1 else None
    duration = sys.argv[2] if len(sys.argv) > 2 else "2 hours"
    assemble(theme, duration)
