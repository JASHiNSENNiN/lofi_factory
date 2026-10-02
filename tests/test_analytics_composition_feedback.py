"""
Tests for the composition-selection engagement-feedback loop: extending the
Thompson-sampling / Beta-Bernoulli bandit machinery (previously wired only
into SEO-pillar choice and video duration) to sub-genre, BPM, and generation
engine (v1/v2) selection.

Fixture-construction pattern mirrors tests/test_analytics.py's
duration_weights()/title_variant_weights() tests: plain flat dicts (no
"history" wrapper — latest_metrics()/composite_engagement_score() treat a
flat dict as already-a-snapshot, which is also what these functions are fed
in production via load_analytics()'s migration).
"""
import random as _random_mod
from collections import Counter

import scripts.analytics as analytics_mod
from scripts.analytics import bpm_bucket_weights, engine_weights, sub_genre_weights
from scripts.composer import _SUBGENRE_CONFIG, _pick_subgenre_weighted

SUBS = ["chillhop", "jazzhop", "ambient_lofi"]


# ── sub_genre_weights() ──────────────────────────────────────────────────

def test_sub_genre_weights_empty_analytics():
    assert sub_genre_weights(SUBS, {}) == {s: 1.0 for s in SUBS}


def test_sub_genre_weights_uniform_below_sample_threshold():
    fake = {f"v{i}": {"sub_genre": "chillhop", "videoThumbnailImpressionsClickRate": 0.05}
            for i in range(3)}
    assert sub_genre_weights(SUBS, fake) == {s: 1.0 for s in SUBS}


def test_sub_genre_weights_rewards_higher_engagement_subgenre():
    fake = {}
    for i in range(6):
        fake[f"a{i}"] = {"sub_genre": "chillhop", "videoThumbnailImpressionsClickRate": 0.09}
    for i in range(6):
        fake[f"b{i}"] = {"sub_genre": "jazzhop", "videoThumbnailImpressionsClickRate": 0.01}
    result = sub_genre_weights(SUBS, fake)
    assert result["chillhop"] > 1.0
    assert result["jazzhop"] < 1.0
    assert result["ambient_lofi"] == 1.0  # no data for this one -> untouched default


def test_sub_genre_weights_clamped_to_range():
    fake = {}
    for i in range(6):
        fake[f"hi_{i}"] = {"sub_genre": "chillhop", "videoThumbnailImpressionsClickRate": 1.0}
    for i in range(6):
        fake[f"lo_{i}"] = {"sub_genre": "jazzhop", "videoThumbnailImpressionsClickRate": 0.0}
    result = sub_genre_weights(SUBS, fake)
    assert result["chillhop"] <= 2.0
    assert result["jazzhop"] >= 0.5


def test_sub_genre_weights_lazy_default_uses_real_subgenre_config():
    # No explicit `sub_genres` -> lazy-imports scripts.composer
    # and defaults to every known key. Cold start (analytics={}) so this
    # only tests wiring, not the bandit math.
    result = sub_genre_weights(analytics={})
    assert set(result.keys()) == set(_SUBGENRE_CONFIG.keys())
    assert all(w == 1.0 for w in result.values())


# ── bpm_bucket_weights() ─────────────────────────────────────────────────

def test_bpm_bucket_weights_empty_analytics():
    assert bpm_bucket_weights(analytics={}) == {}


def test_bpm_bucket_weights_uniform_below_sample_threshold():
    fake = {f"v{i}": {"bpm": 82, "videoThumbnailImpressionsClickRate": 0.05} for i in range(3)}
    assert bpm_bucket_weights(analytics=fake) == {}


def test_bpm_bucket_weights_rewards_higher_engagement_bucket():
    fake = {}
    for i in range(6):
        fake[f"a{i}"] = {"bpm": 82, "videoThumbnailImpressionsClickRate": 0.09}
    for i in range(6):
        fake[f"b{i}"] = {"bpm": 95, "videoThumbnailImpressionsClickRate": 0.01}
    result = bpm_bucket_weights(analytics=fake)
    assert result[80] > 1.0
    assert result[90] < 1.0


def test_bpm_bucket_weights_custom_bucket_width():
    fake = {}
    for i in range(6):
        fake[f"a{i}"] = {"bpm": 84, "videoThumbnailImpressionsClickRate": 0.09}
    for i in range(6):
        fake[f"b{i}"] = {"bpm": 92, "videoThumbnailImpressionsClickRate": 0.01}
    result = bpm_bucket_weights(bucket_width=5, analytics=fake)
    assert result[80] > 1.0   # 84 // 5 * 5 = 80
    assert result[90] < 1.0   # 92 // 5 * 5 = 90


# ── engine_weights() ─────────────────────────────────────────────────────

def test_engine_weights_empty_analytics():
    assert engine_weights({}) == {"v1": 1.0, "v2": 1.0}


def test_engine_weights_uniform_below_sample_threshold():
    fake = {f"v{i}": {"music_engine": "v2", "videoThumbnailImpressionsClickRate": 0.05}
            for i in range(3)}
    assert engine_weights(fake) == {"v1": 1.0, "v2": 1.0}


def test_engine_weights_rewards_higher_engagement_engine():
    fake = {}
    for i in range(6):
        fake[f"a{i}"] = {"music_engine": "v2", "videoThumbnailImpressionsClickRate": 0.09}
    for i in range(6):
        fake[f"b{i}"] = {"music_engine": "v1", "videoThumbnailImpressionsClickRate": 0.01}
    result = engine_weights(fake)
    assert result["v2"] > 1.0
    assert result["v1"] < 1.0


def test_engine_weights_defaults_missing_field_to_v1():
    # Entries logged before music_engine tracking existed have no key at
    # all -- must be treated as "v1", not silently dropped from the bandit.
    fake = {}
    for i in range(6):
        fake[f"a{i}"] = {"videoThumbnailImpressionsClickRate": 0.09}  # no music_engine key
    for i in range(6):
        fake[f"b{i}"] = {"music_engine": "v2", "videoThumbnailImpressionsClickRate": 0.01}
    result = engine_weights(fake)
    assert result["v1"] > 1.0
    assert result["v2"] < 1.0


# ── _pick_subgenre_weighted() actually shifts with the bandit ───────────

def test_pick_subgenre_weighted_shifts_distribution_with_engagement_bandit(monkeypatch):
    all_subs = list(_SUBGENRE_CONFIG.keys())
    target = all_subs[0]

    def _fake_sub_genre_weights(sub_genres=None, analytics=None):
        subs = sub_genres if sub_genres is not None else all_subs
        return {s: (8.0 if s == target else 1.0) for s in subs}

    monkeypatch.setattr(analytics_mod, "sub_genre_weights", _fake_sub_genre_weights)

    counts = Counter()
    n_trials = 300
    for seed in range(n_trials):
        _random_mod.seed(seed)
        picked = _pick_subgenre_weighted([])
        counts[picked] += 1

    uniform_share = 1.0 / len(all_subs)
    observed_share = counts[target] / n_trials
    assert observed_share > uniform_share * 2, (
        f"expected {target!r} biased well above chance ({uniform_share:.3f}), "
        f"got {observed_share:.3f}"
    )


def test_pick_subgenre_weighted_falls_back_when_bandit_lookup_raises(monkeypatch):
    # Engagement weighting must be a no-op (never raise) if analytics lookup
    # itself blows up -- matches every other optional layer in pick_params().
    def _raiser(sub_genres=None, analytics=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(analytics_mod, "sub_genre_weights", _raiser)

    all_subs = set(_SUBGENRE_CONFIG.keys())
    for seed in range(20):
        _random_mod.seed(seed)
        picked = _pick_subgenre_weighted([])
        assert picked in all_subs
