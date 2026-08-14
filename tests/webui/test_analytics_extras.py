"""
Unit tests for the pure data-assembly helpers behind view_analytics()'s new
CSV export and multi-video comparison panel (webui/app.py), and the
playlist-level aggregation used by its new "Playlist performance" section
(scripts/analytics.py's playlist_stats(), which reuses
scripts/playlist_curation.py's pillar -> playlist-ID mapping).
"""
from __future__ import annotations

from scripts import analytics as analytics_mod
from webui.app import _comparison_rows, _rows_to_csv


# ── CSV export ────────────────────────────────────────────────────────────────
def test_rows_to_csv_header_and_basic_row():
    rows = [{
        "video_id": "v1", "title": "Cozy Rain Study", "pillar": "temporal",
        "ctr": 0.055, "views": 1234, "watch_min": 12, "likes": 10, "comments": 2,
    }]

    csv_text = _rows_to_csv(rows)
    lines = csv_text.strip().splitlines()

    assert lines[0] == "video_id,title,pillar,ctr_pct,views,watch_min,likes,comments"
    assert lines[1] == "v1,Cozy Rain Study,temporal,5.5,1234,12,10,2"


def test_rows_to_csv_handles_missing_likes_and_comments():
    rows = [{
        "video_id": "v2", "title": "Night Drive", "pillar": "aesthetic",
        "ctr": 0, "views": 0, "watch_min": 0, "likes": None, "comments": None,
    }]

    lines = _rows_to_csv(rows).strip().splitlines()

    assert lines[1] == "v2,Night Drive,aesthetic,0,0,0,,"


def test_rows_to_csv_multiple_rows_and_comma_in_title_is_quoted():
    rows = [
        {"video_id": "v1", "title": "Rain, Thunder & Lofi", "pillar": "temporal",
         "ctr": 0.02, "views": 10, "watch_min": 1, "likes": 1, "comments": 0},
        {"video_id": "v2", "title": "Plain Title", "pillar": "activity",
         "ctr": 0.03, "views": 20, "watch_min": 2, "likes": 2, "comments": 1},
    ]

    lines = _rows_to_csv(rows).strip().splitlines()

    assert len(lines) == 3  # header + 2 rows
    assert lines[1] == 'v1,"Rain, Thunder & Lofi",temporal,2.0,10,1,1,0'
    assert lines[2] == "v2,Plain Title,activity,3.0,20,2,2,1"


def test_rows_to_csv_empty_rows_still_has_header():
    assert _rows_to_csv([]).strip() == "video_id,title,pillar,ctr_pct,views,watch_min,likes,comments"


# ── Multi-video comparison ───────────────────────────────────────────────────
def test_comparison_rows_filters_and_preserves_selection_order():
    rows = [{"video_id": "a", "x": 1}, {"video_id": "b", "x": 2}, {"video_id": "c", "x": 3}]

    result = _comparison_rows(rows, ["c", "a"])

    assert [r["video_id"] for r in result] == ["c", "a"]


def test_comparison_rows_skips_unknown_ids():
    rows = [{"video_id": "a", "x": 1}]

    result = _comparison_rows(rows, ["a", "ghost"])

    assert [r["video_id"] for r in result] == ["a"]


def test_comparison_rows_empty_selection_returns_empty():
    rows = [{"video_id": "a", "x": 1}]
    assert _comparison_rows(rows, []) == []


def test_comparison_rows_does_not_mutate_input_rows():
    rows = [{"video_id": "a", "x": 1}]
    _comparison_rows(rows, ["a"])
    assert rows == [{"video_id": "a", "x": 1}]


# ── Playlist-level aggregation (scripts/analytics.py: playlist_stats) ────────
def _entry(pillar, ctr, watched, views):
    return {"pillar": pillar, "history": [{
        "videoThumbnailImpressionsClickRate": ctr,
        "estimatedMinutesWatched": watched,
        "views": views,
    }]}


def test_playlist_stats_groups_by_resolved_playlist_id():
    analytics = {
        "v1": _entry("temporal", 0.05, 100, 300),
        "v2": _entry("temporal", 0.03, 50, 100),
        "v3": _entry("aesthetic", 0.10, 200, 500),
    }
    env = {"YT_PLAYLIST_TEMPORAL": "PL_TEMPORAL_ID"}

    result = analytics_mod.playlist_stats(analytics, env)
    by_playlist = {r["playlist_id"]: r for r in result}

    assert by_playlist["PL_TEMPORAL_ID"]["n"] == 2
    assert by_playlist["PL_TEMPORAL_ID"]["pillars"] == ["temporal"]
    # aesthetic has no matching env var and no legacy fallback set -> unassigned
    assert None in by_playlist
    assert by_playlist[None]["n"] == 1
    assert by_playlist[None]["pillars"] == ["aesthetic"]


def test_playlist_stats_legacy_duration_fallback_still_groups_videos():
    # No pillar-specific env var set at all -- everything should fall back to
    # the legacy YT_PLAYLIST_STUDY var (short/default duration bucket) rather
    # than silently dropping videos from the aggregation.
    analytics = {
        "v1": _entry("temporal", 0.05, 100, 300),
        "v2": _entry("cross_genre", 0.04, 80, 200),
    }
    env = {"YT_PLAYLIST_STUDY": "PL_STUDY_ID"}

    result = analytics_mod.playlist_stats(analytics, env)

    assert len(result) == 1
    assert result[0]["playlist_id"] == "PL_STUDY_ID"
    assert result[0]["n"] == 2
    assert sorted(result[0]["pillars"]) == ["cross_genre", "temporal"]


def test_playlist_stats_sorted_by_avg_views_desc():
    analytics = {
        "v1": _entry("temporal", 0.05, 10, 50),
        "v2": _entry("activity", 0.05, 10, 500),
    }
    env = {"YT_PLAYLIST_TEMPORAL": "P_LOW", "YT_PLAYLIST_ACTIVITY": "P_HIGH"}

    result = analytics_mod.playlist_stats(analytics, env)

    assert [r["playlist_id"] for r in result] == ["P_HIGH", "P_LOW"]


def test_playlist_stats_empty_analytics_returns_empty_list():
    assert analytics_mod.playlist_stats({}) == []


def test_playlist_stats_skips_entries_without_ctr_data():
    analytics = {
        "v1": {"pillar": "temporal", "history": []},  # no snapshots yet
        "v2": _entry("temporal", 0.05, 10, 50),
    }
    result = analytics_mod.playlist_stats(analytics, {})
    assert sum(r["n"] for r in result) == 1
