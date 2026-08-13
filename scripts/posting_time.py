"""
posting_time.py — recommend the best hour-of-day / day-of-week to publish.

Joins upload timestamps (upload_log.json, written by publish.py's cmd_upload)
with per-video performance from assets/analytics_log.json (synced by
scripts/analytics.py, owned by a separate agent) to suggest when future
uploads are likely to do best.

Schema note: analytics_log.json's exact shape is scripts/analytics.py's to
define, and this module doesn't assume more of it than it can verify by
reading the file — at minimum a video_id-keyed dict with a numeric "views"
and/or "estimatedMinutesWatched" field per entry (both already used by
generate_seo.py's pillar weighting and webui's Analytics view, so they're
the stable part of the schema). It does NOT currently carry an explicit
first-24h view-velocity metric, so this module uses total views (falling
back to watch-minutes) as its performance signal — a defensible proxy given
it's the only per-video performance data available on disk — and degrades
gracefully any time the log is missing, empty, or a field isn't present,
rather than assuming a schema this worktree can't verify was finalized
elsewhere.

This module only ever produces a *suggestion*. Nothing here calls
auto_service.set_schedule() — see webui/automation.py's "Recommended
posting time" card, which shows this output and requires an explicit click
before touching the live schedule (this pipeline runs unattended and
controls a real, publicly-visible upload, so a silent auto-change is not
acceptable here).
"""
from __future__ import annotations

import datetime
import json
import os
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(__file__), "..")
UPLOAD_LOG = os.path.join(ROOT, "upload_log.json")
ANALYTICS_LOG = os.path.join(ROOT, "assets", "analytics_log.json")

# Below this many upload<->analytics joins, a "best hour" is just noise --
# refuse to recommend rather than dress up a guess as a finding.
MIN_SAMPLES = 3

_DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _load_json(path: str) -> object | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _parse_ts(ts: str) -> datetime.datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except (ValueError, TypeError):
        return None


def _performance_for(video_id: str, analytics: dict) -> float | None:
    """Best-effort performance score for one video: prefer views, fall back
    to watch-minutes. Returns None if neither field is present/numeric."""
    entry = analytics.get(video_id)
    if not isinstance(entry, dict):
        return None
    for key in ("views", "estimatedMinutesWatched"):
        v = entry.get(key)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _empty_result(reason: str, n_samples: int = 0) -> dict:
    return {
        "available": False,
        "reason": reason,
        "best_hour_utc": None,
        "best_day": None,
        "by_hour": [],
        "by_day": [],
        "n_samples": n_samples,
    }


def recommend(upload_log_path: str | None = None,
               analytics_log_path: str | None = None) -> dict:
    """
    Returns:
      {"available": bool, "reason": str | None,
       "best_hour_utc": int | None, "best_day": str | None,
       "by_hour": [{"hour": int, "avg_score": float, "n": int}, ...] (best first),
       "by_day":  [{"day": str, "avg_score": float, "n": int}, ...] (best first),
       "n_samples": int}

    "available" is False (with a human-readable "reason") whenever there
    isn't enough joined upload+analytics data to say anything meaningful --
    callers must show that reason rather than a fabricated recommendation.
    """
    raw_uploads = _load_json(upload_log_path or UPLOAD_LOG)
    if not raw_uploads:
        return _empty_result("no upload history yet (upload_log.json is missing or empty)")

    entries = raw_uploads if isinstance(raw_uploads, list) else raw_uploads.get("entries", [])
    analytics = _load_json(analytics_log_path or ANALYTICS_LOG)
    if not isinstance(analytics, dict) or not analytics:
        return _empty_result(
            "no analytics data yet -- run `python scripts/analytics.py` once uploads "
            "have 7+ days of history, then try again")

    hour_scores: dict[int, list[float]] = defaultdict(list)
    day_scores: dict[str, list[float]] = defaultdict(list)
    n_joined = 0

    for e in entries:
        if not isinstance(e, dict):
            continue
        # Only regular (non-live, non-scheduled-placeholder) uploads carry a
        # stable video_id + publish timestamp pair worth joining.
        if e.get("type") not in (None, "upload"):
            continue
        vid = e.get("video_id")
        ts = _parse_ts(e.get("timestamp", ""))
        if not vid or not ts:
            continue
        perf = _performance_for(vid, analytics)
        if perf is None:
            continue
        n_joined += 1
        hour_scores[ts.hour].append(perf)
        day_scores[_DAY_ORDER[ts.weekday()]].append(perf)

    if n_joined < MIN_SAMPLES:
        return _empty_result(
            f"only {n_joined} upload(s) have joined analytics data yet (need "
            f"{MIN_SAMPLES}+) -- check back after more videos have 7+ days of history",
            n_samples=n_joined,
        )

    by_hour = sorted(
        ({"hour": h, "avg_score": sum(v) / len(v), "n": len(v)} for h, v in hour_scores.items()),
        key=lambda r: -r["avg_score"],
    )
    by_day = sorted(
        ({"day": d, "avg_score": sum(v) / len(v), "n": len(v)} for d, v in day_scores.items()),
        key=lambda r: -r["avg_score"],
    )

    return {
        "available": True,
        "reason": None,
        "best_hour_utc": by_hour[0]["hour"] if by_hour else None,
        "best_day": by_day[0]["day"] if by_day else None,
        "by_hour": by_hour,
        "by_day": by_day,
        "n_samples": n_joined,
    }


if __name__ == "__main__":
    result = recommend()
    if not result["available"]:
        print(f"[posting-time] {result['reason']}")
    else:
        print(f"[posting-time] Best hour (UTC): {result['best_hour_utc']:02d}:00  "
              f"·  Best day: {result['best_day']}  ·  n={result['n_samples']}")
        print("\n  By hour (UTC):")
        for row in result["by_hour"]:
            print(f"    {row['hour']:02d}:00  avg={row['avg_score']:.1f}  n={row['n']}")
        print("\n  By day:")
        for row in result["by_day"]:
            print(f"    {row['day']:10s}  avg={row['avg_score']:.1f}  n={row['n']}")
