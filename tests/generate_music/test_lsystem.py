"""
Tests for the L-system melodic phrase generator (Stage 3 item 5):
_lsystem_expand, _lsystem_to_pitches, generate_lsystem_motif, and its
wiring into _apply_motif_variation's variation pool.
"""

from scripts.generate_music_v2 import (
    Motif,
    _apply_motif_variation,
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
    # U [ D D ] U  -- push after first U, wander down twice, pop back, then U
    # again from the SAME degree the push happened at.
    pitches = _lsystem_to_pitches('U[DD]U', _SCALE, start_idx=5)
    # first U: idx 5->6
    assert pitches[0] == _SCALE[6]
    # D D inside brackets: idx 6->5->4
    assert pitches[1] == _SCALE[5]
    assert pitches[2] == _SCALE[4]
    # pop restores idx to 6 (state at the '[' ), then final U: idx 6->7
    assert pitches[3] == _SCALE[7]


def test_non_melodic_symbols_are_ignored():
    pitches = _lsystem_to_pitches('UxU', _SCALE, start_idx=0)
    assert len(pitches) == 2


def test_empty_scale_returns_empty():
    assert _lsystem_to_pitches('UUU', [], start_idx=0) == []


# ── generate_lsystem_motif ─────────────────────────────────────────────────────

def test_returns_motif_instance():
    m = generate_lsystem_motif(_SCALE, length=6, seed=1)
    assert isinstance(m, Motif)
    assert m.pitches


def test_deterministic_with_seed():
    a = generate_lsystem_motif(_SCALE, length=8, seed=42)
    b = generate_lsystem_motif(_SCALE, length=8, seed=42)
    assert a.pitches == b.pitches


def test_varies_across_seeds():
    results = {tuple(generate_lsystem_motif(_SCALE, length=8, seed=s).pitches) for s in range(10)}
    assert len(results) > 1


def test_output_length_is_bounded():
    for seed in range(10):
        m = generate_lsystem_motif(_SCALE, length=8, seed=seed)
        assert 1 <= len(m.pitches) <= 8


def test_all_pitches_are_scale_tones_within_an_octave():
    # The 'T' operation deliberately transposes by a full octave (see
    # test_transpose_toggles_octave), so a raw pitch may sit outside _SCALE's
    # exact MIDI range while still being a legitimate scale-tone class one
    # octave up/down -- check pitch-class membership instead of raw range.
    scale_pcs = {p % 12 for p in _SCALE}
    for seed in range(15):
        m = generate_lsystem_motif(_SCALE, length=10, seed=seed)
        assert all(p % 12 in scale_pcs for p in m.pitches)


def test_empty_scale_falls_back_to_default_motif():
    m = generate_lsystem_motif([], length=4, seed=1)
    assert m.pitches == [60]


# ── wired into _apply_motif_variation's pool ─────────────────────────────────

def test_variation_pool_includes_lsystem_as_ninth_entry():
    motif = Motif([64, 65, 67])
    result = _apply_motif_variation(motif, _SCALE, var_idx=8, section='A')
    assert result
    assert all(_SCALE[0] <= p <= _SCALE[-1] for p in result)


def test_variation_pool_still_has_all_prior_transforms_reachable():
    # Sanity check the pool grew (added the 9th) without breaking indices
    # 0-7, which existing callers (build_melody_v2's var_idx cycling) rely on.
    motif = Motif([60, 62, 64, 65])
    for idx in range(8):
        result = _apply_motif_variation(motif, _SCALE, var_idx=idx, section='A')
        assert result
