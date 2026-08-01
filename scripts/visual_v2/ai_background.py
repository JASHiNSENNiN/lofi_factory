"""
ai_background.py — Pollinations.ai-powered cozy scene background generator.

Strategy for an undetectable faceless lo-fi channel:
  1. ZERO humans in prompts — empty rooms, nature, objects only
  2. Three scene types per theme (interior / exterior / closeup) rotated by seed
  3. Painterly post-processing pipeline that strips AI sheen:
       desaturate → Kuwahara-approx (cel-shading) → ink edge darkening
       → paper grain → warm grade → selective blur foreground
  4. Every animated overlay (vinyl, EQ, now-playing, orbs) sits on top —
     UI elements dominate the frame so any residual AI artifact is buried

Caches to visuals/bg_scenes/{theme}_{variant}.png — one API call per variant.
"""

import os
import math
import random
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw

_ROOT      = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_DIR = os.path.join(_ROOT, "visuals", "bg_scenes")
os.makedirs(_CACHE_DIR, exist_ok=True)

from .config import W as _W, H as _H

# ── Shared suffix appended to every prompt ───────────────────────────────────
_NO_HUMANS = (
    " The room is empty, quiet, and undisturbed — nobody is present, no occupants, "
    "completely uninhabited. Only objects, furniture, and environment. "
    "Deserted, solitary, still-life scene. No living beings of any kind."
)

_STYLE = (
    " Hand-painted anime background illustration style — cel-shading, painterly "
    "brushstrokes, soft warm colour palette, natural imperfections. "
    "No text, no UI elements, no overlays, no watermarks. "
    "Wide 16:9 cinematic composition. Shallow depth of field, background bokeh. "
    "Natural wear and aged textures — not plastic-looking, not CG render."
)

# ── Per-theme scene bank ───────────────────────────────────────────────────────
# Three variants per theme: [interior, exterior, closeup]
# Rotated by visual_seed % 3 so different seeds produce different scenes.

_SCENES = {
    "cozy_rain": [
        # interior
        "A cozy wooden study room at night with rain streaming down a large window. "
        "Warm amber desk lamp illuminates a cluttered desk: open books, a steaming mug "
        "of tea, scattered papers, a small succulent plant. Bookshelves line the walls. "
        "Fireplace glowing softly in the background. Rain patters on the glass.",

        # exterior
        "A cobblestone alleyway at night in gentle rain. Warm lamppost glow reflects "
        "in puddles. Ivy-covered stone walls. A wooden bench under an awning. "
        "Flower boxes on windowsills. Blurry bokeh city lights in the background. "
        "Peaceful, romantic, quiet.",

        # closeup
        "Close-up still life: an open sketchbook on a wooden desk, a steaming cup "
        "of tea beside it, droplets of rain on the window behind. Warm candlelight. "
        "A small potted fern. Pencil shavings. Cosy and intimate."
    ],

    "midnight_cafe": [
        # interior
        "A late-night café interior, closed and quiet. Pendant lights dimmed low. "
        "Wooden tables with unlit candles and small vases of wildflowers. "
        "A chalkboard menu on the wall. Bookshelves behind the counter. "
        "Rain-streaked window showing a quiet midnight street. Cosy and warm.",

        # exterior
        "A narrow Tokyo side street at midnight. A tiny café with a warm glowing "
        "window and a hand-lettered sign. Potted plants by the doorway. "
        "Rain-wet cobblestones reflecting neon signs in the distance. "
        "A bicycle leaned against the wall. Still and peaceful.",

        # closeup
        "Close-up: a ceramic coffee cup on a wooden café table, steam rising gently. "
        "A dog-eared paperback beside it. Soft warm light from a candle. "
        "Raindrops on the window. A small succulent in a clay pot. Moody and intimate."
    ],

    "purple_dusk": [
        # interior
        "A bedroom at purple dusk. Large window with gradient sky — deep indigo fading "
        "to soft lavender — first stars appearing. Desk with a glowing purple lamp, "
        "crystals, an open sketchbook. Fairy lights strung across the ceiling. "
        "Potted plants on the windowsill. Dreamy and serene.",

        # exterior
        "A hilltop meadow at purple dusk. Tall grass swaying gently. A single ancient "
        "oak tree silhouetted against a purple-pink gradient sky. Fireflies beginning "
        "to glow in the grass below. A wooden fence in the mid-ground. "
        "Soft bokeh in the foreground. Magical and serene.",

        # closeup
        "Close-up: a crystal ball on a velvet cloth, reflecting the purple twilight "
        "sky. Dried lavender bundles and small amethyst stones arranged around it. "
        "Soft candlelight. Mystical and cosy."
    ],

    "amber_night": [
        # interior
        "A cosy attic study at night with slanted wooden beams. Vintage amber desk "
        "lamp casting rich golden light on a mahogany desk with scattered papers "
        "and a cup of pencils. Old leather-bound books on shelves. A round porthole "
        "window with a deep amber moon outside. Warm and literary.",

        # exterior
        "A country road at amber dusk, lit by warm lanterns mounted on wooden posts. "
        "Autumn wheat fields stretch to the horizon. A stone bridge over a quiet "
        "stream. The sky is a deep amber and burnt orange. "
        "Fireflies near the water. Nostalgic and golden.",

        # closeup
        "Close-up: a leather journal open on a mahogany desk, fountain pen resting "
        "across the page. A brass desk lamp. A cup of bourbon or amber tea. "
        "Old books with gold-spine lettering in the background. "
        "Warm amber light. Rich and scholarly."
    ],

    "winter_snow": [
        # interior
        "A cosy cabin living room in winter. Large window with snow falling outside "
        "and frost on the glass. Inside: a crackling fireplace with orange embers, "
        "a wool blanket on an armchair, hot cocoa on a wooden side table. "
        "Pinecones and candles on the mantelpiece. Soft warm light.",

        # exterior
        "A snowy pine forest path at night. Trees laden with snow, soft blue "
        "moonlight filtering through. Footprints in the fresh snow leading away. "
        "A distant warm cabin window glowing in the trees. "
        "Still, silent, magical.",

        # closeup
        "Close-up: a hand-knitted wool mug cosy on a ceramic mug of hot cocoa, "
        "topped with marshmallows. A frosted window behind. Snowflakes visible "
        "outside. A cinnamon stick. Christmas lights softly bokeh'd in the background."
    ],

    "autumn_study": [
        # interior
        "An autumn study with a large window. Maple trees outside blazing in orange "
        "and red, leaves drifting past the glass. Inside: a reading lamp, a stack "
        "of textbooks, a mug of apple cider, a pressed-leaf collection pinned to "
        "a cork board. Warm light. Cosy and academic.",

        # exterior
        "A tree-lined path in full autumn colour. Red and orange maple leaves "
        "covering the ground and still falling. Warm afternoon light filtering "
        "through the canopy. An old wooden bench beside the path. "
        "Distant forest going soft in bokeh. Peaceful.",

        # closeup
        "Close-up: autumn maple leaves arranged on a wooden windowsill, some "
        "pressed flat, some curled. A steaming mug with a cinnamon stick. "
        "Rain on the window. A candle flickering. A small carved pumpkin nearby."
    ],

    "spring_dawn": [
        # interior
        "A light wooden bedroom at spring dawn. Window opens onto cherry blossoms "
        "in soft pink, morning mist, pale yellow sunrise. Sheer white curtains "
        "drifting in a gentle breeze. A desk with a vase of cherry blossom sprigs, "
        "an open journal, a cup of green tea. Fresh and hopeful.",

        # exterior
        "A Japanese garden at spring dawn. Cherry blossom trees (sakura) in full "
        "bloom, petals drifting on a gentle breeze over a koi pond. Stone lanterns. "
        "Morning mist hanging low over the water. Pale pink and soft gold sky. "
        "Serene and timeless.",

        # closeup
        "Close-up: a white ceramic bowl of matcha tea, cherry blossom petals "
        "floating on the surface. A wooden tray on tatami. A single sakura branch "
        "in a slender vase. Morning light filtering through shoji screens."
    ],

    "neon_tokyo": [
        # interior
        "A Tokyo apartment at night. Floor-to-ceiling window showing neon city "
        "lights — pinks, cyans, purples — in the rain-wet streets far below. "
        "Inside: a dark desk with manga volumes stacked on shelves, a small "
        "neon sign on the wall casting pink light, a vinyl record player. "
        "Moody, vibrant, cinematic.",

        # exterior
        "A rain-drenched Tokyo alley at midnight. Neon signs reflect in puddles — "
        "pink kanji, cyan arrows, purple vending machines. Steam rising from "
        "a grate. Wires strung between buildings. Blurry bokeh of distant traffic. "
        "Cyberpunk but intimate.",

        # closeup
        "Close-up: a vinyl record on a turntable, needle in groove, lit by pink "
        "and cyan neon from a nearby sign. Album cover visible beside it — "
        "abstract geometric design. City rain sounds implied. Dark and cinematic."
    ],

    "summer_lofi": [
        # interior
        "A warm summer bedroom at night. Open window with sheer curtains moving "
        "in a gentle breeze, fireflies visible in the garden outside. "
        "A desk fan on low. A glass of iced lemonade on the desk, open notebook. "
        "Potted plants everywhere. Soft warm lamplight. Lazy and summery.",

        # exterior
        "A firefly meadow on a warm summer night. Hundreds of fireflies glowing "
        "gold and green in tall grass. A wooden dock over a still pond reflecting "
        "the stars. Distant tree line silhouette. Warm and magical.",

        # closeup
        "Close-up: a glass of iced water with lemon and mint on a weathered "
        "wooden porch railing. Fireflies bokeh'd in the garden behind. "
        "A hanging wind chime. Summer evening light. Refreshing and peaceful."
    ],

    "blue_hour": [
        # interior
        "A study room during blue hour — deep twilight after sunset. Everything "
        "bathed in rich indigo light from the window, contrasting with warm amber "
        "desk lamp. Books, a globe, a half-finished coffee. City silhouettes visible "
        "outside. Moody and intellectual.",

        # exterior
        "A city park at blue hour — the deep blue twilight between sunset and night. "
        "Lamp posts just flickering on, reflected in a still pond. Trees silhouetted. "
        "Distant city skyline glowing. Benches empty. Quiet and contemplative.",

        # closeup
        "Close-up: a vintage globe on a dark wooden desk, lit by a single warm "
        "lamp against a deep blue window showing city lights. Old books, a compass, "
        "a half-drunk coffee. Scholarly and atmospheric."
    ],

    "forest_rain": [
        # interior
        "A woodland cabin interior on a rainy day. Large windows overlooking a dense "
        "green forest, rain streaming down. Stone fireplace, wooden furniture, "
        "hanging ferns and moss terrariums. Field notebooks and a pressed-flower "
        "collection on the desk. Earthy and cosy.",

        # exterior
        "A misty forest path in gentle rain. Ancient trees with moss-covered roots. "
        "Raindrops pattering on ferns and leaves. A wooden signpost in the fog. "
        "Soft green and grey light filtering through the canopy. "
        "Quiet, wild, atmospheric.",

        # closeup
        "Close-up: a moss terrarium in a glass jar on a wooden windowsill, tiny "
        "ferns and mushrooms inside. Raindrops on the window behind. "
        "A cup of herbal tea. A field notebook with pressed flowers. "
        "Forest sounds implied. Earthy and peaceful."
    ],

    "sakura_night": [
        # interior
        "A Japanese room (washitsu) at night. Tatami floor, shoji screens glowing "
        "with soft candlelight. A low wooden desk with ink brush and paper. "
        "A small lantern casting warm orange light. Through the open shoji screen, "
        "a moonlit sakura garden with petals drifting in. Serene and traditional.",

        # exterior
        "A moonlit Japanese garden at night. Full cherry blossom tree (sakura) in "
        "bloom, petals floating on a gentle breeze over stone path and lanterns. "
        "A red torii gate in the background. Still koi pond reflecting the moon. "
        "Soft pink and deep navy palette. Magical and timeless.",

        # closeup
        "Close-up: a single sakura branch with blossoms, a few petals fallen on "
        "a dark lacquered tray beside a lit candle. Deep navy background. "
        "Moonlight from a window. A small ceramic sake cup. "
        "Japanese aesthetic, minimal and beautiful."
    ],

    "vaporwave": [
        # interior
        "A retro 1980s room at night. CRT television glowing with static, VHS tape tower "
        "stacked beside a vintage synthesizer. Pink and cyan neon strip lights behind the "
        "shelves. A cassette player on a wooden desk, a potted cactus, pastel grid poster "
        "on the wall. Dreamy, nostalgic, synthwave aesthetic.",

        # exterior
        "A rain-wet city street at night with a retrowave sunset gradient — magenta fading "
        "to deep purple — reflected in puddles. A geometric grid stretches into the horizon. "
        "Palm trees silhouetted. Distant neon signs. Dreamy vaporwave aesthetic, painterly.",

        # closeup
        "Close-up: a VHS cassette tape on a pastel grid surface, label peeling at the corner. "
        "A Walkman beside it, headphones coiled. Pink and cyan neon light reflected in the "
        "tape window. Retro 80s aesthetic, nostalgic and dreamy.",
    ],

    "lofi_house": [
        # interior
        "A dark urban loft apartment at night. Floor-to-ceiling windows show glittering "
        "city lights below. Inside: concrete walls, a record player spinning, blue-tinted "
        "LED strip lighting under the shelves, a leather chair. Minimal, modern, atmospheric.",

        # exterior
        "A rooftop terrace in a city at night. String lights overhead, city skyline glowing "
        "below. A low table with drinks and vinyl records. Deep blue urban sky. Warm and "
        "intimate against the cool city backdrop. Lo-fi urban aesthetic.",

        # closeup
        "Close-up: a vinyl record spinning on a turntable, electric blue light reflecting "
        "off the grooves. City lights blurred behind the window. A glass of iced water. "
        "Dark and atmospheric, urban night energy.",
    ],

    "lofi_classical": [
        # interior
        "A grand home library at night. Floor-to-ceiling bookshelves, a grand piano visible "
        "through an open door. A reading desk with a brass lamp casting golden light over "
        "sheet music and an open score. Deep navy walls, Persian rug. Refined and scholarly.",

        # exterior
        "A moonlit European courtyard with baroque architecture. Stone arches, ivy-covered "
        "walls, a fountain silent in the dark. Warm light from a tall window. A stone bench "
        "below a carved balcony. Timeless, elegant, deeply quiet.",

        # closeup
        "Close-up: sheet music open on a music stand, handwritten annotations in pencil. "
        "A reed pen beside it, a candle flickering. Dark wood background. A metronome "
        "frozen mid-tick. Scholarly and intimate.",
    ],

    "bedroom_pop": [
        # interior
        "A cosy bedroom studio at golden hour. Fairy lights strung across the ceiling, "
        "a ukulele leaned against the wall, a bulletin board with photos and handwritten "
        "lyrics pinned up. Warm afternoon light through sheer curtains. Plants on the "
        "windowsill. DIY, intimate, indie aesthetic.",

        # exterior
        "A sunny suburban backyard in late afternoon. A hammock strung between two trees, "
        "books and a lemonade beside it. Flowers in bloom. Soft golden light filtering "
        "through leaves. A wind chime. Gentle and carefree.",

        # closeup
        "Close-up: a handwritten notebook open to song lyrics, a pencil eraser beside it. "
        "A warm mug of chamomile tea. Fairy lights soft bokeh in the background. "
        "Stickers on the notebook cover. DIY indie warmth.",
    ],

    "lofi_rnb": [
        # interior
        "A warm urban apartment in the evening. Brick walls, a turntable on a wooden shelf, "
        "soul records in a crate below. Amber pendant lights casting a golden glow. "
        "A leather sofa, a saxophone in the corner. Soulful and intimate.",

        # exterior
        "A city block at dusk in a warm neighbourhood. Brownstone steps, a barbershop sign "
        "glowing amber, music drifting from an open window. Warm orange-gold light on "
        "brick facades. Pigeons on a wire. Soulful urban evening.",

        # closeup
        "Close-up: a vinyl soul record on a turntable, label spinning slowly. A glass of "
        "amber bourbon on a coaster beside it. Warm lamp light. A saxophone mouthpiece "
        "on the table. Soulful, warm, intimate evening atmosphere.",
    ],
}


# ── Painterly post-processing ──────────────────────────────────────────────────

def _kuwahara_approx(img: Image.Image, radius: int = 4) -> Image.Image:
    """
    Approximate Kuwahara filter using quadrant-variance smoothing.
    Produces the oil-painting / cel-shading effect that makes images look
    hand-illustrated rather than photo-realistic or AI-smooth.

    True Kuwahara is expensive; this uses a 2-pass approach:
      1. Bilateral-style: strong blur → edge-detect → blend
      2. Produces region-preserving smoothing with sharp edges
    """
    arr = np.array(img, dtype=np.float32)
    # Strong smoothing pass
    blurred = np.array(img.filter(ImageFilter.GaussianBlur(radius=radius)), dtype=np.float32)
    # Edge strength map from original
    grey = img.convert("L")
    edges = np.array(grey.filter(ImageFilter.FIND_EDGES()), dtype=np.float32) / 255.0
    edges = np.clip(edges * 3.0, 0, 1)  # amplify edge signal
    edges_3ch = np.stack([edges, edges, edges], axis=2)
    # Blend: use original on edges, blurred on flat areas
    result = arr * edges_3ch + blurred * (1 - edges_3ch)
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


def _ink_edges(img: Image.Image, strength: float = 0.35) -> Image.Image:
    """
    Darken edges slightly to simulate ink linework in anime/illustration.
    Edge pixels are pushed toward the theme's dark colour.
    """
    grey   = img.convert("L")
    edges  = grey.filter(ImageFilter.FIND_EDGES())
    edges  = edges.filter(ImageFilter.GaussianBlur(radius=0.8))  # soften ink lines
    e_arr  = np.array(edges, dtype=np.float32) / 255.0
    e_arr  = np.clip(e_arr * 2.5, 0, 1) * strength  # amplify + scale by strength
    img_arr = np.array(img, dtype=np.float32)
    # Darken toward black proportional to edge strength
    result  = img_arr * (1 - e_arr[:, :, np.newaxis])
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


def _paper_grain(img: Image.Image, strength: float = 6.0) -> Image.Image:
    """
    Add organic paper/canvas grain. Removes the ultra-smooth AI texture.
    Uses structured noise (not pure random) for a more natural feel.
    """
    arr  = np.array(img, dtype=np.float32)
    # Layered noise: fine + coarse for natural paper texture
    fine   = np.random.normal(0, strength,       arr.shape).astype(np.float32)
    coarse = np.random.normal(0, strength * 0.4, arr.shape).astype(np.float32)
    coarse = np.kron(coarse[::3, ::3, :],
                     np.ones((3, 3, 1), dtype=np.float32))[:arr.shape[0], :arr.shape[1], :]
    noise  = fine + coarse
    return Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8))


def _colour_quantize(img: Image.Image, colours: int = 64) -> Image.Image:
    """
    Reduce colour count to simulate hand-painted illustration colour palette.
    Anime art uses far fewer unique colours than AI-generated images.
    Uses PIL quantize with dithering for a natural look.
    """
    q = img.quantize(colors=colours, method=Image.Quantize.MEDIANCUT, dither=0)
    return q.convert("RGB")


def _selective_desaturate(img: Image.Image,
                           amount: float = 0.18,
                           protect_warm: bool = True) -> Image.Image:
    """
    Slightly desaturate the image but protect warm tones (orange/amber/red).
    AI images are often oversaturated; this matches hand-drawn illustration levels.
    protect_warm: boosts saturation in red-orange-yellow hue range instead of cutting.
    """
    hsv = img.convert("HSV") if hasattr(Image, "HSV") else None
    # Fall back to RGB manipulation
    grey = img.convert("L").convert("RGB")
    arr_col  = np.array(img,  dtype=np.float32)
    arr_grey = np.array(grey, dtype=np.float32)
    result = arr_col * (1 - amount) + arr_grey * amount
    if protect_warm:
        # Warm pixel mask: red channel dominant
        warm_mask = ((arr_col[:, :, 0] > arr_col[:, :, 2] + 20) &
                     (arr_col[:, :, 0] > 100)).astype(np.float32)
        warm_mask = warm_mask[:, :, np.newaxis]
        # In warm areas, pull back toward original (less desaturation)
        result = result + arr_col * warm_mask * (amount * 0.5)
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


def _warm_grade(img: Image.Image) -> Image.Image:
    """Push colour temperature warm — matches the lo-fi palette expectation."""
    r, g, b = img.split()
    r = ImageEnhance.Brightness(r).enhance(1.05)
    b = ImageEnhance.Brightness(b).enhance(0.93)
    return Image.merge("RGB", (r, g, b))


def _vignette(img: Image.Image, strength: float = 0.45) -> Image.Image:
    """Dark oval vignette — makes edges feel hand-finished, hides AI corner artifacts."""
    arr = np.array(img, dtype=np.float32)
    ys  = np.linspace(-1, 1, arr.shape[0])[:, np.newaxis]
    xs  = np.linspace(-1, 1, arr.shape[1])[np.newaxis, :]
    vig = 1.0 - strength * np.clip((xs**2 + ys**2), 0, 1)**0.7
    vig = vig[:, :, np.newaxis]
    return Image.fromarray(np.clip(arr * vig, 0, 255).astype(np.uint8))


def _soft_blur(img: Image.Image, sigma: float = 0.7) -> Image.Image:
    """
    Research finding: "never perfectly sharp backgrounds" — a slight blur
    mimics the depth-of-field softness of real anime background art and
    prevents the hyper-sharp AI render look.
    """
    return img.filter(ImageFilter.GaussianBlur(radius=sigma))


# ── Canvas texture (static, generated once) ───────────────────────────────────
_CANVAS_TEXTURE: np.ndarray | None = None

def _get_canvas_texture(w: int, h: int) -> np.ndarray:
    """
    Generate a procedural canvas/paper texture as a (H, W) float32 array [0,1].
    Simulates the woven micro-texture of illustration paper.
    Applied at 12% blend — just enough to feel physical, invisible as texture.
    Cached globally so it's only generated once per process.
    """
    global _CANVAS_TEXTURE
    if _CANVAS_TEXTURE is not None and _CANVAS_TEXTURE.shape == (h, w):
        return _CANVAS_TEXTURE

    rng = np.random.default_rng(seed=42)  # fixed seed = same texture always

    # Layer 1: fine random grain (base paper roughness)
    fine = rng.standard_normal((h, w)).astype(np.float32) * 0.04

    # Layer 2: horizontal fibre weave (canvas threads)
    fibre_h = np.sin(np.arange(h, dtype=np.float32) * 3.7)[:, np.newaxis] * 0.03
    fibre_v = np.sin(np.arange(w, dtype=np.float32) * 5.1)[np.newaxis, :] * 0.03

    # Layer 3: low-frequency paper bump (unevenness of the sheet)
    bump_y = np.linspace(0, math.pi * 4, h, dtype=np.float32)
    bump_x = np.linspace(0, math.pi * 6, w, dtype=np.float32)
    bump   = (np.sin(bump_y)[:, np.newaxis] * np.cos(bump_x)[np.newaxis, :]) * 0.015

    texture = fine + fibre_h + fibre_v + bump
    # Normalise to [0, 1] centred at 0.5
    texture = (texture - texture.min()) / (texture.max() - texture.min() + 1e-8)

    _CANVAS_TEXTURE = texture
    return _CANVAS_TEXTURE


def _canvas_overlay(img: Image.Image, strength: float = 0.12) -> Image.Image:
    """
    Blend the canvas texture onto the image at `strength` opacity using
    multiply-screen combined mode: darkens highs and lightens lows slightly,
    giving a painted-on-canvas feel without obvious darkening.
    """
    arr     = np.array(img, dtype=np.float32) / 255.0
    texture = _get_canvas_texture(img.width, img.height)[:, :, np.newaxis]

    # Soft-light blend: subtle texture without heavy darkening
    # softlight(A, B) = A*(1 - 2B)*A^2 + 2A*B  (simplified)
    blend = arr + (texture - 0.5) * strength * 2
    return Image.fromarray(np.clip(blend * 255, 0, 255).astype(np.uint8))


def make_painterly(img: Image.Image) -> Image.Image:
    """
    Full anti-AI disguise pipeline (research-validated, 9 stages):

      1. Soft background blur         — removes hyper-sharp AI render look
      2. Selective desaturation       — removes AI oversaturation
      3. Kuwahara approximation       — cel-shading / oil-paint regions
      4. Colour quantization          — hand-drawn palette (fewer unique colours)
      5. Ink edge darkening           — simulates linework in anime illustration
      6. Canvas texture overlay       — physical "painted on paper" micro-texture
      7. Per-frame paper grain        — removes AI airbrush smoothness
      8. Warm colour grade            — lo-fi palette: warm reds, cool blues
      9. Vignette                     — hand-finished dark corners, hides AI artifacts
    """
    img = _soft_blur(img, sigma=0.7)
    img = _selective_desaturate(img, amount=0.18)
    img = _kuwahara_approx(img, radius=3)
    img = _colour_quantize(img, colours=80)
    img = _ink_edges(img, strength=0.30)
    img = _canvas_overlay(img, strength=0.12)
    img = _paper_grain(img, strength=5.5)
    img = _warm_grade(img)
    img = _vignette(img, strength=0.42)
    return img


# ── Pollinations.ai API call ───────────────────────────────────────────────────
# API moved to gen.pollinations.ai — free key from https://enter.pollinations.ai
# Set POLLINATIONS_KEY in .env (optional but recommended for higher rate limits).

_POLL_MODELS = [
    "flux",    # FLUX.1-schnell — fast, high quality
    "zimage",  # Z-Image Turbo — fast 6B FLUX with 2× upscaling
]

_POLL_KEY = os.getenv("POLLINATIONS_KEY", "")

def _call_pollinations(prompt: str, seed: int = 42) -> Image.Image:
    import requests
    import time
    from io import BytesIO
    from urllib.parse import quote

    # Encode prompt for URL path — safe='' encodes slashes and all special chars
    encoded = quote(prompt, safe="")
    base_url = f"https://gen.pollinations.ai/image/{encoded}"

    for model in _POLL_MODELS:
        params = {
            "model":   model,
            "width":   1280,
            "height":  720,
            "seed":    seed,
            "enhance": "false",
        }
        if _POLL_KEY:
            params["key"] = _POLL_KEY
        for attempt in range(2):
            try:
                print(f"  [ai_bg] Pollinations model={model} attempt {attempt + 1}/2 (seed={seed})...")
                r = requests.get(base_url, params=params, timeout=120)
                if r.status_code == 200:
                    ct = r.headers.get("content-type", "")
                    if ct.startswith("image/"):
                        return Image.open(BytesIO(r.content))
                    print(f"  [ai_bg]   → 200 but content-type={ct!r}, skipping")
                else:
                    print(f"  [ai_bg]   → HTTP {r.status_code}: {r.text[:120]}")
            except Exception as e:
                print(f"  [ai_bg]   → {type(e).__name__}: {e}")
            if attempt == 0:
                time.sleep(10)
        print(f"  [ai_bg] Model {model} exhausted, trying next...")

    raise RuntimeError("Pollinations.ai: all models failed")


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_bg_scene(theme_name:   str,
                      api_key:      str  = None,
                      force_regen:  bool = False,
                      variant:      int  = 0) -> np.ndarray | None:
    """
    Return (H, W, 3) uint8 RGB array of a cosy AI-painted background scene.

    variant (0/1/2) selects interior / exterior / closeup for the theme.
    Images are cached; call with force_regen=True to regenerate.
    Returns None on failure (caller falls back to gradient background).
    """
    variant = variant % 3
    cache_name = f"{theme_name}_v{variant}.png"
    cache_path = os.path.join(_CACHE_DIR, cache_name)

    if not force_regen and os.path.exists(cache_path):
        print(f"  [ai_bg] Cache hit: {cache_name}")
        img = Image.open(cache_path).convert("RGB")
        return np.array(img.resize((_W, _H), Image.LANCZOS))

    scenes     = _SCENES.get(theme_name, _SCENES["cozy_rain"])
    scene_desc = scenes[variant]
    # Short focused prompt — Pollinations is a diffusion model, not a chat model.
    # Verbose style instructions inflate URL length and hurt routing reliability.
    poll_prompt = (scene_desc +
                   " anime illustration style, painterly brushwork, no people, empty scene, "
                   "16:9 cinematic wide shot, warm cozy lighting, soft depth of field")
    variant_names = ["interior", "exterior", "closeup"]
    print(f"  [ai_bg] Generating '{theme_name}' ({variant_names[variant]}) via Pollinations.ai...")

    try:
        img = _call_pollinations(poll_prompt, seed=variant)
    except Exception as e:
        print(f"  [ai_bg] Generation failed: {e} — falling back to gradient")
        return None

    # Resize → painterly disguise → cache
    img = img.convert("RGB").resize((_W, _H), Image.LANCZOS)
    img = make_painterly(img)
    img.save(cache_path, quality=95)
    print(f"  [ai_bg] Saved: {cache_name}")

    return np.array(img)
