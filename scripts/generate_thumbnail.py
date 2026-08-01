"""
generate_thumbnail.py
---------------------
Generates YouTube thumbnails for lo-fi videos.
Aesthetic: abstract, glitchy, neon — NOT the generic anime girl.
Uses only Pillow + numpy. No external AI needed.

Output: assets/thumb_THEME_VARIANT.jpg (1280x720)
"""

import os
import math
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

W, H = 1280, 720

THEME_STYLES = {
    "neon_rain": {
        "bg": (8, 0, 20),
        "grad_to": (0, 10, 35),
        "neon1": (0, 255, 180),
        "neon2": (180, 0, 255),
        "neon3": (255, 50, 100),
        "text_color": (255, 255, 255),
        "glow_color": (0, 255, 180),
    },
    "vhs_dream": {
        "bg": (20, 5, 40),
        "grad_to": (5, 20, 50),
        "neon1": (255, 100, 200),
        "neon2": (100, 200, 255),
        "neon3": (255, 220, 50),
        "text_color": (255, 240, 255),
        "glow_color": (255, 100, 200),
    },
    "void_bloom": {
        "bg": (0, 0, 5),
        "grad_to": (5, 0, 15),
        "neon1": (80, 0, 200),
        "neon2": (0, 200, 150),
        "neon3": (200, 0, 80),
        "text_color": (200, 200, 255),
        "glow_color": (80, 0, 200),
    },
    "retro_city": {
        "bg": (15, 5, 30),
        "grad_to": (30, 10, 50),
        "neon1": (255, 80, 0),
        "neon2": (255, 200, 0),
        "neon3": (0, 150, 255),
        "text_color": (255, 240, 200),
        "glow_color": (255, 120, 0),
    },
}

TITLE_TEMPLATES = [
    "lofi to {mood} to",
    "{mood} lofi beats",
    "beats for {time}",
    "{adj} frequencies",
    "lofi • {mood} • {time}",
    "{time} frequencies",
    "{mood} static",
    "signal from {place}",
    "late {time} transmission",
    "{adj} lofi dreams",
]

MOODS = ["study", "drift", "fade", "exist", "disappear", "breathe", "forget", "float", "stay", "wander"]
TIMES = ["3am", "2am", "late night", "midnight", "early morning", "dusk", "the void"]
ADJS = ["analog", "broken", "distant", "blurred", "static", "warm", "cold", "hollow", "soft", "faded"]
PLACES = ["nowhere", "somewhere", "the past", "static", "a dream", "the archive", "signal decay"]

DURATIONS = ["1 hour", "2 hours", "3 hours", "all night"]


def get_random_title():
    template = random.choice(TITLE_TEMPLATES)
    title = template.format(
        mood=random.choice(MOODS),
        time=random.choice(TIMES),
        adj=random.choice(ADJS),
        place=random.choice(PLACES),
    )
    return title.upper()


def draw_gradient(arr, bg, grad_to):
    for y in range(H):
        t = y / H
        r = int(bg[0] + (grad_to[0] - bg[0]) * t)
        g = int(bg[1] + (grad_to[1] - bg[1]) * t)
        b = int(bg[2] + (grad_to[2] - bg[2]) * t)
        arr[y, :] = [r, g, b]


def draw_orbs(arr, style):
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    colors = [style["neon1"], style["neon2"], style["neon3"]]
    for _ in range(5):
        cx = random.randint(0, W)
        cy = random.randint(0, H)
        r = random.randint(80, 300)
        color = random.choice(colors)
        for ring in range(r, 0, -8):
            alpha = int(80 * (ring / r) ** 2.5)
            d.ellipse([cx-ring, cy-ring, cx+ring, cy+ring], fill=(*color, alpha))
    base = Image.fromarray(arr).convert("RGBA")
    return np.array(Image.alpha_composite(base, overlay).convert("RGB"))


def draw_grid(arr, style):
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    horizon = int(H * 0.65)
    vp = W // 2
    color = style["neon3"]
    for i in range(-10, 11):
        x_bottom = vp + i * 100
        d.line([(vp, horizon), (x_bottom, H)], fill=(*color, 60), width=1)
    for j in range(0, H - horizon, 35):
        y = horizon + j
        ratio = j / (H - horizon)
        c = tuple(int(x * ratio * 0.5) for x in color)
        d.line([(0, y), (W, y)], fill=c, width=1)
    return np.array(img)


def draw_scanlines(arr):
    for y in range(0, H, 4):
        arr[y] = np.clip(arr[y].astype(int) - 25, 0, 255)
    return arr


def add_rgb_split(img, amount=4):
    """Chromatic aberration / RGB split effect"""
    r, g, b = img.split()
    r = np.roll(np.array(r), amount, axis=1)
    b = np.roll(np.array(b), -amount, axis=1)
    return Image.merge("RGB", [Image.fromarray(r), g, Image.fromarray(b)])


def add_noise(arr, intensity=8):
    noise = np.random.randint(-intensity, intensity, arr.shape, dtype=np.int16)
    return np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def draw_glitch_bars(arr, style):
    """Random horizontal glitch bars"""
    for _ in range(random.randint(2, 6)):
        y = random.randint(0, H - 20)
        h = random.randint(2, 10)
        shift = random.randint(5, 25) * random.choice([-1, 1])
        arr[y:y+h] = np.roll(arr[y:y+h], shift, axis=1)
    return arr


def draw_text_layered(img, title, duration, style):
    """Draw main title with glow + duration badge"""
    d = ImageDraw.Draw(img)

    # Try to load a font, fallback to default
    font_large = ImageFont.load_default()
    font_small = ImageFont.load_default()

    glow = style["glow_color"]
    txt_color = style["text_color"]

    # Duration badge (top right)
    badge_text = duration
    badge_x, badge_y = W - 220, 30
    d.rectangle([badge_x - 10, badge_y - 5, badge_x + 190, badge_y + 35], fill=(*glow, 180))
    d.text((badge_x, badge_y), badge_text, fill=(0, 0, 0))

    # Main title — centered, with glow effect (draw multiple times offset)
    lines = title.split("•") if "•" in title else [title]
    y_start = H // 2 - 60
    for line in lines:
        line = line.strip()
        # Glow pass
        for dx, dy in [(-2,0),(2,0),(0,-2),(0,2),(-2,-2),(2,2)]:
            d.text((W//2 + dx - 200, y_start + dy), line, fill=(*glow, 100))
        # Main text
        d.text((W//2 - 200, y_start), line, fill=txt_color)
        y_start += 50

    # Subtle "lofi" watermark bottom left
    d.text((20, H - 40), "◈ lofi frequencies", fill=(*glow,))

    return img


def generate_thumbnail(theme_name=None, duration=None, variant=0):
    if theme_name is None:
        theme_name = random.choice(list(THEME_STYLES.keys()))
    if duration is None:
        duration = random.choice(DURATIONS)

    style = THEME_STYLES[theme_name]
    title = get_random_title()

    print(f"[THUMB] Theme: {theme_name} | Title: {title} | Duration: {duration}")

    arr = np.zeros((H, W, 3), dtype=np.uint8)
    draw_gradient(arr, style["bg"], style["grad_to"])
    arr = draw_orbs(arr, style)

    if theme_name == "retro_city":
        arr = draw_grid(arr, style)

    arr = add_noise(arr)
    arr = draw_glitch_bars(arr, style)
    arr = draw_scanlines(arr)

    img = Image.fromarray(arr)
    img = add_rgb_split(img, amount=3)

    # Slight bloom via blur overlay
    blurred = img.filter(ImageFilter.GaussianBlur(radius=8))
    img = Image.blend(img, blurred, alpha=0.15)

    img = draw_text_layered(img, title, duration, style)

    out_name = f"thumb_{theme_name}_{variant:02d}.jpg"
    out_path = os.path.join(ASSETS_DIR, out_name)
    img.save(out_path, quality=95)
    print(f"  Saved: {out_path}")
    return out_path, title


if __name__ == "__main__":
    import sys
    theme = sys.argv[1] if len(sys.argv) > 1 else None
    for i in range(4):
        generate_thumbnail(theme, variant=i)
