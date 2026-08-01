import random
from unittest.mock import patch

from scripts.generate_music_gemini import VOICING_OPTIONS
from scripts.generate_music_v2 import (
    _enumerate_shift_options,
    _voice_lead_progression_ga,
    _voicing_transition_cost,
    build_chords_v2,
)

_SAMPLE_CHORDS = list(VOICING_OPTIONS.keys())[:2]


def test_identical_voicing_has_zero_cost():
    assert _voicing_transition_cost([57, 60, 64, 67], [57, 60, 64, 67]) == 0.0


def test_parallel_fifths_penalty_fires():
    # prev is a perfect 5th (50,57); shifted moves both voices up 2 semitones
    # in the same direction, landing on another perfect 5th (52,59).
    cost = _voicing_transition_cost([50, 57], [52, 59])
    assert cost >= 8.0


def test_tight_spacing_penalty_fires_even_at_zero_displacement():
    cost = _voicing_transition_cost([60, 61], [60, 61])
    assert cost == 3.0  # (3 - 1) * 1.5, no displacement/parallel/contrary terms


def test_enumerate_shift_options_only_yields_ascending_variants():
    options = _enumerate_shift_options([60, 64, 67])
    assert all(v == sorted(v) for v in options)
    assert [60, 64, 67] in options  # zero-shift identity is always valid


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

    # A handful of purely random voicing choices from the actual options, for
    # comparison -- the GA shouldn't do worse than an arbitrary pick.
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


def test_build_chords_v2_ga_branch_is_reachable():
    # Force the 15% GA-voicing branch to fire and confirm it actually runs
    # end-to-end without crashing -- not just unit-tested in isolation.
    progression = [(_SAMPLE_CHORDS[0], 2), (_SAMPLE_CHORDS[1], 2)]
    ga_flag: list = []
    with patch('random.random', return_value=0.0):
        events = build_chords_v2(
            progression, start_bar=0, num_loops=1, swing=0.0, bpm=80, ga_flag=ga_flag,
        )
    assert ga_flag == [True]
    assert events
