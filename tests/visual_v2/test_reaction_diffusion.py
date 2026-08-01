import numpy as np
import pytest

from scripts.visual_v2.reaction_diffusion import (
    PRESETS,
    _laplacian,
    gray_scott_bg,
    gray_scott_texture,
)


def test_laplacian_of_constant_field_is_zero():
    const = np.full((8, 8), 3.0)
    assert np.all(_laplacian(const) == 0)


def test_laplacian_hot_pixel_periodic_wraparound():
    # hot pixel at [0,0] specifically exercises np.roll's wraparound at the
    # array edge, not just an interior neighborhood.
    hot = np.zeros((8, 8))
    hot[0, 0] = 5.0
    lap = _laplacian(hot)
    assert lap[0, 0] == -20.0  # -4 * center
    assert lap[1, 0] == 5.0 and lap[-1, 0] == 5.0
    assert lap[0, 1] == 5.0 and lap[0, -1] == 5.0


def test_gray_scott_texture_small_scale_shape_and_range():
    # Deliberately small step count -- the 1500-step production default is
    # reserved for the dedicated @pytest.mark.slow test below.
    field = gray_scott_texture(16, 16, steps=20, seed=0)
    assert field.shape == (16, 16)
    assert field.dtype == np.float32
    assert not np.isnan(field).any()
    assert field.min() >= 0.0 and field.max() <= 1.0


def test_gray_scott_texture_deterministic_per_seed():
    a = gray_scott_texture(16, 16, steps=20, seed=1)
    b = gray_scott_texture(16, 16, steps=20, seed=1)
    assert np.array_equal(a, b)


def test_gray_scott_texture_differs_across_seeds():
    a = gray_scott_texture(16, 16, steps=20, seed=1)
    b = gray_scott_texture(16, 16, steps=20, seed=2)
    assert not np.array_equal(a, b)


def test_gray_scott_bg_output_shape_is_h_w_3():
    # Catches an h/w transpose bug: shape must be (h, w, 3), not (w, h, 3).
    bg = gray_scott_bg(
        {'bg_top': (10, 20, 30), 'bg_bot': (200, 190, 180)},
        w=32, h=18, steps=20, sim_res=16,
    )
    assert bg.shape == (18, 32, 3)
    assert bg.dtype == np.uint8


@pytest.mark.slow
@pytest.mark.parametrize("preset", list(PRESETS.keys()))
def test_gray_scott_texture_production_scale_no_blowup(preset):
    feed, kill = PRESETS[preset]
    field = gray_scott_texture(64, 64, feed=feed, kill=kill, steps=1500, seed=0)
    assert not np.isnan(field).any()
    assert not np.isinf(field).any()
    assert field.min() >= 0.0 and field.max() <= 1.0
