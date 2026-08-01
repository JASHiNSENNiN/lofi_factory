"""
generate_visual_cozy.py  v3
---------------------------
Complete rewrite — fixes composition, item placement, and animation richness.

Key changes from v2:
  • Window centered (x=555-1355, 800px wide) — was far-left x=160-940
  • Cat, mug, candle all LEFT of window (x<555) — were INSIDE window region
  • Wide curtains (175px per side, 7 fold strips) — were 66px total
  • Tall 3-shelf bookshelf on left wall (227px wide) — was 48px sliver
  • Open laptop on desk (intentionally in front of window — correct lo-fi look)
  • Fairy lights strung above window (22 bulbs, individual flicker noise)
  • Rain-on-glass effect (slow drips on window pane, separate from outside rain)
  • Moon + stars visible through window
  • Plant with oscillating leaves (per-leaf phase noise)
  • Desk has perspective edge (front face visible)
  • Floor/rug visible in foreground
  • Wainscoting on lower wall panels
  • Proper cast shadows under each desk item

Themes: cozy_rain | midnight_cafe | purple_dusk | amber_night
Output: visuals/bg_{theme}_{ts}.mp4  1920×1080 @ 24 fps
"""

import os, sys, subprocess, datetime, math, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import cairo as _cairo

# ── Resolution & paths ──────────────────────────────────────────────────────
W, H   = 1920, 1080
FPS    = 24
VISUALS_DIR = os.path.join(os.path.dirname(__file__), "..", "visuals")
os.makedirs(VISUALS_DIR, exist_ok=True)

# ── SCENE GEOMETRY ───────────────────────────────────────────────────────────
# Window — large, centered: 800×640 px glass area
WIN_X0, WIN_Y0 = 555,  70     # glass top-left
WIN_X1, WIN_Y1 = 1355, 710    # glass bottom-right

DESK_Y      = 778              # desk surface top
DESK_FACE_H = 44               # depth of visible desk front face
FLOOR_Y     = DESK_Y + DESK_FACE_H   # where floor begins

# Curtains — wide panels framing window (175px each side)
LCURT_X0    = WIN_X0 - 175    # = 380   left curtain outer edge
LCURT_X1    = WIN_X0 + 30     # = 585   left curtain inner edge (slight overlap)
RCURT_X0    = WIN_X1 - 30     # = 1325  right curtain inner edge
RCURT_X1    = WIN_X1 + 175    # = 1530  right curtain outer edge

# ── DESK OBJECT POSITIONS ────────────────────────────────────────────────────
# LEFT desk zone (x < WIN_X0 = 555)
CAT_CX       = 278             # sleeping cat body centre x — body fits x≈113..498
CAT_CY       = DESK_Y - 26    # body centre y

CANDLE_X     = 330             # candle centre x — LEFT of curtain zone (curtain starts at x=380)
CANDLE_BASE  = DESK_Y

MUG_X        = 295             # mug centre x — LEFT of curtain zone
MUG_TOP      = DESK_Y - 98    # mug rim y

STACK_X      = 90              # stacked desk books left edge
STACK_Y      = DESK_Y

# CENTRE desk — laptop sits in front of window (correct for lo-fi)
LAPTOP_CX    = 900             # screen centre x
LAPTOP_Y     = DESK_Y         # base y

# RIGHT desk zone (x > WIN_X1 = 1355)
LAMP_X       = 1690            # lamp pole base x
LAMP_CY      = DESK_Y - 312   # shade centre y

HP_X         = 1492            # headphones centre x
HP_Y         = DESK_Y - 14

PLANT_X      = 1848            # succulent pot centre x
PLANT_Y      = DESK_Y

# Wall-mounted
CLOCK_CX     = 1618            # right wall clock centre x
CLOCK_CY     = 390             # right wall clock centre y

SHELF_X0     = 22              # left-wall bookshelf left edge
SHELF_X1     = 249             # left-wall bookshelf right edge
SHELF_BOT    = DESK_Y - 22    # bottom shelf panel y
SHELF_TOP    = 330             # top of bookshelf unit

# Fairy lights — strung across curtain rod above window
FAIRY_Y      = WIN_Y0 - 32    # string y
FAIRY_N      = 22              # number of bulbs

# Rain on glass — slow drips on window pane
GLASS_DRIP_N = 28

# Laptop exclusion zone — laptop is IN FRONT of window, rain must not render on it
# Screen geometry: keyboard width=360, screen top = DESK_Y - 2 - 295 = 481
LAPTOP_SCR_X0 = LAPTOP_CX - 182   # = 718
LAPTOP_SCR_X1 = LAPTOP_CX + 182   # = 1082
LAPTOP_SCR_Y0 = LAPTOP_Y - 297    # = 481 (top of screen panel)

# ── COLOUR PALETTES ──────────────────────────────────────────────────────────
# v3 pastel — walls at 40-50% lightness (anime-style: you see the hue at night)
THEMES = {
    "cozy_rain": {
        # Midnight Lavender — soft indigo-purple, visible walls
        "bg_top":     ( 45,  35,  70),   "bg_bot":     ( 30,  25,  55),
        "wall":       ( 95,  85, 130),   "wainscot":   (105,  94, 140),
        "shadow":     ( 55,  45,  88),
        "desk":       (140, 108,  72),   "desk_hl":    (168, 132,  90),
        "desk_face":  (112,  84,  54),   "desk_drk":   ( 88,  64,  38),
        "lamp_col":   (255, 218, 140),   "lamp_glow":  (255, 185,  95),
        "win_sky":    ( 62,  48, 108),   "win_low":    ( 82,  60, 145),
        "rain":       (185, 218, 248),   "rain_a":     52,
        "steam":      (210, 228, 248),
        "frame_col":  (115,  88,  58),   "sill_col":   (132, 105,  70),
        "curtain":    (182, 162, 210),   "curtain_hi": (208, 188, 232),
        "curtain_lo": (158, 138, 185),   "curtain_rod":(108,  84,  58),
        "rug_base":   (205, 155, 155),   "rug_brd":    (175, 120, 120),
        "floor":      (115,  85,  52),
        "fairy_col":  (255, 232, 148),
        "warmth_r":  8, "warmth_b": -4, "ao_str": 0.11,
    },
    "midnight_cafe": {
        # Warm Mauve — dusty rose walls, cozy blue-purple
        "bg_top":     ( 38,  30,  58),   "bg_bot":     ( 25,  20,  42),
        "wall":       ( 82,  72, 108),   "wainscot":   ( 92,  80, 118),
        "shadow":     ( 48,  38,  72),
        "desk":       (135, 102,  65),   "desk_hl":    (160, 122,  80),
        "desk_face":  (108,  80,  48),   "desk_drk":   ( 84,  58,  32),
        "lamp_col":   (255, 222, 148),   "lamp_glow":  (255, 192, 108),
        "win_sky":    ( 55,  42,  98),   "win_low":    ( 72,  55, 125),
        "rain":       (162, 192, 228),   "rain_a":     44,
        "steam":      (215, 232, 250),
        "frame_col":  ( 95,  72,  48),   "sill_col":   (112,  88,  58),
        "curtain":    (195, 168, 158),   "curtain_hi": (218, 192, 182),
        "curtain_lo": (170, 144, 135),   "curtain_rod":( 95,  72,  50),
        "rug_base":   (188, 148, 165),   "rug_brd":    (158, 118, 135),
        "floor":      (105,  78,  45),
        "fairy_col":  (255, 238, 168),
        "warmth_r":  8, "warmth_b": -4, "ao_str": 0.12,
    },
    "purple_dusk": {
        # Rose Bloom — magenta-lavender walls, soft pink accents
        "bg_top":     ( 55,  40,  88),   "bg_bot":     ( 38,  28,  68),
        "wall":       (118,  90, 148),   "wainscot":   (128, 100, 158),
        "shadow":     ( 72,  52, 105),
        "desk":       (148, 108,  88),   "desk_hl":    (175, 132, 110),
        "desk_face":  (118,  84,  65),   "desk_drk":   ( 92,  62,  46),
        "lamp_col":   (240, 198, 255),   "lamp_glow":  (215, 165, 250),
        "win_sky":    ( 78,  48, 130),   "win_low":    (105,  68, 165),
        "rain":       (200, 178, 238),   "rain_a":     46,
        "steam":      (228, 218, 250),
        "frame_col":  (125,  88, 115),   "sill_col":   (142, 105, 132),
        "curtain":    (218, 165, 198),   "curtain_hi": (238, 188, 218),
        "curtain_lo": (195, 142, 175),   "curtain_rod":(108,  78, 108),
        "rug_base":   (212, 162, 185),   "rug_brd":    (180, 130, 155),
        "floor":      (128,  88,  72),
        "fairy_col":  (228, 202, 255),
        "warmth_r":  4, "warmth_b": -2, "ao_str": 0.10,
    },
    "amber_night": {
        # Honey Dusk — warm dusty lavender walls, amber lamp
        "bg_top":     ( 50,  38,  65),   "bg_bot":     ( 35,  26,  48),
        "wall":       ( 98,  82, 115),   "wainscot":   (108,  90, 124),
        "shadow":     ( 62,  48,  80),
        "desk":       (158, 118,  68),   "desk_hl":    (185, 142,  85),
        "desk_face":  (128,  92,  48),   "desk_drk":   ( 98,  68,  32),
        "lamp_col":   (255, 205,  95),   "lamp_glow":  (255, 172,  58),
        "win_sky":    ( 58,  45,  92),   "win_low":    ( 80,  62, 118),
        "rain":       (210, 188, 165),   "rain_a":     54,
        "steam":      (232, 222, 205),
        "frame_col":  (125,  95,  60),   "sill_col":   (142, 112,  72),
        "curtain":    (192, 162, 122),   "curtain_hi": (215, 185, 145),
        "curtain_lo": (168, 138, 100),   "curtain_rod":( 98,  72,  45),
        "rug_base":   (210, 162, 148),   "rug_brd":    (178, 128, 112),
        "floor":      (122,  90,  48),
        "fairy_col":  (255, 225, 135),
        "warmth_r": 10, "warmth_b": -5, "ao_str": 0.11,
    },
}

# ══════════════════════════════════════════════════════════════════════════════
#  LOOPING NOISE
# ══════════════════════════════════════════════════════════════════════════════

def looping_noise(n_frames: int, n_harmonics: int = 6, seed: int = 0) -> np.ndarray:
    rng = np.random.RandomState(seed)
    t   = np.linspace(0, 2 * np.pi, n_frames, endpoint=False)
    sig = np.zeros(n_frames, dtype=np.float64)
    for h in range(1, n_harmonics + 1):
        amp   = 1.0 / h
        phase = rng.uniform(0, 2 * np.pi)
        sig  += amp * np.sin(h * t + phase)
    mn, mx = sig.min(), sig.max()
    return ((sig - mn) / (mx - mn)).astype(np.float32)

# ══════════════════════════════════════════════════════════════════════════════
#  STATIC PRE-COMPUTED LAYERS
# ══════════════════════════════════════════════════════════════════════════════

def make_gradient(theme: str) -> np.ndarray:
    c   = THEMES[theme]
    top = np.array(c["bg_top"], dtype=np.float32)
    bot = np.array(c["bg_bot"], dtype=np.float32)
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    for i in range(H):
        t = i / (H - 1)
        arr[i] = (top * (1 - t) + bot * t).astype(np.uint8)
    return arr


def make_bokeh_city(theme: str, seed: int = 7) -> np.ndarray:
    """Rich multi-layer city: sky gradient → moon → stars → 3 building layers → lit windows → street glow."""
    c   = THEMES[theme]
    rng = np.random.RandomState(seed)
    arr = np.zeros((H, W, 3), dtype=np.uint8)

    # Sky gradient inside window
    sky_top = np.array(c["win_sky"], dtype=np.float32)
    sky_bot = np.array(c["win_low"], dtype=np.float32)
    for i in range(WIN_Y0, WIN_Y1):
        t = (i - WIN_Y0) / (WIN_Y1 - WIN_Y0)
        col = (sky_top * (1 - t) + sky_bot * t).astype(np.uint8)
        arr[i, WIN_X0:WIN_X1] = col

    # Moon — soft white circle with glow halo
    moon_x = int(WIN_X0 + (WIN_X1 - WIN_X0) * 0.72)
    moon_y = WIN_Y0 + 110
    moon_r = 36
    ys, xs = np.ogrid[WIN_Y0:WIN_Y1, WIN_X0:WIN_X1]
    dist_moon = np.sqrt((xs - moon_x) ** 2 + (ys - moon_y) ** 2)
    moon_mask = dist_moon < moon_r
    halo_mask = (dist_moon >= moon_r) & (dist_moon < moon_r + 55)
    arr[WIN_Y0:WIN_Y1, WIN_X0:WIN_X1][moon_mask] = [225, 230, 245]
    halo_t = np.clip(1.0 - (dist_moon[halo_mask] - moon_r) / 55, 0, 1)
    region = arr[WIN_Y0:WIN_Y1, WIN_X0:WIN_X1]
    region[halo_mask] = np.clip(
        region[halo_mask].astype(np.float32) + np.outer(halo_t, [35, 45, 65]),
        0, 255
    ).astype(np.uint8)
    arr[WIN_Y0:WIN_Y1, WIN_X0:WIN_X1] = region

    # Stars (above city horizon)
    star_zone_bottom = WIN_Y0 + int((WIN_Y1 - WIN_Y0) * 0.45)
    for _ in range(140):
        sx = rng.randint(WIN_X0 + 5, WIN_X1 - 5)
        sy = rng.randint(WIN_Y0 + 5, star_zone_bottom)
        # Skip near moon
        if abs(sx - moon_x) < 50 and abs(sy - moon_y) < 50:
            continue
        sb = rng.randint(55, 175)
        arr[sy, sx] = [sb, sb, min(255, sb + 18)]

    # Anime bokeh circles — large translucent discs drawn UNDER buildings
    # Flat fills (no gradients), 40-155px radius, 0.35-0.60 opacity
    win_h_b = WIN_Y1 - WIN_Y0
    win_w_b = WIN_X1 - WIN_X0
    bokeh_cols = [
        (160, 120, 255), (120, 180, 255), (255, 160, 190),
        (120, 255, 185), (255, 210, 120), (185, 140, 255),
    ]
    bokeh_ov = Image.new("RGBA", (win_w_b, win_h_b), (0, 0, 0, 0))
    bokeh_d  = ImageDraw.Draw(bokeh_ov)
    for _ in range(26):
        bx  = rng.randint(-60, win_w_b + 60)
        by  = rng.randint(-40, win_h_b)
        br  = rng.randint(40, 155)
        bc  = bokeh_cols[rng.randint(0, len(bokeh_cols))]
        op  = rng.randint(89, 155)   # 0.35–0.61 × 255
        bokeh_d.ellipse([bx - br, by - br, bx + br, by + br], fill=(*bc, op))
    bokeh_blurred = bokeh_ov.filter(ImageFilter.GaussianBlur(radius=42))
    base_win = Image.fromarray(arr[WIN_Y0:WIN_Y1, WIN_X0:WIN_X1]).convert("RGBA")
    arr[WIN_Y0:WIN_Y1, WIN_X0:WIN_X1] = np.array(
        Image.alpha_composite(base_win, bokeh_blurred).convert("RGB")
    )

    # Building silhouettes — 3 depth layers
    # Heights capped so top 45% of window always shows visible sky.
    # Buildings tinted with sky colour for depth (not pure black).
    win_vis_h = WIN_Y1 - WIN_Y0          # 640
    sky_horizon = int(win_vis_h * 0.52)  # tallest building = 52% of window height

    def sky_tinted(base_lum: int, tint_mix: float) -> list:
        """Blend near-black grey with sky colour for atmospheric depth."""
        t = sky_top * tint_mix + np.array([base_lum] * 3, dtype=np.float32) * (1 - tint_mix)
        return np.clip(t, 0, 255).astype(np.uint8).tolist()

    # Layer 1: far background — sky-tinted, tallest allowed = 52% window height
    for _ in range(55):
        bx  = rng.randint(WIN_X0, WIN_X1 - 18)
        bw  = rng.randint(12, 55)
        bh  = rng.randint(110, sky_horizon)
        col = sky_tinted(rng.randint(12, 28), 0.25)
        y0  = max(WIN_Y0, WIN_Y1 - bh)
        arr[y0:WIN_Y1, bx:min(WIN_X1, bx + bw)] = col

    # Layer 2: mid distance — slightly more lit, shorter
    for _ in range(38):
        bx  = rng.randint(WIN_X0, WIN_X1 - 28)
        bw  = rng.randint(28, 88)
        bh  = rng.randint(75, int(sky_horizon * 0.75))
        col = sky_tinted(rng.randint(20, 40), 0.18)
        y0  = max(WIN_Y0, WIN_Y1 - bh)
        arr[y0:WIN_Y1, bx:min(WIN_X1, bx + bw)] = col

    # Layer 3: near foreground — darkest, shortest
    for _ in range(22):
        bx  = rng.randint(WIN_X0 - 10, WIN_X1 - 50)
        bw  = rng.randint(55, 155)
        bh  = rng.randint(45, int(sky_horizon * 0.55))
        col = sky_tinted(rng.randint(8, 18), 0.12)
        y0  = max(WIN_Y0, WIN_Y1 - bh)
        arr[y0:WIN_Y1, bx:min(WIN_X1, bx + bw)] = col

    # Lit windows — warm & cool, scattered across buildings
    for _ in range(420):
        lx  = rng.randint(WIN_X0 + 8, WIN_X1 - 12)
        ly  = rng.randint(WIN_Y0 + 120, WIN_Y1 - 28)
        lw  = rng.randint(3, 8)
        lh  = rng.randint(4, 10)
        br  = rng.randint(110, 255)
        warm = rng.random() > 0.28
        col = (min(255, br), min(255, int(br * 0.76)), br // 7) if warm \
              else (br // 7, br // 2, min(255, br))
        y0, y1_ = max(WIN_Y0, ly), min(WIN_Y1, ly + lh)
        x0, x1_ = max(WIN_X0, lx), min(WIN_X1, lx + lw)
        if y0 < y1_ and x0 < x1_:
            arr[y0:y1_, x0:x1_] = col

    # Street-level orange glow at window bottom (vectorized)
    for y in range(WIN_Y1 - 38, WIN_Y1):
        t2 = (y - (WIN_Y1 - 38)) / 38
        row_add_r = (t2 * rng.uniform(55, 130, WIN_X1 - WIN_X0)).astype(np.int32)
        row_add_g = (t2 * rng.uniform(35, 80,  WIN_X1 - WIN_X0)).astype(np.int32)
        arr[y, WIN_X0:WIN_X1, 0] = np.clip(
            arr[y, WIN_X0:WIN_X1, 0].astype(np.int32) + row_add_r, 0, 255)
        arr[y, WIN_X0:WIN_X1, 1] = np.clip(
            arr[y, WIN_X0:WIN_X1, 1].astype(np.int32) + row_add_g, 0, 255)

    # Bokeh blur
    img = Image.fromarray(arr).filter(ImageFilter.GaussianBlur(radius=5))
    return np.array(img)


def make_bokeh_twinkle(n_frames: int, seed: int = 42) -> np.ndarray:
    noise = looping_noise(n_frames, n_harmonics=4, seed=seed % 10000)
    return 0.88 + 0.12 * noise


def make_lamp_light_map(theme: str) -> np.ndarray:
    warm = np.array([1.0, 0.68, 0.28], dtype=np.float32)
    y_idx, x_idx = np.mgrid[0:H, 0:W].astype(np.float32)
    dx = x_idx - LAMP_X
    dy = y_idx - LAMP_CY
    dist_sq = dx ** 2 + dy ** 2
    dist    = np.sqrt(dist_sq) + 1e-6
    iq      = np.clip(540_000.0 / (dist_sq + 14_000.0), 0, 1.0).astype(np.float32)
    cos_down = dy / dist
    cone    = np.clip((cos_down + 0.12) / 1.12, 0.0, 1.0).astype(np.float32) ** 2.2
    result  = (iq[:, :, None] * cone[:, :, None] * warm).astype(np.float32)
    result[WIN_Y0:WIN_Y1, WIN_X0:WIN_X1] = 0.0
    result[:LAMP_CY - 60, :] *= 0.04
    return result


def make_window_ambient(theme: str) -> np.ndarray:
    win_cx = (WIN_X0 + WIN_X1) // 2
    win_cy = (WIN_Y0 + WIN_Y1) // 2
    y_idx, x_idx = np.mgrid[0:H, 0:W].astype(np.float32)
    dist = np.sqrt((x_idx - win_cx) ** 2 + (y_idx - win_cy) ** 2)
    amb  = (0.055 * np.exp(-dist / 620.0)).astype(np.float32)
    cool = np.array([0.55, 0.72, 1.0], dtype=np.float32)
    return (amb[:, :, None] * cool).astype(np.float32)


def make_candle_glow_map() -> np.ndarray:
    cy_candle = CANDLE_BASE - 72
    y_idx, x_idx = np.mgrid[0:H, 0:W].astype(np.float32)
    cdx = x_idx - CANDLE_X
    cdy = y_idx - cy_candle
    c_light = np.clip(58000.0 / (cdx ** 2 + cdy ** 2 + 1800.0), 0, 0.58).astype(np.float32)
    return np.stack([c_light, c_light * 0.55, c_light * 0.12], axis=-1)


def make_laptop_glow_map() -> np.ndarray:
    """Soft blue-white ambient from open laptop screen."""
    scr_cy = LAPTOP_Y - 155
    y_idx, x_idx = np.mgrid[0:H, 0:W].astype(np.float32)
    dist = np.sqrt((x_idx - LAPTOP_CX) ** 2 + (y_idx - scr_cy) ** 2)
    amb  = np.clip(0.075 * np.exp(-dist / 295.0), 0, 0.11).astype(np.float32)
    cool = np.array([0.70, 0.82, 1.0], dtype=np.float32)
    return (amb[:, :, None] * cool).astype(np.float32)


def make_ambient_occlusion(theme: str) -> np.ndarray:
    c = THEMES[theme]
    ao_str = c["ao_str"]
    y_idx, x_idx = np.mgrid[0:H, 0:W].astype(np.float32)
    dx = np.minimum(x_idx, W - x_idx) / (W / 2)
    dy = np.minimum(y_idx, H - y_idx) / (H / 2)
    corner = 1.0 - ao_str * (1.0 - np.sqrt(dx ** 2 + dy ** 2).clip(0, 1))
    under  = np.where(y_idx > FLOOR_Y, 0.78, 1.0).astype(np.float32)
    return (corner * under).astype(np.float32)


def make_vignette(strength: float = 0.52) -> np.ndarray:
    y_idx, x_idx = np.mgrid[0:H, 0:W].astype(np.float32)
    dx = (x_idx - W / 2) / (W / 2)
    dy = (y_idx - H / 2) / (H / 2)
    dist = np.sqrt(dx ** 2 + dy ** 2)
    t = np.clip(dist / 1.42, 0, 1).astype(np.float32)
    smooth = t * t * (3.0 - 2.0 * t)
    return (1.0 - strength * smooth).astype(np.float32)


# ══════════════════════════════════════════════════════════════════════════════
#  CAIRO CAT (cel-shaded anime sleeping cat)  — unchanged from v2
# ══════════════════════════════════════════════════════════════════════════════

def make_cat_cairo(theme: str):
    CW, CH  = 420, 260
    CCX, CCY = 165, 115

    surface = _cairo.ImageSurface(_cairo.FORMAT_ARGB32, CW, CH)
    ctx     = _cairo.Context(surface)
    ctx.set_antialias(_cairo.ANTIALIAS_BEST)

    cx, cy   = CCX, CCY
    hcx, hcy = cx - 70, cy - 27

    BASE = (0.148, 0.133, 0.125)
    DARK = (0.078, 0.063, 0.051)
    HI   = (0.243, 0.216, 0.196)
    PINK = (0.824, 0.553, 0.576)
    OUTL = (0.055, 0.039, 0.027)

    def body_path():
        ctx.save()
        ctx.translate(cx, cy)
        ctx.scale(82, 33)
        ctx.arc(0, 0, 1, 0, 2 * math.pi)
        ctx.restore()

    def head_path():
        ctx.arc(hcx, hcy, 31, 0, 2 * math.pi)

    def oval(ocx, ocy, rx, ry, fill_col, out_col=None, lw=2.5):
        ctx.save()
        ctx.translate(ocx, ocy)
        ctx.scale(rx, ry)
        ctx.arc(0, 0, 1, 0, 2 * math.pi)
        ctx.restore()
        if out_col:
            ctx.set_source_rgb(*out_col)
            ctx.set_line_width(lw)
            ctx.stroke_preserve()
        ctx.set_source_rgb(*fill_col)
        ctx.fill()

    def cel_clip(shape_fn, shad, hi):
        for (ecx, ecy, erx, ery), col, alpha in [
            (shad, DARK, 0.68), (hi, HI, 0.50)
        ]:
            ctx.save()
            shape_fn()
            ctx.clip()
            ctx.save()
            ctx.translate(ecx, ecy)
            ctx.scale(erx, ery)
            ctx.arc(0, 0, 1, 0, 2 * math.pi)
            ctx.restore()
            ctx.set_source_rgba(*col, alpha)
            ctx.fill()
            ctx.restore()

    tail_segs = [
        (cx + 115, cy + 40,  cx + 100, cy + 80,  cx + 45,  cy + 82),
        (cx -  10, cy + 84,  cx -  58, cy + 70,  cx -  72, cy + 50),
        (cx -  78, cy + 35,  cx -  65, cy + 20,  cx -  48, cy + 24),
    ]
    for lw, col in [(22, OUTL), (16, BASE)]:
        ctx.move_to(cx + 82, cy + 5)
        for seg in tail_segs:
            ctx.curve_to(*seg)
        ctx.set_source_rgb(*col)
        ctx.set_line_width(lw)
        ctx.set_line_cap(_cairo.LINE_CAP_ROUND)
        ctx.stroke()
    ctx.move_to(cx + 82, cy + 5)
    ctx.curve_to(*tail_segs[0])
    ctx.set_source_rgba(*HI, 0.30)
    ctx.set_line_width(5)
    ctx.stroke()

    body_path()
    ctx.set_source_rgb(*OUTL)
    ctx.set_line_width(4.5)
    ctx.set_line_join(_cairo.LINE_JOIN_ROUND)
    ctx.stroke_preserve()
    ctx.set_source_rgb(*BASE)
    ctx.fill()
    cel_clip(body_path, (cx + 22, cy + 18, 74, 27), (cx - 18, cy - 14, 56, 21))

    for bcx, bcy, tipx, tipy, hw in [
        (hcx - 15, hcy - 22, hcx - 13, hcy - 54, 11),
        (hcx +  5, hcy - 24, hcx +  9, hcy - 56, 10),
    ]:
        ctx.move_to(bcx - hw, bcy + 10)
        ctx.line_to(tipx, tipy)
        ctx.line_to(bcx + hw, bcy + 10)
        ctx.close_path()
        ctx.set_source_rgb(*OUTL)
        ctx.set_line_width(3.0)
        ctx.set_line_join(_cairo.LINE_JOIN_ROUND)
        ctx.stroke_preserve()
        ctx.set_source_rgb(*BASE)
        ctx.fill()
        ctx.move_to(bcx - hw + 4, bcy + 8)
        ctx.line_to((tipx + bcx) // 2, tipy + 12)
        ctx.line_to(bcx + hw - 4, bcy + 8)
        ctx.close_path()
        ctx.set_source_rgb(*PINK)
        ctx.fill()

    head_path()
    ctx.set_source_rgb(*OUTL)
    ctx.set_line_width(4.0)
    ctx.stroke_preserve()
    ctx.set_source_rgb(*BASE)
    ctx.fill()
    cel_clip(head_path, (hcx + 8, hcy + 10, 24, 18), (hcx - 10, hcy - 10, 17, 13))

    # Anime blush marks — soft pink circles on cheeks, drawn before eyes/whiskers
    for bx_off in [-17, 16]:
        ctx.arc(hcx + bx_off, hcy + 9, 13, 0, 2 * math.pi)
        ctx.set_source_rgba(0.855, 0.420, 0.545, 0.44)
        ctx.fill()

    ctx.set_line_cap(_cairo.LINE_CAP_ROUND)
    for ex_off in [-14, 9]:
        ex = hcx + ex_off
        ey = hcy + 4
        ctx.move_to(ex - 9, ey + 1)
        ctx.curve_to(ex - 4, ey - 6, ex + 4, ey - 6, ex + 9, ey + 1)
        ctx.set_source_rgb(*OUTL)
        ctx.set_line_width(2.2)
        ctx.stroke()
        for dot_x in (ex - 9, ex + 9):
            ctx.arc(dot_x, ey + 1, 1.2, 0, 2 * math.pi)
            ctx.fill()

    nx, ny = hcx - 2, hcy + 12
    ctx.move_to(nx - 5, ny)
    ctx.line_to(nx, ny - 7)
    ctx.line_to(nx + 5, ny)
    ctx.close_path()
    ctx.set_source_rgb(*PINK)
    ctx.fill()

    ctx.move_to(nx - 6, ny + 1)
    ctx.curve_to(nx - 3, ny + 6, nx, ny + 3, nx, ny + 3)
    ctx.curve_to(nx, ny + 3, nx + 3, ny + 6, nx + 6, ny + 1)
    ctx.set_source_rgb(*OUTL)
    ctx.set_line_width(1.6)
    ctx.set_line_cap(_cairo.LINE_CAP_ROUND)
    ctx.stroke()

    for pdx, pdy in [(-22, 30), (8, 34)]:
        oval(hcx + pdx, hcy + pdy, 16, 9, BASE, OUTL, 2.5)

    ctx.set_line_width(1.0)
    ctx.set_line_cap(_cairo.LINE_CAP_ROUND)
    for side in (-1, 1):
        for wy_idx, v_ang in enumerate([-0.06, 0.0, 0.06]):
            wx0 = hcx + side * 14
            wy0 = hcy + 9 + (wy_idx - 1) * 4
            wx1 = wx0 + side * 50 * math.cos(v_ang)
            wy1 = wy0 + 50 * math.sin(side * v_ang)
            ctx.move_to(wx0, wy0)
            ctx.line_to(wx1, wy1)
            ctx.set_source_rgba(0.36, 0.30, 0.26, 0.70)
            ctx.stroke()

    buf  = bytes(surface.get_data())
    arr  = np.frombuffer(buf, dtype=np.uint8).reshape(CH, CW, 4).copy()
    rgba = arr[:, :, [2, 1, 0, 3]]
    return Image.fromarray(rgba), CCX, CCY


def paste_cat(frame: np.ndarray, cat_arr: np.ndarray,
              paste_x: int, paste_y: int) -> None:
    ch, cw = cat_arr.shape[:2]
    y0 = max(0, paste_y);  y1 = min(H, paste_y + ch)
    x0 = max(0, paste_x);  x1 = min(W, paste_x + cw)
    if y0 >= y1 or x0 >= x1:
        return
    sy0, sy1 = y0 - paste_y, y0 - paste_y + (y1 - y0)
    sx0, sx1 = x0 - paste_x, x0 - paste_x + (x1 - x0)
    src_rgb = cat_arr[sy0:sy1, sx0:sx1, :3].astype(np.float32)
    src_a   = cat_arr[sy0:sy1, sx0:sx1,  3:4].astype(np.float32) / 255.0
    dst     = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = np.clip(
        dst * (1.0 - src_a) + src_rgb * src_a, 0, 255
    ).astype(np.uint8)


# ══════════════════════════════════════════════════════════════════════════════
#  STATIC SCENE
# ══════════════════════════════════════════════════════════════════════════════

def _clamp_col(r, g, b):
    return (min(255, max(0, r)), min(255, max(0, g)), min(255, max(0, b)))


def make_static_scene(theme: str, city: np.ndarray) -> np.ndarray:
    c   = THEMES[theme]
    arr = make_gradient(theme)
    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)

    # ── 1. CITY / WINDOW BACKGROUND ─────────────────────────────────────────
    win_h = WIN_Y1 - WIN_Y0
    win_w = WIN_X1 - WIN_X0
    tint  = Image.new("RGB", (win_w, win_h), c["win_sky"])
    city_crop = city[WIN_Y0:WIN_Y1, WIN_X0:WIN_X1]
    blended = Image.blend(tint, Image.fromarray(city_crop), alpha=0.80)
    img.paste(blended, (WIN_X0, WIN_Y0))
    draw = ImageDraw.Draw(img)

    # ── 2. WALL ZONES ────────────────────────────────────────────────────────
    wc = c["wall"]
    # Left wall (x=0 to LCURT_X0)
    draw.rectangle([0, 0, LCURT_X0, H], fill=wc)
    # Right wall (x=RCURT_X1 to W)
    draw.rectangle([RCURT_X1, 0, W, H], fill=wc)
    # Below-window wall band (between bottom of window and desk)
    draw.rectangle([WIN_X0, WIN_Y1, WIN_X1, DESK_Y], fill=wc)
    # Wainscoting — slightly lighter lower wall panel
    wn = c["wainscot"]
    wainscot_y0 = int(DESK_Y * 0.82)   # starts ~82% down the wall
    draw.rectangle([0, wainscot_y0, LCURT_X0,  DESK_Y], fill=wn)
    draw.rectangle([RCURT_X1, wainscot_y0, W, DESK_Y], fill=wn)
    # Thin rail dividing wainscot from upper wall
    rail_col = _clamp_col(wn[0] + 16, wn[1] + 12, wn[2] + 10)
    draw.rectangle([0, wainscot_y0, LCURT_X0, wainscot_y0 + 4], fill=rail_col)
    draw.rectangle([RCURT_X1, wainscot_y0, W, wainscot_y0 + 4], fill=rail_col)

    # ── 3. LEFT-WALL BOOKSHELF (3-shelf unit) ───────────────────────────────
    sw = SHELF_X1 - SHELF_X0
    sd = c["desk"]
    wood = (min(255, sd[0] + 8), min(255, sd[1] + 5), min(255, sd[2] + 2))
    wood_dk = (max(0, sd[0] - 8), max(0, sd[1] - 5), max(0, sd[2] - 2))
    panel_w = 14
    # Left and right side panels
    draw.rectangle([SHELF_X0, SHELF_TOP, SHELF_X0 + panel_w, SHELF_BOT], fill=wood)
    draw.rectangle([SHELF_X1 - panel_w, SHELF_TOP, SHELF_X1, SHELF_BOT], fill=wood)
    # Top panel
    draw.rectangle([SHELF_X0, SHELF_TOP, SHELF_X1, SHELF_TOP + panel_w], fill=wood)
    # 3 shelf horizontals
    shelf_ys = [SHELF_TOP + (SHELF_BOT - SHELF_TOP) * i // 3 for i in range(1, 4)]
    shelf_ys[-1] = SHELF_BOT
    for sy in shelf_ys:
        draw.rectangle([SHELF_X0, sy - 12, SHELF_X1, sy], fill=wood)
        # Under-shelf shadow
        draw.rectangle([SHELF_X0 + 2, sy, SHELF_X1 - 2, sy + 8],
                       fill=_clamp_col(wood_dk[0], wood_dk[1], wood_dk[2]))

    # Books on each shelf
    book_sets = [
        [((135, 48, 48), 28), ((52, 96, 148), 34), ((64, 118, 60), 24),
         ((136, 104, 36), 30), ((92, 52, 128), 20)],
        [((78, 78, 78), 26), ((120, 74, 50), 32), ((44, 90, 112), 28),
         ((148, 62, 42), 22), ((68, 118, 82), 36)],
        [((112, 82, 38), 28), ((46, 82, 148), 24), ((118, 46, 76), 32),
         ((72, 112, 60), 20), ((138, 112, 42), 30)],
    ]
    for shelf_idx, (sy, bset) in enumerate(zip([SHELF_TOP, shelf_ys[0], shelf_ys[1]], book_sets)):
        shelf_top = sy + panel_w if shelf_idx == 0 else shelf_ys[shelf_idx - 1]
        shelf_base = shelf_ys[shelf_idx] - 12
        bx = SHELF_X0 + panel_w + 4
        for i, (bc, bw) in enumerate(bset):
            bh = shelf_base - shelf_top - 2
            if bh <= 0:
                continue
            # Book body
            draw.rectangle([bx, shelf_top + (10 - i * 2) % 10, bx + bw, shelf_base], fill=bc)
            # Spine highlight
            hi = _clamp_col(bc[0] + 35, bc[1] + 30, bc[2] + 25)
            draw.rectangle([bx, shelf_top + (10 - i * 2) % 10, bx + 3, shelf_base], fill=hi)
            # Spine title line
            lo = _clamp_col(bc[0] - 20, bc[1] - 18, bc[2] - 16)
            draw.rectangle([bx + 6, shelf_top + (10 - i * 2) % 10 + 8,
                            bx + bw - 4, shelf_top + (10 - i * 2) % 10 + 11], fill=lo)
            bx += bw + random.Random(shelf_idx * 10 + i + 33).randint(1, 5)

    # ── 4. LEFT-WALL POLAROID PHOTOS ────────────────────────────────────────
    for px, py in [(SHELF_X1 + 18, DESK_Y - 480), (SHELF_X1 + 14, DESK_Y - 370)]:
        draw.rectangle([px, py, px + 58, py + 68], fill=(228, 220, 208))
        pc = [(82, 58, 50), (58, 82, 72), (70, 62, 92)][(px % 3)]
        draw.rectangle([px + 5, py + 5, px + 53, py + 50], fill=pc)
        draw.rectangle([px + 8, py + 54, px + 50, py + 58], fill=(155, 148, 136))

    # ── 4b. STICKY NOTES on left wall (between bookshelf and curtain) ────────
    notes_data = [
        (262, DESK_Y - 318, (255, 228, 120)),   # sunny yellow
        (296, DESK_Y - 262, (200, 255, 210)),   # mint green
        (264, DESK_Y - 200, (255, 195, 215)),   # sakura pink
        (298, DESK_Y - 148, (210, 210, 255)),   # lavender blue
    ]
    for nx, ny, nc in notes_data:
        # Note body
        draw.rectangle([nx, ny, nx + 60, ny + 54], fill=nc)
        # Bottom and right shadow (folded paper look)
        drk_nc = _clamp_col(nc[0] - 38, nc[1] - 38, nc[2] - 38)
        draw.rectangle([nx + 2, ny + 51, nx + 62, ny + 56], fill=drk_nc)
        draw.rectangle([nx + 57, ny + 2, nx + 62, ny + 54], fill=drk_nc)
        # Ruled lines
        ln_col = _clamp_col(nc[0] - 60, nc[1] - 60, nc[2] - 60)
        for loff in [14, 24, 36, 46]:
            draw.line([(nx + 7, ny + loff), (nx + 52, ny + loff)],
                      fill=ln_col, width=1)
        # Small folded corner (top-right)
        fc_col = _clamp_col(nc[0] - 55, nc[1] - 55, nc[2] - 55)
        draw.polygon([(nx + 50, ny), (nx + 60, ny), (nx + 60, ny + 10)], fill=fc_col)

    # ── 5. RIGHT-WALL CLOCK ──────────────────────────────────────────────────
    cx2, cy2 = CLOCK_CX, CLOCK_CY
    # Outer ring
    draw.ellipse([cx2 - 38, cy2 - 38, cx2 + 38, cy2 + 38], fill=(215, 205, 185))
    draw.ellipse([cx2 - 33, cy2 - 33, cx2 + 33, cy2 + 33], fill=(245, 240, 228))
    for angle in range(0, 360, 30):
        rad = math.radians(angle)
        x0c = cx2 + int(22 * math.sin(rad)); y0c = cy2 - int(22 * math.cos(rad))
        x1c = cx2 + int(28 * math.sin(rad)); y1c = cy2 - int(28 * math.cos(rad))
        draw.line([(x0c, y0c), (x1c, y1c)], fill=(75, 66, 55), width=2)
    # Hands at ~10:48 — classic lo-fi study time
    for hand_angle, length, width in [(258, 18, 2), (288, 23, 2)]:
        rad = math.radians(hand_angle)
        draw.line([cx2, cy2,
                   cx2 + int(length * math.sin(rad)),
                   cy2 - int(length * math.cos(rad))],
                  fill=(48, 40, 32), width=width)
    draw.ellipse([cx2 - 3, cy2 - 3, cx2 + 3, cy2 + 3], fill=(80, 65, 50))

    # ── 6. WINDOW FRAME ──────────────────────────────────────────────────────
    fr = c["frame_col"]
    fw = 12
    # Outer frame
    draw.rectangle([WIN_X0 - fw, WIN_Y0 - fw, WIN_X1 + fw, WIN_Y0], fill=fr)
    draw.rectangle([WIN_X0 - fw, WIN_Y1, WIN_X1 + fw, WIN_Y1 + fw], fill=fr)
    draw.rectangle([WIN_X0 - fw, WIN_Y0, WIN_X0, WIN_Y1], fill=fr)
    draw.rectangle([WIN_X1, WIN_Y0, WIN_X1 + fw, WIN_Y1], fill=fr)
    # Cross dividers (4-pane window)
    mid_x = (WIN_X0 + WIN_X1) // 2
    mid_y = (WIN_Y0 + WIN_Y1) // 2
    draw.rectangle([mid_x - 6, WIN_Y0, mid_x + 6, WIN_Y1], fill=fr)
    draw.rectangle([WIN_X0, mid_y - 5, WIN_X1, mid_y + 5], fill=fr)
    # Frame highlights
    fr_hi = _clamp_col(fr[0] + 22, fr[1] + 18, fr[2] + 14)
    draw.rectangle([WIN_X0 - fw, WIN_Y0 - fw, WIN_X1 + fw, WIN_Y0 - fw + 3], fill=fr_hi)
    draw.rectangle([WIN_X0 - fw, WIN_Y0 - fw, WIN_X0 - fw + 3, WIN_Y1 + fw], fill=fr_hi)

    # Window sill (stone ledge below window)
    sl = c["sill_col"]
    draw.rectangle([WIN_X0 - fw - 8, WIN_Y1 + fw,
                    WIN_X1 + fw + 8, WIN_Y1 + fw + 22], fill=sl)
    sl_hi = _clamp_col(sl[0] + 20, sl[1] + 16, sl[2] + 12)
    draw.rectangle([WIN_X0 - fw - 8, WIN_Y1 + fw,
                    WIN_X1 + fw + 8, WIN_Y1 + fw + 5], fill=sl_hi)

    # Rain droplets on glass (static elongated streaks)
    rng_g = np.random.RandomState(42)
    for _ in range(GLASS_DRIP_N):
        gx = rng_g.randint(WIN_X0 + 15, WIN_X1 - 15)
        gy = rng_g.randint(WIN_Y0 + 60, WIN_Y1 - 80)
        gl = rng_g.randint(14, 55)
        draw.line([(gx, gy), (gx + 1, gy + gl)],
                  fill=(200, 220, 240), width=1)

    # ── 7. CURTAIN ROD ───────────────────────────────────────────────────────
    rod_y   = WIN_Y0 - 38
    rod_col = c["curtain_rod"]
    draw.rectangle([LCURT_X0 + 10, rod_y - 5, RCURT_X1 - 10, rod_y + 5], fill=rod_col)
    # Rod end finials
    for fx in [LCURT_X0 + 10, RCURT_X1 - 10]:
        draw.ellipse([fx - 10, rod_y - 10, fx + 10, rod_y + 10], fill=rod_col)

    # ── 8. CURTAINS — curtains are drawn in apply_curtain_sway per-frame ────
    # (placeholder: static base drawn here, overwritten each frame)
    _draw_curtain_static(draw, c)

    # ── 9. DESK SURFACE + FRONT FACE ────────────────────────────────────────
    # Full bottom: base color
    draw.rectangle([0, DESK_Y, W, H], fill=c["desk"])
    # Highlight strip at top edge
    draw.rectangle([0, DESK_Y, W, DESK_Y + 5], fill=c["desk_hl"])
    # Slight perspective front face (darker band below highlight)
    draw.rectangle([0, DESK_Y + 5, W, DESK_Y + DESK_FACE_H], fill=c["desk_face"])
    # Shadow below front face (floor)
    draw.rectangle([0, FLOOR_Y, W, H], fill=c["floor"])
    # Subtle floor-to-desk shadow gradient (first 30px of floor)
    fl = c["floor"]
    for y in range(FLOOR_Y, FLOOR_Y + 30):
        t3 = (y - FLOOR_Y) / 30
        row_col = (
            int(fl[0] * (0.6 + 0.4 * t3)),
            int(fl[1] * (0.6 + 0.4 * t3)),
            int(fl[2] * (0.6 + 0.4 * t3)),
        )
        draw.rectangle([0, y, W, y + 1], fill=row_col)

    # ── 10. RUG (Persian-style, foreground floor) ───────────────────────────
    rug_x0, rug_x1 = 200, 1720
    rug_y0, rug_y1 = FLOOR_Y + 28, H - 8
    rb  = c["rug_base"]
    rbd = c["rug_brd"]
    draw.rectangle([rug_x0, rug_y0, rug_x1, rug_y1], fill=rb)
    # Multiple border insets
    for inset, brd_col in [(0, rbd), (12, _clamp_col(rb[0]+15, rb[1]+8, rb[2]+8)),
                            (22, rbd), (30, rb)]:
        draw.rectangle([rug_x0 + inset, rug_y0 + inset,
                        rug_x1 - inset, rug_y0 + inset + 8], fill=brd_col)
        draw.rectangle([rug_x0 + inset, rug_y1 - inset - 8,
                        rug_x1 - inset, rug_y1 - inset], fill=brd_col)
        draw.rectangle([rug_x0 + inset, rug_y0 + inset,
                        rug_x0 + inset + 8, rug_y1 - inset], fill=brd_col)
        draw.rectangle([rug_x1 - inset - 8, rug_y0 + inset,
                        rug_x1 - inset, rug_y1 - inset], fill=brd_col)
    # Simple diamond motif grid
    dm_col = _clamp_col(rb[0] + 25, rb[1] + 12, rb[2] + 12)
    for dx in range(rug_x0 + 60, rug_x1 - 60, 90):
        for dy in range(rug_y0 + 30, rug_y1 - 20, 40):
            d = 10
            draw.polygon([(dx, dy - d), (dx + d, dy), (dx, dy + d), (dx - d, dy)],
                          fill=dm_col)

    # ── 11. STACKED BOOKS (left desk) ────────────────────────────────────────
    by2 = DESK_Y
    for bc, bw2, bth in [
        ((148, 55, 55), 118, 14),
        (( 55, 105, 148), 108, 10),
        (( 72, 128, 64), 100,  8),
    ]:
        draw.rectangle([STACK_X, by2 - bth, STACK_X + bw2, by2], fill=bc)
        hi2 = _clamp_col(bc[0] + 30, bc[1] + 26, bc[2] + 22)
        draw.rectangle([STACK_X, by2 - bth, STACK_X + 4, by2], fill=hi2)
        by2 -= bth
    # Shadow under stack
    for off in range(1, 6):
        a = 1.0 - off / 6
        dk = c["desk_drk"] if "desk_drk" in c else c["desk"]
        draw.rectangle([STACK_X + 2, DESK_Y, STACK_X + 118, DESK_Y + off],
                       fill=_clamp_col(dk[0], dk[1], dk[2]))

    # ── 12. CANDLE ───────────────────────────────────────────────────────────
    cand_w = 20
    cand_h = 72
    cx3, cy3 = CANDLE_X, CANDLE_BASE
    # Saucer / holder
    draw.ellipse([cx3 - 24, cy3 - 8, cx3 + 24, cy3 + 10],
                 fill=(175, 154, 115))
    saucer_hi = (195, 174, 135)
    draw.ellipse([cx3 - 20, cy3 - 5, cx3 + 20, cy3 + 2], fill=saucer_hi)
    # Wax column (slightly tapered)
    draw.polygon([
        (cx3 - cand_w // 2 + 2, cy3 - cand_h),
        (cx3 + cand_w // 2 - 2, cy3 - cand_h),
        (cx3 + cand_w // 2, cy3 - 4),
        (cx3 - cand_w // 2, cy3 - 4),
    ], fill=(238, 232, 215))
    # Wax highlight (left side)
    draw.polygon([
        (cx3 - cand_w // 2 + 2, cy3 - cand_h),
        (cx3 - cand_w // 2 + 6, cy3 - cand_h),
        (cx3 - cand_w // 2 + 5, cy3 - 4),
        (cx3 - cand_w // 2, cy3 - 4),
    ], fill=(250, 246, 234))
    # Wax drip streaks
    for dx_d, dy_d in [(-4, 12), (5, 8), (2, 18)]:
        draw.line([(cx3 + dx_d, cy3 - cand_h + 2),
                   (cx3 + dx_d, cy3 - cand_h + 2 + dy_d)],
                  fill=(238, 232, 215), width=3)
    # Wick
    draw.line([(cx3, cy3 - cand_h), (cx3, cy3 - cand_h - 9)],
              fill=(38, 28, 18), width=2)

    # ── 13. COFFEE MUG (tapered body, rim ellipse, handle arc) ───────────────
    mw = 56
    mh = 85
    mx, my = MUG_X, MUG_TOP
    mug_body = (68, 48, 40)
    mug_hi   = (90, 68, 58)
    # Shadow on desk
    draw.ellipse([mx - mw // 2 - 4, DESK_Y - 4, mx + mw // 2 + 4, DESK_Y + 10],
                 fill=_clamp_col(mug_body[0] - 20, mug_body[1] - 14, mug_body[2] - 10))
    # Tapered body (polygon: wider at top, narrower at bottom)
    draw.polygon([
        (mx - mw // 2,     my),
        (mx + mw // 2,     my),
        (mx + mw // 2 - 5, my + mh),
        (mx - mw // 2 + 5, my + mh),
    ], fill=mug_body)
    # Highlight stripe on left side
    draw.polygon([
        (mx - mw // 2,     my + 6),
        (mx - mw // 2 + 8, my + 6),
        (mx - mw // 2 + 6, my + mh - 4),
        (mx - mw // 2 + 2, my + mh - 4),
    ], fill=mug_hi)
    # Top rim ellipse
    draw.ellipse([mx - mw // 2 - 2, my - 12, mx + mw // 2 + 2, my + 12],
                 fill=(82, 62, 52))
    draw.ellipse([mx - mw // 2 + 5, my - 9, mx + mw // 2 - 5, my + 9],
                 fill=(22, 14, 8))   # dark coffee surface
    # Bottom ellipse
    draw.ellipse([mx - mw // 2 + 5, my + mh - 8, mx + mw // 2 - 5, my + mh + 8],
                 fill=mug_body)
    # Handle (arc + fill)
    hbx0 = mx + mw // 2 - 6
    hbx1 = mx + mw // 2 + 36
    hby0 = my + 16
    hby1 = my + mh - 18
    draw.arc([hbx0, hby0, hbx1, hby1], start=270, end=90, fill=mug_body, width=8)
    draw.arc([hbx0 + 4, hby0 + 4, hbx1 - 4, hby1 - 4], start=270, end=90,
             fill=mug_hi, width=3)

    # ── 14. LAPTOP (open, screen glowing) ────────────────────────────────────
    # Base/keyboard — trapezoidal for slight perspective
    lkb_w, lkb_h = 360, 22
    lkb_cx = LAPTOP_CX
    lkb_y  = LAPTOP_Y - 2
    draw.polygon([
        (lkb_cx - lkb_w // 2,     lkb_y),
        (lkb_cx + lkb_w // 2,     lkb_y),
        (lkb_cx + lkb_w // 2 - 8, lkb_y + lkb_h),
        (lkb_cx - lkb_w // 2 + 8, lkb_y + lkb_h),
    ], fill=(42, 42, 48))
    # Keyboard keys (simplified rows)
    for ky in range(lkb_y + 4, lkb_y + lkb_h - 6, 6):
        for kx in range(lkb_cx - lkb_w // 2 + 12, lkb_cx + lkb_w // 2 - 12, 18):
            draw.rectangle([kx, ky, kx + 14, ky + 4], fill=(52, 52, 58))
    # Screen (trapezoid — slightly wider at bottom due to perspective)
    scr_bot_y = lkb_y - 2
    scr_top_y = lkb_y - 295
    scr_bw    = 355
    scr_tw    = 328
    draw.polygon([
        (lkb_cx - scr_bw // 2, scr_bot_y),
        (lkb_cx + scr_bw // 2, scr_bot_y),
        (lkb_cx + scr_tw // 2, scr_top_y),
        (lkb_cx - scr_tw // 2, scr_top_y),
    ], fill=(36, 36, 42))  # screen bezel
    # Screen glass (slightly inset, glowing blue-grey)
    inset = 10
    for y in range(scr_top_y + inset, scr_bot_y - inset):
        t_scr = (y - (scr_top_y + inset)) / (scr_bot_y - scr_top_y - 2 * inset)
        # Gradient: cooler/darker at top, slightly warmer at bottom (desktop)
        r = int(30 + 15 * t_scr)
        g = int(38 + 12 * t_scr)
        b = int(62 + 8 * t_scr)
        draw.rectangle([lkb_cx - scr_bw // 2 + inset + 4,
                        y,
                        lkb_cx + scr_bw // 2 - inset - 4,
                        y + 1], fill=(r, g, b))
    # Simulated screen content (blurry lines suggesting text/notes)
    for line_y in range(scr_top_y + 40, scr_bot_y - 30, 18):
        line_w = int(scr_tw * 0.55 * (0.5 + 0.5 * random.Random(line_y).random()))
        draw.rectangle([lkb_cx - line_w // 2, line_y,
                        lkb_cx - line_w // 2 + line_w, line_y + 4],
                       fill=(55, 72, 105))
    # Screen reflection/highlight at top
    draw.rectangle([lkb_cx - scr_tw // 2 + inset + 4, scr_top_y + inset,
                    lkb_cx + scr_tw // 2 - inset - 4, scr_top_y + inset + 6],
                   fill=(55, 68, 95))
    # Hinge
    draw.rectangle([lkb_cx - scr_bw // 2, scr_bot_y - 3,
                    lkb_cx + scr_bw // 2, scr_bot_y + 3], fill=(55, 55, 62))

    # ── 15. OPEN NOTEBOOK (right of laptop area — below window) ─────────────
    nb_cx = 1125
    nb_y0 = DESK_Y - 18
    nb_y1 = DESK_Y
    nb_w  = 210
    # Left page
    draw.rectangle([nb_cx - nb_w // 2, nb_y0, nb_cx, nb_y1],
                   fill=(242, 238, 228))
    # Right page
    draw.rectangle([nb_cx, nb_y0, nb_cx + nb_w // 2, nb_y1],
                   fill=(245, 241, 232))
    # Spine shadow
    draw.rectangle([nb_cx - 3, nb_y0, nb_cx + 3, nb_y1], fill=(180, 174, 162))
    # Ruled lines (left page)
    for ly_off in range(3, 15, 3):
        draw.line([(nb_cx - nb_w // 2 + 8, DESK_Y - ly_off),
                   (nb_cx - 8, DESK_Y - ly_off)],
                  fill=(178, 172, 160), width=1)
    # Sketch lines (right page — squiggle pattern)
    for ly_off in range(3, 15, 4):
        draw.line([(nb_cx + 8, DESK_Y - ly_off),
                   (nb_cx + nb_w // 2 - 30, DESK_Y - ly_off)],
                  fill=(178, 172, 160), width=1)
    # Pen resting on notebook
    pen_x = nb_cx + nb_w // 2 - 14
    draw.rectangle([pen_x, nb_y0 - 2, pen_x + 8, nb_y1], fill=(38, 38, 72))
    draw.polygon([(pen_x, nb_y0 - 2), (pen_x + 8, nb_y0 - 2), (pen_x + 4, nb_y0 - 12)],
                 fill=(188, 55, 55))

    # ── 16. HEADPHONES (on desk right zone) ──────────────────────────────────
    hx, hy = HP_X, HP_Y
    # Headband arc
    draw.arc([hx - 32, hy - 52, hx + 32, hy], start=180, end=0,
             fill=(36, 32, 30), width=9)
    # Ear cups (left and right)
    for ex_off, ew in [(-40, 20), (40, 20)]:
        draw.ellipse([hx + ex_off - ew // 2, hy - 18,
                      hx + ex_off + ew // 2, hy + 10], fill=(36, 32, 30))
        draw.ellipse([hx + ex_off - ew // 2 + 3, hy - 15,
                      hx + ex_off + ew // 2 - 3, hy + 7], fill=(55, 50, 46))
    # Cushion rings
    for ex_off in [-40, 40]:
        draw.arc([hx + ex_off - 16, hy - 14, hx + ex_off + 16, hy + 6],
                 start=0, end=360, fill=(50, 45, 42), width=3)

    # ── 17. SUCCULENT PLANT (right zone) ─────────────────────────────────────
    px4, py4 = PLANT_X, PLANT_Y
    # Pot (tapered trapezoid)
    draw.polygon([
        (px4 - 32, py4),     (px4 + 32, py4),
        (px4 + 26, py4 - 50), (px4 - 26, py4 - 50),
    ], fill=(132, 72, 42))
    draw.ellipse([px4 - 28, py4 - 56, px4 + 28, py4 - 44],
                 fill=(152, 88, 55))
    draw.ellipse([px4 - 22, py4 - 53, px4 + 22, py4 - 46],
                 fill=(38, 26, 15))  # soil
    # Succulent rosette — concentric rings of petals
    base_y = py4 - 50
    for ring, (ring_r, n_petals, petal_len, petal_w, green) in enumerate([
        (0,  6, 22, 11, (40, 105, 58)),    # innermost: darkest
        (16, 8, 28, 13, (52, 122, 68)),    # mid ring
        (30, 10, 22, 10, (62, 138, 75)),   # outer ring: lightest
    ]):
        for i in range(n_petals):
            angle = 2 * math.pi * i / n_petals + ring * 0.2
            # Petal tip
            tip_x = px4 + int((ring_r + petal_len) * math.cos(angle))
            tip_y = base_y - int((ring_r + petal_len) * 0.45 * math.sin(angle + math.pi / 2))
            # Petal as ellipse
            mid_x = px4 + int((ring_r + petal_len / 2) * math.cos(angle))
            mid_y = base_y - int((ring_r + petal_len / 2) * 0.45 * math.sin(angle + math.pi / 2))
            draw.ellipse([mid_x - petal_w // 2, mid_y - petal_w,
                          mid_x + petal_w // 2, mid_y + petal_w // 2], fill=green)
    # Centre bud
    draw.ellipse([px4 - 8, base_y - 10, px4 + 8, base_y + 6],
                 fill=(32, 90, 50))

    # ── 18. DESK LAMP (right zone — articulated arm) ─────────────────────────
    lx = LAMP_X
    lc = c["lamp_col"]
    lc_dim = _clamp_col(lc[0] // 2 + 55, lc[1] // 2 + 42, lc[2] // 4 + 22)

    # Weighted base (solid ellipse)
    draw.ellipse([lx - 38, DESK_Y - 14, lx + 38, DESK_Y + 14],
                 fill=(62, 54, 46))
    draw.ellipse([lx - 34, DESK_Y - 10, lx + 34, DESK_Y + 10],
                 fill=(78, 68, 58))

    # Lower arm (angled up-left from base)
    arm1_x0, arm1_y0 = lx, DESK_Y - 14
    arm1_x1 = lx - 55
    arm1_y1 = DESK_Y - 175
    draw.line([(arm1_x0, arm1_y0), (arm1_x1, arm1_y1)], fill=(68, 60, 52), width=7)
    # Joint
    draw.ellipse([arm1_x1 - 7, arm1_y1 - 7, arm1_x1 + 7, arm1_y1 + 7],
                 fill=(85, 76, 65))
    # Upper arm (continues up-left to shade)
    arm2_x1 = lx - 90
    arm2_y1 = DESK_Y - 320
    draw.line([(arm1_x1, arm1_y1), (arm2_x1, arm2_y1)], fill=(68, 60, 52), width=6)
    # Second joint
    draw.ellipse([arm2_x1 - 6, arm2_y1 - 6, arm2_x1 + 6, arm2_y1 + 6],
                 fill=(85, 76, 65))

    # Shade (cone pointing down-right)
    shade_cx, shade_cy = arm2_x1 + 20, arm2_y1 + 10
    shade_pts = [
        (shade_cx - 72, shade_cy - 10),
        (shade_cx + 62, shade_cy - 10),
        (shade_cx + 46, shade_cy + 82),
        (shade_cx - 50, shade_cy + 82),
    ]
    draw.polygon(shade_pts, fill=lc_dim)
    # Inner glow
    inner_pts = [
        (shade_cx - 56, shade_cy - 4),
        (shade_cx + 48, shade_cy - 4),
        (shade_cx + 34, shade_cy + 76),
        (shade_cx - 38, shade_cy + 76),
    ]
    draw.polygon(inner_pts, fill=lc)
    # Bulb visible at bottom
    draw.ellipse([shade_cx - 10, shade_cy + 70,
                  shade_cx + 10, shade_cy + 94], fill=lc)

    return np.array(img)


def _draw_curtain_static(draw: ImageDraw.ImageDraw, c: dict):
    """Draw static curtains (no sway). Called by make_static_scene; overdrawn per-frame by apply_curtain_sway."""
    n_folds = 7
    fold_colors = [c["curtain_lo"], c["curtain_hi"], c["curtain"],
                   c["curtain_lo"], c["curtain_hi"], c["curtain"], c["curtain_lo"]]
    # Left curtain
    lw = (LCURT_X1 - LCURT_X0) // n_folds
    for i in range(n_folds):
        x0 = LCURT_X0 + i * lw
        draw.rectangle([x0, WIN_Y0 - 46, x0 + lw + 1, WIN_Y1 + 48], fill=fold_colors[i])
    # Right curtain
    rw = (RCURT_X1 - RCURT_X0) // n_folds
    for i in range(n_folds):
        x0 = RCURT_X0 + i * rw
        col = fold_colors[n_folds - 1 - i]
        draw.rectangle([x0, WIN_Y0 - 46, x0 + rw + 1, WIN_Y1 + 48], fill=col)
    # Gather bunching at top (slightly darker scallops)
    dk = c["curtain_lo"]
    for i in range(n_folds):
        for side, base_x in [("L", LCURT_X0), ("R", RCURT_X0)]:
            fw2 = lw if side == "L" else rw
            bx = base_x + i * fw2
            draw.ellipse([bx - 4, WIN_Y0 - 52, bx + fw2 + 4, WIN_Y0 - 28], fill=dk)


# ══════════════════════════════════════════════════════════════════════════════
#  FAIRY LIGHTS
# ══════════════════════════════════════════════════════════════════════════════

def make_fairy_positions() -> list:
    """Return list of (x, y) for each bulb along catenary-like string."""
    x_left  = LCURT_X0 + 20
    x_right = RCURT_X1 - 20
    sag     = 28   # midpoint drop in pixels
    positions = []
    for i in range(FAIRY_N):
        t  = i / (FAIRY_N - 1)
        x  = int(x_left + t * (x_right - x_left))
        # Parabolic sag
        y  = int(FAIRY_Y + sag * 4 * t * (1 - t))
        positions.append((x, y))
    return positions


def make_fairy_noise(n_frames: int) -> np.ndarray:
    """Per-bulb looping brightness noise, shape (n_frames, FAIRY_N)."""
    arr = np.zeros((n_frames, FAIRY_N), dtype=np.float32)
    for i in range(FAIRY_N):
        arr[:, i] = 0.60 + 0.40 * looping_noise(n_frames, n_harmonics=5, seed=200 + i)
    return arr


def draw_fairy_lights(frame: np.ndarray, positions: list,
                      brightnesses: np.ndarray, theme: str) -> None:
    """Render fairy lights onto frame in-place. Uses tight ROI for speed."""
    c   = THEMES[theme]
    fc  = np.array(c["fairy_col"], dtype=np.float32)

    # ROI: just the strip around the fairy lights
    ry0 = max(0, FAIRY_Y - 28)
    ry1 = min(H, FAIRY_Y + 44)
    rx0 = max(0, LCURT_X0)
    rx1 = min(W, RCURT_X1)
    rh, rw = ry1 - ry0, rx1 - rx0
    if rh <= 0 or rw <= 0:
        return

    overlay = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
    d       = ImageDraw.Draw(overlay)

    # String wire
    prev = None
    for (bx, by) in positions:
        lbx, lby = bx - rx0, by - ry0
        if prev:
            d.line([prev, (lbx, lby)], fill=(80, 65, 50, 100), width=1)
        prev = (lbx, lby)

    for i, (bx, by) in enumerate(positions):
        lbx, lby = bx - rx0, by - ry0
        br       = float(brightnesses[i])
        bulb_col = (int(fc[0] * br), int(fc[1] * br), int(fc[2] * br), 220)
        d.ellipse([lbx - 4, lby - 4, lbx + 4, lby + 8], fill=bulb_col)
        glow_r   = int(14 + 6 * br)
        glow_a   = int(80 * br)
        glow_col = (int(fc[0]), int(fc[1] * 0.82), int(fc[2] * 0.30), glow_a)
        d.ellipse([lbx - glow_r, lby - glow_r + 2,
                   lbx + glow_r, lby + glow_r + 2], fill=glow_col)

    blurred = overlay.filter(ImageFilter.GaussianBlur(radius=5))
    roi_img = Image.fromarray(frame[ry0:ry1, rx0:rx1]).convert("RGBA")
    merged  = Image.alpha_composite(roi_img, blurred)
    frame[ry0:ry1, rx0:rx1] = np.array(merged.convert("RGB"))


# ══════════════════════════════════════════════════════════════════════════════
#  DYNAMIC SYSTEMS
# ══════════════════════════════════════════════════════════════════════════════

class RainSystem:
    """Angled rain drops falling inside the window pane."""
    ANGLE_DEG = 14

    def __init__(self, theme: str, n: int = 110, rng_seed: int = 0):
        c = THEMES[theme]
        self.color      = np.array(c["rain"], dtype=np.float32)
        self.base_alpha = c["rain_a"] / 255.0
        rng = np.random.RandomState(rng_seed)
        self.n       = n
        self.x       = rng.uniform(WIN_X0, WIN_X1, n).astype(np.float32)
        self.y       = rng.uniform(-H, 0, n).astype(np.float32)
        self.speed   = rng.uniform(9, 22, n).astype(np.float32)
        self.length  = rng.randint(20, 55, n)
        self.opacity = rng.uniform(0.22, 0.65, n).astype(np.float32)
        self.dx_per_dy = math.tan(math.radians(self.ANGLE_DEG))

    def update(self):
        self.y += self.speed
        self.x += self.speed * self.dx_per_dy
        mask  = (self.y > WIN_Y1 + 50) | (self.x > WIN_X1 + 30)
        count = int(mask.sum())
        if count:
            rng = np.random.default_rng()
            self.y[mask] = rng.uniform(-120, WIN_Y0, count)
            self.x[mask] = rng.uniform(WIN_X0 - 60, WIN_X1, count)

    def render(self, frame: np.ndarray):
        adx = self.dx_per_dy
        col = self.color
        for i in range(self.n):
            alpha  = self.opacity[i] * self.base_alpha
            blend  = 1.0 - alpha
            length = int(self.length[i])
            steps  = np.arange(length, dtype=np.float32)
            py = (self.y[i] - steps).astype(np.int32)
            px = (self.x[i] - steps * adx).astype(np.int32)
            valid = (py >= WIN_Y0) & (py < WIN_Y1) & (px >= WIN_X0) & (px < WIN_X1)
            # Laptop is IN FRONT of window — don't render rain on its screen
            on_laptop = ((py >= LAPTOP_SCR_Y0) &
                         (px >= LAPTOP_SCR_X0) & (px < LAPTOP_SCR_X1))
            valid = valid & ~on_laptop
            py, px = py[valid], px[valid]
            if len(py) == 0:
                continue
            frame[py, px] = np.clip(
                frame[py, px].astype(np.float32) * blend + col * alpha,
                0, 255
            ).astype(np.uint8)


class GlassDripSystem:
    """Slow drips sliding down the window glass — distinct from rain outside."""
    def __init__(self, n: int = GLASS_DRIP_N, rng_seed: int = 88):
        rng = np.random.RandomState(rng_seed)
        self.n      = n
        self.x      = rng.randint(WIN_X0 + 20, WIN_X1 - 20, n).astype(np.float32)
        self.y      = rng.uniform(WIN_Y0 + 20, WIN_Y1 - 100, n).astype(np.float32)
        self.speed  = rng.uniform(0.15, 0.55, n).astype(np.float32)  # very slow
        self.length = rng.randint(12, 48, n)
        self.alpha  = rng.uniform(0.10, 0.28, n).astype(np.float32)
        self.active = rng.uniform(0, 1, n).astype(np.float32)  # staggered start

    def update(self):
        self.active = np.minimum(self.active + 0.008, 1.0)
        self.y += self.speed * self.active
        mask = self.y > WIN_Y1 - 10
        cnt  = int(mask.sum())
        if cnt:
            rng = np.random.default_rng()
            self.y[mask]    = rng.uniform(WIN_Y0 + 20, WIN_Y0 + 120, cnt)
            self.x[mask]    = rng.uniform(WIN_X0 + 20, WIN_X1 - 20, cnt)
            self.active[mask] = 0.0

    def render(self, frame: np.ndarray):
        col = np.array([200, 218, 240], dtype=np.float32)
        for i in range(self.n):
            if self.active[i] < 0.1:
                continue
            a = self.alpha[i] * self.active[i]
            cx_, cy_ = int(self.x[i]), int(self.y[i])
            length   = int(self.length[i])
            for j in range(length):
                py = cy_ + j
                if WIN_Y0 <= py < WIN_Y1 and WIN_X0 <= cx_ < WIN_X1 and not (
                        py >= LAPTOP_SCR_Y0 and LAPTOP_SCR_X0 <= cx_ < LAPTOP_SCR_X1):
                    seg_a = a * max(0.0, 1.0 - j / length)
                    frame[py, cx_] = np.clip(
                        frame[py, cx_].astype(np.float32) * (1 - seg_a) + col * seg_a,
                        0, 255
                    ).astype(np.uint8)


class SteamSystem:
    """Organic steam curls rising from coffee mug."""
    def __init__(self, theme: str, src_x: int, src_y: int,
                 n: int = 32, rng_seed: int = 12):
        c = THEMES[theme]
        self.color = np.array(c["steam"], dtype=np.float32)
        rng = np.random.RandomState(rng_seed)
        self.n        = n
        self.src_x    = src_x
        self.src_y    = src_y
        self.x        = rng.uniform(src_x - 10, src_x + 10, n).astype(np.float32)
        self.y        = rng.uniform(src_y - 50, src_y, n).astype(np.float32)
        self.vx       = rng.uniform(-0.35, 0.35, n).astype(np.float32)
        self.age      = rng.uniform(0, 1, n).astype(np.float32)
        self.max_life = rng.uniform(55, 100, n).astype(np.float32)
        self.size     = rng.uniform(4, 13, n).astype(np.float32)
        self.phase    = rng.uniform(0, 2 * np.pi, n).astype(np.float32)

    def update(self, t: float):
        self.age += 1.0
        vy   = np.random.uniform(0.38, 0.88, self.n)
        drift = 0.45 * np.sin(self.age * 0.08 + self.phase)
        self.y -= vy
        self.x += self.vx + drift + np.random.uniform(-0.14, 0.14, self.n)
        mask = (self.age >= self.max_life) | (self.y < self.src_y - 100)
        cnt  = int(mask.sum())
        if cnt:
            rng = np.random.default_rng()
            self.x[mask]   = rng.uniform(self.src_x - 10, self.src_x + 10, cnt)
            self.y[mask]   = rng.uniform(self.src_y - 5, self.src_y, cnt)
            self.age[mask] = 0

    def render(self, frame: np.ndarray):
        col = self.color
        for i in range(self.n):
            frac  = max(0.0, 1.0 - self.age[i] / self.max_life[i])
            alpha = frac * 0.22
            if alpha < 0.01:
                continue
            cx_, cy_ = int(self.x[i]), int(self.y[i])
            r = max(2, int(self.size[i]))
            y0, y1_ = max(0, cy_ - r), min(H, cy_ + r + 1)
            x0, x1_ = max(0, cx_ - r), min(W, cx_ + r + 1)
            if y0 >= y1_ or x0 >= x1_:
                continue
            yy, xx = np.ogrid[y0:y1_, x0:x1_]
            d = np.sqrt((yy - cy_) ** 2 + (xx - cx_) ** 2).astype(np.float32)
            falloff = np.clip(1.0 - d / r, 0, 1) * alpha
            region  = frame[y0:y1_, x0:x1_].astype(np.float32)
            frame[y0:y1_, x0:x1_] = np.clip(
                region * (1 - falloff[:, :, None]) + col * falloff[:, :, None],
                0, 255
            ).astype(np.uint8)


class CandleFlame:
    """Pre-computed flickering candle flame with glow halo."""
    def __init__(self, n_frames: int, cx: int, base_y: int):
        self.cx      = cx
        self.base_y  = base_y
        self.size_n  = looping_noise(n_frames, n_harmonics=8, seed=10)
        self.sway_n  = looping_noise(n_frames, n_harmonics=6, seed=20)
        self.bright_n= looping_noise(n_frames, n_harmonics=5, seed=30)

    def render(self, frame: np.ndarray, f_idx: int) -> None:
        sn = self.size_n[f_idx]
        sw = self.sway_n[f_idx]
        bn = self.bright_n[f_idx]

        flame_h = int(24 + 14 * sn)
        flame_w = int( 9 +  4 * sn)
        sway_x  = int( 5 * (sw - 0.5))
        cx_     = self.cx + sway_x
        tip_y   = self.base_y - flame_h

        brightness = 0.72 + 0.28 * bn
        outer_col  = (255, int((122 + 78 * bn) * brightness),
                      int(( 22 + 28 * sn) * brightness), int(205 * brightness))
        inner_col  = (255, int((202 + 53 * bn) * brightness),
                      int(( 62 + 78 * sn) * brightness), int(225 * brightness))
        glow_size  = int(52 + 28 * bn)

        # --- Tight ROI: only process a small crop around the flame ---
        pad = glow_size + 12
        ry0 = max(0, tip_y - pad);         ry1 = min(H, self.base_y + 20)
        rx0 = max(0, cx_ - pad);           rx1 = min(W, cx_ + pad)
        rh, rw = ry1 - ry0, rx1 - rx0
        if rh <= 0 or rw <= 0:
            return

        # Local coords inside ROI
        lcx  = cx_          - rx0
        lby  = self.base_y  - ry0
        ltip = tip_y        - ry0

        overlay = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
        d       = ImageDraw.Draw(overlay)

        glow_a = int(88 * brightness)
        d.ellipse([lcx - glow_size, lby - glow_size,
                   lcx + glow_size, lby + 10],
                  fill=(255, int(138 * brightness), 28, glow_a))
        d.polygon([
            (lcx,              ltip),
            (lcx + flame_w,    lby - flame_h // 3),
            (lcx + flame_w//2, lby),
            (lcx - flame_w//2, lby),
            (lcx - flame_w,    lby - flame_h // 3),
        ], fill=outer_col)
        d.polygon([
            (lcx,              ltip + flame_h // 4),
            (lcx + flame_w//2, lby - flame_h // 5),
            (lcx,              lby - 2),
            (lcx - flame_w//2, lby - flame_h // 5),
        ], fill=inner_col)
        d.ellipse([lcx - 3, ltip - 2, lcx + 3, ltip + 6],
                  fill=(255, 255, int(120 + 80 * sn), int(180 * brightness)))

        blurred = overlay.filter(ImageFilter.GaussianBlur(radius=9))
        d2 = ImageDraw.Draw(blurred)
        d2.polygon([
            (lcx,              ltip),
            (lcx + flame_w,    lby - flame_h // 3),
            (lcx + flame_w//2, lby),
            (lcx - flame_w//2, lby),
            (lcx - flame_w,    lby - flame_h // 3),
        ], fill=outer_col)
        d2.polygon([
            (lcx,              ltip + flame_h // 4),
            (lcx + flame_w//2, lby - flame_h // 5),
            (lcx,              lby - 2),
            (lcx - flame_w//2, lby - flame_h // 5),
        ], fill=inner_col)

        roi_img = Image.fromarray(frame[ry0:ry1, rx0:rx1]).convert("RGBA")
        merged  = Image.alpha_composite(roi_img, blurred)
        frame[ry0:ry1, rx0:rx1] = np.array(merged.convert("RGB"))


class DustMotes:
    """Slow-drifting dust motes in the warm lamp illumination zone."""
    def __init__(self, n: int = 28, rng_seed: int = 99):
        rng = np.random.RandomState(rng_seed)
        self.n    = n
        # Spawn in the lamp cone zone
        self.x    = rng.uniform(LAMP_X - 350, LAMP_X + 180, n).astype(np.float32)
        self.y    = rng.uniform(LAMP_CY + 20, DESK_Y - 20, n).astype(np.float32)
        self.age  = rng.uniform(0, 1, n).astype(np.float32)
        self.life = rng.uniform(110, 230, n).astype(np.float32)
        self.size = rng.uniform(1.5, 4.2, n).astype(np.float32)
        self.vx   = rng.uniform(-0.30, 0.30, n).astype(np.float32)
        self.vy   = rng.uniform(-0.22, 0.06, n).astype(np.float32)

    def update(self):
        self.age += 1.0
        self.x += self.vx + np.random.normal(0, 0.14, self.n)
        self.y += self.vy + np.random.normal(0, 0.09, self.n)
        mask = ((self.age >= self.life) | (self.y < LAMP_CY - 80) | (self.y > DESK_Y))
        cnt  = int(mask.sum())
        if cnt:
            rng = np.random.default_rng()
            self.x[mask]   = rng.uniform(LAMP_X - 330, LAMP_X + 160, cnt)
            self.y[mask]   = rng.uniform(LAMP_CY + 40, DESK_Y - 15, cnt)
            self.age[mask] = 0

    def render(self, frame: np.ndarray):
        for i in range(self.n):
            life_frac = 1.0 - abs(self.age[i] / self.life[i] - 0.5) * 2
            alpha = life_frac * 0.30
            if alpha < 0.02:
                continue
            cx_, cy_ = int(self.x[i]), int(self.y[i])
            r = max(1, int(self.size[i]))
            y0, y1_ = max(0, cy_ - r), min(H, cy_ + r + 1)
            x0, x1_ = max(0, cx_ - r), min(W, cx_ + r + 1)
            if y0 >= y1_ or x0 >= x1_:
                continue
            yy, xx = np.ogrid[y0:y1_, x0:x1_]
            d = np.sqrt((yy - cy_) ** 2 + (xx - cx_) ** 2).astype(np.float32)
            falloff  = np.clip(1.0 - d / (r + 0.5), 0, 1) * alpha
            mote_col = np.array([232, 218, 192], dtype=np.float32)
            region   = frame[y0:y1_, x0:x1_].astype(np.float32)
            frame[y0:y1_, x0:x1_] = np.clip(
                region * (1 - falloff[:, :, None]) + mote_col * falloff[:, :, None],
                0, 255
            ).astype(np.uint8)


class PlantLeafSystem:
    """Subtle oscillation of the succulent's outer ring of petals."""
    def __init__(self, n_frames: int, rng_seed: int = 77):
        # 10 outer petal tips oscillate individually
        self.n_petals = 10
        rng = np.random.RandomState(rng_seed)
        # Pre-compute per-petal looping noise
        self.leaf_noise = np.array([
            looping_noise(n_frames, n_harmonics=4, seed=rng_seed + i)
            for i in range(self.n_petals)
        ])  # shape (n_petals, n_frames)
        self.phases    = rng.uniform(0, 2 * math.pi, self.n_petals)
        self.amplitudes = rng.uniform(1.5, 4.0, self.n_petals)

    def get_offsets(self, f_idx: int) -> list:
        """Return list of (dx, dy) offsets for each outer petal tip."""
        offsets = []
        for i in range(self.n_petals):
            n = self.leaf_noise[i, f_idx]
            amp = self.amplitudes[i]
            dx = amp * (n - 0.5) * math.cos(self.phases[i])
            dy = amp * (n - 0.5) * math.sin(self.phases[i]) * 0.3  # gentler vertical
            offsets.append((dx, dy))
        return offsets

    def render(self, frame: np.ndarray, f_idx: int, theme: str) -> None:
        """Redraw outer petal ring with animated offsets — pure numpy ellipses."""
        offsets  = self.get_offsets(f_idx)
        base_y   = PLANT_Y - 50
        ring_r   = 30
        petal_len = 22
        pw, ph   = 5, 10    # petal semi-axes
        green    = np.array([62, 138, 75], dtype=np.uint8)
        for i in range(self.n_petals):
            angle   = 2 * math.pi * i / self.n_petals + 0.4
            dx_off, dy_off = offsets[i]
            mid_x = PLANT_X + int((ring_r + petal_len / 2) * math.cos(angle) + dx_off * 0.5)
            mid_y = base_y  - int((ring_r + petal_len / 2) * 0.45 * math.sin(angle + math.pi / 2) - dy_off * 0.5)
            y0, y1_ = max(0, mid_y - ph), min(H, mid_y + ph + 1)
            x0, x1_ = max(0, mid_x - pw), min(W, mid_x + pw + 1)
            if y0 >= y1_ or x0 >= x1_:
                continue
            yy, xx = np.ogrid[y0:y1_, x0:x1_]
            mask = ((yy - mid_y) / ph) ** 2 + ((xx - mid_x) / pw) ** 2 <= 1
            frame[y0:y1_, x0:x1_][mask] = green


class SparkleSystem:
    """4-pointed star sparkles near lamp shade and reflective surfaces."""

    def __init__(self, n_frames: int, rng_seed: int = 57):
        rng = np.random.RandomState(rng_seed)
        # Spawn coords: around lamp shade, laptop screen top, fairy light zone
        spawn = [
            (LAMP_X - 72, LAMP_CY - 42), (LAMP_X + 50, LAMP_CY - 58),
            (LAMP_X - 18, LAMP_CY - 28), (LAMP_X + 28, LAMP_CY - 14),
            (LAMP_X - 95, LAMP_CY - 65), (LAMP_X + 12, LAMP_CY - 80),
            (LAPTOP_CX - 72, LAPTOP_Y - 302), (LAPTOP_CX + 68, LAPTOP_Y - 298),
            (WIN_X0 - 40, WIN_Y0 - 18),  (WIN_X1 + 38, WIN_Y0 - 22),
        ]
        self.n  = len(spawn)
        self.sx = np.array([s[0] for s in spawn], dtype=np.float32)
        self.sy = np.array([s[1] for s in spawn], dtype=np.float32)
        # Per-sparkle looping brightness noise, staggered phases
        self.noise        = np.array([
            looping_noise(n_frames, n_harmonics=3, seed=rng_seed + i)
            for i in range(self.n)
        ])  # (n, n_frames)
        self.phase_offset = rng.randint(0, n_frames, self.n)

    def render(self, frame: np.ndarray, f_idx: int, theme: str) -> None:
        c  = THEMES[theme]
        lc = np.array(c["lamp_col"], dtype=np.float32)
        for i in range(self.n):
            n_idx      = (f_idx + int(self.phase_offset[i])) % self.noise.shape[1]
            brightness = float(self.noise[i, n_idx])
            if brightness < 0.52:
                continue
            alpha = (brightness - 0.52) / 0.48   # 0..1
            cx_, cy_ = int(self.sx[i]), int(self.sy[i])
            size     = max(3, int(3 + 10 * alpha))
            # Warm white-yellow tint
            col = (
                int(min(255, lc[0] * 0.65 + 255 * 0.35)),
                int(min(255, lc[1] * 0.65 + 255 * 0.35)),
                int(min(255, lc[2] * 0.45 + 255 * 0.55)),
            )
            pad  = size + 5
            ry0  = max(0, cy_ - pad);  ry1 = min(H, cy_ + pad + 1)
            rx0  = max(0, cx_ - pad);  rx1 = min(W, cx_ + pad + 1)
            if ry0 >= ry1 or rx0 >= rx1:
                continue
            rh_, rw_ = ry1 - ry0, rx1 - rx0
            lcx_, lcy_ = cx_ - rx0, cy_ - ry0
            a_int = int(alpha * 235)
            overlay = Image.new("RGBA", (rw_, rh_), (0, 0, 0, 0))
            d = ImageDraw.Draw(overlay)
            # Long 4-pointed cross
            d.line([(lcx_ - size, lcy_), (lcx_ + size, lcy_)],
                   fill=(*col, a_int), width=2)
            d.line([(lcx_, lcy_ - size), (lcx_, lcy_ + size)],
                   fill=(*col, a_int), width=2)
            # Short diagonal cross (45°), half intensity
            diag = max(1, int(size * 0.42))
            d.line([(lcx_ - diag, lcy_ - diag), (lcx_ + diag, lcy_ + diag)],
                   fill=(*col, a_int // 2), width=1)
            d.line([(lcx_ + diag, lcy_ - diag), (lcx_ - diag, lcy_ + diag)],
                   fill=(*col, a_int // 2), width=1)
            # Bright centre dot
            d.ellipse([lcx_ - 2, lcy_ - 2, lcx_ + 2, lcy_ + 2],
                      fill=(255, 255, 255, a_int))
            blurred = overlay.filter(ImageFilter.GaussianBlur(radius=2))
            roi_img = Image.fromarray(frame[ry0:ry1, rx0:rx1]).convert("RGBA")
            merged  = Image.alpha_composite(roi_img, blurred)
            frame[ry0:ry1, rx0:rx1] = np.array(merged.convert("RGB"))


# ══════════════════════════════════════════════════════════════════════════════
#  PER-FRAME POST-PROCESSING
# ══════════════════════════════════════════════════════════════════════════════

def apply_curtain_sway(frame: np.ndarray, t: float, theme: str) -> np.ndarray:
    """Redraw curtains with per-fold sine sway — pure numpy, no PIL overhead."""
    c       = THEMES[theme]
    period  = 5.0
    n_folds = 7
    fold_colors = [c["curtain_lo"], c["curtain_hi"], c["curtain"],
                   c["curtain_lo"], c["curtain_hi"], c["curtain"], c["curtain_lo"]]
    lw  = (LCURT_X1 - LCURT_X0) // n_folds
    rw_ = (RCURT_X1 - RCURT_X0) // n_folds

    cy0 = max(0, WIN_Y0 - 52);  cy1 = min(H, WIN_Y1 + 52)
    sc0 = max(0, WIN_Y0 - 54);  sc1 = max(0, WIN_Y0 - 26)
    dk  = np.array(c["curtain_lo"], dtype=np.uint8)

    for i in range(n_folds):
        phase = i * (math.pi / 4)
        sway  = int(6 * math.sin(2 * math.pi * t / period + phase))

        # Left fold body
        x0 = max(0, LCURT_X0 + i * lw + sway)
        x1 = min(W, x0 + lw + 2)
        if x0 < x1:
            frame[cy0:cy1, x0:x1] = fold_colors[i]
        # Left scallop top
        sx0 = max(0, LCURT_X0 + i * lw + sway - 3)
        sx1 = min(W, sx0 + lw + 6)
        if sc0 < sc1 and sx0 < sx1:
            frame[sc0:sc1, sx0:sx1] = dk

        # Right fold body
        x0r = max(0, RCURT_X0 + i * rw_ - sway)
        x1r = min(W, x0r + rw_ + 2)
        if x0r < x1r:
            frame[cy0:cy1, x0r:x1r] = fold_colors[n_folds - 1 - i]
        # Right scallop top
        sxr0 = max(0, RCURT_X0 + i * rw_ - sway - 3)
        sxr1 = min(W, sxr0 + rw_ + 6)
        if sc0 < sc1 and sxr0 < sxr1:
            frame[sc0:sc1, sxr0:sxr1] = dk

    return frame


def apply_cat_breathing(frame: np.ndarray, cat_arr: np.ndarray,
                        cat_ccx: int, cat_ccy: int, t: float) -> None:
    """Composite cat with sine breathing offset."""
    breath_off = int(2 * math.sin(2 * math.pi * t / 4.0))
    paste_cat(frame, cat_arr,
              paste_x=CAT_CX - cat_ccx,
              paste_y=CAT_CY + breath_off - cat_ccy)


def warm_grade(frame: np.ndarray, theme: str) -> np.ndarray:
    c = THEMES[theme]
    f = frame.astype(np.int16)
    f[:, :, 0] = np.clip(f[:, :, 0] + c["warmth_r"], 0, 255)
    f[:, :, 2] = np.clip(f[:, :, 2] + c["warmth_b"], 0, 255)
    return f.astype(np.uint8)


def apply_bloom(frame: np.ndarray, threshold: int = 180,
                strength: float = 0.38, radius: int = 12) -> np.ndarray:
    bright = np.clip(frame.astype(np.int16) - threshold, 0, 255).astype(np.uint8)
    if bright.max() == 0:
        return frame
    bloom = np.array(
        Image.fromarray(bright).filter(ImageFilter.GaussianBlur(radius=radius))
    ).astype(np.float32)
    return np.clip(frame.astype(np.float32) + bloom * strength, 0, 255).astype(np.uint8)


def chromatic_aberration(frame: np.ndarray, shift: int = 2) -> np.ndarray:
    result = frame.copy()
    result[:, shift:,  0] = frame[:, :-shift, 0]
    result[:, :-shift, 2] = frame[:, shift:,  2]
    return result


def film_grain(frame: np.ndarray, strength: float = 6.5) -> np.ndarray:
    g = np.random.normal(0, strength, frame.shape).astype(np.int16)
    return np.clip(frame.astype(np.int16) + g, 0, 255).astype(np.uint8)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def generate_visual(theme_name: str = "cozy_rain",
                    duration_secs: int = 30, fps: int = FPS,
                    visual_seed: int = None):
    if theme_name not in THEMES:
        theme_name = "cozy_rain"
    if visual_seed is None:
        visual_seed = random.randint(0, 9999)

    n_frames = duration_secs * fps
    ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(VISUALS_DIR, f"bg_{theme_name}_{ts}.mp4")

    print(f"[VISUAL] {theme_name} | seed={visual_seed} | {n_frames} frames | {duration_secs}s")
    print("  Pre-rendering static scene...")

    city             = make_bokeh_city(theme_name, seed=visual_seed)
    static           = make_static_scene(theme_name, city)
    lamp_map         = make_lamp_light_map(theme_name)
    win_ambient      = make_window_ambient(theme_name)
    laptop_glow      = make_laptop_glow_map()
    ao_mask          = make_ambient_occlusion(theme_name)
    vignette         = make_vignette(strength=0.30)
    city_twinkle     = make_bokeh_twinkle(n_frames, seed=visual_seed + 42)
    candle_glow_map  = make_candle_glow_map()

    lamp_pulse_noise = looping_noise(n_frames, n_harmonics=5, seed=visual_seed + 55)
    lamp_pulse       = 0.82 + 0.18 * lamp_pulse_noise

    # Laptop glow pulse (subtle breathing)
    laptop_pulse     = 0.85 + 0.15 * looping_noise(n_frames, n_harmonics=3, seed=visual_seed + 66)

    # Cat (Cairo cel-shaded)
    cat_img, cat_ccx, cat_ccy = make_cat_cairo(theme_name)
    cat_arr = np.array(cat_img)

    # Fairy lights
    fairy_positions  = make_fairy_positions()
    fairy_noise      = make_fairy_noise(n_frames)   # (n_frames, FAIRY_N)

    # Dynamic systems — seeds offset by visual_seed so each render is unique
    rain    = RainSystem(theme_name, n=110,  rng_seed=visual_seed)
    drips   = GlassDripSystem(rng_seed=visual_seed + 88)
    steam   = SteamSystem(theme_name, src_x=MUG_X, src_y=MUG_TOP, rng_seed=visual_seed + 12)
    flame   = CandleFlame(n_frames, cx=CANDLE_X, base_y=CANDLE_BASE - 74)
    dust    = DustMotes(n=28, rng_seed=visual_seed + 99)
    leaves  = PlantLeafSystem(n_frames, rng_seed=visual_seed + 77)
    sparks  = SparkleSystem(n_frames, rng_seed=visual_seed + 57)

    # ffmpeg rawvideo pipe
    ffcmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{W}x{H}", "-pix_fmt", "rgb24",
        "-r", str(fps), "-i", "pipe:0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", "20", "-preset", "fast",
        "-movflags", "+faststart",
        out_path,
    ]
    proc = subprocess.Popen(ffcmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    try:
        for f_idx in range(n_frames):
            t   = f_idx / fps
            pls = float(lamp_pulse[f_idx])
            lpt = float(laptop_pulse[f_idx])

            # 1. Base: AO on static scene
            frame = np.clip(
                static.astype(np.float32) * ao_mask[:, :, None],
                0, 255
            ).astype(np.uint8)

            # 2. City twinkle
            twink = float(city_twinkle[f_idx])
            frame[WIN_Y0:WIN_Y1, WIN_X0:WIN_X1] = np.clip(
                frame[WIN_Y0:WIN_Y1, WIN_X0:WIN_X1].astype(np.float32) * twink,
                0, 255
            ).astype(np.uint8)

            # 3. Lamp illumination (additive, warm, pulsing)
            frame = np.clip(
                frame.astype(np.float32)
                + lamp_map * pls * 100
                + win_ambient * 32
                + laptop_glow * lpt * 55,
                0, 255
            ).astype(np.uint8)

            # 4. Curtain sway (redraws curtains with sine offsets)
            frame = apply_curtain_sway(frame, t, theme_name)

            # 5. Cat breathing — AFTER curtain so cat appears IN FRONT of curtain (correct z-order)
            apply_cat_breathing(frame, cat_arr, cat_ccx, cat_ccy, t)

            # 6. Rain (outside, fast)
            rain.update()
            rain.render(frame)

            # 7. Glass drips (inside pane, slow)
            drips.update()
            drips.render(frame)

            # 8. Steam from mug
            steam.update(t)
            steam.render(frame)

            # 9. Candle flame
            flame.render(frame, f_idx)

            # 10. Candle spill
            candle_bright = float(flame.bright_n[f_idx])
            frame = np.clip(
                frame.astype(np.float32) + candle_glow_map * (candle_bright * 92),
                0, 255
            ).astype(np.uint8)

            # 11. Dust motes
            dust.update()
            dust.render(frame)

            # 12. Plant leaf oscillation
            leaves.render(frame, f_idx, theme_name)

            # 13. Fairy lights (individual bulb flicker)
            draw_fairy_lights(frame, fairy_positions, fairy_noise[f_idx], theme_name)

            # 13b. Sparkles (near lamp + screen edges)
            sparks.render(frame, f_idx, theme_name)

            # 14. Post-processing
            frame = warm_grade(frame, theme_name)
            # Cool blue shadow overlay — anime night-room depth
            frame[:, :, 2] = np.clip(
                frame[:, :, 2].astype(np.int16) + 10, 0, 255
            ).astype(np.uint8)
            frame = apply_bloom(frame, threshold=162, strength=0.46, radius=14)
            frame = np.clip(
                frame.astype(np.float32) * vignette[:, :, None],
                0, 255
            ).astype(np.uint8)
            frame = film_grain(frame, strength=4.0)

            proc.stdin.write(frame.tobytes())

            if f_idx % (fps * 5) == 0:
                print(f"  {f_idx * 100 // n_frames}%  ({f_idx}/{n_frames})")

    finally:
        proc.stdin.close()
        proc.wait()

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"[VISUAL] Done: {out_path} ({size_mb:.1f} MB)")
    return out_path, theme_name


if __name__ == "__main__":
    theme    = sys.argv[1] if len(sys.argv) > 1 else "cozy_rain"
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    seed     = int(sys.argv[3]) if len(sys.argv) > 3 else None
    generate_visual(theme_name=theme, duration_secs=duration, visual_seed=seed)
