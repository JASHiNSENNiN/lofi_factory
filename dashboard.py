"""
dashboard.py — Lo-fi Factory TUI Dashboard
==========================================
Real-time terminal dashboard for monitoring and controlling the lofi pipeline.

Usage:
  python dashboard.py          # open dashboard directly
  ./lofi                       # recommended: open inside tmux (SSH-resilient)
  python publish.py dashboard  # alias

Keyboard shortcuts:
  a  — Auto: generate fresh video + upload
  l  — Live: start YouTube live stream
  e  — End:  end active live stream
  r  — Refresh state immediately
  q  — Quit

SSH resilience: run via ./lofi which wraps this in a tmux session.
If you close SSH and reconnect: tmux attach -t lofi
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import glob
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))

import auto_service

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Label, RichLog, Static, DataTable
from textual.reactive import reactive
from rich.text import Text
from rich.panel import Panel


# ── Helpers ────────────────────────────────────────────────────────────────────

def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _load_json(path: str):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _fmt_uptime(started_at: str) -> str:
    try:
        # Handle both aware and naive ISO strings
        dt = datetime.fromisoformat(started_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s   = divmod(rem, 60)
        return f"{h}h {m:02d}m {s:02d}s"
    except Exception:
        return "?"


def _fmt_ts(ts_str: str) -> str:
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.strftime("%b %d %H:%M")
    except Exception:
        return ts_str[:16]


def _find_latest_grade_log() -> str | None:
    """Find the most recent ffmpeg grade log from an active assembly job."""
    logs = glob.glob(os.path.join(ROOT, "output", "*.grade.log"))
    if logs:
        return max(logs, key=os.path.getmtime)
    return None


def _find_latest_audio_log() -> str | None:
    """Find the most recent audio concat log from an active assembly job."""
    logs = glob.glob(os.path.join(ROOT, "output", "tmp_*", "audio_concat.log"))
    if logs:
        return max(logs, key=os.path.getmtime)
    return None


def _parse_ffmpeg_progress(line: str) -> dict | None:
    """Parse a ffmpeg stats line: frame= 1234 fps=24.0 time=01:00:00 speed=1.0x"""
    if "time=" not in line:
        return None
    result = {}
    for part in line.split():
        if "=" in part:
            k, _, v = part.partition("=")
            result[k.strip()] = v.strip()
    return result if result else None


# ── Widgets ────────────────────────────────────────────────────────────────────

class StreamPanel(Static):
    """Top-left: live stream status."""

    DEFAULT_CSS = """
    StreamPanel {
        border: solid $primary;
        padding: 1 2;
        height: 10;
        width: 1fr;
    }
    """

    def render_state(self, state: dict | None) -> Text:
        t = Text()
        if state is None:
            t.append("  OFFLINE\n", style="bold dim")
            t.append("\n  No active broadcast.\n")
            t.append("  Press ")
            t.append("[L]", style="bold green")
            t.append(" to start a live stream.")
            return t

        pid   = state.get("ffmpeg_pid")
        alive = bool(pid and _pid_alive(int(pid)))
        url   = state.get("watch_url", "")
        title = state.get("title", "")[:50]
        uptime = _fmt_uptime(state.get("started_at", ""))

        if alive:
            t.append("  LIVE\n", style="bold green")
        else:
            t.append("  CRASHED / STALE\n", style="bold red")

        t.append(f"\n  {title}\n", style="bold")
        if url:
            short = url.replace("https://www.youtube.com", "")
            t.append(f"  {short}\n", style="link " + url)
        t.append(f"\n  Uptime: {uptime}")
        return t

    def update_state(self, state: dict | None) -> None:
        self.update(self.render_state(state))


class UploadsPanel(Static):
    """Top-right: recent upload history."""

    DEFAULT_CSS = """
    UploadsPanel {
        border: solid $primary;
        padding: 1 2;
        height: 10;
        width: 2fr;
    }
    """

    def update_entries(self, entries: list[dict]) -> None:
        t = Text()
        if not entries:
            t.append("  No uploads yet.", style="dim")
            self.update(t)
            return
        for e in reversed(entries[-5:]):
            tag  = f"[{e.get('type','?').upper()[:4]}]"
            ts   = _fmt_ts(e.get("timestamp", ""))
            title = e.get("title", "")[:48]
            url  = e.get("url", "")
            t.append(f"  {tag} ", style="bold cyan")
            t.append(f"{ts}  ", style="dim")
            if url:
                t.append(title, style="link " + url)
            else:
                t.append(title)
            t.append("\n")
        self.update(t)


class JobPanel(Static):
    """Middle: current job progress."""

    DEFAULT_CSS = """
    JobPanel {
        border: solid $accent;
        padding: 0 2;
        height: 5;
    }
    """

    def set_idle(self) -> None:
        t = Text()
        t.append("  No job running. ", style="dim")
        t.append("[A]", style="bold yellow")
        t.append(" auto-generate & upload   ", style="dim")
        t.append("[L]", style="bold green")
        t.append(" start live stream", style="dim")
        self.update(t)

    def set_stage(self, stage: str, detail: str = "") -> None:
        t = Text()
        t.append(f"  {stage}", style="bold yellow")
        if detail:
            t.append(f"  {detail}", style="dim")
        self.update(t)

    def set_ffmpeg(self, parsed: dict, target_secs: int | None = None) -> None:
        time_s  = parsed.get("time", "?")
        fps     = parsed.get("fps", "?")
        speed   = parsed.get("speed", "?")
        frame   = parsed.get("frame", "?")

        bar = ""
        if target_secs and time_s != "?":
            try:
                parts  = [int(x) for x in time_s.split(":")]
                done   = parts[0]*3600 + parts[1]*60 + parts[2]
                pct    = min(done / target_secs, 1.0)
                filled = int(pct * 40)
                bar    = f"  [{'█'*filled}{'░'*(40-filled)}] {pct*100:.0f}%\n"
            except Exception:
                bar = ""

        t = Text()
        if bar:
            t.append(bar, style="green")
        t.append(f"  frame={frame}  fps={fps}  time={time_s}  speed={speed}")
        self.update(t)


class AutoLoopPanel(Static):
    """Thin status bar for the lofi-auto timer (daily render+upload run)."""

    DEFAULT_CSS = """
    AutoLoopPanel {
        border: solid $accent;
        padding: 0 2;
        height: 3;
    }
    """

    def update_state(self, st: dict) -> None:
        t = Text()
        if not st.get("installed"):
            t.append("  Auto-schedule: not installed", style="dim")
            t.append("  — run deploy/setup.sh on the server", style="dim")
            self.update(t)
            return
        if st["running_now"]:
            t.append("  ● Auto-run IN PROGRESS", style="bold yellow")
        elif st["active"]:
            t.append("  ● Auto-schedule ARMED", style="bold green")
        else:
            t.append("  ○ Auto-schedule stopped", style="bold red")
        t.append(f"   every {st['every_hours']}h from {st['start_hour']:02d}:00", style="dim")
        if st.get("next_run"):
            t.append(f"   next: {st['next_run']}", style="dim")
        t.append(f"   boot: {'yes' if st['enabled'] else 'no'}   ", style="dim")
        t.append("[U]", style="bold yellow")
        t.append(" start/stop  ", style="dim")
        t.append("[B]", style="bold yellow")
        t.append(" toggle boot", style="dim")
        self.update(t)


# ── Main App ───────────────────────────────────────────────────────────────────

class LofiDashboard(App):

    TITLE = "Lofi Factory"
    CSS = """
    Screen {
        layout: vertical;
    }
    #top-row {
        layout: horizontal;
        height: 10;
    }
    #job-panel {
        height: 5;
    }
    #log-panel {
        border: solid $surface-lighten-1;
        height: 1fr;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("a", "run_auto",         "Auto gen+upload"),
        Binding("l", "run_live",         "Live stream"),
        Binding("e", "end_stream",       "End stream"),
        Binding("u", "toggle_auto_loop", "Toggle auto-loop"),
        Binding("b", "toggle_auto_boot", "Toggle boot"),
        Binding("r", "refresh",          "Refresh"),
        Binding("q", "quit",             "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self._active_proc: asyncio.subprocess.Process | None = None
        self._log_tail_task: asyncio.Task | None = None
        self._target_secs: int | None = None
        self._stream_state: dict | None = None
        self._uploads: list[dict] = []
        self._last_upload_mtime: float = 0.0

    # ── Compose ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="top-row"):
            yield StreamPanel(id="stream-panel")
            yield UploadsPanel(id="uploads-panel")
        yield JobPanel(id="job-panel")
        yield AutoLoopPanel(id="auto-loop-panel")
        yield RichLog(id="log-panel", highlight=True, markup=False, auto_scroll=True)
        yield Footer()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self.set_interval(2.0,  self._poll_state)
        self.set_interval(10.0, self._poll_uploads)
        self.set_interval(5.0,  self._poll_auto_loop)
        # Initial load
        self._do_poll_state()
        self._do_poll_uploads()
        self._do_poll_auto_loop()
        # Start tailing idle log
        self._start_idle_log_tail()
        self.query_one(JobPanel).set_idle()

    # ── State polling ─────────────────────────────────────────────────────────

    def _poll_state(self) -> None:
        self._do_poll_state()

    def _do_poll_state(self) -> None:
        state_path = os.path.join(ROOT, "live_state.json")
        state = _load_json(state_path)
        self._stream_state = state
        self.query_one(StreamPanel).update_state(state)

    def _poll_uploads(self) -> None:
        self._do_poll_uploads()

    def _do_poll_uploads(self) -> None:
        log_path = os.path.join(ROOT, "upload_log.json")
        try:
            mtime = os.path.getmtime(log_path)
        except FileNotFoundError:
            return
        if mtime == self._last_upload_mtime:
            return
        self._last_upload_mtime = mtime
        entries = _load_json(log_path) or []
        self._uploads = entries
        self.query_one(UploadsPanel).update_entries(entries)

    def _poll_auto_loop(self) -> None:
        self._do_poll_auto_loop()

    def _do_poll_auto_loop(self) -> None:
        st = auto_service.status()
        self.query_one(AutoLoopPanel).update_state(st)

    # ── Log tail (when idle) ──────────────────────────────────────────────────

    def _start_idle_log_tail(self) -> None:
        if self._log_tail_task and not self._log_tail_task.done():
            return
        self._log_tail_task = asyncio.create_task(self._tail_idle_logs())

    def _stop_idle_log_tail(self) -> None:
        if self._log_tail_task and not self._log_tail_task.done():
            self._log_tail_task.cancel()

    async def _tail_idle_logs(self) -> None:
        """Show last lines of stream or assembly logs when no job is active."""
        log = self.query_one(RichLog)
        shown = set()

        # Prefer ffmpeg stream log if a stream is (or was) running
        stream_log = os.path.join(ROOT, "ffmpeg_stream.log")
        grade_log  = _find_latest_grade_log()
        audio_log  = _find_latest_audio_log()

        for path in [stream_log, grade_log, audio_log]:
            if path and os.path.exists(path):
                key = path
                if key not in shown:
                    shown.add(key)
                    log.write(f"[dim]─── {os.path.basename(path)} (tail) ───[/dim]")
                    try:
                        with open(path) as f:
                            lines = f.readlines()
                        for line in lines[-30:]:
                            log.write(line.rstrip())
                    except Exception as e:
                        log.write(f"[dim](could not read log: {e})[/dim]")
                break  # only show one

    # ── Subprocess streaming ──────────────────────────────────────────────────

    async def _run_cmd(self, *args: str, stage: str = "") -> None:
        """Spawn a publish.py command and stream its output to the log panel."""
        if self._active_proc and self._active_proc.returncode is None:
            self.query_one(RichLog).write(
                "[bold red]A job is already running. Wait for it to finish.[/bold red]"
            )
            return

        self._stop_idle_log_tail()
        log = self.query_one(RichLog)
        log.clear()
        log.write(f"[bold cyan]$ python {' '.join(args)}[/bold cyan]")

        job = self.query_one(JobPanel)
        job.set_stage(stage or args[0])

        proc = await asyncio.create_subprocess_exec(
            sys.executable, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=ROOT,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        self._active_proc = proc

        async for raw_line in proc.stdout:
            line = raw_line.decode(errors="replace").rstrip()
            log.write(line)

            # Update job panel from ffmpeg stats lines
            parsed = _parse_ffmpeg_progress(line)
            if parsed:
                job.set_ffmpeg(parsed, self._target_secs)
            elif line.startswith("[ASSEMBLE] Duration:"):
                # Extract target_secs: "[ASSEMBLE] Duration: 2 hours (7200s)"
                try:
                    self._target_secs = int(line.split("(")[1].split("s)")[0])
                except Exception:
                    self._target_secs = None
                job.set_stage("Assembling video", line.split("Duration:")[-1].strip())
            elif "[2/5]" in line or "music" in line.lower():
                job.set_stage("Generating music", "")
            elif "[1/5]" in line or "visual" in line.lower():
                job.set_stage("Rendering visual", "")
            elif "[3/5]" in line or "SEO" in line:
                job.set_stage("Generating SEO", "")
            elif "[4/5]" in line or "Thumbnail" in line.lower():
                job.set_stage("Generating thumbnail", "")
            elif "[UPLOAD]" in line:
                job.set_stage("Uploading to YouTube", line)
            elif "LIVE" in line and "broadcast" in line.lower():
                job.set_stage("Starting live stream", "")

        await proc.wait()
        rc = proc.returncode
        if rc == 0:
            log.write(f"[bold green]✓ Done (exit 0)[/bold green]")
            self._do_poll_uploads()
            self._do_poll_state()
        else:
            log.write(f"[bold red]✗ Failed (exit {rc})[/bold red]")

        self._active_proc = None
        self._target_secs = None
        job.set_idle()
        self._start_idle_log_tail()

    # ── Actions (keybindings) ─────────────────────────────────────────────────

    def action_run_auto(self) -> None:
        asyncio.create_task(self._run_cmd("publish.py", "auto", stage="Auto: generate + upload"))

    def action_run_live(self) -> None:
        asyncio.create_task(self._run_cmd("publish.py", "live", stage="Starting live stream..."))

    def action_end_stream(self) -> None:
        asyncio.create_task(self._run_cmd("publish.py", "end", stage="Ending stream..."))

    async def action_toggle_auto_loop(self) -> None:
        st = await asyncio.to_thread(auto_service.status)
        log = self.query_one(RichLog)
        if not st["installed"]:
            log.write("[bold red]lofi-auto.service not installed — run deploy/setup.sh[/bold red]")
            return
        try:
            if st["active"]:
                await asyncio.to_thread(auto_service.stop)
                log.write("[dim]─ auto-loop stopped ─[/dim]")
            else:
                await asyncio.to_thread(auto_service.start)
                log.write("[dim]─ auto-loop started ─[/dim]")
        except RuntimeError as e:
            log.write(f"[bold red]{e}[/bold red]")
        self._do_poll_auto_loop()

    async def action_toggle_auto_boot(self) -> None:
        st = await asyncio.to_thread(auto_service.status)
        log = self.query_one(RichLog)
        if not st["installed"]:
            log.write("[bold red]lofi-auto.service not installed — run deploy/setup.sh[/bold red]")
            return
        try:
            await asyncio.to_thread(auto_service.set_enabled, not st["enabled"])
        except RuntimeError as e:
            log.write(f"[bold red]{e}[/bold red]")
        self._do_poll_auto_loop()

    def action_refresh(self) -> None:
        self._do_poll_state()
        self._do_poll_uploads()
        self._do_poll_auto_loop()
        log = self.query_one(RichLog)
        log.write("[dim]─ refreshed ─[/dim]")

    def action_quit(self) -> None:
        self.exit()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = LofiDashboard()
    app.run()
