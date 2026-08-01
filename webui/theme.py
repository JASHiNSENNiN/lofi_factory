"""
theme.py — "Lofi Studio" design system for the Lo-fi Factory panel.

A warm, cozy creator-studio look: deep plum-charcoal background with an amber
glow, cream text, a persistent left sidebar, a "Now Rendering" hero, glass-warm
stat + library cards, and an animated waveform. Call ``apply()`` per page.

See DESIGN.md for the full spec.
"""
from __future__ import annotations

from contextlib import contextmanager

from nicegui import ui

# ── Palette ───────────────────────────────────────────────────────────────────
PRIMARY = "#e8a45c"    # warm amber — primary CTAs
SECONDARY = "#b6a6e0"  # dusty lavender — secondary
TEAL = "#6fcaa8"       # positive / healthy / live-good
ROSE = "#e8849a"       # negative / stop
INFO = "#8fb8e8"
BG = "#15121c"
SURFACE = "#211b2b"

CARD = "studio-card w-full"
H = "studio-h"
SUB = "studio-sub"
LOG = "studio-log w-full"

_CSS = """
:root{
  --bg:#15121c; --bg2:#1b1626; --sidebar:#100d16;
  --surface:rgba(40,32,54,0.66); --surface2:rgba(54,44,72,0.7);
  --border:rgba(232,164,92,0.16); --border2:rgba(182,166,224,0.18);
  --text:#f3ede2; --muted:#a89db5;
  --amber:#e8a45c; --lav:#b6a6e0; --teal:#6fcaa8; --rose:#e8849a;
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

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
.studio-sidebar{
  background:linear-gradient(180deg,#15101e,#100d16) !important;
  border-right:1px solid var(--border); width:230px;
}
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
  border-radius:20px; padding:20px 22px;
  box-shadow:0 14px 40px rgba(0,0,0,0.38), inset 0 1px 0 rgba(255,255,255,0.04);
  backdrop-filter:blur(12px);
}
.studio-h{ font-size:1.02rem; font-weight:680; color:var(--text); }
.studio-sub{ font-size:.8rem; color:var(--muted); line-height:1.45; }

/* ── Hero "Now Rendering" ────────────────────────────────────────────────── */
.hero{
  background:
    radial-gradient(700px 220px at 0% 0%, rgba(232,164,92,0.14), transparent 60%),
    var(--surface) !important;
  border:1px solid var(--border); border-radius:24px; padding:22px 24px;
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
  border-radius:18px; padding:16px 18px; min-width:0;
}
.stat-num{ font-size:1.7rem; font-weight:780; line-height:1.1; color:var(--text); }
.stat-lbl{ font-size:.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:1px; }

/* ── Library cards ───────────────────────────────────────────────────────── */
.libcard{
  border-radius:16px; overflow:hidden; cursor:pointer; transition:transform .16s, box-shadow .16s;
  border:1px solid var(--border2); background:var(--surface);
}
.libcard:hover{ transform:translateY(-3px); box-shadow:0 16px 34px rgba(0,0,0,0.5); }
.libcard img{ width:100%; aspect-ratio:16/9; object-fit:cover; display:block; }
.libcard .meta{ padding:8px 12px; }
.libcard .meta .t{ font-size:.82rem; font-weight:600; color:var(--text);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.libcard .meta .d{ font-size:.7rem; color:var(--muted); }

/* ── Waveform (animated) ─────────────────────────────────────────────────── */
.wave{ display:flex; align-items:center; gap:3px; height:34px; }
.wave i{ width:3px; border-radius:3px; background:linear-gradient(var(--amber),var(--lav));
  animation:wv 1s ease-in-out infinite; }
@keyframes wv{ 0%,100%{ height:6px; opacity:.5 } 50%{ height:30px; opacity:1 } }
.wave.paused i{ animation-play-state:paused; height:6px; opacity:.35; }

/* ── Pills / chips ───────────────────────────────────────────────────────── */
.pill{ border-radius:999px; padding:3px 12px; font-size:.76rem; font-weight:650;
  border:1px solid rgba(255,255,255,0.10); background:rgba(0,0,0,0.22); }

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


@contextmanager
def card(title: str | None = None, subtitle: str | None = None, classes: str = ""):
    with ui.element("div").classes(f"{CARD} {classes}"):
        if title:
            ui.label(title).classes(H)
        if subtitle:
            ui.label(subtitle).classes(SUB)
        yield


def waveform(bars: int = 26, paused: bool = False):
    cls = "wave paused" if paused else "wave"
    html = "".join(
        f'<i style="animation-delay:{(i % 13) * 0.07:.2f}s"></i>' for i in range(bars)
    )
    return ui.html(f'<div class="{cls}">{html}</div>')
