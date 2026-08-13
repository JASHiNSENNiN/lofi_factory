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
run_now = _svc.run_now


# start/stop/set_enabled/set_schedule are thin wrappers (rather than the
# plain aliases the rest of this module uses) so each successful admin
# action gets an audit-log entry -- see system_admin.audit_log. Raised
# exceptions from _svc propagate before the log call, so a failed systemctl
# call is never recorded as if it had succeeded.
def start() -> None:
    _svc.start()
    system_admin.audit_log("automation_start", {})


def stop() -> None:
    _svc.stop()
    system_admin.audit_log("automation_stop", {})


def set_enabled(enabled: bool) -> None:
    _svc.set_enabled(enabled)
    system_admin.audit_log("automation_set_enabled", {"enabled": enabled})


def set_schedule(start_hour: int = 0, every_hours: int = 24) -> None:
    _svc.set_schedule(start_hour, every_hours)
    system_admin.audit_log(
        "automation_set_schedule", {"start_hour": start_hour, "every_hours": every_hours})


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
