"""
generate_thumbnail_cozy.py
--------------------------
YouTube thumbnail generator — atmospheric programmatic backgrounds.
NO AI image generation: 100% fast, consistent, cozy aesthetic.

Design: warm night-sky gradient + dual glow orbs + stars + bokeh
        + frosted glass text card. Theme-specific atmospheric FX.

Output: assets/thumb_{theme}_{timestamp}.jpg  (1280×720, JPEG q95)
"""

import os
import re
import sys
import datetime

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

# ── Paths ──────────────────────────────────────────────────────────────────────
_ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(_ROOT, "assets")
FONTS_DIR  = os.path.join(ASSETS_DIR, "fonts")
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(FONTS_DIR,  exist_ok=True)

TW, TH = 1280, 720

# ── Theme palettes ─────────────────────────────────────────────────────────────
THEMES = {
    "cozy_rain": {
        "bg_top": (10, 12, 30), "bg_bot": (22, 18, 48),
        "accent": (255, 195, 85), "text_main": (240, 230, 210),
        "badge_bg": (255, 195, 85), "badge_text": (15, 12, 30),
        "grad_overlay": (10, 8, 25, 200),
    },
    "midnight_cafe": {
        "bg_top": (5, 8, 22), "bg_bot": (18, 14, 36),
        "accent": (70, 248, 220), "text_main": (245, 235, 215),
        "badge_bg": (70, 248, 220), "badge_text": (5, 8, 22),
        "grad_overlay": (8, 6, 20, 200),
    },
    "purple_dusk": {
        "bg_top": (18, 10, 40), "bg_bot": (36, 18, 62),
        "accent": (210, 95, 255), "text_main": (238, 230, 248),
        "badge_bg": (210, 95, 255), "badge_text": (18, 10, 40),
        "grad_overlay": (15, 8, 35, 200),
    },
    "amber_night": {
        "bg_top": (14, 10, 24), "bg_bot": (28, 18, 40),
        "accent": (255, 185, 65), "text_main": (242, 232, 212),
        "badge_bg": (255, 185, 65), "badge_text": (14, 10, 24),
        "grad_overlay": (12, 8, 20, 200),
    },
    "winter_snow": {
        "bg_top": (12, 18, 45), "bg_bot": (5, 8, 30),
        "accent": (185, 228, 255), "text_main": (228, 238, 255),
        "badge_bg": (185, 228, 255), "badge_text": (5, 8, 30),
        "grad_overlay": (5, 8, 25, 200),
    },
    "autumn_study": {
        "bg_top": (38, 18, 8), "bg_bot": (20, 8, 4),
        "accent": (255, 165, 50), "text_main": (245, 228, 198),
        "badge_bg": (255, 165, 50), "badge_text": (38, 18, 8),
        "grad_overlay": (28, 12, 5, 200),
    },
    "spring_dawn": {
        "bg_top": (32, 15, 42), "bg_bot": (15, 6, 25),
        "accent": (255, 168, 210), "text_main": (248, 235, 248),
        "badge_bg": (255, 168, 210), "badge_text": (22, 8, 28),
        "grad_overlay": (18, 8, 22, 200),
    },
    "neon_tokyo": {
        "bg_top": (10, 6, 25), "bg_bot": (4, 2, 14),
        "accent": (255, 55, 210), "text_main": (252, 215, 252),
        "badge_bg": (255, 55, 210), "badge_text": (6, 3, 16),
        "grad_overlay": (5, 2, 15, 200),
    },
    "summer_lofi": {
        "bg_top": (12, 25, 12), "bg_bot": (5, 12, 5),
        "accent": (95, 248, 165), "text_main": (218, 248, 225),
        "badge_bg": (95, 248, 165), "badge_text": (5, 12, 5),
        "grad_overlay": (5, 10, 5, 200),
    },
    "blue_hour": {
        "bg_top": (8, 14, 45), "bg_bot": (2, 6, 28),
        "accent": (70, 160, 255), "text_main": (215, 232, 255),
        "badge_bg": (70, 160, 255), "badge_text": (4, 8, 28),
        "grad_overlay": (3, 6, 20, 200),
    },
    "forest_rain": {
        "bg_top": (6, 18, 8), "bg_bot": (2, 8, 4),
        "accent": (68, 232, 152), "text_main": (205, 242, 218),
        "badge_bg": (68, 232, 152), "badge_text": (4, 12, 5),
        "grad_overlay": (3, 10, 4, 200),
    },
    "sakura_night": {
        "bg_top": (22, 8, 32), "bg_bot": (10, 3, 18),
        "accent": (255, 168, 228), "text_main": (252, 228, 248),
        "badge_bg": (255, 168, 228), "badge_text": (15, 5, 20),
        "grad_overlay": (12, 4, 16, 200),
    },
    # New subgenre themes
    "vaporwave": {
        "bg_top": (28, 5, 45), "bg_bot": (12, 2, 28),
        "accent": (255, 60, 220), "text_main": (255, 200, 255),
        "badge_bg": (255, 60, 220), "badge_text": (18, 3, 30),
        "grad_overlay": (22, 4, 38, 200),
    },
    "lofi_house": {
        "bg_top": (10, 14, 32), "bg_bot": (4, 6, 20),
        "accent": (50, 190, 255), "text_main": (215, 238, 255),
        "badge_bg": (50, 190, 255), "badge_text": (4, 8, 22),
        "grad_overlay": (6, 10, 24, 200),
    },
    "lofi_classical": {
        "bg_top": (8, 10, 32), "bg_bot": (3, 4, 18),
        "accent": (228, 195, 90), "text_main": (245, 235, 205),
        "badge_bg": (228, 195, 90), "badge_text": (6, 8, 28),
        "grad_overlay": (5, 6, 22, 200),
    },
    "bedroom_pop": {
        "bg_top": (30, 14, 38), "bg_bot": (15, 6, 22),
        "accent": (255, 188, 148), "text_main": (252, 235, 225),
        "badge_bg": (255, 188, 148), "badge_text": (22, 8, 14),
        "grad_overlay": (22, 10, 30, 200),
    },
    "lofi_rnb": {
        "bg_top": (30, 10, 15), "bg_bot": (14, 4, 6),
        "accent": (255, 172, 70), "text_main": (252, 228, 195),
        "badge_bg": (255, 172, 70), "badge_text": (20, 6, 4),
        "grad_overlay": (22, 6, 10, 200),
    },
}

TITLE_TEMPLATES = {
    "cozy_rain":     ["rainy study night", "cozy lo-fi rain", "late night vibes", "study with rain", "coffee & rain"],
    "midnight_cafe": ["midnight café", "late night focus", "café at midnight", "coffee & lo-fi", "night owl beats"],
    "purple_dusk":   ["purple dusk vibes", "dusk lo-fi", "twilight study", "evening calm", "neon dusk beats"],
    "amber_night":   ["amber night", "warm study beats", "golden hour lo-fi", "amber glow mix", "lantern lo-fi"],
    "winter_snow":   ["winter study session", "snowfall lo-fi", "cold night beats", "winter focus mix", "frosted window lo-fi"],
    "autumn_study":  ["autumn study night", "falling leaves lo-fi", "october lo-fi", "harvest moon beats", "cozy autumn mix"],
    "spring_dawn":   ["spring dawn lo-fi", "blossom beats", "morning calm mix", "spring study vibes", "pink dawn lo-fi"],
    "neon_tokyo":    ["tokyo night lo-fi", "neon city beats", "cyberpunk study mix", "midnight tokyo", "neon rain lo-fi"],
    "summer_lofi":   ["summer nights lo-fi", "open window beats", "july study mix", "summer focus lo-fi", "warm breeze lo-fi"],
    "blue_hour":     ["blue hour lo-fi", "twilight study mix", "evening calm beats", "dusk lo-fi session", "indigo night mix"],
    "forest_rain":   ["forest rain lo-fi", "deep woods study", "green night beats", "rain on leaves mix", "forest focus lo-fi"],
    "sakura_night":  ["sakura night lo-fi", "cherry blossom beats", "hanami study mix", "pink moon lo-fi", "late night sakura"],
    # New subgenre themes
    "vaporwave":      ["vaporwave study session", "retrowave lo-fi", "80s nostalgia beats", "aesthetic lofi mix", "slow down & drift"],
    "lofi_house":     ["lofi house session", "deep house study beats", "late night 4/4 groove", "city groove lo-fi", "steady house vibes"],
    "lofi_classical": ["piano study session", "classical lo-fi beats", "baroque study mix", "refined focus music", "piano & cello lo-fi"],
    "bedroom_pop":    ["bedroom pop lo-fi", "indie study beats", "diy bedroom session", "guitar & soft drums", "homespun lo-fi mix"],
    "lofi_rnb":       ["lofi r&b session", "soul study beats", "neo-soul lo-fi", "soulful night mix", "warm rnb study vibes"],
}


# ── Title-card text derivation ────────────────────────────────────────────────

_EMOJI_RE   = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]+"
)
_TRAILING_DURATION_RE = re.compile(r"\s*(?:—\s*.*|\([^()]*\))\s*$")
_SHORT_TITLE_MAX_CHARS = 28


def _derive_short_title(full_title: str) -> str | None:
    """
    Derive a short, thumbnail-card-sized phrase from the actual generated SEO
    title (e.g. "lofi hip hop · it's midnight and you're still awake — 2
    hours" -> "it's midnight and you're still awake"), so the thumbnail and
    the video title agree on what the video is about instead of the
    thumbnail drawing an unrelated phrase from a small static per-theme pool.
    Returns None if the derived phrase isn't usable (too short/long after
    trimming), so the caller can fall back to the theme's template pool.
    """
    if not full_title:
        return None
    text = _EMOJI_RE.sub("", full_title).strip()
    # Drop the leading "lofi hip hop · " / "study music · " / "lofi · " tag.
    if " · " in text:
        text = text.split(" · ", 1)[1]
    # Drop a trailing " — <duration>" or "(<duration>)" clause.
    text = _TRAILING_DURATION_RE.sub("", text).strip(" -—·")
    if len(text) > _SHORT_TITLE_MAX_CHARS:
        # Trim to the last full word that fits, rather than rejecting
        # outright -- most generated clauses run a little over budget, and a
        # clean word-boundary cut still reads better than falling back to an
        # unrelated static template phrase.
        words, trimmed = text.split(), ""
        for word in words:
            candidate = f"{trimmed} {word}".strip()
            if len(candidate) > _SHORT_TITLE_MAX_CHARS:
                break
            trimmed = candidate
        text = trimmed
        if text.count("(") > text.count(")"):
            # Truncation landed inside an unclosed parenthetical -- cut
            # before it rather than leaving a dangling "(" on the card.
            text = text.rsplit("(", 1)[0].strip()
    if len(text) < 4:
        return None
    return text.lower()


# ── Font management ────────────────────────────────────────────────────────────

_BEBAS_PATH = os.path.join(FONTS_DIR, "BebasNeue-Regular.ttf")
_BEBAS_URL  = (
    "https://github.com/dharmatype/Bebas-Neue/raw/master/"
    "fonts/BebasNeue(2018)_by_Ryoichi_Tsunekawa/BebasNeue-Regular.ttf"
)
_TITLE_FONT_PATH: str | None = None


def _ensure_bebas() -> str | None:
    if os.path.exists(_BEBAS_PATH):
        return _BEBAS_PATH
    try:
        import requests
        resp = requests.get(_BEBAS_URL, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 10_000:
            with open(_BEBAS_PATH, "wb") as f:
                f.write(resp.content)
            print(f"  [THUMB] Downloaded BebasNeue → {_BEBAS_PATH}")
            return _BEBAS_PATH
    except Exception as e:
        print(f"  [THUMB] Font download skipped: {e}")
    return None


def _resolve_title_font() -> str:
    global _TITLE_FONT_PATH
    if _TITLE_FONT_PATH and os.path.exists(_TITLE_FONT_PATH):
        return _TITLE_FONT_PATH
    candidates = [
        _ensure_bebas(),
        "/usr/share/fonts/TTF/FiraSansCompressed-Heavy.ttf",
        "/usr/share/fonts/TTF/FiraSansCompressed-ExtraBold.ttf",
        "/usr/share/fonts/TTF/FiraSansCondensed-Heavy.ttf",
        "/usr/share/fonts/TTF/OpenSans-CondensedExtraBold.ttf",
        "/usr/share/fonts/TTF/DejaVuSansCondensed-Bold.ttf",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            _TITLE_FONT_PATH = p
            return p
    return ""


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    if path and os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


# ── Background builder ─────────────────────────────────────────────────────────

def _build_bg(theme: str, seed: int) -> Image.Image:
    """Atmospheric programmatic background: gradient + dual glow + stars + bokeh."""
    rng = np.random.default_rng(seed)
    c   = THEMES[theme]

    # 1. Smooth gradient (smoothstep curve for more interesting sky feel)
    top = np.array(c["bg_top"], dtype=np.float32)
    bot = np.array(c["bg_bot"], dtype=np.float32)
    arr = np.zeros((TH, TW, 3), dtype=np.float32)
    for y in range(TH):
        t = y / TH
        t_s = t * t * (3 - 2 * t)   # smoothstep
        arr[y] = top * (1 - t_s) + bot * t_s

    ys_g = np.arange(TH)[:, None].astype(np.float32)
    xs_g = np.arange(TW)[None, :].astype(np.float32)

    # 2. Primary glow orb — accent color, upper-right area
    accent = np.array(c["accent"], dtype=np.float32)
    gx = int(TW * 0.68);  gy = int(TH * 0.28)
    dist  = np.sqrt((xs_g - gx)**2 + (ys_g - gy)**2)
    glow  = np.clip(1.0 - dist / 340, 0, 1) ** 2.0
    for ch in range(3):
        arr[:, :, ch] = np.clip(arr[:, :, ch] + accent[ch] * glow * 0.30, 0, 255)

    # 3. Secondary warm glow — lower-left, warmer tint (depth/lamp feel)
    g2x = int(TW * 0.16);  g2y = int(TH * 0.74)
    dist2 = np.sqrt((xs_g - g2x)**2 + (ys_g - g2y)**2)
    glow2 = np.clip(1.0 - dist2 / 230, 0, 1) ** 3.0
    warm  = np.array([
        min(255, c["bg_top"][0] + 55),
        min(255, c["bg_top"][1] + 18),
        max(0,   c["bg_top"][2] - 18),
    ], dtype=np.float32)
    for ch in range(3):
        arr[:, :, ch] = np.clip(arr[:, :, ch] + warm[ch] * glow2 * 0.20, 0, 255)

    img  = Image.fromarray(arr.astype(np.uint8))
    draw = ImageDraw.Draw(img, "RGBA")

    # 4. Stars — upper 55% of frame only
    n_stars = int(rng.integers(60, 95))
    for _ in range(n_stars):
        sx     = int(rng.uniform(30, TW - 30))
        sy     = int(rng.uniform(12, TH * 0.54))
        bright = int(rng.uniform(125, 215))
        # Weighted towards tiny stars
        sz     = int(rng.choice([1, 1, 2], p=[0.65, 0.25, 0.10]))
        sc     = (bright, bright, min(255, bright + 22), 255)
        if sz == 1:
            draw.point((sx, sy), fill=sc)
        else:
            draw.ellipse([sx-1, sy-1, sx+1, sy+1], fill=sc)

    # 5. Bokeh — soft semi-transparent accent blobs (depth of field feel)
    n_bokeh = int(rng.integers(7, 14))
    for _ in range(n_bokeh):
        bx  = int(rng.uniform(0, TW))
        by  = int(rng.uniform(0, TH))
        br  = int(rng.uniform(20, 70))
        bla = int(rng.uniform(8, 32))
        bc  = (min(255, int(accent[0] * 0.88)),
               min(255, int(accent[1] * 0.88)),
               min(255, int(accent[2] * 0.88)),
               bla)
        draw.ellipse([bx - br, by - br, bx + br, by + br], fill=bc)

    return img


# ── Theme-specific atmosphere FX ───────────────────────────────────────────────

def _add_theme_fx(img: Image.Image, theme: str, rng: np.random.Generator) -> Image.Image:
    """Overlay subtle atmospheric elements that hint at the theme's setting."""
    draw = ImageDraw.Draw(img, "RGBA")

    if theme in ("cozy_rain", "forest_rain"):
        # Diagonal rain streaks
        n = int(rng.integers(35, 60))
        for _ in range(n):
            x    = int(rng.uniform(0, TW))
            y0   = int(rng.uniform(0, TH * 0.85))
            ln   = int(rng.uniform(14, 38))
            a    = int(rng.uniform(20, 50))
            draw.line([(x, y0), (x + int(ln * 0.12), y0 + ln)],
                      fill=(190, 215, 255, a), width=1)

    elif theme == "winter_snow":
        # Soft snow dots scattered across frame
        n = int(rng.integers(45, 75))
        for _ in range(n):
            x = int(rng.uniform(0, TW))
            y = int(rng.uniform(0, TH))
            a = int(rng.uniform(35, 85))
            draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(225, 238, 255, a))

    elif theme == "neon_tokyo":
        # Subtle retro perspective grid on lower half
        hy = int(TH * 0.42)
        vp = TW // 2
        ac = THEMES[theme]["accent"]
        line_col = (int(ac[0] * 0.25), int(ac[1] * 0.25), int(ac[2] * 0.25), 38)
        for i in range(-9, 10):
            draw.line([(vp, hy), (vp + i * 115, TH)], fill=line_col, width=1)
        rows = 6
        for j in range(rows):
            frac = j / rows
            y    = hy + int((TH - hy) * frac * frac)
            a    = int(38 * frac)
            draw.line([(0, y), (TW, y)],
                      fill=(int(ac[0]*0.2), int(ac[1]*0.2), int(ac[2]*0.2), a), width=1)

    elif theme in ("sakura_night", "spring_dawn"):
        # Oval petal shapes drifting across upper frame
        ac = THEMES[theme]["accent"]
        n  = int(rng.integers(14, 24))
        for _ in range(n):
            px = int(rng.uniform(0, TW))
            py = int(rng.uniform(0, TH * 0.68))
            pr = int(rng.uniform(5, 12))
            a  = int(rng.uniform(45, 95))
            draw.ellipse([px - pr, py - pr // 2, px + pr, py + pr // 2],
                         fill=(*ac, a))

    elif theme == "amber_night":
        # Subtle warm horizontal haze bands (candlelight flicker suggestion)
        ac = THEMES[theme]["accent"]
        n  = int(rng.integers(3, 6))
        for _ in range(n):
            y = int(rng.uniform(TH * 0.55, TH))
            a = int(rng.uniform(8, 20))
            h = int(rng.uniform(4, 14))
            draw.rectangle([(0, y), (TW, y + h)], fill=(*ac, a))

    return img


# ── Vignette ──────────────────────────────────────────────────────────────────

def _apply_vignette(img: Image.Image, strength: float = 0.45) -> Image.Image:
    arr = np.array(img, dtype=np.float32)
    ys  = np.linspace(-1, 1, TH)[:, np.newaxis]
    xs  = np.linspace(-1, 1, TW)[np.newaxis, :]
    vig = 1.0 - strength * np.clip((xs**2 + ys**2), 0, 1) ** 0.65
    return Image.fromarray(np.clip(arr * vig[:, :, np.newaxis], 0, 255).astype(np.uint8))


# ── Duration badge ─────────────────────────────────────────────────────────────

def _draw_duration_badge(img: Image.Image, theme: str, duration: str) -> Image.Image:
    """Pill-shaped duration badge, top-left corner."""
    c    = THEMES[theme]
    draw = ImageDraw.Draw(img, "RGBA")
    font = _load_font(_resolve_title_font(), 30)

    text       = duration.upper()
    tw, th     = _text_size(draw, text, font)
    pad_x, pad_y = 18, 9
    bw = tw + pad_x * 2
    bh = th + pad_y * 2
    bx, by = 28, 28

    draw.rounded_rectangle([bx, by, bx + bw, by + bh],
                            radius=bh // 2,
                            fill=(*c["badge_bg"], 225),
                            outline=(255, 255, 255, 160), width=2)
    draw.text((bx + pad_x + 1, by + pad_y + 1), text,
              font=font, fill=(0, 0, 0, 80))
    draw.text((bx + pad_x, by + pad_y), text,
              font=font, fill=(*c["badge_text"], 255))
    return img


# ── Compositional layouts ──────────────────────────────────────────────────────
#
# Three genuinely different card *compositions* (not just RNG-seeded noise
# variants). Every layout still draws through the same per-theme color/FX
# system (THEMES, _build_bg, _add_theme_fx) — only the placement/size of the
# text card changes:
#
#   centered — original layout: card dead-centre, slightly below frame middle.
#   thirds   — rule-of-thirds: narrower card sitting in the left or right
#              third of the frame, on the lower third gridline, leaving the
#              opposite two-thirds free for the gradient/glow to breathe.
#   edge     — asymmetric: a wide low band hugging the bottom edge (opposite
#              the top-left duration badge), leaving the whole upper frame
#              open for the atmospheric background.
LAYOUT_NAMES = ("centered", "thirds", "edge")


def _stable_int(s: str) -> int:
    """
    Deterministic string hash that does NOT depend on Python's per-process
    hash randomization (unlike the builtin hash()), so layout selection is
    reproducible across runs/processes given the same theme+variant -- not
    just within a single process.
    """
    h = 0
    for ch in s:
        h = (h * 131 + ord(ch)) % 1_000_003
    return h


def _select_layout(theme_name: str, variant: int) -> str:
    """
    Deterministically pick a compositional layout from (theme_name, variant).
    Same inputs always produce the same layout (reproducible thumbnails).
    Consecutive variants (as run.py uses for the primary + `_alt` A/B pair)
    always land on *different* layouts, since LAYOUT_NAMES has length 3 and
    consecutive integers are never congruent mod 3.
    """
    idx = (_stable_int(theme_name) + variant) % len(LAYOUT_NAMES)
    return LAYOUT_NAMES[idx]


def _select_side(theme_name: str, variant: int) -> str:
    """Deterministically pick which edge/third ('left' or 'right') an
    off-center layout hugs, independent of the layout choice itself."""
    idx = (_stable_int(theme_name + "|side") + variant) % 2
    return "left" if idx == 0 else "right"


_TITLE_FONT_SIZES = (78, 68, 60, 52, 46)


def _fit_title_font(draw: ImageDraw.ImageDraw, text: str, font_path: str, max_text_w: int):
    """Shrink the title font until it fits max_text_w, so narrower (thirds/
    edge) cards don't overflow their frosted-glass backing. Falls back to the
    smallest size if even that overflows, rather than looping forever."""
    font = w = h = None
    for size in _TITLE_FONT_SIZES:
        font = _load_font(font_path, size)
        w, h = _text_size(draw, text, font)
        if w <= max_text_w:
            return font, w, h
    return font, w, h


def _card_position(layout: str, side: str, card_w: int, card_h: int) -> tuple[int, int]:
    """Compute the (x, y) top-left origin of the text card for a layout."""
    if layout == "thirds":
        cx_frac = 0.24 if side == "left" else 0.76
        card_x  = int(TW * cx_frac) - card_w // 2
        card_x  = max(40, min(TW - 40 - card_w, card_x))
        card_y  = int(TH * 0.60) - card_h // 2   # sits on the lower third line
    elif layout == "edge":
        margin = 56
        card_x = margin if side == "left" else TW - margin - card_w
        card_x = max(40, min(TW - 40 - card_w, card_x))
        card_y = TH - card_h - 64             # low band hugging the bottom edge
    else:  # centered
        card_x = (TW - card_w) // 2
        card_y = int(TH * 0.52) - card_h // 2   # slightly below centre
    return card_x, card_y


def _max_card_width(layout: str) -> int:
    if layout == "thirds":
        return int(TW * 0.44)
    if layout == "edge":
        return int(TW * 0.62)
    return TW - 80   # centered


# ── Elegant frosted-glass text card ───────────────────────────────────────────

def _draw_text_card(
    img: Image.Image,
    theme: str,
    short_title: str,
    duration: str,
    layout: str = "centered",
    side: str = "left",
    glass_alpha: int = 155,
    force_solid_dark: bool = False,
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """
    Text card with frosted-glass backing, composed per `layout`:
      ✦  (accent deco mark)
      Title In Mixed Case   (auto-shrinks to fit the card)
      ─────────────────     (thin accent rule)
      lofi · 2 hours        (30px subtitle)

    Returns (img, card_bbox) where card_bbox is (x0, y0, x1, y1) in full-frame
    pixel coordinates, so callers can run a legibility check against exactly
    the region that was drawn.
    """
    c         = THEMES[theme]
    font_path = _resolve_title_font()

    # Mixed case title — much more elegant than ALL CAPS
    title_text = short_title.title()
    sub_text   = f"lofi  ·  {duration}"
    deco_text  = "*"

    draw = ImageDraw.Draw(img, "RGBA")

    pad_x    = 44
    pad_top  = 18
    pad_bot  = 22
    rule_gap = 10    # gap above and below the accent rule

    max_card_w = _max_card_width(layout)
    title_font, tw_t, th_t = _fit_title_font(draw, title_text, font_path, max_card_w - pad_x * 2)
    sub_font   = _load_font(font_path, 30)
    deco_font  = _load_font(font_path, 26)

    tw_s, th_s = _text_size(draw, sub_text,  sub_font)
    tw_d, th_d = _text_size(draw, deco_text, deco_font)

    # Card dimensions: pad around the widest element
    inner_w  = max(tw_t, tw_s, tw_d)
    card_w   = min(inner_w + pad_x * 2, max_card_w)
    card_h   = pad_top + th_d + 10 + th_t + rule_gap + 2 + rule_gap + th_s + pad_bot

    card_x, card_y = _card_position(layout, side, card_w, card_h)

    # Frosted glass: dark semi-transparent rounded rect. `force_solid_dark`
    # ignores the theme's tinted overlay color in favor of a near-black
    # backing -- used as the last-resort legibility fallback, since it
    # guarantees strong contrast against every theme's (light) text_main.
    if force_solid_dark:
        glass_col = (10, 10, 14, glass_alpha)
    else:
        glass_col = (*c["grad_overlay"][:3], glass_alpha)
    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + card_h],
        radius=20, fill=glass_col,
    )
    # Subtle bright border
    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + card_h],
        radius=20, outline=(*c["accent"], 55), width=1,
    )

    # ── Deco mark ✦ ──
    cur_y = card_y + pad_top
    dx    = card_x + (card_w - tw_d) // 2
    draw.text((dx, cur_y), deco_text, font=deco_font, fill=(*c["accent"], 210))
    cur_y += th_d + 10

    # ── Title ──
    tx = card_x + (card_w - tw_t) // 2
    draw.text((tx + 2, cur_y + 2), title_text, font=title_font,
              fill=(0, 0, 0, 70))   # shadow
    draw.text((tx,     cur_y),     title_text, font=title_font,
              fill=(*c["text_main"], 255))
    cur_y += th_t + rule_gap

    # ── Accent rule ──
    rx0 = card_x + pad_x
    rx1 = card_x + card_w - pad_x
    draw.line([(rx0, cur_y), (rx1, cur_y)], fill=(*c["accent"], 170), width=2)
    cur_y += 2 + rule_gap

    # ── Subtitle ──
    sx = card_x + (card_w - tw_s) // 2
    draw.text((sx, cur_y), sub_text, font=sub_font,
              fill=(*c["accent"], 195))

    card_bbox = (card_x, card_y, card_x + card_w, card_y + card_h)
    return img, card_bbox


# ── Small-size legibility check ────────────────────────────────────────────────
#
# Pure luminance-contrast math (WCAG relative-luminance formula), run against
# the thumbnail downsampled to a realistic YouTube grid preview size. No AI/
# ML involved -- just numpy on pixel values.

_PREVIEW_W, _PREVIEW_H = 120, 90     # ~ a YouTube grid thumbnail preview
_MIN_CONTRAST_RATIO    = 3.0         # WCAG AA "large text" threshold


def _relative_luminance(rgb) -> float:
    """WCAG 2.x relative luminance of an sRGB color."""
    srgb = np.asarray(rgb, dtype=np.float64) / 255.0
    lin  = np.where(srgb <= 0.03928, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    return float(0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2])


def _contrast_ratio(rgb1, rgb2) -> float:
    """WCAG contrast ratio between two sRGB colors, always >= 1.0."""
    l1, l2 = _relative_luminance(rgb1), _relative_luminance(rgb2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _check_card_legibility(
    img: Image.Image,
    card_bbox: tuple[int, int, int, int],
    text_rgb: tuple[int, int, int],
    min_ratio: float = _MIN_CONTRAST_RATIO,
) -> tuple[bool, float]:
    """
    Downsample the full thumbnail to a realistic small YouTube-grid preview
    size (~120x90) and measure the WCAG contrast ratio between the card's
    nominal text color and the *observed* average color of the card region
    once downsampled. At small preview sizes, thin glyph strokes get
    resampled/anti-aliased into the surrounding card background -- so
    comparing the nominal text color against the downsampled region average
    is a real proxy for "does the title still read as text, or does it wash
    out into the card" once YouTube shrinks it for the video grid.

    Returns (passes, ratio).
    """
    small = img.convert("RGB").resize((_PREVIEW_W, _PREVIEW_H), Image.LANCZOS)
    x0, y0, x1, y1 = card_bbox
    sx0 = max(0, min(_PREVIEW_W - 1, round(x0 * _PREVIEW_W / TW)))
    sx1 = max(sx0 + 1, min(_PREVIEW_W, round(x1 * _PREVIEW_W / TW)))
    sy0 = max(0, min(_PREVIEW_H - 1, round(y0 * _PREVIEW_H / TH)))
    sy1 = max(sy0 + 1, min(_PREVIEW_H, round(y1 * _PREVIEW_H / TH)))

    region = np.array(small.crop((sx0, sy0, sx1, sy1)), dtype=np.float64)
    bg_rgb = region.reshape(-1, 3).mean(axis=0)

    ratio = _contrast_ratio(text_rgb, tuple(bg_rgb))
    return ratio >= min_ratio, ratio


# ── Watermark ─────────────────────────────────────────────────────────────────

_WATERMARK_OV = None


def _draw_watermark(img: Image.Image) -> Image.Image:
    global _WATERMARK_OV
    if _WATERMARK_OV is None:
        ov   = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
        d    = ImageDraw.Draw(ov)
        font = _load_font(
            "/usr/share/fonts/TTF/FiraSansCondensed-Heavy.ttf"
            if os.path.exists("/usr/share/fonts/TTF/FiraSansCondensed-Heavy.ttf")
            else _resolve_title_font(),
            20,
        )
        text = "lofi factory"
        x, y = 32, TH - 38
        d.text((x + 1, y + 1), text, fill=(0, 0, 0, 80), font=font)
        d.text((x, y),         text, fill=(210, 210, 210, 100), font=font)
        _WATERMARK_OV = np.array(ov)

    ov_arr = _WATERMARK_OV
    alpha  = ov_arr[:, :, 3:4].astype(np.float32) / 255.0
    dst    = np.array(img, dtype=np.float32)
    result = np.clip(
        dst * (1 - alpha) + ov_arr[:, :, :3].astype(np.float32) * alpha,
        0, 255,
    ).astype(np.uint8)
    return Image.fromarray(result)


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_thumbnail(
    theme_name: str = "cozy_rain",
    duration:   str = "2 hours",
    title:      str = None,
    variant:    int = 0,
) -> tuple[str, str]:
    if theme_name not in THEMES:
        theme_name = "cozy_rain"

    if title is None:
        choices = TITLE_TEMPLATES.get(theme_name, TITLE_TEMPLATES["cozy_rain"])
        title   = choices[variant % len(choices)]

    # Prefer a short phrase derived from the actual generated SEO title, so
    # thumbnail and video title never disagree about what the video is
    # about; fall back to the theme's static template pool when the real
    # title isn't usable as thumbnail text (too long, no title passed, etc).
    short_title = _derive_short_title(title)
    if short_title is None:
        choices     = TITLE_TEMPLATES.get(theme_name, TITLE_TEMPLATES["cozy_rain"])
        short_title = choices[variant % len(choices)]

    seed = abs(variant * 137 + hash(theme_name) % 10000)
    rng  = np.random.default_rng(seed)

    # Deterministic per-track composition: same (theme, variant) always
    # renders the same layout, and the A/B `_alt` pair (variant, variant+1)
    # always lands on a genuinely different composition -- not just
    # different decorative RNG noise (see LAYOUT_NAMES docstring above).
    layout = _select_layout(theme_name, variant)
    side   = _select_side(theme_name, variant)

    ts       = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(ASSETS_DIR, f"thumb_{theme_name}_{ts}.jpg")

    print(f"[THUMB] {theme_name} | '{short_title}' | {duration} | layout={layout}/{side}")

    base_img = _build_bg(theme_name, seed)
    base_img = _add_theme_fx(base_img, theme_name, rng)
    base_img = _apply_vignette(base_img, strength=0.44)
    base_img = _draw_duration_badge(base_img, theme_name, duration)

    c = THEMES[theme_name]

    # Legibility-guarded card draw: try the selected layout at increasing
    # card-background opacity; if it still fails the small-preview contrast
    # check, fall back to the centered layout with a forced near-black
    # (highest-contrast) card background rather than silently shipping an
    # unreadable thumbnail.
    attempts = [
        (layout,     side, 155, False),
        (layout,     side, 205, False),
        (layout,     side, 240, False),
        ("centered", "left", 245, True),
    ]
    img = None
    for i, (lyt, sd, alpha, solid_dark) in enumerate(attempts):
        candidate = base_img.copy()
        candidate, card_bbox = _draw_text_card(
            candidate, theme_name, short_title, duration,
            layout=lyt, side=sd, glass_alpha=alpha, force_solid_dark=solid_dark,
        )
        ok, ratio = _check_card_legibility(candidate, card_bbox, c["text_main"])
        if ok or i == len(attempts) - 1:
            img = candidate
            if not ok:
                print(f"[THUMB] legibility check below threshold even after fallback "
                      f"(ratio={ratio:.2f} < {_MIN_CONTRAST_RATIO}) -- shipping best effort")
            elif i > 0:
                print(f"[THUMB] legibility check passed after adjustment #{i} (ratio={ratio:.2f})")
            break

    img = _draw_watermark(img)

    img.save(out_path, "JPEG", quality=95, optimize=True, progressive=True)
    size_kb = os.path.getsize(out_path) // 1024
    print(f"[THUMB] → {out_path} ({size_kb} KB)")
    return out_path, title


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _theme    = sys.argv[1] if len(sys.argv) > 1 else "midnight_cafe"
    _duration = sys.argv[2] if len(sys.argv) > 2 else "2 hours"
    _variant  = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    generate_thumbnail(theme_name=_theme, duration=_duration, variant=_variant)
    print("Done.")
