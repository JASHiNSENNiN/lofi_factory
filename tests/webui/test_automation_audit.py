"""
Confirms webui/automation.py's start/stop/set_enabled/set_schedule wrappers
write an admin-audit-log entry on success and propagate the underlying
auto_service error (without logging) on failure. auto_service itself is
mocked -- these tests never touch the real systemd user session.
"""
from __future__ import annotations

import asyncio

import pytest

from webui import automation, system_admin


@pytest.fixture
def _isolated_audit_log(tmp_path, monkeypatch):
    log = tmp_path / "admin_audit.jsonl"
    monkeypatch.setattr(system_admin, "AUDIT_LOG", str(log))
    return log


def _actions() -> list[str]:
    return [e["action"] for e in system_admin.audit_log_tail()]


def test_start_logs_on_success(monkeypatch, _isolated_audit_log):
    monkeypatch.setattr(automation._svc, "start", lambda: None)
    asyncio.run(automation.start())
    assert _actions() == ["automation_start"]


def test_start_does_not_log_on_failure(monkeypatch, _isolated_audit_log):
    def boom():
        raise RuntimeError("systemctl start failed")

    monkeypatch.setattr(automation._svc, "start", boom)
    with pytest.raises(RuntimeError):
        asyncio.run(automation.start())
    assert _actions() == []


def test_stop_logs_on_success(monkeypatch, _isolated_audit_log):
    monkeypatch.setattr(automation._svc, "stop", lambda: None)
    asyncio.run(automation.stop())
    assert _actions() == ["automation_stop"]


def test_set_enabled_logs_with_detail(monkeypatch, _isolated_audit_log):
    monkeypatch.setattr(automation._svc, "set_enabled", lambda enabled: None)
    asyncio.run(automation.set_enabled(True))
    entries = system_admin.audit_log_tail()
    assert entries[0] == {
        "ts": entries[0]["ts"], "action": "automation_set_enabled",
        "detail": {"enabled": True},
    }


def test_set_schedule_logs_with_detail(monkeypatch, _isolated_audit_log):
    monkeypatch.setattr(automation._svc, "set_schedule",
                         lambda start_hour, every_hours: None)
    asyncio.run(automation.set_schedule(6, 12))
    entries = system_admin.audit_log_tail()
    assert entries[0]["action"] == "automation_set_schedule"
    assert entries[0]["detail"] == {"start_hour": 6, "every_hours": 12}


def test_set_schedule_does_not_log_on_validation_error(monkeypatch, _isolated_audit_log):
    def boom(start_hour, every_hours):
        raise ValueError("bad schedule")

    monkeypatch.setattr(automation._svc, "set_schedule", boom)
    with pytest.raises(ValueError):
        asyncio.run(automation.set_schedule(99, 5))
    assert _actions() == []
