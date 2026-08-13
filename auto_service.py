"""
auto_service.py — thin wrapper around `systemctl --user` / `journalctl --user`
for the lofi-auto timer/service pair (the standalone 24/7 render+upload job).

Scheduling model: lofi-auto.timer fires on a wall-clock schedule (default:
daily at 00:00) which triggers lofi-auto.service, a oneshot unit that runs
`publish.py auto` once and exits. A sleep-based loop can't reliably land on
a specific time of day (it drifts, and restarts don't re-anchor to the
clock) — a systemd timer does this natively and also survives reboots
(Persistent=true catches up a missed run).

The schedule is stored as a systemd calendar expression in a drop-in
override (~/.config/systemd/user/lofi-auto.timer.d/schedule.conf) so it
survives re-running deploy/setup.sh, which only touches the base unit files.

This module is the single place that knows how to reflect/control the
schedule — publish.py's `auto-service` CLI subcommand, dashboard.py's TUI
panel, and webui/automation.py all import it so the three surfaces stay in
sync.
"""
from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path

TIMER = "lofi-auto.timer"
SERVICE = "lofi-auto.service"
MIN_INTERVAL_HOURS = 6

_OVERRIDE_DIR = Path.home() / ".config" / "systemd" / "user" / "lofi-auto.timer.d"
_OVERRIDE_FILE = _OVERRIDE_DIR / "schedule.conf"
_ONCAL_RE = re.compile(r"^\*-\*-\* ([\d,]+):00:00$")


def _systemctl(*args: str, unit: str = TIMER) -> tuple[int, str]:
    r = subprocess.run(["systemctl", "--user", *args, unit],
                        capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def _show(unit: str, *props: str) -> dict:
    _, out = _systemctl("show", "-p", ",".join(props), unit=unit)
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def valid_intervals() -> list[int]:
    """Divisors of 24 at or above the floor — the only step sizes that tile a
    24h day evenly (anything else drifts: e.g. every 10h from midnight lands
    at 0, 10, 20, 6, 16, 2... effectively every 2h, not every 10h)."""
    return [h for h in range(MIN_INTERVAL_HOURS, 25) if 24 % h == 0]


VALID_INTERVALS = valid_intervals()


def _oncalendar_expr(start_hour: int, every_hours: int) -> str:
    if every_hours >= 24:
        return f"*-*-* {start_hour:02d}:00:00"
    # Explicit comma-separated hours (not systemd's "HH/step" shorthand):
    # "HH/step" is rejected outright by systemd whenever start+step > 23
    # (e.g. "18/12:00:00" fails to parse), while a discrete list always works.
    hours = sorted((start_hour + k * every_hours) % 24 for k in range(24 // every_hours))
    return f"*-*-* {','.join(f'{h:02d}' for h in hours)}:00:00"


def get_schedule() -> tuple[int, int]:
    """Returns (start_hour, every_hours) — defaults to (0, 24) = daily at midnight.
    start_hour is normalized to the earliest hour in the schedule."""
    if _OVERRIDE_FILE.exists():
        for line in _OVERRIDE_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("OnCalendar=") and line != "OnCalendar=":
                m = _ONCAL_RE.match(line.split("=", 1)[1])
                if m:
                    hours = sorted(int(h) for h in m.group(1).split(","))
                    every = (hours[1] - hours[0]) if len(hours) > 1 else 24
                    return hours[0], every
    return 0, 24


def set_schedule(start_hour: int = 0, every_hours: int = 24) -> None:
    """Change when the daily auto-upload run fires. every_hours has a floor of
    MIN_INTERVAL_HOURS (to avoid hammering the YouTube upload quota / posting
    too frequently) and must evenly divide 24 so runs land on a predictable,
    evenly-spaced schedule."""
    if not (0 <= start_hour <= 23):
        raise ValueError("start_hour must be 0-23")
    if every_hours not in VALID_INTERVALS:
        raise ValueError(f"every_hours must be one of {VALID_INTERVALS} (got {every_hours})")

    expr = _oncalendar_expr(start_hour, every_hours)
    _OVERRIDE_DIR.mkdir(parents=True, exist_ok=True)
    # The blank "OnCalendar=" resets the base unit's list-type directive
    # before adding ours — otherwise the drop-in would add to it, not replace it.
    _OVERRIDE_FILE.write_text(f"[Timer]\nOnCalendar=\nOnCalendar={expr}\n")

    r = subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr).strip() or "systemctl daemon-reload failed")
    # Restart just re-arms the timer against the new schedule; it does not
    # run the service.
    if status()["active"]:
        _systemctl("restart", unit=TIMER)


def status() -> dict:
    """Snapshot of the timer + whether a run is currently in progress."""
    t = _show(TIMER, "LoadState", "ActiveState", "UnitFileState",
              "NextElapseUSecRealtime", "LastTriggerUSec")
    installed = t.get("LoadState") == "loaded"
    s = _show(SERVICE, "ActiveState") if installed else {}

    def _usec_to_iso(v: str | None) -> str | None:
        if not v or v in ("0", "n/a"):
            return None
        try:
            return datetime.fromtimestamp(int(v) / 1_000_000).strftime("%Y-%m-%d %H:%M")
        except (ValueError, OSError):
            return None

    start_hour, every_hours = get_schedule() if installed else (0, 24)
    return {
        "installed": installed,
        "active": t.get("ActiveState") == "active",
        "enabled": t.get("UnitFileState") in ("enabled", "enabled-runtime", "static"),
        "running_now": s.get("ActiveState") in ("active", "activating"),
        "next_run": _usec_to_iso(t.get("NextElapseUSecRealtime")),
        "last_run": _usec_to_iso(t.get("LastTriggerUSec")),
        "start_hour": start_hour,
        "every_hours": every_hours,
    }


def start() -> None:
    rc, out = _systemctl("start")
    if rc != 0:
        raise RuntimeError(out or "systemctl start failed")


def stop() -> None:
    rc, out = _systemctl("stop")
    if rc != 0:
        raise RuntimeError(out or "systemctl stop failed")


def restart() -> None:
    rc, out = _systemctl("restart")
    if rc != 0:
        raise RuntimeError(out or "systemctl restart failed")


def set_enabled(enabled: bool) -> None:
    rc, out = _systemctl("enable" if enabled else "disable")
    if rc != 0:
        raise RuntimeError(out or "systemctl enable/disable failed")


def run_now() -> None:
    """Trigger an immediate one-off run without waiting for the schedule."""
    rc, out = _systemctl("start", unit=SERVICE)
    if rc != 0:
        raise RuntimeError(out or "systemctl start (service) failed")


def resource_status() -> dict:
    """Current memory usage vs. configured limits, plus the last invocation's
    exit status, for lofi-auto.service (the oneshot the timer fires — the
    resource/exit-code properties live on the service unit, not the timer).
    Reuses _show(), the same systemctl-show helper status() is built on.

    MemoryHigh/MemoryMax are systemd's resource-control throttle/hard-kill
    limits (systemd.resource-control(5)); MemoryCurrent is live RSS+cache
    usage. ExecMainStatus/ExecMainCode describe how the last run ended
    (ExecMainCode "exited" + ExecMainStatus 0 = clean success; "killed" means
    a signal, e.g. OOM, terminated it instead).
    """
    d = _show(SERVICE, "MemoryHigh", "MemoryMax", "MemoryCurrent",
              "ExecMainStatus", "ExecMainCode")

    def _mem(v: str | None) -> int | None:
        if not v or v in ("infinity", "[not set]", "n/a"):
            return None
        try:
            return int(v)
        except ValueError:
            return None

    return {
        "memory_high": _mem(d.get("MemoryHigh")),
        "memory_max": _mem(d.get("MemoryMax")),
        "memory_current": _mem(d.get("MemoryCurrent")),
        "exec_main_status": d.get("ExecMainStatus"),
        "exec_main_code": d.get("ExecMainCode") or None,
    }


def logs_cmd(n: int = 200, follow: bool = True) -> list[str]:
    """journalctl argv to show/follow the service's logs (caller decides how to run it)."""
    cmd = ["journalctl", "--user", "-u", SERVICE, "-n", str(n), "--no-pager"]
    if follow:
        cmd.append("-f")
    return cmd
