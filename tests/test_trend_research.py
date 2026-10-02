"""
Tests for trend_research.py's historical competitor tracking (Stage 1
"Analytics rigor" item 7): assets/trend_cache.json as an append-only history
of dated snapshots instead of a single overwritten row, plus
the snapshot history kept in assets/trend_cache.json.
"""
import json


import scripts.trend_research as tr


def _snapshot(fetched_at: str, videos: list[dict]) -> dict:
    return {
        "trending_titles": [v["title"] for v in videos],
        "trending_tags": [],
        "trending_duration": {},
        "yt_videos": videos,
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


# ── get_trend_snapshot: append-only history ─────────────────────────────────
def _patch_fetchers(monkeypatch, videos):
    monkeypatch.setattr(tr, "fetch_yt_trending", lambda max_results=20: videos)


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


