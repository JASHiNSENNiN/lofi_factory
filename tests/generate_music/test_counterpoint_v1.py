"""
Tests for the species-counterpoint voice-leading cost function ported into
v1 (composer.py) from v2's Stage-3 work: per-voice-pair
parallel-5th/octave detection (not just adjacent pairs), per-pair
contrary-motion scoring, and dissonance/suspension-resolution treatment.
Mirrors test_counterpoint.py (which tests the original v2 version) against
the new v1 location -- _voicing_transition_cost is byte-identical, only the
import changes.
"""

from scripts.composer import _voicing_transition_cost


# ── parallel 5th/octave: every pair, not just adjacent ──────────────────────

def test_clean_voicing_scores_better_than_parallel_fifths():
    prev = [48, 55, 60, 64]
    clean = [50, 57, 60, 65]
    parallel = [50, 57, 62, 66]

    clean_cost = _voicing_transition_cost(prev, clean)
    parallel_cost = _voicing_transition_cost(prev, parallel)
    assert parallel_cost > clean_cost


def test_parallel_fifth_between_non_adjacent_voices_is_detected():
    prev = [48, 55, 55]
    shifted = [50, 55, 57]
    cost = _voicing_transition_cost(prev, shifted)
    assert cost >= 8.0


def test_parallel_octave_between_outer_voices_of_wide_chord():
    prev = [40, 55, 60, 64, 76]
    shifted = [43, 55, 60, 64, 79]
    cost = _voicing_transition_cost(prev, shifted)
    assert cost >= 8.0


def test_similar_motion_to_a_fifth_without_parallel_start_is_not_penalized():
    prev = [60, 64]
    shifted = [62, 69]
    cost = _voicing_transition_cost(prev, shifted)
    assert cost < 8.0


# ── per-pair contrary motion ─────────────────────────────────────────────────

def test_contrary_motion_scores_better_than_similar_motion_same_displacement():
    prev = [55, 64]
    contrary = [57, 62]
    similar = [57, 66]
    assert _voicing_transition_cost(prev, contrary) < _voicing_transition_cost(prev, similar)


# ── dissonance / suspension-resolution ───────────────────────────────────────

def test_dissonance_resolved_by_step_scores_better_than_left_hanging():
    prev = [60, 61]
    resolved = [60, 60]
    hanging = [61, 62]
    resolved_cost = _voicing_transition_cost(prev, resolved)
    hanging_cost = _voicing_transition_cost(prev, hanging)
    assert resolved_cost < hanging_cost


def test_dissonance_resolved_by_leap_is_not_rewarded_like_a_step():
    prev = [60, 61]
    step_resolution = [60, 60]
    leap_resolution = [60, 72]
    assert (_voicing_transition_cost(prev, step_resolution)
            < _voicing_transition_cost(prev, leap_resolution))


def test_tritone_is_treated_as_dissonant():
    prev = [60, 66]
    resolved = [60, 65]
    cost_resolved = _voicing_transition_cost(prev, resolved)
    cost_static = _voicing_transition_cost(prev, [60, 66])
    assert cost_resolved < cost_static


def test_sevenths_are_not_treated_as_dissonant_clashes():
    prev = [60, 70]
    held = [60, 70]
    cost = _voicing_transition_cost(prev, held)
    assert cost == 0.0


# ── every pair is scored independently (not aggregated into one bucket) ─────

def test_cost_increases_monotonically_as_more_pairs_violate():
    prev = [48, 55, 60, 67]
    one_violation = [50, 57, 60, 67]
    two_violations = [50, 57, 62, 69]

    cost_one = _voicing_transition_cost(prev, one_violation)
    cost_two = _voicing_transition_cost(prev, two_violations)
    assert cost_two > cost_one
