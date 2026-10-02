"""
thumbnail_scene.py — the illustrated room behind a thumbnail's title.

A cozy room at the theme's time of day: a big window whose view matches the
theme (rain, snow, a lit city, a moon, a sunset, blossom), a desk lit by a
warm lamp, and a few things on it (mug, plant, books, headphones, records).
It replaces a single small silhouette on a dark gradient, which read as
empty at thumbnail size. Everything is drawn with PIL; no image assets.
"""
from __future__ import annotations

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


def draw_room(img: Image.Image, c: dict, theme: str, window_side: str,
              rng: np.random.Generator) -> Image.Image:
    """Paint the room into `img` (the wall gradient). `window_side` is where the
    window goes: opposite the title, or "center" behind a centered title."""
    from scripts.generate_thumbnail_cozy import (
        _silhouette_cat, _silhouette_coffee_cup, _silhouette_plant,
    )
    TW, TH = img.size
    view = _VIEW.get(theme, "night_city")
    x0, y0, x1, y1 = _window_box(window_side, TW, TH)
    ww, wh = x1 - x0, y1 - y0

    # The view, then the glass's faint reflection, then the frame and sill.
    outside = _view_layer(view, c, ww, wh, rng)
    if view in ("rain_city", "rain_forest"):
        outside = outside.filter(ImageFilter.GaussianBlur(0.6))
    img.paste(outside, (x0, y0))
    d = ImageDraw.Draw(img, "RGBA")
    d.polygon([(x0 + ww * 0.08, y1), (x0 + ww * 0.3, y0), (x0 + ww * 0.42, y0),
               (x0 + ww * 0.2, y1)], fill=(255, 255, 255, 12))
    if view in ("rain_city", "rain_forest"):            # droplets on the glass
        for _ in range(40):
            dx, dy, r = rng.uniform(x0, x1), rng.uniform(y0, y1), rng.uniform(1.5, 3.5)
            d.ellipse([dx - r, dy - r, dx + r, dy + r], fill=(230, 240, 255, 70))
    frame = tuple(max(0, int(v * 0.55)) for v in c["bg_bot"])
    fw = max(10, int(TW * 0.011))
    d.rectangle([x0 - fw, y0 - fw, x1 + fw, y1 + fw], outline=(*frame, 255), width=fw)
    d.line([((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1)], fill=(*frame, 255), width=fw - 2)
    d.line([(x0, y0 + wh * 0.45), (x1, y0 + wh * 0.45)], fill=(*frame, 255), width=fw - 2)
    sill_c = tuple(min(255, int(v * 1.6) + 20) for v in frame)
    d.rectangle([x0 - fw * 2, y1 + fw, x1 + fw * 2, y1 + fw * 2.4], fill=(*sill_c, 255))
    if view == "snow":
        d.rectangle([x0, y1 - 6, x1, y1], fill=(235, 242, 255, 230))

    # Desk.
    desk_y = int(TH * 0.80)
    wood = _mix((78, 52, 36), c["bg_bot"], 0.3)
    d.rectangle([0, desk_y, TW, TH], fill=(*wood, 255))
    d.line([(0, desk_y), (TW, desk_y)], fill=(*_mix(wood, _WARM, 0.35), 255), width=3)

    # Lamp at the window's outer edge, glowing over the desk.
    s = TH * 0.20
    if window_side == "center":
        lamp_x, flip = int(TW * 0.12), False
    elif window_side == "left":
        lamp_x, flip = int(x0 + ww * 0.08), False
    else:
        lamp_x, flip = int(x1 - ww * 0.08), True
    _lamp(img, lamp_x, desk_y, s, flip)
    d = ImageDraw.Draw(img, "RGBA")

    # Things on the desk under the window, lit from the lamp side.
    fill = (30, 22, 20, 245)
    rim = (*_WARM, 190)
    palette = [_mix(c["accent"], (60, 40, 30), 0.45), (122, 70, 52), (70, 88, 110)]
    objs = ["mug", "plant", "books", "headphones"]
    rng.shuffle(objs)
    span = (x0 + ww * 0.22, x1 - ww * 0.22) if window_side != "center" else (TW * 0.3, TW * 0.7)
    for i, name in enumerate(objs[:3]):
        cx = span[0] + (span[1] - span[0]) * (i + 0.5) / 3
        size = TH * 0.22
        if name == "mug":
            _silhouette_coffee_cup(d, cx, desk_y - size * 0.29, size, size, fill, rim, rng)
        elif name == "plant":
            _silhouette_plant(d, cx, desk_y - size * 0.34, size * 1.1, size * 1.1, fill, rim, rng)
        elif name == "books":
            _books(d, cx, desk_y, size, palette)
        else:
            _headphones(d, cx, desk_y, size * 0.8, fill, rim)

    # Sometimes a cat on the sill.
    if rng.random() < 0.45:
        cs = TH * 0.13
        catx = x0 + ww * (0.18 if window_side != "left" else 0.82)
        _silhouette_cat(d, catx, y1 + fw - cs * 0.78, cs, cs, (18, 14, 16, 255), rim, rng)
    return img


def window_side_for(layout: str, text_side: str) -> str:
    if layout == "centered":
        return "center"
    return "right" if text_side == "left" else "left"

