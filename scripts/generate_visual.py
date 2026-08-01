"""
generate_visual.py
------------------
Generates an abstract animated lo-fi background video using only ffmpeg + Pillow.
Aesthetic: VHS glitch, neon rain, morphing color gradients, scanlines.
No GPU needed. Output: visuals/bg_THEME.mp4 (loopable, 30s base loop)
"""

import subprocess
import os
import random
import math
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import numpy as np

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "visuals")
os.makedirs(OUTPUT_DIR, exist_ok=True)

THEMES = {
    "neon_rain": {
        "bg_colors": [(10, 0, 30), (0, 10, 40)],
        "accent": [(0, 255, 180), (180, 0, 255), (255, 50, 100)],
        "desc": "Neon rain on dark city glass",
    },
    "vhs_dream": {
        "bg_colors": [(20, 5, 40), (5, 20, 50)],
        "accent": [(255, 100, 200), (100, 200, 255), (255, 220, 50)],
        "desc": "VHS glitch tape dreamy haze",
    },
    "void_bloom": {
        "bg_colors": [(0, 0, 0), (5, 0, 15)],
        "accent": [(80, 0, 200), (0, 200, 150), (200, 0, 80)],
        "desc": "Flowers blooming from void darkness",
    },
    "retro_city": {
        "bg_colors": [(15, 5, 30), (30, 10, 50)],
        "accent": [(255, 80, 0), (255, 200, 0), (0, 150, 255)],
        "desc": "Retro synthwave city horizon",
    },
}

W, H = 1920, 1080
FPS = 24
LOOP_SECS = 30  # base loop length; ffmpeg will extend to full duration


def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def add_scanlines(img, intensity=30):
    arr = np.array(img, dtype=np.int16)
    for y in range(0, H, 3):
        arr[y] = np.clip(arr[y] - intensity, 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


def add_vhs_glitch(img, frame_idx):
    """Horizontal RGB shift glitch effect"""
    arr = np.array(img)
    if random.random() < 0.15:  # 15% chance per frame
        shift = random.randint(3, 12)
        band_y = random.randint(0, H - 40)
        band_h = random.randint(5, 40)
        arr[band_y:band_y+band_h, :, 0] = np.roll(arr[band_y:band_y+band_h, :, 0], shift, axis=1)
        arr[band_y:band_y+band_h, :, 2] = np.roll(arr[band_y:band_y+band_h, :, 2], -shift, axis=1)
    return Image.fromarray(arr)


def draw_gradient_bg(draw, t, colors):
    """Slowly morphing gradient background"""
    c1 = lerp_color(colors[0], colors[1], (math.sin(t * 0.3) + 1) / 2)
    for y in range(H):
        ratio = y / H
        r = int(c1[0] * (1 - ratio * 0.5))
        g = int(c1[1] * (1 - ratio * 0.3))
        b = int(c1[2] + (20 * ratio))
        draw.line([(0, y), (W, y)], fill=(min(r,255), min(g,255), min(b,255)))


def draw_neon_rain(draw, t, accent_colors, drops):
    """Animated neon rain drops"""
    for drop in drops:
        drop["y"] = (drop["y"] + drop["speed"]) % (H + 50)
        color = accent_colors[drop["color_idx"]]
        alpha_fade = max(0, 255 - drop["len"] * 3)
        for i in range(drop["len"]):
            y = int(drop["y"]) - i * 4
            if 0 <= y < H:
                fade = int(255 * (1 - i / drop["len"]))
                c = tuple(int(x * fade / 255) for x in color)
                draw.line([(drop["x"], y), (drop["x"], y + 3)], fill=c, width=1)


def draw_floating_orbs(img_arr, t, accent_colors):
    """Soft glowing orbs drifting slowly"""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for orb in ORBS:
        ox = int(W/2 + math.sin(t * orb["freq_x"] + orb["phase"]) * orb["amp_x"])
        oy = int(H/2 + math.cos(t * orb["freq_y"] + orb["phase"]) * orb["amp_y"])
        color = accent_colors[orb["color_idx"]]
        r = orb["radius"]
        for ring in range(r, 0, -4):
            alpha = int(60 * (ring / r) ** 2)
            d.ellipse([ox-ring, oy-ring, ox+ring, oy+ring], fill=(*color, alpha))
    base = Image.fromarray(img_arr).convert("RGBA")
    return np.array(Image.alpha_composite(base, overlay).convert("RGB"))


def draw_grid_lines(draw, t, accent):
    """Perspective grid like synthwave horizon"""
    horizon_y = int(H * 0.62)
    vp_x = W // 2
    color = (*accent[0], 60)
    # Vertical lines converging to vanishing point
    for i in range(-12, 13):
        x_bottom = vp_x + i * 120
        draw.line([(vp_x, horizon_y), (x_bottom, H)], fill=accent[0], width=1)
    # Horizontal lines with scroll animation
    scroll = (t * 40) % 60
    for j in range(0, H - horizon_y, 30):
        y = horizon_y + j + scroll
        if y > H:
            break
        # Perspective fade: further lines are thinner and dimmer
        ratio = (y - horizon_y) / (H - horizon_y)
        c = tuple(int(x * ratio * 0.6) for x in accent[0])
        draw.line([(0, int(y)), (W, int(y))], fill=c, width=1)


def draw_text_glitch(draw, t, theme_name):
    """Occasional glitchy text flicker"""
    if random.random() < 0.03:
        texts = ["lo-fi", "✦ chill ✦", "study", "relax", "dream", theme_name.replace("_", " ")]
        txt = random.choice(texts)
        x = random.randint(50, W - 200)
        y = random.randint(50, H - 100)
        color = (255, 255, 255, 120)
        try:
            draw.text((x, y), txt, fill=(200, 200, 255))
        except Exception:
            pass


def generate_frames(theme_name, theme, num_frames):
    frames_dir = os.path.join(OUTPUT_DIR, f"frames_{theme_name}")
    os.makedirs(frames_dir, exist_ok=True)

    accent = theme["accent"]
    bg_colors = theme["bg_colors"]

    # Init rain drops
    rain_drops = [
        {
            "x": random.randint(0, W),
            "y": random.randint(0, H),
            "speed": random.uniform(4, 14),
            "len": random.randint(5, 20),
            "color_idx": random.randint(0, len(accent) - 1),
        }
        for _ in range(120)
    ]

    global ORBS
    ORBS = [
        {
            "amp_x": random.randint(100, 400),
            "amp_y": random.randint(80, 300),
            "freq_x": random.uniform(0.05, 0.2),
            "freq_y": random.uniform(0.05, 0.2),
            "phase": random.uniform(0, math.pi * 2),
            "radius": random.randint(60, 180),
            "color_idx": random.randint(0, len(accent) - 1),
        }
        for _ in range(6)
    ]

    print(f"  Rendering {num_frames} frames for theme '{theme_name}'...")
    for i in range(num_frames):
        t = i / FPS
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        draw_gradient_bg(draw, t, bg_colors)

        if theme_name in ("retro_city", "vhs_dream"):
            draw_grid_lines(draw, t, accent)

        arr = draw_floating_orbs(np.array(img), t, accent)
        img = Image.fromarray(arr)
        draw = ImageDraw.Draw(img)

        draw_neon_rain(draw, t, accent, rain_drops)
        draw_text_glitch(draw, t, theme_name)

        img = add_scanlines(img)
        img = add_vhs_glitch(img, i)

        # Slight blur for that dreamy soft focus
        img = img.filter(ImageFilter.GaussianBlur(radius=0.6))

        img.save(os.path.join(frames_dir, f"frame_{i:05d}.png"))

        if i % 24 == 0:
            print(f"    Frame {i}/{num_frames}")

    return frames_dir


def frames_to_video(frames_dir, theme_name, duration_secs):
    out_path = os.path.join(OUTPUT_DIR, f"bg_{theme_name}.mp4")
    loop_frames = FPS * LOOP_SECS
    total_frames = FPS * duration_secs

    # First: make the base loop
    loop_video = os.path.join(OUTPUT_DIR, f"loop_{theme_name}.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", os.path.join(frames_dir, "frame_%05d.png"),
        "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p",
        "-vf", "scale=1920:1080",
        loop_video
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    # Then loop it to full duration
    cmd2 = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", loop_video,
        "-t", str(duration_secs),
        "-c", "copy",
        out_path
    ]
    subprocess.run(cmd2, check=True, capture_output=True)

    # Cleanup frames and temp loop
    import shutil
    shutil.rmtree(frames_dir)
    os.remove(loop_video)

    print(f"  Visual saved: {out_path}")
    return out_path


def generate_visual(theme_name=None, duration_secs=7200):
    """Main entry point. theme_name=None picks random."""
    if theme_name is None:
        theme_name = random.choice(list(THEMES.keys()))
    theme = THEMES[theme_name]
    print(f"[VISUAL] Generating theme: {theme_name} — {theme['desc']}")

    num_frames = FPS * LOOP_SECS
    frames_dir = generate_frames(theme_name, theme, num_frames)
    out_path = frames_to_video(frames_dir, theme_name, duration_secs)
    return out_path, theme_name


if __name__ == "__main__":
    import sys
    theme = sys.argv[1] if len(sys.argv) > 1 else None
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 7200
    path, name = generate_visual(theme, duration)
    print(f"Done: {path}")
