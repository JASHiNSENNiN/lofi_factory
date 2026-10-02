"""
Tests for the new 3-against-4 cross-rhythm generator
(generate_polyrhythm_pattern) -- research/theory/rhythm-groove.md's finding
that a true independent-pulse-train cross-rhythm wasn't represented by the
existing Euclidean/CA generators (which fold everything into one 16-step
additive grouping). This technique isn't in the theory doc; it's gated to lofi_world/nujabes in
pick_params() rather than offered to every genre.
"""

from scripts.composer import (
    CHH,
    KICK,
    OHH,
    RIM,
    SNARE,
    generate_polyrhythm_pattern,
)


def test_returns_full_pattern_shape():
    pattern = generate_polyrhythm_pattern(energy=0.5, seed=1)
    for voice in (KICK, SNARE, CHH, OHH, RIM):
        assert voice in pattern
        assert len(pattern[voice]) == 16


def test_kick_lands_on_the_four_pulse_grid():
    pattern = generate_polyrhythm_pattern(energy=0.5, ratio=(3, 4), seed=2)
    kick_onsets = [i for i, v in enumerate(pattern[KICK]) if v > 0]
    assert kick_onsets == [0, 4, 8, 12]


def test_hat_follows_independent_three_pulse_cycle():
    pattern = generate_polyrhythm_pattern(energy=0.5, ratio=(3, 4), seed=3)
    hat_onsets = [i for i, v in enumerate(pattern[CHH]) if v > 0]
    assert len(hat_onsets) == 3
    # A true 3-pulse cycle over 16 steps must NOT land on the same 4 steps
    # (0,4,8,12) the kick's 4-pulse cycle uses -- that's the entire point of
    # a cross-rhythm (independent pulse trains, not the same grid twice).
    assert set(hat_onsets) != {0, 4, 8, 12}


def test_different_ratio_produces_different_hat_count():
    p34 = generate_polyrhythm_pattern(energy=0.5, ratio=(3, 4), seed=4)
    p54 = generate_polyrhythm_pattern(energy=0.5, ratio=(5, 4), seed=4)
    hats_34 = sum(1 for v in p34[CHH] if v > 0)
    hats_54 = sum(1 for v in p54[CHH] if v > 0)
    assert hats_34 == 3
    assert hats_54 == 5


def test_deterministic_with_seed():
    a = generate_polyrhythm_pattern(energy=0.6, seed=42)
    b = generate_polyrhythm_pattern(energy=0.6, seed=42)
    assert a == b


def test_energy_affects_kick_velocity():
    low = generate_polyrhythm_pattern(energy=0.1, seed=5)
    high = generate_polyrhythm_pattern(energy=0.9, seed=5)
    low_peak = max(low[KICK])
    high_peak = max(high[KICK])
    assert high_peak > low_peak


def test_velocities_are_valid_midi_range():
    pattern = generate_polyrhythm_pattern(energy=0.7, seed=6)
    for voice_vels in pattern.values():
        for v in voice_vels:
            assert 0 <= v <= 127
