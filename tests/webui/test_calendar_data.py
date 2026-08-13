"""Unit tests for webui/data.py's calendar_entries() (Content Calendar page data)."""
from __future__ import annotations

from datetime import datetime, timezone

from webui import data
from webui.jobs import QueueItem


def test_empty_inputs_yield_empty_calendar():
    result = data.calendar_entries(upload_entries=[], queue_pending=[])
    assert result == {"timeline": [], "queue_pending": []}


def test_published_upload_becomes_timeline_entry():
    entries = [{
        "type": "upload", "video_id": "v1", "url": "https://youtube.com/watch?v=v1",
        "title": "cozy rain lofi", "timestamp": "2026-01-05T17:00:00+00:00",
    }]
    result = data.calendar_entries(upload_entries=entries, queue_pending=[])
    assert len(result["timeline"]) == 1
    row = result["timeline"][0]
    assert row["kind"] == "published"
    assert row["status"] == "public"
    assert row["title"] == "cozy rain lofi"
    assert row["when"] == datetime(2026, 1, 5, 17, 0, tzinfo=timezone.utc)


def test_scheduled_upload_uses_scheduled_at_not_upload_timestamp():
    entries = [{
        "type": "upload", "video_id": "v2", "title": "midnight study",
        "timestamp": "2026-01-01T10:00:00+00:00",
        "scheduled_at": "2026-01-10T20:00:00.000Z",
    }]
    result = data.calendar_entries(upload_entries=entries, queue_pending=[])
    row = result["timeline"][0]
    assert row["kind"] == "scheduled"
    assert row["when"] == datetime(2026, 1, 10, 20, 0, tzinfo=timezone.utc)


def test_live_and_scheduled_live_entries_classified_separately():
    entries = [
        {"type": "live", "title": "24/7 stream", "timestamp": "2026-01-02T00:00:00+00:00"},
        {"type": "scheduled", "title": "future broadcast",
         "scheduled_at": "2026-01-03T00:00:00.000Z", "timestamp": "2026-01-01T00:00:00+00:00"},
    ]
    result = data.calendar_entries(upload_entries=entries, queue_pending=[])
    kinds = {row["title"]: row["kind"] for row in result["timeline"]}
    assert kinds["24/7 stream"] == "live"
    assert kinds["future broadcast"] == "scheduled_live"


def test_timeline_sorted_newest_first():
    entries = [
        {"type": "upload", "video_id": "old", "title": "old", "timestamp": "2026-01-01T00:00:00+00:00"},
        {"type": "upload", "video_id": "new", "title": "new", "timestamp": "2026-01-10T00:00:00+00:00"},
        {"type": "upload", "video_id": "mid", "title": "mid", "timestamp": "2026-01-05T00:00:00+00:00"},
    ]
    result = data.calendar_entries(upload_entries=entries, queue_pending=[])
    assert [row["title"] for row in result["timeline"]] == ["new", "mid", "old"]


def test_scheduled_future_upload_sorts_above_recent_past_upload():
    entries = [
        {"type": "upload", "video_id": "v1", "title": "already public",
         "timestamp": "2026-01-05T00:00:00+00:00"},
        {"type": "upload", "video_id": "v2", "title": "goes live later",
         "timestamp": "2026-01-01T00:00:00+00:00", "scheduled_at": "2026-06-01T00:00:00.000Z"},
    ]
    result = data.calendar_entries(upload_entries=entries, queue_pending=[])
    assert [row["title"] for row in result["timeline"]] == ["goes live later", "already public"]


def test_malformed_timestamp_sorts_last_not_first():
    entries = [
        {"type": "upload", "video_id": "v1", "title": "has timestamp",
         "timestamp": "2026-01-05T00:00:00+00:00"},
        {"type": "upload", "video_id": "v2", "title": "bad timestamp", "timestamp": "not-a-date"},
    ]
    result = data.calendar_entries(upload_entries=entries, queue_pending=[])
    assert [row["title"] for row in result["timeline"]] == ["has timestamp", "bad timestamp"]
    assert result["timeline"][1]["when"] is None


def test_non_dict_entries_are_skipped():
    entries = [None, "garbage", {"type": "upload", "video_id": "v1", "title": "ok",
                                  "timestamp": "2026-01-05T00:00:00+00:00"}]
    result = data.calendar_entries(upload_entries=entries, queue_pending=[])
    assert len(result["timeline"]) == 1


def test_queue_pending_items_pass_through_in_order():
    items = [
        QueueItem(id="q1", name="render", args=["run.py"], slot="main", note="batch A"),
        QueueItem(id="q2", name="render", args=["run.py", "--theme", "vaporwave"],
                  slot="main", note="batch B"),
    ]
    result = data.calendar_entries(upload_entries=[], queue_pending=items)
    assert [p["id"] for p in result["queue_pending"]] == ["q1", "q2"]
    assert result["queue_pending"][0]["note"] == "batch A"
    assert result["queue_pending"][1]["args"] == ["run.py", "--theme", "vaporwave"]


def test_calendar_entries_reads_live_state_when_args_omitted(monkeypatch, tmp_path):
    # No explicit args -> pulls from upload_history() (upload_log.json) and
    # jobs.queue.list_pending() -- verify it doesn't blow up and returns the
    # expected shape even with a real (temp, isolated) empty upload log.
    from webui import config
    monkeypatch.setattr(config, "UPLOAD_LOG", str(tmp_path / "upload_log.json"))
    result = data.calendar_entries()
    assert "timeline" in result and "queue_pending" in result
