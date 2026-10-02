"""
Tests for the whole-progression voice-leading optimizer (GA + simulated
annealing) ported into v1 (composer.py) from v2's Stage-3
work, and its integration into build_chords() (v1's own restructure, not a
port -- v2's build_chords_v2 has a different 15%-probability-GA design;
v1's build_chords() always tries the whole-progression optimizer first and
falls back to the pre-existing greedy per-chord _voice_lead_choice() only
on failure). The pure-function tests mirror test_voice_leading.py (which
tests the original v2 versions).
"""

import random

import scripts.composer as gmg
from scripts.composer import (
    VOICING_OPTIONS,
    _enumerate_shift_options,
    _voice_lead_progression_ga,
    _voicing_transition_cost,
    build_chords,
)

_SAMPLE_CHORDS = list(VOICING_OPTIONS.keys())[:2]


def test_identical_voicing_has_zero_cost():
    assert _voicing_transition_cost([57, 60, 64, 67], [57, 60, 64, 67]) == 0.0


def test_parallel_fifths_penalty_fires():
    cost = _voicing_transition_cost([50, 57], [52, 59])
    assert cost >= 8.0


def test_tight_spacing_penalty_fires_even_at_zero_displacement():
    cost = _voicing_transition_cost([60, 61], [60, 61])
    assert cost == 6.0


def test_enumerate_shift_options_only_yields_ascending_variants():
    options = _enumerate_shift_options([60, 64, 67])
    assert all(v == sorted(v) for v in options)
    assert [60, 64, 67] in options


def test_ga_returns_valid_ascending_voicings_for_each_chord():
    random.seed(0)
    progression = [(_SAMPLE_CHORDS[0], 2), (_SAMPLE_CHORDS[1], 2)]
    result = _voice_lead_progression_ga(progression, pop_size=8, generations=5)
    assert len(result) == 2
    assert all(v == sorted(v) for v in result)


def test_ga_beats_a_random_chromosome():
    random.seed(1)
    progression = [(_SAMPLE_CHORDS[0], 2), (_SAMPLE_CHORDS[1], 2)]
    result = _voice_lead_progression_ga(progression, pop_size=8, generations=10)
    ga_cost = _voicing_transition_cost(result[0], result[1])

    worse_costs = []
    for _ in range(10):
        a = random.choice(VOICING_OPTIONS.get(_SAMPLE_CHORDS[0], [[60, 64, 67]]))
        b = random.choice(VOICING_OPTIONS.get(_SAMPLE_CHORDS[1], [[60, 64, 67]]))
        worse_costs.append(_voicing_transition_cost(a, b))
    assert ga_cost <= max(worse_costs)


def test_ga_handles_unknown_chord_name_without_raising():
    progression = [('XYZ9', 2), (_SAMPLE_CHORDS[0], 2)]
    result = _voice_lead_progression_ga(progression, pop_size=8, generations=5)
    assert len(result) == 2


# ── build_chords() integration (v1-specific: always-on, not probability-gated) ──

def test_build_chords_uses_progression_wide_voice_leading():
    # Spy on _voice_lead_progression_best to confirm build_chords() calls it
    # once, on the FULL flattened (num_loops * len(progression)) resolved
    # sequence -- not per-chord.
    calls = []
    real_best = gmg._voice_lead_progression_best

    def spy_best(resolved, *a, **kw):
        calls.append(list(resolved))
        return real_best(resolved, *a, **kw)

    import unittest.mock as mock
    with mock.patch.object(gmg, "_voice_lead_progression_best", spy_best):
        progression = [(_SAMPLE_CHORDS[0], 2), (_SAMPLE_CHORDS[1], 2)]
        events = build_chords(progression, start_bar=0, num_loops=3, swing=0.5, bpm=80)

    assert len(calls) == 1
    assert len(calls[0]) == 3 * len(progression)   # flattened across all num_loops
    assert events


def test_build_chords_falls_back_on_ga_failure(monkeypatch):
    # If the whole-progression optimizer raises for any reason, build_chords()
    # must still produce valid events via the greedy _voice_lead_choice()
    # fallback rather than propagating the exception (this must never block
    # a render).
    def boom(*a, **kw):
        raise RuntimeError("simulated optimizer failure")

    monkeypatch.setattr(gmg, "_voice_lead_progression_best", boom)
    progression = [(_SAMPLE_CHORDS[0], 2), (_SAMPLE_CHORDS[1], 2)]
    events = build_chords(progression, start_bar=0, num_loops=2, swing=0.5, bpm=80)
    assert events
    assert all(len(e) == 4 for e in events)   # (t, note, vel, dur) shape preserved


def test_build_chords_output_unaffected_by_optimizer_choice_of_winner():
    # Whichever of GA/annealing wins internally, build_chords()'s output
    # shape/length contract must hold regardless.
    progression = [(_SAMPLE_CHORDS[0], 1), (_SAMPLE_CHORDS[1], 1)]
    events = build_chords(progression, start_bar=0, num_loops=1, swing=0.55, bpm=90, tension=0.9)
    assert events
    assert all(isinstance(e[0], int) and isinstance(e[1], int) for e in events)
