"""
postfx.py — Per-frame post-processing: bloom, film grain, watermark.
"""

import os
import numpy as np
from PIL import Image, ImageFilter, ImageFont

from .config import W, H
from .themes import THEMES


# ── Bloom ─────────────────────────────────────────────────────────────────────

def apply_bloom(frame: np.ndarray, threshold: int = 155,
                strength: float = 0.35, radius: int = 14) -> np.ndarray:
    bright = np.clip(frame.astype(np.int16) - threshold, 0, 255).astype(np.uint8)
    if bright.max() == 0:
        return frame
    # Downsample to ¼ resolution before blurring — 16× cheaper, indistinguishable result.
    # Bloom is a low-frequency effect; sub-pixel accuracy is irrelevant.
    small_w, small_h = W // 4, H // 4
    small = Image.fromarray(bright).resize((small_w, small_h), Image.BOX)
    blurred_small = small.filter(ImageFilter.GaussianBlur(radius=max(1, radius // 4)))
    bloom = np.array(
        blurred_small.resize((W, H), Image.BILINEAR)
    ).astype(np.float32)
    return np.clip(frame.astype(np.float32) + bloom * strength, 0, 255).astype(np.uint8)


# ── Film grain ────────────────────────────────────────────────────────────────

def film_grain(frame: np.ndarray, strength: float = 3.5) -> np.ndarray:
    """
    Per-pixel Gaussian noise, luminance-scaled (more grain in shadows, less
    in highlights — matching real film stock's characteristic response)
    rather than a flat strength applied uniformly across all brightness.
    """
    luminance = (0.299 * frame[:, :, 0] + 0.587 * frame[:, :, 1]
                 + 0.114 * frame[:, :, 2]).astype(np.float32) / 255.0
    lum_factor = (1.6 - 1.1 * luminance)[:, :, None]   # shadows ~1.6x, highlights ~0.5x
    g = np.random.normal(0, 1.0, frame.shape).astype(np.float32) * strength * lum_factor
    return np.clip(frame.astype(np.float32) + g, 0, 255).astype(np.uint8)


# ── Warm colour grade ─────────────────────────────────────────────────────────

def warm_grade(frame: np.ndarray, theme: str) -> np.ndarray:
    c = THEMES[theme]
    f = frame.astype(np.int16)
    f[:, :, 0] = np.clip(f[:, :, 0] + c.get("warmth_r", 0), 0, 255)
    f[:, :, 2] = np.clip(f[:, :, 2] + c.get("warmth_b", 0), 0, 255)
    return f.astype(np.uint8)


# ── Vignette ──────────────────────────────────────────────────────────────────

def apply_vignette(frame: np.ndarray, vignette: np.ndarray) -> np.ndarray:
    return np.clip(
        frame.astype(np.float32) * vignette[:, :, None], 0, 255
    ).astype(np.uint8)


# ── Chromatic aberration (optional) ───────────────────────────────────────────

_CA_DIST_CACHE = None


def _get_ca_distance_grid() -> np.ndarray:
    """Cached normalized radial distance grid [0,1] (0 at center, 1 at
    corners) — same formula as static_layers.make_vignette's dist."""
    global _CA_DIST_CACHE
    if _CA_DIST_CACHE is None:
        y_idx, x_idx = np.mgrid[0:H, 0:W].astype(np.float32)
        dx = (x_idx - W / 2) / (W / 2)
        dy = (y_idx - H / 2) / (H / 2)
        _CA_DIST_CACHE = np.clip(np.sqrt(dx ** 2 + dy ** 2) / 1.42, 0, 1)
    return _CA_DIST_CACHE


def chromatic_aberration(frame: np.ndarray, shift: int = 3) -> np.ndarray:
    """
    Radially-varying chromatic aberration — small near the center, up to
    `shift` px at the corners — instead of a constant global shift (real
    lens CA increases toward the edges). Applied as a handful of discrete
    radial bands (not a true per-pixel remap) to stay cheap; reuses the same
    distance-grid formula as static_layers.make_vignette.
    """
    if shift <= 0:
        return frame
    dist = _get_ca_distance_grid()
    result = frame.copy()
    for band_shift in range(1, shift + 1):
        lo = (band_shift - 1) / shift
        hi = band_shift / shift
        mask = (dist >= lo) & ((dist <= hi) if band_shift == shift else (dist < hi))
        if not mask.any():
            continue
        shifted_r = frame[:, :, 0].copy()
        shifted_r[:, band_shift:] = frame[:, :-band_shift, 0]
        shifted_b = frame[:, :, 2].copy()
        shifted_b[:, :-band_shift] = frame[:, band_shift:, 2]
        result[:, :, 0] = np.where(mask, shifted_r, result[:, :, 0])
        result[:, :, 2] = np.where(mask, shifted_b, result[:, :, 2])
    return result


# ── Scanline darken pass ──────────────────────────────────────────────────────

def apply_scanlines(frame: np.ndarray, scanlines: np.ndarray) -> np.ndarray:
    return np.clip(
        frame.astype(np.float32) * scanlines[:, :, None], 0, 255
    ).astype(np.uint8)


# ── Watermark ─────────────────────────────────────────────────────────────────

_WATERMARK_OV = None


def _get_font(size: int = 22):
    candidates = [
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


