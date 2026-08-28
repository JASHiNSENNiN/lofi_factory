"""
Tests for trend_research.py's historical competitor tracking (Stage 1
"Analytics rigor" item 7): assets/trend_cache.json as an append-only history
of dated snapshots instead of a single overwritten row, plus
compute_trend_deltas() for tracking competitor view-count changes over time.
"""
import json

import pytest

import scripts.trend_research as tr


def _snapshot(fetched_at: str, videos: list[dict]) -> dict:
    return {
        "trending_titles": [v["title"] for v in videos],
        "trending_tags": [],
        "trending_duration": {},
        "yt_videos": videos,
        "yt_dlp_videos": [],
        "gemini_insight": None,
        "groq_analysis": None,
        "season": "summer",
        "seasonal_keywords": [],
        "fetched_at": fetched_at,
        "suggested_theme": "cozy_rain",
        "music_hints": {},
    }


# ── _load_history / _save_history ───────────────────────────────────────────
def test_load_history_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "CACHE_FILE", str(tmp_path / "nope.json"))
    assert tr._load_history() == []


def test_load_history_wraps_old_single_snapshot_dict_format(tmp_path, monkeypatch):
    cache = tmp_path / "trend_cache.json"
    old_format = _snapshot("2026-01-01T00:00:00+00:00", [])
    cache.write_text(json.dumps(old_format))
    monkeypatch.setattr(tr, "CACHE_FILE", str(cache))

    history = tr._load_history()
    assert history == [old_format]


def test_load_history_passes_through_list_format(tmp_path, monkeypatch):
    cache = tmp_path / "trend_cache.json"
    snaps = [_snapshot("2026-01-01T00:00:00+00:00", []),
             _snapshot("2026-01-02T00:00:00+00:00", [])]
    cache.write_text(json.dumps(snaps))
    monkeypatch.setattr(tr, "CACHE_FILE", str(cache))

    assert tr._load_history() == snaps


def test_load_history_malformed_json_returns_empty(tmp_path, monkeypatch):
    cache = tmp_path / "trend_cache.json"
    cache.write_text("not valid json{{{")
    monkeypatch.setattr(tr, "CACHE_FILE", str(cache))
    assert tr._load_history() == []


def test_save_history_caps_at_max_history(tmp_path, monkeypatch):
    cache = tmp_path / "trend_cache.json"
    monkeypatch.setattr(tr, "CACHE_FILE", str(cache))
    monkeypatch.setattr(tr, "MAX_HISTORY", 3)

    history = [_snapshot(f"2026-01-0{i}T00:00:00+00:00", []) for i in range(1, 6)]
    tr._save_history(history)

    saved = json.loads(cache.read_text())
    assert len(saved) == 3
    # Oldest trimmed first -- the last 3 of the 5 should remain.
    assert [s["fetched_at"][:10] for s in saved] == ["2026-01-03", "2026-01-04", "2026-01-05"]


# ── compute_trend_deltas ─────────────────────────────────────────────────────
def test_compute_trend_deltas_none_with_fewer_than_two_snapshots():
    assert tr.compute_trend_deltas([]) is None
    assert tr.compute_trend_deltas([_snapshot("2026-01-01T00:00:00+00:00", [])]) is None


def test_compute_trend_deltas_matches_by_title_and_computes_delta():
    prev = _snapshot("2026-01-01T00:00:00+00:00", [
        {"title": "cozy rain lofi", "channel": "c1", "views": 1000},
        {"title": "midnight study beats", "channel": "c2", "views": 500},
    ])
    latest = _snapshot("2026-01-08T00:00:00+00:00", [
        {"title": "cozy rain lofi", "channel": "c1", "views": 1500},
        {"title": "midnight study beats", "channel": "c2", "views": 400},
        {"title": "brand new video", "channel": "c3", "views": 200},  # no prior match
    ])
    result = tr.compute_trend_deltas([prev, latest])

    assert result["date_prev"] == "2026-01-01"
    assert result["date_latest"] == "2026-01-08"
    assert result["total_views_prev"] == 1500
    assert result["total_views_latest"] == 2100
    assert result["delta_total"] == 600
    assert result["delta_pct"] == pytest.approx(600 / 1500)

    by_title = {r["title"]: r for r in result["per_video"]}
    assert set(by_title.keys()) == {"cozy rain lofi", "midnight study beats"}
    assert by_title["cozy rain lofi"]["delta"] == 500
    assert by_title["midnight study beats"]["delta"] == -100
    # Sorted largest-positive-delta first.
    assert result["per_video"][0]["title"] == "cozy rain lofi"


def test_compute_trend_deltas_no_overlap_still_returns_totals():
    prev = _snapshot("2026-01-01T00:00:00+00:00", [{"title": "old vid", "views": 100}])
    latest = _snapshot("2026-01-08T00:00:00+00:00", [{"title": "new vid", "views": 300}])
    result = tr.compute_trend_deltas([prev, latest])
    assert result["per_video"] == []
    assert result["total_views_prev"] == 100
    assert result["total_views_latest"] == 300


def test_compute_trend_deltas_zero_prev_views_delta_pct_none():
    prev = _snapshot("2026-01-01T00:00:00+00:00", [])
    latest = _snapshot("2026-01-08T00:00:00+00:00", [{"title": "x", "views": 100}])
    result = tr.compute_trend_deltas([prev, latest])
    assert result["total_views_prev"] == 0
    assert result["delta_pct"] is None


# ── get_trend_snapshot: append-only history ─────────────────────────────────
def _patch_fetchers(monkeypatch, videos):
    monkeypatch.setattr(tr, "fetch_yt_trending", lambda max_results=20: videos)
    monkeypatch.setattr(tr, "fetch_yt_dlp_trending", lambda max_results=15: [])
    monkeypatch.setattr(tr, "fetch_gemini_trends", lambda: None)
    monkeypatch.setattr(tr, "_groq_analyze_trends", lambda *a, **k: None)


def test_get_trend_snapshot_appends_new_snapshot_on_force_refresh(tmp_path, monkeypatch):
    cache = tmp_path / "trend_cache.json"
    monkeypatch.setattr(tr, "CACHE_FILE", str(cache))
    _patch_fetchers(monkeypatch, [{"title": "lofi beats to study", "channel": "c",
                                    "views": 1000, "tags": ["lofi"], "duration": "2 hours"}])

    snap1 = tr.get_trend_snapshot(force_refresh=True)
    assert snap1["yt_videos"][0]["views"] == 1000
    history_after_1 = json.loads(cache.read_text())
    assert len(history_after_1) == 1

    _patch_fetchers(monkeypatch, [{"title": "lofi beats to study", "channel": "c",
                                    "views": 2000, "tags": ["lofi"], "duration": "2 hours"}])
    snap2 = tr.get_trend_snapshot(force_refresh=True)
    assert snap2["yt_videos"][0]["views"] == 2000

    history_after_2 = json.loads(cache.read_text())
    assert len(history_after_2) == 2  # appended, not overwritten
    assert history_after_2[0]["yt_videos"][0]["views"] == 1000  # first snapshot preserved

    deltas = tr.compute_trend_deltas(history_after_2)
    assert deltas["per_video"][0]["delta"] == 1000


def test_get_trend_snapshot_uses_cache_without_appending_when_fresh(tmp_path, monkeypatch):
    cache = tmp_path / "trend_cache.json"
    monkeypatch.setattr(tr, "CACHE_FILE", str(cache))
    _patch_fetchers(monkeypatch, [{"title": "a", "channel": "c", "views": 1,
                                    "tags": [], "duration": "1 hour"}])

    tr.get_trend_snapshot(force_refresh=True)
    assert len(json.loads(cache.read_text())) == 1

    # Not forced, and the snapshot we just wrote is well within CACHE_TTL --
    # should return the cached one without appending another.
    tr.get_trend_snapshot(force_refresh=False)
    assert len(json.loads(cache.read_text())) == 1


def test_get_trend_snapshot_migrates_old_format_file_on_disk(tmp_path, monkeypatch):
    cache = tmp_path / "trend_cache.json"
    cache.write_text(json.dumps(_snapshot("2026-01-01T00:00:00+00:00", [])))
    monkeypatch.setattr(tr, "CACHE_FILE", str(cache))
    _patch_fetchers(monkeypatch, [{"title": "new", "channel": "c", "views": 5,
                                    "tags": [], "duration": "1 hour"}])

    tr.get_trend_snapshot(force_refresh=True)

    saved = json.loads(cache.read_text())
    assert isinstance(saved, list)
    assert len(saved) == 2  # old dict-format snapshot wrapped + new one appended


# ── extract_title_benefit_signals ───────────────────────────────────────────
def test_extract_title_benefit_signals_ranks_by_frequency():
    snapshot = _snapshot("2026-01-01T00:00:00+00:00", [
        {"title": "lofi hip hop radio - beats to sleep and relax to"},
        {"title": "1 A.M study session - lofi beats to sleep to"},
        {"title": "chill lofi mix to relax to"},
    ])
    ranked = tr.extract_title_benefit_signals(snapshot, top_k=2)
    # "sleep" appears twice, "relax" twice, "study"/"chill" once each --
    # both top hits must outrank the once-only words.
    assert set(ranked) == {"sleep", "relax"}


def test_extract_title_benefit_signals_falls_back_without_trend_data():
    empty_snapshot = _snapshot("2026-01-01T00:00:00+00:00", [])
    assert tr.extract_title_benefit_signals({}, top_k=3) == ["study", "focus", "relax"]
    assert tr.extract_title_benefit_signals(empty_snapshot, top_k=3) == ["study", "focus", "relax"]


def test_extract_title_benefit_signals_falls_back_when_vocab_absent():
    # Real titles exist, but none mention any benefit-keyword -- still a
    # graceful fallback to the static vocabulary rather than an empty list.
    snapshot = _snapshot("2026-01-01T00:00:00+00:00", [
        {"title": "lofi hip hop radio for coding and gaming sessions"},
    ])
    assert tr.extract_title_benefit_signals(snapshot, top_k=3) == ["study", "focus", "relax"]
