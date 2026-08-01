"""
reaction_diffusion.py — Gray-Scott reaction-diffusion simulation, used as an
alternative organic-texture background generator to the flat/noise-warped
gradient in static_layers.py. Simulated ONCE at low resolution to a settled
state and cached by the caller — never per-frame. Animation (if any) should
come from noise.py's orbit-warp trick applied to the settled field, matching
the "precompute once, cheap per-frame access" philosophy used throughout
scripts/visual_v2/ (apply_bloom's downsample, make_vinyl_label_frames' cache).

This is a structurally different technique from noise.py's Perlin/fBm:
noise fields are a closed-form function sampled directly, while this is an
emergent pattern that develops from simulating a reaction-diffusion PDE
forward in time.
"""

from __future__ import annotations

import numpy as np

# Pearson's parameter atlas — named (feed, kill) pairs producing visually
# distinct, well-documented Gray-Scott patterns.
PRESETS: dict[str, tuple[float, float]] = {
    "spots":   (0.035, 0.065),
    "stripes": (0.030, 0.058),
    "coral":   (0.0545, 0.062),
    "maze":    (0.029, 0.057),
}


def _laplacian(a: np.ndarray) -> np.ndarray:
    """5-point discrete Laplacian with periodic (wraparound) boundary via
    np.roll — this also makes the resulting field naturally tileable."""
    return (
        np.roll(a, 1, axis=0) + np.roll(a, -1, axis=0)
        + np.roll(a, 1, axis=1) + np.roll(a, -1, axis=1)
        - 4 * a
    )


def gray_scott_texture(w: int, h: int, feed: float = 0.035, kill: float = 0.065,
                        steps: int = 1500, seed: int = 0,
                        du: float = 0.16, dv: float = 0.08) -> np.ndarray:
    """
    Simulate a Gray-Scott reaction-diffusion system to a settled pattern.
    Returns a float32 [0, 1] array (the v / "activator" concentration).
    Only cheap at low resolution + bounded step count — call this once
    during setup, never per-frame.
    """
    rng = np.random.RandomState(seed)
    u = np.ones((h, w), dtype=np.float64)
    v = np.zeros((h, w), dtype=np.float64)

    # Seed a handful of random square patches with the reactive species —
    # without an initial perturbation the system stays at the trivial
    # (u=1, v=0) fixed point forever.
    n_seeds = rng.randint(3, 7)
    for _ in range(n_seeds):
        r = max(2, min(h, w) // rng.randint(8, 20))
        cy = rng.randint(r, max(r + 1, h - r))
        cx = rng.randint(r, max(r + 1, w - r))
        y0, y1 = max(0, cy - r), min(h, cy + r)
        x0, x1 = max(0, cx - r), min(w, cx + r)
        u[y0:y1, x0:x1] = 0.50
        v[y0:y1, x0:x1] = 0.25
    u += rng.uniform(-0.02, 0.02, size=u.shape)
    v += rng.uniform(-0.02, 0.02, size=v.shape)

    dt = 1.0
    for _ in range(steps):
        lu = _laplacian(u)
        lv = _laplacian(v)
        uvv = u * v * v
        u += (du * lu - uvv + feed * (1.0 - u)) * dt
        v += (dv * lv + uvv - (feed + kill) * v) * dt
        np.clip(u, 0.0, 1.0, out=u)
        np.clip(v, 0.0, 1.0, out=v)

    mn, mx = v.min(), v.max()
    if mx - mn < 1e-9:
        return np.full((h, w), 0.5, dtype=np.float32)
    return ((v - mn) / (mx - mn)).astype(np.float32)


def gray_scott_bg(theme_colors: dict, w: int, h: int, preset: str = "coral",
                   seed: int = 0, steps: int = 1500, sim_res: int = 128) -> np.ndarray:
    """
    Drop-in alternate background generator (same output shape/dtype as
    static_layers.make_gradient_bg): simulate Gray-Scott at a low internal
    resolution (sim_res on the shorter axis), upsample, and colorize the
    settled concentration field through the theme's bg_top/bg_bot colors
    (concentration -> color lerp, replacing make_gradient_bg's y-position ->
    color lerp).
    """
    from PIL import Image

    feed, kill = PRESETS.get(preset, PRESETS["coral"])
    aspect = w / h
    sim_h = sim_res
    sim_w = max(8, int(sim_res * aspect))

    field = gray_scott_texture(sim_w, sim_h, feed=feed, kill=kill, steps=steps, seed=seed)
    field_img = Image.fromarray((field * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)
    field_full = np.asarray(field_img, dtype=np.float32) / 255.0

    top = np.array(theme_colors["bg_top"], dtype=np.float32)
    bot = np.array(theme_colors["bg_bot"], dtype=np.float32)
    t = field_full[:, :, None]
    arr = top[None, None, :] * (1 - t) + bot[None, None, :] * t
    return arr.astype(np.uint8)
