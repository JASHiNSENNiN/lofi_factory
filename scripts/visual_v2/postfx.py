"""
postfx.py — Per-frame post-processing: bloom, film grain, watermark.
"""

import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import W, H, CHANNEL_NAME
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
    g = np.random.normal(0, strength, frame.shape).astype(np.int16)
    return np.clip(frame.astype(np.int16) + g, 0, 255).astype(np.uint8)


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

def chromatic_aberration(frame: np.ndarray, shift: int = 1) -> np.ndarray:
    result = frame.copy()
    if shift > 0:
        result[:, shift:, 0]  = frame[:, :-shift, 0]
        result[:, :-shift, 2] = frame[:, shift:, 2]
    return result


# ── Scanline darken pass ──────────────────────────────────────────────────────

def apply_scanlines(frame: np.ndarray, scanlines: np.ndarray) -> np.ndarray:
    return np.clip(
        frame.astype(np.float32) * scanlines[:, :, None], 0, 255
    ).astype(np.uint8)


# ── Watermark ─────────────────────────────────────────────────────────────────

_WATERMARK_OV = None


def _get_font(size: int = 22):
    from PIL import ImageFont
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


def draw_watermark(frame: np.ndarray,
                   channel_name: str = CHANNEL_NAME) -> None:
    """Cached semi-transparent channel name bottom-right."""
    global _WATERMARK_OV
    if _WATERMARK_OV is None:
        ov   = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d    = ImageDraw.Draw(ov)
        font = _get_font(22)
        text = channel_name
        x, y = W - 235, H - 48
        d.text((x + 1, y + 1), text, fill=(0, 0, 0, 90), font=font)
        d.text((x, y),         text, fill=(210, 210, 210, 110), font=font)
        _WATERMARK_OV = np.array(ov)

    ov_arr = _WATERMARK_OV
    alpha  = ov_arr[:, :, 3:4].astype(np.float32) / 255.0
    dst    = frame.astype(np.float32)
    frame[:] = np.clip(
        dst * (1 - alpha) + ov_arr[:, :, :3].astype(np.float32) * alpha,
        0, 255
    ).astype(np.uint8)
