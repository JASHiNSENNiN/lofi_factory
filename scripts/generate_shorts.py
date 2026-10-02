"""
generate_shorts.py — Shorts repurposing pipeline.

Takes an already-assembled long-form lofi video (run.py's normal output) and
its audio, automatically picks a vertical-friendly "highlight" window instead
of a fixed timestamp, crops/pads it to 9:16, and (optionally) uploads it as a
YouTube Short via scripts/upload_youtube.py.

HIGHLIGHT SELECTION
  Lofi tracks are mostly steady-state (no big drops to detect), so "highlight"
  here means "peak energy" — the window_secs-long span with the highest mean
  RMS loudness, on the theory that the fullest-sounding part of the mix is
  the best few seconds to hook a Shorts viewer. This follows the same simple
  RMS formula scripts/drum_sampler.py and scripts/lofi_fx.py's own filters
  use elsewhere in this codebase (sqrt(mean(x**2))), computed here via a
  streaming block read (soundfile.SoundFile, no full-file numpy load) so it
  stays memory-safe against a multi-hour source track. lofi_fx.py's FX chain
  itself is not imported or modified — this only reuses the same RMS idiom,
  read-only.

DURATION
  <=60s is the safest cross-device target for YouTube Shorts (the vertical
  Shorts shelf), so the default window is 58s to leave ffmpeg trim/encode
  rounding some margin.

CROSS-POSTING (TikTok / Instagram Reels)
  Deliberately NOT implemented — see crosspost() below. Off by default
  (CROSSPOST_ENABLED unset), and even when enabled it raises a clear
  "not implemented" error rather than pretending to upload anywhere. Neither
  platform offers a first-party free API for this; a real integration needs
  a paid aggregator (e.g. Ayrshare) or a heavily-gated first-party developer
  app — see the crosspost() docstring for specifics.

CLI
  python scripts/generate_shorts.py --video output/lofi_XYZ.mp4
  python scripts/generate_shorts.py --video output/lofi_XYZ.mp4 --save-only
  python scripts/generate_shorts.py --video output/lofi_XYZ.mp4 --window-secs 45
Also reachable via `python publish.py shorts ...` (see publish.py's `shorts`
subcommand, which delegates to run_pipeline() below).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUTPUT_DIR = os.path.join(ROOT, "output")
ASSETS_DIR = os.path.join(ROOT, "assets")
SHORTS_DIR = os.path.join(OUTPUT_DIR, "shorts")

# Safest cross-device Shorts duration target (YouTube's vertical-Shorts shelf).
DEFAULT_WINDOW_SECS = 58.0
SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920

# Off by default -- see crosspost() below for why this stays a stub.
CROSSPOST_ENABLED = os.environ.get("CROSSPOST_ENABLED", "") == "1"


# ─────────────────────────────────────────────────────────────────────────────
# Highlight-window selection
# ─────────────────────────────────────────────────────────────────────────────
def pick_highlight_window(rms, times, total_secs: float,
                            window_secs: float = DEFAULT_WINDOW_SECS) -> tuple[float, float]:
    """
    Pure windowing logic over a precomputed RMS energy curve (no file I/O —
    unit-testable with a synthetic curve). `rms`/`times` are equal-length
    sequences: `rms[i]` is the energy of the block starting at `times[i]`
    seconds. Returns (start_sec, end_sec) for the window_secs-long span with
    the highest mean energy.

    Falls back to (0, min(window_secs, total_secs)) whenever there isn't
    enough signal to meaningfully compare windows (empty curve, or the
    track is already shorter than window_secs) rather than guessing.
    """
    total_secs = max(0.0, float(total_secs))
    if total_secs <= window_secs or len(rms) == 0:
        return 0.0, min(window_secs, total_secs)

    n = len(times)
    best_start, best_score, found = 0.0, -1.0, False
    for i in range(n):
        t = times[i]
        if t + window_secs > total_secs:
            break
        end = t + window_secs
        vals = [rms[j] for j in range(i, n) if times[j] < end]
        if not vals:
            continue
        score = sum(vals) / len(vals)
        found = True
        if score > best_score:
            best_score, best_start = score, t

    if not found:
        return 0.0, min(window_secs, total_secs)
    return best_start, best_start + window_secs


def _rms_curve_from_file(audio_path: str, hop_secs: float = 1.0):
    """
    Streaming short-time RMS energy curve, one value per `hop_secs`-long
    block, read via soundfile.SoundFile.read() in a loop rather than loading
    the whole file into memory at once -- lofi masters can run for hours, and
    a naive full-file numpy load (`sf.read()`, as lofi_fx.py's Pedalboard
    chain does for a normal-length track) would be tens of GB for those.
    Returns (rms: list[float], times: list[float], total_secs: float).
    """
    import numpy as np
    import soundfile as sf

    info = sf.info(audio_path)
    sr = info.samplerate or 44100
    total_secs = (info.frames / sr) if sr else 0.0
    hop = max(1, int(hop_secs * sr))

    rms: list[float] = []
    times: list[float] = []
    t = 0.0
    with sf.SoundFile(audio_path) as f:
        while True:
            block = f.read(hop, dtype="float32", always_2d=True)
            if block.shape[0] == 0:
                break
            mono = block.mean(axis=1)
            rms.append(float(np.sqrt(np.mean(np.square(mono)) + 1e-12)))
            times.append(t)
            t += hop_secs
            if block.shape[0] < hop:
                break
    return rms, times, total_secs


def select_highlight_window(audio_path: str, window_secs: float = DEFAULT_WINDOW_SECS,
                              hop_secs: float = 1.0) -> tuple[float, float]:
    """Load `audio_path` and return the best (start_sec, end_sec) window."""
    rms, times, total_secs = _rms_curve_from_file(audio_path, hop_secs=hop_secs)
    return pick_highlight_window(rms, times, total_secs, window_secs=window_secs)


# ─────────────────────────────────────────────────────────────────────────────
# ffmpeg: audio extraction + vertical crop
# ─────────────────────────────────────────────────────────────────────────────
def extract_audio_track(video_path: str, out_wav: str) -> None:
    """Pull the audio track out of a video file as 44.1kHz stereo PCM WAV, so
    _rms_curve_from_file() can analyze it without decoding video frames."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn",
         "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", out_wav],
        check=True, capture_output=True,
    )


def get_video_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except (ValueError, TypeError):
        return 0.0


def build_vertical_clip(video_path: str, out_path: str, start_sec: float, end_sec: float) -> None:
    """
    Trim [start_sec, end_sec) from `video_path` into a 1080x1920 vertical clip:
    the whole 16:9 frame scaled to the full width, centred over a blurred,
    zoomed copy of itself filling the rest. (A centre crop kept only the
    middle ~30% of the frame and cut the on-screen title panel in half.)
    """
    duration = max(0.1, end_sec - start_sec)
    vf = (f"split=2[bgsrc][fgsrc];"
          f"[bgsrc]scale=w={SHORTS_WIDTH}:h={SHORTS_HEIGHT}:force_original_aspect_ratio=increase,"
          f"crop={SHORTS_WIDTH}:{SHORTS_HEIGHT},boxblur=20:2,eq=brightness=-0.08[bg];"
          f"[fgsrc]scale={SHORTS_WIDTH}:-2[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{start_sec:.2f}", "-i", video_path, "-t", f"{duration:.2f}",
         "-filter_complex", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_path],
        check=True, capture_output=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Metadata
# ─────────────────────────────────────────────────────────────────────────────
def build_shorts_metadata(seo: dict, title_override: str | None = None) -> dict:
    """
    Derive Shorts-compliant title/description/tags from the long-form
    video's SEO dict (assets/seo_*.json). Pure/testable: no I/O.

    - Title: the long-form title, trimmed to leave room for a trailing
      " #Shorts" tag within YouTube's 100-char title limit.
    - Description/tags: carried over, with #Shorts guaranteed present per
      YouTube's own Shorts-discoverability convention.
    """
    base_title = title_override or seo.get("title") or "lo-fi beats"
    suffix = " #Shorts"
    title = f"{base_title[:100 - len(suffix)].rstrip()}{suffix}"[:100]

    description = (seo.get("description") or "Lo-fi beats.").strip()
    if "#shorts" not in description.lower():
        description = f"{description}\n\n#Shorts #lofi #shorts"
    description = description[:4900]

    tags = [t for t in seo.get("tags", []) if isinstance(t, str)]
    if not any(t.lower() == "shorts" for t in tags):
        tags = ["Shorts", "lofi shorts"] + tags

    return {
        "title": title,
        "description": description,
        "tags": tags,
        "category_id": seo.get("category_id", "10"),
        "privacy": seo.get("privacy", "public"),
        "made_for_kids": seo.get("made_for_kids", False),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Cross-posting stub (TikTok / Instagram Reels) — deliberately not implemented
# ─────────────────────────────────────────────────────────────────────────────
def crosspost(video_path: str, platforms: list[str] | None = None) -> dict:
    """
    Opt-in stub for cross-posting a finished Short to TikTok / Instagram
    Reels. Off by default (CROSSPOST_ENABLED unset or not "1").

    Even when enabled, this deliberately does NOT fake an upload — it raises
    NotImplementedError, because neither platform has a first-party free
    upload API suited to this pipeline:
      - TikTok's Content Posting API requires an approved developer app tied
        to an audited use case (not just an API key).
      - Instagram Reels publishing requires a Meta Business app that has
        passed App Review for the instagram_content_publish permission.
    A real integration needs EITHER:
      1. A paid third-party aggregator (e.g. Ayrshare, https://www.ayrshare.com)
         that handles both platforms' OAuth + upload behind one API call and
         a monthly fee, OR
      2. Direct platform apps as described above, each with their own
         review process and rate limits.
    Wiring either one in means: a provider API key env var, an HTTP client
    call per platform here, and its own retry/error handling (mirroring
    upload_youtube.py's chunked-upload exponential backoff). None of that is
    implemented on purpose — a clearly-labeled error is safer than silently
    no-op'ing or claiming a cross-post succeeded when nothing was sent.
    """
    if not CROSSPOST_ENABLED:
        return {"attempted": False, "platforms": platforms or [],
                "reason": "CROSSPOST_ENABLED is not set to \"1\" -- cross-posting is off by default"}
    raise NotImplementedError(
        "CROSSPOST_ENABLED=1 but no cross-post provider is wired up. See the crosspost() "
        "docstring in scripts/generate_shorts.py for what a real TikTok/Instagram Reels "
        "integration needs (e.g. an Ayrshare API key) before enabling this."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────
def _find_latest(directory: str, pattern: str) -> str | None:
    files = sorted(glob.glob(os.path.join(directory, pattern)), key=os.path.getmtime, reverse=True)
    return files[0] if files else None


def _load_seo(seo_path: str | None) -> dict:
    path = seo_path or _find_latest(ASSETS_DIR, "seo_*.json")
    if not path or not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def run_pipeline(video_path: str | None = None, seo_path: str | None = None,
                   out_path: str | None = None, window_secs: float = DEFAULT_WINDOW_SECS,
                   upload: bool = True, privacy: str | None = None,
                   title_override: str | None = None, youtube=None,
                   crosspost_platforms: list[str] | None = None) -> dict:
    """
    End-to-end: pick a highlight window, render the vertical clip, optionally
    upload it as a Short, optionally attempt cross-posting. Returns a summary
    dict describing what happened -- callers (CLI / publish.py) print/log it.
    """
    video_path = video_path or _find_latest(OUTPUT_DIR, "lofi_*.mp4")
    if not video_path or not os.path.exists(video_path):
        raise FileNotFoundError("No source video found -- pass --video or run.py first")

    seo = _load_seo(seo_path)
    total_secs = get_video_duration(video_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = os.path.join(tmpdir, "audio.wav")
        extract_audio_track(video_path, wav_path)
        start_sec, end_sec = select_highlight_window(wav_path, window_secs=window_secs)

    if end_sec <= start_sec:
        # Degenerate source (near-zero duration) -- fall back to the very start
        # rather than producing an empty/invalid clip.
        start_sec, end_sec = 0.0, min(window_secs, max(total_secs, window_secs))

    stem = os.path.splitext(os.path.basename(video_path))[0]
    out_path = out_path or os.path.join(SHORTS_DIR, f"{stem}_short.mp4")
    build_vertical_clip(video_path, out_path, start_sec, end_sec)

    metadata = build_shorts_metadata(seo, title_override=title_override)
    if privacy:
        metadata["privacy"] = privacy

    result = {
        "source_video": video_path,
        "clip_path": out_path,
        "window": {"start_sec": round(start_sec, 2), "end_sec": round(end_sec, 2)},
        "metadata": metadata,
        "uploaded": False,
        "video_id": None,
        "url": None,
        "crosspost": None,
    }

    if upload:
        if youtube is None:
            from scripts.upload_youtube import get_authenticated_service
            youtube = get_authenticated_service()
        from scripts.upload_youtube import upload_video
        thumb_path = None  # Shorts auto-generate a thumbnail from the frame; no custom thumb needed
        video_id, url = upload_video(youtube, out_path, metadata, thumb_path)
        result["uploaded"] = True
        result["video_id"] = video_id
        result["url"] = url

        if crosspost_platforms:
            result["crosspost"] = crosspost(out_path, crosspost_platforms)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Repurpose a long-form lofi video into a YouTube Short")
    parser.add_argument("--video", help="Source video (default: latest in output/)")
    parser.add_argument("--seo", help="SEO JSON to derive title/description/tags from")
    parser.add_argument("--out", help="Output path for the vertical clip")
    parser.add_argument("--window-secs", type=float, default=DEFAULT_WINDOW_SECS,
                        help=f"Clip length in seconds (default: {DEFAULT_WINDOW_SECS} -- "
                             f"keep <=60 for Shorts eligibility)")
    parser.add_argument("--title", help="Override the Short's title (before the #Shorts suffix)")
    parser.add_argument("--privacy", choices=["public", "unlisted", "private"], default=None)
    parser.add_argument("--save-only", action="store_true",
                        help="Render the vertical clip locally without uploading")
    parser.add_argument("--crosspost", nargs="*", default=None, metavar="PLATFORM",
                        help="Attempt cross-posting to these platforms after upload "
                             "(requires CROSSPOST_ENABLED=1; see crosspost() docstring)")
    args = parser.parse_args()

    result = run_pipeline(
        video_path=args.video, seo_path=args.seo, out_path=args.out,
        window_secs=args.window_secs, upload=not args.save_only,
        privacy=args.privacy, title_override=args.title,
        crosspost_platforms=args.crosspost,
    )

    print(f"\n[shorts] Clip: {result['clip_path']}")
    print(f"  Highlight window: {result['window']['start_sec']}s - {result['window']['end_sec']}s")
    print(f"  Title: {result['metadata']['title']}")
    if result["uploaded"]:
        print(f"  Uploaded: {result['url']}")
    else:
        print("  Not uploaded (--save-only)")
    if result["crosspost"]:
        print(f"  Cross-post: {result['crosspost']}")


if __name__ == "__main__":
    main()
