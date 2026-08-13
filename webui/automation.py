"""
automation.py — web UI control surface for the lofi-auto timer/service pair.

Unlike jobs.py (which owns subprocesses started BY the webui process), the
auto-upload run fires on a systemd timer (default: daily at midnight) so it
keeps generating/uploading on schedule across webui restarts and deploys.
This module just reflects/controls that independent timer via the shared
auto_service helper (also used by publish.py's `auto-service` CLI subcommand
and dashboard.py's TUI panel).
"""
from __future__ import annotations

import asyncio

import auto_service as _svc

from . import system_admin

MIN_INTERVAL_HOURS = _svc.MIN_INTERVAL_HOURS
VALID_INTERVALS = _svc.VALID_INTERVALS

status = _svc.status

# NiceGUI runs on a single-threaded asyncio event loop. _svc.start/run_now/etc.
# shell out via subprocess.run(), which is fully synchronous -- and since
# lofi-auto.service is Type=oneshot, `systemctl --user start lofi-auto.service`
# blocks until the whole render+upload pipeline finishes (can be minutes).
# Calling that directly from a button handler used to freeze the *entire*
# webui for every client for the full run duration (TLS handshakes included --
# the event loop never got back to accept()). Push each call to a worker
# thread so the event loop stays free; publish.py's CLI and dashboard.py's
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
