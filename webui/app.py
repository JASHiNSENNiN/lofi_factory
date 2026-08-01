"""
app.py — "Lofi Studio" web control panel for the Lo-fi Factory.

A creator-studio UI (sidebar + Now-Rendering hero + live channel stats + a
library grid of rendered videos) over the existing run.py / publish.py pipeline.
Design system in theme.py, spec in DESIGN.md. Run via:  python webui.py
"""
from __future__ import annotations

import time

from fastapi import Request
from fastapi.responses import RedirectResponse

from nicegui import app, ui

from . import auth, automation, config, data, jobs, stats, theme, youtube_oauth

NAV = [
    ("studio", "Studio", "graphic_eq"),
    ("library", "Library", "grid_view"),
    ("live", "Live", "sensors"),
    ("trends", "Trends", "trending_up"),
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


def _fmt_elapsed(secs: float) -> str:
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def render_dialog() -> None:
    with ui.dialog() as dlg, ui.element("div").classes("studio-card w-96 gap-3"):
        ui.label("New render").classes(theme.H)
        tsel = ui.select(config.THEMES, value="random", label="Theme").classes("w-full")
        dsel = ui.select(config.DURATIONS, value="2 hours", label="Duration").classes("w-full")
        psel = ui.select(config.PRIVACY, value="public", label="Privacy").classes("w-full")

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
            ui.button("Render + Upload", on_click=lambda: go(True)).props("color=primary")
    dlg.open()


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────
def view_studio(root) -> None:
    with root:
        # ── Hero: Now Rendering ────────────────────────────────────────────────
        with ui.element("div").classes("hero w-full"):
            with ui.row().classes("items-center gap-5 no-wrap w-full"):
                lib = stats.library(limit=1)
                if lib:
                    ui.image(f"/media/{lib[0]['thumb_name']}")\
                        .style("width:148px;height:148px;border-radius:18px")\
                        .classes("hero-art").props("fit=cover")
                else:
                    with ui.element("div").classes("hero-art hero-art-empty")\
                            .style("width:148px;height:148px"):
                        ui.label("🎧")
                with ui.column().classes("gap-2 grow min-w-0"):
                    with ui.row().classes("items-center gap-2"):
                        status = ui.label().classes("pill")
                        ttl = ui.label("").classes("studio-h")
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
                status.style("color:#e8a45c")
                ttl.text = j.name
                sub.text = f"{_fmt_elapsed(time.time() - j.started_at)} elapsed · {_last_stage(j)}"
                prog.visible = True
            elif jobs.manager.stream_running():
                status.text = "🔴 LIVE"
                status.style("color:#e8849a")
                ttl.text = "Broadcasting"
                sub.text = f"{_fmt_elapsed(time.time() - jobs.manager.stream.started_at)} on air"
                prog.visible = False
            else:
                status.text = "● IDLE"
                status.style("color:#6fcaa8")
                ttl.text = "Studio idle"
                sub.text = "Press New render to generate a fresh lofi video."
                prog.visible = False

        refresh_hero()
        ui.timer(1.0, refresh_hero)

        # ── Stat cards ─────────────────────────────────────────────────────────
        with ui.row().classes("w-full gap-4 no-wrap"):
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
        with ui.element("div").classes("studio-card w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Recent renders").classes(theme.H)
                ui.button("View all", on_click=lambda: set_view("library"))\
                    .props("flat dense color=primary")
            _library_grid(stats.library(limit=8))

        # ── Collapsible live output ────────────────────────────────────────────
        with ui.expansion("Live output", icon="terminal").classes("studio-card w-full"):
            live_log(lambda: jobs.manager.current, height="h-72")


def _library_grid(cards: list[dict]) -> None:
    if not cards:
        ui.label("No renders yet.").classes(theme.SUB)
        return
    with ui.element("div").classes(
            "w-full grid gap-3 mt-2").style(
            "grid-template-columns:repeat(auto-fill,minmax(190px,1fr))"):
        for c in cards:
            def open_url(u=c["url"]):
                if u:
                    ui.navigate.to(u, new_tab=True)
                else:
                    ui.notify("No public URL for this render", type="info")
            with ui.element("div").classes("libcard").on("click", open_url):
                ui.image(f"/media/{c['thumb_name']}").props("ratio=1.7778 fit=cover")
                with ui.element("div").classes("meta"):
                    ui.label(c["title"]).classes("t")
                    ui.label(f"{c['theme']} · {c['when']}").classes("d")


def view_library(root) -> None:
    with root:
        with ui.element("div").classes("studio-card w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Library").classes(theme.H)
                ui.button("Refresh", icon="refresh",
                          on_click=lambda: set_view("library")).props("flat dense color=primary")
            _library_grid(stats.library(limit=48))


def view_live(root) -> None:
    with root:
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

            with ui.row().classes("gap-3 mt-2"):
                ui.button("Start stream", icon="sensors", on_click=start).props("color=primary")
                ui.button("End stream", icon="stop_circle",
                          on_click=lambda: jobs.manager.run("end", ["publish.py", "end"]))\
                    .props("color=negative")
                ui.button("Status", icon="info",
                          on_click=lambda: jobs.manager.run("status", ["publish.py", "status"]))\
                    .props("flat color=primary")
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
                    pill.style("color:#e8a45c")
                    sub.text = "Run deploy/setup.sh on this server to install lofi-auto.timer."
                    next_lbl.text = ""
                    for b in (start_btn, stop_btn, boot_btn, run_now_btn, hour_sel, every_sel, apply_btn):
                        b.visible = False
                    return
                for b in (start_btn, stop_btn, boot_btn, run_now_btn, hour_sel, every_sel, apply_btn):
                    b.visible = True
                if st["running_now"]:
                    pill.text = "● RUNNING NOW"
                    pill.style("color:#e8a45c")
                elif st["active"]:
                    pill.text = "● ARMED"
                    pill.style("color:#6fcaa8")
                else:
                    pill.text = "○ STOPPED"
                    pill.style("color:#e8849a")
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
                            .classes("text-warning text-sm").style("color:#e8a45c")
                    elif st["needs_web_client"]:
                        ui.label("⚠ Desktop OAuth client + tunnel: in-browser re-login needs a "
                                 "Web-application client. (Local login works as-is.)")\
                            .style("color:#e8a45c").classes("text-sm")
                    ui.label("Redirect URI for Google Cloud Console:").classes(theme.SUB + " mt-1")
                    ui.label(st["redirect_uri"]).classes("font-mono text-sm")\
                        .style("background:rgba(0,0,0,.35);padding:3px 8px;border-radius:8px")

            refresh_yt()

        with theme.card("yt-dlp cookies",
                        "Server IPs are bot-gated by YouTube. Upload a Netscape cookies.txt "
                        "(browser logged into YouTube) to enable audio covers."):
            cookie_status = ui.label().classes("text-sm")

            def refresh_cookie() -> None:
                cs = data.cookies_status()
                if cs["present"]:
                    cookie_status.text = f"✅ cookies.txt ({cs['size_kb']} KB, {cs['modified']})"
                    cookie_status.style("color:#6fcaa8")
                else:
                    cookie_status.text = "❌ no cookies.txt — downloads fall back to MIDI"
                    cookie_status.style("color:#e8849a")

            def on_upload(e) -> None:
                with open(config.COOKIES_FILE, "wb") as f:
                    f.write(e.content.read())
                refresh_cookie()
                ui.notify("cookies.txt saved", type="positive")

            ui.upload(on_upload=on_upload, auto_upload=True, label="Upload cookies.txt")\
                .props("accept=.txt color=primary").classes("max-w-md")
            refresh_cookie()


VIEWS = {
    "studio": view_studio, "library": view_library, "live": view_live,
    "trends": view_trends, "automation": view_automation, "settings": view_settings,
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

    with ui.left_drawer(value=True, fixed=True).classes("studio-sidebar p-3"):
        with ui.row().classes("items-center gap-2 px-2 pt-1 pb-3"):
            ui.label("🎧").classes("text-2xl")
            ui.label("LO-FI FACTORY").classes("studio-brand")
        for key, label, icon in NAV:
            item = ui.element("div").classes("nav-item")
            with item:
                ui.icon(icon)
                ui.label(label)
            item.on("click", lambda k=key: _set(k))
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

    global set_view
    set_view = _set
    _set("studio")


@ui.page("/login")
def login_page() -> None:
    theme.apply()
    if auth.is_authenticated():
        ui.navigate.to("/")
        return
    with ui.element("div").classes("studio-card absolute-center w-80 gap-3").style(
            "display:flex;flex-direction:column"):
        ui.label("🎧 LO-FI FACTORY").classes("studio-brand self-center")
        ui.label("studio control panel").classes(theme.SUB + " self-center")
        if not config.is_configured():
            ui.label("No WEBUI_PASSWORD set. Add it to .env and restart.")\
                .style("color:#e8a45c").classes("text-sm")
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
    ui.run(
        host=config.HTTP_HOST,
        port=config.HTTP_PORT,
        title="Lo-fi Factory Studio",
        storage_secret=config.STORAGE_SECRET,
        reload=False,
        show=False,
        dark=True,
    )
