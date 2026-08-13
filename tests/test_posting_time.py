"""Unit tests for scripts/posting_time.py's recommend()."""
from __future__ import annotations

import json

from scripts import posting_time


def _write(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f)
    return str(path)


def test_missing_upload_log_is_unavailable(tmp_path):
    result = posting_time.recommend(
        upload_log_path=str(tmp_path / "no_such_upload_log.json"),
        analytics_log_path=str(tmp_path / "no_such_analytics.json"),
    )
    assert result["available"] is False
    assert "upload history" in result["reason"]


def test_empty_upload_log_is_unavailable(tmp_path):
    up = _write(tmp_path / "upload_log.json", [])
    an = _write(tmp_path / "analytics_log.json", {})
    result = posting_time.recommend(upload_log_path=up, analytics_log_path=an)
    assert result["available"] is False


def test_upload_log_without_analytics_is_unavailable(tmp_path):
    up = _write(tmp_path / "upload_log.json", [
        {"type": "upload", "video_id": "v1", "timestamp": "2026-01-05T17:00:00+00:00"},
    ])
    an = _write(tmp_path / "analytics_log.json", {})  # empty -- analytics.py hasn't synced yet
    result = posting_time.recommend(upload_log_path=up, analytics_log_path=an)
    assert result["available"] is False
    assert "analytics" in result["reason"]


def test_below_min_samples_is_unavailable(tmp_path):
    up = _write(tmp_path / "upload_log.json", [
        {"type": "upload", "video_id": "v1", "timestamp": "2026-01-05T17:00:00+00:00"},
        {"type": "upload", "video_id": "v2", "timestamp": "2026-01-06T09:00:00+00:00"},
    ])
    an = _write(tmp_path / "analytics_log.json", {
        "v1": {"views": 100}, "v2": {"views": 50},
    })
    result = posting_time.recommend(upload_log_path=up, analytics_log_path=an)
    assert result["available"] is False
    assert result["n_samples"] == 2


def test_recommends_highest_scoring_hour_and_day(tmp_path):
    # v1/v2 both published at 17:00 UTC on a Monday/Tuesday and performed
    # very well; v3 published at 09:00 UTC and performed poorly -- 17:00
    # should win clearly.
    up = _write(tmp_path / "upload_log.json", [
        {"type": "upload", "video_id": "v1", "timestamp": "2026-01-05T17:00:00+00:00"},  # Monday
        {"type": "upload", "video_id": "v2", "timestamp": "2026-01-06T17:00:00+00:00"},  # Tuesday
        {"type": "upload", "video_id": "v3", "timestamp": "2026-01-07T09:00:00+00:00"},  # Wednesday
    ])
    an = _write(tmp_path / "analytics_log.json", {
        "v1": {"views": 5000},
        "v2": {"views": 4800},
        "v3": {"views": 50},
    })
    result = posting_time.recommend(upload_log_path=up, analytics_log_path=an)
    assert result["available"] is True
    assert result["best_hour_utc"] == 17
    assert result["n_samples"] == 3
    hours = {r["hour"]: r for r in result["by_hour"]}
    assert hours[17]["avg_score"] > hours[9]["avg_score"]


def test_falls_back_to_watch_minutes_when_views_missing(tmp_path):
    up = _write(tmp_path / "upload_log.json", [
        {"type": "upload", "video_id": "v1", "timestamp": "2026-01-05T20:00:00+00:00"},
        {"type": "upload", "video_id": "v2", "timestamp": "2026-01-06T08:00:00+00:00"},
        {"type": "upload", "video_id": "v3", "timestamp": "2026-01-07T20:00:00+00:00"},
    ])
    an = _write(tmp_path / "analytics_log.json", {
        "v1": {"estimatedMinutesWatched": 900},
        "v2": {"estimatedMinutesWatched": 10},
        "v3": {"estimatedMinutesWatched": 850},
    })
    result = posting_time.recommend(upload_log_path=up, analytics_log_path=an)
    assert result["available"] is True
    assert result["best_hour_utc"] == 20


def test_ignores_live_and_scheduled_placeholder_entries(tmp_path):
    up = _write(tmp_path / "upload_log.json", [
        {"type": "live", "broadcast_id": "b1", "timestamp": "2026-01-05T03:00:00+00:00"},
        {"type": "scheduled", "broadcast_id": "b2", "timestamp": "2026-01-05T04:00:00+00:00"},
        {"type": "upload", "video_id": "v1", "timestamp": "2026-01-05T17:00:00+00:00"},
        {"type": "upload", "video_id": "v2", "timestamp": "2026-01-06T17:00:00+00:00"},
        {"type": "upload", "video_id": "v3", "timestamp": "2026-01-07T17:00:00+00:00"},
    ])
    an = _write(tmp_path / "analytics_log.json", {
        "v1": {"views": 100}, "v2": {"views": 120}, "v3": {"views": 110},
    })
    result = posting_time.recommend(upload_log_path=up, analytics_log_path=an)
    assert result["available"] is True
    assert result["n_samples"] == 3  # the live/scheduled rows never counted


def test_entries_missing_video_id_or_timestamp_are_skipped(tmp_path):
    up = _write(tmp_path / "upload_log.json", [
        {"type": "upload", "video_id": None, "timestamp": "2026-01-05T17:00:00+00:00"},
        {"type": "upload", "video_id": "v1", "timestamp": ""},
        {"type": "upload", "video_id": "v2", "timestamp": "2026-01-06T17:00:00+00:00"},
        {"type": "upload", "video_id": "v3", "timestamp": "2026-01-07T17:00:00+00:00"},
        {"type": "upload", "video_id": "v4", "timestamp": "2026-01-08T17:00:00+00:00"},
    ])
    an = _write(tmp_path / "analytics_log.json", {
        "v2": {"views": 100}, "v3": {"views": 100}, "v4": {"views": 100},
    })
    result = posting_time.recommend(upload_log_path=up, analytics_log_path=an)
    assert result["available"] is True
    assert result["n_samples"] == 3
