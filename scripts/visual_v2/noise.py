"""
noise.py — Looping harmonic noise and shared colour helpers.
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


def clamp_col(r: int, g: int, b: int) -> tuple:
    """Clamp RGB tuple to [0, 255]."""
    return (max(0, min(255, r)),
            max(0, min(255, g)),
            max(0, min(255, b)))
