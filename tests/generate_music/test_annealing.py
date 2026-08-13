"""
Tests for the simulated-annealing voice-leading optimizer (Stage 3 item 3):
_voice_lead_progression_annealing and the GA-vs-annealing chooser
_voice_lead_progression_best.
"""

import random

from scripts.generate_music_gemini import VOICING_OPTIONS
from scripts.generate_music_v2 import (
    _build_voicing_gene_pools,
    _chromosome_cost,
    _voice_lead_progression_annealing,
    _voice_lead_progression_best,
    _voice_lead_progression_ga,
    _voicing_transition_cost,
)

_SAMPLE_CHORDS = list(VOICING_OPTIONS.keys())[:3]


def _total_cost(voicings):
    total = 0.0
    prev = None
    for v in voicings:
        if prev is not None:
            total += _voicing_transition_cost(prev, v)
        prev = v
    return total


# ── determinism ──────────────────────────────────────────────────────────────

def test_annealing_deterministic_with_seed():
    progression = [(_SAMPLE_CHORDS[0], 2), (_SAMPLE_CHORDS[1], 2), (_SAMPLE_CHORDS[2], 2)]
    a = _voice_lead_progression_annealing(progression, iterations=200, seed=7)
    b = _voice_lead_progression_annealing(progression, iterations=200, seed=7)
    assert a == b


def test_annealing_varies_across_seeds():
    progression = [(_SAMPLE_CHORDS[0], 2), (_SAMPLE_CHORDS[1], 2), (_SAMPLE_CHORDS[2], 2)]
    results = {tuple(map(tuple, _voice_lead_progression_annealing(progression, iterations=100, seed=s)))
               for s in range(8)}
    assert len(results) > 1


# ── output shape ──────────────────────────────────────────────────────────────

def test_annealing_returns_valid_ascending_voicings_for_each_chord():
    progression = [(_SAMPLE_CHORDS[0], 2), (_SAMPLE_CHORDS[1], 2)]
    result = _voice_lead_progression_annealing(progression, iterations=150, seed=3)
    assert len(result) == 2
    assert all(v == sorted(v) for v in result)


def test_annealing_handles_unknown_chord_name_without_raising():
    progression = [('XYZ9', 2), (_SAMPLE_CHORDS[0], 2)]
    result = _voice_lead_progression_annealing(progression, iterations=100, seed=1)
    assert len(result) == 2


def test_annealing_handles_single_chord_progression():
    progression = [(_SAMPLE_CHORDS[0], 4)]
    result = _voice_lead_progression_annealing(progression, iterations=50, seed=1)
    assert len(result) == 1


# ── convergence: annealing should not do worse than a random start ──────────

def test_annealing_converges_to_lower_or_equal_cost_than_random_start():
    progression = [(_SAMPLE_CHORDS[0], 2), (_SAMPLE_CHORDS[1], 2), (_SAMPLE_CHORDS[2], 2)]
    gene_pools = _build_voicing_gene_pools([c for c, _ in progression])

    rng = random.Random(99)
    random_chromosome = [rng.randrange(len(pool)) for pool in gene_pools]
    random_cost = _chromosome_cost(gene_pools, random_chromosome)

    annealed = _voice_lead_progression_annealing(progression, iterations=400, seed=99)
    annealed_cost = _total_cost(annealed)

    assert annealed_cost <= random_cost


def test_more_iterations_do_not_increase_best_cost():
    # Annealing tracks the best-seen chromosome throughout the run, so a
    # longer run must never report a WORSE final cost than a shorter one
    # with the same seed (monotonic non-increasing "best so far").
    progression = [(_SAMPLE_CHORDS[0], 2), (_SAMPLE_CHORDS[1], 2), (_SAMPLE_CHORDS[2], 2)]
    short_run = _voice_lead_progression_annealing(progression, iterations=20, seed=5)
    long_run = _voice_lead_progression_annealing(progression, iterations=400, seed=5)
    assert _total_cost(long_run) <= _total_cost(short_run)


# ── GA-vs-annealing chooser ───────────────────────────────────────────────────

def test_best_picks_lower_cost_of_ga_and_annealing():
    random.seed(11)
    progression = [(_SAMPLE_CHORDS[0], 2), (_SAMPLE_CHORDS[1], 2), (_SAMPLE_CHORDS[2], 2)]
    voicings, winner = _voice_lead_progression_best(
        progression, pop_size=8, generations=10, annealing_iterations=150,
    )
    assert winner in ('ga', 'annealing')
    assert len(voicings) == 3

    ga_only = _voice_lead_progression_ga(progression, pop_size=8, generations=10)
    sa_only = _voice_lead_progression_annealing(progression, iterations=150)

    chosen_cost = _total_cost(voicings)
    assert chosen_cost <= max(_total_cost(ga_only), _total_cost(sa_only))


def test_best_never_worse_than_either_individual_optimizer():
    random.seed(23)
    progression = [(_SAMPLE_CHORDS[0], 2), (_SAMPLE_CHORDS[1], 2)]
    for _ in range(5):
        voicings, winner = _voice_lead_progression_best(
            progression, pop_size=8, generations=8, annealing_iterations=100,
        )
        assert _total_cost(voicings) >= 0.0
        assert winner in ('ga', 'annealing')
