# Lo-fi Factory — Web UI Design

The control panel's look is defined centrally in `webui/theme.py` and applied per
page via `theme.apply()`. This doc captures the design system and rationale.

## Aesthetic: "lofi night"
Cozy, late-night-study mood that matches the channel's content — deep plum/indigo
background with a soft lavender→amber glow, glassy translucent cards, calm
typography. Not a corporate dashboard; a warm workbench.

## Palette
| Token | Hex | Use |
|-------|-----|-----|
| `primary` | `#a78bfa` | lavender — primary actions (Generate+Upload, Connect) |
| `secondary` | `#6d5dd3` | deep violet — secondary actions (Generate only) |
| `accent` | `#f4a261` | warm amber — highlights, warnings, "running" state |
| `positive` | `#5cc8a0` | success, connected, idle-healthy |
| `negative` | `#e8688a` | destructive (Cancel, End, Disconnect), errors |
| `info` | `#6cb6ff` | informational notices |
| bg base | `#15111f` | page background |
| surface | `rgba(40,32,64,.55)` | card glass |

Background is a layered radial gradient (lavender top-left, amber top-right) over
the base — gives depth without busy imagery.

## Typography
- **Inter** (400–700) for all UI text — clean, legible at small sizes.
- **JetBrains Mono** for the live-log panels and code-like values (redirect URI,
  video filenames).
- Loaded from Google Fonts in `theme.apply()`.

## Components
- **Card / `theme.panel(title, subtitle)`** — the one structural primitive.
  Translucent surface, 18px radius, soft shadow + 1px lavender border, blur.
  Every tab is a stack of panels: a controls panel + a "Live output" log panel.
- **Header (`.lofi-header`)** — gradient bar, 🎧 wordmark, live **status pills**
  (idle / running / LIVE) and a YouTube connection pill that refresh every second.
- **Status pill (`theme.pill`)** — rounded chip; color is driven live by state.
- **Live log (`.lofi-log`)** — near-black terminal surface, mono font, mint text;
  the focal point during generation/streaming.
- **Buttons** — rounded (12px), no uppercase, weight 600; color encodes intent
  (primary = go, negative = stop/destroy, flat = passive like Refresh/Status).

## Layout
- Centered single column, `max-w-5xl`, generous gaps (16px) and card padding.
- Six tabs: Generate · Upload · Live · lofi-inator · History · Settings.
- Tab panels have no default padding; spacing comes from the panel cards so the
  rhythm is consistent everywhere.

## Principles
1. **One primitive, repeated** — everything is a `panel`, so the UI stays
   coherent as tabs are added.
2. **Color = intent** — users read button safety by hue, not by reading labels.
3. **Always-live status** — header pills and logs poll, so the panel reflects the
   real pipeline state without manual refresh.
4. **Calm, not flashy** — low-saturation surfaces, soft glow; the moving logs are
   the only "motion," matching the lofi vibe.

## Extending
Add a tab by writing a `tab_x()` that composes `theme.panel(...)` blocks and
registering it in `index()`. Reuse `live_log(get_job)` for anything that shells
out through `jobs.manager`. Don't hand-roll colors — use the Quasar tokens
(`color=primary`, `text-positive`, …) or the CSS variables in `theme.py`.
