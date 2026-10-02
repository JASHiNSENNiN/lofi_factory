"""
scene.py — Lo-fi Radio Interface: vinyl record, now-playing panel, header.
Replaces the old room-scene approach with an abstract radio station UI.
"""

import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import (
    W, H, HEADER_H, HEADER_MID,
    VINYL_CX, VINYL_CY, VINYL_R, VINYL_LABEL_R, VINYL_HOLE_R,
    DIVIDER_X, NP_X0, NP_Y0, NP_X1, NP_Y1,
    PROG_Y, PROG_X0, PROG_X1, PROG_H,
    CHANNEL_NAME,
)
from .themes import THEMES


# ── Font helpers ──────────────────────────────────────────────────────────────

_FONTS: dict = {}

def _font(size: int) -> ImageFont.FreeTypeFont:
    if size in _FONTS:
        return _FONTS[size]
    candidates = [
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                _FONTS[size] = ImageFont.truetype(p, size)
                return _FONTS[size]
            except Exception:
                pass
    _FONTS[size] = ImageFont.load_default()
    return _FONTS[size]


def _font_reg(size: int) -> ImageFont.FreeTypeFont:
    key = f"reg_{size}"
    if key in _FONTS:
        return _FONTS[key]
    candidates = [
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                _FONTS[key] = ImageFont.truetype(p, size)
                return _FONTS[key]
            except Exception:
                pass
    _FONTS[key] = ImageFont.load_default()
    return _FONTS[key]


def _text_w(d: ImageDraw.ImageDraw, text: str, font) -> int:
    bb = d.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


# ── Alpha paste helper ────────────────────────────────────────────────────────

def paste_img_rgba(frame: np.ndarray, img_rgba: np.ndarray, x: int, y: int) -> None:
    ih, iw = img_rgba.shape[:2]
    fy0 = max(0, y);  fy1 = min(H, y + ih)
    fx0 = max(0, x);  fx1 = min(W, x + iw)
    sy0 = fy0 - y;   sy1 = sy0 + (fy1 - fy0)
    sx0 = fx0 - x;   sx1 = sx0 + (fx1 - fx0)
    if fy1 <= fy0 or fx1 <= fx0:
        return
    src   = img_rgba[sy0:sy1, sx0:sx1]
    alpha = src[:, :, 3:4].astype(np.float32) / 255.0
    dst   = frame[fy0:fy1, fx0:fx1].astype(np.float32)
    frame[fy0:fy1, fx0:fx1] = np.clip(
        dst * (1 - alpha) + src[:, :, :3].astype(np.float32) * alpha,
        0, 255
    ).astype(np.uint8)


# ── Decorative perspective grid ───────────────────────────────────────────────

def make_grid_overlay(theme: str) -> np.ndarray:
    """Static RGBA perspective grid (bottom half of frame)."""
    c   = THEMES[theme]
    acc = c["accent"]
    pil = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d   = ImageDraw.Draw(pil)

    horizon_y = H - 280
    vp_x      = W // 2

    # Converging verticals
    for i in range(19):
        t_   = i / 18
        bot_x = int(t_ * W)
        alpha = int(14 + 10 * (1 - abs(t_ - 0.5) * 2))
        d.line([vp_x, horizon_y, bot_x, H], fill=(*acc, alpha), width=1)

    # Horizontal depth rings
    for j in range(1, 12):
        depth = j / 11.0
        y     = horizon_y + int((H - horizon_y) * depth ** 0.55)
        spread = int(W * 0.5 * depth ** 0.45)
        x0 = max(0, vp_x - spread); x1 = min(W, vp_x + spread)
        alpha = int(10 + 14 * depth)
        d.line([x0, y, x1, y], fill=(*acc, alpha), width=1)

    return np.array(pil)  # RGBA


# ── Vinyl record ──────────────────────────────────────────────────────────────

def make_vinyl_body(theme: str) -> np.ndarray:
    """Pre-rendered vinyl disk (body only — groove rings, sheen). RGBA numpy."""
    size = (VINYL_R + 10) * 2
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = size // 2

    # Outer record body
    draw.ellipse([cx - VINYL_R, cy - VINYL_R, cx + VINYL_R, cy + VINYL_R],
                 fill=(13, 13, 18, 255))

    # Groove rings
    for r in range(VINYL_LABEL_R + 10, VINYL_R - 4, 3):
        shade = 30 if (r // 3) % 2 == 0 else 20
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     outline=(shade, shade, shade + 8, 190), width=1)

    # Specular highlight arc (top-left quadrant, makes it look 3D)
    for i in range(8):
        ri  = VINYL_R - 3 - i * 3
        br  = max(0, 65 - i * 8)
        draw.arc([cx - ri, cy - ri, cx + ri, cy + ri],
                 start=195, end=255, fill=(br, br, br + 15, br), width=2)

    # Centre hole
    draw.ellipse([cx - VINYL_HOLE_R, cy - VINYL_HOLE_R,
                  cx + VINYL_HOLE_R, cy + VINYL_HOLE_R],
                 fill=(0, 0, 0, 255))

    return np.array(img)  # RGBA


def make_vinyl_label_frames(theme: str, n_steps: int = 96) -> list:
    """
    Pre-renders n_steps rotations of the vinyl label (small centre circle).
    At 33⅓ RPM × 24fps ≈ 8.33°/frame; n_steps=96 → step=3.75°.
    """
    c    = THEMES[theme]
    lc   = c["vinyl_label"]
    acc  = c["accent"]
    size = (VINYL_LABEL_R + 3) * 2
    cx   = cy = size // 2

    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d    = ImageDraw.Draw(base)

    # Label background
    d.ellipse([0, 0, size - 1, size - 1], fill=(*lc, 255))

    # Concentric accent rings
    for r, al in [(VINYL_LABEL_R - 8, 90), (VINYL_LABEL_R - 18, 60),
                  (VINYL_LABEL_R - 30, 38)]:
        if r > 4:
            d.ellipse([cx - r, cy - r, cx + r, cy + r],
                      outline=(*acc, al), width=1)

    # Text
    fnt_lg = _font(16); fnt_sm = _font_reg(11)
    d.text((cx, cy - 10), "LOFI",  fill=(*acc, 230), font=fnt_lg, anchor="mm")
    d.text((cx, cy +  8), "RADIO", fill=(*acc, 165), font=fnt_sm, anchor="mm")

    # 12-o'clock reference dot
    d.ellipse([cx - 3, cy - VINYL_LABEL_R + 6,
               cx + 3, cy - VINYL_LABEL_R + 12], fill=(*acc, 200))

    # Centre hole
    d.ellipse([cx - VINYL_HOLE_R, cy - VINYL_HOLE_R,
               cx + VINYL_HOLE_R, cy + VINYL_HOLE_R], fill=(0, 0, 0, 255))

    deg_step = 360.0 / n_steps
    frames   = []
    for i in range(n_steps):
        rot = base.rotate(-i * deg_step, resample=Image.BICUBIC, expand=False)
        frames.append(np.array(rot))
    return frames


_VINYL_FRAME_DEG = (33.333 / 60) * (360.0 / 24)   # ≈ 8.333°/video frame
_VINYL_STEP_DEG  = 360.0 / 96                       # 3.75° per label frame


def draw_vinyl(frame: np.ndarray, vinyl_body: np.ndarray,
               label_frames: list, f_idx: int, theme: str) -> None:
    c   = THEMES[theme]
    acc = c["accent"]

    # Background glow halo
    gr = VINYL_R + 50
    gy0 = max(0, VINYL_CY - gr); gy1 = min(H, VINYL_CY + gr)
    gx0 = max(0, VINYL_CX - gr); gx1 = min(W, VINYL_CX + gr)
    if gy1 > gy0 and gx1 > gx0:
        ys   = np.arange(gy0, gy1)[:, None].astype(np.float32) - VINYL_CY
        xs   = np.arange(gx0, gx1)[None, :].astype(np.float32) - VINYL_CX
        dist = np.sqrt(ys**2 + xs**2)
        glow = np.clip(1.0 - dist / gr, 0, 1) ** 3 * 0.10
        reg  = frame[gy0:gy1, gx0:gx1].astype(np.float32)
        for ch, av in enumerate(acc):
            reg[:, :, ch] = np.clip(reg[:, :, ch] + glow * av, 0, 255)
        frame[gy0:gy1, gx0:gx1] = reg.astype(np.uint8)

    # Paste body
    bs = vinyl_body.shape[0]
    paste_img_rgba(frame, vinyl_body, VINYL_CX - bs // 2, VINYL_CY - bs // 2)

    # Paste rotating label
    label_idx = int(f_idx * _VINYL_FRAME_DEG / _VINYL_STEP_DEG) % len(label_frames)
    la = label_frames[label_idx]
    ls = la.shape[0]
    paste_img_rgba(frame, la, VINYL_CX - ls // 2, VINYL_CY - ls // 2)


def draw_tone_arm(frame: np.ndarray, f_idx: int, fps: int) -> None:
    """Stylised tone arm: pivots from upper-right, rests over record groove."""
    t       = f_idx / fps
    sway    = 1.8 * math.sin(2 * math.pi * t / 9.0)
    pivot_x = VINYL_CX + VINYL_R + 52
    pivot_y = VINYL_CY - VINYL_R - 30
    arm_len = 205
    angle   = math.radians(215.0 + sway)
    tip_x   = int(pivot_x + arm_len * math.cos(angle))
    tip_y   = int(pivot_y + arm_len * math.sin(angle))

    pil  = Image.fromarray(frame).convert("RGBA")
    ov   = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d    = ImageDraw.Draw(ov)
    d.line([pivot_x + 2, pivot_y + 2, tip_x + 2, tip_y + 2],
           fill=(0, 0, 0, 100), width=3)
    d.line([pivot_x, pivot_y, tip_x, tip_y],
           fill=(150, 145, 138, 230), width=3)
    d.ellipse([pivot_x - 7, pivot_y - 7, pivot_x + 7, pivot_y + 7],
              fill=(120, 115, 108, 255))
    d.ellipse([tip_x - 3, tip_y - 3, tip_x + 3, tip_y + 3],
              fill=(210, 205, 195, 255))
    frame[:] = np.array(Image.alpha_composite(pil, ov).convert("RGB"))


# ── Now-Playing panel ─────────────────────────────────────────────────────────

def draw_now_playing(frame: np.ndarray, title: str, genre: str,
                     f_idx: int, n_frames: int, theme: str) -> None:
    c   = THEMES[theme]
    acc = c["accent"]
    pc  = c["panel_col"]  # (R, G, B, A)

    pil = Image.fromarray(frame).convert("RGBA")
    ov  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d   = ImageDraw.Draw(ov)

    pad = 24
    # Panel background
    d.rounded_rectangle(
        [NP_X0 - pad, NP_Y0 - pad, NP_X1 + pad, NP_Y1 + pad],
        radius=20, fill=pc
    )
    # Accent top line
    d.rectangle([NP_X0 - pad, NP_Y0 - pad,
                 NP_X1 + pad, NP_Y0 - pad + 3],
                fill=(*acc, 210))

    # "THIS SESSION" label (one baked-in title covers the whole video, so it
    # names the session, not a single track)
    fnt_s = _font_reg(22)
    d.text((NP_X0, NP_Y0 + 12), "THIS SESSION",
           fill=(*acc, 200), font=fnt_s)
    sep_x = NP_X0 + _text_w(d, "THIS SESSION", fnt_s) + 18
    d.line([sep_x, NP_Y0 + 22, NP_X1, NP_Y0 + 22],
           fill=(*acc, 55), width=1)

    # Track title — word-wrap across up to 2 lines using actual pixel width
    fnt_title  = _font(50)
    max_w      = NP_X1 - NP_X0          # available width in panel
    words      = title.split()
    line1, line2 = [], []
    for word in words:
        # Once a word spills to line 2, everything after it goes there too;
        # filling line 1 with later short words reordered the title.
        if not line2 and _text_w(d, " ".join(line1 + [word]), fnt_title) <= max_w:
            line1.append(word)
        else:
            line2.append(word)
    # If line2 is too wide, truncate with ellipsis
    if line2:
        while line2 and _text_w(d, " ".join(line2) + "…", fnt_title) > max_w:
            line2.pop()
        l2_text = (" ".join(line2) + "…") if line2 else ""
    else:
        l2_text = ""
    d.text((NP_X0, NP_Y0 + 48), " ".join(line1),
           fill=(238, 238, 248, 245), font=fnt_title)
    if l2_text:
        d.text((NP_X0, NP_Y0 + 104), l2_text,
               fill=(238, 238, 248, 200), font=_font(44))

    # Genre badge — sit below title (shifts down if two-line title)
    title_bottom = NP_Y0 + (160 if l2_text else 110)
    fnt_g = _font_reg(24)
    badge = f" {genre} "
    bw    = _text_w(d, badge, fnt_g) + 10
    by0   = title_bottom; by1 = by0 + 34
    d.rounded_rectangle([NP_X0, by0, NP_X0 + bw, by1],
                         radius=8, fill=(*acc, 50), outline=(*acc, 120), width=1)
    d.text((NP_X0 + 5, by0 + 5), badge, fill=(*acc, 220), font=fnt_g)

    # Mini waveform oscilloscope
    wx0, wx1 = NP_X0, NP_X1
    wy  = title_bottom + 90
    amp = 38
    phase_speed = 2 * math.pi * 2.5  # 2.5 cycles / second
    t   = f_idx / 24.0
    pts = []
    for ix in range(wx0, wx1, 3):
        pos   = (ix - wx0) / (wx1 - wx0)
        wave  = (math.sin(pos * 2 * math.pi * 5 + t * phase_speed)
                 * math.cos(pos * 2 * math.pi * 1.3 + t * 1.1))
        pts.append((ix, int(wy + amp * wave)))
    if len(pts) >= 2:
        d.line(pts, fill=(*acc, 85), width=2)

    # Progress bar track
    py = PROG_Y
    d.rounded_rectangle([PROG_X0, py, PROG_X1, py + PROG_H],
                         radius=3, fill=(70, 70, 90, 120))

    # Filled bar, playhead, and time text are overlaid by ffmpeg at assembly time
    # with accurate global timestamps — see assemble_video.apply_vhs_grade()

    frame[:] = np.array(Image.alpha_composite(pil, ov).convert("RGB"))


# ── Header bar ────────────────────────────────────────────────────────────────

def draw_header(frame: np.ndarray, t: float, theme: str,
                channel_name: str = CHANNEL_NAME) -> None:
    c   = THEMES[theme]
    acc = c["accent"]
    pc  = c["panel_col"]

    pil = Image.fromarray(frame).convert("RGBA")
    ov  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d   = ImageDraw.Draw(ov)

    # Header background
    d.rectangle([0, 0, W, HEADER_H], fill=(*pc[:3], 215))
    d.line([0, HEADER_H - 1, W, HEADER_H - 1], fill=(*acc, 90), width=1)

    # Pulsing accent dot. (This used to be a red "LIVE" badge, baked into the
    # loop used for every uploaded video too, which isn't live.)
    pulse_a = int(145 + 110 * math.sin(2 * math.pi * t / 1.2))
    dx, dy = 38, HEADER_MID
    d.ellipse([dx - 8, dy - 8, dx + 8, dy + 8], fill=(*acc, pulse_a))
    d.ellipse([dx - 13, dy - 13, dx + 13, dy + 13],
              outline=(*acc, pulse_a // 3), width=2)

    # "LO-FI RADIO"
    fnt_h = _font(28)
    d.text((dx + 22, dy), "LO-FI RADIO",
           fill=(232, 232, 242, 235), font=fnt_h, anchor="lm")

    # Channel name centre
    fnt_ch = _font_reg(24)
    d.text((W // 2, dy), channel_name,
           fill=(195, 195, 212, 180), font=fnt_ch, anchor="mm")
    # No clock: anything baked into a 60-second loop shows the render's wall
    # time, repeated every minute of the video.

    frame[:] = np.array(Image.alpha_composite(pil, ov).convert("RGB"))


# ── Divider line ──────────────────────────────────────────────────────────────

_DIVIDER_CACHE: dict = {}

def draw_divider(frame: np.ndarray, theme: str) -> None:
    """Static per-theme divider — cached after first render."""
    global _DIVIDER_CACHE
    if theme not in _DIVIDER_CACHE:
        c   = THEMES[theme]
        acc = c["accent"]
        ov  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d   = ImageDraw.Draw(ov)
        d.line([DIVIDER_X, HEADER_H + 15, DIVIDER_X, NP_Y1 + 28],
               fill=(*acc, 50), width=1)
        ov_arr = np.array(ov)
        _DIVIDER_CACHE[theme] = ov_arr

    ov_arr = _DIVIDER_CACHE[theme]
    alpha  = ov_arr[:, :, 3:4].astype(np.float32) / 255.0
    dst    = frame.astype(np.float32)
    frame[:] = np.clip(
        dst * (1 - alpha) + ov_arr[:, :, :3].astype(np.float32) * alpha,
        0, 255
    ).astype(np.uint8)
