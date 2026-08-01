import pytest

from scripts.generate_music_gemini import (
    CHH,
    KICK,
    OHH,
    RIM,
    SNARE,
    _bjorklund,
    generate_euclidean_drum_pattern,
)

# ── _bjorklund: actual verified outputs ──────────────────────────────────────
# NOTE: this is a leveling/accumulator Euclidean-rhythm construction (not the
# textbook recursive Bjorklund algorithm), rotated so the first onset lands on
# step 0. Its E(3,8) is NOT the commonly-cited tresillo rotation
# [1,0,0,1,0,0,1,0] -- both are valid maximally-even rotations of the same gap
# sequence, but only the one actually produced by this code is asserted here.

@pytest.mark.parametrize("k,n,expected", [
    (3, 8, [1, 0, 0, 1, 0, 1, 0, 0]),
    (5, 8, [1, 0, 1, 1, 0, 1, 1, 0]),
    (3, 16, [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0]),
    (5, 16, [1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0]),
    (2, 16, [1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0]),
    (7, 16, [1, 0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0, 1, 0, 0]),
    (4, 4, [1, 1, 1, 1]),
    (0, 8, [0] * 8),
    (8, 8, [1] * 8),
])
def test_bjorklund_known_outputs(k, n, expected):
    assert _bjorklund(k, n) == expected


@pytest.mark.parametrize("k,n", [(3, 8), (5, 8), (3, 16), (5, 16), (4, 4), (2, 16), (7, 16)])
def test_bjorklund_onset_count_matches_k(k, n):
    assert sum(_bjorklund(k, n)) == k


def test_bjorklund_copies_agree():
    soundfile = pytest.importorskip("soundfile")
    from scripts.drum_sampler import _bjorklund as bj2

    for k, n in [(3, 8), (5, 8), (3, 16), (5, 16), (2, 16), (7, 16)]:
        assert _bjorklund(k, n) == bj2(k, n)


# ── generate_euclidean_drum_pattern ──────────────────────────────────────────

_DRUM_KEYS = {KICK, SNARE, CHH, OHH, RIM}


def test_pattern_has_expected_keys_and_shape():
    pat = generate_euclidean_drum_pattern(energy=0.5, complexity=0.5, seed=1)
    assert set(pat.keys()) == _DRUM_KEYS
    for onsets in pat.values():
        assert len(onsets) == 16
        assert all(0 <= v <= 127 for v in onsets)


def test_pattern_deterministic_for_same_seed():
    p1 = generate_euclidean_drum_pattern(0.5, 0.5, seed=1)
    p2 = generate_euclidean_drum_pattern(0.5, 0.5, seed=1)
    assert p1 == p2


def test_higher_energy_has_at_least_as_many_kicks():
    lo = generate_euclidean_drum_pattern(energy=0.0, complexity=0.5, seed=1)
    hi = generate_euclidean_drum_pattern(energy=1.0, complexity=0.5, seed=1)
    lo_kicks = sum(v > 0 for v in lo[KICK])
    hi_kicks = sum(v > 0 for v in hi[KICK])
    assert hi_kicks >= lo_kicks


def test_snare_hits_the_backbeat_across_seeds():
    for seed in range(10):
        pat = generate_euclidean_drum_pattern(energy=0.5, complexity=0.5, seed=seed)
        snare = pat[SNARE]
        assert snare[4] > 0 or snare[12] > 0, f"seed={seed} missed backbeat: {snare}"
