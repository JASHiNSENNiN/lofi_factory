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
import numpy as np
import pytest

from scripts.generate_music_gemini import (
    _SECTION_TRANSITION_FX,
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
