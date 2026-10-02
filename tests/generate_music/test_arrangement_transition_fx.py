"""
Tests for research/theory/arrangement-structure.md's remaining "Concrete
additions" table entries -- everything EXCEPT the aaba/build song forms and
_FORM_BY_SUBGENRE mappings (already implemented, confirmed present:
_SONG_FORMS['aaba']/['build'], bossa_lofi/lofi_drill/lofi_phonk already
mapped, jazz_cafe fixed this session) and the per-section texture-density
variation (already effectively implemented via build_texture()'s tension-
weighted `0.35 + 0.40 * sec_tension` probability -- a continuous,
tension-driven density that supersedes the research doc's flat-50%-per-
track framing, which was already stale by the time this session read it).

Covers what was genuinely still missing: _SECTION_TRANSITION_FX and the 3
audio-domain transition effects (vinyl stop / reverse riser / filter
sweep) in scripts/lofi_fx.py.
"""
import random

import mido
import numpy as np
import pytest

import scripts.composer as gmg
from scripts.composer import (
    _compute_section_transitions,
    _SECTION_TRANSITION_FX,
    _SONG_FORMS,
    section_transition_fx_for,
)
from scripts.lofi_fx import (
    _apply_filter_sweep,
    _apply_reverse_riser,
    _apply_vinyl_stop,
)


def _stereo(n=44100 * 3, sr=44100, seed=0):
    rng = np.random.default_rng(seed)
    tone = rng.standard_normal(n).astype(np.float32) * 0.2
    return np.stack([tone, tone]), sr


# ── _SECTION_TRANSITION_FX lookup ───────────────────────────────────────────

def test_transition_fx_table_only_uses_real_labels():
    valid_labels = {"I", "A", "BR", "B", "O"}
    for (frm, to) in _SECTION_TRANSITION_FX:
        assert frm in valid_labels
        assert to in valid_labels


def test_section_transition_fx_for_known_pairs():
    assert section_transition_fx_for("A", "BR") == "filter_lowpass_sweep"
    assert section_transition_fx_for("BR", "A") == "vinyl_stop"


def test_section_transition_fx_for_unknown_pair_returns_none():
    assert section_transition_fx_for("I", "O") is None


# ── vinyl stop ───────────────────────────────────────────────────────────────

def test_vinyl_stop_preserves_shape_dtype_and_no_nan():
    stereo, sr = _stereo()
    at = int(sr * 2)
    result = _apply_vinyl_stop(stereo, sr, at)
    assert result.shape == stereo.shape
    assert result.dtype == np.float32
    assert not np.isnan(result).any()


def test_vinyl_stop_leaves_audio_at_and_after_boundary_untouched():
    stereo, sr = _stereo()
    at = int(sr * 2)
    result = _apply_vinyl_stop(stereo, sr, at, duration_s=0.6)
    assert np.array_equal(result[:, at:], stereo[:, at:])


def test_vinyl_stop_fades_toward_silence_right_before_boundary():
    stereo, sr = _stereo()
    at = int(sr * 2)
    result = _apply_vinyl_stop(stereo, sr, at, duration_s=0.6)
    # The last few samples before the boundary should be much quieter than
    # the original signal there (needle-lift fade).
    tail_before = np.abs(result[0, at - 50:at])
    original_tail = np.abs(stereo[0, at - 50:at])
    assert tail_before.mean() < original_tail.mean()


def test_vinyl_stop_too_short_input_is_safe_passthrough():
    stereo, sr = _stereo(n=2)
    result = _apply_vinyl_stop(stereo, sr, at_sample=1)
    assert result.shape == stereo.shape


# ── reverse riser ────────────────────────────────────────────────────────────

def test_reverse_riser_preserves_shape_dtype_and_no_nan():
    stereo, sr = _stereo()
    at = int(sr * 2)
    result = _apply_reverse_riser(stereo, sr, at)
    assert result.shape == stereo.shape
    assert result.dtype == np.float32
    assert not np.isnan(result).any()


def test_reverse_riser_builds_toward_the_boundary():
    stereo, sr = _stereo()
    at = int(sr * 2)
    result = _apply_reverse_riser(stereo, sr, at, duration_s=1.0, amplitude=0.5)
    win_start = at - int(sr * 1.0)
    added = np.abs(result[0, win_start:at] - stereo[0, win_start:at])
    early = added[: len(added) // 4].mean()
    late = added[-len(added) // 4:].mean()
    assert late > early   # amplitude ramps up toward the transition point


def test_reverse_riser_leaves_audio_after_boundary_untouched():
    stereo, sr = _stereo()
    at = int(sr * 2)
    result = _apply_reverse_riser(stereo, sr, at, duration_s=1.0)
    assert np.array_equal(result[:, at:], stereo[:, at:])


# ── filter sweep ─────────────────────────────────────────────────────────────

def test_filter_sweep_preserves_shape_dtype_and_no_nan():
    stereo, sr = _stereo()
    at = int(sr * 2)
    result = _apply_filter_sweep(stereo, sr, at)
    assert result.shape == stereo.shape
    assert result.dtype == np.float32
    assert not np.isnan(result).any()


def test_filter_sweep_down_reduces_high_frequency_energy_toward_boundary():
    # Broadband noise input, sweep 'down' -- energy above ~4kHz right before
    # the boundary should end up lower than at the start of the sweep
    # window (cutoff has moved from wide-open down toward 400Hz by then).
    rng = np.random.default_rng(1)
    n = 44100 * 3
    noise = rng.standard_normal(n).astype(np.float32) * 0.2
    stereo = np.stack([noise, noise])
    sr = 44100
    at = int(sr * 2)
    result = _apply_filter_sweep(stereo, sr, at, duration_s=1.5, direction="down")

    win_start = at - int(sr * 1.5)
    block = int(sr * 1.5) // 8

    def _high_freq_energy(x):
        spectrum = np.abs(np.fft.rfft(x))
        freqs = np.fft.rfftfreq(len(x), d=1.0 / sr)
        return float(np.sum(spectrum[freqs > 4000] ** 2))

    early_energy = _high_freq_energy(result[0, win_start:win_start + block])
    late_energy = _high_freq_energy(result[0, at - block:at])
    assert late_energy < early_energy


def test_filter_sweep_leaves_audio_after_boundary_untouched():
    stereo, sr = _stereo()
    at = int(sr * 2)
    result = _apply_filter_sweep(stereo, sr, at, duration_s=1.5)
    assert np.array_equal(result[:, at:], stereo[:, at:])


def test_filter_sweep_too_short_window_is_safe_passthrough():
    stereo, sr = _stereo(n=10)
    result = _apply_filter_sweep(stereo, sr, at_sample=5)
    assert result.shape == stereo.shape


# ── _compute_section_transitions (build_midi()'s wiring point) ─────────────
# The pure bar->sample computation build_midi() calls once per track (see
# its own comment there): fixed given `form`+`bpm`, independent of the
# per-attempt randomness in build_midi()'s quality-gate retry loop.

def test_build_form_alternates_sweep_and_vinyl_stop_at_expected_bars():
    # 'build' = [('I',1),('A',3),('BR',1),('A',3),('BR',1),('A',3),('O',1)];
    # hand-traced boundaries at prog_bars=4: I->A (no fx), A->BR@16 (sweep),
    # BR->A@20 (vinyl_stop), A->BR@32 (sweep), BR->A@36 (vinyl_stop),
    # A->O@48 (no fx defined for that pair).
    result = _compute_section_transitions(_SONG_FORMS['build'], prog_bars=4, bpm=80)
    bar_seconds = 240.0 / 80
    expected_bars = [16, 20, 32, 36]
    expected_fx   = ['filter_lowpass_sweep', 'vinyl_stop', 'filter_lowpass_sweep', 'vinyl_stop']
    assert [fx for _, fx in result] == expected_fx
    assert [pos for pos, _ in result] == [int(b * bar_seconds * 44100) for b in expected_bars]


def test_standard_form_transitions_at_expected_bars():
    # 'standard' = [('I',1),('A',4),('BR',1),('B',4),('O',1)]; boundaries at
    # prog_bars=4: I->A (no fx), A->BR@20 (sweep), BR->B@24 (reverse_riser),
    # B->O@40 (sweep).
    result = _compute_section_transitions(_SONG_FORMS['standard'], prog_bars=4, bpm=80)
    assert [fx for _, fx in result] == [
        'filter_lowpass_sweep', 'reverse_riser', 'filter_lowpass_sweep',
    ]


def test_single_section_form_has_no_boundaries():
    assert _compute_section_transitions([('A', 4)], prog_bars=4, bpm=80) == []


def test_form_with_no_defined_transition_pairs_is_empty():
    # I->O has no entry in _SECTION_TRANSITION_FX.
    assert _compute_section_transitions([('I', 1), ('O', 1)], prog_bars=4, bpm=80) == []


def test_higher_bpm_yields_proportionally_earlier_sample_positions():
    slow = _compute_section_transitions(_SONG_FORMS['build'], prog_bars=4, bpm=80)
    fast = _compute_section_transitions(_SONG_FORMS['build'], prog_bars=4, bpm=160)
    assert [fx for _, fx in slow] == [fx for _, fx in fast]
    for (pos_slow, _), (pos_fast, _) in zip(slow, fast):
        assert pos_fast == pytest.approx(pos_slow / 2, rel=1e-6)


def test_custom_sr_scales_sample_positions_linearly():
    at_44k = _compute_section_transitions(_SONG_FORMS['build'], prog_bars=4, bpm=80, sr=44100)
    at_48k = _compute_section_transitions(_SONG_FORMS['build'], prog_bars=4, bpm=80, sr=48000)
    for (pos_44k, _), (pos_48k, _) in zip(at_44k, at_48k):
        assert pos_48k == pytest.approx(pos_44k * (48000 / 44100), rel=1e-6)


def test_all_returned_fx_names_are_real_lofi_fx_functions():
    valid_names = set(_SECTION_TRANSITION_FX.values())
    for form_name in ('standard', 'aaba', 'build'):
        for _, fx in _compute_section_transitions(_SONG_FORMS[form_name], prog_bars=4, bpm=80):
            assert fx in valid_names


# ── build_midi() end-to-end: the actual return-value wiring ────────────────

@pytest.fixture
def _isolated_music_dir(tmp_path, monkeypatch):
    """build_midi() writes to music/.params_history.json etc. as a side
    effect -- redirect to tmp_path (mirrors test_build_midi_integration.py's
    isolated_music_dir fixture) so this never touches real project state."""
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    monkeypatch.setattr(gmg, "MUSIC_DIR", str(music_dir))
    monkeypatch.setattr(gmg, "_PARAMS_HISTORY_FILE", str(music_dir / ".params_history.json"))
    monkeypatch.setattr(gmg, "_MELODY_HISTORY_FILE", str(music_dir / ".melody_history.json"))
    monkeypatch.setattr(gmg, "_RECIPE_LOG_FILE", str(music_dir / ".recipe_log.jsonl"))
    return music_dir


def test_build_midi_returns_path_and_section_transitions(_isolated_music_dir, tmp_path):
    random.seed(0)
    params = gmg.pick_params(genre_hint='lofi_drill')   # 'build' form, has real transitions
    out_path = tmp_path / 'drill.mid'

    result = gmg.build_midi(params, str(out_path))

    assert isinstance(result, tuple) and len(result) == 2
    path, transitions = result
    assert path == str(out_path)
    assert isinstance(transitions, list)
    valid_names = set(_SECTION_TRANSITION_FX.values())
    for entry in transitions:
        assert isinstance(entry, tuple) and len(entry) == 2
        pos, fx = entry
        assert isinstance(pos, int) and pos >= 0
        assert fx in valid_names
    mido.MidiFile(str(out_path))   # the primary return value must still be a valid path


def test_build_midi_transitions_fire_across_a_seeded_sweep(_isolated_music_dir, tmp_path):
    # lofi_drill's hand-authored form ('build') always has 4 real
    # transitions UNLESS build_midi()'s ~25% generative-form-grammar branch
    # overrides form_name for that attempt -- sweep seeds so both paths get
    # exercised, and assert the non-generative case is never silently empty.
    saw_nonempty = False
    for seed in range(15):
        random.seed(seed)
        params = gmg.pick_params(genre_hint='lofi_drill')
        _, transitions = gmg.build_midi(params, str(tmp_path / f'drill_{seed}.mid'))
        if transitions:
            saw_nonempty = True
    assert saw_nonempty, "no seed in the sweep produced a non-empty section_transitions list"
