"""
Tests for the two rhythm-groove.md items that were deferred pending a real
build_drums() architecture change (now implemented): the drill hi-hat
triplet subdivision (chh_triplet=) and lofi_phonk's roll_density lever.
"""
import random

from scripts import genre_presets
from scripts.generate_music_gemini import (
    CHH,
    DRUM_PATTERNS,
    KICK,
    SNARE,
    _CHH_TRIPLET_GENRES,
    _PHONK_ROLL_PATTERN_IDX,
    _ROLL_DENSITY_BY_GENRE,
    _TRIPLET_STEPS_PER_BAR,
    _build_triplet_hat_events,
    _scale_roll_intensity,
    build_drums,
)

_PATTERN_A = DRUM_PATTERNS[0]


# ── drill-triplet hi-hat subdivision ────────────────────────────────────────

def test_lofi_drill_is_registered_for_chh_triplet():
    assert "lofi_drill" in _CHH_TRIPLET_GENRES
    assert genre_presets.build_chh_triplet_genres() == _CHH_TRIPLET_GENRES


def test_chh_triplet_false_matches_prior_behavior_exactly():
    random.seed(1)
    a = build_drums(_PATTERN_A, 0, 4, 0.6, 80, chh_triplet=False)
    random.seed(1)
    b = build_drums(_PATTERN_A, 0, 4, 0.6, 80)   # default
    assert a == b


def test_chh_triplet_true_produces_twelve_hits_per_bar_worth_of_chh():
    random.seed(2)
    events = build_drums(_PATTERN_A, 0, 1, 0.6, 80, chh_triplet=True)
    chh_events = [e for e in events if e[1] == CHH]
    # 8% random drop means slightly fewer than 12, never more.
    assert 8 <= len(chh_events) <= _TRIPLET_STEPS_PER_BAR


def test_chh_triplet_does_not_remove_kick_or_snare():
    random.seed(3)
    events = build_drums(_PATTERN_A, 0, 2, 0.6, 80, chh_triplet=True)
    assert any(e[1] == KICK for e in events)
    assert any(e[1] == SNARE for e in events)


def test_build_triplet_hat_events_lands_on_a_12_step_grid():
    random.seed(4)
    events = _build_triplet_hat_events(start_bar=0, num_bars=1, bpm=80)
    assert 0 < len(events) <= _TRIPLET_STEPS_PER_BAR
    for t, note, vel, dur in events:
        assert note == CHH
        assert 0 <= vel <= 127


def test_triplet_accent_steps_are_louder_than_ghost_steps(monkeypatch):
    # Disable the random drop/jitter so accent-vs-ghost velocity is a clean
    # comparison, not noise.
    monkeypatch.setattr(random, "random", lambda: 1.0)   # never drops a step
    events = _build_triplet_hat_events(start_bar=0, num_bars=1, bpm=80)
    # Every 3rd step (0,3,6,9) is accented; velocities should skew higher
    # than the ghosted in-between steps.
    accented = [events[i][2] for i in (0, 3, 6, 9) if i < len(events)]
    ghosted = [events[i][2] for i in (1, 2, 4, 5, 7, 8, 10, 11) if i < len(events)]
    assert sum(accented) / len(accented) > sum(ghosted) / len(ghosted)


# ── phonk roll-density ───────────────────────────────────────────────────────

def test_lofi_phonk_has_a_configured_roll_density():
    assert "lofi_phonk" in _ROLL_DENSITY_BY_GENRE
    assert 0.0 <= _ROLL_DENSITY_BY_GENRE["lofi_phonk"] <= 1.0


def test_scale_roll_intensity_only_affects_pattern_q():
    other_pattern = DRUM_PATTERNS[0]
    result = _scale_roll_intensity(other_pattern, density=1.0)
    assert result is other_pattern   # untouched, not even copied


def test_scale_roll_intensity_zero_flattens_the_roll():
    pattern_q = DRUM_PATTERNS[_PHONK_ROLL_PATTERN_IDX]
    flat = _scale_roll_intensity(pattern_q, density=0.0)
    for step in (12, 13, 14, 15):
        assert flat[CHH][step] == 55   # _PHONK_ROLL_FLAT_VEL


def test_scale_roll_intensity_one_matches_authored_ramp():
    pattern_q = DRUM_PATTERNS[_PHONK_ROLL_PATTERN_IDX]
    full = _scale_roll_intensity(pattern_q, density=1.0)
    assert full[CHH][12:16] == pattern_q[CHH][12:16]


def test_scale_roll_intensity_does_not_mutate_the_original_pattern():
    pattern_q = DRUM_PATTERNS[_PHONK_ROLL_PATTERN_IDX]
    original = list(pattern_q[CHH])
    _scale_roll_intensity(pattern_q, density=0.0)
    assert pattern_q[CHH] == original


def test_scale_roll_intensity_leaves_other_voices_untouched():
    pattern_q = DRUM_PATTERNS[_PHONK_ROLL_PATTERN_IDX]
    scaled = _scale_roll_intensity(pattern_q, density=0.3)
    assert scaled[KICK] == pattern_q[KICK]
    assert scaled[SNARE] == pattern_q[SNARE]


def test_intermediate_density_lands_between_flat_and_full():
    pattern_q = DRUM_PATTERNS[_PHONK_ROLL_PATTERN_IDX]
    half = _scale_roll_intensity(pattern_q, density=0.5)
    for step, full_vel in zip((12, 13, 14, 15), (60, 68, 76, 85)):
        assert 55 < half[CHH][step] < full_vel
