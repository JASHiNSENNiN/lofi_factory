"""
data.py — read-only views over the factory's on-disk state for the UI, plus
a small, deliberately narrow set of delete operations for the Library/Samples
tabs (see delete_render/render_delete_manifest and delete_sample below).
"""
from __future__ import annotations

import glob
import json
import os
import re
import time
from datetime import datetime, timezone

from . import config, system_admin

# Files younger than this are likely still being written by an in-progress
# render (e.g. an mp4's moov atom isn't written until the encode finishes) --
# listing them would show a player that can't actually play yet. A 90s grace
# window comfortably covers the gap without meaningfully delaying visibility
# of a real finished file.
_MIN_SAMPLE_AGE_SECS = 90


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


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def calendar_entries(upload_entries: list[dict] | None = None,
                      queue_pending: list | None = None) -> dict:
    """
    Assemble the Content Calendar page's data: a chronological timeline of
    past + future-scheduled uploads, plus the batch queue's still-pending
    items (which don't have a fixed clock time -- they run next-in-line as
    soon as a job slot frees up, see webui/jobs.py's JobQueue).

    Pure by default only in the sense that both args are overridable: pass
    explicit lists (as the tests do) to assemble from synthetic data with no
    file/singleton access at all. Called with no args, it reads live state
    (upload_log.json via upload_history(), and jobs.queue's pending list).

    Returns {"timeline": [...], "queue_pending": [...]}.
      timeline entries: {"kind", "when": datetime|None, "title", "status",
        "url", "video_id"} sorted newest/soonest-first (entries with no
        parseable timestamp sort last, not first -- a malformed log line
        shouldn't jump to the top of the page).
      queue_pending entries: {"id", "name", "slot", "note", "added_at", "args"}
        in queue (FIFO execution) order.
    """
    if upload_entries is None:
        upload_entries = upload_history(limit=200)
    if queue_pending is None:
        from . import jobs as _jobs
        queue_pending = _jobs.queue.list_pending()

    timeline: list[dict] = []
    for e in upload_entries:
        if not isinstance(e, dict):
            continue
        etype = e.get("type") or "upload"
        scheduled_at = e.get("scheduled_at")
        if etype == "upload" and scheduled_at:
            when = _parse_iso(scheduled_at)
            kind, status = "scheduled", "scheduled (private until publish)"
        elif etype == "upload":
            when = _parse_iso(e.get("timestamp"))
            kind, status = "published", "public"
        elif etype == "live":
            when = _parse_iso(e.get("timestamp"))
            kind, status = "live", "streamed"
        elif etype == "scheduled":
            when = _parse_iso(e.get("scheduled_at") or e.get("timestamp"))
            kind, status = "scheduled_live", "scheduled (live broadcast)"
        else:
            when = _parse_iso(e.get("timestamp"))
            kind, status = etype, etype
        timeline.append({
            "kind": kind,
            "when": when,
            "title": e.get("title") or "(untitled)",
            "status": status,
            "url": e.get("url"),
            "video_id": e.get("video_id"),
        })

    # None sorts last: a malformed/missing timestamp shouldn't float to the
    # top just because it compares as "smaller" than every real datetime.
    _epoch = datetime.min.replace(tzinfo=timezone.utc)
    timeline.sort(key=lambda x: x["when"] or _epoch, reverse=True)

    pending = [{
        "id": item.id, "name": item.name, "slot": item.slot,
        "note": item.note, "added_at": item.added_at, "args": item.args,
        "status": item.status,
    } for item in queue_pending]

    return {"timeline": timeline, "queue_pending": pending}


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


def _pid_alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, PermissionError, ValueError):
        return False


def live_status() -> dict | None:
    """The running broadcast, from either live system, with a real liveness
    check. `mode` is "single" (publish.py live: one finished video, looped;
    live_state.json) or "24/7" (stream_live.py: endless, generating music;
    stream_state.json).

    None means nothing is live (or the state was cleared after it ended).
    alive=False means a state file says a stream runs but its process is gone
    (CRASHED / STALE).
    """
    for name, mode, pid_key in (("live_state.json", "single", "ffmpeg_pid"),
                                ("stream_state.json", "24/7", "pid")):
        path = os.path.join(config.ROOT, name)
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                state = json.load(f)
        except Exception:
            continue
        state["mode"] = mode
        state["alive"] = _pid_alive(state.get(pid_key))
        return state
    return None


def clear_247_state() -> None:
    try:
        os.remove(os.path.join(config.ROOT, "stream_state.json"))
    except OSError:
        pass


def stop_247_stream() -> bool:
    """Ask a running stream_live.py to stop. It ends its YouTube broadcast and
    clears stream_state.json itself. Only signals a PID that really is that
    script, so a stale file can't hit an unrelated process."""
    import signal
    path = os.path.join(config.ROOT, "stream_state.json")
    try:
        with open(path) as f:
            pid = int(json.load(f).get("pid"))
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = f.read().replace(b"\0", b" ").decode(errors="replace")
    except (OSError, ValueError, TypeError):
        return False
    if "stream_live" not in cmdline and "--stream" not in cmdline:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        return False


def render_delete_manifest(card: dict) -> list[dict]:
    """
    Files a `stats.library()` card positively owns -- the exact set
    `delete_render` will remove. Deliberately narrow: only the thumbnail
    (+ its `_alt.jpg` sibling, by naming convention), the local mp4 (+ its
    `.grade.log`), and that render's own `output/tmp_{ts}/` dir if one is
    still around. Never touches `music/*.wav` or `visuals/bg_*.mp4` -- those
    are shared/reused across renders (see run.py's own pruning logic), not
    1:1 owned by a single render, so deleting them here could silently break
    other cards. Returns [] entries only for paths that actually exist, so a
    stale/already-cleaned-up card doesn't show phantom rows in the confirm
    dialog.
    """
    paths: list[str] = []

    thumb = card.get("thumb")
    if thumb and os.path.exists(thumb):
        paths.append(thumb)
        stem, ext = os.path.splitext(thumb)
        alt = f"{stem}_alt{ext}"
        if os.path.exists(alt):
            paths.append(alt)

    video_file = card.get("video_file")
    if video_file:
        video_path = os.path.join(config.OUTPUT_DIR, video_file)
        if os.path.exists(video_path):
            paths.append(video_path)
        grade_log = video_path + ".grade.log"
        if os.path.exists(grade_log):
            paths.append(grade_log)
        m = re.search(r"(\d{8}_\d{6})", video_file)
        if m:
            tmp_dir = os.path.join(config.OUTPUT_DIR, f"tmp_{m.group(1)}")
            if os.path.isdir(tmp_dir):
                for root, _dirs, files in os.walk(tmp_dir):
                    for f in files:
                        paths.append(os.path.join(root, f))
                paths.append(tmp_dir)  # dir itself, removed last

    manifest = []
    for p in paths:
        try:
            size = 0 if os.path.isdir(p) else os.path.getsize(p)
        except OSError:
            size = 0
        manifest.append({"path": p, "name": os.path.basename(p), "size_bytes": size})
    return manifest


def delete_render(card: dict) -> list[str]:
    """Delete exactly the files render_delete_manifest(card) identifies. Best-
    effort per-file (a partial failure doesn't abort the rest); returns the
    paths actually removed.

    Refuses outright while any render job is running -- a real incident, not
    a hypothetical: a user deleted the one card showing (an in-progress
    render's own thumbnail/video, which stats.library() has no way to
    distinguish from a finished one) while it was still being written,
    permanently losing an hours-long encode's output the moment ffmpeg
    closed the now-unlinked file. Blocking delete entirely during any run is
    coarser than strictly necessary (it also blocks deleting unrelated old
    renders), but correlating "this card == that specific running job"
    isn't reliable before the job's [RESULT] line lands, and simple +
    guaranteed-safe beats clever + still-losable here.
    """
    import shutil

    from . import jobs
    if jobs.manager.is_busy():
        raise RuntimeError(
            "A render is in progress -- delete is disabled until it finishes, "
            "so an in-progress file can't be deleted out from under it.")

    manifest = render_delete_manifest(card)
    removed = []
    for entry in manifest:
        p = entry["path"]
        try:
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
            removed.append(p)
        except OSError:
            continue
    if removed:
        system_admin.audit_log(
            "render_delete", {"video_file": card.get("video_file"), "removed": removed})
    return removed


def _wav_duration_secs(path: str) -> float | None:
    import wave
    try:
        with wave.open(path, "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return None


def _ffprobe_duration_secs(path: str) -> float | None:
    import subprocess
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10,
        )
        return float(out.stdout.strip())
    except Exception:
        return None


def music_samples(limit: int = 60) -> list[dict]:
    """Standalone generated tracks in music/*.wav -- these are full, playable
    soundtracks (or stems) rendered before any video assembly, invisible to
    the rest of the UI today. Newest first."""
    paths = sorted(
        glob.glob(os.path.join(config.MUSIC_DIR, "track_*.wav")),
        key=os.path.getmtime, reverse=True,
    )
    out = []
    now = time.time()
    for path in paths[:limit]:
        try:
            st = os.stat(path)
        except OSError:
            continue
        if now - st.st_mtime < _MIN_SAMPLE_AGE_SECS:
            continue  # likely still being written by an in-progress render
        meta = {}
        meta_path = path + ".meta.json"
        if os.path.exists(meta_path):
            try:
                meta = json.load(open(meta_path))
            except Exception:
                meta = {}
        dur = _wav_duration_secs(path)
        out.append({
            "name": os.path.basename(path),
            "path": path,
            "title": meta.get("title") or os.path.basename(path),
            "genre": meta.get("genre"),
            "size_mb": round(st.st_size / 1_048_576, 1),
            "duration_secs": dur,
            "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return out


def visual_samples(limit: int = 60) -> list[dict]:
    """Background visual loops in visuals/bg_*.mp4 -- silent, theme-tagged,
    reused across renders. Newest first."""
    paths = sorted(
        glob.glob(os.path.join(config.VISUALS_DIR, "bg_*.mp4")),
        key=os.path.getmtime, reverse=True,
    )
    out = []
    now = time.time()
    for path in paths[:limit]:
        try:
            st = os.stat(path)
        except OSError:
            continue
        if now - st.st_mtime < _MIN_SAMPLE_AGE_SECS:
            continue  # likely still being written by an in-progress render
        name = os.path.basename(path)
        m = re.match(r"^bg_(?P<theme>.+)_\d{8}_\d{6}\.mp4$", name)
        theme = m["theme"].replace("_", " ") if m else "unknown"
        out.append({
            "name": name,
            "path": path,
            "theme": theme,
            "size_mb": round(st.st_size / 1_048_576, 1),
            "duration_secs": _ffprobe_duration_secs(path),
            "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return out


def delete_sample(path: str) -> bool:
    """Delete one music/visual sample file (+ its .meta.json sidecar for
    music tracks, if present). `path` must resolve inside MUSIC_DIR or
    VISUALS_DIR -- rejects anything else so this can't be pointed at
    arbitrary files."""
    real = os.path.realpath(path)
    allowed_roots = (os.path.realpath(config.MUSIC_DIR), os.path.realpath(config.VISUALS_DIR))
    if not any(real.startswith(root + os.sep) for root in allowed_roots):
        return False
    if not os.path.isfile(real):
        return False
    try:
        os.remove(real)
    except OSError:
        return False
    meta = real + ".meta.json"
    if os.path.exists(meta):
        try:
            os.remove(meta)
        except OSError:
            pass
    return True


