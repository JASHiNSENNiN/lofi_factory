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
import time
import math
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
# Researched 2026-08-16 (YouTube thumbnail CTR guides, consistent across
# sources): high-CTR thumbnails run 0-3 "high-impact" words, not a full
# clause -- 28 chars was landing 5-6 words ("3 hours in. remote work"),
# forcing _fit_title_font to shrink hard to make it fit any reasonable card
# width. Cut closer to that target while still allowing a short real phrase
# (this app's concept-driven design deliberately avoids generic clickbait
# templates, so keep deriving from the real title rather than gutting to a
# bare 3-word cap) -- word-boundary trimming in _derive_short_title below
# still applies at this new budget.
_SHORT_TITLE_MAX_CHARS = 20


_DANGLING = {"of", "for", "to", "and", "the", "a", "an", "in", "on", "at", "with",
             "but", "or", "your", "my", "still", "straight", "no", "from", "by"}
# Words that only say "what genre / how long"; a clause made of nothing else
# describes no scene and is useless on a thumbnail.
_TAG_WORDS = {"lofi", "lo-fi", "hip", "hop", "study", "music", "beats", "chill",
              "mix", "of", "straight", "hour", "hours", "min", "minutes", "jazz",
              "soul", "neo", "city", "pop", "house", "rnb", "bossa", "nova",
              "ambient", "vaporwave", "chillhop", "phonk", "synthwave", "garage",
              "classical", "piano", "funk", "drill", "dark", "bedroom", "anime"}


_NOT_A_SCENE = re.compile(r"\b\d+\s*(hour|hours|min)\b|^no\b|\bone long set\b|\bcheck back\b")


def _is_tag_only(clause: str) -> bool:
    """True for clauses that describe no scene: only genre/duration words,
    a duration ("1 hour to sleep"), or a disclaimer ("no commentary")."""
    words = [w.strip(",.").lower() for w in clause.split()]
    return (all(w in _TAG_WORDS or w.isdigit() for w in words)
            or bool(_NOT_A_SCENE.search(clause.lower())))


def _clean_end(text: str) -> str:
    """Strip trailing punctuation, numbers and words that can't end a phrase."""
    words = text.strip(" ,·—-").split()
    while words and (words[-1].lower().strip(",.") in _DANGLING or words[-1].strip(",.").isdigit()):
        words.pop()
    return " ".join(words).strip(" ,·—-")


def _derive_short_title(full_title: str) -> str | None:
    """
    Short, thumbnail-sized phrase from the real SEO title, so thumbnail and
    title describe the same video. Picks the most descriptive whole clause
    that fits (clauses are separated by " · ", "," and " — "), skipping
    clauses that are only genre/duration tags, and never ends on a dangling
    word. Returns None when nothing usable is left, so the caller falls back
    to the theme's template phrases.
    """
    if not full_title:
        return None
    text = _EMOJI_RE.sub("", full_title).strip()
    text = _TRAILING_DURATION_RE.sub("", text).strip(" -—·")
    clauses = [c.strip() for c in re.split(r"\s+·\s+|,\s+|\s+—\s+", text) if c.strip()]
    # Only whole clauses: cutting a longer clause short gives half-phrases
    # like "made for tired", so if nothing fits, use the theme's own phrases.
    fitting = [_clean_end(c) for c in clauses
               if len(c) <= _SHORT_TITLE_MAX_CHARS and not _is_tag_only(c)]
    fitting = [c for c in fitting if len(c.split()) >= 2 and not _is_tag_only(c)]
    if not fitting:
        return None
    best = max(fitting, key=len)
    if len(best) < 4 or len(best.split()) < 2:
        return None
    return best.lower()


# ── Font management ────────────────────────────────────────────────────────────

_BEBAS_PATH = os.path.join(FONTS_DIR, "BebasNeue-Regular.ttf")
# Fixed 2026-08-16: the old dharmatype path 404'd (repo reorganized -- author
# folder renamed "_by_Ryoichi_Tsunekawa" -> "ByDhamraType", moved under a
# ttf/ subdir). Confirmed dead silently for who knows how long: every single
# thumbnail generated on this box fell all the way through to
# ImageFont.load_default() (a tiny fixed-size bitmap font that ignores the
# `size` argument entirely) because _resolve_title_font's other fallback
# paths (/usr/share/fonts/TTF/...) are Arch/Manjaro-convention paths that
# don't exist on this Debian box either -- see the real paths below.
_BEBAS_URL  = (
    "https://raw.githubusercontent.com/dharmatype/Bebas-Neue/master/"
    "fonts/BebasNeue(2018)ByDhamraType/ttf/BebasNeue-Regular.ttf"
)
_TITLE_FONT_PATH: str | None = None


def _ensure_bebas() -> str | None:
    if os.path.exists(_BEBAS_PATH):
        return _BEBAS_PATH
    try:
        import requests
        resp = requests.get(_BEBAS_URL, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 10_000:
            os.makedirs(FONTS_DIR, exist_ok=True)
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
        # Real paths on THIS box (confirmed via `find /usr/share/fonts`) --
        # the old list here was entirely Arch/Manjaro-convention
        # (/usr/share/fonts/TTF/...), which doesn't exist on Debian/Ubuntu,
        # so every single one of these silently missed and every thumbnail
        # fell through to PIL's tiny fixed-size default bitmap font. Ordered
        # condensed-and-bold first (fits more chars at a given width, same
        # intent as the old list) down to universally-present plain bold.
        "/usr/share/fonts/opentype/urw-base35/NimbusSansNarrow-Bold.otf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
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


# ── Bloom ──────────────────────────────────────────────────────────────────────

def _apply_bloom(img: Image.Image, threshold: int = 130,
                  blur_radius: int = 18, strength: float = 0.55) -> Image.Image:
    """
    Cheap bloom: isolate the brightest pixels (the glow orbs), Gaussian-blur
    just that layer, and screen-composite it back over the original. Gives
    the glow a real soft halo instead of the flat radial falloff the orb math
    alone produces -- standard procedural-graphics trick, PIL/numpy only.
    """
    arr  = np.asarray(img, dtype=np.float32)
    luma = arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114
    mask = np.clip((luma - threshold) / max(1, 255 - threshold), 0, 1)[:, :, None]
    bright = Image.fromarray((arr * mask).astype(np.uint8))
    bloom_arr = np.asarray(bright.filter(ImageFilter.GaussianBlur(blur_radius)),
                            dtype=np.float32)
    out = 255.0 - (255.0 - arr) * (255.0 - bloom_arr * strength) / 255.0
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


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


# ── Film grain ────────────────────────────────────────────────────────────────

def _apply_film_grain(img: Image.Image, seed: int, strength: float = 10.0) -> Image.Image:
    """Low-opacity luminance noise so flat gradient bands read as filmic
    texture instead of flat-digital -- seeded off the same per-render seed as
    everything else, so a given (theme, variant) always renders identically."""
    rng   = np.random.default_rng(seed + 90210)
    arr   = np.asarray(img, dtype=np.float32)
    noise = rng.normal(0, strength, size=(TH, TW, 1)).astype(np.float32)
    return Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8))


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


# Raised 2026-08-16: research is consistent that thumbnail titles need
# 60-80pt+ at native 1280x720 canvas resolution to read as "dominant," not
# just technically legible -- the old (78..46) range's smallest steps were
# routinely what got hit once a real (non-trivial) title needed to fit the
# card, landing well under that floor. Paired with the shorter
# _SHORT_TITLE_MAX_CHARS and wider _max_card_width below so the bigger
# sizes actually get room to be used instead of immediately shrinking back
# down to fit an unchanged card width.
_TITLE_FONT_SIZES = (108, 94, 82, 72, 64)


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
    # Widened 2026-08-16 alongside the bigger _TITLE_FONT_SIZES -- the old,
    # narrower caps (0.44/0.62) were the actual reason titles kept landing on
    # the smallest font-size step regardless of how big the range went.
    if layout == "thirds":
        return int(TW * 0.56)
    if layout == "edge":
        return int(TW * 0.74)
    return TW - 64   # centered


# ── Scene silhouette ────────────────────────────────────────────────────────────
#
# The single biggest gap versus competing lofi-channel thumbnails: this
# generator was pure abstract gradient + text, with no focal subject. Nearly
# every high-CTR lofi thumbnail (Lofi Girl etc.) leads with a recognizable
# illustrated scene. Added here as flat, single-tone silhouette shapes built
# from plain PIL polygon/ellipse primitives -- no external art assets, no AI
# image generation, same toolkit already used for the rain streaks / neon
# grid / petals in `_add_theme_fx`.

def _scene_colors(theme: str) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """(fill, rim) colors for a scene silhouette: a near-black fill (reads as
    a silhouette regardless of theme tint) and an accent-colored rim used
    sparingly for backlit edge details (headphone band, steam, vinyl grooves)."""
    c = THEMES[theme]
    fill = (
        max(0, c["bg_top"][0] // 3),
        max(0, c["bg_top"][1] // 3),
        max(0, c["bg_top"][2] // 3),
        235,
    )
    # Bright enough to outline the shape: without a rim light a near-black
    # silhouette disappears into the night-sky backgrounds.
    rim = (*c["accent"], 170)
    return fill, rim


def _silhouette_listener(draw, cx, cy, w, h, fill, rim, rng) -> tuple[float, float, float, float]:
    """Person-at-desk-with-headphones bust -- universal fallback subject."""
    scale = min(w, h)
    head_r = scale * 0.17
    head_cy = cy - scale * 0.18
    shoulder_w = scale * 0.55
    shoulder_top = head_cy + head_r * 1.15   # small neck gap below the head
    shoulder_bot = cy + scale * 0.42
    # Rounded shoulders (a straight-sided trapezoid read as a tombstone),
    # rim-lit so the shape reads against a dark background.
    draw.rounded_rectangle(
        [cx - shoulder_w * 0.5, shoulder_top, cx + shoulder_w * 0.5, shoulder_bot],
        radius=int(shoulder_w * 0.32), fill=fill, outline=rim, width=2)
    draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r],
                 fill=fill, outline=rim, width=2)
    band_r = head_r * 1.25
    draw.arc(
        [cx - band_r, head_cy - band_r * 1.1, cx + band_r, head_cy + band_r * 0.9],
        200, 340, fill=rim, width=max(2, int(scale * 0.02)),
    )
    cup_r = head_r * 0.42
    draw.ellipse([cx - band_r - cup_r * 0.3, head_cy - cup_r,
                  cx - band_r + cup_r * 1.1, head_cy + cup_r], fill=fill, outline=rim, width=2)
    draw.ellipse([cx + band_r - cup_r * 1.1, head_cy - cup_r,
                  cx + band_r + cup_r * 0.3, head_cy + cup_r], fill=fill, outline=rim, width=2)
    x0 = cx - shoulder_w * 0.5 - cup_r
    x1 = cx + shoulder_w * 0.5 + cup_r
    y0 = head_cy - band_r * 1.1
    y1 = shoulder_bot
    return (x0, y0, x1, y1)


def _silhouette_cat(draw, cx, cy, w, h, fill, rim, rng) -> tuple[float, float, float, float]:
    """Sitting cat, side profile, with a curved tail."""
    scale = min(w, h)
    body_w, body_h = scale * 0.5, scale * 0.6
    body_box = [cx - body_w * 0.5, cy - body_h * 0.2, cx + body_w * 0.5, cy + body_h * 0.8]
    draw.ellipse(body_box, fill=fill)
    head_r = scale * 0.18
    head_cx, head_cy = cx + body_w * 0.15, cy - body_h * 0.25
    draw.ellipse([head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r], fill=fill)
    draw.polygon([
        (head_cx - head_r * 0.7, head_cy - head_r * 0.6),
        (head_cx - head_r * 0.2, head_cy - head_r * 1.5),
        (head_cx + head_r * 0.1, head_cy - head_r * 0.7),
    ], fill=fill)
    draw.polygon([
        (head_cx + head_r * 0.2, head_cy - head_r * 0.7),
        (head_cx + head_r * 0.6, head_cy - head_r * 1.4),
        (head_cx + head_r * 0.8, head_cy - head_r * 0.5),
    ], fill=fill)
    tail_pts = []
    for t in range(9):
        f = t / 8
        tx = cx - body_w * 0.45 - scale * 0.28 * f
        ty = cy + body_h * 0.5 - scale * 0.35 * math.sin(f * math.pi * 0.9)
        tail_pts.append((tx, ty))
    draw.line(tail_pts, fill=fill, width=max(3, int(scale * 0.045)), joint="curve")
    xs = [p[0] for p in tail_pts] + [body_box[0], body_box[2]]
    ys = [p[1] for p in tail_pts] + [body_box[1], head_cy - head_r * 1.5]
    return (min(xs), min(ys), max(xs), body_box[3])


def _silhouette_plant(draw, cx, cy, w, h, fill, rim, rng) -> tuple[float, float, float, float]:
    """Potted plant, a small fan of leaves radiating up from a pot."""
    scale = min(w, h)
    pot_w, pot_h = scale * 0.34, scale * 0.22
    pot_top = cy + scale * 0.12
    draw.polygon([
        (cx - pot_w * 0.5, pot_top), (cx + pot_w * 0.5, pot_top),
        (cx + pot_w * 0.38, pot_top + pot_h), (cx - pot_w * 0.38, pot_top + pot_h),
    ], fill=fill)
    n_leaves = 5
    leaf_len = scale * 0.42
    for i in range(n_leaves):
        ang = math.radians(-90 + (i - (n_leaves - 1) / 2) * 22)
        tipx = cx + leaf_len * math.sin(ang)
        tipy = pot_top - leaf_len * math.cos(ang)
        midx = cx + leaf_len * 0.5 * math.sin(ang) + leaf_len * 0.14 * math.cos(ang)
        midy = pot_top - leaf_len * 0.5 * math.cos(ang) + leaf_len * 0.14 * math.sin(ang)
        draw.polygon([(cx, pot_top), (midx, midy), (tipx, tipy)], fill=fill)
    x0 = cx - leaf_len
    x1 = cx + leaf_len
    y0 = pot_top - leaf_len * 1.05
    y1 = pot_top + pot_h
    return (x0, y0, x1, y1)


def _silhouette_coffee_cup(draw, cx, cy, w, h, fill, rim, rng) -> tuple[float, float, float, float]:
    """Cup with a handle and bezier-ish curling steam."""
    scale = min(w, h)
    cup_w, cup_h = scale * 0.34, scale * 0.28
    cup_top = cy
    draw.rounded_rectangle(
        [cx - cup_w * 0.5, cup_top, cx + cup_w * 0.5, cup_top + cup_h],
        radius=cup_h * 0.15, fill=fill,
    )
    handle_r = cup_h * 0.28
    draw.ellipse(
        [cx + cup_w * 0.5 - handle_r * 0.4, cup_top + cup_h * 0.25,
         cx + cup_w * 0.5 + handle_r * 1.3, cup_top + cup_h * 0.85],
        outline=fill, width=max(3, int(scale * 0.03)),
    )
    steam_top = cup_top - scale * 0.06
    for i, dx in enumerate((-0.18, 0.0, 0.18)):
        pts = []
        for t in range(10):
            f = t / 9
            sx = cx + cup_w * dx + math.sin(f * math.pi * 2.2 + i) * scale * 0.03
            sy = steam_top - f * scale * 0.34
            pts.append((sx, sy))
        draw.line(pts, fill=rim, width=max(2, int(scale * 0.012)), joint="curve")
    x0 = cx - cup_w * 0.5 - handle_r * 0.3
    x1 = cx + cup_w * 0.5 + handle_r * 1.3
    y0 = steam_top - scale * 0.34
    y1 = cup_top + cup_h
    return (x0, y0, x1, y1)


def _silhouette_vinyl_cassette(draw, cx, cy, w, h, fill, rim, rng) -> tuple[float, float, float, float]:
    """Spinning vinyl record: disc + concentric grooves + label."""
    scale = min(w, h)
    r = scale * 0.4
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
    for frac in (0.78, 0.6, 0.42):
        draw.ellipse([cx - r * frac, cy - r * frac, cx + r * frac, cy + r * frac],
                      outline=rim, width=1)
    label_r = r * 0.28
    draw.ellipse([cx - label_r, cy - label_r, cx + label_r, cy + label_r], fill=rim)
    hole_r = r * 0.04
    draw.ellipse([cx - hole_r, cy - hole_r, cx + hole_r, cy + hole_r], fill=fill)
    return (cx - r, cy - r, cx + r, cy + r)


def _silhouette_window_scene(draw, cx, cy, w, h, fill, rim, rng) -> tuple[float, float, float, float]:
    """Window frame with a small skyline glimpsed through the lower pane."""
    scale = min(w, h)
    fw, fh = scale * 0.6, scale * 0.82
    x0, y0, x1, y1 = cx - fw / 2, cy - fh / 2, cx + fw / 2, cy + fh / 2
    frame_w = max(4, int(scale * 0.035))
    draw.rounded_rectangle([x0, y0, x1, y1], radius=scale * 0.03, outline=fill, width=frame_w)
    draw.line([(cx, y0), (cx, y1)], fill=fill, width=frame_w)
    my = y0 + (y1 - y0) * 0.55
    draw.line([(x0, my), (x1, my)], fill=fill, width=frame_w)
    n = 4
    pane_w = (x1 - x0) / n
    for i in range(n):
        bx0 = x0 + pane_w * i + 3
        bx1 = x0 + pane_w * (i + 1) - 3
        bh  = (fh * 0.5) * rng.uniform(0.25, 0.55)
        draw.rectangle([bx0, y1 - bh, bx1, y1 - 2], fill=fill)
    return (x0, y0, x1, y1)


# Per-theme scene pools -- deterministic index picks a scene that fits the
# theme's setting (rain -> window, house/vaporwave -> vinyl, cozy themes ->
# cat/plant/coffee), same "pick from a themed pool via stable hash" pattern
# TITLE_TEMPLATES already uses.
SCENE_POOL = {
    "cozy_rain":      ("window_scene", "listener", "coffee_cup"),
    "midnight_cafe":  ("coffee_cup", "listener", "vinyl_cassette"),
    "purple_dusk":    ("listener", "vinyl_cassette", "plant"),
    "amber_night":    ("coffee_cup", "plant", "listener"),
    "winter_snow":    ("window_scene", "cat", "listener"),
    "autumn_study":   ("plant", "cat", "coffee_cup"),
    "spring_dawn":    ("plant", "cat", "listener"),
    "neon_tokyo":     ("window_scene", "vinyl_cassette", "listener"),
    "summer_lofi":    ("plant", "listener", "vinyl_cassette"),
    "blue_hour":      ("listener", "window_scene", "vinyl_cassette"),
    "forest_rain":    ("window_scene", "cat", "plant"),
    "sakura_night":   ("plant", "listener", "cat"),
    "vaporwave":      ("vinyl_cassette", "listener", "window_scene"),
    "lofi_house":     ("vinyl_cassette", "listener", "coffee_cup"),
    "lofi_classical": ("vinyl_cassette", "listener", "plant"),
    "bedroom_pop":    ("listener", "vinyl_cassette", "plant"),
    "lofi_rnb":       ("vinyl_cassette", "coffee_cup", "listener"),
}

_SCENE_FUNCS = {
    "listener":      _silhouette_listener,
    "cat":           _silhouette_cat,
    "plant":         _silhouette_plant,
    "coffee_cup":    _silhouette_coffee_cup,
    "vinyl_cassette": _silhouette_vinyl_cassette,
    "window_scene":  _silhouette_window_scene,
}


def _select_scene(theme_name: str, variant: int) -> str:
    """Deterministically pick a scene from (theme_name, variant), same
    reproducibility guarantee as `_select_layout`/`_select_side`."""
    pool = SCENE_POOL.get(theme_name, ("listener", "vinyl_cassette", "plant"))
    idx = (_stable_int(theme_name + "|scene") + variant) % len(pool)
    return pool[idx]


def _scene_slot(layout: str, side: str) -> tuple[int, int, int, int]:
    """Region (cx, cy, max_w, max_h) on the side opposite the text card where
    a scene silhouette can be drawn without touching it."""
    opp = "right" if side == "left" else "left"
    if layout == "thirds":
        cx = int(TW * (0.76 if opp == "right" else 0.24))
        return cx, int(TH * 0.46), int(TW * 0.30), int(TH * 0.62)
    if layout == "edge":
        cx = int(TW * (0.82 if opp == "right" else 0.18))
        return cx, int(TH * 0.36), int(TW * 0.30), int(TH * 0.56)
    # centered: the card spans nearly the full width mid-frame, so there's
    # only room for a corner accent -- tucked bottom-right, clear of both the
    # top-left duration badge and the mid-frame card. Pulled in from the
    # extreme corner (and sized up a bit) so it doesn't disappear into the
    # heaviest vignette falloff -- a corner accent nobody can see isn't
    # earning its keep.
    return int(TW * 0.86), int(TH * 0.80), int(TW * 0.20), int(TH * 0.26)


def _check_scene_card_collision(scene_bbox, card_bbox) -> bool:
    """True if the two axis-aligned boxes overlap."""
    if scene_bbox is None:
        return False
    sx0, sy0, sx1, sy1 = scene_bbox
    cx0, cy0, cx1, cy1 = card_bbox
    return sx0 < cx1 and sx1 > cx0 and sy0 < cy1 and sy1 > cy0


def _draw_scene_silhouette(
    img: Image.Image,
    theme: str,
    layout: str,
    side: str,
    variant: int,
    rng: np.random.Generator,
    avoid_bbox: tuple[int, int, int, int],
) -> tuple[Image.Image, tuple[float, float, float, float] | None]:
    """
    Draw a themed silhouette scene into the slot opposite the text card. The
    collision check runs against the *reserved slot box* before any pixels
    are drawn (rather than drawing then undoing), shrinking once and finally
    skipping the scene entirely rather than ever drawing over the card.
    Returns (img, scene_bbox); scene_bbox is None if nothing was drawn.
    """
    scene_name = _select_scene(theme, variant)
    fn = _SCENE_FUNCS[scene_name]
    fill, rim = _scene_colors(theme)
    cx, cy, max_w, max_h = _scene_slot(layout, side)

    for scale_mult in (1.0, 0.65):
        w, h = int(max_w * scale_mult), int(max_h * scale_mult)
        reserved = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        if not _check_scene_card_collision(reserved, avoid_bbox):
            draw = ImageDraw.Draw(img, "RGBA")
            bbox = fn(draw, cx, cy, w, h, fill, rim, rng)
            return img, bbox
    return img, None


# ── Elegant frosted-glass text card ───────────────────────────────────────────

def _card_geometry(draw: ImageDraw.ImageDraw, theme: str, short_title: str,
                    duration: str, layout: str, side: str) -> dict:
    """
    Compute the text card's fonts/sizes/position without drawing anything.
    Font metrics don't depend on image content, so this is deterministic
    given the same inputs -- callers that need to know the card's real
    footprint *before* it's drawn (scene silhouette placement) can call this
    directly and get exactly the geometry `_draw_text_card` will later use.
    """
    font_path = _resolve_title_font()

    # Mixed case title — much more elegant than ALL CAPS
    title_text = short_title.title()
    # The duration is already on the corner badge; don't print it twice.
    sub_text   = "lofi beats"
    # No deco mark: the intended ✦ isn't in the title font and rendered as "*".
    deco_text  = ""

    pad_x    = 44
    pad_top  = 18
    pad_bot  = 22
    rule_gap = 10    # gap above and below the accent rule

    max_card_w = _max_card_width(layout)
    title_font, tw_t, th_t = _fit_title_font(draw, title_text, font_path, max_card_w - pad_x * 2)
    sub_font   = _load_font(font_path, 30)
    deco_font  = _load_font(font_path, 26)

    tw_s, th_s = _text_size(draw, sub_text,  sub_font)
    tw_d, th_d = (0, 0) if not deco_text else _text_size(draw, deco_text, deco_font)
    # Glyph boxes start below the draw origin (the font's top bearing), so
    # the title's real bottom edge is its box bottom, not its box height.
    th_t = draw.textbbox((0, 0), title_text, font=title_font,
                         stroke_width=max(3, title_font.size // 16))[3]
    th_s = draw.textbbox((0, 0), sub_text, font=sub_font)[3]

    # Card dimensions: pad around the widest element
    inner_w  = max(tw_t, tw_s, tw_d)
    card_w   = min(inner_w + pad_x * 2, max_card_w)
    deco_h   = th_d + 10 if deco_text else 0
    card_h   = pad_top + deco_h + th_t + rule_gap + 2 + rule_gap + th_s + pad_bot

    card_x, card_y = _card_position(layout, side, card_w, card_h)

    return dict(
        title_text=title_text, sub_text=sub_text, deco_text=deco_text,
        title_font=title_font, sub_font=sub_font, deco_font=deco_font,
        tw_t=tw_t, th_t=th_t, tw_s=tw_s, th_s=th_s, tw_d=tw_d, th_d=th_d,
        pad_x=pad_x, pad_top=pad_top, pad_bot=pad_bot, rule_gap=rule_gap,
        card_x=card_x, card_y=card_y, card_w=card_w, card_h=card_h,
    )


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
    c    = THEMES[theme]
    draw = ImageDraw.Draw(img, "RGBA")

    g = _card_geometry(draw, theme, short_title, duration, layout, side)
    title_text, sub_text, deco_text = g["title_text"], g["sub_text"], g["deco_text"]
    title_font, sub_font, deco_font = g["title_font"], g["sub_font"], g["deco_font"]
    tw_t, th_t = g["tw_t"], g["th_t"]
    tw_s, th_s = g["tw_s"], g["th_s"]
    tw_d, th_d = g["tw_d"], g["th_d"]
    pad_x, pad_top, rule_gap = g["pad_x"], g["pad_top"], g["rule_gap"]
    card_x, card_y, card_w, card_h = g["card_x"], g["card_y"], g["card_w"], g["card_h"]

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
    if deco_text:
        dx = card_x + (card_w - tw_d) // 2
        draw.text((dx, cur_y), deco_text, font=deco_font, fill=(*c["accent"], 210))
        cur_y += th_d + 10

    # ── Title ──
    # Real stroke_width outline (native since Pillow 6.2, not a hand-rolled
    # offset-shadow hack) -- researched 2026-08-16: a solid outline is what
    # every YouTube-thumbnail CTR guide converges on for keeping text
    # readable at the ~120px-wide grid preview size regardless of what's
    # behind it, since a soft drop-shadow alone still washes into a busy/
    # similarly-toned background once downsampled that small.
    tx = card_x + (card_w - tw_t) // 2
    draw.text((tx, cur_y), title_text, font=title_font,
              fill=(*c["text_main"], 255),
              stroke_width=max(3, title_font.size // 16), stroke_fill=(0, 0, 0, 235))
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
# Raised 2026-08-16 from 3.0 (bare WCAG AA "large text" minimum, meant for
# comfortable normal-size reading) to 4.5: every YouTube-thumbnail CTR guide
# researched converges on ~4.5:1 measured AT the ~120px-wide grid-preview
# size specifically, a meaningfully higher bar than "technically passes
# accessibility contrast" -- now that the title also gets a real black
# stroke_width outline (see _draw_text_card), this should be comfortably
# hit more often instead of routinely tripping the force_solid_dark fallback.
_MIN_CONTRAST_RATIO    = 4.5


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


# ── Whole-frame brightness check ────────────────────────────────────────────────
#
# Same WCAG-luminance math as `_relative_luminance`, applied to the entire
# frame instead of one text/background pair -- catches the frame as a whole
# rendering too dark to read in the YouTube grid (or, less likely with this
# palette style, blown out), independent of whether the text card itself
# passes its own contrast check.

# Calibrated 2026-08-19 against real output across all 17 themes (measured
# range ~3.5-9.0 on this WCAG-luma 0-255 scale) rather than guessed -- the
# whole-frame mean is dominated by the deliberately near-black night-sky
# background (only the small text card is bright), so a "normal reading
# room" luma floor like 28 would trip on every single legitimate render.
# These bounds exist to catch an actual bug (e.g. an all-black frame from a
# broken draw call, or a blown-out one), not to police this art style's
# intentional moodiness.
_MIN_MEAN_LUMA = 1.5
_MAX_MEAN_LUMA = 200.0


def _check_brightness(img: Image.Image,
                       min_luma: float = _MIN_MEAN_LUMA,
                       max_luma: float = _MAX_MEAN_LUMA) -> tuple[bool, float]:
    """Mean WCAG luma (0-255 scale) of the final frame. Returns (passes, mean_luma)."""
    arr  = np.asarray(img.convert("RGB"), dtype=np.float64) / 255.0
    lin  = np.where(arr <= 0.03928, arr / 12.92, ((arr + 0.055) / 1.055) ** 2.4)
    luma = 0.2126 * lin[:, :, 0] + 0.7152 * lin[:, :, 1] + 0.0722 * lin[:, :, 2]
    mean_luma = float(luma.mean()) * 255.0
    return (min_luma <= mean_luma <= max_luma), mean_luma


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
        # Small soundwave glyph mark ahead of the wordmark -- gives the
        # watermark a consistent recognizable *shape* (not just a text
        # string) across every theme, for channel recognition at a glance.
        gx, gy = 32, TH - 58
        bar_w  = 3
        heights = (7, 13, 9, 16, 6)
        for i, bh in enumerate(heights):
            bx = gx + i * (bar_w + 3)
            d.rounded_rectangle(
                [bx, gy + (16 - bh), bx + bar_w, gy + 16],
                radius=1, fill=(210, 210, 210, 130),
            )

        # Same channel name the video frame shows (one brand, not two).
        from scripts.visual_v2.config import CHANNEL_NAME
        text = CHANNEL_NAME.lower()
        x, y = gx + len(heights) * (bar_w + 3) + 6, TH - 38
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

    seed = abs(variant * 137 + _stable_int(theme_name) % 10000)   # hash() is salted per process
    rng  = np.random.default_rng(seed)

    # Deterministic per-track composition: same (theme, variant) always
    # renders the same layout, and the A/B `_alt` pair (variant, variant+1)
    # always lands on a genuinely different composition -- not just
    # different decorative RNG noise (see LAYOUT_NAMES docstring above).
    layout = _select_layout(theme_name, variant)
    side   = _select_side(theme_name, variant)

    ts       = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(ASSETS_DIR, f"thumb_{theme_name}_{ts}.jpg")
    # run.py calls this twice back-to-back for the main/alt A/B pair
    # (confirmed 2026-08-16), and each call comfortably finishes well under a
    # second -- with only second resolution, the alt call's output silently
    # overwrote the main call's file on disk whenever both landed in the same
    # wall-clock second (the common case), while run.py kept two Python path
    # strings that had actually collapsed to one real file, quietly breaking
    # the A/B thumbnail feature. Waiting out the collision (rather than
    # adding sub-second precision to the filename) keeps this format exactly
    # as every other consumer's regex across the codebase expects it
    # (webui/stats.py's _THUMB_RE, webui/data.py, scripts/assemble_video.py,
    # generate_seo.py all parse/generate this same `\d{8}_\d{6}` shape) --
    # not worth touching all of those just to shave off what's normally a
    # sub-second wait here.
    while os.path.exists(out_path):
        time.sleep(0.05)
        ts       = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(ASSETS_DIR, f"thumb_{theme_name}_{ts}.jpg")

    print(f"[THUMB] {theme_name} | '{short_title}' | {duration} | layout={layout}/{side}")

    base_img = _build_bg(theme_name, seed)
    base_img = _apply_bloom(base_img)
    base_img = _add_theme_fx(base_img, theme_name, rng)
    base_img = _apply_vignette(base_img, strength=0.44)
    base_img = _apply_film_grain(base_img, seed)
    base_img = _draw_duration_badge(base_img, theme_name, duration)

    c = THEMES[theme_name]

    # Legibility-guarded card draw: try the selected layout at increasing
    # card-background opacity; if it still fails the small-preview contrast
    # check, fall back to the centered layout with a forced near-black
    # (highest-contrast) card background rather than silently shipping an
    # unreadable thumbnail. The scene silhouette is placed first each attempt,
    # into the slot opposite whichever (layout, side) that attempt uses, and
    # is checked against that attempt's real card geometry (via
    # `_card_geometry`) before a single scene pixel is drawn -- so it can
    # never end up behind/under the text card.
    attempts = [
        (layout,     side, 155, False),
        (layout,     side, 205, False),
        (layout,     side, 240, False),
        ("centered", "left", 245, True),
    ]
    img = None
    for i, (lyt, sd, alpha, solid_dark) in enumerate(attempts):
        candidate = base_img.copy()
        measure_draw = ImageDraw.Draw(candidate, "RGBA")
        geom = _card_geometry(measure_draw, theme_name, short_title, duration, lyt, sd)
        pending_card_bbox = (
            geom["card_x"], geom["card_y"],
            geom["card_x"] + geom["card_w"], geom["card_y"] + geom["card_h"],
        )
        candidate, _scene_bbox = _draw_scene_silhouette(
            candidate, theme_name, lyt, sd, variant, rng, avoid_bbox=pending_card_bbox,
        )
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

    bright_ok, mean_luma = _check_brightness(img)
    if not bright_ok:
        print(f"[THUMB] brightness check out of band (mean_luma={mean_luma:.1f}, "
              f"expected {_MIN_MEAN_LUMA}-{_MAX_MEAN_LUMA}) -- shipping best effort")

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
