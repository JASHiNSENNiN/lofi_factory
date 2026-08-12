"""
data.py — read-only views over the factory's on-disk state for the UI.

Pure reads of files publish.py/run.py already maintain (upload_log.json, the
output/ folder, live_state). No writes here.
"""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime

from . import config


def upload_history(limit: int = 30) -> list[dict]:
    """Most-recent-first entries from upload_log.json."""
    if not os.path.exists(config.UPLOAD_LOG):
        return []
    try:
        data = json.load(open(config.UPLOAD_LOG))
    except Exception:
        return []
    entries = data if isinstance(data, list) else data.get("entries", [])
    return list(reversed(entries))[:limit]


def output_videos(limit: int = 20) -> list[dict]:
    """Rendered mp4s in output/, newest first, with size + mtime."""
    vids = sorted(
        glob.glob(os.path.join(config.OUTPUT_DIR, "*.mp4")),
        key=os.path.getmtime,
        reverse=True,
    )
    out = []
    for path in vids[:limit]:
        try:
            st = os.stat(path)
            out.append({
                "name": os.path.basename(path),
                "path": path,
                "size_mb": round(st.st_size / 1_048_576, 1),
                "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
        except OSError:
            continue
    return out


def latest_video() -> str | None:
    vids = output_videos(limit=1)
    return vids[0]["path"] if vids else None


def live_status() -> dict | None:
    """live_state.json plus a real liveness check against ffmpeg_pid.

    None means no broadcast has been started (or state was cleared after one
    ended). A non-None result with alive=False means the state file thinks a
    stream is running but the ffmpeg process behind it has actually died --
    same "CRASHED / STALE" distinction the TUI dashboard makes.
    """
    path = os.path.join(config.ROOT, "live_state.json")
    if not os.path.exists(path):
        return None
    try:
        state = json.load(open(path))
    except Exception:
        return None
    pid = state.get("ffmpeg_pid")
    alive = False
    if pid:
        try:
            os.kill(pid, 0)
            alive = True
        except (ProcessLookupError, PermissionError):
            alive = False
    state["alive"] = alive
    return state


def cookies_status() -> dict:
    path = config.COOKIES_FILE
    if os.path.exists(path):
        st = os.stat(path)
        return {
            "present": True,
            "size_kb": round(st.st_size / 1024, 1),
            "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
        }
    return {"present": False, "size_kb": 0, "modified": None}
