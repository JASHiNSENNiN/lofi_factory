"""
app.py — "Lofi Studio" web control panel for the Lo-fi Factory.

A creator-studio UI (sidebar + Now-Rendering hero + live channel stats + a
library grid of rendered videos) over the existing run.py / publish.py pipeline.
Design system in theme.py, spec in DESIGN.md. Run via:  python webui.py
"""
from __future__ import annotations

import json
import os
import re
import time

from fastapi import Request
from fastapi.responses import RedirectResponse

from nicegui import app, ui

from . import auth, automation, config, data, jobs, stats, theme, youtube_oauth

NAV = [
    ("studio", "Studio", "graphic_eq"),
    ("library", "Library", "grid_view"),
    ("samples", "Samples", "library_music"),
    ("live", "Live", "sensors"),
    ("trends", "Trends", "trending_up"),
    ("analytics", "Analytics", "insights"),
    ("automation", "Automation", "autorenew"),
    ("settings", "Settings", "settings"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Shared bits
# ─────────────────────────────────────────────────────────────────────────────
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


# Ported from dashboard.py's TUI stage-detection / ffmpeg progress parsing so the
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


def render_dialog() -> None:
    yt_connected = youtube_oauth.status()["connected"]
    with ui.dialog() as dlg, theme.card(title="New render", classes="w-96 gap-3"):
        tsel = ui.select(config.THEMES, value=config.DEFAULT_THEME, label="Theme").classes("w-full")
        dsel = ui.select(config.DURATIONS, value=config.DEFAULT_DURATION, label="Duration").classes("w-full")
        psel = ui.select(config.PRIVACY, value=config.DEFAULT_PRIVACY, label="Privacy").classes("w-full")
        if not yt_connected:
            ui.label("YouTube isn't connected yet — connect it in Settings before uploading. "
                     "\"Render only\" works fine without it.").classes(f"{theme.SUB} text-amber")

        async def go(upload: bool) -> None:
            if jobs.manager.is_busy():
                ui.notify("A render is already running.", type="warning")
                return
            if upload:
                args = ["publish.py", "auto", "--privacy", psel.value, "--duration", dsel.value]
                if tsel.value != "random":
                    args += ["--theme", tsel.value]
                name = "render+upload"
            else:
                args = ["run.py", "--skip-upload", "--duration", dsel.value]
                if tsel.value != "random":
                    args += ["--theme", tsel.value]
                name = "render"
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
                        ui.label("🎧")
                with ui.column().classes("gap-2 grow min-w-0"):
                    with ui.row().classes("items-center gap-2"):
                        status = ui.label().classes("pill")
                        ttl = ui.label("").classes("text-h1")
                    sub = ui.label("").classes("studio-sub")
                    theme.waveform(30)
                    prog = ui.linear_progress(value=1.0, show_value=False)\
                        .props("indeterminate rounded color=primary").classes("w-full")
            with ui.row().classes("gap-3 mt-4"):
                ui.button("New render", icon="add",
                          on_click=render_dialog).props("color=primary")
                ui.button("Go live", icon="sensors",
                          on_click=lambda: set_view("live")).props("color=secondary")
                ui.button("Cancel", icon="stop",
                          on_click=lambda: jobs.manager.cancel()).props("flat color=negative")

        def refresh_hero() -> None:
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
            else:
                status.text = "● IDLE"
                status.classes(remove=_HERO_STATUS_CLASSES, add="text-teal")
                ttl.text = "Studio idle"
                sub.text = "Press New render to generate a fresh lofi video."
                prog.visible = False

        refresh_hero()
        ui.timer(1.0, refresh_hero)

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

            def refresh_stats() -> None:
                s = stats.channel_stats()
                cells["subs"].text = stats.fmt_count(s["subs"])
                cells["views"].text = stats.fmt_count(s["views"])
                cells["videos"].text = stats.fmt_count(s["videos"])

            refresh_stats()
            ui.timer(30.0, refresh_stats)

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

            theme.data_row([
                {"icon": _STATUS_ICON.get(j.status, "help"), "color": color_cls},
                {"text": j.name, "classes": "text-body font-medium", "width": "lg"},
                {"text": j.status, "color": color_cls, "width": "sm"},
                {"text": _fmt_elapsed(j.duration), "classes": theme.SUB, "width": "xs"},
                {"text": _last_stage(j) if j.status == "failed" else "", "classes": f"{theme.SUB} truncate"},
            ], extra=(lambda: ui.button("View", icon="visibility", on_click=_view)
                      .props("flat dense color=primary")) if card else None)


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
                            f'src="/videos/{c["video_file"]}"></video>'
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
    busy = jobs.manager.is_busy()
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
            with ui.column().classes("w-full gap-1").style(
                    "max-height:180px; overflow-y:auto"):
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


def _open_detail(cards: list[dict], index: int, on_change=lambda: None) -> None:
    c = cards[index]
    with ui.dialog() as dlg, theme.card(classes="w-full gap-3 max-w-3xl"):
        with ui.row().classes("w-full items-start justify-between no-wrap"):
            with ui.column().classes("gap-0"):
                ui.label(c["title"]).classes(theme.H)
                ui.label(f"{c['theme']} · {c['when']}").classes(theme.SUB)
            with ui.row().classes("gap-1 no-wrap"):
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
                f'src="https://www.youtube.com/embed/{c["video_id"]}" '
                f'allowfullscreen></iframe>'
            )
        elif c.get("video_file"):
            ui.html(
                f'<video controls preload="metadata" class="detail-media" '
                f'poster="/media/{c["thumb_name"]}">'
                f'<source src="/videos/{c["video_file"]}" type="video/mp4"></video>'
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
            points = stats.retention(c["video_id"])
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
    dlg.open()


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
            render()


_PILL_STATUS_CLASSES = "text-muted text-teal text-rose text-amber"


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
                elif st["alive"]:
                    pill.text = "🔴 LIVE"
                    pill.classes(remove=_PILL_STATUS_CLASSES, add="text-teal")
                    started = (st.get("started_at") or "")[:16].replace("T", " ")
                    detail.text = f"{st.get('title', '')} · started {started}"
                else:
                    pill.text = "⚠ CRASHED / STALE"
                    pill.classes(remove=_PILL_STATUS_CLASSES, add="text-rose")
                    detail.text = ("live_state.json says a stream is running, but the ffmpeg "
                                   "process is gone. Use Force kill / End stream to clean up.")

            refresh_live_status()
            ui.timer(5.0, refresh_live_status)

        with theme.card("Live stream", "Start, end, or inspect a 24/7 broadcast."):
            with ui.row().classes("items-end gap-4"):
                qsel = ui.select(config.STREAM_QUALITY, value="720p15", label="Quality").classes("w-40")
                psel = ui.select(config.PRIVACY, value="public", label="Privacy").classes("w-36")

            async def start() -> None:
                try:
                    await jobs.manager.run(
                        "live", ["publish.py", "live", "--quality", qsel.value,
                                 "--privacy", psel.value], slot="stream")
                    ui.notify("Starting live stream…", type="positive")
                except RuntimeError as e:
                    ui.notify(str(e), type="warning")

            async def end() -> None:
                try:
                    await jobs.manager.run("end", ["publish.py", "end"], slot="stream")
                except RuntimeError as e:
                    ui.notify(str(e), type="warning")

            async def check_status() -> None:
                try:
                    await jobs.manager.run("status", ["publish.py", "status"], slot="stream")
                except RuntimeError as e:
                    ui.notify(str(e), type="warning")

            with ui.row().classes("gap-3 mt-2"):
                ui.button("Start stream", icon="sensors", on_click=start).props("color=primary")
                ui.button("End stream", icon="stop_circle", on_click=end).props("color=negative")
                ui.button("Status", icon="info", on_click=check_status).props("flat color=primary")
                ui.button("Force kill", icon="power_settings_new",
                          on_click=lambda: jobs.manager.cancel(slot="stream"))\
                    .props("flat color=negative")
        with theme.card("Stream output"):
            live_log(lambda: jobs.manager.stream or jobs.manager.current, height="h-80")


def view_trends(root) -> None:
    with root:
        with theme.card("lofi-inator",
                        "Discover trending songs, generate lofi covers, upload to the "
                        "lofi-inator playlist."):
            with ui.row().classes("items-end gap-4"):
                limit = ui.number("Limit", value=1, min=1, max=10, format="%d").classes("w-28")
                save_only = ui.switch("Save only (no upload)", value=False)

            async def run_inator() -> None:
                if jobs.manager.is_busy():
                    ui.notify("A job is already running.", type="warning")
                    return
                args = ["publish.py", "lofi-inator", "--limit", str(int(limit.value or 1))]
                if save_only.value:
                    args.append("--save-only")
                await jobs.manager.run("lofi-inator", args)
                ui.notify("Running lofi-inator…", type="positive")

            ui.button("Run lofi-inator", icon="auto_awesome",
                      on_click=run_inator).props("color=primary").classes("mt-2")
        with theme.card("Output"):
            live_log(lambda: jobs.manager.current, height="h-72")


_PILLAR_MARKER_COLOR = {"▲": "text-teal", "▼": "text-rose", " ": "text-amber"}
# echarts itemStyle needs real hex (can't reach into CSS custom properties from
# a JSON series config), so this mirrors _PILLAR_MARKER_COLOR using the same
# theme constants instead of a second set of raw literals.
_PILLAR_MARKER_HEX = {"▲": theme.TEAL, "▼": theme.ROSE, " ": theme.PRIMARY}


def view_analytics(root) -> None:
    with root:
        from scripts import analytics as analytics_mod

        data_dict = analytics_mod.load_analytics()
        result = analytics_mod.compute_pillar_stats(data_dict)

        def do_sync() -> None:
            try:
                analytics_mod.sync_analytics()
                ui.notify("Analytics synced", type="positive")
            except Exception as e:  # noqa: BLE001 -- surface any sync failure, don't crash the page
                ui.notify(f"Sync failed: {e}", type="negative")
                return
            set_view("analytics")

        with theme.card():
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Performance by pillar").classes(theme.H)
                ui.button("Sync now", icon="sync", on_click=do_sync)\
                    .props("flat dense color=primary")
            ui.label("How CTR/watch-time compares across SEO title pillars, based on "
                     "uploads 7-90 days old. Feeds back into which pillar gets picked more "
                     "often for future renders (see generate_seo.py's pillar weighting).")\
                .classes(theme.SUB)

            if not result["by_pillar"]:
                ui.label("No analytics data yet. Needs uploaded videos with 7+ days of view "
                         "history, then hit Sync now (or run "
                         "`python scripts/analytics.py --report` on the server).")\
                    .classes(theme.SUB + " mt-3")
            else:
                with ui.row().classes("w-full gap-4 no-wrap mt-2 overflow-x-auto"):
                    with ui.element("div").classes("stat grow"):
                        ui.label(f"{result['channel_avg_ctr'] * 100:.1f}%").classes("stat-num")
                        ui.label("Channel avg CTR").classes("stat-lbl")
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

        if data_dict:
            with theme.card("Per-video performance",
                            "Every tracked upload, most-clicked first. Click a row to open it "
                            "(retention chart, player) the same way as from Library."):
                vids = list(data_dict.keys())
                engagement = stats.video_engagement(vids)
                card_by_vid = {c["video_id"]: c for c in stats.library(limit=200)
                               if c.get("video_id")}

                rows = []
                for vid, d in data_dict.items():
                    eng = engagement.get(vid, {})
                    rows.append({
                        "video_id": vid,
                        "title": d.get("title") or vid,
                        "pillar": d.get("pillar") or "—",
                        "ctr": d.get("videoThumbnailImpressionsClickRate", 0) or 0,
                        "views": int(d.get("views", 0) or 0),
                        "watch_min": round(d.get("averageViewDuration", 0) or 0) // 60,
                        "likes": eng.get("likes"),
                        "comments": eng.get("comments"),
                    })
                rows.sort(key=lambda r: r["ctr"], reverse=True)

                with ui.column().classes("w-full gap-1 mt-2 table-scroll").style(
                        "max-height:420px; overflow-y:auto"):
                    theme.data_row([
                        {"text": "Title", "width": "grow"},
                        {"text": "Pillar", "width": "md"},
                        {"text": "CTR", "width": "xs"},
                        {"text": "Views", "width": "sm"},
                        {"text": "Watch", "width": "xs"},
                        {"text": "Likes", "width": "xs"},
                        {"text": "Comments", "width": "sm"},
                    ], header=True)
                    for r in rows:
                        card = card_by_vid.get(r["video_id"])

                        def _open(r=r, card=card) -> None:
                            if card:
                                _open_detail([card], 0)
                            elif r["video_id"]:
                                ui.navigate.to(
                                    f"https://youtube.com/watch?v={r['video_id']}",
                                    new_tab=True)

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
                        ], on_click=_open)

        swapped = [{"video_id": vid, **d} for vid, d in data_dict.items() if d.get("thumb_swapped")]
        with theme.card("Thumbnail A/B testing",
                        "Runs automatically with the daily analytics sync (lofi-analytics.timer): "
                        "any video 7-30 days old with CTR below 70% of the channel average gets "
                        "its thumbnail swapped to the alt variant generated alongside it during "
                        "render."):
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


def view_automation(root) -> None:
    with root:
        with theme.card("Auto-upload schedule",
                        "Runs `publish.py auto` on a systemd timer (lofi-auto), independent of "
                        "the web UI — it keeps generating and uploading on schedule even if this "
                        "panel restarts or the browser is closed."):
            with ui.row().classes("items-center gap-2"):
                pill = ui.label().classes("pill")
                sub = ui.label("").classes(theme.SUB)
            next_lbl = ui.label("").classes(theme.SUB)

            def refresh_status() -> None:
                st = automation.status()
                if not st["installed"]:
                    pill.text = "⚠ NOT INSTALLED"
                    pill.classes(remove=_PILL_STATUS_CLASSES, add="text-amber")
                    sub.text = "Run deploy/setup.sh on this server to install lofi-auto.timer."
                    next_lbl.text = ""
                    for b in (start_btn, stop_btn, boot_btn, run_now_btn, hour_sel, every_sel, apply_btn):
                        b.visible = False
                    return
                for b in (start_btn, stop_btn, boot_btn, run_now_btn, hour_sel, every_sel, apply_btn):
                    b.visible = True
                if st["running_now"]:
                    pill.text = "● RUNNING NOW"
                    pill.classes(remove=_PILL_STATUS_CLASSES, add="text-amber")
                elif st["active"]:
                    pill.text = "● ARMED"
                    pill.classes(remove=_PILL_STATUS_CLASSES, add="text-teal")
                else:
                    pill.text = "○ STOPPED"
                    pill.classes(remove=_PILL_STATUS_CLASSES, add="text-rose")
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

            async def do_start() -> None:
                try:
                    automation.start()
                    ui.notify("Schedule armed", type="positive")
                except RuntimeError as e:
                    ui.notify(str(e), type="negative")
                refresh_status()

            async def do_stop() -> None:
                try:
                    automation.stop()
                    ui.notify("Schedule stopped", type="warning")
                except RuntimeError as e:
                    ui.notify(str(e), type="negative")
                refresh_status()

            async def do_toggle_boot() -> None:
                try:
                    automation.set_enabled(not automation.status()["enabled"])
                except RuntimeError as e:
                    ui.notify(str(e), type="negative")
                refresh_status()

            async def do_run_now() -> None:
                try:
                    automation.run_now()
                    ui.notify("Triggered an immediate run — see the log below", type="positive")
                except RuntimeError as e:
                    ui.notify(str(e), type="negative")
                refresh_status()

            async def do_apply_schedule() -> None:
                try:
                    automation.set_schedule(int(hour_sel.value), int(every_sel.value))
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

        with theme.card("Automation log", "Live tail of the run's journal."):
            log = ui.log(max_lines=4000).classes(f"{theme.LOG} w-full h-80")
            proc_holder: dict = {}

            def on_line(line: str) -> None:
                log.push(line)

            async def start_tail() -> None:
                try:
                    proc_holder["proc"] = await automation.tail_logs(on_line)
                except FileNotFoundError:
                    log.push("[webui] journalctl not found — can't tail logs on this host.")

            ui.timer(0.1, start_tail, once=True)

            def stop_tail() -> None:
                proc = proc_holder.get("proc")
                if proc and proc.returncode is None:
                    proc.terminate()

            ui.context.client.on_disconnect(stop_tail)


def _env_field(label: str, key: str, *, secret: bool = False) -> None:
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
            ui.notify(f"{key} saved — restart the panel to apply", type="positive")
            if secret:
                inp.value = ""
                relabel(True)

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
                        ui.label("⚠ client_secret.json missing — add it to the repo root.")\
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
                                  label="Upload client_secret.json")\
                            .props("accept=.json color=primary").classes("max-w-md")
                    elif st["needs_web_client"]:
                        ui.label("⚠ Desktop OAuth client + tunnel: in-browser re-login needs a "
                                 "Web-application client. (Local login works as-is.)")\
                            .classes("text-sm text-amber")
                    ui.label("Redirect URI for Google Cloud Console:").classes(theme.SUB + " mt-1")
                    ui.label(st["redirect_uri"]).classes("font-mono text-sm code-chip")
                    ui.label(
                        "⚠ Before relying on unattended auto-uploads: publish the OAuth "
                        "consent screen to Production in Google Cloud Console. Apps left in "
                        "Testing mode get refresh tokens that expire after 7 days, which "
                        "silently breaks lofi-auto's scheduled runs once it happens."
                    ).classes("text-sm mt-2 text-amber")

            refresh_yt()

            with ui.column().classes("gap-2 w-full mt-3"):
                ui.separator()
                ui.label("Alternative: connect via device code").classes(theme.H)
                ui.label(
                    "No redirect back to this box needed -- works even if your device can't "
                    "resolve this box's hostname (e.g. a phone with Tailscale MagicDNS "
                    "trouble). You visit a plain Google page and type a short code instead. "
                    "Needs a separate 'TVs and Limited Input devices' OAuth client from "
                    "Google Cloud Console (Web application clients are rejected for this).")\
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
                              label="Upload TV/device OAuth client JSON")\
                        .props("accept=.json color=primary").classes("max-w-md")
                else:
                    state = {"timer": None}
                    prompt = ui.column().classes("gap-1 w-full")

                    async def start_device_flow() -> None:
                        if state["timer"]:
                            state["timer"].active = False
                        prompt.clear()
                        try:
                            d = youtube_oauth.device_flow_start()
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
                                youtube_oauth.device_flow_poll(d["device_code"])
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

        with theme.card("yt-dlp cookies",
                        "Server IPs are bot-gated by YouTube. Upload a Netscape cookies.txt "
                        "(browser logged into YouTube) to enable audio covers."):
            cookie_status = ui.label().classes("text-sm")

            def refresh_cookie() -> None:
                cs = data.cookies_status()
                if cs["present"]:
                    cookie_status.text = f"✅ cookies.txt ({cs['size_kb']} KB, {cs['modified']})"
                    cookie_status.classes(remove="text-teal text-rose", add="text-teal")
                else:
                    cookie_status.text = "❌ no cookies.txt — downloads fall back to MIDI"
                    cookie_status.classes(remove="text-teal text-rose", add="text-rose")

            async def on_upload(e) -> None:
                raw = await e.file.read()
                with open(config.COOKIES_FILE, "wb") as f:
                    f.write(raw)
                refresh_cookie()
                ui.notify("cookies.txt saved", type="positive")

            ui.upload(on_upload=on_upload, auto_upload=True, label="Upload cookies.txt")\
                .props("accept=.txt color=primary").classes("max-w-md")
            refresh_cookie()

        with theme.card("Integrations & credentials",
                        "Saved to .env — restart lofi-webui.service to apply. Secret fields "
                        "never show their current value, only whether one is set; leave "
                        "blank to keep it unchanged."):
            _env_field("YouTube stream key", "YT_STREAM_KEY", secret=True)
            _env_field("YouTube channel ID", "YT_CHANNEL_ID")
            ui.separator()

            llm_current = config.read_env_file().get("LOFI_LLM_FAILSAFE", "") == "1"
            llm_switch = ui.switch(
                "Allow LLM failsafe (Groq/Gemini) when procedural generation fails",
                value=llm_current)

            def save_llm_failsafe() -> None:
                config.write_env_value("LOFI_LLM_FAILSAFE", "1" if llm_switch.value else "")
                ui.notify("Saved — restart the panel to apply", type="positive")

            llm_switch.on_value_change(save_llm_failsafe)
            _env_field("Groq API key", "GROQ_API_KEY", secret=True)
            _env_field("Gemini API key", "GEMINI_API_KEY", secret=True)
            _env_field("Gemini API key (backup)", "GEMINI_API_KEY_BACKUP", secret=True)
            ui.separator()
            _env_field("Spotify client ID", "SPOTIFY_CLIENT_ID")
            _env_field("Spotify client secret", "SPOTIFY_CLIENT_SECRET", secret=True)
            ui.separator()
            _env_field("Stream alert webhook (Slack/Discord)", "LOFI_STREAM_ALERT_WEBHOOK")

        with theme.card("Render defaults",
                        "Pre-selected values when opening \"New render\" — saves re-picking "
                        "the same options every time. Takes effect after restarting the panel."):
            with ui.row().classes("w-full items-end gap-4"):
                dt_sel = ui.select(config.THEMES, value=config.DEFAULT_THEME,
                                    label="Default theme").classes("w-48")
                dd_sel = ui.select(config.DURATIONS, value=config.DEFAULT_DURATION,
                                    label="Default duration").classes("w-40")
                dp_sel = ui.select(config.PRIVACY, value=config.DEFAULT_PRIVACY,
                                    label="Default privacy").classes("w-36")

            def save_render_defaults() -> None:
                config.write_env_value("DEFAULT_THEME", dt_sel.value)
                config.write_env_value("DEFAULT_DURATION", dd_sel.value)
                config.write_env_value("DEFAULT_PRIVACY", dp_sel.value)
                ui.notify("Render defaults saved — restart the panel to apply", type="positive")

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
        busy = jobs.manager.is_busy()

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
                        f'src="/music/{t["name"]}"></audio>'
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
                            f'src="/visuals/{v["name"]}"></video>'
                        )
                        with ui.row().classes("w-full items-center justify-between no-wrap"):
                            ui.label(f"{v['theme']} · {_fmt_dur(v['duration_secs'])} · "
                                     f"{v['size_mb']} MB").classes(theme.SUB)
                            ui.button(icon="delete_outline", color="negative",
                                      on_click=lambda v=v: _confirm_delete_sample(
                                          v["path"], v["name"], lambda: set_view("samples")))\
                                .props("flat round dense").set_visibility(not busy)


VIEWS = {
    "studio": view_studio, "library": view_library, "live": view_live,
    "trends": view_trends, "analytics": view_analytics, "samples": view_samples,
    "automation": view_automation, "settings": view_settings,
}

# Per-client mutable holder for the active view + nav element refs.
set_view = lambda name: None  # noqa: E731 — reassigned inside the page


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────
@ui.page("/")
def index() -> None:
    theme.apply()
    state = {"current": "studio"}
    nav_refs: dict[str, object] = {}

    drawer = ui.left_drawer(value=False).classes("studio-sidebar p-3")\
        .props("breakpoint=768 show-if-above bordered")

    with ui.header().classes("lg:hidden items-center gap-2 px-3 py-2 appbar-mobile"):
        ui.button(icon="menu", on_click=drawer.toggle).props("flat round dense color=white")
        ui.label("🎧 LO-FI FACTORY").classes("studio-brand")

    with drawer:
        with ui.row().classes("items-center gap-2 px-2 pt-1 pb-3"):
            ui.label("🎧").classes("text-2xl")
            ui.label("LO-FI FACTORY").classes("studio-brand")
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
        content.clear()
        VIEWS[name](content)

    async def _nav_click(name: str) -> None:
        _set(name)
        # Only auto-close on mobile -- show-if-above keeps it pinned open on desktop
        # regardless, but only in response to an actual resize, not every render, so an
        # unconditional hide() here would also collapse it on wide screens.
        if await ui.run_javascript("window.innerWidth < 768"):
            drawer.hide()

    global set_view
    set_view = _set
    _set("studio")


@ui.page("/login")
def login_page() -> None:
    theme.apply()
    if auth.is_authenticated():
        ui.navigate.to("/")
        return
    with theme.card(classes="absolute-center w-80 gap-3 flex flex-col"):
        ui.label("🎧 LO-FI FACTORY").classes("studio-brand self-center")
        ui.label("studio control panel").classes(theme.SUB + " self-center")
        if not config.is_configured():
            ui.label("No WEBUI_PASSWORD set. Add it to .env and restart.")\
                .classes("text-sm text-amber")
            return
        pw = ui.input("Password", password=True, password_toggle_button=True)\
            .classes("w-full").on("keydown.enter", lambda: do_login())

        def do_login() -> None:
            if auth.check_password(pw.value or ""):
                auth.login()
                ui.navigate.to(app.storage.user.get("referrer_path", "/"))
            else:
                ui.notify("Wrong password", type="negative")

        ui.button("Enter studio", on_click=do_login).props("color=primary").classes("w-full mt-1")


# ── OAuth routes ──────────────────────────────────────────────────────────────
@app.get("/youtube/login")
def yt_login():
    try:
        return RedirectResponse(youtube_oauth.authorization_url())
    except Exception as ex:  # noqa: BLE001
        return RedirectResponse(f"/?yt_error={type(ex).__name__}")


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
        return RedirectResponse(f"/?yt_error={type(ex).__name__}")


def run() -> None:
    auth.install(app)
    app.add_static_files("/media", config.ASSETS_DIR)
    app.add_static_files("/videos", config.OUTPUT_DIR)
    app.add_static_files("/music", config.MUSIC_DIR)
    app.add_static_files("/visuals", config.VISUALS_DIR)

    ssl_kwargs = {}
    if config.SSL_CERTFILE and config.SSL_KEYFILE:
        if os.path.exists(config.SSL_CERTFILE) and os.path.exists(config.SSL_KEYFILE):
            ssl_kwargs = {"ssl_certfile": config.SSL_CERTFILE, "ssl_keyfile": config.SSL_KEYFILE}
        else:
            print(f"[webui] WEBUI_SSL_CERTFILE/KEYFILE set but not found on disk "
                  f"-- serving plain HTTP")

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
