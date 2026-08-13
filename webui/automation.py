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

MIN_INTERVAL_HOURS = _svc.MIN_INTERVAL_HOURS
VALID_INTERVALS = _svc.VALID_INTERVALS

status = _svc.status
start = _svc.start
stop = _svc.stop
set_enabled = _svc.set_enabled
run_now = _svc.run_now
set_schedule = _svc.set_schedule
# Sync passthrough, same as the rest of this module -- callers on the async
# side (app.py's Automation view) run it via asyncio.to_thread since it
# shells out to `systemctl show` under the hood.
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
