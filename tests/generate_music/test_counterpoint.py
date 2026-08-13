"""
Tests for the per-voice-pair species-counterpoint upgrade to
_voicing_transition_cost() (Stage 3 item 2) — parallel-5th/octave detection
evaluated independently for every pair of voices (not just adjacent ones),
per-pair contrary-motion scoring, and dissonance/suspension-resolution
treatment.
"""

from scripts.generate_music_v2 import _voicing_transition_cost


# ── parallel 5th/octave: every pair, not just adjacent ──────────────────────

def test_clean_voicing_scores_better_than_parallel_fifths():
    prev = [48, 55, 60, 64]   # C3, G3, C4, E4
    clean = [50, 57, 60, 65]  # small, mostly contrary/oblique motion
    parallel = [50, 57, 62, 66]  # every voice up a whole step -> parallel 5ths/octaves throughout

    clean_cost = _voicing_transition_cost(prev, clean)
    parallel_cost = _voicing_transition_cost(prev, parallel)
    assert parallel_cost > clean_cost


def test_parallel_fifth_between_non_adjacent_voices_is_detected():
    # 3-voice chord: voices 0 and 2 (non-adjacent) move in parallel by a
    # perfect 5th both before and after; voice 1 stays put. The OLD
    # aggregate-adjacent-pairs-only cost function could not see a violation
    # between voice 0 and voice 2 at all.
    prev = [48, 55, 55]       # (0,2) interval = 7 (P5)
    shifted = [50, 55, 57]    # (0,2) interval = 7 (P5), both moved +2, same direction
    cost = _voicing_transition_cost(prev, shifted)
    assert cost >= 8.0   # the parallel-5th penalty must fire for this pair


def test_parallel_octave_between_outer_voices_of_wide_chord():
    prev = [40, 55, 60, 64, 76]      # voices 0 and 4 are two octaves apart (interval class 0)
    shifted = [43, 55, 60, 64, 79]   # both moved +3, same direction, still an octave apart
    cost = _voicing_transition_cost(prev, shifted)
    assert cost >= 8.0


def test_similar_motion_to_a_fifth_without_parallel_start_is_not_penalized():
    # Interval before is NOT a 5th/octave (it's a 3rd), so landing on a 5th
    # afterward is similar motion into a perfect interval, not "parallel"
    # fifths in the strict sense this checker targets (requires interval
    # class 0/7 both before AND after).
    prev = [60, 64]     # M3
    shifted = [62, 69]  # moves to a P5, but didn't start on one
    cost = _voicing_transition_cost(prev, shifted)
    # no parallel-5th penalty component (8.0) should be included
    assert cost < 8.0


# ── per-pair contrary motion ─────────────────────────────────────────────────

def test_contrary_motion_scores_better_than_similar_motion_same_displacement():
    prev = [55, 64]
    contrary = [57, 62]   # voice 0 up 2, voice 1 down 2 -> contrary, |displacement| equal
    similar = [57, 66]    # both up -> similar motion, same total displacement (4)
    assert _voicing_transition_cost(prev, contrary) < _voicing_transition_cost(prev, similar)


# ── dissonance / suspension-resolution ───────────────────────────────────────

def test_dissonance_resolved_by_step_scores_better_than_left_hanging():
    prev = [60, 61]          # m2 (interval class 1) -- dissonant, needs resolution
    resolved = [60, 60]      # top voice steps down by 1 -> consonant unison, stepwise
    hanging = [61, 62]       # both voices shift up together -> still a dissonant m2
    resolved_cost = _voicing_transition_cost(prev, resolved)
    hanging_cost = _voicing_transition_cost(prev, hanging)
    assert resolved_cost < hanging_cost


def test_dissonance_resolved_by_leap_is_not_rewarded_like_a_step():
    prev = [60, 61]           # m2
    step_resolution = [60, 60]     # resolves by step (1 semitone)
    leap_resolution = [60, 72]     # "resolves" (consonant octave) but by a 11-semitone leap
    assert (_voicing_transition_cost(prev, step_resolution)
            < _voicing_transition_cost(prev, leap_resolution))


def test_tritone_is_treated_as_dissonant():
    prev = [60, 66]      # tritone (interval class 6)
    resolved = [60, 65]  # top voice steps down to a P4-ish resolution (interval class 5, consonant-ish)
    cost_resolved = _voicing_transition_cost(prev, resolved)
    cost_static = _voicing_transition_cost(prev, [60, 66])  # unchanged, dissonance held
    assert cost_resolved < cost_static


def test_sevenths_are_not_treated_as_dissonant_clashes():
    # Minor/major 7th intervals are legitimate chord tones in this pipeline's
    # jazz/lofi 7th-chord voicings (VOICING_OPTIONS) -- they must NOT trigger
    # the dissonance-resolution penalty the way a m2/M2/tritone does.
    prev = [60, 70]       # m7 (interval class 10)
    held = [60, 70]       # unchanged
    cost = _voicing_transition_cost(prev, held)
    assert cost == 0.0


# ── every pair is scored independently (not aggregated into one bucket) ─────

def test_cost_increases_monotonically_as_more_pairs_violate():
    # A 4-voice chord where progressively more voice PAIRS have parallel
    # 5ths/octaves should score strictly worse each time, proving each pair
    # contributes its own independent penalty rather than a single flat term.
    prev = [48, 55, 60, 67]  # (0,1)=P5, (2,3)=P5-ish(7), plenty of pairs to work with

    # Move only voices 0,1 in parallel (one violating pair)
    one_violation = [50, 57, 60, 67]
    # Move voices 0,1 AND 2,3 in parallel (two violating pairs)
    two_violations = [50, 57, 62, 69]

    cost_one = _voicing_transition_cost(prev, one_violation)
    cost_two = _voicing_transition_cost(prev, two_violations)
    assert cost_two > cost_one
