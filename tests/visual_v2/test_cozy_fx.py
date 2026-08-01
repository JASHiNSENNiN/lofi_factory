import numpy as np
import pytest

from scripts.visual_v2.config import FPS, H, W
from scripts.visual_v2.cozy_fx import (
    THEME_FX,
    CandleFlicker,
    FireflyField,
    NeonPulse,
    PetalDrift,
    RainOverlay,
    SnowFall,
    SteamRiser,
    WindowGlow,
    build_fx,
)

# Mid-gray, not black: several FX (WindowGlow, CandleFlicker) modulate
# brightness multiplicatively, which a black (0,0,0) frame would silently
# mask (0 * anything == 0) -- this was caught by first-ever execution of
# this code, not assumed from reading it.
_FRAME = np.full((H, W, 3), 128, dtype=np.uint8)

_ALL_CLASSES = [
    lambda: WindowGlow(10, rng_seed=1),
    lambda: RainOverlay(10, rng_seed=1),
    lambda: CandleFlicker(10, rng_seed=1),
    lambda: SteamRiser(10, rng_seed=1),
    lambda: FireflyField(10, rng_seed=1),
    lambda: SnowFall(10, rng_seed=1),
    lambda: PetalDrift(10, rng_seed=1, sakura=False),
    lambda: PetalDrift(10, rng_seed=1, sakura=True),
    lambda: NeonPulse(10, rng_seed=1),
]


@pytest.mark.parametrize("make_fx", _ALL_CLASSES, ids=lambda f: type(f()).__name__)
def test_fx_class_smoke_renders_valid_frame(make_fx):
    fx = make_fx()
    # t values include one past n_frames (10/FPS * 10... use a value > n_frames
    # in frame-index terms) to exercise the frame_idx % n_frames wraparound.
    for t in (0.0, 0.3, 20 / FPS, 1.0):
        out = fx.render(_FRAME, t)
        assert out.shape == (H, W, 3)
        assert out.dtype == np.uint8
        assert not np.isnan(out.astype(float)).any()


def test_build_fx_covers_every_theme():
    for theme, names in THEME_FX.items():
        fx_list = build_fx(theme, n_frames=5, rng_seed=0)
        assert len(fx_list) == len(names)
        for fx in fx_list:
            out = fx.render(_FRAME, 0.0)
            assert out.shape == (H, W, 3)


def test_build_fx_unknown_theme_falls_back_to_default():
    fx_list = build_fx('not_a_real_theme', n_frames=5)
    assert len(fx_list) == 2  # ["window_glow", "candle"]


@pytest.mark.parametrize("cls", [WindowGlow, CandleFlicker, NeonPulse])
def test_noise_field_driven_classes_actually_vary_per_frame(cls):
    # These sample a fixed field cell each render() and rely on the
    # per-frame orbit offset (not the cell index) to vary -- proves the
    # noise field isn't silently short-circuiting to a constant.
    fx = cls(10, rng_seed=1)
    a = fx.render(_FRAME, 0.0)
    b = fx.render(_FRAME, 0.5 * 10 / FPS)
    assert not np.array_equal(a, b)


@pytest.mark.parametrize("cls", [SteamRiser, FireflyField, SnowFall, PetalDrift])
def test_curl_noise_classes_render_across_a_time_sweep_without_exception(cls):
    fx = cls(20, rng_seed=1)
    for t in np.linspace(0, 5, 20):
        out = fx.render(_FRAME, float(t))
        assert out.shape == (H, W, 3)


def test_low_count_instantiation_does_not_break_rendering():
    assert RainOverlay(n_frames=10, density=5).render(_FRAME, 0.0).shape == (H, W, 3)
    assert PetalDrift(n_frames=10, count=3).render(_FRAME, 0.0).shape == (H, W, 3)
