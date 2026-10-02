"""
notify_auto_failure.py — pushes an alert when lofi-auto.service fails.

Triggered by deploy/lofi-auto-notify-failure.service, which lofi-auto.service
points to via OnFailure= (see deploy/lofi-auto.service). Confirmed 2026-08-17:
a run that got killed by TimeoutStartSec produced zero notification anywhere
-- webui/alerts.py already has a working webhook path (send_job_failure(),
used for interactive Studio renders), but nothing wired it to the systemd-
triggered unattended run, so a failure there was silent until someone opened
the web UI and happened to notice the progress bar was gone.

Deliberately a standalone script, not something importing webui/automation.py
at runtime: this needs to work even if the failure is early/severe enough
that the venv or app modules are in a bad state, and it must load .env itself
since only webui.py's own startup does that automatically.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

from webui import alerts  # noqa: E402 -- needs .env loaded first


def _last_result() -> str:
    try:
        out = subprocess.run(
            ["systemctl", "--user", "show", "lofi-auto.service",
             "-p", "Result", "-p", "ExecMainStatus", "-p", "ExecMainCode"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        return " ".join(line.strip() for line in out.splitlines())
    except Exception as e:
        return f"(couldn't read systemd status: {e})"


def main() -> None:
    if not alerts.configured():
        # No alert destination: at least make the failure loud in the journal.
        print("lofi-auto.service FAILED and no alert URL is configured "
              "(set LOFI_STREAM_ALERT_WEBHOOK). " + _last_result(), file=sys.stderr)
        return
    title = "lofi-factory: unattended auto-render failed"
    body = (
        f"lofi-auto.service failed on {os.uname().nodename}.\n"
        f"{_last_result()}\n\n"
        "Check the web UI's Logs page for the automation journal, or "
        "Automation for current status/last-exit detail."
    )
    alerts.send_sync(title, body)


if __name__ == "__main__":
    main()
