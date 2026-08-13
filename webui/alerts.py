"""
alerts.py — multi-platform failure notifications, via apprise.

Kept separate from jobs.py/automation.py so those two files' existing
subprocess/queue-draining responsibilities don't get tangled up with
notification concerns; jobs.py just calls send_job_failure()/
send_queue_failure() at the two points a run can fail.

Reads LOFI_STREAM_ALERT_WEBHOOK from the environment: one or more
apprise-format notification URLs, comma-separated. This is the same env var
scripts/stream_live.py already reads (a single raw Slack/Discord incoming-
webhook URL, POSTed directly) — backward compatible on purpose, because
apprise natively recognizes that exact URL shape:
  https://hooks.slack.com/services/...
  https://discord.com/api/webhooks/...
So an existing single-webhook .env value keeps working unchanged in both
places, while a comma-separated list of any apprise:// URL (Telegram,
email, Pushover, ntfy, ...) now also works here for render/queue failures.
See https://github.com/caronc/apprise/wiki for the URL catalog.

All sending goes through asyncio.to_thread — apprise's Apprise.notify() is a
synchronous, blocking network call. Calling it directly from a NiceGUI
event-loop callback would freeze the whole site the same way a raw blocking
subprocess call does (see webui/automation.py's module docstring for the
real production incident that pattern is there to avoid).
"""
from __future__ import annotations

import asyncio
import logging
import os

import apprise

logger = logging.getLogger(__name__)

ALERT_ENV_KEY = "LOFI_STREAM_ALERT_WEBHOOK"

# How many trailing log lines to include in a job-failure notification body —
# enough to see the actual error, not so much it blows past most providers'
# message-length limits (e.g. Discord's ~2000 char cap).
_LOG_TAIL_LINES = 15


def _urls_from_env(raw: str | None = None) -> list[str]:
    """Split the env value on commas, trimming blanks. A single plain
    webhook URL (no commas) is still a 1-element list, so it round-trips
    exactly like before."""
    if raw is None:
        raw = os.environ.get(ALERT_ENV_KEY, "")
    return [u.strip() for u in raw.split(",") if u.strip()]


def configured(raw: str | None = None) -> bool:
    """True if at least one alert URL is configured."""
    return bool(_urls_from_env(raw))


def _build(urls: list[str]) -> apprise.Apprise | None:
    ap = apprise.Apprise()
    added_any = False
    for u in urls:
        if ap.add(u):
            added_any = True
        else:
            logger.warning("alerts: could not parse a configured notification URL "
                            "(starts with %r) — check %s in .env", u[:12], ALERT_ENV_KEY)
    return ap if added_any else None


def send_sync(title: str, body: str, *, urls: list[str] | None = None) -> bool:
    """Blocking send — call via asyncio.to_thread from async code (see
    send() below). Returns True if at least one configured URL accepted the
    notification, False if nothing is configured or every send failed.
    Never raises — alerting failures must never take down the caller."""
    urls = _urls_from_env() if urls is None else urls
    if not urls:
        return False
    ap = _build(urls)
    if ap is None:
        return False
    try:
        return bool(ap.notify(title=title, body=body))
    except Exception:
        logger.exception("alerts: apprise notify() raised")
        return False


async def send(title: str, body: str, *, urls: list[str] | None = None) -> bool:
    """Async wrapper — offloads the blocking apprise call to a thread so it
    never blocks the NiceGUI event loop."""
    return await asyncio.to_thread(send_sync, title, body, urls=urls)


async def send_test_alert() -> bool:
    """Fired from Settings' "Send test alert" button."""
    return await send(
        "lofi-factory: test alert",
        "This is a test notification from the Lofi Studio Settings page. "
        "If you can see this, alerting is configured correctly.",
    )


async def send_job_failure(job) -> bool:
    """Alert for a JobManager Job reaching status == 'failed'."""
    title = f"lofi-factory: job failed — {job.name}"
    tail = "\n".join(list(job.lines)[-_LOG_TAIL_LINES:])
    body = f"Job {job.id} ({job.name}) exited with code {job.returncode}."
    if tail:
        body += f"\n\nLast output:\n{tail}"
    return await send(title, body)


async def send_queue_failure(item) -> bool:
    """Alert for a JobQueue item that finished as 'failed' after draining.
    Note: since every queued item still runs through JobManager.run()/_pump()
    exactly like a manual click, a queued job failure also triggers
    send_job_failure() above — this fires in addition, with queue-specific
    context (slot, note), not instead of it."""
    title = f"lofi-factory: queued job failed — {item.name}"
    body = (f"Queued item {item.id} ({item.name}, slot={item.slot}) "
            f"exited with code {item.returncode}.")
    if item.note:
        body += f"\nNote: {item.note}"
    return await send(title, body)
