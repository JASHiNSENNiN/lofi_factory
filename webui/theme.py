"""
theme.py — design system for the Lo-fi Factory control panel.

A dense, flat, technical look: near-black background, monospace throughout,
thin 1px borders, sharp corners, no blur/glow/gradients. This is an ops
console for a pipeline (job status, systemd health, upload analytics) --
viewers of the actual YouTube output never see this UI, so it's built to
read as a monitoring tool, not a branded consumer app.

Design tokens live here so app.py never has to know a raw hex code, a magic
pixel value, or reinvent a card/row/nav pattern -- it only ever reaches for a
named class or a helper function.
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
# Functional, not decorative: a cool technical blue for actions, desaturated
# slate for secondary, and clear/legible status colors -- no warm/"cozy" hues.
PRIMARY = "#3b9eff"    # technical blue — primary CTAs
SECONDARY = "#7c8797"  # slate — secondary
TEAL = "#3ecf8e"       # positive / healthy / live-good
ROSE = "#e5484d"       # negative / stop
INFO = "#22b8cf"
MUTED = "#7a7a85"      # de-emphasized text (chart axes, timestamps, hints)
BG = "#0a0a0c"
SURFACE = "#131316"

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
  --bg:#0a0a0c; --bg2:#0d0d10; --sidebar:#08080a;
  --surface:#131316; --surface2:#1a1a1e;
  --border:#26262b; --border2:#2c2c32;
  --amber-wash:rgba(59,158,255,0.08);
  --text:#e4e4e7; --muted:#7a7a85;
  --amber:#3b9eff; --lav:#7c8797; --teal:#3ecf8e; --rose:#e5484d; --info:#22b8cf;

  /* ── Tight spacing scale -- dense/technical over spacious/"cozy": every
     card/hero/stat rule below reads its padding straight from these, so
     halving them here tightens the whole app without touching app.py. ── */
  --space-1:2px; --space-2:4px; --space-3:6px; --space-4:8px;
  --space-5:10px; --space-6:12px; --space-7:16px; --space-8:20px;

""" + _ROOT_SCALE_VARS + """
}
body,.q-page,.nicegui-content,.q-tab__label,.q-btn__content,.q-field,.q-item,
input,button,textarea,select,h1,h2,h3,h4,p,span,div,label{
  font-family:'JetBrains Mono',ui-monospace,'SF Mono',Consolas,monospace;
}
.q-icon,.material-icons,.material-symbols-outlined,.notranslate{
  font-family:'Material Icons' !important;
}
body,.q-page,.nicegui-content{
  background:var(--bg) !important;
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
  background:var(--sidebar) !important;
  border-right:1px solid var(--border); width:220px;
}
.appbar-mobile{ background:var(--sidebar) !important; border-bottom:1px solid var(--border); }
.studio-brand{ font-weight:700; letter-spacing:.5px; font-size:.95rem; }
.nav-item{
  display:flex; align-items:center; gap:10px; padding:7px 10px; border-radius:3px;
  color:var(--muted); cursor:pointer; font-weight:500; transition:background .1s, color .1s;
  user-select:none; border-left:2px solid transparent;
}
.nav-item:hover{ background:var(--surface2); color:var(--text); }
.nav-item.active{
  background:var(--surface2); color:var(--text); border-left:2px solid var(--amber);
}
.nav-item .q-icon{ font-size:18px; }

/* ── Cards ───────────────────────────────────────────────────────────────── */
.studio-card{
  background:var(--surface) !important; border:1px solid var(--border2);
  border-radius:3px; padding:var(--space-5) var(--space-6);
}
/* tone modifiers for theme.card(tone=...) -- e.g. a "connect your account"
   nudge banner -- instead of a one-off inline background style() bypass. */
.studio-card--amber{ background:var(--amber-wash) !important; }

/* ── Hero "Now Rendering" ────────────────────────────────────────────────── */
.hero{
  background:var(--surface) !important;
  border:1px solid var(--border); border-radius:3px; padding:var(--space-6) var(--space-6);
}
.hero-art{
  width:120px; height:120px; border-radius:3px; object-fit:cover;
  border:1px solid var(--border2);
}
.hero-art-empty{
  display:flex; align-items:center; justify-content:center;
  background:var(--surface2); font-size:.7rem; color:var(--muted); letter-spacing:1px;
}

/* ── Stat cards ──────────────────────────────────────────────────────────── */
.stat{
  background:var(--surface) !important; border:1px solid var(--border2);
  border-radius:3px; padding:var(--space-4) var(--space-5); min-width:0;
}

/* ── Library cards ───────────────────────────────────────────────────────── */
.libcard{
  position:relative; border-radius:3px; overflow:hidden; cursor:pointer;
  transition:border-color .12s;
  border:1px solid var(--border2); background:var(--surface);
}
.libcard:hover{ border-color:var(--amber); }
.libcard img{ width:100%; aspect-ratio:16/9; object-fit:cover; display:block; }
.libcard .meta{ padding:8px 12px; }
.libcard .meta .t{ font-size:.82rem; font-weight:600; color:var(--text);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.libcard .meta .d{ font-size:.7rem; color:var(--muted); }
.libcard-media{ position:relative; }
.libcard-del{ position:absolute; top:6px; right:6px; background:rgba(0,0,0,0.6); }

/* ── Detail-dialog player (image/video/iframe share the same frame look) ──── */
.detail-media{ width:100%; border-radius:3px; border:0; }

/* ── Inline code/value chip (redirect URIs, IDs, etc.) ──────────────────── */
.code-chip{ background:rgba(0,0,0,.4); padding:3px 8px; border-radius:3px; }

/* ── Loose list rows (Samples tracks/visuals -- title+meta stacked above a
   media player, unlike the flat-column .data-row pseudo-table) ──────────── */
.list-row{ padding:10px 4px; border-bottom:1px solid var(--border); }
.sample-audio{ width:100%; height:32px; }
.sample-video{ width:100%; border-radius:3px; }

/* ── Pills / chips ───────────────────────────────────────────────────────── */
.pill{ border-radius:3px; padding:2px 8px; font-size:.72rem; font-weight:650;
  border:1px solid var(--border2); background:var(--bg2); letter-spacing:.5px; }

/* ── Data rows (pseudo-table) ────────────────────────────────────────────── */
/* Shared implementation for theme.data_row() -- replaces the column-width
   pattern (ui.row().style("min-width:...px")) independently reinvented across
   Runs/Analytics/A-B-testing lists. .table-scroll makes the wrapping
   container scroll horizontally on narrow viewports instead of clipping. */
/* Right-edge fade hints there's more to see without needing to already know
   to swipe -- narrow/mobile viewports routinely clip data-row's later
   columns (confirmed 2026-08-16: a failed job's reason column was fully
   present in the DOM and scrollable, just invisible with no affordance
   hinting that). Always-on rather than JS-gated on actual overflow -- on a
   row that doesn't overflow this just fades into nothing, harmless. */
.table-scroll{ overflow-x:auto; position:relative; }
.table-scroll::after{
  content:""; position:absolute; top:0; right:0; bottom:0; width:20px;
  background:linear-gradient(to right, transparent, var(--surface));
  pointer-events:none;
}
.data-row{ display:flex; align-items:center; gap:12px; flex-wrap:nowrap;
  padding:4px 4px; border-bottom:1px solid var(--border); }
.data-row--header{ opacity:.6; padding:4px; }
.col-xs{ min-width:60px; } .col-sm{ min-width:80px; } .col-md{ min-width:100px; }
.col-lg{ min-width:140px; } .col-xl{ min-width:220px; }
.col-grow{ flex:2; min-width:220px; }

/* ── Buttons ─────────────────────────────────────────────────────────────── */
.q-btn{ border-radius:3px; text-transform:none; font-weight:600; letter-spacing:.2px; padding:6px 14px; }
.q-btn.bg-primary{ background:var(--amber) !important; color:#0a0a0c !important; }
.q-btn.bg-secondary{ background:var(--lav) !important; color:#0a0a0c !important; }

/* ── Log ─────────────────────────────────────────────────────────────────── */
.studio-log{ background:#000 !important; border:1px solid var(--border2);
  border-radius:3px; font-family:'JetBrains Mono',ui-monospace,monospace !important;
  font-size:11.5px; color:#9fe8bd; }

/* progress bar / field radius */
.q-linear-progress{ border-radius:0; }
.q-field__control{ border-radius:3px !important; }

/* file pickers: no empty file-list box under the header */
.compact-upload{ background:transparent !important; }
.compact-upload .q-uploader__list{ min-height:0; padding:0; }
.compact-upload .q-uploader__subtitle{ display:none; }
"""

_HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700;800&display=swap" rel="stylesheet">
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
