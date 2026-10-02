"""
Tests for the cellular-automaton rhythm generator (Stage 3 item 4):
Wolfram elementary-CA-driven drum pattern generation, an additional
procedural rhythm source alongside the existing Bjorklund/Euclidean
generator (see tests/generate_music/test_euclidean.py for the sibling
tests).
"""

import pytest

from scripts.composer import (
    CHH,
    KICK,
    OHH,
    RIM,
    SNARE,
    _CA_RULE_POOL,
    _ca_evolve,
    _ca_step,
    generate_ca_drum_pattern,
)

_DRUM_KEYS = {KICK, SNARE, CHH, OHH, RIM}


# ── _ca_step / _ca_evolve: elementary CA mechanics ────────────────────────────

def test_rule_90_is_xor_of_neighbors():
    # Rule 90 is the textbook "next = left XOR right" elementary CA rule.
    row = [0, 1, 0, 1, 1, 0, 0, 0]
    nxt = _ca_step(90, row)
    n = len(row)
    expected = [row[(i - 1) % n] ^ row[(i + 1) % n] for i in range(n)]
    assert nxt == expected


def test_rule_0_produces_all_zero_next_generation():
    row = [1, 0, 1, 1, 0, 1, 0, 0]
    assert _ca_step(0, row) == [0] * len(row)


def test_rule_255_produces_all_one_next_generation():
    row = [0, 0, 0, 0, 0, 0, 0, 0]
    assert _ca_step(255, row) == [1] * len(row)


def test_ca_step_wraps_around_circularly():
    # A single 1 at the edge must be able to influence the wrap-around
    # neighbor (index -1 / index n) — verifies circular, not fixed, boundary.
    row = [1, 0, 0, 0]
    nxt_rule150 = _ca_step(150, row)  # rule 150: next = left ^ mid ^ right
    n = len(row)
    expected = [row[(i - 1) % n] ^ row[i] ^ row[(i + 1) % n] for i in range(n)]
    assert nxt_rule150 == expected


def test_ca_evolve_zero_generations_returns_seed():
    result = _ca_evolve(30, width=16, generations=0)
    seed = [0] * 16
    seed[8] = 1
    assert result == seed


def test_ca_evolve_deterministic():
    a = _ca_evolve(30, width=16, generations=5)
    b = _ca_evolve(30, width=16, generations=5)
    assert a == b


def test_ca_evolve_respects_custom_seed_row():
    custom = [1, 1, 0, 0, 0, 0, 0, 0]
    result = _ca_evolve(90, width=8, generations=1, seed_row=custom)
    expected = _ca_step(90, custom)
    assert result == expected


# ── generate_ca_drum_pattern ───────────────────────────────────────────────────

def test_pattern_has_expected_keys_and_shape():
    pat = generate_ca_drum_pattern(energy=0.5, complexity=0.5, seed=1)
    assert set(pat.keys()) == _DRUM_KEYS
    for onsets in pat.values():
        assert len(onsets) == 16
        assert all(0 <= v <= 127 for v in onsets)


def test_pattern_deterministic_for_same_seed():
    p1 = generate_ca_drum_pattern(0.5, 0.5, seed=1)
    p2 = generate_ca_drum_pattern(0.5, 0.5, seed=1)
    assert p1 == p2


def test_pattern_varies_across_seeds():
    patterns = {tuple(generate_ca_drum_pattern(0.5, 0.5, seed=s)[KICK]) for s in range(10)}
    assert len(patterns) > 1


@pytest.mark.parametrize("rule", list(_CA_RULE_POOL))
def test_pattern_never_fully_silent_for_any_pool_rule(rule):
    # Some elementary CA rules die out to a fixed point (all-zero) for
    # certain generation counts -- the degenerate-output fallback must catch
    # every rule in the pool, across a range of complexity values.
    for complexity in (0.0, 0.3, 0.5, 0.7, 1.0):
        pat = generate_ca_drum_pattern(energy=0.5, complexity=complexity, rule=rule, seed=1)
        assert any(v > 0 for v in pat[KICK]), f"rule={rule} complexity={complexity} kick fully silent"
        assert any(v > 0 for v in pat[CHH]), f"rule={rule} complexity={complexity} hats fully silent"


def test_higher_energy_gives_louder_or_equal_kick_accents():
    lo = generate_ca_drum_pattern(energy=0.0, complexity=0.5, rule=30, seed=1)
    hi = generate_ca_drum_pattern(energy=1.0, complexity=0.5, rule=30, seed=1)
    lo_peak = max(lo[KICK]) if any(lo[KICK]) else 0
    hi_peak = max(hi[KICK]) if any(hi[KICK]) else 0
    assert hi_peak >= lo_peak


def test_default_rule_is_chosen_from_pool_when_unspecified():
    # rule=None (default) should pick from _CA_RULE_POOL rather than fail or
    # silently no-op.
    pat = generate_ca_drum_pattern(energy=0.5, complexity=0.5, seed=2)
    assert set(pat.keys()) == _DRUM_KEYS


def test_energy_and_complexity_are_clamped_to_unit_range():
    # Out-of-range inputs must not raise or produce a broken shape.
    pat = generate_ca_drum_pattern(energy=5.0, complexity=-3.0, rule=30, seed=1)
    assert set(pat.keys()) == _DRUM_KEYS
    for onsets in pat.values():
        assert len(onsets) == 16
