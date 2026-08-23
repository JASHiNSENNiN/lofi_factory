"""
qa_thumbnails.py
----------------
Dev-facing QA tool for generate_thumbnail_cozy.py -- NOT part of the
run.py/publish.py pipeline. Renders every theme (a couple of variants each)
into a single labeled contact-sheet PNG so a generator change can be
eyeballed across the whole theme matrix in one image instead of opening
dozens of files in assets/.

Usage:
    python scripts/qa_thumbnails.py [--variants N] [--out PATH]
"""

import os
import sys
import argparse
import tempfile
import datetime

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.generate_thumbnail_cozy as gtc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(_ROOT, "assets")

_TILE_SCALE = 0.32   # contact-sheet tile size relative to the real 1280x720
_TILE_W = int(gtc.TW * _TILE_SCALE)
_TILE_H = int(gtc.TH * _TILE_SCALE)
_LABEL_H = 22
_PAD = 8


def _sample_titles(theme: str) -> list:
    choices = gtc.TITLE_TEMPLATES.get(theme, gtc.TITLE_TEMPLATES["cozy_rain"])
    return [f"lofi hip hop · {t} — 2 hours" for t in choices]


def build_contact_sheet(variants: int = 2, out_path: str = None) -> str:
    themes = list(gtc.THEMES)
    n_cols = variants
    n_rows = len(themes)

    sheet_w = n_cols * (_TILE_W + _PAD) + _PAD
    sheet_h = n_rows * (_TILE_H + _LABEL_H + _PAD) + _PAD
    sheet = Image.new("RGB", (sheet_w, sheet_h), (18, 18, 22))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(gtc._resolve_title_font(), 14)
    except Exception:
        font = ImageFont.load_default()

    with tempfile.TemporaryDirectory() as tmp_dir:
        orig_assets_dir = gtc.ASSETS_DIR
        gtc.ASSETS_DIR = tmp_dir
        try:
            for row, theme in enumerate(themes):
                titles = _sample_titles(theme)
                for col in range(n_cols):
                    variant = col
                    title = titles[variant % len(titles)]
                    path, _ = gtc.generate_thumbnail(
                        theme_name=theme, duration="2 hours", title=title, variant=variant,
                    )
                    tile = Image.open(path).convert("RGB").resize((_TILE_W, _TILE_H), Image.LANCZOS)
                    x = _PAD + col * (_TILE_W + _PAD)
                    y = _PAD + row * (_TILE_H + _LABEL_H + _PAD)
                    sheet.paste(tile, (x, y))
                    layout = gtc._select_layout(theme, variant)
                    scene  = gtc._select_scene(theme, variant)
                    label  = f"{theme} v{variant} [{layout}/{scene}]"
                    draw.text((x, y + _TILE_H + 2), label, font=font, fill=(220, 220, 220))
        finally:
            gtc.ASSETS_DIR = orig_assets_dir

    if out_path is None:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(ASSETS_DIR, f"qa_contact_sheet_{ts}.png")
    sheet.save(out_path, "PNG")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variants", type=int, default=2,
                         help="variants per theme to render (default: 2)")
    parser.add_argument("--out", type=str, default=None,
                         help="output PNG path (default: assets/qa_contact_sheet_<ts>.png)")
    args = parser.parse_args()

    result_path = build_contact_sheet(variants=args.variants, out_path=args.out)
    print(f"[QA] Contact sheet ({len(gtc.THEMES)} themes x {args.variants} variants) -> {result_path}")
