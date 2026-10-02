"""
thumbnail_scene.py — the illustrated room behind a thumbnail's title.

A cozy room at the theme's time of day: a big window whose view matches the
theme (rain, snow, a lit city, a moon, a sunset, blossom), a desk lit by a
warm lamp, and a few things on it (mug, plant, books, headphones, records).
It replaces a single small silhouette on a dark gradient, which read as
empty at thumbnail size. Everything is drawn with PIL; no image assets.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# What's outside the window, per visual theme.
_VIEW = {
    "cozy_rain": "rain_city", "forest_rain": "rain_forest", "winter_snow": "snow",
    "midnight_cafe": "night_city", "neon_tokyo": "neon_city", "purple_dusk": "dusk_city",
    "blue_hour": "dusk_city", "amber_night": "night_city", "lofi_house": "night_city",
    "lofi_rnb": "night_city", "bedroom_pop": "dusk_city", "summer_lofi": "sunset",
    "autumn_study": "autumn", "vaporwave": "vapor_sunset", "sakura_night": "blossom_night",
    "spring_dawn": "dawn", "lofi_classical": "moon",
}

_WARM = (255, 196, 120)


def _mix(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def _sky(view: str, c: dict) -> tuple[tuple, tuple]:
    top = tuple(min(255, int(v * 1.6) + 6) for v in c["bg_top"])
    if view in ("sunset", "autumn"):
        return (70, 40, 90), (255, 150, 90)
    if view == "vapor_sunset":
        return (48, 22, 92), (255, 112, 186)
    if view == "dawn":
        return (110, 128, 196), (255, 196, 196)
    if view == "snow":
        return (24, 34, 72), (92, 112, 160)
    return top, _mix(c["accent"], c["bg_bot"], 0.55)


def _window_box(window_side: str, TW: int, TH: int) -> tuple[int, int, int, int]:
    if window_side == "center":
        return int(TW * 0.27), int(TH * 0.07), int(TW * 0.73), int(TH * 0.62)
    if window_side == "left":
        return int(TW * 0.05), int(TH * 0.08), int(TW * 0.47), int(TH * 0.66)
    return int(TW * 0.53), int(TH * 0.08), int(TW * 0.95), int(TH * 0.66)


def _view_layer(view: str, c: dict, w: int, h: int, rng) -> Image.Image:
    """The scene outside the window, drawn at window size."""
    top, bot = _sky(view, c)
    ys = np.linspace(0, 1, h)[:, None, None]
    arr = (np.array(top, np.float32) * (1 - ys) + np.array(bot, np.float32) * ys)
    arr = np.repeat(arr, w, axis=1)
    # An opaque RGB layer drawn in "RGBA" mode blends each translucent shape
    # (halos, rain, lit windows) onto it. On an RGBA layer they would replace
    # its alpha instead, and the dark wall showed through as rings.
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img, "RGBA")

    night = view not in ("sunset", "autumn", "vapor_sunset", "dawn")
    if night:
        for _ in range(int(rng.integers(25, 45))):
            x, y = rng.uniform(0, w), rng.uniform(0, h * 0.55)
            b = int(rng.uniform(150, 235))
            d.point((x, y), fill=(b, b, min(255, b + 20), 255))
    if view in ("moon", "blossom_night", "night_city", "snow", "dusk_city"):
        mr = h * 0.09
        mx, my = w * rng.uniform(0.62, 0.8), h * rng.uniform(0.18, 0.28)
        for k in range(6, 0, -1):                       # soft halo
            a = int(14 * k)
            d.ellipse([mx - mr * (1 + k * 0.35), my - mr * (1 + k * 0.35),
                       mx + mr * (1 + k * 0.35), my + mr * (1 + k * 0.35)],
                      fill=(255, 244, 214, max(4, 40 - a)))
        d.ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=(255, 246, 220, 255))
    if view in ("sunset", "autumn", "vapor_sunset"):
        sr = h * 0.2
        sx, sy = w * 0.55, h * 0.74
        sun = (255, 214, 120) if view != "vapor_sunset" else (255, 190, 90)
        for k in range(5, 0, -1):
            d.ellipse([sx - sr * (1 + k * 0.25), sy - sr * (1 + k * 0.25),
                       sx + sr * (1 + k * 0.25), sy + sr * (1 + k * 0.25)],
                      fill=(*sun, 18))
        d.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(*sun, 255))
        if view == "vapor_sunset":                      # the classic striped sun
            for i in range(5):
                yy = sy + sr * (0.1 + i * 0.18)
                d.rectangle([sx - sr, yy, sx + sr, yy + sr * 0.05 * (i + 1)], fill=(*bot, 255))

    if view.endswith("city") or view == "snow":
        lit = c["accent"] if view == "neon_city" else _WARM
        x = 0.0
        while x < w:
            bw = rng.uniform(w * 0.06, w * 0.14)
            bh = rng.uniform(h * 0.18, h * (0.55 if view == "neon_city" else 0.42))
            shade = tuple(int(v * 0.45) for v in top)
            d.rectangle([x, h - bh, x + bw - 2, h], fill=(*shade, 255))
            for wy in np.arange(h - bh + 8, h - 6, 11):
                for wx in np.arange(x + 5, x + bw - 8, 9):
                    if rng.random() < 0.32:
                        d.rectangle([wx, wy, wx + 4, wy + 5], fill=(*lit, int(rng.uniform(140, 230))))
            if view == "neon_city" and rng.random() < 0.35:   # a neon sign
                sy0 = h - bh + rng.uniform(10, bh * 0.4)
                d.rectangle([x + 4, sy0, x + bw - 8, sy0 + 6], fill=(*c["accent"], 230))
            x += bw
    if view in ("rain_forest", "autumn", "blossom_night", "dawn"):
        leaf = {"autumn": (196, 92, 40), "blossom_night": (255, 170, 205),
                "dawn": (255, 186, 214)}.get(view, (20, 40, 34))
        trunk = tuple(int(v * 0.35) for v in top)
        for _ in range(int(rng.integers(4, 7))):
            tx, th_ = rng.uniform(0, w), rng.uniform(h * 0.3, h * 0.6)
            d.rectangle([tx - 4, h - th_, tx + 4, h], fill=(*trunk, 255))
            for _ in range(7):
                r = rng.uniform(h * 0.06, h * 0.12)
                cx, cy = tx + rng.uniform(-r, r), h - th_ + rng.uniform(-r, r * 0.6)
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*leaf, 235))
    if view in ("rain_city", "rain_forest"):
        for _ in range(int(rng.integers(70, 110))):
            x, y = rng.uniform(0, w), rng.uniform(0, h)
            ln = rng.uniform(10, 26)
            d.line([(x, y), (x + ln * 0.15, y + ln)], fill=(205, 222, 255, int(rng.uniform(60, 130))), width=1)
    if view == "snow":
        for _ in range(int(rng.integers(80, 120))):
            x, y, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(1.2, 3.2)
            d.ellipse([x - r, y - r, x + r, y + r], fill=(240, 246, 255, int(rng.uniform(150, 240))))
    if view in ("blossom_night", "dawn"):
        for _ in range(int(rng.integers(18, 30))):
            x, y, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(3, 6)
            d.ellipse([x - r, y - r * 0.55, x + r, y + r * 0.55], fill=(255, 190, 215, 200))
    return img


def _books(d, x, base, s, palette):
    y = base
    for i in range(3):
        bw, bh = s * (0.9 - i * 0.12), s * 0.16
        col = palette[i % len(palette)]
        d.rounded_rectangle([x - bw / 2, y - bh, x + bw / 2, y], radius=3, fill=(*col, 255))
        d.line([(x - bw / 2 + 4, y - bh * 0.5), (x + bw / 2 - 4, y - bh * 0.5)],
               fill=(255, 235, 200, 90), width=1)
        y -= bh + 1


def _headphones(d, x, base, s, fill, rim):
    r = s * 0.42
    d.arc([x - r, base - r * 1.6, x + r, base + r * 0.4], 180, 360, fill=rim, width=max(3, int(s * 0.07)))
    for sx in (x - r, x + r):
        d.rounded_rectangle([sx - s * 0.12, base - s * 0.34, sx + s * 0.12, base],
                            radius=int(s * 0.06), fill=fill, outline=rim, width=2)


def _lamp(img: Image.Image, x: int, desk_y: int, s: float, flip: bool) -> None:
    """Desk lamp and its warm pool of light (drawn additively)."""
    TW, TH = img.size
    arr = np.asarray(img, dtype=np.float32)
    ys, xs = np.mgrid[0:TH, 0:TW]
    gx, gy = x + (-s * 0.5 if flip else s * 0.5), desk_y - s * 0.95
    dist = np.sqrt((xs - gx) ** 2 + ((ys - gy) * 1.25) ** 2)
    glow = np.clip(1 - dist / (s * 5.0), 0, 1) ** 1.8
    arr = np.clip(arr + np.array(_WARM, np.float32) * glow[..., None] * 0.75, 0, 255)
    img.paste(Image.fromarray(arr.astype(np.uint8)))
    d = ImageDraw.Draw(img, "RGBA")
    dark = (28, 22, 20, 255)
    d.ellipse([x - s * 0.28, desk_y - s * 0.08, x + s * 0.28, desk_y + s * 0.04], fill=dark)
    arm_top = (x + (-s * 0.4 if flip else s * 0.4), desk_y - s * 1.1)
    d.line([(x, desk_y - s * 0.04), (x, desk_y - s * 0.7), arm_top], fill=dark, width=max(3, int(s * 0.06)))
    hx, hy = arm_top
    sh = s * 0.32
    shade = [(hx - sh, hy + sh * 0.6), (hx - sh * 0.45, hy - sh * 0.35),
             (hx + sh * 0.45, hy - sh * 0.35), (hx + sh, hy + sh * 0.6)]
    d.polygon(shade, fill=(44, 34, 30, 255), outline=(*_WARM, 200))
    d.ellipse([hx - sh * 0.35, hy + sh * 0.45, hx + sh * 0.35, hy + sh * 0.75], fill=(255, 236, 190, 255))


SUPERSAMPLE = 2   # draw at 2x and downscale: PIL shapes have no anti-aliasing


def _wall(c: dict, W: int, H: int, rng) -> Image.Image:
    """A plain painted interior wall: a soft vertical gradient a little lighter
    than the night sky colours, with faint wallpaper stripes. (The old
    background put stars and bokeh blobs on the wall.)"""
    top = np.array([min(255, v * 1.35 + 8) for v in c["bg_top"]], np.float32)
    bot = np.array([min(255, v * 1.2 + 6) for v in c["bg_bot"]], np.float32)
    ys = np.linspace(0, 1, H)[:, None, None]
    arr = np.repeat(top * (1 - ys) + bot * ys, W, axis=1)
    stripes = (np.sin(np.arange(W) / W * math.pi * 2 * 26) > 0.92).astype(np.float32) * 5
    arr = arr + stripes[None, :, None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _spill(img: Image.Image, box, color, strength: float) -> None:
    """Soft light from the window falling on the wall around it."""
    W, H = img.size
    x0, y0, x1, y1 = box
    arr = np.asarray(img, dtype=np.float32)
    ys, xs = np.mgrid[0:H, 0:W]
    dx = np.maximum(0, np.maximum(x0 - xs, xs - x1))
    dy = np.maximum(0, np.maximum(y0 - ys, ys - y1))
    d = np.sqrt(dx ** 2 + dy ** 2)
    g = np.clip(1 - d / (H * 0.35), 0, 1) ** 2.5
    arr = np.clip(arr + np.array(color, np.float32) * g[..., None] * strength, 0, 255)
    img.paste(Image.fromarray(arr.astype(np.uint8)))


def _fairy_lights(d, x0, x1, y, sag, n, rng, s) -> None:
    pts = [(x0 + (x1 - x0) * i / (n - 1), y + sag * math.sin(math.pi * i / (n - 1)))
           for i in range(n)]
    d.line(pts, fill=(40, 30, 26, 255), width=max(2, int(s * 0.6)))
    for (px, py) in pts[1:-1]:
        col = (255, 214, 140) if rng.random() < 0.8 else (255, 170, 190)
        for k, a in ((3.2, 30), (2.0, 60)):
            r = s * k
            d.ellipse([px - r, py - r, px + r, py + r], fill=(*col, a))
        r = s * 0.9
        d.ellipse([px - r, py - r, px + r, py + r], fill=(*col, 255))


def _listener(d, cx, desk_y, H, rim, hair_style: int) -> None:
    """Someone at the desk, seen from behind: hoodie, headphones, elbows on the
    desk, silhouetted against the window. Lofi's familiar figure: present,
    never looking at the viewer."""
    dark, mid = (18, 14, 18, 255), (32, 25, 31, 255)
    w = max(2, int(H * 0.004))
    head_r = H * 0.06
    head_cy = desk_y - H * 0.2
    neck_y = head_cy + head_r * 0.85
    sh_w = H * 0.37                       # shoulder width
    sh_y = neck_y + H * 0.04              # shoulder line
    # Hoodie body: sloped shoulders into a wide back, down past the frame.
    body = [(cx - sh_w * 0.16, neck_y), (cx + sh_w * 0.16, neck_y),
            (cx + sh_w * 0.44, sh_y), (cx + sh_w * 0.52, sh_y + H * 0.07),
            (cx + sh_w * 0.56, H * 1.02), (cx - sh_w * 0.56, H * 1.02),
            (cx - sh_w * 0.52, sh_y + H * 0.07), (cx - sh_w * 0.44, sh_y)]
    d.polygon(body, fill=dark, outline=rim, width=w)
    # Hood folded at the back of the neck, and a spine shadow.
    d.chord([cx - sh_w * 0.24, neck_y - H * 0.02, cx + sh_w * 0.24, neck_y + H * 0.09],
            0, 180, fill=mid)
    d.line([(cx, neck_y + H * 0.09), (cx, H)], fill=(12, 10, 13, 255), width=max(2, int(H * 0.006)))
    # Head, hair, headphones.
    d.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r],
              fill=dark, outline=rim, width=w)
    if hair_style == 1:      # bun
        r = head_r * 0.42
        d.ellipse([cx - r, head_cy - head_r * 1.32 - r * 0.2, cx + r, head_cy - head_r * 1.32 + r * 1.6],
                  fill=dark, outline=rim, width=w)
    elif hair_style == 2:    # ponytail
        d.line([(cx + head_r * 0.1, head_cy + head_r * 0.1),
                (cx + head_r * 0.55, head_cy + head_r * 1.5)],
               fill=dark, width=int(head_r * 0.5), joint="curve")
    band = head_r * 1.16
    d.arc([cx - band, head_cy - band * 1.08, cx + band, head_cy + band * 0.9], 190, 350,
          fill=rim, width=max(3, int(H * 0.01)))
    for side in (-1, 1):
        ex = cx + side * head_r * 1.0
        d.rounded_rectangle([ex - head_r * 0.25, head_cy - head_r * 0.34,
                             ex + head_r * 0.25, head_cy + head_r * 0.38],
                            radius=int(head_r * 0.16), fill=mid, outline=rim, width=w)


def draw_room(img: Image.Image, c: dict, theme: str, window_side: str,
              rng: np.random.Generator) -> Image.Image:
    """Return the room scene (same size as `img`). `window_side` is where the
    window goes: opposite the title, or "center" behind a centered title.
    Drawn at SUPERSAMPLE x and downscaled for smooth edges."""
    from scripts.generate_thumbnail_cozy import (
        _silhouette_cat, _silhouette_coffee_cup, _silhouette_plant,
    )
    out_w, out_h = img.size
    S = SUPERSAMPLE
    TW, TH = out_w * S, out_h * S
    canvas = _wall(c, TW, TH, rng)
    view = _VIEW.get(theme, "night_city")
    x0, y0, x1, y1 = _window_box(window_side, TW, TH)
    ww, wh = x1 - x0, y1 - y0
    sky_top, sky_bot = _sky(view, c)

    # Window light on the wall, then the view through the glass.
    _spill(canvas, (x0, y0, x1, y1), _mix(sky_bot, (255, 255, 255), 0.2), 0.28)
    # The view is drawn at output size and scaled up: its fine details (rain,
    # lit windows, stars) are sized in output pixels and would vanish otherwise.
    outside = _view_layer(view, c, ww // S, wh // S, rng).resize((ww, wh), Image.LANCZOS)
    if view in ("rain_city", "rain_forest"):
        outside = outside.filter(ImageFilter.GaussianBlur(1.0))
    canvas.paste(outside, (x0, y0))
    d = ImageDraw.Draw(canvas, "RGBA")
    d.polygon([(x0 + ww * 0.08, y1), (x0 + ww * 0.3, y0), (x0 + ww * 0.42, y0),
               (x0 + ww * 0.2, y1)], fill=(255, 255, 255, 14))
    if view in ("rain_city", "rain_forest"):            # droplets on the glass
        for _ in range(50):
            dx, dy, r = rng.uniform(x0, x1), rng.uniform(y0, y1), rng.uniform(2.5, 6)
            d.ellipse([dx - r, dy - r, dx + r, dy + r], fill=(230, 240, 255, 70))
    frame = tuple(max(0, int(v * 0.5)) for v in c["bg_bot"])
    fw = max(18, int(TW * 0.011))
    d.rectangle([x0 - fw, y0 - fw, x1 + fw, y1 + fw], outline=(*frame, 255), width=fw)
    d.line([((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1)], fill=(*frame, 255), width=fw - 4)
    d.line([(x0, y0 + wh * 0.45), (x1, y0 + wh * 0.45)], fill=(*frame, 255), width=fw - 4)
    sill_c = tuple(min(255, int(v * 1.6) + 20) for v in frame)
    d.rectangle([x0 - fw * 2, y1 + fw, x1 + fw * 2, y1 + fw * 2.4], fill=(*sill_c, 255))
    if view == "snow":
        d.rectangle([x0, y1 - 10, x1, y1], fill=(235, 242, 255, 230))
    if rng.random() < 0.6:
        _fairy_lights(d, x0 - fw, x1 + fw, y0 - fw * 0.4, wh * 0.08, 13, rng, S * 2.2)

    # Desk.
    desk_y = int(TH * 0.80)
    wood = _mix((86, 58, 40), c["bg_bot"], 0.28)
    d.rectangle([0, desk_y, TW, TH], fill=(*wood, 255))
    d.line([(0, desk_y), (TW, desk_y)], fill=(*_mix(wood, _WARM, 0.45), 255), width=6)

    # Lamp at the window's outer edge, glowing over the desk.
    s = TH * 0.20
    if window_side == "center":
        lamp_x, flip = int(TW * 0.14), False
    elif window_side == "left":
        lamp_x, flip = int(x0 + ww * 0.06), False
    else:
        lamp_x, flip = int(x1 - ww * 0.06), True
    _lamp(canvas, lamp_x, desk_y, s, flip)
    d = ImageDraw.Draw(canvas, "RGBA")

    # Two things on the desk, either side of the listener.
    fill, rim = (30, 22, 20, 245), (*_WARM, 200)
    cx = (x0 + x1) / 2
    size = TH * 0.20
    left, right = cx - ww * 0.36, cx + ww * 0.36
    prop_a = rng.choice(["mug", "books"])
    prop_b = rng.choice(["plant", "headphones"])
    for name, px in ((prop_a, left if not flip else right), (prop_b, right if not flip else left)):
        if name == "mug":
            _silhouette_coffee_cup(d, px, desk_y - size * 0.29, size, size, fill, rim, rng)
        elif name == "plant":
            _silhouette_plant(d, px, desk_y - size * 0.34, size * 1.1, size * 1.1, fill, rim, rng)
        elif name == "books":
            _books(d, px, desk_y, size, [_mix(c["accent"], (60, 40, 30), 0.45), (122, 70, 52), (70, 88, 110)])
        else:
            _headphones(d, px, desk_y, size * 0.8, fill, rim)

    # Sometimes a cat on the sill, on the side away from the lamp.
    if rng.random() < 0.4:
        cs = TH * 0.11
        catx = x0 + ww * (0.16 if flip else 0.84)
        _silhouette_cat(d, catx, y1 + fw - cs * 0.78, cs, cs, (16, 12, 14, 255), rim, rng)

    # The listener, back to us, facing the window.
    rimlight = (*_mix(sky_bot, (255, 255, 255), 0.35), 210)
    _listener(d, cx, desk_y, TH, rimlight, int(rng.integers(0, 3)))

    return canvas.resize((out_w, out_h), Image.LANCZOS)


def split_tone(img: Image.Image, c: dict, amount: float = 0.18) -> Image.Image:
    """Cool shadows, warm highlights: the warm-lamp/cool-window contrast that
    makes cozy interiors read (complementary orange/teal grading)."""
    arr = np.asarray(img, dtype=np.float32)
    luma = (arr @ np.array([0.299, 0.587, 0.114], np.float32))[..., None] / 255.0
    cool = np.array(_mix(c["bg_bot"], (40, 70, 120), 0.5), np.float32)
    warm = np.array(_WARM, np.float32)
    shadow = (1 - luma) ** 2
    high = luma ** 2
    graded = arr + amount * (shadow * (cool - arr) * 0.6 + high * (warm - arr) * 0.35)
    return Image.fromarray(np.clip(graded, 0, 255).astype(np.uint8))


def window_side_for(layout: str, text_side: str) -> str:
    if layout == "centered":
        return "center"
    return "right" if text_side == "left" else "left"

