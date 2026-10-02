"""
noise.py — Looping harmonic noise, vectorized 2D Perlin/fBm noise fields, and
shared colour helpers.

The 2D Perlin implementation follows the standard vectorized gradient-noise
algorithm (grid gradients + quintic interpolation, no per-pixel Python loops).
"""

import math
import numpy as np


def looping_noise(n_frames: int, n_harmonics: int = 6, seed: int = 0) -> np.ndarray:
    """Returns a [0, 1] float32 array that loops perfectly over n_frames."""
    rng = np.random.RandomState(seed)
    t   = np.linspace(0, 2 * math.pi, n_frames, endpoint=False)
    sig = np.zeros(n_frames, dtype=np.float64)
    for h in range(1, n_harmonics + 1):
        amp   = 1.0 / h
        phase = rng.uniform(0, 2 * math.pi)
        sig  += amp * np.sin(h * t + phase)
    mn, mx = sig.min(), sig.max()
    return ((sig - mn) / (mx - mn)).astype(np.float32)


# ─── Vectorized 2D Perlin / fractal (fBm) noise ────────────────────────────

def _quintic(t: np.ndarray) -> np.ndarray:
    """Ken Perlin's improved quintic smoothstep: 6t^5 - 15t^4 + 10t^3."""
    return t * t * t * (t * (t * 6 - 15) + 10)


def perlin2d(shape: tuple[int, int], res: tuple[int, int], seed: int = 0,
             tileable: tuple[bool, bool] = (False, False)) -> np.ndarray:
    """
    Vectorized 2D Perlin noise. `shape` (h, w) MUST be an exact multiple of
    `res` (grid cells) in both dimensions — use fractal_noise2d() below for a
    safe wrapper that handles arbitrary shapes via pad+crop. Returns a float
    array roughly in [-1, 1] (not normalized to [0,1]).
    """
    rng = np.random.RandomState(seed)
    h, w = shape
    ry, rx = res
    delta = (ry / h, rx / w)
    d = (h // ry, w // rx)
    grid = np.mgrid[0:ry:delta[0], 0:rx:delta[1]].transpose(1, 2, 0) % 1

    angles = 2 * np.pi * rng.rand(ry + 1, rx + 1)
    gradients = np.dstack((np.cos(angles), np.sin(angles)))
    if tileable[0]:
        gradients[-1, :] = gradients[0, :]
    if tileable[1]:
        gradients[:, -1] = gradients[:, 0]
    gradients = gradients.repeat(d[0], 0).repeat(d[1], 1)

    g00 = gradients[:-d[0], :-d[1]]
    g10 = gradients[d[0]:, :-d[1]]
    g01 = gradients[:-d[0], d[1]:]
    g11 = gradients[d[0]:, d[1]:]

    n00 = np.sum(np.dstack((grid[:, :, 0],     grid[:, :, 1]))     * g00, 2)
    n10 = np.sum(np.dstack((grid[:, :, 0] - 1, grid[:, :, 1]))     * g10, 2)
    n01 = np.sum(np.dstack((grid[:, :, 0],     grid[:, :, 1] - 1)) * g01, 2)
    n11 = np.sum(np.dstack((grid[:, :, 0] - 1, grid[:, :, 1] - 1)) * g11, 2)

    t = _quintic(grid)
    n0 = n00 * (1 - t[:, :, 0]) + t[:, :, 0] * n10
    n1 = n01 * (1 - t[:, :, 0]) + t[:, :, 0] * n11
    return math.sqrt(2) * ((1 - t[:, :, 1]) * n0 + t[:, :, 1] * n1)


def fractal_noise2d(h: int, w: int, octaves: int = 4, persistence: float = 0.5,
                     lacunarity: int = 2, base_res: int = 4, seed: int = 0,
                     tileable: tuple[bool, bool] = (False, False)) -> np.ndarray:
    """
    Safe wrapper around perlin2d() for arbitrary (h, w): internally pads up to
    the nearest shape that's a valid multiple of every octave's grid resolution
    (required by the underlying algorithm), generates fBm (summed octaves with
    per-octave amplitude/frequency falloff), then crops back to (h, w).
    Returns a float32 array normalized to [0, 1].
    """
    max_freq = lacunarity ** (octaves - 1)
    multiple = base_res * max_freq
    pad_h = ((h + multiple - 1) // multiple) * multiple
    pad_w = ((w + multiple - 1) // multiple) * multiple
    pad_h = max(pad_h, multiple)
    pad_w = max(pad_w, multiple)

    noise = np.zeros((pad_h, pad_w), dtype=np.float64)
    frequency, amplitude = 1, 1.0
    for octave in range(octaves):
        noise += amplitude * perlin2d(
            (pad_h, pad_w),
            (base_res * frequency, base_res * frequency),
            seed=seed + octave * 97,   # decorrelate octaves while staying deterministic
            tileable=tileable,
        )
        frequency *= lacunarity
        amplitude *= persistence

    cropped = noise[:h, :w]
    mn, mx = cropped.min(), cropped.max()
    if mx - mn < 1e-9:
        return np.full((h, w), 0.5, dtype=np.float32)
    return ((cropped - mn) / (mx - mn)).astype(np.float32)


def noise_field_frames(w: int, h: int, n_frames: int, octaves: int = 4,
                        persistence: float = 0.5, lacunarity: int = 2,
                        base_res: int = 4, warp_amp: float = 0.4, seed: int = 0):
    """
    Precompute ONE static tileable fractal noise field (h, w), then return a
    cheap `get(frame_idx) -> np.ndarray[h, w]` accessor that animates it by
    sampling through a small circular pixel offset. Because the offset path
    traces a closed circle over n_frames (sin/cos are exactly periodic), this
    guarantees perfectly seamless looping WITHOUT recomputing the noise field
    per frame — same "precompute once, cheap per-frame access" philosophy as
    apply_bloom's downsample trick and make_vinyl_label_frames' rotation cache.
    tileable=(True, True) means np.roll's wraparound introduces no seam.
    """
    field = fractal_noise2d(h, w, octaves=octaves, persistence=persistence,
                             lacunarity=lacunarity, base_res=base_res, seed=seed,
                             tileable=(True, True))
    max_off_y = max(1, int(warp_amp * h * 0.05))
    max_off_x = max(1, int(warp_amp * w * 0.05))

    def get(frame_idx: int) -> np.ndarray:
        theta = 2 * math.pi * (frame_idx / max(1, n_frames))
        off_y = int(max_off_y * math.sin(theta))
        off_x = int(max_off_x * math.cos(theta))
        return np.roll(np.roll(field, off_y, axis=0), off_x, axis=1)

    return get


def noise_gradient(field: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Spatial gradient (dy, dx) of a 2D noise field via finite differences
    (np.gradient), used to derive divergence-free curl-noise flow-field
    motion for particles: velocity = (dfield/dy, -dfield/dx).
    """
    dy, dx = np.gradient(field)
    return dy, dx
