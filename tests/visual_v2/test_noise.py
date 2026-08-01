import numpy as np

from scripts.visual_v2.noise import (
    fractal_noise2d,
    noise_field_frames,
    noise_gradient,
    perlin2d,
)


def test_perlin2d_shape_and_bounded_range():
    field = perlin2d((64, 64), (4, 4), seed=0)
    assert field.shape == (64, 64)
    assert np.issubdtype(field.dtype, np.floating)
    assert not np.isnan(field).any()
    assert field.min() >= -1.5 and field.max() <= 1.5


def test_fractal_noise2d_arbitrary_shape_pad_crop():
    # deliberately non-multiple-of-16 shape to exercise the pad/crop path
    field = fractal_noise2d(37, 53, seed=0)
    assert field.shape == (37, 53)
    assert field.dtype == np.float32
    assert field.min() >= 0.0 and field.max() <= 1.0


def test_fractal_noise2d_deterministic_per_seed():
    a = fractal_noise2d(64, 64, seed=42)
    b = fractal_noise2d(64, 64, seed=42)
    assert np.array_equal(a, b)


def test_fractal_noise2d_differs_across_seeds():
    a = fractal_noise2d(64, 64, seed=42)
    b = fractal_noise2d(64, 64, seed=43)
    assert not np.array_equal(a, b)


def test_fractal_noise2d_never_nan_at_minimum_valid_size():
    # h == w == base_res is the smallest shape the octave math supports
    field = fractal_noise2d(4, 4, seed=0, base_res=4, octaves=1)
    assert not np.isnan(field).any()


def test_fractal_noise2d_tileable_seam_is_not_a_visible_discontinuity():
    field = fractal_noise2d(64, 64, seed=0, tileable=(True, True))
    seam_diff = np.abs(field[:, 0] - field[:, -1]).mean()
    interior_diff = np.abs(field[:, 1:] - field[:, :-1]).mean()
    assert seam_diff < interior_diff * 3


def test_noise_field_frames_loops_perfectly():
    get = noise_field_frames(32, 18, n_frames=10, seed=0)
    assert get(0).shape == (18, 32)
    assert np.array_equal(get(0), get(10))


def test_noise_gradient_of_flat_field_is_zero():
    dy, dx = noise_gradient(np.zeros((16, 16)))
    assert np.all(dy == 0)
    assert np.all(dx == 0)


def test_noise_gradient_of_linear_ramp_has_constant_sign():
    ramp = np.tile(np.arange(16, dtype=float), (16, 1))
    dy, dx = noise_gradient(ramp)
    assert np.all(dy == 0)
    signs = set(np.sign(dx).flatten().tolist())
    assert signs == {1.0}
