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


def _history(groups, metric="views"):
    """Upload log + analytics for `groups`: [(hour, value, count), ...], one
    upload per day starting Monday 2026-01-05."""
    import datetime as dt
    uploads, analytics, day, n = [], {}, dt.date(2026, 1, 5), 0
    for hour, value, count in groups:
        for _ in range(count):
            vid = f"v{n}"
            uploads.append({"type": "upload", "video_id": vid,
                            "timestamp": f"{day.isoformat()}T{hour:02d}:00:00+00:00"})
            analytics[vid] = {metric: value}
            day += dt.timedelta(days=1)
            n += 1
    return uploads, analytics


def test_recommends_highest_scoring_hour(tmp_path):
    ups, an = _history([(17, 5000, 12), (9, 50, 12)])
    result = posting_time.recommend(upload_log_path=_write(tmp_path / "u.json", ups),
                                    analytics_log_path=_write(tmp_path / "a.json", an))
    assert result["available"] is True
    assert result["best_hour_utc"] == 17
    assert result["n_samples"] == 24
    hours = {r["hour"]: r for r in result["by_hour"]}
    assert hours[17]["avg_score"] > hours[9]["avg_score"]


def test_too_few_uploads_is_not_a_recommendation(tmp_path):
    # Three uploads used to be enough to name a "best hour".
    ups, an = _history([(17, 5000, 2), (9, 50, 1)])
    result = posting_time.recommend(upload_log_path=_write(tmp_path / "u.json", ups),
                                    analytics_log_path=_write(tmp_path / "a.json", an))
    assert result["available"] is False


def test_single_schedule_has_nothing_to_compare(tmp_path):
    ups, an = _history([(0, 100, 25)])        # the timer always fires at 00:00
    result = posting_time.recommend(upload_log_path=_write(tmp_path / "u.json", ups),
                                    analytics_log_path=_write(tmp_path / "a.json", an))
    # Weekdays vary, so a day comparison exists; the only hour ever tried
    # must not be reported as the "best" one.
    assert result["best_hour_utc"] is None


def test_falls_back_to_watch_minutes_when_views_missing(tmp_path):
    ups, an = _history([(20, 900, 12), (8, 10, 12)], metric="estimatedMinutesWatched")
    result = posting_time.recommend(upload_log_path=_write(tmp_path / "u.json", ups),
                                    analytics_log_path=_write(tmp_path / "a.json", an))
    assert result["available"] is True
    assert result["best_hour_utc"] == 20


def test_ignores_live_and_scheduled_placeholder_entries(tmp_path):
    ups, an = _history([(17, 100, 12), (9, 90, 12)])
    ups = [{"type": "live", "broadcast_id": "b1", "timestamp": "2026-01-05T03:00:00+00:00"},
           {"type": "scheduled", "broadcast_id": "b2", "timestamp": "2026-01-05T04:00:00+00:00"}] + ups
    result = posting_time.recommend(upload_log_path=_write(tmp_path / "u.json", ups),
                                    analytics_log_path=_write(tmp_path / "a.json", an))
    assert result["available"] is True
    assert result["n_samples"] == 24  # the live/scheduled rows never counted


def test_entries_missing_video_id_or_timestamp_are_skipped(tmp_path):
    ups, an = _history([(17, 100, 12), (9, 90, 12)])
    ups += [{"type": "upload", "video_id": None, "timestamp": "2026-01-05T17:00:00+00:00"},
            {"type": "upload", "video_id": "vx", "timestamp": ""}]
    an["vx"] = {"views": 1}
    result = posting_time.recommend(upload_log_path=_write(tmp_path / "u.json", ups),
                                    analytics_log_path=_write(tmp_path / "a.json", an))
    assert result["available"] is True
    assert result["n_samples"] == 24
