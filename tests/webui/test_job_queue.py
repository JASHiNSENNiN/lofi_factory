"""Unit tests for webui/jobs.py's JobQueue (batch upload queue).

All pure/synchronous operations (add/list/cancel/remove/reorder/persistence)
are exercised directly. The async drain loop is exercised against a small
fake JobManager so no real subprocess/event-loop-heavy JobManager is needed.
"""
from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import patch

import pytest

from webui.jobs import Job, JobQueue, QueueItem


@pytest.fixture
def queue(tmp_path) -> JobQueue:
    return JobQueue(path=str(tmp_path / "job_queue.json"))


def test_add_appends_to_pending(queue):
    item = queue.add("render", ["run.py", "--skip-upload"], slot="main", note="batch 1")
    assert item.status == "pending"
    assert item.slot == "main"
    assert item.note == "batch 1"
    pending = queue.list_pending()
    assert len(pending) == 1
    assert pending[0].id == item.id


def test_add_preserves_fifo_order(queue):
    a = queue.add("render", ["a"])
    b = queue.add("render", ["b"])
    c = queue.add("render", ["c"])
    assert [i.id for i in queue.list_pending()] == [a.id, b.id, c.id]


def test_list_pending_filters_by_slot(queue):
    queue.add("render", ["a"], slot="main")
    queue.add("live", ["b"], slot="stream")
    assert [i.slot for i in queue.list_pending()] == ["main", "stream"]
    assert [i.slot for i in queue.list_pending(slot="main")] == ["main"]
    assert [i.slot for i in queue.list_pending(slot="stream")] == ["stream"]


def test_reorder_moves_item_within_pending(queue):
    a = queue.add("render", ["a"])
    b = queue.add("render", ["b"])
    c = queue.add("render", ["c"])
    assert queue.reorder(c.id, 0) is True
    assert [i.id for i in queue.list_pending()] == [c.id, a.id, b.id]


def test_reorder_clamps_out_of_range_index(queue):
    a = queue.add("render", ["a"])
    b = queue.add("render", ["b"])
    assert queue.reorder(a.id, 999) is True
    assert [i.id for i in queue.list_pending()] == [b.id, a.id]


def test_reorder_unknown_id_returns_false(queue):
    queue.add("render", ["a"])
    assert queue.reorder("nope", 0) is False


def test_cancel_moves_pending_item_to_history(queue):
    item = queue.add("render", ["a"])
    assert queue.cancel(item.id) is True
    assert queue.list_pending() == []
    hist = queue.list_history()
    assert len(hist) == 1
    assert hist[0].id == item.id
    assert hist[0].status == "cancelled"
    assert hist[0].finished_at is not None


def test_cancel_unknown_id_returns_false(queue):
    assert queue.cancel("nope") is False


def test_remove_hard_deletes_pending_item(queue):
    item = queue.add("render", ["a"])
    assert queue.remove(item.id) is True
    assert queue.list_pending() == []
    assert queue.list_history() == []  # no history trace, unlike cancel()


def test_remove_can_delete_from_history(queue):
    item = queue.add("render", ["a"])
    queue.cancel(item.id)
    assert queue.remove(item.id) is True
    assert queue.list_history() == []


def test_remove_unknown_id_returns_false(queue):
    assert queue.remove("nope") is False


def test_pop_next_returns_oldest_matching_slot(queue):
    a = queue.add("render", ["a"], slot="main")
    queue.add("live", ["b"], slot="stream")
    popped = queue.pop_next("main")
    assert popped.id == a.id
    assert queue.list_pending(slot="main") == []
    assert queue.pop_next("main") is None


def test_persistence_round_trips_through_disk(tmp_path):
    path = str(tmp_path / "job_queue.json")
    q1 = JobQueue(path=path)
    q1.add("render", ["run.py", "--skip-upload"], slot="main", note="batch")
    q1.cancel(q1.list_pending()[0].id)
    q1.add("render", ["run.py", "--duration", "2 hours"], slot="main")

    assert os.path.exists(path)
    with open(path) as f:
        raw = json.load(f)
    assert len(raw["pending"]) == 1
    assert len(raw["history"]) == 1

    q2 = JobQueue(path=path)
    assert len(q2.list_pending()) == 1
    assert len(q2.list_history()) == 1
    assert q2.list_pending()[0].args == ["run.py", "--duration", "2 hours"]


def test_missing_queue_file_starts_empty(tmp_path):
    q = JobQueue(path=str(tmp_path / "nonexistent" / "job_queue.json"))
    assert q.list_pending() == []
    assert q.list_history() == []


def test_corrupt_queue_file_degrades_gracefully(tmp_path):
    path = tmp_path / "job_queue.json"
    path.write_text("{not valid json")
    q = JobQueue(path=str(path))
    assert q.list_pending() == []
    assert q.list_history() == []


# ── QueueItem (de)serialization ─────────────────────────────────────────────

def test_queue_item_round_trips_dict():
    item = QueueItem(id="q1", name="render", args=["a", "b"], slot="main")
    d = item.to_dict()
    restored = QueueItem.from_dict(d)
    assert restored == item


def test_queue_item_from_dict_ignores_unknown_keys():
    d = {"id": "q1", "name": "render", "args": [], "slot": "main",
         "status": "pending", "some_future_field": "ignored"}
    item = QueueItem.from_dict(d)
    assert item.id == "q1"


# ── draining against a fake JobManager ──────────────────────────────────────

class _FakeManager:
    """Mimics just enough of JobManager for drain_forever(): is_busy(),
    stream_running(), and an async run() that completes a fake Job almost
    immediately -- no real subprocess involved."""

    def __init__(self):
        self._busy = False
        self.launched: list[tuple[str, list[str], str]] = []

    def is_busy(self) -> bool:
        return self._busy

    def stream_running(self) -> bool:
        return False

    async def run(self, name, args, *, slot="main"):
        if self._busy:
            raise RuntimeError("Another job is already running.")
        self.launched.append((name, args, slot))
        self._busy = True
        job = Job(id=f"{name}-1", name=name, cmd=args, status="running")

        async def _finish():
            await asyncio.sleep(0.01)
            job.status = "success"
            job.returncode = 0
            job.finished_at = 1.0
            self._busy = False

        asyncio.create_task(_finish())
        return job


def test_drain_forever_launches_pending_item_and_records_history(queue):
    async def run():
        mgr = _FakeManager()
        queue.add("render", ["run.py", "--skip-upload"], slot="main")

        drain_task = asyncio.create_task(queue.drain_forever(mgr, poll_secs=0.01))
        try:
            for _ in range(200):
                if queue.list_history():
                    break
                await asyncio.sleep(0.01)
        finally:
            drain_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await drain_task
        return mgr

    mgr = asyncio.run(run())
    assert mgr.launched == [("render", ["run.py", "--skip-upload"], "main")]
    hist = queue.list_history()
    assert len(hist) == 1
    assert hist[0].status == "success"
    assert queue.list_pending() == []


def test_drain_forever_respects_busy_slot(queue):
    async def run():
        mgr = _FakeManager()
        mgr._busy = True  # slot already occupied by a manual/direct run
        queue.add("render", ["run.py"], slot="main")

        drain_task = asyncio.create_task(queue.drain_forever(mgr, poll_secs=0.01))
        await asyncio.sleep(0.05)
        drain_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await drain_task
        return mgr

    mgr = asyncio.run(run())
    # Never launched -- still sitting in pending, untouched.
    assert mgr.launched == []
    assert len(queue.list_pending()) == 1


# ── stream-slot queue add (queue_dialog's new slot selector) ────────────────

def test_add_stream_slot_queues_live_args(queue):
    item = queue.add("live", ["publish.py", "live", "--quality", "720p15",
                               "--privacy", "public"], slot="stream", note="go live at 8pm")
    assert item.slot == "stream"
    assert item.args == ["publish.py", "live", "--quality", "720p15", "--privacy", "public"]
    assert [i.slot for i in queue.list_pending()] == ["stream"]


# ── retry (re-queue a failed history item) ──────────────────────────────────

def test_retry_requeues_failed_item_with_original_args(queue):
    item = queue.add("render", ["run.py", "--theme", "vaporwave"], slot="main", note="batch A")
    popped = queue.pop_next("main")
    popped.status = "failed"
    popped.returncode = 1
    queue.push_history(popped)
    assert queue.list_pending() == []

    retried = queue.retry(popped.id)
    assert retried is not None
    assert retried.id != popped.id  # a new queue item, not a mutation of the old one
    assert retried.name == "render"
    assert retried.args == ["run.py", "--theme", "vaporwave"]
    assert retried.slot == "main"
    assert retried.note == "batch A"
    assert retried.status == "pending"
    assert [i.id for i in queue.list_pending()] == [retried.id]


def test_retry_unknown_id_returns_none(queue):
    assert queue.retry("nope") is None


def test_retry_refuses_non_failed_history_item(queue):
    item = queue.add("render", ["a"])
    queue.cancel(item.id)  # history entry, but status == "cancelled", not "failed"
    assert queue.retry(item.id) is None


# ── queue-drain failure alerting ─────────────────────────────────────────────
class _FakeFailingManager:
    """Like _FakeManager, but the launched job always finishes 'failed' --
    exercises JobQueue._run_item's alerts.send_queue_failure() call."""

    def __init__(self):
        self._busy = False

    def is_busy(self) -> bool:
        return self._busy

    def stream_running(self) -> bool:
        return False

    async def run(self, name, args, *, slot="main"):
        self._busy = True
        job = Job(id=f"{name}-1", name=name, cmd=args, status="running")

        async def _finish():
            await asyncio.sleep(0.01)
            job.status = "failed"
            job.returncode = 1
            job.finished_at = 1.0
            self._busy = False

        asyncio.create_task(_finish())
        return job


def test_drain_forever_alerts_on_queue_item_failure(queue, monkeypatch):
    monkeypatch.setenv("LOFI_STREAM_ALERT_WEBHOOK", "json://example.com/hook")

    async def run():
        mgr = _FakeFailingManager()
        queue.add("render", ["run.py", "--skip-upload"], slot="main")

        with patch("apprise.Apprise.add", return_value=True), \
             patch("apprise.Apprise.notify", return_value=True) as mock_notify:
            drain_task = asyncio.create_task(queue.drain_forever(mgr, poll_secs=0.01))
            try:
                # Wait for the alert itself (not just the history write, which
                # happens synchronously a moment earlier in _run_item) -- the
                # notify call is offloaded to a thread via asyncio.to_thread,
                # so it lands on the mock slightly after list_history() would
                # already show the finished item.
                for _ in range(300):
                    if mock_notify.called:
                        break
                    await asyncio.sleep(0.01)
            finally:
                drain_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await drain_task
            return mock_notify

    mock_notify = asyncio.run(run())
    mock_notify.assert_called_once()
    _, kwargs = mock_notify.call_args
    assert "render" in kwargs["title"]
