"""
app.py — "Lofi Studio" web control panel for the Lo-fi Factory.

A creator-studio UI (sidebar + Now-Rendering hero + live channel stats + a
library grid of rendered videos) over the existing run.py / publish.py pipeline.
Design system in theme.py, spec in DESIGN.md. Run via:  python webui.py
"""
from __future__ import annotations

import asyncio
import csv
import datetime
import html
import io
import json
import os
import re
import time
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from nicegui import app, ui
from nicegui.timer import Timer

from . import (
    alerts, auth, automation, config, data, jobs, stats, system_admin, theme, youtube_oauth,
)

NAV = [
    ("studio", "Studio", "graphic_eq"),
    ("library", "Library", "grid_view"),
    ("samples", "Samples", "library_music"),
    ("live", "Live", "sensors"),
    ("logs", "Logs", "receipt_long"),
    ("analytics", "Analytics", "insights"),
    ("automation", "Automation", "autorenew"),
    ("calendar", "Calendar", "calendar_month"),
    ("system", "System", "monitor_heart"),
    ("settings", "Settings", "settings"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Shared bits
# ─────────────────────────────────────────────────────────────────────────────
def _src(prefix: str, name: str) -> str:
    """A URL for raw HTML attributes: file names are percent-encoded and the
    result HTML-escaped, so a name with a quote or '#' can't break out."""
    return html.escape(prefix + quote(str(name), safe=""), quote=True)


def live_log(get_job, height: str = "h-72") -> None:
    log = ui.log(max_lines=4000).classes(f"{theme.LOG} w-full {height}")
    state = {"n": 0, "job": None}

    def refresh() -> None:
        job = get_job()
        if job is None:
            return
        if job is not state["job"]:
            log.clear()
            state.update(n=0, job=job)
        lines = list(job.lines)
        if len(lines) > state["n"]:
            for line in lines[state["n"]:]:
                log.push(line)
            state["n"] = len(lines)

    ui.timer(0.4, refresh)


def _last_stage(job) -> str:
    for line in reversed(job.lines):
        s = line.strip()
        if s:
            return s[:88]
    return "starting…"


# Stage detection / ffmpeg progress parsing (originally from the removed TUI) so the
# web log gets the same friendly stage names + progress bar as the terminal one.
def _parse_ffmpeg_progress(line: str) -> dict | None:
    """Parse an ffmpeg -stats line: frame=1234 fps=24.0 time=01:00:00 speed=1.0x"""
    if "time=" not in line:
        return None
    result = {}
    for part in line.split():
        if "=" in part:
            k, _, v = part.partition("=")
            result[k.strip()] = v.strip()
    return result if result else None


def _stage_from_lines(job) -> str | None:
    for line in reversed(job.lines):
        low = line.lower()
        if "[assemble] duration:" in low:
            return "Assembling video"
        if "[upload]" in line:
            return "Uploading to YouTube"
        if "[2/5]" in line or "music" in low:
            return "Generating music"
        if "[1/5]" in line or "visual" in low:
            return "Rendering visual"
        if "[3/5]" in line or "seo" in low:
            return "Generating SEO"
        if "[4/5]" in line or "thumbnail" in low:
            return "Generating thumbnail"
    return None


def _target_secs(job) -> int | None:
    for line in job.lines:
        if line.startswith("[ASSEMBLE] Duration:"):
            m = re.search(r"\((\d+)s\)", line)
            if m:
                return int(m.group(1))
    return None


def _latest_ffmpeg_progress(job) -> dict | None:
    for line in reversed(job.lines):
        parsed = _parse_ffmpeg_progress(line)
        if parsed:
            return parsed
    return None


def _fmt_elapsed(secs: float) -> str:
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# Sub-genre/mood/engine dropdowns are shared verbatim between render_dialog()
# (Studio "New render") and queue_dialog() (Calendar "Add to queue") -- both
# build the identical run.py/publish.py argv from the identical set of
# controls, so the argv-building itself lives in one place (testable without
# spinning up a real NiceGUI dialog) rather than being copy-pasted per-dialog
# the way theme/duration/privacy historically were.
def _subgenre_select_options() -> dict[str, str]:
    return {"auto": "Auto (algorithm picks)",
            **{k: k.replace("_", " ").title() for k in config.subgenre_choices()}}


_ENGINE_SELECT_OPTIONS = {
    "v1": "Standard",
    "v2": "Experimental",
}


def _build_render_args(*, upload: bool, theme: str, duration: str, privacy: str,
                        subgenre: str = "auto", mood: str = "", engine: str = "v1") -> list[str]:
    """Build the run.py (render-only) or publish.py auto (render+upload) argv
    for a render job, given the dialog's current control values. `theme`
    "random" and `subgenre` "auto" let the pipeline pick and are left out of
    argv. The v1 composer is the pipeline default; v2 is opt-in."""
    if upload:
        args = ["publish.py", "auto", "--privacy", privacy, "--duration", duration]
    else:
        args = ["run.py", "--skip-upload", "--duration", duration]
    if theme != "random":
        args += ["--theme", theme]
    if subgenre != "auto":
        args += ["--sub-genre", subgenre]
    if mood:
        args += ["--mood", mood]
    if engine == "v2":
        args += ["--music-v2"]
    return args


def render_dialog() -> None:
    yt_connected = youtube_oauth.status()["connected"]
    with ui.dialog() as dlg, theme.card(title="New render", classes="w-96 gap-3"):
        tsel = ui.select(config.THEMES, value=config.DEFAULT_THEME, label="Theme").classes("w-full")
        dsel = ui.select(config.DURATIONS, value=config.DEFAULT_DURATION, label="Duration").classes("w-full")
        psel = ui.select(config.PRIVACY, value=config.DEFAULT_PRIVACY, label="Privacy").classes("w-full")
        sgsel = ui.select(_subgenre_select_options(), value="auto", label="Sub-genre").classes("w-full")
        mood_input = ui.input("Mood (optional)", placeholder="e.g. rainy study session").classes("w-full")
        esel = ui.select(_ENGINE_SELECT_OPTIONS, value="v1", label="Composer").classes("w-full")
        if not yt_connected:
            ui.label("YouTube isn't connected yet — connect it in Settings before uploading. "
                     "\"Render only\" works fine without it.").classes(f"{theme.SUB} text-amber")

        async def go(upload: bool) -> None:
            if jobs.manager.is_busy() or system_admin.pipeline_running():
                ui.notify("A render is already running.", type="warning")
                return
            args = _build_render_args(
                upload=upload, theme=tsel.value, duration=dsel.value, privacy=psel.value,
                subgenre=sgsel.value, mood=mood_input.value, engine=esel.value,
            )
            name = "render+upload" if upload else "render"
            await jobs.manager.run(name, args)
            dlg.close()
            ui.notify(f"Started: {name}", type="positive")
            set_view("studio")

        with ui.row().classes("w-full justify-end gap-2 mt-1"):
            ui.button("Cancel", on_click=dlg.close).props("flat color=primary")
            ui.button("Render only", on_click=lambda: go(False)).props("color=secondary")
            upload_btn = ui.button("Render + Upload", on_click=lambda: go(True))\
                .props("color=primary")
            if not yt_connected:
                upload_btn.disable()
                upload_btn.tooltip("Connect YouTube in Settings first")
    dlg.open()


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────
_HERO_STATUS_CLASSES = "text-amber text-rose text-teal"


def view_studio(root) -> None:
    with root:
        # ── Hero: Now Rendering ────────────────────────────────────────────────
        with ui.element("div").classes("hero w-full"):
            with ui.row().classes("items-center gap-5 no-wrap w-full overflow-x-auto"):
                lib = stats.library(limit=1)
                if lib:
                    ui.image(f"/media/{lib[0]['thumb_name']}").classes("hero-art")\
                        .props("fit=cover")
                else:
                    with ui.element("div").classes("hero-art hero-art-empty"):
                        ui.label("NO DATA")
                with ui.column().classes("gap-2 grow min-w-0"):
                    with ui.row().classes("items-center gap-2"):
                        status = ui.label().classes("pill")
                        ttl = ui.label("").classes("text-h1")
                    sub = ui.label("").classes("studio-sub")
                    prog = ui.linear_progress(value=1.0, show_value=False)\
                        .props("indeterminate rounded color=primary").classes("w-full")
            with ui.row().classes("gap-3 mt-4"):
                ui.button("New render", icon="add",
                          on_click=render_dialog).props("color=primary")
                ui.button("Go live", icon="sensors",
                          on_click=lambda: set_view("live")).props("color=secondary")
                cancel_btn = ui.button("Cancel render", icon="stop",
                                       on_click=lambda: jobs.manager.cancel())\
                    .props("flat color=negative")

        # Automation status/progress is polled on its own slower async timer
        # (it shells out to systemctl + reads /proc + a log file -- too slow
        # to run synchronously on refresh_hero's 1Hz tick without stalling
        # the event loop) and cached here for refresh_hero to read.
        _auto_hero_state: dict = {}

        async def refresh_auto_for_hero() -> None:
            if jobs.manager.is_busy() or jobs.manager.stream_running():
                return  # a manual job/stream owns the hero; don't bother polling
            auto_st = await asyncio.to_thread(automation.status)
            running = auto_st.get("running_now", False)
            progress = await asyncio.to_thread(automation.render_progress) if running else None
            external = (not running) and await asyncio.to_thread(system_admin.pipeline_running)
            _auto_hero_state.clear()
            _auto_hero_state.update(running=running, progress=progress, external=external)
            refresh_hero()

        def refresh_hero() -> None:
            cancel_btn.visible = jobs.manager.is_busy()
            if jobs.manager.is_busy():
                j = jobs.manager.current
                status.text = "● RENDERING"
                status.classes(remove=_HERO_STATUS_CLASSES, add="text-amber")
                ttl.text = j.name
                stage = _stage_from_lines(j) or _last_stage(j)
                elapsed = _fmt_elapsed(time.time() - j.started_at)
                fp = _latest_ffmpeg_progress(j)
                pct = None
                if fp and fp.get("time"):
                    target = _target_secs(j)
                    if target:
                        try:
                            hh, mm, ss = (int(float(x)) for x in fp["time"].split(":")[:3])
                            pct = min((hh * 3600 + mm * 60 + ss) / target, 1.0)
                        except (ValueError, ZeroDivisionError):
                            pct = None
                if pct is not None:
                    sub.text = f"{elapsed} elapsed · {stage} · {pct * 100:.0f}% · speed {fp.get('speed', '?')}"
                    prog.props(remove="indeterminate")
                    prog.value = pct
                else:
                    detail = f" · speed {fp['speed']}" if fp and fp.get("speed") else ""
                    sub.text = f"{elapsed} elapsed · {stage}{detail}"
                    prog.props(add="indeterminate")
                prog.visible = True
            elif jobs.manager.stream_running():
                status.text = "🔴 LIVE"
                status.classes(remove=_HERO_STATUS_CLASSES, add="text-rose")
                ttl.text = "Broadcasting"
                sub.text = f"{_fmt_elapsed(time.time() - jobs.manager.stream.started_at)} on air"
                prog.visible = False
            elif jobs.manager.current is not None and jobs.manager.current.status == "failed":
                j = jobs.manager.current
                status.text = "⚠ FAILED"
                status.classes(remove=_HERO_STATUS_CLASSES, add="text-rose")
                ttl.text = j.name
                sub.text = f"Last run failed · {_last_stage(j)}"
                prog.visible = False
            elif _auto_hero_state.get("running"):
                status.text = "● AUTO-RENDERING"
                status.classes(remove=_HERO_STATUS_CLASSES, add="text-amber")
                ttl.text = "Unattended render in progress"
                p = _auto_hero_state.get("progress") or {}
                stage = {"generating": "Generating music/visual/SEO",
                         "encoding": "Encoding final video",
                         "uploading": "Uploading to YouTube"}.get(p.get("stage"), "Working")
                if p.get("percent") is not None:
                    eta = p.get("eta_secs")
                    eta_txt = f" · ETA {_fmt_elapsed(eta)}" if eta else ""
                    speed_txt = f" · {p['speed']:.2f}x speed" if p.get("speed") else ""
                    sub.text = f"{stage} · {p['percent']:.0f}%{eta_txt}{speed_txt}"
                    prog.props(remove="indeterminate")
                    prog.value = p["percent"] / 100
                else:
                    sub.text = f"{stage}…"
                    prog.props(add="indeterminate")
                prog.visible = True
            elif _auto_hero_state.get("external"):
                status.text = "● RENDERING"
                status.classes(remove=_HERO_STATUS_CLASSES, add="text-amber")
                ttl.text = "Render running outside the panel"
                sub.text = "Started from the command line. New renders wait until it finishes."
                prog.props(add="indeterminate")
                prog.visible = True
            else:
                status.text = "● IDLE"
                status.classes(remove=_HERO_STATUS_CLASSES, add="text-teal")
                ttl.text = "Studio idle"
                sub.text = "Press New render to generate a fresh lofi video."
                prog.visible = False

        refresh_hero()
        ui.timer(1.0, refresh_hero)
        ui.timer(0.2, refresh_auto_for_hero, once=True)
        ui.timer(5.0, refresh_auto_for_hero)

        # ── System pulse: automation + queue + health in one glance, so
        # opening Studio answers "what's happening / what's next / what's
        # wrong" without a tour through Automation/Calendar/System. Each chip
        # is clickable -- jumps straight to the page that can act on it. ────
        with theme.card("System pulse", "Automation status, what's queued next, "
                        "and anything that needs attention."):
            pulse_col = ui.column().classes("w-full gap-2")

            def _pulse_chip(text: str, color_cls: str, nav_target: str) -> None:
                with ui.element("div").classes(
                        f"pill cursor-pointer {color_cls}").on(
                        "click", lambda t=nav_target: set_view(t)):
                    ui.label(text).classes("text-xs")

            async def refresh_pulse() -> None:
                auto_st = await asyncio.to_thread(automation.status)
                fallback_st = await asyncio.to_thread(automation.auto_run_state)
                pending = jobs.queue.list_pending()
                cert = await asyncio.to_thread(system_admin.cert_status)
                snap = await asyncio.to_thread(system_admin.resource_snapshot)

                pulse_col.clear()
                with pulse_col, ui.row().classes("items-center gap-2 flex-wrap"):
                    if not auto_st["installed"]:
                        _pulse_chip("automation not installed", "text-muted", "automation")
                    elif auto_st["running_now"]:
                        progress = await asyncio.to_thread(automation.render_progress)
                        pct_txt = (f" · {progress['percent']:.0f}%"
                                   if progress and progress.get("percent") is not None else "")
                        _pulse_chip(f"● auto-render running now{pct_txt}", "text-amber", "automation")
                    elif auto_st["active"]:
                        _pulse_chip(f"○ armed · next {auto_st.get('next_run') or '?'}",
                                    "text-teal", "automation")
                    else:
                        _pulse_chip("○ automation stopped", "text-rose", "automation")

                    if pending:
                        _pulse_chip(f"{len(pending)} queued", "text-info", "calendar")

                    if fallback_st["in_fallback"]:
                        _pulse_chip(f"⚠ {fallback_st['consecutive_failures']} consecutive "
                                    "failures — fallback mode", "text-rose", "automation")

                    if cert and cert.get("expiring_soon"):
                        _pulse_chip(f"⚠ TLS cert expires in {cert['days_left']:.0f}d",
                                    "text-amber", "system")

                    if snap["disk_percent"] > 90:
                        _pulse_chip(f"⚠ disk {snap['disk_percent']:.0f}% full",
                                    "text-rose", "system")

            ui.timer(0.1, refresh_pulse, once=True)
            ui.timer(15.0, refresh_pulse)

        # ── Stat cards ─────────────────────────────────────────────────────────
        if not youtube_oauth.status()["connected"]:
            with theme.card(classes="w-full flex items-center justify-between", tone="amber"):
                ui.label("Connect YouTube to see channel stats (subscribers, views, videos).")\
                    .classes(theme.SUB)
                ui.button("Connect", icon="link",
                          on_click=lambda: set_view("settings")).props("dense color=primary")
        else:
            with ui.row().classes("w-full gap-4 no-wrap overflow-x-auto"):
                cells = {}
                for key, label in [("subs", "Subscribers"), ("views", "Views"),
                                   ("videos", "Videos")]:
                    with ui.element("div").classes("stat grow"):
                        cells[key] = ui.label("—").classes("stat-num")
                        ui.label(label).classes("stat-lbl")

            async def refresh_stats() -> None:
                # A YouTube API call; keep it off the event loop.
                s = await asyncio.to_thread(stats.channel_stats)
                cells["subs"].text = stats.fmt_count(s["subs"])
                cells["views"].text = stats.fmt_count(s["views"])
                cells["videos"].text = stats.fmt_count(s["videos"])

            ui.timer(0.1, refresh_stats, once=True)
            ui.timer(30.0, refresh_stats)

        # ── Views by video ──────────────────────────────────────────────────────
        # Single-series bar (no legend needed -- see dataviz skill's color-
        # formula: one series doesn't need one) using the same
        # video_engagement() batched call the Content table (Library view)
        # reuses, so this costs nothing extra beyond what's already fetched
        # on that page. Real absolute counts, not a sparse day-by-day
        # analytics series -- renders meaningfully even with only 1-2 videos.
        _lib_for_chart = stats.library(limit=10)
        _vids_for_chart = [c["video_id"] for c in _lib_for_chart if c.get("video_id")]
        if _vids_for_chart:
            _eng_for_chart = stats.video_engagement(_vids_for_chart)
            _chart_rows = sorted(
                [{"title": c["title"], "views": _eng_for_chart.get(c["video_id"], {}).get("views", 0)}
                 for c in _lib_for_chart if c.get("video_id")],
                key=lambda r: r["views"], reverse=True,
            )
            with theme.card("Views by video", "Published uploads, most-viewed first."):
                ui.echart({
                    "grid": {"left": 8, "right": 16, "top": 8, "bottom": 8, "containLabel": True},
                    "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                    "xAxis": {"type": "value", "axisLabel": {"color": theme.MUTED}},
                    "yAxis": {"type": "category", "inverse": True,
                              "data": [r["title"][:36] for r in _chart_rows],
                              "axisLabel": {"color": theme.MUTED, "fontSize": 11}},
                    "series": [{
                        "type": "bar", "data": [r["views"] for r in _chart_rows],
                        "itemStyle": {"color": theme.PRIMARY, "borderRadius": [0, 3, 3, 0]},
                        "barMaxWidth": 22,
                    }],
                }).classes("w-full mt-1").style(f"height:{max(120, 44 * len(_chart_rows))}px")

        # ── Library preview ────────────────────────────────────────────────────
        with theme.card():
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Recent renders").classes(theme.H)
                ui.button("View all", on_click=lambda: set_view("library"))\
                    .props("flat dense color=primary")
            _library_grid(stats.library(limit=8))

        # ── Run history ─────────────────────────────────────────────────────────
        with theme.card(title="Recent runs"):
            _runs_table(jobs.manager.history[:10])

        # ── Collapsible live output ────────────────────────────────────────────
        with ui.expansion("Live output", icon="terminal").classes("studio-card w-full"):
            live_log(lambda: jobs.manager.current, height="h-72")


_STATUS_COLOR = {"running": "text-amber", "success": "text-teal",
                  "failed": "text-rose", "cancelled": "text-muted"}
_STATUS_ICON = {"running": "sync", "success": "check_circle",
                 "failed": "error", "cancelled": "block"}


def _card_from_artifacts(j) -> dict | None:
    """Build a Library-card-shaped dict straight from a Job's exact artifact
    paths (see jobs.py's [RESULT]-line parsing) -- lets Runs history open/
    delete a render precisely, without stats.library()'s fuzzy timestamp
    join (which this job may not even show up in yet on a fast page check)."""
    art = j.artifacts
    if not art.get("video"):
        return None
    thumb = art.get("thumb", "")
    return {
        "theme": "", "dt": None,
        "thumb": thumb,
        "thumb_name": os.path.basename(thumb) if thumb else "",
        "title": j.name,
        "url": None,
        "video_id": None,
        "video_file": os.path.basename(art["video"]),
        "when": "",
    }


async def _retry_job(job_id: str) -> None:
    """Re-run a failed JobManager history entry with its exact original
    cmd/args (see jobs.JobManager.retry) -- shared by the Studio "Recent
    runs" table and any other place that lists JobManager history."""
    try:
        await jobs.manager.retry(job_id)
        ui.notify("Retrying job…", type="positive")
    except (ValueError, RuntimeError) as e:
        ui.notify(str(e), type="negative")


def _retention_chart(points) -> None:
    if points:
        xs = [round(p["t"] * 100) for p in points]
        ys = [round(p["pct"] * 100, 1) for p in points]
        ui.echart({
            "grid": {"left": 40, "right": 16, "top": 16, "bottom": 28},
            "xAxis": {"type": "category", "data": xs,
                      "name": "% of video", "axisLabel": {"color": theme.MUTED}},
            "yAxis": {"type": "value", "name": "% watching",
                      "axisLabel": {"color": theme.MUTED}},
            "series": [{"type": "line", "data": ys, "smooth": True,
                        "areaStyle": {"opacity": 0.15}, "color": theme.PRIMARY}],
        }).classes("w-full").style("height:220px")
    else:
        ui.label("No retention data yet — needs more views, or check that YouTube "
                 "is connected in Settings.").classes(theme.SUB)


def _job_details_dialog(j) -> None:
    """Full detail behind one job row: exact command, absolute timestamps,
    exit code, slot -- not just what fits in the summary row. The "detailed"
    half of the log; the summary row is the "at a glance" half."""
    started = datetime.datetime.fromtimestamp(j.started_at).strftime("%Y-%m-%d %H:%M:%S")
    finished = (datetime.datetime.fromtimestamp(j.finished_at).strftime("%Y-%m-%d %H:%M:%S")
                if j.finished_at else "—")
    with ui.dialog() as dlg, theme.card(title=j.name, classes="w-full gap-2 max-w-2xl"):
        for label, value in [
            ("Job ID", j.id), ("Status", j.status), ("Slot", j.slot),
            ("Started", started), ("Finished", finished),
            ("Duration", _fmt_elapsed(j.duration)),
            ("Exit code", str(j.returncode) if j.returncode is not None else "—"),
        ]:
            with ui.row().classes("w-full items-center gap-3 no-wrap"):
                ui.label(label).classes(f"{theme.SUB} w-24 shrink-0")
                ui.label(value).classes("text-sm font-mono truncate")
        ui.label("Command").classes(f"{theme.SUB} mt-2")
        ui.label(" ".join(j.cmd)).classes("text-xs font-mono code-chip w-full")

        full_log = jobs.read_job_log(j.id)
        ui.label("Full output").classes(f"{theme.SUB} mt-2")
        if full_log:
            ui.label(full_log).classes(f"{theme.LOG} w-full h-96 overflow-y-auto "
                                        "whitespace-pre-wrap p-3")
        elif getattr(j, "error", ""):
            ui.label(j.error).classes("text-xs font-mono code-chip w-full")
            ui.label("(only the last line was kept — this job ran before full-log "
                     "persistence existed)").classes(f"{theme.SUB} text-xs")
        else:
            ui.label("No output captured.").classes(theme.SUB)
        ui.button("Close", on_click=dlg.close).props("flat").classes("self-end mt-2")
    dlg.open()


def _read_title_variants(seo_path: str) -> tuple[str, list[str], list[str]]:
    """(current_title, variants, strategies) parsed from a seo_*.json file.
    Falls back to a single-item variants list (just the chosen title) if the
    file predates title_variants being logged, or is missing/unreadable."""
    try:
        with open(seo_path) as f:
            seo = json.load(f)
    except Exception:
        return "", [], []
    title = seo.get("title", "")
    variants = seo.get("title_variants") or ([title] if title else [])
    strategies = seo.get("title_variant_strategies") or []
    return title, variants, strategies


def _upload_with_title_dialog(j) -> None:
    """Pre-publish review checkpoint for a completed "Render only" job: shows
    the 3 title variants generate_seo.py already generated for this render
    (job.artifacts["seo"], parsed by jobs.py from run.py's [RESULT] line),
    lets you pick one or edit it freely, then uploads with that exact title.

    Manual-path only, by design: the scheduled/unattended `publish.py auto`
    run (lofi-auto.timer) never goes through the webui at all and stays
    fully autonomous -- this dialog only exists for when a human is here at
    the dashboard reviewing a job they just triggered.
    """
    art = j.artifacts
    seo_path, video_path = art.get("seo"), art.get("video")
    if not seo_path or not video_path:
        ui.notify("No SEO/video artifacts recorded for this job.", type="warning")
        return

    current_title, variants, strategies = _read_title_variants(seo_path)
    if not variants:
        ui.notify("No title variants found in this job's SEO file.", type="warning")
        return
    labels = list(strategies) + ["custom"] * (len(variants) - len(strategies))
    options = {v: f"({label}) {v}" for v, label in zip(variants, labels)}

    with ui.dialog() as dlg, theme.card(title="Upload with title", classes="w-full gap-3 max-w-2xl"):
        ui.label(os.path.basename(video_path)).classes(theme.SUB)
        variant_sel = ui.select(options, value=variants[0], label="Generated variant")\
            .classes("w-full")
        title_in = ui.input("Title (editable)", value=variants[0])\
            .classes("w-full").props("maxlength=100 counter")
        variant_sel.on_value_change(lambda e: setattr(title_in, "value", e.value))

        with ui.row().classes("w-full justify-end gap-2 mt-1"):
            ui.button("Cancel", on_click=dlg.close).props("flat color=primary")

            async def do_upload() -> None:
                chosen = (title_in.value or "").strip()
                if not chosen:
                    ui.notify("Title can't be empty.", type="warning")
                    return
                if jobs.manager.is_busy():
                    ui.notify("Another job is already running.", type="warning")
                    return
                await jobs.manager.run(
                    "upload",
                    ["publish.py", "upload", "--video", video_path,
                     "--seo", seo_path, "--title", chosen],
                )
                dlg.close()
                ui.notify("Started: upload", type="positive")
                set_view("studio")

            ui.button("Upload", icon="cloud_upload", on_click=do_upload)\
                .props("unelevated color=primary")
    dlg.open()


def _runs_table(history: list) -> None:
    if not history:
        ui.label("No runs yet this session.").classes(theme.SUB + " mt-1")
        return
    with ui.column().classes("w-full gap-1 mt-2 table-scroll"):
        for j in history:
            color_cls = _STATUS_COLOR.get(j.status, "text-muted")
            card = _card_from_artifacts(j) if j.status == "success" else None

            def _view(card=card) -> None:
                _open_detail([card], 0)

            def _row_actions(card=card, j=j) -> None:
                ui.button(icon="info_outline", on_click=lambda j=j: _job_details_dialog(j))\
                    .props("flat dense round").tooltip("Full details")
                if card:
                    ui.button("View", icon="visibility", on_click=_view)\
                        .props("flat dense color=primary")
                if j.status == "failed":
                    ui.button("Retry", icon="replay",
                              on_click=lambda j=j: _retry_job(j.id))\
                        .props("flat dense color=secondary")
                if j.status == "success" and j.name == "render" and j.artifacts.get("seo"):
                    ui.button("Upload with title…", icon="cloud_upload",
                              on_click=lambda j=j: _upload_with_title_dialog(j))\
                        .props("flat dense color=primary")

            # Reason column right after status (not after duration) -- on a
            # narrow/mobile viewport the columns past what fits need a
            # horizontal swipe to reach, and "why did it fail" matters more
            # at a glance than exactly how long it ran for.
            theme.data_row([
                {"icon": _STATUS_ICON.get(j.status, "help"), "color": color_cls},
                {"text": j.name, "classes": "text-body font-medium", "width": "lg"},
                {"text": j.status, "color": color_cls, "width": "sm"},
                {"text": (getattr(j, "error", "") or _last_stage(j)) if j.status == "failed" else "",
                 "classes": f"{theme.SUB} truncate"},
                {"text": _fmt_elapsed(j.duration), "classes": theme.SUB, "width": "xs"},
            ], extra=_row_actions)


def _library_grid(cards: list[dict], on_change=lambda: None) -> None:
    if not cards:
        ui.label("No renders yet.").classes(theme.SUB)
        return
    with ui.element("div").classes(
            "w-full grid gap-3 mt-2").style(
            "grid-template-columns:repeat(auto-fill,minmax(190px,1fr))"):
        for i, c in enumerate(cards):
            with ui.element("div").classes("libcard")\
                    .on("click", lambda i=i: _open_detail(cards, i, on_change)):
                if c.get("video_file"):
                    # Hover-to-preview: swap the static poster for the actual clip
                    # (muted, looping, loaded on demand) while the pointer is over
                    # the card, same interaction as hover-video-player-style
                    # galleries -- gives a real motion preview without needing to
                    # open the detail dialog for every card. Bound via NiceGUI's
                    # mouseenter/mouseleave (not inline onmouseenter= HTML attrs --
                    # ui.html() strips those as an XSS precaution, confirmed via a
                    # real DOM dump showing every other attribute survived except
                    # the two on* handlers).
                    with ui.element("div").classes("libcard-media") as media:
                        ui.image(f"/media/{c['thumb_name']}")\
                            .props("ratio=1.7778 fit=cover loading=lazy")
                        ui.html(
                            f'<video muted loop preload="none" playsinline '
                            f'style="display:none;position:absolute;inset:0;'
                            f'width:100%;height:100%;object-fit:cover" '
                            f'src="{_src("/videos/", c["video_file"])}"></video>'
                        )
                    mid = media.id

                    async def _hover_enter(mid=mid) -> None:
                        # A slow/backgrounded client tab can miss the default
                        # 1s response window (seen for real: TimeoutError from
                        # a mobile session over a Tailscale relay hop) -- the
                        # JS still runs client-side regardless, we just don't
                        # need to wait for confirmation, so swallow it rather
                        # than let it surface as an unhandled exception.
                        try:
                            await ui.run_javascript(
                                f"const m=document.getElementById('c{mid}');"
                                f"const v=m&&m.querySelector('video');"
                                f"const p=m&&m.querySelector('.q-img,img');"
                                f"if(v){{v.style.display='block';v.play().catch(()=>{{}});}}"
                                f"if(p)p.style.display='none';",
                                timeout=5.0,
                            )
                        except TimeoutError:
                            pass

                    async def _hover_leave(mid=mid) -> None:
                        try:
                            await ui.run_javascript(
                                f"const m=document.getElementById('c{mid}');"
                                f"const v=m&&m.querySelector('video');"
                                f"const p=m&&m.querySelector('.q-img,img');"
                                f"if(v){{v.pause();v.style.display='none';}}"
                                f"if(p)p.style.display='block';",
                                timeout=5.0,
                            )
                        except TimeoutError:
                            pass

                    media.on("mouseenter", _hover_enter)
                    media.on("mouseleave", _hover_leave)
                else:
                    ui.image(f"/media/{c['thumb_name']}")\
                        .props("ratio=1.7778 fit=cover loading=lazy")
                with ui.element("div").classes("meta"):
                    ui.label(c["title"]).classes("t")
                    ui.label(f"{c['theme']} · {c['when']}").classes("d")
                ui.button(icon="delete_outline") \
                    .props("flat round dense color=white") \
                    .classes("libcard-del") \
                    .on("click.stop", lambda c=c: _confirm_delete_render(c, on_change))


def _confirm_delete_render(c: dict, on_change) -> None:
    busy = _render_in_progress()
    manifest = [] if busy else data.render_delete_manifest(c)
    total_bytes = sum(m["size_bytes"] for m in manifest)
    with ui.dialog() as dlg, theme.card(title=f"Delete “{c['title']}”?", classes="gap-3 max-w-lg"):
        if busy:
            ui.label("A render is in progress — delete is disabled until it "
                     "finishes (this protects against deleting a file that's "
                     "still being written).").classes(theme.SUB)
        elif not manifest:
            ui.label("No local files found for this render (already cleaned up, "
                     "or it only exists on YouTube).").classes(theme.SUB)
        else:
            ui.label(f"{len(manifest)} file(s), {total_bytes / 1_048_576:.0f} MB total — "
                     f"this cannot be undone.").classes(theme.SUB)
            with ui.column().classes("w-full gap-1 max-h-[180px] overflow-y-auto"):
                for m in manifest:
                    with ui.row().classes("w-full justify-between no-wrap"):
                        ui.label(m["name"]).classes("text-sm truncate")
                        ui.label(f"{m['size_bytes'] / 1_048_576:.1f} MB")\
                            .classes(f"text-sm {theme.SUB}")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dlg.close).props("flat")

            def do_delete() -> None:
                try:
                    removed = data.delete_render(c)
                except RuntimeError as e:
                    ui.notify(str(e), type="negative")
                    return
                dlg.close()
                ui.notify(f"Deleted {len(removed)} file(s)."
                          if removed else "Nothing to delete.", type="positive")
                on_change()

            ui.button("Delete", icon="delete", on_click=do_delete, color="negative") \
                .props("unelevated" if manifest else "flat disable")
    dlg.open()


def _edit_video_dialog(c: dict) -> None:
    """Edit an already-published video's title/description/tags/privacy, and
    regenerate + push a new thumbnail with the current generator. Confirmed
    2026-08-16: nothing in this codebase could touch a video after upload at
    all -- publish.py/upload_youtube.py only ever set these once, at upload
    time. This is the YT-Studio feature that was actually missing (editing
    live content), not another view of data that already had a page."""
    video_id = c["video_id"]
    with ui.dialog() as dlg, theme.card(title="Edit video", classes="w-full gap-3 max-w-2xl"):
        body = ui.column().classes("w-full gap-3")
        with body:
            ui.label("Loading current details…").classes(theme.SUB)

        async def load() -> None:
            details = await asyncio.to_thread(stats.get_video_details, video_id)
            body.clear()
            with body:
                if details is None:
                    ui.label("Couldn't load this video from YouTube — check the connection "
                             "in Settings.").classes("text-rose")
                    return
                title_in = ui.input("Title", value=details["title"]).classes("w-full")
                desc_in = ui.textarea("Description", value=details["description"])\
                    .classes("w-full").props("rows=8")
                tags_in = ui.input("Tags (comma-separated)",
                                    value=", ".join(details["tags"])).classes("w-full")
                privacy_in = ui.select(["public", "unlisted", "private"],
                                        value=details["privacy"], label="Privacy").classes("w-48")

                thumb_status = ui.label("").classes(theme.SUB)

                async def do_regenerate_thumbnail() -> None:
                    thumb_status.text = "Regenerating…"
                    new_path = await asyncio.to_thread(
                        stats.regenerate_thumbnail, video_id, title_in.value)
                    if not new_path:
                        thumb_status.text = ("Couldn't determine this video's original theme/"
                                              "duration — regenerate skipped.")
                        return
                    ok = await asyncio.to_thread(stats.set_video_thumbnail, video_id, new_path)
                    thumb_status.text = ("Pushed new thumbnail to YouTube." if ok
                                          else "Generated locally, but pushing to YouTube failed.")
                    if ok:
                        ui.notify("Thumbnail updated", type="positive")

                with ui.row().classes("items-center gap-2") as thumb_row:
                    ui.button("Regenerate + push thumbnail", icon="auto_awesome",
                              on_click=do_regenerate_thumbnail).props("flat color=primary")
                thumb_status.move(thumb_row)

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Cancel", on_click=dlg.close).props("flat")

                    async def do_save() -> None:
                        tags = [t.strip() for t in (tags_in.value or "").split(",") if t.strip()]
                        ok = await asyncio.to_thread(
                            stats.update_video, video_id,
                            title=title_in.value, description=desc_in.value,
                            tags=tags, privacy=privacy_in.value,
                            category_id=details["category_id"])
                        ui.notify("Saved to YouTube" if ok else "Save failed — check connection",
                                  type="positive" if ok else "negative")
                        if ok:
                            dlg.close()

                    ui.button("Save changes", icon="save", on_click=do_save,
                              color="primary").props("unelevated")

        ui.timer(0.1, load, once=True)
    dlg.open()


def _open_detail(cards: list[dict], index: int, on_change=lambda: None) -> None:
    c = cards[index]
    with ui.dialog() as dlg, theme.card(classes="w-full gap-3 max-w-3xl"):
        with ui.row().classes("w-full items-start justify-between no-wrap"):
            with ui.column().classes("gap-0"):
                ui.label(c["title"]).classes(theme.H)
                ui.label(f"{c['theme']} · {c['when']}").classes(theme.SUB)
            with ui.row().classes("gap-1 no-wrap"):
                if c.get("video_id"):
                    ui.button(icon="edit", color="primary",
                              on_click=lambda: (dlg.close(), _edit_video_dialog(c)))\
                        .props("flat round dense").tooltip("Edit title/description/tags/thumbnail")
                ui.button(icon="delete_outline", color="negative",
                          on_click=lambda: (dlg.close(), _confirm_delete_render(c, on_change)))\
                    .props("flat round dense")
                ui.button(icon="close", on_click=dlg.close).props("flat round dense")

        # ── Lightbox-style prev/next (click or ←/→) — browse the whole set
        # without closing and reopening from the grid each time. ─────────────
        if len(cards) > 1:
            def goto(delta: int) -> None:
                dlg.close()
                _open_detail(cards, (index + delta) % len(cards), on_change)

            with ui.row().classes("w-full items-center justify-between no-wrap"):
                ui.button(icon="chevron_left", on_click=lambda: goto(-1)) \
                    .props("flat dense").tooltip("Previous (←)")
                ui.label(f"{index + 1} / {len(cards)}").classes(theme.SUB)
                ui.button(icon="chevron_right", on_click=lambda: goto(1)) \
                    .props("flat dense").tooltip("Next (→)")

            def on_key(e) -> None:
                if not e.action.keydown:
                    return
                if e.key == "ArrowLeft":
                    goto(-1)
                elif e.key == "ArrowRight":
                    goto(1)

            kb = ui.keyboard(on_key=on_key)
            dlg.on("hide", lambda: kb.delete())

        # ── Player ──────────────────────────────────────────────────────────
        if c.get("video_id"):
            ui.html(
                f'<iframe width="100%" height="380" class="detail-media" '
                f'src="{_src("https://www.youtube.com/embed/", c["video_id"])}" '
                f'allowfullscreen></iframe>'
            )
        elif c.get("video_file"):
            ui.html(
                f'<video controls preload="metadata" class="detail-media" '
                f'poster="{_src("/media/", c["thumb_name"])}">'
                f'<source src="{_src("/videos/", c["video_file"])}" type="video/mp4"></video>'
            )
        else:
            ui.image(f"/media/{c['thumb_name']}").props("fit=cover").classes("detail-media")

        # ── Metadata ────────────────────────────────────────────────────────
        with ui.row().classes("w-full gap-4 no-wrap overflow-x-auto"):
            if c.get("video_file"):
                try:
                    st = os.stat(os.path.join(config.OUTPUT_DIR, c["video_file"]))
                    with ui.element("div").classes("stat grow"):
                        ui.label(f"{st.st_size / 1_048_576:.0f} MB").classes("stat-num")
                        ui.label("File size").classes("stat-lbl")
                except OSError:
                    pass
            with ui.element("div").classes("stat grow"):
                ui.label("YouTube" if c.get("video_id") else "Local only").classes("stat-num")
                ui.label("Status").classes("stat-lbl")
        if c.get("url"):
            ui.link("Open on YouTube ↗", c["url"], new_tab=True).classes("text-sm")

        # ── Audience retention (uploaded videos with view data only) ──────────
        if c.get("video_id"):
            ui.separator()
            ui.label("Audience retention").classes(theme.H)
            retention_box = ui.column().classes("w-full")
            with retention_box:
                ui.label("Loading…").classes(theme.SUB)

            async def _fill_retention(vid=c["video_id"]) -> None:
                points = await asyncio.to_thread(stats.retention, vid)
                retention_box.clear()
                with retention_box:
                    _retention_chart(points)

            ui.timer(0.05, _fill_retention, once=True)

        # ── Comments (list + reply + moderate + delete) ───────────────────────
        if c.get("video_id"):
            ui.separator()
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Comments").classes(theme.H)
                comments_refresh_btn = ui.button(icon="refresh").props("flat dense round")
            comments_container = ui.column().classes("w-full gap-2")

            def _render_one_comment(cm: dict) -> None:
                with ui.column().classes("w-full gap-1").style(
                        "padding:8px; border-radius:10px; "
                        "background:rgba(255,255,255,0.03)"):
                    with ui.row().classes("w-full items-center justify-between no-wrap"):
                        ui.label(cm["author"]).classes("text-sm font-medium")
                        ui.label(f"👍 {cm['like_count']}").classes(theme.SUB)
                    ui.label(cm["text"]).classes("text-sm")
                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        ui.label(f"status: {cm.get('moderation_status', 'published')}")\
                            .classes(theme.SUB)
                        ui.button(icon="visibility_off",
                                  on_click=lambda cm=cm: _moderate(cm, "heldForReview"))\
                            .props("flat dense round size=sm").tooltip("Hold for review")
                        ui.button(icon="check_circle",
                                  on_click=lambda cm=cm: _moderate(cm, "published"))\
                            .props("flat dense round size=sm").tooltip("Publish")
                        ui.button(icon="block", color="negative",
                                  on_click=lambda cm=cm: _moderate(cm, "rejected"))\
                            .props("flat dense round size=sm").tooltip("Reject")
                        ui.button(icon="delete_outline", color="negative",
                                  on_click=lambda cm=cm: _delete(cm))\
                            .props("flat dense round size=sm").tooltip("Delete")
                    reply_box = ui.input(placeholder="Reply...").props("dense")\
                        .classes("w-full")
                    ui.button("Reply", icon="reply",
                              on_click=lambda cm=cm, box=reply_box: _reply(cm, box))\
                        .props("flat dense color=primary")
                    if cm.get("replies"):
                        with ui.column().classes(
                                "w-full gap-1 ml-5 pl-2.5 border-l-2 border-white/10"):
                            for rep in cm["replies"]:
                                with ui.row().classes(
                                        "w-full items-center justify-between no-wrap"):
                                    ui.label(rep["author"]).classes("text-xs font-medium")
                                    ui.label(f"👍 {rep['like_count']}").classes(theme.SUB)
                                ui.label(rep["text"]).classes("text-xs")

            async def _render_comments(force: bool = False) -> None:
                # YouTube API calls: off the event loop, or every open panel stalls.
                comment_list = await asyncio.to_thread(stats.list_comments, c["video_id"], force=force)
                comments_container.clear()
                with comments_container:
                    if comment_list is None:
                        ui.label("No comment data — check that YouTube is connected in "
                                 "Settings (comments may also be disabled on this "
                                 "video).").classes(theme.SUB)
                    elif not comment_list:
                        ui.label("No comments yet.").classes(theme.SUB)
                    else:
                        for cm in comment_list:
                            _render_one_comment(cm)

            async def _moderate(cm: dict, status: str) -> None:
                ok = await asyncio.to_thread(stats.set_comment_moderation, cm["id"], status)
                ui.notify("Moderation updated" if ok else "Failed — check YouTube connection",
                          type="positive" if ok else "negative")
                if ok:
                    await _render_comments(force=True)

            async def _delete(cm: dict) -> None:
                ok = await asyncio.to_thread(stats.delete_comment, cm["id"])
                ui.notify("Comment deleted" if ok else "Failed — check YouTube connection",
                          type="positive" if ok else "negative")
                if ok:
                    await _render_comments(force=True)

            async def _reply(cm: dict, box) -> None:
                text = (box.value or "").strip()
                if not text:
                    return
                result = await asyncio.to_thread(stats.reply_to_comment, cm["id"], text)
                if result:
                    box.value = ""
                    ui.notify("Reply posted", type="positive")
                    await _render_comments(force=True)
                else:
                    ui.notify("Reply failed — check YouTube connection", type="negative")

            comments_refresh_btn.on_click(lambda: _render_comments(force=True))
            with comments_container:
                ui.label("Loading comments…").classes(theme.SUB)
            ui.timer(0.05, _render_comments, once=True)
    dlg.open()


_CONTENT_SORTS = {
    "Newest": lambda r: r["dt"] or datetime.datetime.min,
    "Most views": lambda r: r["views"],
    "Most likes": lambda r: r["likes"],
    "Most comments": lambda r: r["comments"],
}


def _content_table(cards: list[dict], sort_by: str) -> None:
    """YouTube-Studio-style Content table: every synced video, one row each,
    with the at-a-glance stats the grid view can't show without opening each
    one individually. Reuses stats.video_engagement() (already powers the
    Analytics per-video table) for likes/comments/views in one batched call."""
    if not cards:
        ui.label("No renders yet.").classes(theme.SUB)
        return
    vids = [c["video_id"] for c in cards if c.get("video_id")]
    engagement = stats.video_engagement(vids) if vids else {}
    rows = []
    for c in cards:
        eng = engagement.get(c.get("video_id"), {})
        rows.append({**c, "views": eng.get("views", 0), "likes": eng.get("likes", 0),
                     "comments": eng.get("comments", 0)})
    rows.sort(key=_CONTENT_SORTS.get(sort_by, _CONTENT_SORTS["Newest"]), reverse=True)

    with ui.column().classes("w-full gap-1 mt-2 table-scroll"):
        theme.data_row([
            {"text": "Video", "width": "fill"},
            {"text": "Published", "width": "md"},
            {"text": "Status", "width": "sm"},
            {"text": "Views", "width": "sm"},
            {"text": "Likes", "width": "sm"},
            {"text": "Comments", "width": "sm"},
        ], header=True)
        for i, r in enumerate(rows):
            def _view(cards=rows, i=i) -> None:
                _open_detail(cards, i)

            with ui.row().classes("data-row cursor-pointer items-center gap-3 no-wrap")\
                    .on("click", _view):
                with ui.row().classes("items-center gap-2 no-wrap dcol-fill"):
                    ui.image(f"/media/{r['thumb_name']}").classes("w-20 aspect-video rounded")\
                        .props("fit=cover")
                    ui.label(r["title"]).classes("text-sm font-medium truncate min-w-0 flex-1")\
                        .tooltip(r["title"])
                ui.label(r["when"]).classes(f"{theme.SUB} dcol-md")
                if r.get("video_id"):
                    ui.label("Public").classes("text-teal text-sm dcol-sm")
                else:
                    ui.label("Local only").classes(f"{theme.SUB} dcol-sm")
                ui.label(stats.fmt_count(r["views"])).classes("text-sm dcol-sm")
                ui.label(stats.fmt_count(r["likes"])).classes("text-sm dcol-sm")
                ui.label(stats.fmt_count(r["comments"])).classes("text-sm dcol-sm")


def view_library(root) -> None:
    with root:
        with theme.card():
            # No `no-wrap` here (unlike the pseudo-table rows) -- title/search/refresh
            # read fine reflowing to a second line on a narrow phone width instead of
            # needing a horizontal-scroll affordance for just 3 items.
            with ui.row().classes("w-full items-center justify-between gap-3"):
                ui.label("Library").classes(theme.H)
                search = ui.input(placeholder="Search title or theme...")\
                    .props("dense clearable").classes("grow max-w-xs")
                with ui.row().classes("items-center gap-2"):   # wraps on a phone
                    sort_sel = ui.select(list(_CONTENT_SORTS), value="Newest")\
                        .props("dense").classes("w-36")
                    # Table-first by default -- matches YT Studio's own
                    # Content tab (a sortable table, not a thumbnail grid);
                    # the grid is still one click away for visual browsing.
                    table_toggle = ui.switch("Table view", value=True)
                    ui.button("Refresh", icon="refresh",
                              on_click=lambda: set_view("library")).props("flat dense color=primary")

            state = {"limit": 48}
            grid_container = ui.column().classes("w-full")

            def render() -> None:
                grid_container.clear()
                cards = stats.library(limit=state["limit"])
                q = (search.value or "").strip().lower()
                if q:
                    cards = [c for c in cards
                             if q in c["title"].lower() or q in c["theme"].lower()]
                with grid_container:
                    if table_toggle.value:
                        _content_table(cards, sort_sel.value)
                    else:
                        _library_grid(cards, on_change=render)
                        if not q and len(cards) >= state["limit"]:
                            ui.button("Load more", icon="expand_more", on_click=load_more)\
                                .props("flat dense color=primary").classes("mt-3")

            def load_more() -> None:
                state["limit"] += 48
                render()

            # No debounce needed: this filters an already-fetched in-memory list
            # (stats.library() reads local files, no network call per keystroke).
            search.on_value_change(render)
            sort_sel.on_value_change(render)
            table_toggle.on_value_change(render)
            render()


_PILL_STATUS_CLASSES = "text-muted text-teal text-rose text-amber"


_LIVE_MODES = {"single": "Loop the latest video", "247": "24/7 with new music"}


def view_live(root) -> None:
    with root:
        with theme.card():
            pill = ui.label().classes("pill")
            detail = ui.label("").classes(theme.SUB)

            def refresh_live_status() -> None:
                st = data.live_status()
                if st is None:
                    pill.text = "○ OFFLINE"
                    pill.classes(remove=_PILL_STATUS_CLASSES, add="text-muted")
                    detail.text = "No active broadcast."
                    return
                kind = "24/7 stream" if st["mode"] == "24/7" else "Looping one video"
                if st["alive"]:
                    pill.text = "🔴 LIVE"
                    pill.classes(remove=_PILL_STATUS_CLASSES, add="text-teal")
                    started = (st.get("started_at") or "")[:16].replace("T", " ")
                    title = st.get("title") or st.get("watch_url") or ""
                    detail.text = f"{kind} · {title} · started {started}"
                else:
                    pill.text = "⚠ CRASHED / STALE"
                    pill.classes(remove=_PILL_STATUS_CLASSES, add="text-rose")
                    detail.text = (f"{kind}: the state file says it is running, but its process "
                                   "is gone. Press End stream to clean up.")

            refresh_live_status()
            ui.timer(5.0, refresh_live_status)

        with theme.card("Live stream", "Loop the latest finished video, or run an endless "
                        "stream that keeps composing new music while it plays."):
            with ui.row().classes("items-end gap-4 flex-wrap"):
                msel = ui.select(_LIVE_MODES, value="single", label="Mode").classes("w-56")
                qsel = ui.select(config.STREAM_QUALITY, value="720p15", label="Quality").classes("w-40")
                psel = ui.select(config.PRIVACY, value="public", label="Privacy").classes("w-36")
            msel.on_value_change(lambda e: qsel.set_visibility(e.value == "single"))

            async def start() -> None:
                if msel.value == "247":
                    args, name = ["run.py", "--stream"], "live 24/7"
                else:
                    args = ["publish.py", "live", "--quality", qsel.value, "--privacy", psel.value]
                    name = "live"
                try:
                    await jobs.manager.run(name, args, slot="stream")
                    ui.notify("Starting live stream…", type="positive")
                except RuntimeError as e:
                    ui.notify(str(e), type="warning")

            async def end() -> None:
                st = data.live_status()
                if st and st["mode"] == "24/7":
                    if not st["alive"]:
                        data.clear_247_state()
                        ui.notify("Cleared a stale 24/7 stream record.", type="info")
                    elif data.stop_247_stream():
                        ui.notify("Stopping the 24/7 stream; it ends the broadcast itself.",
                                  type="positive")
                    else:
                        ui.notify("Couldn't signal the 24/7 stream process.", type="negative")
                    return
                try:
                    await jobs.manager.run("end", ["publish.py", "end"], slot="control")
                except RuntimeError as e:
                    ui.notify(str(e), type="warning")

            async def check_status() -> None:
                try:
                    await jobs.manager.run("status", ["publish.py", "status"], slot="control")
                except RuntimeError as e:
                    ui.notify(str(e), type="warning")

            with ui.row().classes("gap-3 mt-2"):
                start_btn = ui.button("Start stream", icon="sensors", on_click=start)\
                    .props("color=primary")
                end_btn = ui.button("End stream", icon="stop_circle", on_click=end)\
                    .props("color=negative")
                ui.button("Status", icon="info", on_click=check_status).props("flat color=primary")
                kill_btn = ui.button("Force kill", icon="power_settings_new",
                                     on_click=lambda: jobs.manager.cancel(slot="stream"))\
                    .props("flat color=negative")

            def refresh_buttons() -> None:
                streaming = jobs.manager.stream_running()
                live = data.live_status()
                start_btn.set_enabled(not streaming and not (live and live["alive"]))
                end_btn.set_enabled(streaming or live is not None)
                kill_btn.set_enabled(streaming)

            refresh_buttons()
            ui.timer(2.0, refresh_buttons)
        with theme.card("Stream output"):
            def _latest_stream_job():
                cands = [j for j in (jobs.manager.stream, jobs.manager.control) if j]
                return max(cands, key=lambda j: j.started_at) if cands else None
            live_log(_latest_stream_job, height="h-80")


_PILLAR_MARKER_COLOR = {"▲": "text-teal", "▼": "text-rose", " ": "text-amber"}
# echarts itemStyle needs real hex (can't reach into CSS custom properties from
# a JSON series config), so this mirrors _PILLAR_MARKER_COLOR using the same
# theme constants instead of a second set of raw literals.
_PILLAR_MARKER_HEX = {"▲": theme.TEAL, "▼": theme.ROSE, " ": theme.PRIMARY}

# ── Analytics view helpers (pure -- CSV export & multi-video comparison) ──────
# Kept as standalone functions (not inlined in view_analytics) so they're unit
# testable without spinning up NiceGUI -- same convention as
# _card_from_artifacts / _parse_ffmpeg_progress etc. above.
_CSV_COLUMNS = ["video_id", "title", "pillar", "ctr_pct", "views", "watch_min", "likes", "comments"]


def _rows_to_csv(rows: list[dict]) -> str:
    """CSV text from the per-video performance table's row dicts (see
    view_analytics()'s `rows` list) -- one row per tracked video."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_CSV_COLUMNS)
    for r in rows:
        writer.writerow([
            r.get("video_id", ""),
            r.get("title", ""),
            r.get("pillar", ""),
            round((r.get("ctr") or 0) * 100, 2),
            r.get("views", 0),
            r.get("watch_min", 0),
            r.get("likes") if r.get("likes") is not None else "",
            r.get("comments") if r.get("comments") is not None else "",
        ])
    return buf.getvalue()


def _comparison_rows(rows: list[dict], selected_ids: list[str]) -> list[dict]:
    """Subset of per-video performance `rows` matching `selected_ids`, in
    selection order -- feeds the multi-video comparison panel. Reuses the
    data already fetched for the main table; no refetch."""
    by_id = {r["video_id"]: r for r in rows}
    return [by_id[vid] for vid in selected_ids if vid in by_id]


def view_analytics(root) -> None:
    with root:
        from scripts import analytics as analytics_mod

        data_dict = analytics_mod.load_analytics()
        result = analytics_mod.compute_pillar_stats(data_dict)
        history_by_vid = analytics_mod.load_analytics_history()

        async def do_sync() -> None:
            # API calls take seconds per video; run them off the event loop
            # so the panel stays responsive for everyone while syncing.
            before = analytics_mod.load_analytics()
            try:
                after = await asyncio.to_thread(analytics_mod.sync_analytics)
            except Exception as e:  # noqa: BLE001 -- surface any sync failure, don't crash the page
                ui.notify(f"Sync failed: {e}", type="negative")
                return
            n_before = sum(len(v.get("history", [])) for v in before.values() if isinstance(v, dict))
            n_after = sum(len(v.get("history", [])) for v in after.values() if isinstance(v, dict))
            if n_after > n_before:
                ui.notify(f"Synced {n_after - n_before} new snapshot(s)", type="positive")
            else:
                ui.notify("Nothing new to sync: videos need to be 7 to 90 days old, "
                          "once per day.", type="info")
            set_view("analytics")

        with ui.tabs().classes("w-full") as analytics_tabs:
            ui.tab("overview", label="Overview")
            ui.tab("performance", label="Performance")
            ui.tab("audience", label="Audience")
            ui.tab("revenue", label="Revenue")
            ui.tab("content", label="Content")
        with ui.tab_panels(analytics_tabs, value="overview").classes("w-full"):
            with ui.tab_panel("overview").classes("gap-5"):
                with theme.card():
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Which title styles work").classes(theme.H)
                        ui.button("Sync now", icon="sync", on_click=do_sync)\
                            .props("flat dense color=primary")
                    ui.label("Click-through and watch time for each title style, from uploads "
                             "7 to 90 days old. Styles that do better get picked more often for "
                             "future videos.")\
                        .classes(theme.SUB)

                    if not result["by_pillar"]:
                        ui.label("Nothing to show yet. Videos need about a week of views; "
                                 "then press Sync now.")\
                            .classes(theme.SUB + " mt-3")
                    else:
                        with ui.row().classes("w-full gap-4 no-wrap mt-2 overflow-x-auto"):
                            with ui.element("div").classes("stat grow"):
                                ui.label(f"{result['channel_avg_ctr'] * 100:.1f}%").classes("stat-num")
                                ui.label("Channel click-through").classes("stat-lbl")
                            with ui.element("div").classes("stat grow"):
                                ui.label(str(result["n_total"])).classes("stat-num")
                                ui.label("Videos tracked").classes("stat-lbl")

                        pillars = [r["pillar"] for r in result["by_pillar"]]
                        ctrs = [round(r["avg_ctr"] * 100, 2) for r in result["by_pillar"]]
                        colors = [_PILLAR_MARKER_HEX.get(r["marker"], theme.PRIMARY)
                                  for r in result["by_pillar"]]
                        ui.echart({
                            "grid": {"left": 60, "right": 16, "top": 16, "bottom": 40},
                            "xAxis": {"type": "category", "data": pillars,
                                      "axisLabel": {"color": theme.MUTED, "rotate": 20}},
                            "yAxis": {"type": "value", "name": "avg CTR %",
                                      "axisLabel": {"color": theme.MUTED}},
                            "series": [{
                                "type": "bar", "data": [
                                    {"value": v, "itemStyle": {"color": c}}
                                    for v, c in zip(ctrs, colors)
                                ],
                            }],
                        }).classes("w-full mt-3").style("height:260px")

                        with ui.column().classes("w-full gap-1 mt-2 table-scroll"):
                            for row in result["by_pillar"]:
                                color_cls = _PILLAR_MARKER_COLOR.get(row["marker"], "text-amber")
                                theme.data_row([
                                    {"text": row["marker"] or "·", "color": color_cls, "classes": ""},
                                    {"text": row["pillar"], "classes": "text-sm font-medium", "width": "lg"},
                                    {"text": f"{row['avg_ctr'] * 100:.1f}% CTR", "color": color_cls,
                                     "classes": "text-sm", "width": "md"},
                                    {"text": f"{row['avg_views']:.0f} avg views", "classes": theme.SUB},
                                    {"text": f"{row['avg_watch_min']:.0f} min avg watch", "classes": theme.SUB},
                                    {"text": f"n={row['n']}", "classes": theme.SUB},
                                ])

                # ── Bandit arm posteriors ───────────────────────────────────────────
                with ui.element("div").classes("studio-card w-full"):
                    ui.label("How often each title style gets picked").classes(theme.H)
                    ui.label("A video counts as a win when its engagement beats the channel "
                             "median. The bar is each style's estimated win rate; it starts at "
                             "50% and moves as results come in. n is the number of videos.")\
                        .classes(theme.SUB)
                    posteriors = analytics_mod.pillar_bandit_posteriors(analytics=data_dict)
                    with ui.column().classes("w-full gap-1 mt-2"):
                        for pillar, st in sorted(posteriors.items(), key=lambda kv: -kv[1]["mean"]):
                            with ui.row().classes("w-full items-center gap-3 no-wrap data-row"):
                                ui.label(pillar).classes("text-sm font-medium dcol-md")
                                ui.linear_progress(value=st["mean"], show_value=False)\
                                    .classes("grow").props("rounded color=primary")
                                ui.label(f"{st['mean'] * 100:.1f}%").classes("text-sm dcol-xs")
                                ui.label(f"n={st['n']:.0f}").classes(theme.SUB)

                # ── Title-feature bandit posteriors ─────────────────────────────────
                with ui.element("div").classes("studio-card w-full"):
                    ui.label("What in a title helps").classes(theme.H)
                    ui.label("The same win rate, split by features of the published title: "
                             "length, emoji, and a study/focus/relax/sleep keyword list. Title "
                             "picks lean toward features that win.")\
                        .classes(theme.SUB)
                    feature_posteriors = analytics_mod.title_feature_bandit_posteriors(analytics=data_dict)
                    if not feature_posteriors:
                        ui.label("No title performance data logged yet — needs synced analytics "
                                 "on at least a few published videos.").classes(theme.SUB + " mt-3")
                    else:
                        with ui.column().classes("w-full gap-3 mt-2"):
                            for dim, buckets in sorted(feature_posteriors.items()):
                                ui.label(dim.replace("_", " ")).classes("text-sm font-semibold")
                                with ui.column().classes("w-full gap-1"):
                                    for bucket, st in sorted(buckets.items(), key=lambda kv: -kv[1]["mean"]):
                                        with ui.row().classes("w-full items-center gap-3 no-wrap data-row"):
                                            ui.label(bucket).classes("text-sm font-medium dcol-md")
                                            ui.linear_progress(value=st["mean"], show_value=False)\
                                                .classes("grow").props("rounded color=primary")
                                            ui.label(f"{st['mean'] * 100:.1f}%").classes("text-sm dcol-xs")
                                            ui.label(f"α={st['alpha']:.0f} β={st['beta']:.0f}")\
                                                .classes(f"{theme.SUB} dcol-md")
                                            ui.label(f"n={st['n']:.0f}").classes(theme.SUB)

                # ── Cohort growth curves + forecast + viral-moment flags ────────────
                _TOP_N = 6
                _cohort_candidates = []
                for vid, d in data_dict.items():
                    m = analytics_mod.latest_metrics(d)
                    hist = history_by_vid.get(vid, [])
                    if not hist:
                        continue
                    _cohort_candidates.append((vid, d, hist, float(m.get("views") or 0)))
                _cohort_candidates.sort(key=lambda t: -t[3])
                top_videos = _cohort_candidates[:_TOP_N]

            with ui.tab_panel("performance").classes("gap-5"):
                with ui.element("div").classes("studio-card w-full"):
                    ui.label("Growth curves & forecasts").classes(theme.H)
                    ui.label("Total views by days since upload, for the top "
                             f"{_TOP_N} videos, lined up so different upload dates compare "
                             "fairly. The forecast extends recent daily views 7 and 30 days "
                             "ahead once there are 4 syncs.").classes(theme.SUB)

                    if not top_videos:
                        ui.label("No longitudinal history yet — needs at least one synced snapshot "
                                 "per video.").classes(theme.SUB + " mt-3")
                    else:
                        series = []
                        for vid, d, hist, _ in top_videos:
                            upload_date = d.get("upload_date")
                            title = d.get("title") or vid
                            points = []
                            try:
                                d0 = datetime.date.fromisoformat(upload_date) if upload_date else None
                            except ValueError:
                                d0 = None
                            for snap in hist:
                                sdate, sviews = snap.get("date"), snap.get("views")
                                if not sdate or sviews is None or d0 is None:
                                    continue
                                try:
                                    day_offset = (datetime.date.fromisoformat(sdate) - d0).days
                                except ValueError:
                                    continue
                                points.append([day_offset, sviews])
                            points.sort(key=lambda p: p[0])
                            if points:
                                series.append({"name": title[:40], "type": "line", "showSymbol": True,
                                               "data": points})

                        ui.echart({
                            "grid": {"left": 60, "right": 16, "top": 40, "bottom": 40},
                            "legend": {"top": 0, "textStyle": {"color": theme.MUTED, "fontSize": 10}},
                            "tooltip": {"trigger": "axis"},
                            "xAxis": {"type": "value", "name": "days since upload",
                                      "axisLabel": {"color": theme.MUTED}},
                            "yAxis": {"type": "value", "name": "cumulative views",
                                      "axisLabel": {"color": theme.MUTED}},
                            "series": series,
                        }).classes("w-full mt-1").style("height:280px")

                        with ui.column().classes("w-full gap-1 mt-3"):
                            ui.label("Forecast (7d / 30d) & viral-moment flags").classes(
                                "text-sm font-medium")
                            for vid, d, hist, current_views in top_videos:
                                title = d.get("title") or vid
                                forecast = analytics_mod.forecast_views(hist)
                                viral = analytics_mod.detect_viral_moment(hist)
                                cells = [
                                    {"text": title[:40], "classes": "text-sm truncate", "width": "grow"},
                                    {"text": f"now {stats.fmt_count(int(current_views))}",
                                     "classes": theme.SUB, "width": "md"},
                                ]
                                if forecast:
                                    cells.append({
                                        "text": f"7d ~{stats.fmt_count(int(forecast['forecast']['7d']))}",
                                        "classes": theme.SUB, "width": "md"})
                                    cells.append({
                                        "text": f"30d ~{stats.fmt_count(int(forecast['forecast']['30d']))}",
                                        "classes": theme.SUB, "width": "md"})
                                else:
                                    cells.append({"text": "forecast: needs more history",
                                                  "classes": theme.SUB, "width": "xl"})
                                if viral and viral.get("flagged"):
                                    up = viral["direction"] == "up"
                                    color_cls = "text-teal" if up else "text-rose"
                                    cells.append({"icon": "trending_up" if up else "trending_down",
                                                  "color": color_cls})
                                    cells.append({"text": f"viral moment {viral['change_point_date']}",
                                                  "classes": f"text-sm {color_cls}"})
                                theme.data_row(cells)

                rows: list[dict] = []
                if data_dict:
                    with theme.card(classes="w-full"):
                        with ui.row().classes("w-full items-center justify-between"):
                            ui.label("Per-video performance").classes(theme.H)
                            export_btn = ui.button("Export CSV", icon="download").props(
                                "flat dense color=primary")
                        ui.label("Every tracked upload, most-clicked first. Click a row to open it "
                                 "(retention chart, player) the same way as from Library. Check up to "
                                 "4 rows to compare them side-by-side below.")\
                            .classes(theme.SUB)

                        vids = list(data_dict.keys())
                        engagement = stats.video_engagement(vids)
                        card_by_vid = {c["video_id"]: c for c in stats.library(limit=200)
                                       if c.get("video_id")}

                        for vid, d in data_dict.items():
                            eng = engagement.get(vid, {})
                            m = analytics_mod.latest_metrics(d)
                            rows.append({
                                "video_id": vid,
                                "title": d.get("title") or vid,
                                "pillar": d.get("pillar") or "—",
                                "ctr": m.get("videoThumbnailImpressionsClickRate", 0) or 0,
                                "views": int(m.get("views", 0) or 0),
                                "watch_min": round(m.get("averageViewDuration", 0) or 0) // 60,
                                "likes": eng.get("likes"),
                                "comments": eng.get("comments"),
                            })
                        rows.sort(key=lambda r: r["ctr"], reverse=True)

                        export_btn.on_click(lambda: ui.download(
                            _rows_to_csv(rows).encode("utf-8"),
                            "analytics_per_video.csv", media_type="text/csv"))

                        # ── Multi-video comparison (pins 2-4 rows, reuses `rows` -- no
                        # refetch) ─────────────────────────────────────────────────
                        _selected_ids: list[str] = []
                        comparison_container = ui.column().classes("w-full")

                        def _render_comparison() -> None:
                            comparison_container.clear()
                            with comparison_container:
                                if len(_selected_ids) < 2:
                                    return
                                compare = _comparison_rows(rows, _selected_ids)
                                ui.separator().classes("mt-3")
                                ui.label(f"Comparing {len(compare)} videos").classes(
                                    "text-sm font-medium mt-2")
                                ui.echart({
                                    "grid": {"left": 60, "right": 16, "top": 40, "bottom": 60},
                                    "legend": {"top": 0, "textStyle": {"color": theme.MUTED,
                                                                        "fontSize": 10}},
                                    "tooltip": {"trigger": "axis"},
                                    "xAxis": {"type": "category",
                                              "data": ["CTR %", "Views (100s)", "Watch (min)",
                                                       "Likes", "Comments"],
                                              "axisLabel": {"color": theme.MUTED, "rotate": 15}},
                                    "yAxis": {"type": "value", "axisLabel": {"color": theme.MUTED}},
                                    "series": [{
                                        "name": c["title"][:30], "type": "bar",
                                        "data": [
                                            round(c["ctr"] * 100, 2),
                                            round(c["views"] / 100, 1),
                                            c["watch_min"],
                                            c["likes"] or 0,
                                            c["comments"] or 0,
                                        ],
                                    } for c in compare],
                                }).classes("w-full mt-1").style("height:260px")
                                with ui.column().classes("w-full gap-1 mt-2 table-scroll"):
                                    theme.data_row([
                                        {"text": "Title", "width": "grow"},
                                        {"text": "CTR", "width": "xs"},
                                        {"text": "Views", "width": "sm"},
                                        {"text": "Watch", "width": "xs"},
                                        {"text": "Likes", "width": "xs"},
                                        {"text": "Comments", "width": "sm"},
                                    ], header=True)
                                    for c in compare:
                                        theme.data_row([
                                            {"text": c["title"][:40], "classes": "text-sm truncate",
                                             "width": "grow"},
                                            {"text": f"{c['ctr'] * 100:.1f}%", "classes": "text-sm",
                                             "width": "xs"},
                                            {"text": stats.fmt_count(c["views"]), "classes": "text-sm",
                                             "width": "sm"},
                                            {"text": f"{c['watch_min']}m", "classes": "text-sm",
                                             "width": "xs"},
                                            {"text": stats.fmt_count(c["likes"])
                                             if c["likes"] is not None else "—",
                                             "classes": "text-sm", "width": "xs"},
                                            {"text": stats.fmt_count(c["comments"])
                                             if c["comments"] is not None else "—",
                                             "classes": "text-sm", "width": "sm"},
                                        ])

                        def _toggle_selected(vid: str, checked: bool) -> None:
                            if checked:
                                if len(_selected_ids) >= 4:
                                    ui.notify("Comparison is limited to 4 videos — "
                                              "uncheck one first.", type="warning")
                                    return
                                if vid not in _selected_ids:
                                    _selected_ids.append(vid)
                            elif vid in _selected_ids:
                                _selected_ids.remove(vid)
                            _render_comparison()

                        with ui.column().classes(
                                "w-full gap-1 mt-2 table-scroll max-h-[420px] overflow-y-auto"):
                            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                                ui.label("").classes("shrink-0 w-7")
                                theme.data_row([
                                    {"text": "Title", "width": "grow"},
                                    {"text": "Pillar", "width": "md"},
                                    {"text": "CTR", "width": "xs"},
                                    {"text": "Views", "width": "sm"},
                                    {"text": "Watch", "width": "xs"},
                                    {"text": "Likes", "width": "xs"},
                                    {"text": "Comments", "width": "sm"},
                                ], header=True, classes="grow")
                            for r in rows:
                                card = card_by_vid.get(r["video_id"])

                                def _open(r=r, card=card) -> None:
                                    if card:
                                        _open_detail([card], 0)
                                    elif r["video_id"]:
                                        ui.navigate.to(
                                            f"https://youtube.com/watch?v={r['video_id']}",
                                            new_tab=True)

                                with ui.row().classes("w-full items-center gap-2 no-wrap"):
                                    ui.checkbox(value=False, on_change=(
                                        lambda e, vid=r["video_id"]: _toggle_selected(vid, e.value)
                                    )).props("dense").classes("shrink-0")
                                    theme.data_row([
                                        {"text": r["title"], "classes": "text-sm truncate", "width": "grow"},
                                        {"text": r["pillar"], "classes": "text-sm", "width": "md"},
                                        {"text": f"{r['ctr'] * 100:.1f}%", "classes": "text-sm", "width": "xs"},
                                        {"text": stats.fmt_count(r["views"]), "classes": "text-sm", "width": "sm"},
                                        {"text": f"{r['watch_min']}m", "classes": "text-sm", "width": "xs"},
                                        {"text": stats.fmt_count(r["likes"]) if r["likes"] is not None else "—",
                                         "classes": "text-sm", "width": "xs"},
                                        {"text": stats.fmt_count(r["comments"]) if r["comments"] is not None else "—",
                                         "classes": "text-sm", "width": "sm"},
                                    ], on_click=_open, classes="grow")

                swapped = [{"video_id": vid, **d} for vid, d in data_dict.items() if d.get("thumb_swapped")]
                ab_tested = sorted(
                    ([{"video_id": vid, **d} for vid, d in data_dict.items()
                      if d.get("thumb_ab_p") is not None]),
                    key=lambda s: s["thumb_ab_p"],
                )
                with theme.card("Thumbnail A/B testing",
                                "The daily sync swaps a 7 to 30 day old video to its second "
                                "thumbnail only when its click-through is clearly below the "
                                "channel's, by a significance test corrected for checking many "
                                "videos at once."):
                    if not swapped:
                        ui.label("No swaps yet.").classes(theme.SUB + " mt-2")
                    else:
                        with ui.column().classes("w-full gap-1 mt-2 table-scroll"):
                            for s in swapped:
                                theme.data_row([
                                    {"icon": "swap_horiz", "color": "text-amber"},
                                    {"text": s.get("title", s["video_id"]), "classes": "text-sm", "width": "xl"},
                                    {"text": f"swapped {s.get('thumb_swapped_at', '')[:10]}", "classes": theme.SUB},
                                ])

                    if ab_tested:
                        ui.label("Latest test result per video").classes(
                            "text-sm font-medium mt-4")
                        with ui.column().classes("w-full gap-1 mt-1 table-scroll"):
                            theme.data_row([
                                {"text": "Title", "width": "grow"},
                                {"text": "CTR", "width": "xs"},
                                {"text": "z", "width": "xs"},
                                {"text": "p-value", "width": "sm"},
                                {"text": "variant", "width": "xs"},
                            ], header=True)
                            for s in ab_tested:
                                m = analytics_mod.latest_metrics(s)
                                p_value = s["thumb_ab_p"]
                                significant = p_value < 0.05
                                color_cls = "text-rose" if significant else theme.SUB
                                theme.data_row([
                                    {"text": s.get("title", s["video_id"])[:40],
                                     "classes": "text-sm truncate", "width": "grow"},
                                    {"text": f"{(m.get('videoThumbnailImpressionsClickRate') or 0) * 100:.1f}%",
                                     "classes": "text-sm", "width": "xs"},
                                    {"text": f"{s.get('thumb_ab_z', 0):.2f}", "classes": "text-sm", "width": "xs"},
                                    {"text": f"{p_value:.4f}" + (" *" if significant else ""),
                                     "classes": f"text-sm {color_cls}", "width": "sm"},
                                    {"text": s.get("ab_variant") or "—", "classes": theme.SUB, "width": "xs"},
                                ])

                # ── Traffic-source breakdown + subscriber growth (YT Analytics API) ──
            with ui.tab_panel("audience").classes("gap-5"):
                with ui.element("div").classes("studio-card w-full"):
                    ui.label("Traffic sources & subscriber growth").classes(theme.H)
                    ui.label("Where views came from in the last 28 days, and subscribers "
                             "gained or lost per day over the last 90.").classes(theme.SUB)

                    traffic = stats.traffic_sources()
                    if not traffic:
                        ui.label("No traffic-source data yet — needs YouTube connected in Settings "
                                 "and some recent view volume.").classes(theme.SUB + " mt-3")
                    else:
                        ui.echart({
                            "tooltip": {"trigger": "item"},
                            "legend": {"orient": "vertical", "left": "left",
                                       "textStyle": {"color": theme.MUTED, "fontSize": 10}},
                            "series": [{
                                "type": "pie", "radius": ["35%", "65%"],
                                "data": [{"name": t["source"], "value": t["views"]} for t in traffic],
                                "label": {"color": theme.MUTED},
                            }],
                        }).classes("w-full mt-2").style("height:260px")

                    growth = stats.subscriber_growth()
                    if growth:
                        ui.label("Subscriber growth (net gained/lost per day)").classes(
                            "text-sm font-medium mt-4")
                        ui.echart({
                            "grid": {"left": 50, "right": 16, "top": 20, "bottom": 40},
                            "tooltip": {"trigger": "axis"},
                            "xAxis": {"type": "category", "data": [g["date"] for g in growth],
                                      "axisLabel": {"color": theme.MUTED, "rotate": 30, "fontSize": 9}},
                            "yAxis": {"type": "value", "name": "net subs",
                                      "axisLabel": {"color": theme.MUTED}},
                            "series": [{
                                "type": "bar",
                                "data": [{"value": g["net"],
                                          "itemStyle": {"color": theme.TEAL if g["net"] >= 0
                                                        else theme.ROSE}}
                                         for g in growth],
                            }],
                        }).classes("w-full mt-2").style("height:220px")
                    elif traffic:
                        # Only show a second "no data" note if the traffic panel above didn't
                        # already explain the not-connected case.
                        ui.label("No subscriber growth data yet.").classes(theme.SUB + " mt-3")

                # ── Revenue / RPM / CPM (opt-in — see Settings: Connect monetary analytics) ──
            with ui.tab_panel("revenue").classes("gap-5"):
                with ui.element("div").classes("studio-card w-full"):
                    ui.label("Revenue & RPM").classes(theme.H)
                    if not stats.revenue_available():
                        ui.label(
                            "Not connected. Revenue/RPM/CPM figures need the "
                            "yt-analytics-monetary.readonly scope, which is intentionally NOT "
                            "requested by the normal YouTube login (so ordinary uploads/analytics "
                            "never trigger a surprise consent screen). Opt in from Settings -> "
                            "'Revenue & RPM' to grant just this extra scope via a separate consent "
                            "flow.").classes(theme.SUB + " mt-2")
                        ui.button("Go to Settings", icon="settings",
                                  on_click=lambda: set_view("settings"))\
                            .props("flat dense color=primary").classes("mt-2")
                    else:
                        revenue = stats.revenue_stats()
                        if not revenue:
                            ui.label("Connected, but no revenue data returned yet (channel may not "
                                     "be monetized, or too new for estimates).").classes(
                                theme.SUB + " mt-2")
                        else:
                            total_rev = sum(r["revenue"] for r in revenue)
                            avg_cpm = (sum(r["cpm"] for r in revenue) / len(revenue)) if revenue else 0
                            with ui.row().classes("w-full gap-4 no-wrap mt-2"):
                                with ui.element("div").classes("stat grow"):
                                    ui.label(f"${total_rev:.2f}").classes("stat-num")
                                    ui.label("Est. revenue (28d)").classes("stat-lbl")
                                with ui.element("div").classes("stat grow"):
                                    ui.label(f"${avg_cpm:.2f}").classes("stat-num")
                                    ui.label("Avg CPM").classes("stat-lbl")
                            ui.echart({
                                "grid": {"left": 50, "right": 16, "top": 20, "bottom": 40},
                                "tooltip": {"trigger": "axis"},
                                "xAxis": {"type": "category", "data": [r["date"] for r in revenue],
                                          "axisLabel": {"color": theme.MUTED, "rotate": 30,
                                                        "fontSize": 9}},
                                "yAxis": {"type": "value", "name": "$ est. revenue",
                                          "axisLabel": {"color": theme.MUTED}},
                                "series": [{"type": "line", "data": [r["revenue"] for r in revenue],
                                            "smooth": True, "areaStyle": {"opacity": 0.15},
                                            "color": theme.PRIMARY}],
                            }).classes("w-full mt-3").style("height:220px")

            with ui.tab_panel("content").classes("gap-5"):
                # ── Playlist-level aggregation (pillar -> playlist mapping from
                # scripts/playlist_curation.py) ───────────────────────────────────────
                if data_dict:
                    plist = analytics_mod.playlist_stats(data_dict)
                    with ui.element("div").classes("studio-card w-full"):
                        ui.label("Playlist performance").classes(theme.H)
                        ui.label("Videos grouped by the playlist they go into. 'Unassigned' "
                                 "means no playlist is set for that title style; set "
                                 "YT_PLAYLIST_<STYLE> in .env to add one.").classes(theme.SUB)
                        with ui.column().classes("w-full gap-1 mt-2 table-scroll"):
                            theme.data_row([
                                {"text": "Playlist", "width": "xl"},
                                {"text": "Pillars", "width": "lg"},
                                {"text": "Avg CTR", "width": "sm"},
                                {"text": "Avg views", "width": "sm"},
                                {"text": "n", "width": "xs"},
                            ], header=True)
                            for p in plist:
                                label = p["playlist_id"] or "Unassigned"
                                theme.data_row([
                                    {"text": label, "classes": "text-sm font-medium truncate", "width": "xl"},
                                    {"text": ", ".join(p["pillars"]), "classes": theme.SUB, "width": "lg"},
                                    {"text": f"{p['avg_ctr'] * 100:.1f}%", "classes": "text-sm", "width": "sm"},
                                    {"text": stats.fmt_count(int(p["avg_views"])), "classes": "text-sm",
                                     "width": "sm"},
                                    {"text": str(p["n"]), "classes": theme.SUB, "width": "xs"},
                                ])

                # ── Upload history (upload_log.json, full metadata -- distinct from
                # Studio's "Recent runs", which is only this webui session's last 20
                # jobs. This is the full all-time record: which SEO pillar, which
                # title variant won the bandit pick, and the concept each video was
                # generated from -- previously backed by data.upload_history() with
                # no UI anywhere to see it. ──────────────────────────────────────────
                with theme.card("Upload history", "Every upload with the title style, concept "
                                "and title it used."):
                    entries = data.upload_history(limit=30)
                    if not entries:
                        ui.label("No uploads recorded yet.").classes(theme.SUB + " mt-1")
                    else:
                        with ui.column().classes("w-full gap-1 mt-2 table-scroll"):
                            theme.data_row([
                                {"text": "When", "width": "md"},
                                {"text": "Title", "width": "xl"},
                                {"text": "Pillar", "width": "sm"},
                                {"text": "Concept", "width": "xl"},
                                {"text": "Duration", "width": "xs"},
                            ], header=True)
                            for e in entries:
                                ts = (e.get("timestamp") or "")[:16].replace("T", " ")
                                dur = e.get("duration_secs")
                                dur_txt = f"{int(dur // 60)}min" if dur else "—"
                                variants = e.get("title_variants") or []
                                chosen_idx = e.get("title_chosen_idx")
                                variant_note = (f" (variant {chosen_idx + 1}/{len(variants)})"
                                                 if variants and chosen_idx is not None else "")
                                url = e.get("url")

                                def _row_extra(url=url) -> None:
                                    if url:
                                        ui.button(icon="open_in_new",
                                                  on_click=lambda url=url: ui.navigate.to(url, new_tab=True))\
                                            .props("flat dense round color=primary")

                                theme.data_row([
                                    {"text": ts, "classes": theme.SUB, "width": "md"},
                                    {"text": (e.get("title") or "—") + variant_note,
                                     "classes": "text-sm font-medium truncate", "width": "xl"},
                                    {"text": e.get("pillar") or "—", "classes": theme.SUB, "width": "sm"},
                                    {"text": e.get("concept") or "—", "classes": f"{theme.SUB} truncate",
                                     "width": "xl"},
                                    {"text": dur_txt, "classes": theme.SUB, "width": "xs"},
                                ], extra=_row_extra)


def view_automation(root) -> None:
    with root:
        with theme.card("Auto-upload schedule",
                        "Makes and uploads a video on a schedule. It runs on its own, so it "
                        "keeps going when this panel or your browser is closed."):
            with ui.row().classes("items-center gap-2"):
                pill = ui.label().classes("pill")
                sub = ui.label("").classes(theme.SUB)
            next_lbl = ui.label("").classes(theme.SUB)
            progress_lbl = ui.label("").classes(theme.SUB)
            progress_bar = ui.linear_progress(value=0, show_value=False)\
                .props("rounded color=amber").classes("w-full")
            progress_bar.visible = False
            fallback_lbl = ui.label("").classes("text-sm text-amber")

            def refresh_fallback_state() -> None:
                st = automation.auto_run_state()
                if st["in_fallback"]:
                    fallback_lbl.text = (
                        f"⚠ {st['consecutive_failures']} consecutive auto-run failures — "
                        f"forcing the lightest duration tier until one succeeds.")
                    fallback_lbl.visible = True
                elif st["consecutive_failures"]:
                    fallback_lbl.text = f"{st['consecutive_failures']} recent failure(s), not yet in fallback."
                    fallback_lbl.visible = True
                else:
                    fallback_lbl.visible = False

            def refresh_status() -> None:
                st = automation.status()
                if not st["installed"]:
                    pill.text = "⚠ NOT INSTALLED"
                    pill.classes(remove=_PILL_STATUS_CLASSES, add="text-amber")
                    sub.text = "Run deploy/setup.sh on the server to set it up."
                    next_lbl.text = ""
                    for b in (start_btn, stop_btn, boot_btn, run_now_btn, hour_sel, every_sel, apply_btn):
                        b.visible = False
                    return
                for b in (start_btn, stop_btn, boot_btn, run_now_btn, hour_sel, every_sel, apply_btn):
                    b.visible = True
                if st["running_now"]:
                    pill.text = "● RUNNING NOW"
                    pill.classes(remove=_PILL_STATUS_CLASSES, add="text-amber")
                    p = automation.render_progress() or {}
                    stage = {"generating": "Generating music/visual/SEO",
                             "encoding": "Encoding final video",
                             "uploading": "Uploading to YouTube"}.get(p.get("stage"), "Working")
                    if p.get("percent") is not None:
                        eta = p.get("eta_secs")
                        eta_txt = f" · ETA {_fmt_elapsed(eta)}" if eta else ""
                        speed_txt = f" · {p['speed']:.2f}x speed" if p.get("speed") else ""
                        progress_lbl.text = f"{stage} · {p['percent']:.0f}%{eta_txt}{speed_txt}"
                        progress_bar.props(remove="indeterminate")
                        progress_bar.value = p["percent"] / 100
                    else:
                        progress_lbl.text = f"{stage}…"
                        progress_bar.props(add="indeterminate")
                    progress_lbl.visible = True
                    progress_bar.visible = True
                elif st["active"]:
                    pill.text = "● ARMED"
                    pill.classes(remove=_PILL_STATUS_CLASSES, add="text-teal")
                    progress_lbl.visible = False
                    progress_bar.visible = False
                else:
                    pill.text = "○ STOPPED"
                    pill.classes(remove=_PILL_STATUS_CLASSES, add="text-rose")
                    progress_lbl.visible = False
                    progress_bar.visible = False
                sub.text = (f"Every {st['every_hours']}h, starting {st['start_hour']:02d}:00"
                            f" · boot: {'yes' if st['enabled'] else 'no'}")
                bits = []
                if st["next_run"]:
                    bits.append(f"next run {st['next_run']}")
                if st["last_run"]:
                    bits.append(f"last run {st['last_run']}")
                next_lbl.text = " · ".join(bits)
                boot_btn.text = "Disable start-at-boot" if st["enabled"] else "Enable start-at-boot"
                if not hour_sel._edited:
                    hour_sel.value = st["start_hour"]
                if not every_sel._edited:
                    every_sel.value = st["every_hours"]
                refresh_fallback_state()

            async def do_start() -> None:
                try:
                    await automation.start()
                    ui.notify("Schedule armed", type="positive")
                except RuntimeError as e:
                    ui.notify(str(e), type="negative")
                refresh_status()

            async def do_stop() -> None:
                try:
                    await automation.stop()
                    ui.notify("Schedule stopped", type="warning")
                except RuntimeError as e:
                    ui.notify(str(e), type="negative")
                refresh_status()

            async def do_toggle_boot() -> None:
                try:
                    await automation.set_enabled(not automation.status()["enabled"])
                except RuntimeError as e:
                    ui.notify(str(e), type="negative")
                refresh_status()

            async def do_run_now() -> None:
                try:
                    # This kicks off a systemctl call that returns once the run
                    # itself completes (Type=oneshot) -- await here just yields
                    # the event loop back while the worker thread waits, it does
                    # NOT block other clients. See webui/automation.py.
                    await automation.run_now()
                    ui.notify("Triggered an immediate run — see the log below", type="positive")
                except RuntimeError as e:
                    ui.notify(str(e), type="negative")
                refresh_status()

            async def do_apply_schedule() -> None:
                try:
                    await automation.set_schedule(int(hour_sel.value), int(every_sel.value))
                    hour_sel._edited = every_sel._edited = False
                    ui.notify("Schedule updated", type="positive")
                except (RuntimeError, ValueError) as e:
                    ui.notify(str(e), type="negative")
                refresh_status()

            with ui.row().classes("items-end gap-4 mt-2"):
                hour_sel = ui.number("Start hour (0-23)", value=0, min=0, max=23, format="%d")\
                    .classes("w-40")
                every_sel = ui.select(automation.VALID_INTERVALS, value=24,
                                      label="Every N hours").classes("w-40")
                # Track manual edits so the periodic refresh doesn't clobber in-progress input.
                hour_sel._edited = False
                every_sel._edited = False
                hour_sel.on_value_change(lambda: setattr(hour_sel, "_edited", True))
                every_sel.on_value_change(lambda: setattr(every_sel, "_edited", True))
                apply_btn = ui.button("Apply schedule", icon="schedule", on_click=do_apply_schedule)\
                    .props("color=secondary")

            with ui.row().classes("gap-3 mt-2"):
                start_btn = ui.button("Arm", icon="play_arrow", on_click=do_start)\
                    .props("color=primary")
                stop_btn = ui.button("Stop", icon="stop", on_click=do_stop)\
                    .props("color=negative")
                boot_btn = ui.button("", on_click=do_toggle_boot).props("flat color=primary")
                run_now_btn = ui.button("Run now", icon="bolt", on_click=do_run_now)\
                    .props("flat color=primary")
                ui.button("Refresh", icon="refresh", on_click=refresh_status)\
                    .props("flat color=primary")

            refresh_status()
            ui.timer(5.0, refresh_status)

        # ── Posting-time recommendation (suggestion only, opt-in apply) ──────
        # Joins upload_log.json timestamps with assets/analytics_log.json view
        # performance (scripts/posting_time.py) to suggest a better hour/day.
        # Deliberately never calls automation.set_schedule() itself -- this
        # pipeline controls a real, public upload, so a schedule change stays
        # a two-click action: "Use this hour" only pre-fills the form above,
        # the human still has to press "Apply schedule".
        with theme.card("Recommended posting time",
                        "Which upload hour got the most views so far. It only fills in "
                        "the hour above; nothing changes until you press Apply schedule."):
            rec_label = ui.label("Checking…").classes(theme.SUB)
            rec_actions = ui.row().classes("items-center gap-3 mt-1")

            def refresh_recommendation() -> None:
                from scripts import posting_time
                rec = posting_time.recommend()
                rec_actions.clear()
                if not rec["available"]:
                    rec_label.text = f"Not enough data yet — {rec['reason']}"
                    return
                hour = rec["best_hour_utc"]
                hour_txt = f"{hour:02d}:00" if hour is not None else "only one hour tried so far"
                rec_label.text = (
                    f"Best hour (UTC): {hour_txt}  ·  "
                    f"Best day: {rec['best_day'] or 'only one day tried so far'}  ·  "
                    f"based on {rec['n_samples']} upload(s) with analytics data")

                def use_hour() -> None:
                    hour_sel.value = rec["best_hour_utc"]
                    hour_sel._edited = True
                    ui.notify("Filled in the recommended hour below — click "
                              "\"Apply schedule\" to actually change it.", type="info")

                if hour is not None:
                    with rec_actions:
                        ui.button("Use this hour", icon="auto_awesome", on_click=use_hour) \
                            .props("flat dense color=secondary")

            refresh_recommendation()

        # ── Resource usage / last exit status (systemd unit introspection) ──
        # Additive block, separate from the schedule card above -- reads
        # MemoryHigh/MemoryMax/MemoryCurrent + ExecMainStatus/ExecMainCode
        # off lofi-auto.service via auto_service.resource_status() (built on
        # the same _systemctl()/`systemctl show` helper the rest of that
        # module already uses). The subprocess call is real I/O, so it's
        # offloaded to a thread rather than blocking the event loop directly.
        with theme.card("Resource usage & last exit status",
                        "Memory the scheduled job is using against its limit, and how "
                        "its last run ended."):
            res_cols = ui.row().classes("w-full gap-4 no-wrap flex-wrap")
            res_note = ui.label("").classes(theme.SUB)

            def _fmt_bytes(n: int | None) -> str:
                if n is None:
                    return "—"
                for unit in ("B", "KB", "MB", "GB"):
                    if n < 1024:
                        return f"{n:.0f} {unit}"
                    n /= 1024
                return f"{n:.1f} TB"

            async def refresh_resources() -> None:
                if not automation.status()["installed"]:
                    res_note.text = "Install lofi-auto.timer to see resource usage."
                    return
                try:
                    rs = await asyncio.to_thread(automation.resource_status)
                except Exception as e:
                    res_note.text = f"Couldn't read systemd status: {e}"
                    return
                res_cols.clear()
                with res_cols:
                    for key, label in [("memory_current", "Current"),
                                        ("memory_high", "High watermark"),
                                        ("memory_max", "Hard limit")]:
                        with ui.element("div").classes("stat grow"):
                            ui.label(_fmt_bytes(rs[key])).classes("stat-num")
                            ui.label(label).classes("stat-lbl")
                code = rs.get("exec_main_code") or "—"
                status_num = rs.get("exec_main_status")
                ok = code == "exited" and status_num in ("0", 0)
                color_cls = "text-teal" if ok else ("text-rose" if code != "—" else "text-muted")
                res_note.classes(replace=f"text-sm {color_cls}")
                res_note.text = (f"Last run: {code}"
                                  + (f", exit code {status_num}" if status_num is not None else ""))

            ui.timer(0.1, refresh_resources, once=True)
            ui.timer(10.0, refresh_resources)

        # ── Encode speed history ────────────────────────────────────────────
        # The real, measured-not-guessed number the dynamic duration picker
        # (publish.py's _pick_auto_duration) actually runs on -- watching it
        # here is how you'd notice this box getting slower/faster/switching
        # encoder paths over time instead of that only ever being an
        # invisible input to a background calculation.
        speed_hist = automation.encode_speed_history()
        if speed_hist:
            with theme.card("Encode speed history", "How fast this machine encoded each "
                            "past render (1.0 = real time). Scheduled runs pick a video "
                            "length that finishes in time at this speed."):
                series = []
                all_labels: list[str] = []
                for key, color in (("vaapi", theme.PRIMARY), ("software", theme.SECONDARY)):
                    samples = speed_hist.get(key) or []
                    if not samples:
                        continue
                    series.append({
                        "name": key, "type": "line", "data": samples,
                        "itemStyle": {"color": color}, "lineStyle": {"color": color},
                        "symbolSize": 8,
                    })
                    if len(samples) > len(all_labels):
                        all_labels = [f"run {i + 1}" for i in range(len(samples))]
                ui.echart({
                    "grid": {"left": 8, "right": 16, "top": 32, "bottom": 24,
                             "containLabel": True},
                    "legend": {"top": 0, "textStyle": {"color": theme.MUTED, "fontSize": 10}},
                    "tooltip": {"trigger": "axis"},
                    "xAxis": {"type": "category", "data": all_labels,
                              "axisLabel": {"color": theme.MUTED, "fontSize": 10}},
                    "yAxis": {"type": "value", "name": "realtime ×",
                              "axisLabel": {"color": theme.MUTED}},
                    "series": series,
                }).classes("w-full").style("height:220px")

        # Live tail of the lofi-auto systemd journal now lives on the Logs
        # page (view_logs), alongside job history and the admin audit log,
        # instead of being the only log surface reachable from this tab.


# ─────────────────────────────────────────────────────────────────────────────
# Content calendar (Stage 2 "automation depth" — additive block, new page)
#
# Shows a merged timeline of past uploads + future-scheduled uploads
# (upload_log.json, via webui/data.py's calendar_entries()) alongside the
# batch upload queue's still-pending items (webui/jobs.py's JobQueue) —
# queued renders that will run next-in-line as soon as a slot frees up, with
# add/reorder/cancel controls. Kept as its own function + its own NAV/VIEWS
# entry so it doesn't touch view_analytics/view_automation.
# ─────────────────────────────────────────────────────────────────────────────
_CAL_KIND_STYLE = {
    "published":      ("check_circle", "text-teal"),
    "scheduled":      ("schedule", "text-amber"),
    "live":           ("sensors", "text-rose"),
    "scheduled_live": ("event", "text-amber"),
}
# Queue-slot chip styling -- "stream" queue items are new (see queue_dialog's
# slot selector) and need to read as clearly distinct from "main" ones in
# the shared "Up next" list rather than blending into a plain text label.
_SLOT_STYLE = {
    "main":   ("movie", "text-muted", "render"),
    "stream": ("sensors", "text-rose", "live"),
}


def _slot_chip(slot: str) -> None:
    icon, color_cls, label = _SLOT_STYLE.get(slot, ("event_note", "text-muted", slot))
    with ui.row().classes("items-center gap-1 no-wrap dcol-sm"):
        ui.icon(icon).classes(f"{color_cls} text-base")
        ui.label(label).classes(f"{theme.SUB} {color_cls}")


def queue_dialog() -> None:
    """Add-to-queue dialog — same render options as the Studio tab's "New
    render" dialog, but appends to the persisted batch queue instead of
    launching immediately (see webui/jobs.py's JobQueue). Multiple can be
    queued back-to-back; JobQueue.drain_forever() runs them one at a time per
    slot as it frees up, exactly respecting the existing single-job busy
    check.

    A "Queue slot" selector picks which JobQueue slot the item drains into --
    "main" (render/render+upload, drains alongside "New render" clicks) or
    "stream" (go-live, drains alongside "Go live" clicks on the Live page).
    JobQueue.add() has always accepted slot= structurally; this dialog is
    just the first UI that exposes the stream slot."""
    yt_connected = youtube_oauth.status()["connected"]
    with ui.dialog() as dlg, ui.element("div").classes("studio-card w-96 gap-3"):
        ui.label("Add to queue").classes(theme.H)
        slot_sel = ui.select({"main": "Render / Upload", "stream": "Live stream"},
                              value="main", label="Queue slot").classes("w-full")
        note = ui.input("Note (optional)", placeholder='e.g. "weekend batch"').classes("w-full")

        with ui.column().classes("w-full gap-2") as main_fields:
            tsel = ui.select(config.THEMES, value=config.DEFAULT_THEME, label="Theme").classes("w-full")
            dsel = ui.select(config.DURATIONS, value=config.DEFAULT_DURATION, label="Duration").classes("w-full")
            psel = ui.select(config.PRIVACY, value=config.DEFAULT_PRIVACY, label="Privacy").classes("w-full")
            sgsel = ui.select(_subgenre_select_options(), value="auto", label="Sub-genre").classes("w-full")
            mood_input = ui.input("Mood (optional)", placeholder="e.g. rainy study session").classes("w-full")
            esel = ui.select(_ENGINE_SELECT_OPTIONS, value="v1", label="Composer").classes("w-full")
            if not yt_connected:
                ui.label("YouTube isn't connected — \"Render only\" still works; "
                         "connect YouTube in Settings before queuing an upload.") \
                    .classes(f"{theme.SUB} text-amber")

        with ui.column().classes("w-full gap-2") as stream_fields:
            qsel = ui.select(config.STREAM_QUALITY, value="720p15", label="Quality").classes("w-full")
            psel_stream = ui.select(config.PRIVACY, value="public", label="Privacy").classes("w-full")
            if not yt_connected:
                ui.label("YouTube isn't connected — connect it in Settings before "
                         "queuing a live stream.").classes(f"{theme.SUB} text-amber")

        def add(upload: bool) -> None:
            if slot_sel.value == "stream":
                args = ["publish.py", "live", "--quality", qsel.value,
                        "--privacy", psel_stream.value]
                jobs.queue.add("live", args, slot="stream", note=note.value or "")
            elif upload:
                args = _build_render_args(
                    upload=True, theme=tsel.value, duration=dsel.value, privacy=psel.value,
                    subgenre=sgsel.value, mood=mood_input.value, engine=esel.value,
                )
                jobs.queue.add("render+upload", args, slot="main", note=note.value or "")
            else:
                args = _build_render_args(
                    upload=False, theme=tsel.value, duration=dsel.value, privacy=psel.value,
                    subgenre=sgsel.value, mood=mood_input.value, engine=esel.value,
                )
                jobs.queue.add("render", args, slot="main", note=note.value or "")
            dlg.close()
            ui.notify("Added to queue", type="positive")
            set_view("calendar")

        with ui.row().classes("w-full justify-end gap-2 mt-1"):
            ui.button("Cancel", on_click=dlg.close).props("flat color=primary")
            render_only_btn = ui.button("Render only", on_click=lambda: add(False)) \
                .props("color=secondary")
            upload_btn = ui.button("Render + Upload", on_click=lambda: add(True)) \
                .props("color=primary")
            stream_btn = ui.button("Queue live stream", on_click=lambda: add(True)) \
                .props("color=primary")
            if not yt_connected:
                upload_btn.disable()
                upload_btn.tooltip("Connect YouTube in Settings first")
                stream_btn.disable()
                stream_btn.tooltip("Connect YouTube in Settings first")

        def on_slot_change() -> None:
            is_stream = slot_sel.value == "stream"
            main_fields.visible = not is_stream
            stream_fields.visible = is_stream
            render_only_btn.visible = not is_stream
            upload_btn.visible = not is_stream
            stream_btn.visible = is_stream

        slot_sel.on_value_change(on_slot_change)
        on_slot_change()
    dlg.open()


def view_calendar(root) -> None:
    with root:
        with ui.element("div").classes("studio-card w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Content calendar").classes(theme.H)
                with ui.row().classes("gap-2"):
                    ui.button("Add to queue", icon="playlist_add", on_click=queue_dialog) \
                        .props("color=primary dense")
                    ui.button("Refresh", icon="refresh",
                              on_click=lambda: set_view("calendar")).props("flat dense color=primary")
            ui.label("Scheduled and past uploads in one timeline, plus what's queued to "
                     "render next. Queued items don't have a fixed clock time — they run "
                     "one at a time as soon as a render slot is free.").classes(theme.SUB)

        cal = data.calendar_entries()

        # ── Up next (batch queue) ────────────────────────────────────────────
        with ui.element("div").classes("studio-card w-full"):
            ui.label("Up next (queued)").classes(theme.H)
            pending = cal["queue_pending"]
            if not pending:
                ui.label('Nothing queued. Use "Add to queue" to batch up renders ahead of time.') \
                    .classes(theme.SUB + " mt-2")
            else:
                with ui.column().classes("w-full gap-1 mt-2 table-scroll"):
                    for idx, item in enumerate(pending):
                        with ui.row().classes("w-full items-center gap-3 no-wrap data-row"):
                            ui.label(f"#{idx + 1}").classes(f"{theme.SUB} dcol-xs")
                            ui.label(item["name"]).classes("text-sm font-medium dcol-lg")
                            _slot_chip(item["slot"])
                            ui.label(item["note"] or "").classes(f"{theme.SUB} dcol-grow")
                            if idx > 0:
                                ui.button(icon="arrow_upward",
                                          on_click=lambda item=item, idx=idx: (
                                              jobs.queue.reorder(item["id"], idx - 1),
                                              set_view("calendar"))) \
                                    .props("flat round dense").tooltip("Move up")
                            ui.button(icon="close", color="negative",
                                      on_click=lambda item=item: (
                                          jobs.queue.cancel(item["id"]),
                                          ui.notify("Removed from queue"),
                                          set_view("calendar"))) \
                                .props("flat round dense").tooltip("Remove")

        # ── Recent queue runs (finished batch-queue items, both slots) ───────
        # Additive block, separate from "Up next" above -- shows what already
        # ran (success/failed/cancelled) with a Retry action on failed items
        # (re-queues the exact original args/slot/note via JobQueue.retry()).
        with ui.element("div").classes("studio-card w-full"):
            ui.label("Recent queue runs").classes(theme.H)
            history = jobs.queue.list_history(limit=10)
            if not history:
                ui.label("No queued runs finished yet.").classes(theme.SUB + " mt-2")
            else:
                with ui.column().classes("w-full gap-1 mt-2 table-scroll"):
                    for item in history:
                        color_cls = _STATUS_COLOR.get(item.status, "text-muted")
                        with ui.row().classes("w-full items-center gap-3 no-wrap data-row"):
                            ui.icon(_STATUS_ICON.get(item.status, "help")).classes(color_cls)
                            ui.label(item.name).classes("text-sm font-medium dcol-lg")
                            _slot_chip(item.slot)
                            ui.label(item.status).classes(f"text-sm {color_cls} dcol-sm")
                            ui.label(item.note or "").classes(f"{theme.SUB} dcol-grow")
                            if item.status == "failed":
                                ui.button("Retry", icon="replay",
                                          on_click=lambda item=item: (
                                              jobs.queue.retry(item.id),
                                              ui.notify("Re-queued", type="positive"),
                                              set_view("calendar"))) \
                                    .props("flat dense color=secondary")

        # ── Timeline (past + scheduled uploads) ──────────────────────────────
        with ui.element("div").classes("studio-card w-full"):
            ui.label("Timeline").classes(theme.H)
            timeline = cal["timeline"]
            if not timeline:
                ui.label("No uploads yet.").classes(theme.SUB + " mt-2")
            else:
                with ui.column().classes("w-full gap-1 mt-2 max-h-[520px] overflow-y-auto"):
                    last_day = None
                    for row in timeline:
                        day = row["when"].strftime("%A, %b %d, %Y") if row["when"] else "Unknown date"
                        if day != last_day:
                            ui.label(day).classes("text-sm font-semibold mt-3 text-amber")
                            last_day = day
                        icon, color_cls = _CAL_KIND_STYLE.get(row["kind"], ("event_note", "text-muted"))
                        with ui.row().classes("w-full items-center gap-3 no-wrap data-row"):
                            ui.icon(icon).classes(color_cls)
                            time_str = row["when"].strftime("%H:%M UTC") if row["when"] else "—"
                            ui.label(time_str).classes(f"{theme.SUB} dcol-sm")
                            ui.label(row["title"]).classes("text-sm font-medium truncate dcol-grow")
                            ui.label(row["status"]).classes(f"{theme.SUB} dcol-xl")
                            if row.get("url"):
                                ui.link("Open ↗", row["url"], new_tab=True).classes("text-sm")


def _env_field(label: str, key: str, *, secret: bool = False, on_save=None) -> None:
    """One .env-backed settings row: input + Save, reused for every credential field."""
    current = config.read_env_file().get(key, "")
    with ui.row().classes("w-full items-end gap-3 no-wrap"):
        if secret:
            inp = ui.input(label, password=True, password_toggle_button=True)\
                .props('placeholder="leave blank to keep current"').classes("grow")

            def relabel(has_value: bool) -> None:
                inp.props(f'label="{label} ({"set" if has_value else "not set"})"')

            relabel(bool(current))
        else:
            inp = ui.input(label, value=current).classes("grow")

        def save(inp=inp, key=key, secret=secret) -> None:
            val = (inp.value or "").strip()
            if secret and not val:
                ui.notify("No change (left blank)", type="info")
                return
            try:
                config.write_env_value(key, val)
            except ValueError as e:
                ui.notify(str(e), type="negative")
                return
            # Takes effect immediately for anything (like alerts.py) that
            # reads os.environ live -- writing the .env *file* alone doesn't
            # touch this already-running process's environment. Fields that
            # need a real restart (OAuth clients built once at import time,
            # etc.) still need one; this is strictly additive, not a
            # replacement for that.
            os.environ[key] = val
            ui.notify(f"{key} saved", type="positive")
            if secret:
                inp.value = ""
                relabel(True)
            if on_save:
                # on_save may be sync or async (e.g. an async refresh_x
                # callback) -- ui.timer handles both without this function
                # itself needing to become async just to await one caller's
                # coroutine.
                ui.timer(0.01, on_save, once=True)

        ui.button("Save", on_click=save).props("flat dense color=primary")


def view_settings(root) -> None:
    with root:
        with theme.card("YouTube account"):
            info = ui.column().classes("gap-2 w-full")

            def refresh_yt() -> None:
                info.clear()
                st = youtube_oauth.status()
                with info:
                    if st["connected"]:
                        ch = stats.channel_stats()
                        ui.label(f"✅ Connected{' · ' + ch['title'] if ch.get('title') else ''}")\
                            .classes("text-positive font-semibold")
                        ui.button("Disconnect", icon="link_off",
                                  on_click=lambda: (youtube_oauth.disconnect(), refresh_yt(),
                                                    ui.notify("Disconnected"))).props("flat color=negative")
                    else:
                        ui.label("❌ Not connected").classes("text-negative font-semibold")
                        ui.button("Connect YouTube", icon="link",
                                  on_click=lambda: ui.navigate.to("/youtube/login")).props("color=primary")
                    if not st["client_present"]:
                        ui.label("⚠ No OAuth client yet. Create a \"Web application\" OAuth client "
                                 "in Google Cloud Console and upload its JSON here.")\
                            .classes("text-sm text-amber")

                        async def on_client_secret_upload(e) -> None:
                            raw = await e.file.read()
                            try:
                                parsed = json.loads(raw)
                            except Exception:
                                ui.notify("Not valid JSON — check you exported the OAuth "
                                         "client file from Google Cloud Console.",
                                         type="negative")
                                return
                            if not ({"web", "installed"} & parsed.keys()):
                                ui.notify("Doesn't look like an OAuth client_secret.json — "
                                         "missing a top-level 'web' or 'installed' key.",
                                         type="negative")
                                return
                            fd = os.open(config.CLIENT_SECRET, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                            with os.fdopen(fd, "wb") as f:
                                f.write(raw)
                            ui.notify("client_secret.json saved", type="positive")
                            refresh_yt()

                        ui.upload(on_upload=on_client_secret_upload, auto_upload=True,
                                  max_file_size=64_000, label="Upload client_secret.json")\
                            .props("accept=.json flat bordered").classes("max-w-md compact-upload")
                    elif st["needs_web_client"]:
                        ui.label("⚠ Desktop OAuth client + tunnel: in-browser re-login needs a "
                                 "Web-application client. (Local login works as-is.)")\
                            .classes("text-sm text-amber")
                    ui.label("Redirect URI for Google Cloud Console:").classes(theme.SUB + " mt-1")
                    ui.label(st["redirect_uri"]).classes("font-mono text-sm code-chip")
                    ui.label(
                        "⚠ Set the OAuth consent screen to \"In production\" in Google Cloud "
                        "Console. In \"Testing\" the login expires after 7 days and "
                        "scheduled uploads stop until you reconnect."
                    ).classes("text-sm mt-2 text-amber")

            refresh_yt()

            with ui.column().classes("gap-2 w-full mt-3"):
                ui.separator()
                ui.label("Alternative: connect via device code").classes(theme.H)
                ui.label(
                    "For when the normal login can't redirect back to this machine: you "
                    "type a short code on a Google page instead. Needs its own OAuth client "
                    "of type \"TVs and Limited Input devices\".")\
                    .classes(theme.SUB)

                dstatus = youtube_oauth.device_client_status()
                if not dstatus["present"]:
                    async def on_device_client_upload(e) -> None:
                        raw = await e.file.read()
                        try:
                            parsed = json.loads(raw)
                        except Exception:
                            ui.notify("Not valid JSON.", type="negative")
                            return
                        if not ({"web", "installed"} & parsed.keys()):
                            ui.notify("Doesn't look like an OAuth client_secret.json.",
                                     type="negative")
                            return
                        fd = os.open(config.CLIENT_SECRET_DEVICE,
                                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                        with os.fdopen(fd, "wb") as f:
                            f.write(raw)
                        ui.notify("Device OAuth client saved", type="positive")
                        set_view("settings")

                    ui.upload(on_upload=on_device_client_upload, auto_upload=True,
                              max_file_size=64_000, label="Upload TV/device OAuth client JSON")\
                        .props("accept=.json flat bordered").classes("max-w-md compact-upload")
                else:
                    state = {"timer": None}
                    prompt = ui.column().classes("gap-1 w-full")

                    async def start_device_flow() -> None:
                        if state["timer"]:
                            state["timer"].active = False
                        prompt.clear()
                        try:
                            d = await asyncio.to_thread(youtube_oauth.device_flow_start)
                        except Exception as e:
                            ui.notify(f"Couldn't start device flow: {e}", type="negative")
                            return
                        with prompt:
                            ui.label("Go to:").classes(theme.SUB)
                            ui.label(d["verification_url"]).classes("font-mono text-sm")
                            ui.label("Enter this code:").classes(theme.SUB + " mt-1")
                            ui.label(d["user_code"]).classes("text-lg font-bold tracking-widest")
                            with ui.row().classes("items-center gap-2 mt-1"):
                                ui.spinner()
                                ui.label("Waiting for you to finish on Google's site...")\
                                    .classes(theme.SUB)

                        async def poll() -> None:
                            try:
                                await asyncio.to_thread(youtube_oauth.device_flow_poll,
                                                        d["device_code"])
                            except youtube_oauth.DeviceFlowPending:
                                return
                            except Exception as e:
                                state["timer"].active = False
                                prompt.clear()
                                with prompt:
                                    ui.label(f"Failed: {e}").classes("text-negative text-sm")
                                return
                            state["timer"].active = False
                            prompt.clear()
                            ui.notify("YouTube connected!", type="positive")
                            refresh_yt()

                        state["timer"] = ui.timer(max(d["interval"], 5), poll)

                    ui.button("Connect via device code", icon="qr_code_2",
                              on_click=start_device_flow).props("color=primary")

        # ── Revenue & RPM (opt-in monetary scope) ──────────────────────────
        with theme.card(
                "Revenue & RPM",
                "Optional. Revenue numbers need an extra YouTube permission that the "
                "normal login doesn't ask for. Connecting here asks for just that one, "
                "and keeps it in its own token file."):
            monetary_info = ui.column().classes("gap-2 w-full")

            def refresh_monetary() -> None:
                monetary_info.clear()
                mst = youtube_oauth.monetary_status()
                with monetary_info:
                    if mst["connected"]:
                        ui.label("✅ Monetary analytics connected")\
                            .classes("text-positive font-semibold")
                        ui.button("Disconnect", icon="link_off",
                                  on_click=lambda: (youtube_oauth.monetary_disconnect(),
                                                    refresh_monetary(),
                                                    ui.notify("Disconnected"))
                                  ).props("flat color=negative")
                    else:
                        ui.label("Not connected. The Revenue tab in Analytics stays empty "
                                 "until it is.").classes(theme.SUB)
                        ui.button("Connect monetary analytics", icon="attach_money",
                                  on_click=lambda: ui.navigate.to("/youtube/monetary/login"))\
                            .props("color=primary")
                    if not mst["client_present"]:
                        ui.label("⚠ Upload the OAuth client in the YouTube account card "
                                 "first; this uses the same one.")\
                            .classes("text-sm text-amber")
                    ui.label("Redirect URI for Google Cloud Console (register alongside "
                             "the main one):").classes(theme.SUB + " mt-1")
                    ui.label(mst["redirect_uri"])\
                        .classes("font-mono text-sm bg-black/35 rounded-lg px-2 py-0.5 break-all")

            refresh_monetary()

        with theme.card("Integrations & credentials",
                        "Saved to .env and used by the next job. Secret fields only show "
                        "whether a value is set; leave one blank to keep it."):
            _env_field("YouTube stream key", "YT_STREAM_KEY", secret=True)
            _env_field("YouTube channel ID", "YT_CHANNEL_ID")
            ui.separator()

            _env_field("Alert URL(s) — stream reconnect, render/queue failures",
                       "LOFI_STREAM_ALERT_WEBHOOK")
            ui.label("A Slack or Discord webhook URL, or several comma-separated apprise "
                     "URLs for Telegram, email, ntfy and others.") \
                .classes(theme.SUB)

            async def send_test_alert() -> None:
                if not alerts.configured():
                    ui.notify("No alert URL configured above — save one first.", type="warning")
                    return
                ok = await alerts.send_test_alert()
                ui.notify("Test alert sent." if ok else
                          "Failed to send — check the URL(s) and webui logs.",
                          type="positive" if ok else "negative")

            ui.button("Send test alert", icon="notifications_active", on_click=send_test_alert) \
                .props("flat dense color=secondary")

        with theme.card("Render defaults",
                        "Pre-selected values when opening \"New render\" — saves re-picking "
                        "the same options every time."):
            with ui.row().classes("w-full items-end gap-4"):
                dt_sel = ui.select(config.THEMES, value=config.DEFAULT_THEME,
                                    label="Default theme").classes("w-48")
                dd_sel = ui.select(config.DURATIONS, value=config.DEFAULT_DURATION,
                                    label="Default duration").classes("w-40")
                dp_sel = ui.select(config.PRIVACY, value=config.DEFAULT_PRIVACY,
                                    label="Default privacy").classes("w-44")

            def save_render_defaults() -> None:
                config.write_env_value("DEFAULT_THEME", dt_sel.value)
                config.write_env_value("DEFAULT_DURATION", dd_sel.value)
                config.write_env_value("DEFAULT_PRIVACY", dp_sel.value)
                config.DEFAULT_THEME = dt_sel.value
                config.DEFAULT_DURATION = dd_sel.value
                config.DEFAULT_PRIVACY = dp_sel.value
                ui.notify("Render defaults saved", type="positive")

            ui.button("Save defaults", icon="save", on_click=save_render_defaults)\
                .props("flat dense color=primary").classes("mt-2")


def _fmt_dur(secs: float | None) -> str:
    if secs is None:
        return "—"
    m, s = divmod(int(secs), 60)
    return f"{m}:{s:02d}"


def _confirm_delete_sample(path: str, name: str, on_change) -> None:
    with ui.dialog() as dlg, theme.card(title=f"Delete “{name}”?", subtitle="This cannot be undone.",
                                        classes="gap-3 max-w-md"):
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dlg.close).props("flat")

            def do_delete() -> None:
                if _render_in_progress():   # the page may be older than the render
                    dlg.close()
                    ui.notify("A render is running; try again when it's done.", type="warning")
                    return
                ok = data.delete_sample(path)
                dlg.close()
                ui.notify("Deleted." if ok else "Delete failed.",
                          type="positive" if ok else "negative")
                on_change()

            ui.button("Delete", icon="delete", on_click=do_delete, color="negative")\
                .props("unelevated")
    dlg.open()


def view_samples(root) -> None:
    with root:
        busy = _render_in_progress()

        with theme.card():
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Music tracks").classes(theme.H)
                ui.button("Refresh", icon="refresh",
                          on_click=lambda: set_view("samples")).props(
                          "flat dense color=primary")
            if busy:
                ui.label("A render is running — samples it may be using are "
                         "temporarily protected from deletion.").classes(theme.SUB)

            tracks = data.music_samples()
            if not tracks:
                ui.label("No generated tracks yet.").classes(theme.SUB)
            for t in tracks:
                with ui.column().classes("w-full gap-1 list-row"):
                    with ui.row().classes("w-full items-center justify-between no-wrap"):
                        with ui.column().classes("gap-0 min-w-0"):
                            ui.label(t["title"]).classes("text-sm font-medium truncate")
                            sub = f"{t['genre'] + ' · ' if t.get('genre') else ''}" \
                                  f"{_fmt_dur(t['duration_secs'])} · {t['size_mb']} MB · " \
                                  f"{t['modified']}"
                            ui.label(sub).classes(f"{theme.SUB} truncate")
                        ui.button(icon="delete_outline", color="negative",
                                  on_click=lambda t=t: _confirm_delete_sample(
                                      t["path"], t["name"], lambda: set_view("samples")))\
                            .props("flat round dense").set_visibility(not busy)
                    ui.html(
                        f'<audio controls preload="none" class="sample-audio" '
                        f'src="{_src("/music/", t["name"])}"></audio>'
                    )

        with theme.card("Visual loops", classes="w-full mt-4"):
            visuals = data.visual_samples()
            if not visuals:
                ui.label("No visual loops yet.").classes(theme.SUB)
            with ui.element("div").classes("w-full grid gap-3 mt-2").style(
                    "grid-template-columns:repeat(auto-fill,minmax(220px,1fr))"):
                for v in visuals:
                    with ui.column().classes("gap-1"):
                        ui.html(
                            f'<video controls preload="metadata" muted class="sample-video" '
                            f'src="{_src("/visuals/", v["name"])}"></video>'
                        )
                        with ui.row().classes("w-full items-center justify-between no-wrap"):
                            ui.label(f"{v['theme']} · {_fmt_dur(v['duration_secs'])} · "
                                     f"{v['size_mb']} MB").classes(theme.SUB)
                            ui.button(icon="delete_outline", color="negative",
                                      on_click=lambda v=v: _confirm_delete_sample(
                                          v["path"], v["name"], lambda: set_view("samples")))\
                                .props("flat round dense").set_visibility(not busy)


# ─────────────────────────────────────────────────────────────────────────────
# System admin — resource monitor, disk usage, restart, backups, audit log.
# Added as a standalone block (new NAV/VIEWS entry only) to avoid conflicting
# with other in-flight edits to this file. All data-gathering / side-effect
# logic lives in system_admin.py; every blocking call here goes through
# asyncio.to_thread per the async discipline the rest of the app follows.
# ─────────────────────────────────────────────────────────────────────────────
def _confirm_restart_webui() -> None:
    # Confirmed live 2026-08-17: restarting lofi-webui.service sends SIGTERM
    # to its entire cgroup, which includes any render subprocess JobManager
    # currently has running underneath it -- a restart mid-render silently
    # killed a real in-progress job (5m45s in, 41% through visual frames),
    # with no warning at all before this check existed.
    busy = jobs.manager.is_busy()
    with ui.dialog() as dlg, ui.element("div").classes("studio-card gap-3")\
            .style("max-width:420px"):
        ui.label("Restart the web UI?").classes(theme.H)
        if busy:
            ui.label(f"⚠ \"{jobs.manager.current.name}\" is running right now — "
                     "restarting will kill it immediately (SIGTERM to the whole "
                     "process, not just the web UI). It will NOT resume after "
                     "restart.").classes("text-sm text-rose")
        ui.label("This restarts lofi-webui.service right now, which will drop this "
                 "browser session for a few seconds while it comes back up. Only do "
                 "this on purpose.").classes(theme.SUB)
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dlg.close).props("flat")

            async def do_restart() -> None:
                dlg.close()
                ui.notify("Restarting webui service…", type="warning")
                try:
                    await asyncio.to_thread(system_admin.restart_webui)
                except Exception as e:  # noqa: BLE001 — surface whatever systemctl/subprocess raised
                    ui.notify(f"Restart failed: {e}", type="negative")

            ui.button("Kill job & restart" if busy else "Restart now", icon="restart_alt",
                      on_click=do_restart, color="negative").props("unelevated")
    dlg.open()


def _confirm_restore_backup(name: str, on_change) -> None:
    with ui.dialog() as dlg, ui.element("div").classes("studio-card gap-3")\
            .style("max-width:420px"):
        ui.label(f"Restore backup “{name}”?").classes(theme.H)
        ui.label("Overwrites the current token.json / .env / upload_log.json with the "
                 "versions from this backup. This cannot be undone.").classes(theme.SUB)
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dlg.close).props("flat")

            async def do_restore() -> None:
                try:
                    restored = await asyncio.to_thread(system_admin.restore_backup, name)
                except ValueError as e:
                    ui.notify(str(e), type="negative")
                    return
                dlg.close()
                ui.notify(f"Restored {len(restored)} file(s) — restart the panel to apply."
                          if restored else "Nothing to restore.", type="positive")
                on_change()

            ui.button("Restore", icon="restore", on_click=do_restore,
                      color="negative").props("unelevated")
    dlg.open()


def _confirm_delete_backup(name: str, on_change) -> None:
    with ui.dialog() as dlg, ui.element("div").classes("studio-card gap-3")\
            .style("max-width:420px"):
        ui.label(f"Delete backup “{name}”?").classes(theme.H)
        ui.label("This cannot be undone.").classes(theme.SUB)
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dlg.close).props("flat")

            async def do_delete() -> None:
                ok = await asyncio.to_thread(system_admin.delete_backup, name)
                dlg.close()
                ui.notify("Backup deleted." if ok else "Delete failed.",
                          type="positive" if ok else "negative")
                on_change()

            ui.button("Delete", icon="delete", on_click=do_delete,
                      color="negative").props("unelevated")
    dlg.open()


def _render_in_progress() -> bool:
    return (jobs.manager.is_busy()
            or automation.status().get("running_now", False)
            or system_admin.pipeline_running())


def _confirm_clean_scratch(on_change) -> None:
    busy = _render_in_progress()
    with ui.dialog() as dlg, ui.element("div").classes("studio-card gap-3")\
            .style("max-width:460px"):
        if busy:
            ui.label("Clean up orphaned scratch files?").classes(theme.H)
            ui.label("A render is in progress (Studio or the lofi-auto systemd run) — "
                     "cleanup is disabled until it finishes, since this can't tell an "
                     "in-progress run's files from true leftovers.").classes(theme.SUB)
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Close", on_click=dlg.close).props("flat")
        else:
            files_holder: dict = {}

            async def load() -> None:
                files_holder["files"] = await asyncio.to_thread(system_admin.orphaned_scratch_files)
                total = sum(f["size_bytes"] for f in files_holder["files"])
                body.text = (f"{len(files_holder['files'])} file(s), {total / 1_048_576:.0f} MB "
                             "— this cannot be undone." if files_holder["files"]
                             else "Nothing to clean up.")

            ui.label("Clean up orphaned scratch files?").classes(theme.H)
            body = ui.label("Scanning…").classes(theme.SUB)
            ui.timer(0.1, load, once=True)
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dlg.close).props("flat")

                async def do_clean() -> None:
                    # Re-check at click time: a render may have started since
                    # the dialog opened.
                    if await asyncio.to_thread(_render_in_progress):
                        dlg.close()
                        ui.notify("A render started — cleanup cancelled.", type="warning")
                        return
                    try:
                        result = await asyncio.to_thread(system_admin.clean_orphaned_scratch)
                    except RuntimeError as e:
                        dlg.close()
                        ui.notify(str(e), type="warning")
                        return
                    dlg.close()
                    ui.notify(f"Deleted {result['deleted']} file(s), "
                              f"freed {result['freed_bytes'] / 1_048_576:.0f} MB."
                              if result["deleted"] else "Nothing to clean up.",
                              type="positive" if result["deleted"] else "info")
                    on_change()

                ui.button("Clean up", icon="delete_sweep", on_click=do_clean,
                          color="negative").props("unelevated")
    dlg.open()


def view_system(root) -> None:
    with root:
        # ── Resource monitor (CPU / RAM / disk / GPU) — polls every 5s ─────────
        with theme.card("Resource monitor", "CPU, memory and disk on this machine. "
                        "Updates every 5 seconds."):
            meters = {}
            with ui.element("div").classes("w-full grid grid-cols-1 sm:grid-cols-3 gap-4"):
                for key, label, color in (("cpu", "CPU", "primary"), ("ram", "Memory", "secondary"),
                                          ("disk", "Disk", "info")):
                    with ui.column().classes("gap-1 min-w-0"):
                        num = ui.label("—").classes("stat-num")
                        ui.label(label).classes("stat-lbl")
                        bar = ui.linear_progress(value=0, show_value=False)\
                            .props(f"rounded color={color}").classes("w-full")
                    meters[key] = (num, bar)
            cpu_lbl, cpu_bar = meters["cpu"]
            ram_lbl, ram_bar = meters["ram"]
            disk_lbl, disk_bar = meters["disk"]
            gpu_box = ui.column().classes("w-full gap-1 mt-1")

            async def refresh_resources() -> None:
                snap = await asyncio.to_thread(system_admin.resource_snapshot)
                cpu_lbl.text = f"{snap['cpu_percent']:.0f}%"
                cpu_bar.value = snap["cpu_percent"] / 100
                ram_lbl.text = f"{snap['ram_used_gb']:.1f}/{snap['ram_total_gb']:.1f} GB"
                ram_bar.value = snap["ram_percent"] / 100
                disk_lbl.text = f"{snap['disk_used_gb']:.1f}/{snap['disk_total_gb']:.1f} GB"
                disk_bar.value = snap["disk_percent"] / 100

                gpu = await asyncio.to_thread(system_admin.gpu_snapshot)
                gpu_box.clear()
                if gpu:
                    with gpu_box:
                        if gpu["util_percent"] is not None:
                            ui.label(
                                f"GPU ({gpu['backend']}): {gpu['util_percent']:.0f}% · "
                                f"{gpu['mem_used_mb']:.0f}/{gpu['mem_total_mb']:.0f} MB"
                            ).classes(theme.SUB)
                        else:
                            ui.label(f"GPU ({gpu['backend']}): {gpu['info']}")\
                                .classes(theme.SUB)
                # else: no nvidia-smi/vainfo on this box — panel stays empty rather
                # than showing a broken GPU row.

            ui.timer(0.1, refresh_resources, once=True)
            ui.timer(5.0, refresh_resources)

        # ── Disk-usage breakdown ───────────────────────────────────────────────
        with theme.card("Disk usage", "What the factory's own files take up."):
            breakdown_col = ui.column().classes("w-full gap-2")

            async def refresh_breakdown() -> None:
                breakdown = await asyncio.to_thread(system_admin.disk_usage_breakdown)
                breakdown_col.clear()
                biggest = max(breakdown.values(), default=0) or 1
                with breakdown_col:
                    for name, nbytes in sorted(breakdown.items(), key=lambda kv: -kv[1]):
                        gb = nbytes / 1_073_741_824
                        with ui.row().classes("w-full items-center justify-between no-wrap"):
                            ui.label(name).classes("text-sm font-medium")
                            ui.label(f"{gb:.2f} GB").classes(theme.SUB)
                        ui.linear_progress(value=nbytes / biggest, show_value=False)\
                            .props("rounded color=secondary").classes("w-full")
            ui.button("Refresh", icon="refresh", on_click=refresh_breakdown)\
                .props("flat dense color=primary")
            ui.timer(0.1, refresh_breakdown, once=True)

        # ── Orphaned scratch-file cleanup ───────────────────────────────────────
        with theme.card("Render leftovers", "Per-render tracks and visual loops in "
                        "music/ and visuals/. Uploads prune these automatically; this "
                        "clears all of them. The live stream library is never touched."):
            scratch_note = ui.label("—").classes(theme.SUB)

            async def refresh_scratch() -> None:
                if await asyncio.to_thread(system_admin.pipeline_running):
                    scratch_note.text = "A render is running; its files are in use."
                    scratch_note.classes(replace=theme.SUB)
                    return
                files = await asyncio.to_thread(system_admin.orphaned_scratch_files)
                total = sum(f["size_bytes"] for f in files)
                if files:
                    scratch_note.text = f"{len(files)} file(s), {total / 1_048_576:.0f} MB"
                    scratch_note.classes(replace=f"{theme.SUB} text-amber")
                else:
                    scratch_note.text = "None found."
                    scratch_note.classes(replace=theme.SUB)

            with ui.row().classes("gap-2 mt-1"):
                ui.button("Refresh", icon="refresh", on_click=refresh_scratch)\
                    .props("flat dense color=primary")
                ui.button("Clean up", icon="delete_sweep",
                          on_click=lambda: _confirm_clean_scratch(refresh_scratch))\
                    .props("flat dense color=negative")
            ui.timer(0.1, refresh_scratch, once=True)

        # ── Tailscale / TLS cert status ─────────────────────────────────────────
        with theme.card("Tailscale / TLS", "Network + certificate status for this box."):
            net_col = ui.column().classes("w-full gap-2")

            async def refresh_network() -> None:
                ts = await asyncio.to_thread(system_admin.tailscale_status)
                cert = await asyncio.to_thread(system_admin.cert_status)
                net_col.clear()
                with net_col:
                    if ts:
                        ui.label(
                            f"Tailscale: {ts['hostname']} ({ts['tailscale_ip'] or '?'}) · "
                            f"{ts['peer_count']} peer(s) · "
                            f"{'online' if ts['online'] else 'offline'}"
                        ).classes("text-sm")
                    else:
                        ui.label("Tailscale not detected on this box (binary missing or "
                                 "daemon unreachable).").classes(theme.SUB)
                    if cert:
                        color_cls = "text-rose" if cert["expiring_soon"] else "text-teal"
                        warn = " ⚠ expiring soon" if cert["expiring_soon"] else ""
                        ui.label(
                            f"TLS cert: expires {cert['expires']} "
                            f"({cert['days_left']:.0f}d left){warn}"
                        ).classes(f"text-sm {color_cls}")
                    else:
                        ui.label("No TLS cert configured (WEBUI_SSL_CERTFILE unset, or "
                                 "file missing).").classes(theme.SUB)

            ui.button("Refresh", icon="refresh", on_click=refresh_network)\
                .props("flat dense color=primary")
            ui.timer(0.1, refresh_network, once=True)

        # ── Maintenance: restart + config backups ───────────────────────────────
        with theme.card("Maintenance", "Self-service restart and local config backups."):
            ui.button("Restart web UI", icon="restart_alt", on_click=_confirm_restart_webui)\
                .props("color=negative")

            ui.separator().classes("my-3")
            ui.label("Config backups").classes(theme.H)
            ui.label("Copies token.json, .env, and upload_log.json (whichever exist) to "
                     "backups/<timestamp>/ on local disk — never sent to the browser, "
                     "since these are live secrets.").classes(theme.SUB)
            backup_col = ui.column().classes("w-full gap-2 mt-2")

            def refresh_backups() -> None:
                backup_col.clear()
                backups = system_admin.list_backups()
                with backup_col:
                    if not backups:
                        ui.label("No backups yet.").classes(theme.SUB)
                    for b in backups:
                        with ui.row().classes("w-full items-center justify-between no-wrap"):
                            with ui.column().classes("gap-0"):
                                ui.label(b["name"]).classes("font-mono text-sm")
                                ui.label(f"{', '.join(b['files']) or '(empty)'} · "
                                         f"{b['total_bytes'] / 1024:.0f} KB").classes(theme.SUB)
                            with ui.row().classes("gap-1 no-wrap"):
                                ui.button(icon="restore",
                                          on_click=lambda n=b["name"]: _confirm_restore_backup(
                                              n, refresh_backups)).props("flat round dense")
                                ui.button(icon="delete_outline", color="negative",
                                          on_click=lambda n=b["name"]: _confirm_delete_backup(
                                              n, refresh_backups)).props("flat round dense")

            async def do_create_backup() -> None:
                result = await asyncio.to_thread(system_admin.create_backup)
                ui.notify(f"Backed up {len(result['files'])} file(s)" if result["files"]
                          else "Nothing found to back up.",
                          type="positive" if result["files"] else "info")
                refresh_backups()

            ui.button("Create backup", icon="save", on_click=do_create_backup)\
                .props("color=primary")
            refresh_backups()
        # Admin audit log now lives on the Logs page (view_logs) alongside
        # job history and the automation journal tail.


# ─────────────────────────────────────────────────────────────────────────────
# Logs — everything that used to be scattered across four separate places
# (a live_log() widget re-embedded per-tab in Studio/Live/Automation, the
# lofi-auto journal tail that only lived inside Automation, the admin audit
# log that only lived inside System, and JobManager's persisted run history
# which had no dedicated page of its own at all) now lives here, one place.
# ─────────────────────────────────────────────────────────────────────────────
def view_logs(root) -> None:
    with root:
        with theme.card("Live output", "Whatever the web UI itself is currently running "
                        "(a Studio render or a queued job)."):
            live_log(lambda: jobs.manager.current, height="h-72")

        with theme.card("Recent runs", "Every job the web UI has run this deploy — "
                        "retry a failed one from here."):
            _runs_table(jobs.manager.history)

        with theme.card("Automation log", "Live tail of the lofi-auto systemd journal — "
                        "the unattended daily render+upload, independent of anything "
                        "started from this page."):
            auto_log = ui.log(max_lines=4000).classes(f"{theme.LOG} w-full h-80")
            auto_proc_holder: dict = {}

            def _on_auto_line(line: str) -> None:
                auto_log.push(line)

            async def _start_auto_tail() -> None:
                try:
                    auto_proc_holder["proc"] = await automation.tail_logs(_on_auto_line)
                except FileNotFoundError:
                    auto_log.push("[webui] journalctl not found — can't tail logs on this host.")

            ui.timer(0.1, _start_auto_tail, once=True)

            def _stop_auto_tail() -> None:
                proc = auto_proc_holder.get("proc")
                if proc and proc.returncode is None:
                    proc.terminate()

            ui.context.client.on_disconnect(_stop_auto_tail)

        with theme.card("Admin audit log", "Last 50 admin actions (restarts, backups, "
                        "deletes, schedule changes)."):
            audit_col = ui.column().classes("w-full gap-1")

            async def refresh_audit() -> None:
                entries = await asyncio.to_thread(system_admin.audit_log_tail, 50)
                audit_col.clear()
                with audit_col:
                    if not entries:
                        ui.label("No admin actions logged yet.").classes(theme.SUB)
                    for e in entries:
                        # Wraps on a phone: time + action, then the detail below.
                        with ui.row().classes("w-full items-center gap-x-3 gap-y-0"):
                            ui.label(e.get("ts", "")).classes(
                                "text-xs font-mono text-muted whitespace-nowrap")
                            ui.label(e.get("action", "")).classes("text-sm whitespace-nowrap")
                            ui.label(json.dumps(e.get("detail", {})))\
                                .classes(f"text-xs {theme.SUB} truncate")

            ui.button("Refresh", icon="refresh", on_click=refresh_audit)\
                .props("flat dense color=primary")
            ui.timer(0.1, refresh_audit, once=True)

        # ── Alerts ───────────────────────────────────────────────────────────
        # Every alerts.send_sync() call (job/queue/automation failures, test
        # alerts from Settings) now persists here regardless of whether a
        # webhook is even configured -- confirmed 2026-08-17: this app's
        # alert system could fail, or simply have nothing configured, with
        # zero trace anywhere in the web UI. This card is that trace.
        with theme.card("Alerts", "Every alert this app has tried to send — "
                        "webhook delivery or not, it's logged here first."):
            alert_chart_holder = ui.column().classes("w-full")
            alert_list_holder = ui.column().classes("w-full gap-1 mt-3")

            async def refresh_alerts() -> None:
                entries = await asyncio.to_thread(alerts.recent, 100)
                alert_chart_holder.clear()
                alert_list_holder.clear()
                with alert_chart_holder:
                    if not alerts.configured():
                        _env_field("Alert URL(s)", alerts.ALERT_ENV_KEY, on_save=refresh_alerts)

                        async def send_test() -> None:
                            ok = await alerts.send_test_alert()
                            ui.notify("Test alert sent." if ok else
                                      "Nothing configured yet — save a URL above first.",
                                      type="positive" if ok else "warning")
                            await refresh_alerts()

                        ui.button("Send test alert", icon="notifications_active",
                                  on_click=send_test).props("flat dense color=secondary")
                    if entries:
                        by_day: dict[str, dict[str, int]] = {}
                        for e in entries:
                            day = (e.get("ts") or "")[:10]
                            bucket = by_day.setdefault(day, {"sent": 0, "failed": 0})
                            bucket["sent" if e.get("sent") else "failed"] += 1
                        days = sorted(by_day)[-14:]
                        ui.echart({
                            "grid": {"left": 8, "right": 16, "top": 24, "bottom": 24,
                                     "containLabel": True},
                            "legend": {"top": 0, "textStyle": {"color": theme.MUTED,
                                                                "fontSize": 10}},
                            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                            "xAxis": {"type": "category", "data": days,
                                      "axisLabel": {"color": theme.MUTED, "fontSize": 10}},
                            "yAxis": {"type": "value", "minInterval": 1,
                                      "axisLabel": {"color": theme.MUTED}},
                            "series": [
                                {"name": "Sent", "type": "bar", "stack": "a",
                                 "data": [by_day[d]["sent"] for d in days],
                                 "itemStyle": {"color": theme.TEAL}},
                                {"name": "Failed to send", "type": "bar", "stack": "a",
                                 "data": [by_day[d]["failed"] for d in days],
                                 "itemStyle": {"color": theme.ROSE}},
                            ],
                        }).classes("w-full").style("height:180px")
                with alert_list_holder:
                    if not entries:
                        ui.label("No alerts yet.").classes(theme.SUB)
                    for e in entries[:30]:
                        color_cls = "text-teal" if e.get("sent") else (
                            "text-muted" if not e.get("configured") else "text-rose")
                        icon = "check_circle" if e.get("sent") else (
                            "notifications_off" if not e.get("configured") else "error")
                        with ui.row().classes("w-full items-start gap-3 no-wrap"):
                            ui.icon(icon).classes(f"{color_cls} text-base mt-1")
                            with ui.column().classes("gap-0 min-w-0"):
                                ui.label(e.get("title", "")).classes("text-sm font-medium")
                                ui.label(e.get("ts", "")).classes(
                                    "text-xs font-mono text-muted")

            ui.button("Refresh", icon="refresh", on_click=refresh_alerts)\
                .props("flat dense color=primary")
            ui.timer(0.1, refresh_alerts, once=True)


VIEWS = {
    "studio": view_studio, "library": view_library, "live": view_live,
    "logs": view_logs, "analytics": view_analytics, "samples": view_samples,
    "automation": view_automation, "calendar": view_calendar,
    "system": view_system, "settings": view_settings,
}

# Per-client mutable holder for the active view + nav element refs.
set_view = lambda name: None  # noqa: E731 — reassigned inside the page


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────
@ui.page("/")
def index(request: Request) -> None:
    theme.apply()
    if request.query_params.get("yt") == "connected":
        ui.notify("YouTube connected", type="positive")
    elif "yt_error" in request.query_params:
        detail = request.query_params["yt_error"][:300]
        ui.notify(f"YouTube connect failed: {detail}", type="negative")
    state = {"current": "studio"}
    nav_refs: dict[str, object] = {}

    drawer = ui.left_drawer(value=False).classes("studio-sidebar p-3")\
        .props("breakpoint=768 show-if-above bordered")

    with ui.header().classes("lg:hidden items-center gap-2 px-3 py-2 appbar-mobile"):
        ui.button(icon="menu", on_click=drawer.toggle).props("flat round dense color=white")
        ui.label("LOFI_FACTORY").classes("studio-brand")

    with drawer:
        with ui.row().classes("items-center gap-2 px-2 pt-1 pb-3"):
            ui.label("LOFI_FACTORY").classes("studio-brand")
        for key, label, icon in NAV:
            item = ui.element("div").classes("nav-item")
            with item:
                ui.icon(icon)
                ui.label(label)
            item.on("click", lambda k=key: _nav_click(k))
            nav_refs[key] = item
        ui.element("div").classes("grow")
        with ui.element("div").classes("nav-item").on(
                "click", lambda: (auth.logout(), ui.navigate.to("/login"))):
            ui.icon("logout")
            ui.label("Log out")

    content = ui.column().classes("w-full max-w-5xl mx-auto px-6 py-6 gap-5")

    def _set(name: str) -> None:
        state["current"] = name
        for k, el in nav_refs.items():
            el.classes(remove="active")
            if k == name:
                el.classes(add="active")
        # Every view's periodic ui.timer()s (refresh_hero, refresh_stats,
        # refresh_resources, ...) keep firing after content.clear() removes
        # their target elements -- clear() drops the elements but doesn't
        # stop the still-scheduled Timer, so its next tick tries to update a
        # now-deleted label and NiceGUI raises "The parent element this slot
        # belongs to has been deleted" as an unhandled background-task
        # exception. Confirmed live 2026-08-16 spamming the journal on every
        # nav switch. Deactivating the outgoing view's timers first (they're
        # real Timer elements, discoverable as descendants of `content` since
        # every view renders `with root:`) closes this system-wide in one
        # place instead of patching every individual refresh callback.
        for t in list(content.descendants()):
            if isinstance(t, Timer):
                t.deactivate()
        content.clear()
        VIEWS[name](content)

    async def _nav_click(name: str) -> None:
        _set(name)
        # Only auto-close on mobile -- show-if-above keeps it pinned open on desktop
        # regardless, but only in response to an actual resize, not every render, so an
        # unconditional hide() here would also collapse it on wide screens.
        try:
            is_mobile = await ui.run_javascript("window.innerWidth < 768", timeout=3.0)
        except TimeoutError:
            # Confirmed live: the default 1s budget routinely isn't enough
            # (slow client, tab backgrounded, high-latency Tailscale link) and
            # this was crashing into an unhandled-exception traceback in the
            # journal on ordinary navigation. Worst case on a genuine miss:
            # the mobile drawer just doesn't auto-close, which is harmless.
            return
        if is_mobile:
            drawer.hide()

    global set_view
    set_view = _set
    _set("studio")


@ui.page("/login")
def login_page(request: Request) -> None:
    theme.apply()
    if auth.is_authenticated():
        ui.navigate.to("/")
        return
    with theme.card(classes="absolute-center w-80 gap-3 flex flex-col"):
        ui.label("LOFI_FACTORY").classes("studio-brand self-center")
        ui.label("control panel").classes(theme.SUB + " self-center")
        if not config.is_configured():
            ui.label("No WEBUI_PASSWORD set. Add it to .env and restart.")\
                .classes("text-sm text-amber")
            return
        pw = ui.input("Password", password=True, password_toggle_button=True)\
            .classes("w-full").on("keydown.enter", lambda: do_login())

        client = auth.client_id(request)

        def do_login() -> None:
            wait = auth.lockout_remaining(client)
            if wait:
                ui.notify(f"Too many failed attempts. Try again in {int(wait // 60) + 1} min.",
                          type="negative")
                return
            if auth.check_password(pw.value or ""):
                auth.record_success(client)
                auth.login()
                ui.navigate.to(app.storage.user.get("referrer_path", "/"))
            else:
                auth.record_failure(client)
                ui.notify("Wrong password", type="negative")

        ui.button("Enter studio", on_click=do_login).props("color=primary").classes("w-full mt-1")


@app.get("/robots.txt")
def robots_txt():
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


# ── OAuth routes ──────────────────────────────────────────────────────────────
@app.get("/youtube/login")
def yt_login():
    try:
        return RedirectResponse(youtube_oauth.authorization_url())
    except Exception as ex:  # noqa: BLE001
        print(f"[webui] YouTube login failed: {ex}")
        return RedirectResponse(f"/?yt_error={quote(f'{type(ex).__name__}: {ex}'[:300])}")


@app.get("/youtube/callback")
def yt_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code:
        return RedirectResponse("/?yt_error=no_code")
    try:
        youtube_oauth.handle_callback(code, state)
        return RedirectResponse("/?yt=connected")
    except Exception as ex:  # noqa: BLE001
        print(f"[webui] YouTube callback failed: {ex}")
        return RedirectResponse(f"/?yt_error={quote(f'{type(ex).__name__}: {ex}'[:300])}")


# Separate opt-in consent round-trip for the monetary scope (Settings ->
# "Connect monetary analytics") -- deliberately its own pair of routes/state,
# never touched by the main /youtube/login /youtube/callback flow above.
@app.get("/youtube/monetary/login")
def yt_monetary_login():
    try:
        return RedirectResponse(youtube_oauth.monetary_authorization_url())
    except Exception as ex:  # noqa: BLE001
        return RedirectResponse(f"/?yt_error={type(ex).__name__}")


@app.get("/youtube/monetary/callback")
def yt_monetary_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code:
        return RedirectResponse("/?yt_error=no_code")
    try:
        youtube_oauth.monetary_handle_callback(code, state)
        return RedirectResponse("/?yt_monetary=connected")
    except Exception as ex:  # noqa: BLE001
        return RedirectResponse(f"/?yt_error={type(ex).__name__}")


_warmer_task = None


def _start_stats_warmer() -> None:
    """Keep stats.py's YouTube caches warm in the background (see
    stats.warm_caches) so building a page never waits on the network."""
    global _warmer_task

    async def loop() -> None:
        while True:
            await asyncio.to_thread(stats.warm_caches)
            await asyncio.sleep(stats.WARM_EVERY_SECS)
    if _warmer_task is None or _warmer_task.done():
        _warmer_task = asyncio.create_task(loop())


def run() -> None:
    auth.install(app)
    # Batch upload queue: start draining assets/job_queue.json once the event
    # loop is up (see webui/jobs.py's JobQueue — additive to the existing
    # single-job model, so this is the only new startup wiring it needs).
    app.on_startup(jobs.start_queue_drain)
    app.on_startup(_start_stats_warmer)
    # Fonts only, and public (the login page uses them too; see auth.py).
    app.add_static_files("/static/fonts", os.path.join(config.ASSETS_DIR, "fonts"))
    app.add_static_files("/media", config.ASSETS_DIR)
    app.add_static_files("/videos", config.OUTPUT_DIR)
    app.add_static_files("/music", config.MUSIC_DIR)
    app.add_static_files("/visuals", config.VISUALS_DIR)

    ssl_kwargs = {}
    if config.SSL_CERTFILE and config.SSL_KEYFILE:
        if os.path.exists(config.SSL_CERTFILE) and os.path.exists(config.SSL_KEYFILE):
            ssl_kwargs = {"ssl_certfile": config.SSL_CERTFILE, "ssl_keyfile": config.SSL_KEYFILE}
        else:
            print("[webui] WEBUI_SSL_CERTFILE/KEYFILE set but not found on disk "
                  "-- serving plain HTTP")

    ui.run(
        host=config.HTTP_HOST,
        port=config.HTTP_PORT,
        title="Lo-fi Factory Studio",
        storage_secret=config.STORAGE_SECRET,
        reload=False,
        show=False,
        dark=True,
        **ssl_kwargs,
    )
