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
