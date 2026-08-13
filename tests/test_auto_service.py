"""Unit tests for auto_service.resource_status() (systemd memory/exit-status
introspection for the Automation view's new resource panel).

subprocess.run is mocked throughout -- no real `systemctl` call is ever made.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import auto_service


def _fake_run(stdout: str):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=0)


def test_resource_status_parses_memory_and_exit_fields():
    show_output = (
        "MemoryHigh=524288000\n"
        "MemoryMax=1073741824\n"
        "MemoryCurrent=104857600\n"
        "ExecMainStatus=0\n"
        "ExecMainCode=exited\n"
    )
    with patch("subprocess.run", return_value=_fake_run(show_output)) as mock_run:
        status = auto_service.resource_status()

    assert status == {
        "memory_high": 524288000,
        "memory_max": 1073741824,
        "memory_current": 104857600,
        "exec_main_status": "0",
        "exec_main_code": "exited",
    }
    args = mock_run.call_args[0][0]
    assert args[:3] == ["systemctl", "--user", "show"]
    assert "MemoryHigh" in args[4] and "ExecMainCode" in args[4]
    assert args[-1] == auto_service.SERVICE


def test_resource_status_treats_infinity_and_not_set_as_none():
    show_output = (
        "MemoryHigh=infinity\n"
        "MemoryMax=[not set]\n"
        "MemoryCurrent=n/a\n"
        "ExecMainStatus=\n"
        "ExecMainCode=\n"
    )
    with patch("subprocess.run", return_value=_fake_run(show_output)):
        status = auto_service.resource_status()

    assert status["memory_high"] is None
    assert status["memory_max"] is None
    assert status["memory_current"] is None
    assert status["exec_main_code"] is None


def test_resource_status_reports_killed_run():
    show_output = (
        "MemoryHigh=infinity\n"
        "MemoryMax=infinity\n"
        "MemoryCurrent=209715200\n"
        "ExecMainStatus=9\n"
        "ExecMainCode=killed\n"
    )
    with patch("subprocess.run", return_value=_fake_run(show_output)):
        status = auto_service.resource_status()

    assert status["exec_main_code"] == "killed"
    assert status["exec_main_status"] == "9"
    assert status["memory_current"] == 209715200


def test_resource_status_handles_unparseable_memory_value():
    # Defensive: an unexpected non-numeric, non-sentinel value shouldn't raise.
    show_output = "MemoryHigh=garbage\nMemoryMax=infinity\nMemoryCurrent=1\n"
    with patch("subprocess.run", return_value=_fake_run(show_output)):
        status = auto_service.resource_status()
    assert status["memory_high"] is None
