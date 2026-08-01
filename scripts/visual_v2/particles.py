"""
particles.py — Floating orb atmosphere particles for the abstract interface.
"""

import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .config import W, H, ORB_COUNT
from .themes import THEMES


class FloatingOrbs:
    """
    Soft glowing circles that drift slowly across the frame.
    Gives the background depth and atmosphere.
    """

    def __init__(self, n: int = ORB_COUNT, rng_seed: int = 0):
        rng = np.random.RandomState(rng_seed)
        self.n  = n
        # Position, velocity, size, alpha, hue-offset
        self.px  = rng.uniform(0, W, n).astype(np.float32)
        self.py  = rng.uniform(0, H, n).astype(np.float32)
        self.vx  = rng.uniform(-0.18, 0.18, n).astype(np.float32)
        self.vy  = rng.uniform(-0.12, 0.12, n).astype(np.float32)
        self.r   = rng.uniform(28, 180, n).astype(np.float32)
        self.alp = rng.uniform(0.03, 0.12, n).astype(np.float32)
        # Sine drift params (slow)
        self.dr_amp   = rng.uniform(18, 80, n).astype(np.float32)
        self.dr_freq  = rng.uniform(0.20, 0.65, n).astype(np.float32)
        self.dr_phase = rng.uniform(0, 2 * math.pi, n).astype(np.float32)
        self.dr_axis  = rng.randint(0, 2, n)  # 0=x drift, 1=y drift

    def update(self, t: float) -> None:
        drift = self.dr_amp * np.sin(self.dr_freq * t + self.dr_phase)
        x_mask = self.dr_axis == 0
        self.px = np.where(x_mask, (self.px + self.vx + drift * 0.003) % W, self.px)
        self.py = np.where(~x_mask, (self.py + self.vy + drift * 0.003) % H, self.py)

    def render(self, frame: np.ndarray, theme: str) -> None:
        c      = THEMES[theme]
        accent = np.array(c["accent"], dtype=np.float32)

        for i in range(self.n):
            cx = int(self.px[i]); cy = int(self.py[i])
            r  = int(self.r[i]); alp = self.alp[i]

            y0 = max(0, cy - r); y1 = min(H, cy + r)
            x0 = max(0, cx - r); x1 = min(W, cx + r)
            if y1 <= y0 or x1 <= x0:
                continue

            # Radial gradient mask
            ys = np.arange(y0, y1)[:, None] - cy
            xs = np.arange(x0, x1)[None, :] - cx
            dist = np.sqrt(ys**2 + xs**2)
            mask = np.clip(1.0 - dist / (r + 1e-6), 0, 1).astype(np.float32)
            mask = mask ** 2.2  # softer falloff

            region = frame[y0:y1, x0:x1].astype(np.float32)
            for ch in range(3):
                region[:, :, ch] += mask * accent[ch] * alp
            frame[y0:y1, x0:x1] = np.clip(region, 0, 255).astype(np.uint8)


class MusicNotes:
    """
    Small ♪ symbols that float upward, theme-coloured.
    Optional atmospheric touch — 8 active notes at a time.
    """

    def __init__(self, rng_seed: int = 0):
        rng = np.random.RandomState(rng_seed)
        n = 8
        self.px  = rng.uniform(W * 0.15, W * 0.85, n).astype(np.float32)
        self.py  = rng.uniform(H * 0.3, H * 0.9, n).astype(np.float32)
        self.vy  = rng.uniform(0.25, 0.70, n).astype(np.float32)
        self.life = rng.uniform(0, 1, n).astype(np.float32)   # 0-1 phase
        self.life_spd = rng.uniform(0.0012, 0.0030, n).astype(np.float32)
        self.symbols = ["♪", "♫", "♩", "♬"]
        self.sym_idx = rng.randint(0, 4, n)
        self._font = None

    def _get_font(self):
        if self._font is not None:
            return self._font
        from PIL import ImageFont
        import os
        for path in [
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
        ]:
            if os.path.exists(path):
                try:
                    self._font = ImageFont.truetype(path, 20)
                    return self._font
                except Exception:
                    pass
        self._font = ImageFont.load_default()
        return self._font

    def update(self) -> None:
        for i in range(len(self.py)):
            self.life[i] += self.life_spd[i]
            if self.life[i] >= 1.0:
                self.life[i] = 0.0
                self.py[i] = H * 0.9
            self.py[i] -= self.vy[i]

    def render(self, frame: np.ndarray, theme: str) -> None:
        c      = THEMES[theme]
        accent = c["accent"]
        pil    = Image.fromarray(frame)
        draw   = ImageDraw.Draw(pil, "RGBA")
        font   = self._get_font()

        for i in range(len(self.py)):
            alp = int(min(self.life[i], 1.0 - self.life[i]) * 2 * 180)
            if alp < 5:
                continue
            sym = self.symbols[self.sym_idx[i]]
            draw.text(
                (int(self.px[i]), int(self.py[i])),
                sym,
                fill=(*accent, alp),
                font=font,
            )

        frame[:] = np.array(pil.convert("RGB"))
