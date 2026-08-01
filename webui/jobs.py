"""
jobs.py — run pipeline/publish commands as subprocesses with live log streaming.

The web UI never re-implements pipeline logic; it shells out to the exact same
``run.py`` / ``publish.py`` commands the CLI uses and streams their stdout into
the browser. A single JobManager tracks the active job plus a short history so
any connected page can attach and watch the live output.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from . import config

# How many log lines to retain per job (ring buffer for late-joining pages).
_MAX_LINES = 4000


@dataclass
class Job:
    id: str
    name: str
    cmd: list[str]
    status: str = "running"          # running | success | failed | cancelled
    returncode: int | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    lines: deque[str] = field(default_factory=lambda: deque(maxlen=_MAX_LINES))
    _proc: asyncio.subprocess.Process | None = None
    # UI callbacks: (line) -> None and () -> None for status changes.
    _line_subs: set[Callable[[str], None]] = field(default_factory=set)
    _status_subs: set[Callable[[], None]] = field(default_factory=set)

    @property
    def running(self) -> bool:
        return self.status == "running"

    @property
    def duration(self) -> float:
        return (self.finished_at or time.time()) - self.started_at

    def subscribe(self, on_line: Callable[[str], None],
                  on_status: Callable[[], None]) -> Callable[[], None]:
        """Attach UI callbacks; returns an unsubscribe function."""
        self._line_subs.add(on_line)
        self._status_subs.add(on_status)

        def _off() -> None:
            self._line_subs.discard(on_line)
            self._status_subs.discard(on_status)

        return _off

    def _emit_line(self, line: str) -> None:
        self.lines.append(line)
        for cb in list(self._line_subs):
            try:
                cb(line)
            except Exception:
                pass

    def _emit_status(self) -> None:
        for cb in list(self._status_subs):
            try:
                cb()
            except Exception:
                pass


class JobManager:
    """Owns the single active job and recent history. One heavy job at a time."""

    def __init__(self) -> None:
        self.current: Job | None = None
        self.history: list[Job] = []
        # The live-stream job is tracked separately so a generation run and an
        # active broadcast can coexist.
        self.stream: Job | None = None

    # ── queries ──────────────────────────────────────────────────────────────
    def is_busy(self) -> bool:
        return self.current is not None and self.current.running

    def stream_running(self) -> bool:
        return self.stream is not None and self.stream.running

    # ── execution ────────────────────────────────────────────────────────────
    async def run(self, name: str, args: list[str], *, slot: str = "main") -> Job:
        """
        Launch ``python <args...>`` from the repo root. ``slot`` selects which
        tracker holds the job: "main" (generation/upload/etc.) or "stream".
        Raises RuntimeError if that slot is already busy.
        """
        if slot == "stream":
            if self.stream_running():
                raise RuntimeError("A live stream is already running.")
        else:
            if self.is_busy():
                raise RuntimeError("Another job is already running.")

        cmd = [config.PYTHON, *args]
        job = Job(id=f"{name}-{int(time.time())}", name=name, cmd=cmd)
        if slot == "stream":
            self.stream = job
        else:
            self.current = job
        self.history.insert(0, job)
        self.history = self.history[:20]

        asyncio.create_task(self._pump(job))
        return job

    async def _pump(self, job: Job) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                *job.cmd,
                cwd=config.ROOT,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            job._proc = proc
            assert proc.stdout is not None
            async for raw in proc.stdout:
                job._emit_line(raw.decode(errors="replace").rstrip("\n"))
            await proc.wait()
            job.returncode = proc.returncode
            job.status = "success" if proc.returncode == 0 else "failed"
        except Exception as ex:  # noqa: BLE001 — surface any launch failure to UI
            job._emit_line(f"[webui] job crashed: {ex!r}")
            job.status = "failed"
        finally:
            job.finished_at = time.time()
            job._emit_status()

    async def cancel(self, slot: str = "main") -> None:
        job = self.stream if slot == "stream" else self.current
        if job and job.running and job._proc:
            job._proc.terminate()
            try:
                await asyncio.wait_for(job._proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                job._proc.kill()
            job.status = "cancelled"
            job.finished_at = time.time()
            job._emit_status()


# Module-level singleton shared by all pages.
manager = JobManager()
