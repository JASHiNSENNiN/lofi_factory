"""
particles.py — Floating orb atmosphere particles for the abstract interface.
"""

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
        # Position, size, alpha
        self.px  = rng.uniform(0, W, n).astype(np.float32)
        self.py  = rng.uniform(0, H, n).astype(np.float32)
        self.r   = rng.uniform(28, 180, n).astype(np.float32)
        self.alp = rng.uniform(0.03, 0.12, n).astype(np.float32)
        self.speed = rng.uniform(0.15, 0.5, n).astype(np.float32)

        # Curl-noise flow field: a static fractal field whose spatial gradient
        # (dy, -dx) is divergence-free, producing swirly current-like drift —
        # replaces the old constant-velocity + single-axis sine wobble.
        from .noise import fractal_noise2d, noise_gradient
        self._field_h = max(4, H // 8)
        self._field_w = max(4, W // 8)
        field = fractal_noise2d(self._field_h, self._field_w, octaves=3,
                                 seed=rng_seed + 900, tileable=(True, True))
        dy, dx = noise_gradient(field)
        self._flow_dy = dy
        self._flow_dx = dx

    def _flow_direction(self, px: np.ndarray, py: np.ndarray):
        """Unit-length curl-noise flow direction (vx, vy) at given positions."""
        fy = (py / H * self._field_h).astype(np.int32) % self._field_h
        fx = (px / W * self._field_w).astype(np.int32) % self._field_w
        vy = self._flow_dy[fy, fx]
        vx = -self._flow_dx[fy, fx]
        mag = np.sqrt(vx ** 2 + vy ** 2) + 1e-6
        return vx / mag, vy / mag

    def update(self, t: float) -> None:
        dir_x, dir_y = self._flow_direction(self.px, self.py)
        self.px = (self.px + dir_x * self.speed) % W
        self.py = (self.py + dir_y * self.speed) % H

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
