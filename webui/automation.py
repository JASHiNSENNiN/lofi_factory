"""
automation.py — web UI control surface for the lofi-auto timer/service pair.

Unlike jobs.py (which owns subprocesses started BY the webui process), the
auto-upload run fires on a systemd timer (default: daily at midnight) so it
keeps generating/uploading on schedule across webui restarts and deploys.
This module just reflects/controls that independent timer via the shared
auto_service helper (also used by publish.py's `auto-service` CLI subcommand
and the web panel).
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import re

import auto_service as _svc

from . import config, system_admin

MIN_INTERVAL_HOURS = _svc.MIN_INTERVAL_HOURS
VALID_INTERVALS = _svc.VALID_INTERVALS

status = _svc.status

# Written by publish.py's _record_auto_result() -- tracks consecutive
# unattended-run failures so `auto` mode can fall back to the lightest
# duration tier instead of repeatedly re-rolling a pool that's already
# failing. Read-only here; this module only surfaces it for visibility.
_AUTO_STATE_FILE = os.path.join(config.ASSETS_DIR, ".auto_run_state.json")
AUTO_FALLBACK_AFTER_FAILURES = 2  # must match publish.py's own threshold


def auto_run_state() -> dict:
    """{"consecutive_failures": int, "in_fallback": bool} -- best-effort, a
    missing/corrupt state file just means no failures recorded yet."""
    try:
        with open(_AUTO_STATE_FILE) as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    failures = state.get("consecutive_failures", 0)
    return {"consecutive_failures": failures,
            "in_fallback": failures >= AUTO_FALLBACK_AFTER_FAILURES}


# Written by scripts/assemble_video.py's record_encode_speed_sample() after
# every encode attempt (success, stall-kill, or hard-timeout) -- the real,
# self-updating measurement publish.py's dynamic duration picker reads.
# Surfaced here too so it's visible, not just consumed invisibly by that
# picker -- confirmed 2026-08-16/17 this box's *actual* speed contradicted
# a hardcoded assumption in code, so watching it over time matters.
_ENCODE_SPEED_FILE = os.path.join(config.ASSETS_DIR, ".encode_speed_history.json")


def encode_speed_history() -> dict:
    """{"vaapi": [floats], "software": [floats]} -- most-recent-last, same
    shape assemble_video.py writes. Empty dict if nothing measured yet."""
    try:
        with open(_ENCODE_SPEED_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# ─────────────────────────────────────────────────────────────────────────────
# Live render progress for the unattended auto-run — read straight from the
# ffmpeg encode's own `-stats` log file and live /proc cmdline instead of
# lofi-auto's stdout (confirmed 2026-08-16: that unit has no
# PYTHONUNBUFFERED=1, so its own print()s can sit unflushed for many minutes;
# ffmpeg's -stats output bypasses that entirely by writing straight to
# scripts/assemble_video.py's `output/<video>.mp4.grade.log` file instead of
# stdout, and /proc/<pid>/cmdline is always current, not a log tail).
# ─────────────────────────────────────────────────────────────────────────────
def _cgroup_pids(unit: str) -> list[int]:
    uid = os.getuid()
    path = (f"/sys/fs/cgroup/user.slice/user-{uid}.slice/"
            f"user@{uid}.service/app.slice/{unit}/cgroup.procs")
    try:
        with open(path) as f:
            return [int(p) for p in f.read().split()]
    except OSError:
        return []


def _find_ffmpeg_pid(pids: list[int]) -> int | None:
    for pid in pids:
        try:
            with open(f"/proc/{pid}/comm") as f:
                if f.read().strip() == "ffmpeg":
                    return pid
        except OSError:
            continue
    return None


def _ffmpeg_target_secs(pid: int) -> int | None:
    """The `-t <secs>` argument off the live process's own argv -- exact and
    always current, unlike anything derived from log text."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            args = f.read().decode(errors="replace").split("\0")
        if "-t" in args:
            return int(args[args.index("-t") + 1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def render_progress() -> dict | None:
    """Best-effort snapshot of the unattended auto-render's current stage,
    and percent/ETA when it's in the final encode. None if nothing's running.
    {"stage": "generating"|"encoding"|"uploading",
     "percent": float|None, "eta_secs": float|None, "speed": float|None}"""
    if not status().get("running_now"):
        return None

    pids = _cgroup_pids("lofi-auto.service")
    ffmpeg_pid = _find_ffmpeg_pid(pids)

    if ffmpeg_pid is None:
        # No encoder running yet/anymore -- either still generating music/
        # visual/SEO, or past encoding and into the upload step. A finished
        # .grade.log's sibling .mp4 stops growing once ffmpeg exits and
        # ~publish.py moves on to upload_youtube.py, so "log file exists but
        # no ffmpeg process" is the signal for that transition.
        stage = "uploading" if glob.glob(os.path.join(config.OUTPUT_DIR, "*.mp4.grade.log")) \
            else "generating"
        return {"stage": stage, "percent": None, "eta_secs": None, "speed": None}

    target_secs = _ffmpeg_target_secs(ffmpeg_pid)
    logs = sorted(glob.glob(os.path.join(config.OUTPUT_DIR, "*.mp4.grade.log")),
                  key=os.path.getmtime, reverse=True)
    if not logs or not target_secs:
        return {"stage": "encoding", "percent": None, "eta_secs": None, "speed": None}

    try:
        size = os.path.getsize(logs[0])
        with open(logs[0], "rb") as f:
            f.seek(max(0, size - 4000))
            tail = f.read().decode(errors="replace")
    except OSError:
        return {"stage": "encoding", "percent": None, "eta_secs": None, "speed": None}

    times = re.findall(r"time=(\d+):(\d+):(\d+)\.\d+", tail)
    speeds = re.findall(r"speed=\s*([\d.]+)x", tail)
    if not times:
        return {"stage": "encoding", "percent": None, "eta_secs": None, "speed": None}

    h, m, s = (int(x) for x in times[-1])
    elapsed_secs = h * 3600 + m * 60 + s
    percent = min(elapsed_secs / target_secs, 0.999) * 100
    speed = float(speeds[-1]) if speeds else None
    eta_secs = (target_secs - elapsed_secs) / speed if speed else None
    return {"stage": "encoding", "percent": percent, "eta_secs": eta_secs, "speed": speed}


# NiceGUI runs on a single-threaded asyncio event loop. _svc.start/run_now/etc.
# shell out via subprocess.run(), which is fully synchronous -- and since
# lofi-auto.service is Type=oneshot, `systemctl --user start lofi-auto.service`
# blocks until the whole render+upload pipeline finishes (can be minutes).
# Calling that directly from a button handler used to freeze the *entire*
# webui for every client for the full run duration (TLS handshakes included --
# the event loop never got back to accept()). Push each call to a worker
# thread so the event loop stays free; publish.py's CLI and the panel's
# TUI still call auto_service's sync functions directly, which is fine there
# since neither has other concurrent clients to starve.
#
# Each also logs a system_admin.audit_log entry on success only -- an
# exception from _svc propagates before the log call, so a failed systemctl
# call is never recorded as if it had succeeded.


async def start() -> None:
    await asyncio.to_thread(_svc.start)
    system_admin.audit_log("automation_start", {})


async def stop() -> None:
    await asyncio.to_thread(_svc.stop)
    system_admin.audit_log("automation_stop", {})


async def set_enabled(enabled: bool) -> None:
    await asyncio.to_thread(_svc.set_enabled, enabled)
    system_admin.audit_log("automation_set_enabled", {"enabled": enabled})


async def run_now() -> None:
    await asyncio.to_thread(_svc.run_now)
    system_admin.audit_log("automation_run_now", {})


async def set_schedule(hour: int, every_hours: int) -> None:
    await asyncio.to_thread(_svc.set_schedule, hour, every_hours)
    system_admin.audit_log(
        "automation_set_schedule", {"start_hour": hour, "every_hours": every_hours})


# Sync passthrough, same as auto_service's other read-only functions --
# callers on the async side (app.py's Automation view) run it via
# asyncio.to_thread since it shells out to `systemctl show` under the hood.
resource_status = _svc.resource_status


async def tail_logs(on_line, n: int = 200) -> asyncio.subprocess.Process:
    """Stream `journalctl --user -u lofi-auto -f` lines to on_line(str).

    Returns the process so the caller can terminate it when the page closes.
    """
    proc = await asyncio.create_subprocess_exec(
        *_svc.logs_cmd(n=n, follow=True),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async def _pump() -> None:
        assert proc.stdout is not None
        async for raw in proc.stdout:
            on_line(raw.decode(errors="replace").rstrip("\n"))

    asyncio.create_task(_pump())
    return proc
