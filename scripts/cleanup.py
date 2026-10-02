"""Disk cleanup after a successful upload.

Called by every path that uploads a freshly rendered video (publish.py auto,
the web panel's render+upload, and run.py without --skip-upload), so the
box doesn't fill up with multi-GB renders. The live stream's library in
music/stream/ is never touched.
"""
from __future__ import annotations

import glob
import os
import time

KEEP_VISUAL_LOOPS = 2
KEEP_TRACKS = 40                  # about two videos' worth of tracks
KEEP_ASSET_DAYS = 35              # thumbnail swaps look at videos up to 30 days old


def _remove(path: str) -> int:
    try:
        size = os.path.getsize(path)
        os.remove(path)
        return size
    except OSError:
        return 0


def _prune_newest(pattern: str, keep: int, sidecar_suffix: str | None = None) -> int:
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    freed = 0
    for f in files[keep:]:
        freed += _remove(f)
        if sidecar_suffix:
            freed += _remove(f + sidecar_suffix)
    return freed


def _prune_older_than(pattern: str, days: float) -> int:
    cutoff = time.time() - days * 86400
    return sum(_remove(f) for f in glob.glob(pattern) if os.path.getmtime(f) < cutoff)


def cleanup_after_upload(root: str, uploaded_video: str | None) -> int:
    """Delete the uploaded render and prune old intermediates. Returns bytes freed."""
    freed = _remove(uploaded_video) if uploaded_video else 0
    freed += _prune_newest(os.path.join(root, "visuals", "bg_*.mp4"), KEEP_VISUAL_LOOPS)
    for ext in ("wav", "mp3"):
        freed += _prune_newest(os.path.join(root, "music", f"*.{ext}"), KEEP_TRACKS,
                               sidecar_suffix=".meta.json")
    for pattern in ("thumb_*.png", "thumb_*.jpg", "seo_*.json"):
        freed += _prune_older_than(os.path.join(root, "assets", pattern), KEEP_ASSET_DAYS)
    for d in glob.glob(os.path.join(root, "output", "tmp_*")):
        if os.path.isdir(d) and os.path.getmtime(d) < time.time() - 86400:
            for f in glob.glob(os.path.join(d, "*")):
                freed += _remove(f)
            try:
                os.rmdir(d)
            except OSError:
                pass
    if freed:
        print(f"\n[cleanup] Freed {freed / 1_048_576:.1f} MB of disk space.")
    return freed
