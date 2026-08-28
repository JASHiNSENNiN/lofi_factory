"""
Tests for research/theory/rhythm-groove.md's remaining "Concrete additions"
table entries -- everything EXCEPT pattern Q (phonk hat-roll) and the
build_drums() gauss-jitter migration, both already implemented and
confirmed present (pattern Q exists at DRUM_PATTERNS index 16; build_drums
already uses _gauss_jitter/_gauss_velocity throughout).

Covers what was genuinely still missing: the dembow _EUCL_HATS preset and
rule 126 added to _CA_RULE_POOL.
"""

from scripts.generate_music_gemini import (
    DRUM_PATTERNS,
    _CA_RULE_POOL,
    _ca_step,
    _EUCL_HATS,
    generate_ca_drum_pattern,
)


def test_dembow_preset_exists_and_is_full_length():
    assert "dembow" in _EUCL_HATS
    assert len(_EUCL_HATS["dembow"]) == 16


def test_dembow_onsets_match_documented_positions():
    # research/theory/rhythm-groove.md: "kick-equivalent onsets on steps 0,
    # 6; snare-equivalent on steps 2, 8".
    onsets = [i for i, v in enumerate(_EUCL_HATS["dembow"]) if v]
    assert onsets == [0, 2, 6, 8]


def test_pattern_q_phonk_hat_roll_already_present():
    # 17 patterns (A-Q, 0-indexed) confirms Q exists -- regression guard
    # for the already-implemented item, not new work.
    assert len(DRUM_PATTERNS) >= 17


def test_ca_rule_pool_includes_rule_126():
    assert 126 in _CA_RULE_POOL
    # The 4 originally-implemented rules must still be present too --
    # additive, not a replacement.
    assert {30, 90, 110, 184}.issubset(set(_CA_RULE_POOL))


def test_rule_126_produces_a_valid_ca_generation():
    row = [0] * 16
    row[8] = 1
    result = _ca_step(126, row)
    assert len(result) == 16
    assert all(v in (0, 1) for v in result)


def test_ca_drum_pattern_can_select_rule_126():
    # Force selection of rule 126 explicitly and confirm the generator
    # still produces a valid, non-degenerate full pattern.
    pattern = generate_ca_drum_pattern(energy=0.6, complexity=0.5, rule=126, seed=1)
    assert any(pattern[k] for k in pattern)
