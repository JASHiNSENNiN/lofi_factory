"""
Tests for the L-system melodic phrase generator ported into v1
(composer.py) from v2's Stage-3 work: _lsystem_expand,
_lsystem_to_pitches, generate_lsystem_motif. Mirrors test_lsystem.py's
coverage (which tests the original v2 versions) against the new v1
locations -- v1's generate_lsystem_motif returns a plain pitch list
(matching generate_motif()'s own convention) rather than v2's Motif
wrapper, so those specific assertions are adapted; _lsystem_expand/
_lsystem_to_pitches are pure and byte-identical to v2's, so those tests are
copied as-is with a new import.
"""

from scripts.composer import (
    _lsystem_expand,
    _lsystem_to_pitches,
    _LSYSTEM_PRESETS,
    generate_lsystem_motif,
)

_SCALE = list(range(60, 73))   # 13-note chromatic-ish stand-in scale


# ── _lsystem_expand ────────────────────────────────────────────────────────────

def test_expand_zero_iterations_returns_axiom():
    assert _lsystem_expand('U', {'U': 'UDU'}, iterations=0) == 'U'


def test_expand_grows_with_iterations():
    rules = {'U': 'UDU', 'D': 'DUD'}
    gen0 = _lsystem_expand('U', rules, 0, max_len=1000)
    gen1 = _lsystem_expand('U', rules, 1, max_len=1000)
    gen2 = _lsystem_expand('U', rules, 2, max_len=1000)
    assert len(gen0) < len(gen1) < len(gen2)
    assert gen1 == 'UDU'


def test_expand_respects_max_len_bound():
    rules = {'U': 'UDU', 'D': 'DUD'}
    result = _lsystem_expand('U', rules, iterations=20, max_len=30)
    assert len(result) <= 30


def test_expand_is_deterministic():
    rules = {'U': 'UDU', 'D': 'DUD'}
    a = _lsystem_expand('U', rules, 4, max_len=100)
    b = _lsystem_expand('U', rules, 4, max_len=100)
    assert a == b


def test_all_presets_expand_without_error_and_stay_bounded():
    for axiom, rules in _LSYSTEM_PRESETS:
        result = _lsystem_expand(axiom, rules, iterations=6, max_len=200)
        assert 0 < len(result) <= 200


# ── _lsystem_to_pitches ────────────────────────────────────────────────────────

def test_step_up_and_down_move_scale_degree():
    pitches = _lsystem_to_pitches('UU', _SCALE, start_idx=0)
    assert pitches == [_SCALE[1], _SCALE[2]]

    pitches_down = _lsystem_to_pitches('DD', _SCALE, start_idx=5)
    assert pitches_down == [_SCALE[4], _SCALE[3]]


def test_step_up_clamps_at_top_of_scale():
    pitches = _lsystem_to_pitches('UUU', _SCALE, start_idx=len(_SCALE) - 1)
    assert all(p == _SCALE[-1] for p in pitches)


def test_step_down_clamps_at_bottom_of_scale():
    pitches = _lsystem_to_pitches('DDD', _SCALE, start_idx=0)
    assert all(p == _SCALE[0] for p in pitches)


def test_sustain_repeats_current_pitch():
    pitches = _lsystem_to_pitches('USS', _SCALE, start_idx=0)
    assert pitches == [_SCALE[1], _SCALE[1], _SCALE[1]]


def test_transpose_toggles_octave():
    pitches = _lsystem_to_pitches('TT', _SCALE, start_idx=0)
    assert pitches[0] == _SCALE[0] + 12
    assert pitches[1] == _SCALE[0]   # toggled back


def test_push_pop_restores_cursor_state():
    pitches = _lsystem_to_pitches('U[DD]U', _SCALE, start_idx=5)
    assert pitches[0] == _SCALE[6]
    assert pitches[1] == _SCALE[5]
    assert pitches[2] == _SCALE[4]
    assert pitches[3] == _SCALE[7]


def test_non_melodic_symbols_are_ignored():
    pitches = _lsystem_to_pitches('UxU', _SCALE, start_idx=0)
    assert len(pitches) == 2


def test_empty_scale_returns_empty():
    assert _lsystem_to_pitches('UUU', [], start_idx=0) == []


# ── generate_lsystem_motif (v1: returns a plain pitch list) ─────────────────────

def test_returns_plain_pitch_list_not_wrapped():
    m = generate_lsystem_motif(_SCALE, length=6, seed=1)
    assert isinstance(m, list)
    assert m
    assert all(isinstance(p, int) for p in m)


def test_deterministic_with_seed():
    a = generate_lsystem_motif(_SCALE, length=8, seed=42)
    b = generate_lsystem_motif(_SCALE, length=8, seed=42)
    assert a == b


def test_varies_across_seeds():
    results = {tuple(generate_lsystem_motif(_SCALE, length=8, seed=s)) for s in range(10)}
    assert len(results) > 1


def test_output_length_is_bounded():
    for seed in range(10):
        m = generate_lsystem_motif(_SCALE, length=8, seed=seed)
        assert 1 <= len(m) <= 8


def test_all_pitches_are_scale_tones_within_an_octave():
    scale_pcs = {p % 12 for p in _SCALE}
    for seed in range(15):
        m = generate_lsystem_motif(_SCALE, length=10, seed=seed)
        assert all(p % 12 in scale_pcs for p in m)


def test_empty_scale_returns_empty_list():
    assert generate_lsystem_motif([], length=4, seed=1) == []
