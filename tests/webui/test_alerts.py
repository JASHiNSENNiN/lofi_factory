"""Unit tests for webui/alerts.py (apprise-backed failure notifications).

Every test here mocks apprise.Apprise.add/notify — none of them are allowed
to make a real network call. _urls_from_env is exercised with explicit
`raw`/`urls` args throughout so the real process environment (and a real
.env, if one happens to be present) never leaks into a test.

Async entry points are driven with asyncio.run(), matching the convention
already used by tests/webui/test_helpers.py and test_job_queue.py (no
pytest-asyncio dependency needed).
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

from webui import alerts
from webui.jobs import Job, QueueItem

# _ALERT_LOG isolation for every test in this file comes from the global
# autouse fixture in tests/conftest.py, not a local one here.


# ── env parsing ──────────────────────────────────────────────────────────────
def test_urls_from_env_empty_when_unset():
    assert alerts._urls_from_env("") == []


def test_urls_from_env_single_raw_webhook_backward_compatible():
    # The pre-existing single-webhook shape (scripts/stream_live.py's usage)
    # must still round-trip as exactly one URL, unchanged.
    raw = "https://discord.com/api/webhooks/123/abc"
    assert alerts._urls_from_env(raw) == [raw]


def test_urls_from_env_splits_comma_separated_list():
    raw = ("https://discord.com/api/webhooks/123/abc, tgram://bottoken/chatid "
           ",mailto://user:pass@gmail.com")
    assert alerts._urls_from_env(raw) == [
        "https://discord.com/api/webhooks/123/abc",
        "tgram://bottoken/chatid",
        "mailto://user:pass@gmail.com",
    ]


def test_urls_from_env_ignores_blank_segments():
    assert alerts._urls_from_env("a://x,,  ,b://y") == ["a://x", "b://y"]


def test_configured_reflects_urls_present():
    assert alerts.configured("") is False
    assert alerts.configured("a://x") is True


# ── send_sync / send ─────────────────────────────────────────────────────────
def test_send_sync_returns_false_when_nothing_configured():
    assert alerts.send_sync("t", "b", urls=[]) is False


def test_send_sync_calls_apprise_notify_with_title_and_body():
    with patch("apprise.Apprise.add", return_value=True), \
         patch("apprise.Apprise.notify", return_value=True) as mock_notify:
        ok = alerts.send_sync("Test title", "Test body", urls=["json://example.com/hook"])
    assert ok is True
    mock_notify.assert_called_once_with(title="Test title", body="Test body")


def test_send_sync_returns_false_when_url_fails_to_parse():
    with patch("apprise.Apprise.add", return_value=False), \
         patch("apprise.Apprise.notify") as mock_notify:
        ok = alerts.send_sync("t", "b", urls=["not-a-real-url"])
    assert ok is False
    mock_notify.assert_not_called()


def test_send_sync_swallows_notify_exceptions():
    with patch("apprise.Apprise.add", return_value=True), \
         patch("apprise.Apprise.notify", side_effect=RuntimeError("boom")):
        ok = alerts.send_sync("t", "b", urls=["json://example.com/hook"])
    assert ok is False  # must not raise


def test_send_offloads_to_thread_and_returns_result():
    with patch("apprise.Apprise.add", return_value=True), \
         patch("apprise.Apprise.notify", return_value=True) as mock_notify:
        ok = asyncio.run(alerts.send("t", "b", urls=["json://example.com/hook"]))
    assert ok is True
    mock_notify.assert_called_once()


# ── job/queue failure alert builders ─────────────────────────────────────────
def test_send_job_failure_includes_name_and_returncode(monkeypatch):
    monkeypatch.setenv("LOFI_STREAM_ALERT_WEBHOOK", "json://example.com/hook")
    job = Job(id="render-1", name="render", cmd=["python", "run.py"], status="failed")
    job.returncode = 1
    job.lines.append("Traceback (most recent call last):")
    job.lines.append("RuntimeError: disk full")

    with patch("apprise.Apprise.add", return_value=True), \
         patch("apprise.Apprise.notify", return_value=True) as mock_notify:
        ok = asyncio.run(alerts.send_job_failure(job))

    assert ok is True
    _, kwargs = mock_notify.call_args
    assert "render" in kwargs["title"]
    assert "render-1" in kwargs["body"]
    assert "RuntimeError: disk full" in kwargs["body"]


def test_send_job_failure_noop_when_unconfigured(monkeypatch):
    monkeypatch.setenv("LOFI_STREAM_ALERT_WEBHOOK", "")
    job = Job(id="render-2", name="render", cmd=[], status="failed")
    with patch("apprise.Apprise.notify") as mock_notify:
        ok = asyncio.run(alerts.send_job_failure(job))
    assert ok is False
    mock_notify.assert_not_called()


def test_send_queue_failure_includes_slot_and_note(monkeypatch):
    monkeypatch.setenv("LOFI_STREAM_ALERT_WEBHOOK", "json://example.com/hook")
    item = QueueItem(id="q1-1", name="render", args=["run.py"], slot="stream",
                      note="weekend batch", status="failed", returncode=2)

    with patch("apprise.Apprise.add", return_value=True), \
         patch("apprise.Apprise.notify", return_value=True) as mock_notify:
        ok = asyncio.run(alerts.send_queue_failure(item))

    assert ok is True
    _, kwargs = mock_notify.call_args
    assert "q1-1" in kwargs["body"]
    assert "slot=stream" in kwargs["body"]
    assert "weekend batch" in kwargs["body"]


def test_send_test_alert_uses_env(monkeypatch):
    monkeypatch.setenv("LOFI_STREAM_ALERT_WEBHOOK", "json://example.com/hook")
    with patch("apprise.Apprise.add", return_value=True), \
         patch("apprise.Apprise.notify", return_value=True) as mock_notify:
        ok = asyncio.run(alerts.send_test_alert())
    assert ok is True
    mock_notify.assert_called_once()
