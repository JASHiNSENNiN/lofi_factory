"""
character.py — EQ background panel + oscilloscope strip.

The actual EQ bars are NOT drawn here — they are rendered by ffmpeg's
showfreqs filter in assemble_video.py using real audio frequency data.
This module renders the background panel so the EQ zone looks intentional
in standalone preview, and draws decorative elements (floor line, zone labels,
oscilloscope).
"""

import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .config import (
    W, H, EQ_BARS, EQ_X0, EQ_X1, EQ_Y_BOT, EQ_MAX_H, EQ_MIN_H, EQ_GAP,
    HEADER_H,
)
from .noise import looping_noise
from .themes import THEMES


# ── EQ background panel ───────────────────────────────────────────────────────

class EQVisualizer:
    """
    Draws the EQ zone background panel and decorative elements.
    Actual bars come from ffmpeg showfreqs in assemble_video.py.
    """

    def __init__(self, n_frames: int, n_bars: int = EQ_BARS, rng_seed: int = 0):
        self.n_frames = n_frames
        self.n_bars   = n_bars
        # Subtle pulse noise for the floor glow line
        self.pulse = 0.6 + 0.4 * looping_noise(n_frames, n_harmonics=4,
                                                 seed=rng_seed % 9999)

    def render(self, frame: np.ndarray, f_idx: int, theme: str) -> None:
        c   = THEMES[theme]
        acc = np.array(c["accent"], dtype=np.float32)
        top = np.array(c["eq_top"],  dtype=np.float32)
        bot = np.array(c["eq_bot"],  dtype=np.float32)

        eq_top_y = EQ_Y_BOT - EQ_MAX_H
        eq_bot_y = EQ_Y_BOT

        # ── Dark background panel for the EQ zone ──────────────────────────
        if eq_top_y >= 0 and eq_top_y < H and eq_bot_y > eq_top_y:
            # Very subtle gradient tint — darker at top, hint of theme colour at bottom
            band_h = eq_bot_y - eq_top_y
            t_arr  = np.linspace(0.0, 1.0, band_h, dtype=np.float32)
            bg_dark = np.array([6, 6, 10], dtype=np.float32)
            bg_tint = bot * 0.18
            bg_grad = (bg_dark[None, :] * (1 - t_arr)[:, None]
                       + bg_tint[None, :] * t_arr[:, None]).astype(np.uint8)
            frame[eq_top_y:eq_bot_y, EQ_X0:EQ_X1] = np.clip(
                frame[eq_top_y:eq_bot_y, EQ_X0:EQ_X1].astype(np.float32) * 0.35
                + bg_grad[:, None, :] * np.ones((1, EQ_X1 - EQ_X0, 1), dtype=np.float32),
                0, 255
            ).astype(np.uint8)

        # ── Pulsing floor glow line ─────────────────────────────────────────
        pulse = float(self.pulse[f_idx])
        gline = EQ_Y_BOT
        if 0 <= gline < H:
            glow_strip = np.zeros((3, W, 3), dtype=np.float32)
            intensity  = acc * 0.55 * pulse
            glow_strip[:, EQ_X0:EQ_X1] = intensity
            y0 = max(0, gline - 1); y1 = min(H, gline + 2)
            frame[y0:y1] = np.clip(
                frame[y0:y1].astype(np.float32) + glow_strip[:y1 - y0],
                0, 255
            ).astype(np.uint8)

        # ── Horizontal separator above EQ zone ─────────────────────────────
        sep_y = eq_top_y - 1
        if 0 <= sep_y < H:
            frame[sep_y, EQ_X0:EQ_X1] = np.clip(acc * 0.30, 0, 255).astype(np.uint8)

        # ── Zone labels ─────────────────────────────────────────────────────
        self._draw_zone_labels(frame, theme)

    def _draw_zone_labels(self, frame: np.ndarray, theme: str) -> None:
        c   = THEMES[theme]
        acc = c["accent"]
        from .scene import _font_reg
        fnt     = _font_reg(17)
        label_y = EQ_Y_BOT + 12
        zones   = [
            (EQ_X0 + 10,                              "BASS"),
            (EQ_X0 + int((EQ_X1 - EQ_X0) * 0.27),   "LOW-MID"),
            (EQ_X0 + int((EQ_X1 - EQ_X0) * 0.52),   "MID"),
            (EQ_X0 + int((EQ_X1 - EQ_X0) * 0.76),   "HIGH"),
        ]
        pil = Image.fromarray(frame).convert("RGBA")
        ov  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d   = ImageDraw.Draw(ov)
        for zx, label in zones:
            d.text((zx, label_y), label, fill=(*acc, 65), font=fnt)
        frame[:] = np.array(Image.alpha_composite(pil, ov).convert("RGB"))


# ── Oscilloscope strip (above EQ zone) ────────────────────────────────────────

class OscilloscopeBar:
    """
    Animated waveform strip just above the EQ zone — purely decorative,
    gives motion to the otherwise-static upper visual while the EQ zone
    waits for the assembler to inject real bars.
    """

    def __init__(self, n_frames: int, rng_seed: int = 0):
        self.amp_noise = 0.35 + 0.65 * looping_noise(n_frames, n_harmonics=6,
                                                       seed=rng_seed % 9999)

    def render(self, frame: np.ndarray, f_idx: int, theme: str) -> None:
        c    = THEMES[theme]
        acc  = c["accent"]
        amp  = float(self.amp_noise[f_idx]) * 24
        t    = f_idx / 24.0
        y_mid = EQ_Y_BOT - EQ_MAX_H - 18
        if y_mid < HEADER_H or y_mid >= H:
            return
        pts = []
        for ix in range(EQ_X0, EQ_X1, 3):
            pos  = (ix - EQ_X0) / (EQ_X1 - EQ_X0)
            wave = (math.sin(pos * 2 * math.pi * 9 + t * 6.2)
                    * math.cos(pos * 2 * math.pi * 3.7 + t * 2.3))
            pts.append((ix, int(y_mid + amp * wave)))
        if len(pts) < 2:
            return
        pil = Image.fromarray(frame).convert("RGBA")
        ov  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d   = ImageDraw.Draw(ov)
        d.line(pts, fill=(*acc, 90), width=2)
        frame[:] = np.array(Image.alpha_composite(pil, ov).convert("RGB"))
