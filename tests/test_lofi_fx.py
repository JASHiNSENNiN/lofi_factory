import numpy as np

from scripts.lofi_fx import _apply_stereo_width, _apply_sub_bass_saturation


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
