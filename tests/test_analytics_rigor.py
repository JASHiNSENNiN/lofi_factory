"""
Tests for Stage 1 "Analytics rigor": longitudinal storage/migration, the
composite engagement score, the two-proportion z-test, CUSUM change-point
detection, forecasting, and the bandit-backed pillar/duration/title weight
functions in scripts/analytics.py.
"""
import datetime
import json

import pytest

import scripts.analytics as analytics_mod
from scripts.analytics import (
    composite_engagement_score,
    cusum_change_points,
    detect_viral_moment,
    forecast_views,
    latest_metrics,
    load_analytics,
    load_analytics_history,
    pillar_bandit_posteriors,
    pillar_weights,
    two_proportion_ztest,
)


# ── composite_engagement_score ──────────────────────────────────────────────
def test_composite_score_none_when_no_data():
    assert composite_engagement_score({}) is None
    assert composite_engagement_score({"views": 100}) is None


def test_composite_score_full_weighted_average():
    entry = {
        "averageViewDuration": 900,
        "duration_secs": 3600,
        "videoThumbnailImpressionsClickRate": 0.05,
        "likes": 50,
        "comments": 10,
        "views": 1000,
    }
    # watch_ratio = 900 / min(3600, 1800) = 0.5 (w=.40), ctr=0.05 (w=.35),
    # like_rate=0.05 (w=.15), comment_rate=0.01 (w=.10)
    expected = 0.40 * 0.5 + 0.35 * 0.05 + 0.15 * 0.05 + 0.10 * 0.01
    assert composite_engagement_score(entry) == pytest.approx(expected)


def test_composite_score_renormalizes_when_components_missing():
    # Only ctr + like_rate available -- weights .35 and .15 renormalized to sum to 1.
    entry = {"videoThumbnailImpressionsClickRate": 0.04, "likes": 20, "views": 1000}
    expected = (0.35 * 0.04 + 0.15 * 0.02) / 0.50
    assert composite_engagement_score(entry) == pytest.approx(expected)


def test_composite_score_clamps_watch_ratio_over_100_percent():
    entry = {"averageViewDuration": 7200, "duration_secs": 3600}  # re-watches / bad data
    assert composite_engagement_score(entry) == pytest.approx(1.0)


def test_composite_score_ctr_only_equals_raw_ctr():
    entry = {"videoThumbnailImpressionsClickRate": 0.07}
    assert composite_engagement_score(entry) == pytest.approx(0.07)


def test_composite_score_reads_from_longitudinal_history_format():
    entry = {
        "duration_secs": 3600,
        "history": [
            {"date": "2026-01-01", "videoThumbnailImpressionsClickRate": 0.01},
            {"date": "2026-01-08", "videoThumbnailImpressionsClickRate": 0.05,
             "averageViewDuration": 900},
        ],
    }
    # No upload_date, so the latest snapshot is used (ctr=0.05, avd=900) --
    # only two of the four components are available here (no likes/comments),
    # so the .40/.35 weights get renormalized to sum to 1 (divide by 0.75).
    expected = (0.40 * 0.5 + 0.35 * 0.05) / 0.75
    assert composite_engagement_score(entry) == pytest.approx(expected)


# ── binarize_above_median ────────────────────────────────────────────────────


# ── two_proportion_ztest (checked against statsmodels' reference implementation) ──
def test_ztest_matches_statsmodels_reference():
    statsmodels = pytest.importorskip("statsmodels.stats.proportion")
    z_ref, p_ref = statsmodels.proportions_ztest([50, 100], [1000, 1000])
    z, p = two_proportion_ztest(50, 1000, 100, 1000)
    assert z == pytest.approx(z_ref, rel=1e-9)
    assert p == pytest.approx(p_ref, rel=1e-9)


def test_ztest_identical_proportions_not_significant():
    z, p = two_proportion_ztest(50, 1000, 50, 1000)
    assert z == pytest.approx(0.0, abs=1e-9)
    assert p == pytest.approx(1.0, abs=1e-9)


def test_ztest_zero_trials_returns_not_significant():
    assert two_proportion_ztest(0, 0, 5, 100) == (0.0, 1.0)
    assert two_proportion_ztest(5, 100, 0, 0) == (0.0, 1.0)


def test_ztest_large_gap_is_significant():
    # 1% vs 5% CTR at n=5000 each -- a huge, obviously-real gap.
    z, p = two_proportion_ztest(50, 5000, 250, 5000)
    assert p < 0.001
    assert z < 0


def test_ztest_small_sample_gap_not_significant():
    # Same ratio gap (1% vs 5%) but tiny n -- shouldn't be significant.
    z, p = two_proportion_ztest(1, 100, 5, 100)
    assert p > 0.05


# ── CUSUM change-point detection ────────────────────────────────────────────
def test_cusum_too_short_returns_empty():
    assert cusum_change_points([]) == []
    assert cusum_change_points([1.0]) == []


def test_cusum_flat_series_no_variance_returns_empty():
    assert cusum_change_points([5.0] * 20) == []


def test_cusum_deterministic_known_change_point():
    # Explicit threshold/drift for an exact, hand-computed trigger index.
    # mean0 starts at 0; diff=5 each step once we hit the plateau.
    # s_pos accumulates (5-drift)=5 per step (drift=0), crosses threshold=3
    # on the very first post-shift step (i=3, value=5): s_pos=5>3.
    values = [0, 0, 0, 5, 5, 5, 5, 5]
    assert cusum_change_points(values, threshold=3, drift=0) == [3]


def test_cusum_detects_sustained_upward_shift_with_auto_tuning():
    # 15 flat baseline points, then a sustained step up -- default
    # sigma-derived threshold/drift should flag the shift somewhere in the
    # shifted region, not before it.
    values = [10.0] * 15 + [50.0] * 15
    change_points = cusum_change_points(values)
    assert change_points, "expected at least one detected change point"
    assert all(cp >= 15 for cp in change_points)


def test_cusum_multiple_shifts_detected_and_resets():
    values = [0, 0, 0, 10, 10, 10, 0, 0, 0]
    change_points = cusum_change_points(values, threshold=3, drift=0)
    # First shift up (index 3), then shift back down (somewhere after index 6).
    assert len(change_points) >= 2
    assert change_points[0] == 3


# ── detect_viral_moment ──────────────────────────────────────────────────────
def _make_history(daily_views: list[int], start="2026-01-01") -> list[dict]:
    d0 = datetime.date.fromisoformat(start)
    out = []
    cumulative = 0
    for i, delta in enumerate([0] + daily_views):
        cumulative += delta
        out.append({"date": (d0 + datetime.timedelta(days=i)).isoformat(), "views": cumulative})
    return out


def test_detect_viral_moment_none_with_too_little_history():
    history = _make_history([10, 10])  # only 3 snapshots -> 2 velocity points
    assert detect_viral_moment(history) is None


def test_detect_viral_moment_flags_sustained_velocity_jump():
    # 15 days at velocity=10, then 5 days at velocity=50.
    history = _make_history([10] * 15 + [50] * 5)
    result = detect_viral_moment(history)
    assert result is not None
    assert result["flagged"] is True
    assert result["direction"] == "up"
    assert result["velocity_after"] > result["velocity_before"]


def test_detect_viral_moment_none_when_velocity_is_steady():
    history = _make_history([10] * 20)
    assert detect_viral_moment(history) is None


# ── forecast_views ────────────────────────────────────────────────────────────
def test_forecast_views_none_with_too_few_points():
    history = _make_history([10, 10])  # 3 snapshots, min_points default is 4
    assert forecast_views(history) is None


def test_forecast_views_none_with_empty_history():
    assert forecast_views([]) is None


def test_forecast_views_projects_growth_forward():
    # Steady ~100 views/day growth over 10 days.
    history = _make_history([100] * 10)
    result = forecast_views(history)
    assert result is not None
    assert result["current_views"] == pytest.approx(1000.0)
    assert result["daily_velocity_estimate"] > 0
    assert set(result["forecast"].keys()) == {"7d", "30d"}
    assert result["forecast"]["7d"] > result["current_views"]
    assert result["forecast"]["30d"] > result["forecast"]["7d"]


def test_forecast_views_handles_zero_growth_without_crashing():
    history = _make_history([0] * 6)
    result = forecast_views(history)
    # Either a graceful None or a flat forecast -- must not raise.
    if result is not None:
        assert result["forecast"]["7d"] >= result["current_views"]


def test_forecast_views_custom_horizon():
    history = _make_history([50] * 8)
    result = forecast_views(history, horizon_days=(1, 14))
    assert result is not None
    assert set(result["forecast"].keys()) == {"1d", "14d"}


# ── longitudinal migration / latest_metrics ─────────────────────────────────
def test_latest_metrics_passthrough_for_flat_legacy_entry():
    entry = {"videoThumbnailImpressionsClickRate": 0.03, "views": 100}
    assert latest_metrics(entry) == entry


def test_latest_metrics_returns_last_snapshot_for_history_format():
    entry = {
        "pillar": "temporal",
        "history": [
            {"date": "2026-01-01", "views": 10},
            {"date": "2026-01-08", "views": 50},
        ],
    }
    assert latest_metrics(entry) == {"date": "2026-01-08", "views": 50}


def test_latest_metrics_empty_history_returns_empty_dict():
    assert latest_metrics({"history": []}) == {}


def test_load_analytics_migrates_old_flat_format_on_disk(tmp_path, monkeypatch):
    log_path = tmp_path / "analytics_log.json"
    log_path.write_text(json.dumps({
        "vid1": {
            "pillar": "temporal", "duration_secs": 3600,
            "videoThumbnailImpressionsClickRate": 0.04, "views": 200,
            "fetched_at": "2026-01-05T00:00:00+00:00",
        }
    }))
    monkeypatch.setattr(analytics_mod, "ANALYTICS_LOG", str(log_path))

    migrated = load_analytics()
    assert "history" in migrated["vid1"]
    assert len(migrated["vid1"]["history"]) == 1
    snap = migrated["vid1"]["history"][0]
    assert snap["videoThumbnailImpressionsClickRate"] == 0.04
    assert snap["views"] == 200
    assert snap["date"] == "2026-01-05"
    # Metadata stays at top level, unaffected by migration.
    assert migrated["vid1"]["pillar"] == "temporal"
    assert migrated["vid1"]["duration_secs"] == 3600


def test_load_analytics_passes_through_already_migrated_entries(tmp_path, monkeypatch):
    log_path = tmp_path / "analytics_log.json"
    original = {
        "vid1": {
            "pillar": "activity",
            "history": [
                {"date": "2026-01-01", "views": 10},
                {"date": "2026-01-08", "views": 40},
            ],
        }
    }
    log_path.write_text(json.dumps(original))
    monkeypatch.setattr(analytics_mod, "ANALYTICS_LOG", str(log_path))

    migrated = load_analytics()
    assert migrated == original


def test_load_analytics_history_sorted_oldest_first(tmp_path, monkeypatch):
    log_path = tmp_path / "analytics_log.json"
    log_path.write_text(json.dumps({
        "vid1": {"history": [
            {"date": "2026-01-08", "views": 40},
            {"date": "2026-01-01", "views": 10},
        ]},
    }))
    monkeypatch.setattr(analytics_mod, "ANALYTICS_LOG", str(log_path))

    history = load_analytics_history()
    dates = [s["date"] for s in history["vid1"]]
    assert dates == ["2026-01-01", "2026-01-08"]


def test_load_analytics_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(analytics_mod, "ANALYTICS_LOG", str(tmp_path / "nope.json"))
    assert load_analytics() == {}


# ── sync_analytics: longitudinal append + same-day idempotency ─────────────
def _fake_upload_entry(video_id="dQw4w9WgXcQ", days_ago=10, pillar="temporal"):
    ts = (datetime.datetime.now(datetime.timezone.utc)
          - datetime.timedelta(days=days_ago)).isoformat()
    return {
        "type": "upload", "video_id": video_id, "timestamp": ts,
        "pillar": pillar, "concept": "test concept", "title": "test title",
        "title_variants": ["a", "b"], "title_chosen_idx": 0,
        "duration_secs": 3600,
    }


def test_sync_analytics_appends_new_snapshot_to_existing_history(tmp_path, monkeypatch):
    upload_log = tmp_path / "upload_log.json"
    analytics_log = tmp_path / "analytics_log.json"
    upload_log.write_text(json.dumps([_fake_upload_entry()]))
    # Pre-existing OLD-format single-snapshot entry -- sync should migrate it
    # in memory and *append* a second snapshot, not overwrite the first.
    analytics_log.write_text(json.dumps({
        "dQw4w9WgXcQ": {
            "pillar": "temporal", "duration_secs": 3600,
            "videoThumbnailImpressionsClickRate": 0.02, "views": 100,
            "upload_date": "2026-01-01", "fetched_at": "2026-01-01T00:00:00+00:00",
        }
    }))
    monkeypatch.setattr(analytics_mod, "UPLOAD_LOG", str(upload_log))
    monkeypatch.setattr(analytics_mod, "ANALYTICS_LOG", str(analytics_log))
    monkeypatch.setattr(analytics_mod, "_get_analytics_service", lambda: object())
    monkeypatch.setattr(analytics_mod, "_get_channel_id", lambda: "channel123")
    monkeypatch.setattr(
        analytics_mod, "fetch_video_metrics",
        lambda svc, vid, cid, upload_date, end_date: {
            "views": 500, "estimatedMinutesWatched": 400, "averageViewDuration": 1200,
            "videoThumbnailImpressionsClickRate": 0.06, "videoThumbnailImpressions": 8000,
        },
    )

    result = analytics_mod.sync_analytics()

    hist = result["dQw4w9WgXcQ"]["history"]
    assert len(hist) == 2
    assert hist[0]["views"] == 100          # old snapshot preserved
    assert hist[1]["views"] == 500          # new snapshot appended
    assert result["dQw4w9WgXcQ"]["pillar"] == "temporal"  # metadata preserved

    on_disk = json.loads(analytics_log.read_text())
    assert len(on_disk["dQw4w9WgXcQ"]["history"]) == 2


def test_sync_analytics_skips_video_already_synced_today(tmp_path, monkeypatch):
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    upload_log = tmp_path / "upload_log.json"
    analytics_log = tmp_path / "analytics_log.json"
    upload_log.write_text(json.dumps([_fake_upload_entry()]))
    analytics_log.write_text(json.dumps({
        "dQw4w9WgXcQ": {
            "pillar": "temporal", "duration_secs": 3600,
            "history": [{"date": today, "views": 100}],
        }
    }))
    monkeypatch.setattr(analytics_mod, "UPLOAD_LOG", str(upload_log))
    monkeypatch.setattr(analytics_mod, "ANALYTICS_LOG", str(analytics_log))

    def _boom(*a, **k):
        raise AssertionError("fetch_video_metrics should not be called for a video already synced today")

    monkeypatch.setattr(analytics_mod, "fetch_video_metrics", _boom)
    monkeypatch.setattr(analytics_mod, "_get_analytics_service", _boom)
    monkeypatch.setattr(analytics_mod, "_get_channel_id", _boom)

    result = analytics_mod.sync_analytics()
    assert len(result["dQw4w9WgXcQ"]["history"]) == 1  # unchanged


def test_sync_analytics_new_video_gets_randomized_ab_variant(tmp_path, monkeypatch):
    upload_log = tmp_path / "upload_log.json"
    analytics_log = tmp_path / "analytics_log.json"
    upload_log.write_text(json.dumps([_fake_upload_entry(video_id="brandNew123")]))  # 11 chars
    analytics_log.write_text(json.dumps({}))
    monkeypatch.setattr(analytics_mod, "UPLOAD_LOG", str(upload_log))
    monkeypatch.setattr(analytics_mod, "ANALYTICS_LOG", str(analytics_log))
    monkeypatch.setattr(analytics_mod, "_get_analytics_service", lambda: object())
    monkeypatch.setattr(analytics_mod, "_get_channel_id", lambda: "channel123")
    monkeypatch.setattr(
        analytics_mod, "fetch_video_metrics",
        lambda svc, vid, cid, upload_date, end_date: {
            "views": 10, "videoThumbnailImpressionsClickRate": 0.03,
        },
    )

    result = analytics_mod.sync_analytics()
    assert result["brandNew123"]["ab_variant"] in ("A", "B")


# ── pillar_weights (bandit-backed replacement for generate_seo._pillar_weights) ──
def test_pillar_weights_empty_analytics():
    assert pillar_weights(["temporal", "activity"], {}) == {"temporal": 1.0, "activity": 1.0}


def test_pillar_weights_below_sample_threshold_stays_uniform():
    fake = {f"v{i}": {"pillar": "temporal", "videoThumbnailImpressionsClickRate": 0.05}
            for i in range(3)}
    assert pillar_weights(["temporal", "activity"], fake) == {"temporal": 1.0, "activity": 1.0}


def test_pillar_weights_rewards_higher_composite_pillar():
    fake = {}
    for i in range(6):
        fake[f"hi_{i}"] = {"pillar": "temporal", "videoThumbnailImpressionsClickRate": 0.08}
    for i in range(6):
        fake[f"lo_{i}"] = {"pillar": "activity", "videoThumbnailImpressionsClickRate": 0.01}
    result = pillar_weights(["temporal", "activity", "emotional"], fake)
    assert result["temporal"] > 1.0
    assert result["activity"] < 1.0
    assert result["emotional"] == 1.0  # no data at all -> neutral default, not penalized


def test_pillar_weights_clamped_to_range():
    fake = {}
    for i in range(6):
        fake[f"hi_{i}"] = {"pillar": "temporal", "videoThumbnailImpressionsClickRate": 1.0}
    for i in range(6):
        fake[f"lo_{i}"] = {"pillar": "activity", "videoThumbnailImpressionsClickRate": 0.0001}
    result = pillar_weights(["temporal", "activity"], fake)
    assert result["temporal"] <= 2.0
    assert result["activity"] >= 0.5


# ── pillar_bandit_posteriors (raw posterior for the dashboard) ─────────────
def test_pillar_bandit_posteriors_empty_analytics_returns_prior_for_every_pillar():
    result = pillar_bandit_posteriors(["temporal", "activity"], {})
    assert set(result.keys()) == {"temporal", "activity"}
    for stats in result.values():
        assert stats["alpha"] == pytest.approx(1.0)
        assert stats["beta"] == pytest.approx(1.0)
        assert stats["n"] == 0
        assert stats["mean"] == pytest.approx(0.5)


def test_pillar_bandit_posteriors_reflects_observed_data():
    fake = {}
    for i in range(6):
        fake[f"hi_{i}"] = {"pillar": "temporal", "videoThumbnailImpressionsClickRate": 0.08}
    for i in range(6):
        fake[f"lo_{i}"] = {"pillar": "activity", "videoThumbnailImpressionsClickRate": 0.01}
    result = pillar_bandit_posteriors(["temporal", "activity"], fake)
    assert result["temporal"]["n"] == 6
    assert result["activity"]["n"] == 6
    assert result["temporal"]["mean"] > result["activity"]["mean"]
    # 6 successes / 0 failures -> alpha=7, beta=1 for the strictly-above-median arm
    assert result["temporal"]["alpha"] == pytest.approx(7.0)
    assert result["temporal"]["beta"] == pytest.approx(1.0)


def test_composite_score_compares_videos_at_the_same_age():
    entry = {
        "duration_secs": 3600,
        "upload_date": "2026-01-01",
        "history": [
            {"date": "2026-01-03", "videoThumbnailImpressionsClickRate": 0.01},
            {"date": "2026-01-08", "videoThumbnailImpressionsClickRate": 0.04},
            {"date": "2026-02-20", "videoThumbnailImpressionsClickRate": 0.09},
        ],
    }
    # Day 7 after upload is 2026-01-08: that snapshot, not the latest one.
    assert composite_engagement_score(entry) == pytest.approx(0.04)


def test_long_videos_are_not_penalised_for_their_length():
    short = {"averageViewDuration": 900, "duration_secs": 1800}
    long_ = {"averageViewDuration": 900, "duration_secs": 8 * 3600}
    assert composite_engagement_score(short) == composite_engagement_score(long_)


def test_ctr_reported_as_a_percentage_is_normalised():
    from scripts.analytics import ctr_fraction
    assert ctr_fraction(4.5) == pytest.approx(0.045)
    assert ctr_fraction(0.045) == pytest.approx(0.045)
