"""
static_layers.py — Pre-computed background: gradient, star field, scanlines.
All return numpy arrays composited in generate.py.
"""

import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .config import W, H
from .themes import THEMES


# ── Background gradient ──────────────────────────────────────────────────────

def make_gradient_bg(theme: str, seed: int = 11) -> np.ndarray:
    """
    Full-frame vertical gradient, domain-warped by a static fractal (fBm)
    noise field for cloud-like texture instead of a flat linear gradient.
    The field is generated at 1/4 resolution and upsampled (same cheap
    downsample-then-upsample philosophy as postfx.apply_bloom) since this is
    a one-time precompute, not per-frame.
    """
    from .noise import fractal_noise2d
    c   = THEMES[theme]
    top = np.array(c["bg_top"], dtype=np.float32)
    bot = np.array(c["bg_bot"], dtype=np.float32)

    field_small = fractal_noise2d(max(4, H // 4), max(4, W // 4), octaves=4, seed=seed)
    field = np.asarray(
        Image.fromarray((field_small * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR),
        dtype=np.float32,
    ) / 255.0

    t_row    = np.broadcast_to(np.linspace(0, 1, H, dtype=np.float32)[:, None], (H, W))
    t_warped = np.clip(t_row + 0.18 * (field - 0.5), 0, 1)[:, :, None]
    arr = top[None, None, :] * (1 - t_warped) + bot[None, None, :] * t_warped
    return arr.astype(np.uint8)


# ── Star field ───────────────────────────────────────────────────────────────

def make_star_field(theme: str, seed: int = 7) -> np.ndarray:
    """
    Star-like dots scattered across the background, with density weighted by
    a static fractal noise field so stars cluster along noise ridges
    (nebula/dust-lane look) instead of scattering uniformly at random.
    """
    from .noise import fractal_noise2d
    c   = THEMES[theme]
    rng = np.random.RandomState(seed)
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    sc  = np.array(c.get("star_col", [200, 210, 255]), dtype=np.uint8)

    field_small = fractal_noise2d(max(4, H // 4), max(4, W // 4), octaves=3, seed=seed + 500)
    field = np.asarray(
        Image.fromarray((field_small * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR),
        dtype=np.float32,
    ) / 255.0
    # Square the field to sharpen clustering contrast before using as weights.
    weights = (field ** 2).ravel()
    weights = weights / weights.sum()

    n_stars = 280
    flat_idx = rng.choice(H * W, size=n_stars, p=weights)
    ys, xs = np.unravel_index(flat_idx, (H, W))

    for i in range(n_stars):
        sx, sy = int(xs[i]), int(ys[i])
        br = rng.randint(30, 140)
        r  = rng.randint(0, 3)
        col = (sc * (br / 140)).astype(np.uint8)
        y0  = max(0, sy - r); y1 = min(H, sy + r + 1)
        x0  = max(0, sx - r); x1 = min(W, sx + r + 1)
        arr[y0:y1, x0:x1] = col

    # Soft blur to make stars look like light sources
    return np.array(Image.fromarray(arr).filter(ImageFilter.GaussianBlur(radius=1)))


# ── Scanlines overlay ────────────────────────────────────────────────────────

def make_scanlines(strength: float = 0.07) -> np.ndarray:
    """Horizontal scanline pattern — subtle retro CRT look. Returns float32 multiplier."""
    arr = np.ones((H, W), dtype=np.float32)
    arr[1::3] *= (1.0 - strength)    # every 3rd line slightly dimmed
    return arr


# ── Vignette ─────────────────────────────────────────────────────────────────

def make_vignette(strength: float = 0.45) -> np.ndarray:
    """Radial vignette, float32 [0,1] multiplier."""
    y_idx, x_idx = np.mgrid[0:H, 0:W].astype(np.float32)
    dx = (x_idx - W / 2) / (W / 2)
    dy = (y_idx - H / 2) / (H / 2)
    dist  = np.sqrt(dx**2 + dy**2)
    t     = np.clip(dist / 1.42, 0, 1).astype(np.float32)
    smooth = t * t * (3.0 - 2.0 * t)
    return (1.0 - strength * smooth).astype(np.float32)


# ── Twinkle noise ─────────────────────────────────────────────────────────────

def make_star_twinkle(n_frames: int, seed: int = 0) -> np.ndarray:
    """Per-frame twinkle multiplier for star brightness."""
    from .noise import looping_noise
    return 0.82 + 0.18 * looping_noise(n_frames, n_harmonics=4, seed=seed % 9999)
