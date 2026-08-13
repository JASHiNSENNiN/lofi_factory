import numpy as np
import pytest

from scripts.lofi_fx import (
    _apply_kick_sidechain_duck,
    _apply_lufs_mastering,
    _apply_stereo_width,
    _apply_sub_bass_saturation,
    _kick_envelope,
    _SIDECHAIN_DUCK_GENRES,
    _TRACK_LUFS_TARGET,
)

pyln = pytest.importorskip("pyloudnorm")


def _independent_stereo(n=44100 * 2, sr=44100, seed=0):
    rng = np.random.default_rng(seed)
    left = rng.standard_normal(n).astype(np.float32) * 0.1
    right = rng.standard_normal(n).astype(np.float32) * 0.1
    return np.stack([left, right]), sr


def test_stereo_width_identity_at_width_one():
    stereo, _ = _independent_stereo()
    result = _apply_stereo_width(stereo, 1.0)
    assert np.allclose(result, stereo, atol=1e-5)


def test_stereo_width_mono_passthrough():
    mono = np.stack([np.zeros(1000, dtype=np.float32)])
    result = _apply_stereo_width(mono, 1.5)
    assert np.array_equal(result, mono)


def test_stereo_width_scales_side_signal_by_width_factor():
    stereo, _ = _independent_stereo()
    left, right = stereo[0], stereo[1]
    side_before = (left - right) * 0.5

    widened = _apply_stereo_width(stereo, 1.15)
    side_after = (widened[0] - widened[1]) * 0.5

    ratio = np.sqrt(np.mean(side_after ** 2)) / np.sqrt(np.mean(side_before ** 2))
    assert abs(ratio - 1.15) < 1e-3


def test_stereo_width_preserves_mid_signal():
    stereo, _ = _independent_stereo()
    left, right = stereo[0], stereo[1]
    mid_before = (left + right) * 0.5

    widened = _apply_stereo_width(stereo, 1.15)
    mid_after = (widened[0] + widened[1]) * 0.5

    assert np.allclose(mid_before, mid_after, atol=1e-5)


def test_stereo_width_output_shape_and_dtype_match_input():
    stereo, _ = _independent_stereo()
    result = _apply_stereo_width(stereo, 1.1)
    assert result.shape == stereo.shape
    assert result.dtype == np.float32


def test_sub_bass_saturation_shape_dtype_and_no_nan():
    stereo, sr = _independent_stereo()
    result = _apply_sub_bass_saturation(stereo, sr)
    assert result.shape == stereo.shape
    assert result.dtype == np.float32
    assert not np.isnan(result).any()


def test_sub_bass_saturation_actually_changes_the_signal():
    stereo, sr = _independent_stereo()
    result = _apply_sub_bass_saturation(stereo, sr)
    assert not np.allclose(result, stereo)


def test_sub_bass_saturation_does_not_blow_up_peak_level():
    stereo, sr = _independent_stereo()
    result = _apply_sub_bass_saturation(stereo, sr)
    # Parallel-mixed at a modest wet amount -- shouldn't wildly inflate peak
    # level relative to the input, which stayed well under 1.0 (0.1 amplitude
    # random noise).
    assert np.max(np.abs(result)) < 1.0


# ── per-track LUFS mastering (Stage 3 item 7) ────────────────────────────────

def _pink_stereo(seconds=6, sr=44100, seed=0, amplitude=0.05):
    """RMS-normalized pink-ish noise, (channels, samples) -- this module's
    Pedalboard-style array convention (channel-first), unlike
    track_quality.py's (samples, channels) soundfile convention."""
    rng = np.random.default_rng(seed)
    n = int(sr * seconds)
    white = rng.standard_normal(n)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    freqs = freqs.copy()
    freqs[0] = freqs[1] if len(freqs) > 1 else 1.0
    pink = np.fft.irfft(spectrum / np.sqrt(freqs), n)
    rms = np.sqrt(np.mean(pink ** 2))
    pink = (pink / (rms + 1e-9) * amplitude).astype(np.float32)
    return np.stack([pink, pink]), sr


def test_lufs_mastering_hits_target_within_small_tolerance():
    stereo, sr = _pink_stereo(amplitude=0.03)   # start quiet, well under target
    mastered = _apply_lufs_mastering(stereo, sr)

    meter = pyln.Meter(sr)
    measured = meter.integrated_loudness(mastered.T.astype(np.float64))
    assert abs(measured - _TRACK_LUFS_TARGET) < 0.5


def test_lufs_mastering_raises_a_quiet_track():
    stereo, sr = _pink_stereo(amplitude=0.01)
    mastered = _apply_lufs_mastering(stereo, sr)
    assert np.sqrt(np.mean(mastered ** 2)) > np.sqrt(np.mean(stereo ** 2))


def test_lufs_mastering_lowers_a_loud_track():
    stereo, sr = _pink_stereo(amplitude=0.6)
    mastered = _apply_lufs_mastering(stereo, sr)
    assert np.sqrt(np.mean(mastered ** 2)) < np.sqrt(np.mean(stereo ** 2))


def test_lufs_mastering_silent_audio_is_a_safe_noop():
    silent = np.zeros((2, 44100 * 3), dtype=np.float32)
    result = _apply_lufs_mastering(silent, 44100)
    assert np.max(np.abs(result)) == 0.0
    assert not np.isnan(result).any()


def test_lufs_mastering_preserves_shape_and_dtype():
    stereo, sr = _pink_stereo()
    result = _apply_lufs_mastering(stereo, sr)
    assert result.shape == stereo.shape
    assert result.dtype == np.float32


def test_track_lufs_target_leaves_headroom_under_video_level_target():
    # Coordination check: the per-track target must sit BELOW (quieter than)
    # assemble_video.py's -14 LUFS video-level pass, per the documented
    # headroom rationale -- not fighting it by already being as loud or louder.
    assert _TRACK_LUFS_TARGET < -14.0


# ── kick-triggered sidechain ducking (Stage 3 item 7) ────────────────────────

def _kick_and_sustain_mix(seconds=4, sr=44100, kick_every=0.5):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    kick_gate = np.zeros_like(t)
    for onset in np.arange(0, seconds, kick_every):
        idx = int(onset * sr)
        kick_gate[idx:idx + int(0.01 * sr)] = 1.0
    kick = kick_gate * np.sin(2 * np.pi * 60 * t) * 0.6
    sustain = 0.15 * np.sin(2 * np.pi * 300 * t)
    mix = (kick + sustain).astype(np.float32)
    return np.stack([mix, mix]), sr


def test_sidechain_duck_reduces_level_shortly_after_a_kick_hit():
    stereo, sr = _kick_and_sustain_mix()
    ducked = _apply_kick_sidechain_duck(stereo, sr)

    onset_idx = int(1.0 * sr)
    window = slice(onset_idx + 300, onset_idx + 4000)   # just after the kick, still in the duck's release
    before_rms = np.sqrt(np.mean(stereo[0, window] ** 2))
    after_rms = np.sqrt(np.mean(ducked[0, window] ** 2))
    assert after_rms < before_rms


def test_sidechain_duck_preserves_shape_dtype_and_has_no_nan():
    stereo, sr = _kick_and_sustain_mix()
    result = _apply_kick_sidechain_duck(stereo, sr)
    assert result.shape == stereo.shape
    assert result.dtype == np.float32
    assert not np.isnan(result).any()


def test_sidechain_duck_on_silence_is_a_safe_noop():
    silent = np.zeros((2, 44100 * 2), dtype=np.float32)
    result = _apply_kick_sidechain_duck(silent, 44100)
    assert np.max(np.abs(result)) == 0.0


def test_sidechain_duck_never_increases_peak_level():
    stereo, sr = _kick_and_sustain_mix()
    ducked = _apply_kick_sidechain_duck(stereo, sr)
    assert np.max(np.abs(ducked)) <= np.max(np.abs(stereo)) + 1e-6


def test_kick_envelope_peaks_near_kick_onsets():
    _, sr = _kick_and_sustain_mix()
    stereo, sr = _kick_and_sustain_mix()
    mono = stereo.mean(axis=0)
    envelope = _kick_envelope(mono, sr)

    onset_idx = int(1.0 * sr)
    near_kick = envelope[onset_idx:onset_idx + 500].max()
    far_from_kick = envelope[onset_idx + 15000:onset_idx + 18000].max()
    assert near_kick > far_from_kick


def test_sidechain_duck_gate_genre_membership_is_a_small_opt_in_set():
    # Documents/locks the "most genres do NOT want pumping" design intent
    # (see _SIDECHAIN_DUCK_GENRES's comment) -- most of the ~22 genre
    # presets must remain outside this set.
    assert 0 < len(_SIDECHAIN_DUCK_GENRES) < 10
    assert "lofi_house" in _SIDECHAIN_DUCK_GENRES
    assert "lofi_classical" not in _SIDECHAIN_DUCK_GENRES
    assert "ambient" not in _SIDECHAIN_DUCK_GENRES
