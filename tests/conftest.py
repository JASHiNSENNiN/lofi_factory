import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture(autouse=True)
def _isolate_alert_log(tmp_path, monkeypatch):
    """Global, not just tests/webui/test_alerts.py: alerts.send_sync() now
    persists every attempt to assets/alerts_log.jsonl (see webui/alerts.py),
    and it's called from real code paths other tests exercise too (e.g.
    JobManager._pump() on a failing job, via test_job_queue.py) -- confirmed
    2026-08-17 those were leaking fake "job failed" entries into the real
    alert history with no isolation fixture at all. Every test in the whole
    suite gets a scratch path instead, unconditionally.
    """
    try:
        from webui import alerts
    except ImportError:
        return
    monkeypatch.setattr(alerts, "_ALERT_LOG", str(tmp_path / "alerts_log.jsonl"))


@pytest.fixture(autouse=True)
def _isolate_composer_history(tmp_path, monkeypatch):
    """The composer steers away from recently used progressions and melodies
    using music/.params_history.json and .melody_history.json. Tests that
    render tracks used to rewrite the real files, so a test run changed
    what the next real video would pick."""
    try:
        from scripts import composer
    except Exception:
        return
    monkeypatch.setattr(composer, "_PARAMS_HISTORY_FILE", str(tmp_path / "params_history.json"))
    monkeypatch.setattr(composer, "_MELODY_HISTORY_FILE", str(tmp_path / "melody_history.json"))
