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

from .config import W, H, FPS
from .noise import noise_field_frames, noise_gradient, fractal_noise2d


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
    or subtle atmospheric light change. Very subtle (±3% brightness). Driven
    by a small dedicated fractal noise field (sampled at a fixed cell each
    frame) instead of a single sine wave, for a more organic, non-repeating
    breathing pattern — appears in every theme (17/17), so this is the
    highest-reach of the noise-driven cozy_fx upgrades.
    """
    def __init__(self, n_frames: int, rng_seed: int = 1):
        # Window region: upper-right quadrant (typical scene composition)
        self.wx0 = W // 2
        self.wy0 = 0
        self.wx1 = W
        self.wy1 = H // 2
        self._n_frames = max(1, n_frames)
        # Small field (32x32): a small field needs proportionally large
        # warp_amp so a fixed-point sample actually changes frame-to-frame.
        self._field_get = noise_field_frames(32, 32, self._n_frames, octaves=3,
                                              base_res=4, warp_amp=2.5, seed=rng_seed + 4000)

    def render(self, frame: np.ndarray, t: float) -> np.ndarray:
        frame_idx = int(round(t * FPS)) % self._n_frames
        val = float(self._field_get(frame_idx)[16, 16])   # [0,1]
        breath = 1.0 + 0.028 * (val * 2 - 1)               # remap to ±0.028
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
    Simulates the subtle brightness variation of a real flame: a slow,
    organic base wander driven by a small dedicated noise field (replacing
    the old 4-sine sum), plus one residual fast sine harmonic layered on top
    for the quick micro-flicker a candle physically has — a low-res orbiting
    noise field alone under-represents that fast component. Appears in
    11/17 themes.
    """
    def __init__(self, n_frames: int, rng_seed: int = 3):
        rng = random.Random(rng_seed)
        # Lamp position: lower-left of frame (typical desk lamp position in scene)
        self.cx = int(W * 0.22)
        self.cy = int(H * 0.62)
        self.radius = 320
        self._n_frames = max(1, n_frames)
        self._field_get = noise_field_frames(24, 24, self._n_frames, octaves=3,
                                              base_res=4, warp_amp=3.0, seed=rng_seed + 5000)
        self.micro_phase = rng.uniform(0, math.pi * 2)
        self.micro_speed = rng.uniform(6.0, 9.0)
        self.micro_amp   = rng.uniform(0.008, 0.015)

    def render(self, frame: np.ndarray, t: float) -> np.ndarray:
        frame_idx = int(round(t * FPS)) % self._n_frames
        val = float(self._field_get(frame_idx)[12, 12])   # [0,1]
        noise_delta = (val * 2 - 1) * 0.05
        micro_delta = self.micro_amp * math.sin(t * self.micro_speed * 2 * math.pi + self.micro_phase)
        flicker = 1.0 + noise_delta + micro_delta
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
    Curling wisps of steam rising from the mug area. Rendered as soft white
    alpha blobs drifting upward, wandering along a shared static curl-noise
    flow field (same technique as SnowFall/PetalDrift/particles.FloatingOrbs)
    instead of a single sine wobble — turbulent curling is exactly what
    curl-noise models, arguably an even better conceptual fit here than for
    snow or petals.
    """
    def __init__(self, n_frames: int, rng_seed: int = 4, n_wisps: int = 5):
        rng = random.Random(rng_seed)
        self.wisps = []
        for _ in range(n_wisps):
            self.wisps.append({
                "x0":      rng.randint(int(W * 0.18), int(W * 0.28)),
                "speed":   rng.uniform(22, 40),          # px/sec upward
                "wobble_a": rng.uniform(6, 18),           # wander strength
                "life":    rng.uniform(1.5, 3.5),        # seconds per cycle
                "offset":  rng.uniform(0, 3.5),
            })
        self._field_w, self._field_h = 24, 24
        field = fractal_noise2d(self._field_h, self._field_w, octaves=3,
                                 seed=rng_seed + 8000, tileable=(True, True))
        _dy, dx = noise_gradient(field)
        self._flow_dx = dx

    def _wind_at(self, x: float, y: float) -> float:
        fx = int((x / W) * self._field_w) % self._field_w
        fy = int((max(0, min(H - 1, y)) / H) * self._field_h) % self._field_h
        return float(self._flow_dx[fy, fx])

    def render(self, frame: np.ndarray, t: float) -> np.ndarray:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d  = ImageDraw.Draw(ov)
        for w in self.wisps:
            age   = (t + w["offset"]) % w["life"]
            frac  = age / w["life"]                         # 0→1 over lifetime
            y     = int(H * 0.62 - w["speed"] * age * 2)   # rises up
            wander = self._wind_at(w["x0"], y) * w["wobble_a"] * 30
            x     = w["x0"] + int(wander)
            alpha = int(80 * math.sin(frac * math.pi))      # fade in/out
            size  = int(4 + frac * 8)
            if 0 < y < H and alpha > 5:
                d.ellipse([x - size, y - size, x + size, y + size],
                          fill=(240, 240, 250, alpha))
        ov_blur = ov.filter(ImageFilter.GaussianBlur(radius=4))
        return _paste_rgba(frame, np.array(ov_blur))


# ── Fireflies ─────────────────────────────────────────────────────────────────

class FireflyField:
    """
    Drifting warm golden-green glowing points of light. Curl-noise-driven
    wander (own shared static flow field, same technique as SnowFall/
    PetalDrift, but sampling both gradient components since fireflies wander
    in both x and y rather than just falling) layered on top of each fly's
    base linear drift, so paths meander instead of moving in dead-straight
    lines.
    """
    def __init__(self, n_frames: int, rng_seed: int = 5, count: int = 22):
        rng = random.Random(rng_seed)
        self.flies = []
        for _ in range(count):
            self.flies.append({
                "x": rng.uniform(0.3, 1.0) * W,
                "y": rng.uniform(0.2, 0.9) * H,
                "base_vx": rng.uniform(-8, 8),
                "base_vy": rng.uniform(-6, 6),
                "blink_f": rng.uniform(0.3, 1.2),
                "blink_p": rng.uniform(0, math.pi * 2),
                "col": rng.choice([(255, 240, 80), (180, 255, 100), (255, 220, 40)]),
                "size": rng.uniform(2, 5),
            })
        self._field_w, self._field_h = 24, 24
        field = fractal_noise2d(self._field_h, self._field_w, octaves=3,
                                 seed=rng_seed + 9000, tileable=(True, True))
        dy, dx = noise_gradient(field)
        self._flow_dx = dx
        self._flow_dy = dy

    def _flow_at(self, x: float, y: float) -> tuple:
        fx = int((x / W) * self._field_w) % self._field_w
        fy = int((y / H) * self._field_h) % self._field_h
        return float(self._flow_dx[fy, fx]), float(self._flow_dy[fy, fx])

    def render(self, frame: np.ndarray, t: float) -> np.ndarray:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d  = ImageDraw.Draw(ov)
        for fly in self.flies:
            x0 = (fly["x"] + fly["base_vx"] * t) % W
            y0 = (fly["y"] + fly["base_vy"] * t) % H
            wx, wy = self._flow_at(x0, y0)
            x = (x0 + wx * 220) % W
            y = (y0 + wy * 220) % H
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
    """
    Slow-drifting white snowflakes outside the window. Terminal-velocity
    fall model (v(t) = v_term*(1-exp(-t/tau)) — light objects reach terminal
    velocity almost immediately, the physically-correct regime for snow,
    unlike RainOverlay's unbounded gravity accel which is right for heavier
    drops) instead of instant constant-velocity, plus curl-noise wind (one
    shared static flow field per instance, same technique as
    particles.FloatingOrbs) sampled at each flake's current position, so
    nearby flakes drift together during a "gust" instead of each having an
    independently-phased sine wobble.
    """
    def __init__(self, n_frames: int, rng_seed: int = 6, count: int = 80):
        rng = random.Random(rng_seed)
        self.flakes = []
        for _ in range(count):
            v_term = rng.uniform(15, 45)
            tau = rng.uniform(0.15, 0.4)
            fall_distance = H + 40
            # tau << fall_distance/v_term here, so this is an excellent
            # approximation of the true (transcendental) period.
            fall_period = fall_distance / v_term + tau
            self.flakes.append({
                "x":       rng.uniform(0.45, 1.0) * W,   # window region
                "phase":   rng.uniform(0, fall_period),
                "v_term":  v_term,
                "tau":     tau,
                "fall_period": fall_period,
                "drift":   rng.uniform(-8, 8),
                "size":    rng.uniform(1.5, 4),
                "alpha":   rng.randint(60, 160),
            })
        self._field_w, self._field_h = 32, 18
        field = fractal_noise2d(self._field_h, self._field_w, octaves=3,
                                 seed=rng_seed + 6000, tileable=(True, True))
        _dy, dx = noise_gradient(field)
        self._flow_dx = dx

    def _wind_at(self, x: float, y: float) -> float:
        fx = int((x / W) * self._field_w) % self._field_w
        fy = int((y / H) * self._field_h) % self._field_h
        return float(self._flow_dx[fy, fx])

    def render(self, frame: np.ndarray, t: float) -> np.ndarray:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d  = ImageDraw.Draw(ov)
        for flake in self.flakes:
            t_local = (t + flake["phase"]) % flake["fall_period"]
            y = -20 + flake["v_term"] * (t_local - flake["tau"] * (1 - math.exp(-t_local / flake["tau"])))
            wind_offset = self._wind_at(flake["x"], y % H) * 250
            x = (flake["x"] + flake["drift"] * t + wind_offset) % W
            s = flake["size"]
            d.ellipse([x - s, y - s, x + s, y + s],
                      fill=(240, 248, 255, flake["alpha"]))
        ov_soft = ov.filter(ImageFilter.GaussianBlur(radius=1))
        return _paste_rgba(frame, np.array(ov_soft))


# ── Petal drift (autumn leaves / sakura) ─────────────────────────────────────

class PetalDrift:
    """
    Drifting petals — maple leaves (autumn) or sakura (spring/sakura_night).
    Terminal-velocity fall (same physical model as SnowFall) + curl-noise
    wind (own shared static flow field) instead of a sine wobble. Real
    rotation instead of the old fake squash-only "angle_factor" (which only
    ever scaled ellipse width, never actually rotated the shape): ~24
    pre-rotated RGBA sprite tiles are rendered once per (size, color) in
    __init__ and picked by phase each frame — zero per-frame Image.rotate
    calls, same "precompute once" philosophy as scene.make_vinyl_label_frames.
    """
    _N_TILES = 24

    def __init__(self, n_frames: int, rng_seed: int = 7,
                 count: int = 18, sakura: bool = False):
        rng = random.Random(rng_seed)
        self.sakura = sakura
        self.petals = []
        for _ in range(count):
            v_term = rng.uniform(20, 55)
            tau = rng.uniform(0.3, 0.6)
            fall_distance = H + 60
            fall_period = fall_distance / v_term + tau
            self.petals.append({
                "x":          rng.uniform(0, W),
                "phase":      rng.uniform(0, fall_period),
                "v_term":     v_term,
                "tau":        tau,
                "fall_period": fall_period,
                "drift":      rng.uniform(-25, 25),
                "spin_speed": rng.uniform(-1.5, 1.5),
                "spin_phase": rng.uniform(0, 1),
                "size":       rng.randint(4, 10),
                "alpha":      rng.randint(100, 200),
                "shade_pick": rng.random(),
            })

        self._field_w, self._field_h = 32, 18
        field = fractal_noise2d(self._field_h, self._field_w, octaves=3,
                                 seed=rng_seed + 7000, tileable=(True, True))
        _dy, dx = noise_gradient(field)
        self._flow_dx = dx

        self._sprite_cache: dict = {}

    def _get_sprites(self, size: int, color: tuple) -> list:
        key = (size, color)
        if key not in self._sprite_cache:
            base = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
            bd = ImageDraw.Draw(base)
            bd.ellipse([size, int(size * 1.4), size * 3, int(size * 2.6)], fill=color)
            self._sprite_cache[key] = [
                base.rotate(i * 360 / self._N_TILES, resample=Image.BILINEAR)
                for i in range(self._N_TILES)
            ]
        return self._sprite_cache[key]

    def _wind_at(self, x: float, y: float) -> float:
        fx = int((x / W) * self._field_w) % self._field_w
        fy = int((y / H) * self._field_h) % self._field_h
        return float(self._flow_dx[fy, fx])

    def render(self, frame: np.ndarray, t: float) -> np.ndarray:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for p in self.petals:
            t_local = (t + p["phase"]) % p["fall_period"]
            y = -30 + p["v_term"] * (t_local - p["tau"] * (1 - math.exp(-t_local / p["tau"])))
            wind_offset = self._wind_at(p["x"], y % H) * 200
            x = (p["x"] + p["drift"] * t + wind_offset) % W

            if self.sakura:
                col = (255, 182, 193, p["alpha"])  # pink
            else:
                # Autumn: mix of orange/red/brown
                shade = p["shade_pick"]
                if shade < 0.33:
                    col = (220, 80, 30, p["alpha"])   # orange-red
                elif shade < 0.66:
                    col = (200, 120, 20, p["alpha"])  # amber
                else:
                    col = (160, 60, 20, p["alpha"])   # deep red

            sprites = self._get_sprites(p["size"], col)
            tile_idx = int((t * p["spin_speed"] + p["spin_phase"]) * self._N_TILES) % self._N_TILES
            sprite = sprites[tile_idx]
            ov.paste(sprite, (int(x - sprite.width / 2), int(y - sprite.height / 2)), sprite)

        return _paste_rgba(frame, np.array(ov))


# ── Neon pulse (neon_tokyo) ───────────────────────────────────────────────────

class NeonPulse:
    """
    Pulsing coloured light from an off-screen neon sign — hue cycles slowly
    between pink and cyan, casting a faint glow on the left edge of frame.
    Driven by a small dedicated fractal noise field (same fixed-cell-sample
    technique as WindowGlow) instead of a single sine wave, for an organic
    non-repeating pulse — lowest priority of the cozy_fx upgrades (narrowest
    theme reach, 3/17, and the old sine already read as intentionally
    synthetic for a neon sign), so it keeps a residual sine term blended in
    for the sign's characteristic electric "buzz".
    """
    def __init__(self, n_frames: int, rng_seed: int = 8):
        rng = random.Random(rng_seed)
        self.phase = rng.uniform(0, math.pi * 2)
        self.speed = 0.12  # hue rotation cycles per second
        self._n_frames = max(1, n_frames)
        self._field_get = noise_field_frames(24, 24, self._n_frames, octaves=3,
                                              base_res=4, warp_amp=2.0, seed=rng_seed + 10000)

    def render(self, frame: np.ndarray, t: float) -> np.ndarray:
        frame_idx = int(round(t * FPS)) % self._n_frames
        val = float(self._field_get(frame_idx)[12, 12])   # [0,1]
        hue_pos = 0.5 + 0.5 * math.sin((val * 2 - 1) * math.pi + self.phase)
        # Lerp pink (255,20,180) → cyan (0,220,255)
        r = int(255 * (1 - hue_pos))
        g = int(20  + 200 * hue_pos)
        b = int(180 + 75  * hue_pos)
        intensity = 0.06 + 0.02 * (val * 2 - 1) + 0.015 * math.sin(t * 2.7 + self.phase)
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
