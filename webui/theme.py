"""
theme.py — "Lofi Studio" design system for the Lo-fi Factory panel.

A warm, cozy creator-studio look: deep plum-charcoal background with an amber
glow, cream text, a persistent left sidebar, a "Now Rendering" hero, glass-warm
stat + library cards, and an animated waveform. Call ``apply()`` per page.

Design tokens live here so app.py never has to know a raw hex code, a magic
pixel value, or reinvent a card/row/nav pattern -- it only ever reaches for a
named class or a helper function. See DESIGN.md for the full spec.
"""
from __future__ import annotations

import colorsys
from contextlib import contextmanager

from nicegui import ui

# ── Base palette ─────────────────────────────────────────────────────────────
# The five hues the whole app is built from. Each one is also the seed for a
# generated 12-step scale (see "Graduated color scales" below) -- these flat
# constants stay around as the "step 9 / solid" shade for call sites that just
# want *the* brand color (e.g. an echarts series color, which can't reach into
# CSS custom properties).
PRIMARY = "#e8a45c"    # warm amber — primary CTAs
SECONDARY = "#b6a6e0"  # dusty lavender — secondary
TEAL = "#6fcaa8"       # positive / healthy / live-good
ROSE = "#e8849a"       # negative / stop
INFO = "#8fb8e8"
MUTED = "#a89db5"      # de-emphasized text (chart axes, timestamps, hints)
BG = "#15121c"
SURFACE = "#211b2b"

CARD = "studio-card w-full"
H = "studio-h"
SUB = "studio-sub"
LOG = "studio-log w-full"


# ── Graduated color scales (Radix-ui/colors *methodology*, own hues) ────────
# radix-ui/colors (MIT) generates 12 perceptually-graduated, contrast-aware
# steps per hue: 1-2 app-background tints, 3-5 component backgrounds, 6-8
# borders, 9-10 the solid/brand color, 11-12 accessible text. We adapt that
# *method* -- not their literal hex values, which are tuned for Radix's own
# base hues -- to this app's amber/lavender/teal/rose/info, generated from a
# single base hex by walking the same hue through a dark-theme-appropriate
# lightness/saturation curve. This is what lets call sites pick a
# contrast-appropriate step per use case (subtle background vs. border vs.
# text) instead of the old approach of reusing one flat hex at full opacity
# everywhere.
_SCALE_CURVE: list[tuple[float | None, float]] = [
    (0.12, 0.55),  # 1  app-bg tint
    (0.16, 0.60),  # 2  subtle bg
    (0.21, 0.68),  # 3  component bg
    (0.27, 0.75),  # 4  hovered component bg
    (0.33, 0.80),  # 5  active component bg
    (0.40, 0.85),  # 6  subtle border
    (0.48, 0.90),  # 7  border
    (0.56, 0.95),  # 8  strong border / focus ring
    (None, 1.00),  # 9  solid / base brand color (uses the real base L, S)
    (None, 0.92),  # 10 solid hover/pressed
    (0.72, 0.70),  # 11 low-contrast accessible text
    (0.90, 0.35),  # 12 high-contrast accessible text
]


def _hex_to_hsl(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hue, lightness, sat = colorsys.rgb_to_hls(r, g, b)
    return hue, sat, lightness


def _hsl_to_hex(hue: float, sat: float, lightness: float) -> str:
    r, g, b = colorsys.hls_to_rgb(hue, lightness, sat)
    return "#%02x%02x%02x" % tuple(round(max(0.0, min(1.0, c)) * 255) for c in (r, g, b))


def generate_scale(base_hex: str) -> dict[int, str]:
    """Generate a 12-step graduated color scale from a single base hex.

    Keeps the base hue constant and rides a lightness/saturation curve tuned
    for this app's dark background: steps rise from near-invisible background
    tints (1-2) through component fills and borders (3-8) to the original
    brand color (9, exact input hex) and finally to accessible text shades
    (11-12). See ``_SCALE_CURVE`` for the per-step targets.
    """
    hue, sat, lightness = _hex_to_hsl(base_hex)
    scale: dict[int, str] = {}
    for step, (l_target, s_mult) in enumerate(_SCALE_CURVE, start=1):
        if step == 9:
            scale[step] = base_hex.lower()
        elif step == 10:
            scale[step] = _hsl_to_hex(hue, min(sat * s_mult, 1.0), max(lightness - 0.05, 0.05))
        else:
            scale[step] = _hsl_to_hex(hue, min(sat * s_mult, 1.0), l_target)
    return scale


SCALES: dict[str, dict[int, str]] = {
    "amber": generate_scale(PRIMARY),
    "lavender": generate_scale(SECONDARY),
    "teal": generate_scale(TEAL),
    "rose": generate_scale(ROSE),
    "info": generate_scale(INFO),
}


def scale(hue: str, step: int) -> str:
    """Look up one step (1-12) of a generated hue scale, e.g. ``scale("amber", 11)``."""
    return SCALES[hue][step]


def _generate_css() -> str:
    """Build the `--{hue}-{step}` custom properties and `.text-*`/`.bg-*`/
    `.border-*` utility classes for every step of every generated scale."""
    lines = ["  /* generated 12-step scales */"]
    for hue_name, steps in SCALES.items():
        for step, hexv in steps.items():
            lines.append(f"  --{hue_name}-{step}:{hexv};")
    root_vars = "\n".join(lines)

    util_lines = []
    for hue_name, steps in SCALES.items():
        for step in steps:
            util_lines.append(
                f".text-{hue_name}-{step}{{color:var(--{hue_name}-{step});}}"
                f".bg-{hue_name}-{step}{{background:var(--{hue_name}-{step});}}"
                f".border-{hue_name}-{step}{{border-color:var(--{hue_name}-{step});}}"
            )
    utils = "\n".join(util_lines)
    return root_vars, utils


_ROOT_SCALE_VARS, _SCALE_UTILS = _generate_css()

_CSS = """
:root{
  --bg:#15121c; --bg2:#1b1626; --sidebar:#100d16;
  --surface:rgba(40,32,54,0.66); --surface2:rgba(54,44,72,0.7);
  --border:rgba(232,164,92,0.16); --border2:rgba(182,166,224,0.18);
  --amber-wash:rgba(232,164,92,0.08);
  --text:#f3ede2; --muted:#a89db5;
  --amber:#e8a45c; --lav:#b6a6e0; --teal:#6fcaa8; --rose:#e8849a; --info:#8fb8e8;

  /* ── 4/8pt spacing scale, sized around this app's real hardcoded paddings
     (card 20/22, hero 22/24, stat 16/18) so tokens replace values already in
     use rather than inventing new ones. ── */
  --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px;
  --space-5:20px; --space-6:24px; --space-7:32px; --space-8:40px;

""" + _ROOT_SCALE_VARS + """
}
body,.q-page,.nicegui-content,.q-tab__label,.q-btn__content,.q-field,.q-item,
input,button,textarea,select,h1,h2,h3,h4,p,span,div,label{
  font-family:'Inter',system-ui,sans-serif;
}
.q-icon,.material-icons,.material-symbols-outlined,.notranslate{
  font-family:'Material Icons' !important;
}
body,.q-page,.nicegui-content{
  background:
    radial-gradient(1200px 600px at 8% -10%, rgba(232,164,92,0.13), transparent 58%),
    radial-gradient(1000px 620px at 108% 4%, rgba(182,166,224,0.10), transparent 55%),
    var(--bg) !important;
  color:var(--text);
}

/* ── Type scale: display / h1 / h2 / body / label / caption ─────────────────
   Formal roles replacing the old 4 informal classes; studio-h/studio-sub/
   stat-num/stat-lbl are kept as aliases (same rule) so existing call sites
   don't need churn while new code reaches for the named role. ── */
.text-display,.stat-num{ font-size:1.7rem; font-weight:780; line-height:1.1; color:var(--text); }
.text-h1{ font-size:1.35rem; font-weight:760; line-height:1.2; color:var(--text); }
.text-h2,.studio-h{ font-size:1.02rem; font-weight:680; line-height:1.3; color:var(--text); }
.text-body{ font-size:.875rem; font-weight:500; line-height:1.5; color:var(--text); }
.text-label,.stat-lbl{ font-size:.72rem; font-weight:650; color:var(--muted);
  text-transform:uppercase; letter-spacing:1px; line-height:1.3; }
.text-caption,.studio-sub{ font-size:.8rem; font-weight:500; color:var(--muted); line-height:1.45; }

/* ── Semantic color-role text utilities (step 9 = the flat brand hex) ──────── */
.text-amber{ color:var(--amber-9); } .text-lavender{ color:var(--lavender-9); }
.text-teal{ color:var(--teal-9); } .text-rose{ color:var(--rose-9); }
.text-info{ color:var(--info-9); } .text-muted{ color:var(--muted); }
""" + _SCALE_UTILS + """

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
.studio-sidebar{
  background:linear-gradient(180deg,#15101e,#100d16) !important;
  border-right:1px solid var(--border); width:230px;
}
.appbar-mobile{ background:var(--sidebar) !important; border-bottom:1px solid var(--border); }
.studio-brand{ font-weight:800; letter-spacing:.5px; font-size:1.05rem; }
.nav-item{
  display:flex; align-items:center; gap:12px; padding:10px 14px; border-radius:12px;
  color:var(--muted); cursor:pointer; font-weight:550; transition:all .15s; user-select:none;
}
.nav-item:hover{ background:rgba(255,255,255,0.04); color:var(--text); }
.nav-item.active{
  background:linear-gradient(100deg,rgba(232,164,92,0.20),rgba(182,166,224,0.10));
  color:var(--text); box-shadow:inset 0 0 0 1px var(--border);
}
.nav-item .q-icon{ font-size:20px; }

/* ── Cards ───────────────────────────────────────────────────────────────── */
.studio-card{
  background:var(--surface) !important; border:1px solid var(--border2);
  border-radius:20px; padding:var(--space-5) var(--space-6);
  box-shadow:0 14px 40px rgba(0,0,0,0.38), inset 0 1px 0 rgba(255,255,255,0.04);
  backdrop-filter:blur(12px);
}
/* tone modifiers for theme.card(tone=...) -- e.g. a "connect your account"
   nudge banner -- instead of a one-off inline background style() bypass. */
.studio-card--amber{ background:var(--amber-wash) !important; }

/* ── Hero "Now Rendering" ────────────────────────────────────────────────── */
.hero{
  background:
    radial-gradient(700px 220px at 0% 0%, rgba(232,164,92,0.14), transparent 60%),
    var(--surface) !important;
  border:1px solid var(--border); border-radius:24px; padding:var(--space-6) var(--space-6);
  box-shadow:0 18px 50px rgba(0,0,0,0.42);
}
.hero-art{
  width:148px; height:148px; border-radius:18px; object-fit:cover;
  box-shadow:0 10px 28px rgba(0,0,0,0.5); border:1px solid rgba(255,255,255,0.08);
}
.hero-art-empty{
  display:flex; align-items:center; justify-content:center;
  background:linear-gradient(135deg,#2a2238,#1c1726); font-size:46px;
}

/* ── Stat cards ──────────────────────────────────────────────────────────── */
.stat{
  background:var(--surface) !important; border:1px solid var(--border2);
  border-radius:18px; padding:var(--space-4) var(--space-5); min-width:0;
}

/* ── Library cards ───────────────────────────────────────────────────────── */
.libcard{
  position:relative; border-radius:16px; overflow:hidden; cursor:pointer;
  transition:transform .16s, box-shadow .16s;
  border:1px solid var(--border2); background:var(--surface);
}
.libcard:hover{ transform:translateY(-3px); box-shadow:0 16px 34px rgba(0,0,0,0.5); }
.libcard img{ width:100%; aspect-ratio:16/9; object-fit:cover; display:block; }
.libcard .meta{ padding:8px 12px; }
.libcard .meta .t{ font-size:.82rem; font-weight:600; color:var(--text);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.libcard .meta .d{ font-size:.7rem; color:var(--muted); }
.libcard-media{ position:relative; }
.libcard-del{ position:absolute; top:6px; right:6px; background:rgba(20,14,26,0.55); }

/* ── Detail-dialog player (image/video/iframe share the same frame look) ──── */
.detail-media{ width:100%; border-radius:14px; border:0; }

/* ── Inline code/value chip (redirect URIs, IDs, etc.) ──────────────────── */
.code-chip{ background:rgba(0,0,0,.35); padding:3px 8px; border-radius:8px; }

/* ── Loose list rows (Samples tracks/visuals -- title+meta stacked above a
   media player, unlike the flat-column .data-row pseudo-table) ──────────── */
.list-row{ padding:10px 4px; border-bottom:1px solid rgba(255,255,255,0.06); }
.sample-audio{ width:100%; height:32px; }
.sample-video{ width:100%; border-radius:12px; }

/* ── Waveform (animated) ─────────────────────────────────────────────────── */
.wave{ display:flex; align-items:center; gap:3px; height:34px; }
.wave i{ width:3px; border-radius:3px; background:linear-gradient(var(--amber),var(--lav));
  animation:wv 1s ease-in-out infinite; }
@keyframes wv{ 0%,100%{ height:6px; opacity:.5 } 50%{ height:30px; opacity:1 } }
.wave.paused i{ animation-play-state:paused; height:6px; opacity:.35; }

/* ── Pills / chips ───────────────────────────────────────────────────────── */
.pill{ border-radius:999px; padding:3px 12px; font-size:.76rem; font-weight:650;
  border:1px solid rgba(255,255,255,0.10); background:rgba(0,0,0,0.22); }

/* ── Data rows (pseudo-table) ────────────────────────────────────────────── */
/* Shared implementation for theme.data_row() -- replaces the column-width
   pattern (ui.row().style("min-width:...px")) independently reinvented across
   Runs/Analytics/A-B-testing lists. .table-scroll makes the wrapping
   container scroll horizontally on narrow viewports instead of clipping. */
.table-scroll{ overflow-x:auto; }
.data-row{ display:flex; align-items:center; gap:12px; flex-wrap:nowrap;
  padding:6px 4px; border-bottom:1px solid rgba(255,255,255,0.06); }
.data-row--header{ opacity:.6; padding:4px; }
.col-xs{ min-width:60px; } .col-sm{ min-width:80px; } .col-md{ min-width:100px; }
.col-lg{ min-width:140px; } .col-xl{ min-width:220px; }
.col-grow{ flex:2; min-width:220px; }

/* ── Buttons ─────────────────────────────────────────────────────────────── */
.q-btn{ border-radius:13px; text-transform:none; font-weight:650; letter-spacing:.2px; padding:7px 18px; }
.q-btn.bg-primary{ background:linear-gradient(135deg,#f0b56e,#e08a3c) !important;
  color:#231a10 !important; box-shadow:0 8px 22px rgba(232,164,92,0.34); }
.q-btn.bg-secondary{ background:rgba(182,166,224,0.92) !important; color:#1e1730 !important; }

/* ── Log ─────────────────────────────────────────────────────────────────── */
.studio-log{ background:#0d0b13 !important; border:1px solid var(--border2);
  border-radius:14px; font-family:'JetBrains Mono',ui-monospace,monospace !important;
  font-size:11.5px; color:#c9f3df; }

/* progress bar tint */
.q-linear-progress{ border-radius:999px; }
.q-field__control{ border-radius:12px !important; }
"""

_HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
"""


def apply() -> None:
    ui.dark_mode(True)
    ui.colors(primary=PRIMARY, secondary=SECONDARY, accent=PRIMARY,
              positive=TEAL, negative=ROSE, info=INFO, dark=BG)
    ui.add_head_html(_HEAD)
    ui.add_css(_CSS)


def _card_classes(classes: str, tone: str | None) -> str:
    """Pure helper: compose theme.card()'s wrapper class string. Split out
    from card() itself so the tone-modifier and width-override logic is
    unit-testable without a live NiceGUI client/page context.

    Defaults to full width (matching the old hand-rolled "studio-card w-full"
    call sites) unless the caller's own ``classes`` already specify a width
    (``w-*``/``max-w-*``, e.g. a dialog that wants a fixed ``w-96``) -- avoids
    emitting a redundant/conflicting ``w-full`` alongside an explicit width.
    """
    tone_cls = f" studio-card--{tone}" if tone else ""
    tokens = classes.split()
    has_width = any(t == "w-full" or t.startswith("w-") or t.startswith("max-w-") for t in tokens)
    width_cls = "" if has_width else " w-full"
    extra = f" {classes}" if classes else ""
    return f"studio-card{width_cls}{tone_cls}{extra}"


@contextmanager
def card(title: str | None = None, subtitle: str | None = None, classes: str = "",
         tone: str | None = None):
    """A studio-card wrapper. ``tone`` selects a background modifier (currently
    ``"amber"``, a subtle brand-tinted wash for nudge/notice banners) instead
    of a one-off inline ``.style("background:...")`` bypass -- add more tones
    in ``_CSS`` (``.studio-card--<tone>``) as they're needed.
    """
    with ui.element("div").classes(_card_classes(classes, tone)) as el:
        if title:
            ui.label(title).classes(H)
        if subtitle:
            ui.label(subtitle).classes(SUB)
        yield el


def waveform(bars: int = 26, paused: bool = False):
    cls = "wave paused" if paused else "wave"
    html = "".join(
        f'<i style="animation-delay:{(i % 13) * 0.07:.2f}s"></i>' for i in range(bars)
    )
    return ui.html(f'<div class="{cls}">{html}</div>')


# ── Data row (pseudo-table) ──────────────────────────────────────────────────
_COL_WIDTHS = {"xs", "sm", "md", "lg", "xl", "grow"}


def _data_row_cells(cells: list[dict], *, header: bool = False) -> list[dict]:
    """Pure helper: turn a data_row() cell spec into concrete kind/value/classes
    triples. Split out from data_row() so the column-width mapping and cell
    resolution is unit-testable without a live NiceGUI client/page context.

    Each input cell may have: ``text`` (str) or ``icon`` (str, a Material icon
    name -- mutually exclusive with ``text``), ``width`` (one of
    ``_COL_WIDTHS`` or ``None``), ``classes`` (extra classes, default
    ``text-body`` or ``text-label`` when ``header``, ignored for icon cells),
    ``color`` (extra color-utility class, e.g. ``"text-rose"``).
    """
    default_text_cls = "text-label" if header else "text-body"
    resolved = []
    for cell in cells:
        width = cell.get("width")
        if width is not None and width not in _COL_WIDTHS:
            raise ValueError(f"Unknown data_row width {width!r}, expected one of {_COL_WIDTHS}")
        width_cls = f"col-{width}" if width else ""
        is_icon = "icon" in cell
        default_cls = "" if is_icon else default_text_cls
        classes = " ".join(filter(None, [
            cell.get("classes", default_cls),
            cell.get("color", ""),
            width_cls,
        ]))
        value = cell["icon"] if is_icon else cell.get("text", "")
        resolved.append({"kind": "icon" if is_icon else "text", "value": value, "classes": classes})
    return resolved


def data_row(cells: list[dict], *, header: bool = False, on_click=None, classes: str = "",
             extra=None):
    """One row of a lightweight pseudo-table: fixed-width label (or icon)
    columns laid out in a flex row, replacing the
    ``ui.row().style("min-width:...")`` pattern that was independently
    reinvented (with divergent pixel values) across the Runs history,
    Analytics pillar/per-video tables, and the A/B thumbnail-swap list. Wrap
    the containing column in ``.table-scroll`` so columns scroll horizontally
    on narrow viewports instead of clipping.

    :param cells: list of ``{"text": str, "width": "xs"|"sm"|"md"|"lg"|"xl"|"grow"|None,
        "classes": str, "color": str}`` (or ``"icon"`` instead of ``"text"``)
    :param header: use the dimmer header styling + label type role
    :param on_click: optional click handler (row becomes a button-ish, hoverable target)
    :param classes: extra classes on the row itself
    :param extra: optional zero-arg callable invoked inside the row after the
        cells, for trailing widgets a plain label/icon can't express (e.g. a
        per-row "View" button)
    """
    row_classes = "data-row" + (" data-row--header" if header else "")
    if on_click:
        row_classes += " cursor-pointer"
    if classes:
        row_classes += f" {classes}"
    with ui.row().classes(row_classes) as row:
        for resolved in _data_row_cells(cells, header=header):
            if resolved["kind"] == "icon":
                ui.icon(resolved["value"]).classes(resolved["classes"])
            else:
                ui.label(resolved["value"]).classes(resolved["classes"])
        if extra:
            extra()
    if on_click:
        row.on("click", on_click)
    return row
