"""
cozy_fx.py — Animated cozy atmosphere effects rendered per-frame in Python.

These run on top of the AI background scene to add life and prevent "static image"
feel. All effects are subtle — viewers should feel the atmosphere, not notice the FX.

Effects:
  RainOverlay     — vertical streaks on window glass (interior themes)
  CandleFlicker   — warm pulsing glow from a fixed position (replaces static lamp)
  SteamRiser      — curling wisps of steam rising from a cup/mug area
  FireflyField    — drifting warm points of light (summer / forest themes)
  SnowFall        — slow-drifting snowflakes (winter theme)
  PetalDrift      — falling cherry blossom petals (sakura / spring themes)
  WindowGlow      — gentle breathing light from outside window (all themes)
  DepthBreath     — very subtle zoom-in/out on bg to give depth illusion
"""

import math
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .config import W, H


# ── Theme → effect mapping ─────────────────────────────────────────────────────
# Each theme gets a list of effect names to layer. Effects are ordered bg→fg.

THEME_FX = {
    "cozy_rain":     ["window_glow", "rain", "steam", "candle"],
    "midnight_cafe": ["window_glow", "rain", "steam", "candle"],
    "purple_dusk":   ["window_glow", "firefly", "candle"],
    "amber_night":   ["window_glow", "candle", "steam"],
    "winter_snow":   ["window_glow", "snow", "candle", "steam"],
    "autumn_study":  ["window_glow", "petal_fall", "candle", "steam"],
    "spring_dawn":   ["window_glow", "petal_sakura", "steam"],
    "neon_tokyo":    ["window_glow", "rain", "neon_pulse"],
    "summer_lofi":   ["window_glow", "firefly", "steam"],
    "blue_hour":     ["window_glow", "candle"],
    "forest_rain":   ["window_glow", "rain", "firefly"],
    "sakura_night":  ["window_glow", "petal_sakura", "candle"],
    # New subgenre themes
    "vaporwave":     ["window_glow", "neon_pulse", "rain"],
    "lofi_house":    ["window_glow", "neon_pulse", "firefly"],
    "lofi_classical":["window_glow", "candle", "steam"],
    "bedroom_pop":   ["window_glow", "petal_fall", "candle"],
    "lofi_rnb":      ["window_glow", "candle", "steam"],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _alpha_blend(base: np.ndarray, overlay: np.ndarray, alpha: float) -> np.ndarray:
    """Blend overlay (RGB) onto base (RGB) with scalar alpha [0,1]."""
    return np.clip(
        base.astype(np.float32) * (1 - alpha)
        + overlay.astype(np.float32) * alpha,
        0, 255
    ).astype(np.uint8)


def _paste_rgba(base: np.ndarray, rgba: np.ndarray) -> np.ndarray:
    """Alpha-composite an RGBA overlay onto RGB base."""
    a = rgba[:, :, 3:4].astype(np.float32) / 255.0
    rgb = rgba[:, :, :3].astype(np.float32)
    result = base.astype(np.float32) * (1 - a) + rgb * a
    return np.clip(result, 0, 255).astype(np.uint8)


# ── Window ambient glow ───────────────────────────────────────────────────────

class WindowGlow:
    """
    Gentle breathing light from the window area — simulates clouds passing
    or subtle atmospheric light change. Very subtle (±3% brightness).
    """
    def __init__(self, n_frames: int, rng_seed: int = 1):
        rng = random.Random(rng_seed)
        # Window region: upper-right quadrant (typical scene composition)
        self.wx0 = W // 2
        self.wy0 = 0
        self.wx1 = W
        self.wy1 = H // 2
        # Random phase and speed
        self.phase = rng.uniform(0, math.pi * 2)
        self.speed = rng.uniform(0.08, 0.18)  # cycles per second

    def render(self, frame: np.ndarray, t: float) -> np.ndarray:
        breath = 1.0 + 0.028 * math.sin(t * self.speed * 2 * math.pi + self.phase)
        result = frame.copy().astype(np.float32)
        region = result[self.wy0:self.wy1, self.wx0:self.wx1]
        result[self.wy0:self.wy1, self.wx0:self.wx1] = np.clip(region * breath, 0, 255)
        return result.astype(np.uint8)


# ── Rain ─────────────────────────────────────────────────────────────────────

class RainOverlay:
    """
    Rain streaks on a virtual window pane — white-blue translucent vertical
    streaks, physically modeled: gravity-accelerated fall (not constant
    velocity) with a per-drop depth factor for parallax (nearer drops fall
    faster and render bigger/sharper; farther drops fall slower and render
    smaller/softer). Only renders in window area.
    """
    _G_BASE = 900.0  # base gravity, px/s^2 (scaled per-drop by depth)

    def __init__(self, n_frames: int, rng_seed: int = 2, density: int = 60):
        rng = random.Random(rng_seed)
        self.drops = []
        for _ in range(density):
            depth = rng.uniform(0.6, 1.4)   # >1 = nearer/faster/bigger, <1 = farther
            drop_len = rng.randint(12, 45)
            g = self._G_BASE * depth
            fall_distance = H + drop_len
            fall_period = math.sqrt(2 * fall_distance / g)   # free-fall-from-rest period
            self.drops.append({
                "x":            rng.randint(W // 2, W - 50),   # right half (window)
                "phase":        rng.uniform(0, fall_period),   # stagger start times
                "len":          drop_len,
                "g":            g,
                "fall_period":  fall_period,
                "depth":        depth,
                "alpha":        rng.uniform(30, 90) * min(1.0, depth),
                "width":        1 if depth < 1.05 else 2,
                "waver_amp":    rng.uniform(2, 4) * depth,
            })

    def render(self, frame: np.ndarray, t: float) -> np.ndarray:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d  = ImageDraw.Draw(ov)
        for drop in self.drops:
            t_mod = (t + drop["phase"]) % drop["fall_period"]
            # Gravity-accelerated fall from rest: y(t) = y0 + 0.5*g*t^2.
            # At t_mod=0, y=-len (just above frame); at t_mod=fall_period,
            # y=H (exits bottom) — matches how fall_period was derived.
            y = -drop["len"] + 0.5 * drop["g"] * t_mod ** 2
            x = drop["x"] + int(math.sin(y * 0.05) * drop["waver_amp"])
            length = drop["len"] * (0.85 + 0.3 * drop["depth"])
            d.line([(x, int(y)), (x + 1, int(y + length))],
                   fill=(200, 220, 255, int(drop["alpha"])),
                   width=drop["width"])
        # Slight softening so streaks read as glass-refracted rain rather
        # than crisp vector lines.
        ov = ov.filter(ImageFilter.GaussianBlur(radius=0.6))
        return _paste_rgba(frame, np.array(ov))


# ── Candle flicker ────────────────────────────────────────────────────────────

class CandleFlicker:
    """
    Warm pulsing glow radiating from the desk-lamp / candle region.
    Simulates the subtle brightness variation of a real flame.
    """
    def __init__(self, n_frames: int, rng_seed: int = 3):
        rng = random.Random(rng_seed)
        # Lamp position: lower-left of frame (typical desk lamp position in scene)
        self.cx = int(W * 0.22)
        self.cy = int(H * 0.62)
        self.radius = 320
        self.phases = [rng.uniform(0, math.pi * 2) for _ in range(4)]
        self.speeds  = [rng.uniform(1.5, 4.5) for _ in range(4)]
        self.amps    = [rng.uniform(0.015, 0.04) for _ in range(4)]

    def render(self, frame: np.ndarray, t: float) -> np.ndarray:
        # Flicker = sum of sine waves at different frequencies
        flicker = 1.0 + sum(
            a * math.sin(t * s * 2 * math.pi + p)
            for a, s, p in zip(self.amps, self.speeds, self.phases)
        )
        # Radial warm glow mask
        ys = np.arange(H, dtype=np.float32)
        xs = np.arange(W, dtype=np.float32)
        xx, yy = np.meshgrid(xs, ys)
        dist = np.sqrt((xx - self.cx)**2 + (yy - self.cy)**2)
        glow = np.clip(1.0 - dist / self.radius, 0, 1) ** 2
        glow *= (flicker - 1.0) * 0.6  # strength
        result = frame.astype(np.float32)
        # Warm glow: boost red/green, suppress blue
        result[:, :, 0] = np.clip(result[:, :, 0] + glow * 40, 0, 255)
        result[:, :, 1] = np.clip(result[:, :, 1] + glow * 18, 0, 255)
        result[:, :, 2] = np.clip(result[:, :, 2] - glow * 8,  0, 255)
        return result.astype(np.uint8)


# ── Steam ─────────────────────────────────────────────────────────────────────

class SteamRiser:
    """
    Curling wisps of steam rising from the mug area.
    Rendered as soft white alpha blobs drifting upward.
    """
    def __init__(self, n_frames: int, rng_seed: int = 4, n_wisps: int = 5):
        rng = random.Random(rng_seed)
        self.wisps = []
        for _ in range(n_wisps):
            self.wisps.append({
                "x0":    rng.randint(int(W * 0.18), int(W * 0.28)),
                "phase": rng.uniform(0, math.pi * 2),
                "speed": rng.uniform(22, 40),          # px/sec upward
                "wobble_f": rng.uniform(0.5, 1.5),     # Hz
                "wobble_a": rng.uniform(6, 18),         # px amplitude
                "life":  rng.uniform(1.5, 3.5),        # seconds per cycle
                "offset":rng.uniform(0, 3.5),
            })

    def render(self, frame: np.ndarray, t: float) -> np.ndarray:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d  = ImageDraw.Draw(ov)
        for w in self.wisps:
            age   = (t + w["offset"]) % w["life"]
            frac  = age / w["life"]                         # 0→1 over lifetime
            y     = int(H * 0.62 - w["speed"] * age * 2)   # rises up
            x     = w["x0"] + int(w["wobble_a"] * math.sin(t * w["wobble_f"] * 2 * math.pi + w["phase"]))
            alpha = int(80 * math.sin(frac * math.pi))      # fade in/out
            size  = int(4 + frac * 8)
            if 0 < y < H and alpha > 5:
                d.ellipse([x - size, y - size, x + size, y + size],
                          fill=(240, 240, 250, alpha))
        ov_blur = ov.filter(ImageFilter.GaussianBlur(radius=4))
        return _paste_rgba(frame, np.array(ov_blur))


# ── Fireflies ─────────────────────────────────────────────────────────────────

class FireflyField:
    """Drifting warm golden-green glowing points of light."""
    def __init__(self, n_frames: int, rng_seed: int = 5, count: int = 22):
        rng = random.Random(rng_seed)
        self.flies = []
        for _ in range(count):
            self.flies.append({
                "x": rng.uniform(0.3, 1.0) * W,
                "y": rng.uniform(0.2, 0.9) * H,
                "vx": rng.uniform(-8, 8),
                "vy": rng.uniform(-6, 6),
                "blink_f": rng.uniform(0.3, 1.2),
                "blink_p": rng.uniform(0, math.pi * 2),
                "col": rng.choice([(255, 240, 80), (180, 255, 100), (255, 220, 40)]),
                "size": rng.uniform(2, 5),
            })

    def render(self, frame: np.ndarray, t: float) -> np.ndarray:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d  = ImageDraw.Draw(ov)
        for fly in self.flies:
            x = (fly["x"] + fly["vx"] * t) % W
            y = (fly["y"] + fly["vy"] * t) % H
            blink = (math.sin(t * fly["blink_f"] * 2 * math.pi + fly["blink_p"]) + 1) / 2
            alpha = int(blink ** 2 * 200)
            if alpha < 10:
                continue
            r, g, b = fly["col"]
            s = fly["size"]
            # Outer glow
            for gs, ga in [(s * 3.5, alpha // 5), (s * 2, alpha // 3), (s, alpha)]:
                d.ellipse([x - gs, y - gs, x + gs, y + gs],
                          fill=(r, g, b, ga))
        return _paste_rgba(frame, np.array(ov))


# ── Snow ─────────────────────────────────────────────────────────────────────

class SnowFall:
    """Slow-drifting white snowflakes outside the window."""
    def __init__(self, n_frames: int, rng_seed: int = 6, count: int = 80):
        rng = random.Random(rng_seed)
        self.flakes = []
        for _ in range(count):
            self.flakes.append({
                "x": rng.uniform(0.45, 1.0) * W,  # window region
                "y": rng.uniform(-H, H),
                "speed": rng.uniform(15, 45),
                "drift": rng.uniform(-8, 8),
                "size": rng.uniform(1.5, 4),
                "alpha": rng.randint(60, 160),
                "phase": rng.uniform(0, math.pi * 2),
            })

    def render(self, frame: np.ndarray, t: float) -> np.ndarray:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d  = ImageDraw.Draw(ov)
        for flake in self.flakes:
            y   = (flake["y"] + flake["speed"] * t) % (H + 20) - 20
            x   = flake["x"] + flake["drift"] * t + flake["size"] * 4 * math.sin(t * 0.3 + flake["phase"])
            x   = x % W
            s   = flake["size"]
            d.ellipse([x - s, y - s, x + s, y + s],
                      fill=(240, 248, 255, flake["alpha"]))
        ov_soft = ov.filter(ImageFilter.GaussianBlur(radius=1))
        return _paste_rgba(frame, np.array(ov_soft))


# ── Petal drift (autumn leaves / sakura) ─────────────────────────────────────

class PetalDrift:
    """Drifting petals — maple leaves (autumn) or sakura (spring/sakura_night)."""
    def __init__(self, n_frames: int, rng_seed: int = 7,
                 count: int = 18, sakura: bool = False):
        rng = random.Random(rng_seed)
        self.sakura = sakura
        self.petals = []
        for _ in range(count):
            self.petals.append({
                "x": rng.uniform(0, W),
                "y": rng.uniform(-H * 0.5, H),
                "speed_y": rng.uniform(20, 55),
                "speed_x": rng.uniform(-25, 25),
                "spin": rng.uniform(-2, 2),
                "phase": rng.uniform(0, math.pi * 2),
                "size": rng.randint(4, 10),
                "alpha": rng.randint(100, 200),
            })

    def render(self, frame: np.ndarray, t: float) -> np.ndarray:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d  = ImageDraw.Draw(ov)
        for p in self.petals:
            y = (p["y"] + p["speed_y"] * t) % (H + 30) - 30
            x = (p["x"] + p["speed_x"] * t + 20 * math.sin(t * 0.4 + p["phase"])) % W
            s = p["size"]
            if self.sakura:
                col = (255, 182, 193, p["alpha"])  # pink
            else:
                # Autumn: mix of orange/red/brown
                shade = (p["phase"] % 1)
                if shade < 0.33:
                    col = (220, 80, 30, p["alpha"])   # orange-red
                elif shade < 0.66:
                    col = (200, 120, 20, p["alpha"])  # amber
                else:
                    col = (160, 60, 20, p["alpha"])   # deep red
            # Simple leaf/petal ellipse with rotation implied by squash
            angle_factor = math.cos(t * p["spin"] + p["phase"])
            w_half = max(1, int(s * abs(angle_factor)))
            h_half = s
            d.ellipse([x - w_half, y - h_half, x + w_half, y + h_half], fill=col)
        return _paste_rgba(frame, np.array(ov))


# ── Neon pulse (neon_tokyo) ───────────────────────────────────────────────────

class NeonPulse:
    """
    Pulsing coloured light from an off-screen neon sign — hue cycles slowly
    between pink and cyan, casting a faint glow on the left edge of frame.
    """
    def __init__(self, n_frames: int, rng_seed: int = 8):
        rng = random.Random(rng_seed)
        self.phase = rng.uniform(0, math.pi * 2)
        self.speed = 0.12  # hue rotation cycles per second

    def render(self, frame: np.ndarray, t: float) -> np.ndarray:
        hue_pos = (math.sin(t * self.speed * 2 * math.pi + self.phase) + 1) / 2
        # Lerp pink (255,20,180) → cyan (0,220,255)
        r = int(255 * (1 - hue_pos))
        g = int(20  + 200 * hue_pos)
        b = int(180 + 75  * hue_pos)
        intensity = 0.06 + 0.03 * math.sin(t * 2.7 + self.phase)
        # Left-edge gradient glow
        xs = np.linspace(1, 0, W, dtype=np.float32)[np.newaxis, :] ** 3
        ys = np.ones((H, 1), dtype=np.float32)
        mask = (xs * ys * intensity)[:, :, np.newaxis]
        glow = np.array([r, g, b], dtype=np.float32)
        result = frame.astype(np.float32)
        result = result * (1 - mask) + glow * mask
        return np.clip(result, 0, 255).astype(np.uint8)


# ── Factory ───────────────────────────────────────────────────────────────────

def build_fx(theme_name: str, n_frames: int, rng_seed: int = 0) -> list:
    """Return list of effect objects for this theme, ready to .render(frame, t)."""
    fx_names = THEME_FX.get(theme_name, ["window_glow", "candle"])
    fx = []
    seed_offset = 0
    for name in fx_names:
        s = rng_seed + seed_offset
        if name == "window_glow":
            fx.append(WindowGlow(n_frames, rng_seed=s))
        elif name == "rain":
            fx.append(RainOverlay(n_frames, rng_seed=s, density=55))
        elif name == "candle":
            fx.append(CandleFlicker(n_frames, rng_seed=s))
        elif name == "steam":
            fx.append(SteamRiser(n_frames, rng_seed=s))
        elif name == "firefly":
            fx.append(FireflyField(n_frames, rng_seed=s, count=20))
        elif name == "snow":
            fx.append(SnowFall(n_frames, rng_seed=s, count=70))
        elif name == "petal_fall":
            fx.append(PetalDrift(n_frames, rng_seed=s, count=16, sakura=False))
        elif name == "petal_sakura":
            fx.append(PetalDrift(n_frames, rng_seed=s, count=18, sakura=True))
        elif name == "neon_pulse":
            fx.append(NeonPulse(n_frames, rng_seed=s))
        seed_offset += 100
    return fx
