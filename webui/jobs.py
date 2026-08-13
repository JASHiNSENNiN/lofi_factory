"""
jobs.py — run pipeline/publish commands as subprocesses with live log streaming.

The web UI never re-implements pipeline logic; it shells out to the exact same
``run.py`` / ``publish.py`` commands the CLI uses and streams their stdout into
the browser. A single JobManager tracks the active job plus a short history so
any connected page can attach and watch the live output.

JobQueue (below) is an additive layer on top of that: a persisted, ordered
list of *not-yet-started* jobs that get handed to JobManager.run() one at a
time as each slot frees up. It exists for batching several scheduled
generations ahead of time (see the Calendar page) — direct "New render" /
"Go live" clicks keep using JobManager.run() exactly as before and never
touch the queue.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections import deque
from dataclasses import asdict, dataclass, field
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
    # Exact artifact paths this run produced (video/thumb/thumb_alt/seo), parsed
    # from run.py's `[RESULT] {...}` summary line on success -- see _pump().
    # Empty for jobs that didn't emit one (older command types, failures,
    # publish.py-only runs): callers should fall back to stats.py's
    # nearest-timestamp join in that case, not assume this is always populated.
    artifacts: dict = field(default_factory=dict)
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
                line = raw.decode(errors="replace").rstrip("\n")
                if line.startswith("[RESULT] "):
                    try:
                        job.artifacts = json.loads(line[len("[RESULT] "):])
                    except Exception:
                        pass
                job._emit_line(line)
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


# ─────────────────────────────────────────────────────────────────────────────
# Batch upload queue
# ─────────────────────────────────────────────────────────────────────────────
QUEUE_FILE = os.path.join(config.ASSETS_DIR, "job_queue.json")
_MAX_QUEUE_HISTORY = 100


@dataclass
class QueueItem:
    id: str
    name: str
    args: list[str]
    slot: str = "main"
    # pending -> running -> success | failed | cancelled
    status: str = "pending"
    note: str = ""
    job_id: str | None = None
    returncode: int | None = None
    added_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "QueueItem":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


class JobQueue:
    """
    Persisted FIFO queue of pending jobs, drained one at a time per slot.

    Deliberately kept separate from JobManager's single in-flight job: every
    item here still runs through ``manager.run()`` exactly like a manual
    click, so is_busy()/slot semantics never change. This class only adds
    *what to run next* once a slot frees up, backed by a JSON file
    (assets/job_queue.json) so a queued batch survives a webui restart.

    add()/list_pending()/list_history()/cancel()/remove()/reorder() are pure
    and synchronous (no manager, no event loop) — safe to unit test directly.
    Only drain_forever() touches JobManager/asyncio.
    """

    def __init__(self, path: str | None = None) -> None:
        self._path = path or QUEUE_FILE
        self._pending: list[QueueItem] = []
        self._history: list[QueueItem] = []  # most-recent-first
        self._seq = 0
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._load()

    # ── persistence ─────────────────────────────────────────────────────────
    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path) as f:
                raw = json.load(f)
        except Exception:
            return
        self._pending = [QueueItem.from_dict(d) for d in raw.get("pending", [])]
        self._history = [QueueItem.from_dict(d) for d in raw.get("history", [])]
        self._seq = raw.get("seq", 0)

    def _save(self) -> None:
        payload = {
            "pending": [i.to_dict() for i in self._pending],
            "history": [i.to_dict() for i in self._history[:_MAX_QUEUE_HISTORY]],
            "seq": self._seq,
        }
        tmp = f"{self._path}.tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, self._path)

    # ── queries ──────────────────────────────────────────────────────────────
    def list_pending(self, slot: str | None = None) -> list[QueueItem]:
        items = self._pending
        return [i for i in items if slot is None or i.slot == slot]

    def list_history(self, slot: str | None = None, limit: int = 20) -> list[QueueItem]:
        items = self._history
        if slot is not None:
            items = [i for i in items if i.slot == slot]
        return items[:limit]

    # ── mutation ─────────────────────────────────────────────────────────────
    def add(self, name: str, args: list[str], *, slot: str = "main", note: str = "") -> QueueItem:
        self._seq += 1
        item = QueueItem(id=f"q{self._seq}-{int(time.time())}", name=name,
                          args=list(args), slot=slot, note=note)
        self._pending.append(item)
        self._save()
        return item

    def cancel(self, item_id: str) -> bool:
        """Cancel a still-pending item (moves it to history as 'cancelled').
        No effect on an item that's already running/finished — cancelling an
        in-flight job is JobManager.cancel()'s job, not the queue's."""
        for i, item in enumerate(self._pending):
            if item.id == item_id:
                item.status = "cancelled"
                item.finished_at = time.time()
                self._pending.pop(i)
                self._history.insert(0, item)
                self._save()
                return True
        return False

    def remove(self, item_id: str) -> bool:
        """Hard-delete a pending item (no history trace) or a history entry."""
        before = len(self._pending)
        self._pending = [i for i in self._pending if i.id != item_id]
        if len(self._pending) != before:
            self._save()
            return True
        before = len(self._history)
        self._history = [i for i in self._history if i.id != item_id]
        if len(self._history) != before:
            self._save()
            return True
        return False

    def reorder(self, item_id: str, new_index: int) -> bool:
        """Move a pending item to `new_index` within the pending queue
        (clamped to valid range). Only pending items are reorderable —
        history is immutable."""
        idx = next((k for k, i in enumerate(self._pending) if i.id == item_id), None)
        if idx is None:
            return False
        item = self._pending.pop(idx)
        new_index = max(0, min(new_index, len(self._pending)))
        self._pending.insert(new_index, item)
        self._save()
        return True

    def pop_next(self, slot: str) -> QueueItem | None:
        """Remove and return the oldest pending item for `slot`, or None."""
        for i, item in enumerate(self._pending):
            if item.slot == slot:
                self._pending.pop(i)
                self._save()
                return item
        return None

    def push_history(self, item: QueueItem) -> None:
        self._history.insert(0, item)
        self._save()

    # ── draining (async, needs a JobManager) ────────────────────────────────
    async def _run_item(self, manager: "JobManager", item: QueueItem) -> None:
        item.status = "running"
        item.started_at = time.time()
        try:
            job = await manager.run(item.name, item.args, slot=item.slot)
        except RuntimeError:
            # Slot became busy between the drain loop's check and this call
            # (e.g. a manual "New render" click won the race) — put it back
            # at the front of the queue for the next drain tick instead of
            # dropping it.
            item.status = "pending"
            item.started_at = None
            self._pending.insert(0, item)
            self._save()
            return
        item.job_id = job.id
        while job.running:
            await asyncio.sleep(1)
        item.status = job.status
        item.returncode = job.returncode
        item.finished_at = job.finished_at or time.time()
        self.push_history(item)

    async def drain_forever(self, manager: "JobManager", poll_secs: float = 3.0) -> None:
        """Background loop: whenever a slot is free and the queue has a
        pending item for it, launch it and wait for it to finish before
        considering that slot again. Runs until cancelled."""
        while True:
            for slot, busy in (("main", manager.is_busy()), ("stream", manager.stream_running())):
                if busy:
                    continue
                item = self.pop_next(slot)
                if item:
                    asyncio.create_task(self._run_item(manager, item))
            await asyncio.sleep(poll_secs)


# Module-level singletons shared by all pages.
manager = JobManager()
queue = JobQueue()
_drain_task: asyncio.Task | None = None


def start_queue_drain() -> None:
    """Idempotent: call once at webui startup. Safe to call again (e.g. from
    a test) — a second call is a no-op while the first loop is still alive."""
    global _drain_task
    if _drain_task is None or _drain_task.done():
        _drain_task = asyncio.create_task(queue.drain_forever(manager))
