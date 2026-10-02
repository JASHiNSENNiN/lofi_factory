"""
Unit tests for webui/system_admin.py -- the data-gathering + side-effect
helpers behind the System page (resource monitor, GPU detection, disk-usage
breakdown, Tailscale/TLS status, config backup/restore, restart, and the
admin audit log).

Everything that touches the real machine (psutil, subprocess, systemctl) is
mocked -- these tests never call the real `systemctl --user restart`, read
the real /proc, or shell out to a real `tailscale`/`nvidia-smi`/`vainfo`/
`openssl` binary. File operations use tmp_path fixtures and never touch the
real token.json/.env/upload_log.json.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from webui import config, system_admin


# ── Audit log ────────────────────────────────────────────────────────────────
@pytest.fixture
def _isolated_audit_log(tmp_path, monkeypatch):
    log = tmp_path / "admin_audit.jsonl"
    monkeypatch.setattr(system_admin, "AUDIT_LOG", str(log))
    return log


def test_audit_log_appends_jsonl_entry(_isolated_audit_log):
    system_admin.audit_log("webui_restart", {"foo": "bar"})
    lines = _isolated_audit_log.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["action"] == "webui_restart"
    assert entry["detail"] == {"foo": "bar"}
    assert "ts" in entry


def test_audit_log_creates_parent_dir(tmp_path, monkeypatch):
    log = tmp_path / "nested" / "admin_audit.jsonl"
    monkeypatch.setattr(system_admin, "AUDIT_LOG", str(log))
    system_admin.audit_log("x", {})
    assert log.exists()


def test_audit_log_tail_empty_when_no_file(_isolated_audit_log):
    assert system_admin.audit_log_tail() == []


def test_audit_log_tail_returns_most_recent_first(_isolated_audit_log):
    system_admin.audit_log("first", {"n": 1})
    system_admin.audit_log("second", {"n": 2})
    system_admin.audit_log("third", {"n": 3})
    entries = system_admin.audit_log_tail()
    assert [e["action"] for e in entries] == ["third", "second", "first"]


def test_audit_log_tail_respects_limit(_isolated_audit_log):
    for i in range(10):
        system_admin.audit_log("a", {"n": i})
    entries = system_admin.audit_log_tail(n=3)
    assert len(entries) == 3
    assert entries[0]["detail"]["n"] == 9


def test_audit_log_tail_skips_corrupt_lines(_isolated_audit_log):
    _isolated_audit_log.write_text(
        '{"ts": "x", "action": "good", "detail": {}}\n'
        "not json at all\n"
        '{"ts": "y", "action": "also_good", "detail": {}}\n'
    )
    entries = system_admin.audit_log_tail()
    assert [e["action"] for e in entries] == ["also_good", "good"]


# ── Resource monitor ─────────────────────────────────────────────────────────
def test_resource_snapshot_assembles_expected_fields(monkeypatch):
    import psutil

    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 42.5)
    monkeypatch.setattr(
        psutil, "virtual_memory",
        lambda: SimpleNamespace(used=4 * 1_073_741_824, total=16 * 1_073_741_824, percent=25.0),
    )

    fake_usage = SimpleNamespace(used=100 * 1_073_741_824, total=500 * 1_073_741_824,
                                  free=400 * 1_073_741_824)
    monkeypatch.setattr(system_admin.shutil, "disk_usage", lambda path: fake_usage)

    snap = system_admin.resource_snapshot()
    assert snap["cpu_percent"] == 42.5
    assert snap["ram_used_gb"] == 4.0
    assert snap["ram_total_gb"] == 16.0
    assert snap["ram_percent"] == 25.0
    assert snap["disk_used_gb"] == 100.0
    assert snap["disk_total_gb"] == 500.0
    assert snap["disk_percent"] == 20.0


# ── GPU detection (graceful degradation) ─────────────────────────────────────
def test_gpu_snapshot_none_when_no_binaries_present(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(system_admin.subprocess, "run", fake_run)
    assert system_admin.gpu_snapshot() is None


def test_gpu_snapshot_uses_nvidia_smi_when_available(monkeypatch):
    def fake_run(cmd, **kwargs):
        if cmd[0] == "nvidia-smi":
            return subprocess.CompletedProcess(cmd, 0, stdout="37, 1024, 8192\n", stderr="")
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(system_admin.subprocess, "run", fake_run)
    snap = system_admin.gpu_snapshot()
    assert snap == {
        "backend": "nvidia-smi", "util_percent": 37.0,
        "mem_used_mb": 1024.0, "mem_total_mb": 8192.0,
    }


def test_gpu_snapshot_falls_back_to_vainfo(monkeypatch):
    def fake_run(cmd, **kwargs):
        if cmd[0] == "nvidia-smi":
            raise FileNotFoundError("nvidia-smi")
        if cmd[0] == "vainfo":
            return subprocess.CompletedProcess(
                cmd, 0, stdout="vainfo: VA-API version: 1.20\nvainfo: Driver version: Mesa Gallium driver\n",
                stderr="")
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(system_admin.subprocess, "run", fake_run)
    snap = system_admin.gpu_snapshot()
    assert snap["backend"] == "vaapi"
    assert snap["util_percent"] is None
    assert "driver" in snap["info"].lower() or snap["info"]


def test_gpu_snapshot_none_when_vainfo_returns_nonzero(monkeypatch):
    def fake_run(cmd, **kwargs):
        if cmd[0] == "nvidia-smi":
            raise FileNotFoundError("nvidia-smi")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="no VA display")

    monkeypatch.setattr(system_admin.subprocess, "run", fake_run)
    assert system_admin.gpu_snapshot() is None


# ── Disk-usage breakdown ──────────────────────────────────────────────────────
@pytest.fixture
def _isolated_content_dirs(tmp_path, monkeypatch):
    dirs = {}
    for name in ("OUTPUT_DIR", "MUSIC_DIR", "VISUALS_DIR", "ASSETS_DIR"):
        d = tmp_path / name.lower()
        d.mkdir()
        monkeypatch.setattr(config, name, str(d))
        dirs[name] = d
    return dirs


def test_disk_usage_breakdown_sums_bytes_per_directory(_isolated_content_dirs):
    (_isolated_content_dirs["OUTPUT_DIR"] / "a.mp4").write_bytes(b"x" * 1000)
    (_isolated_content_dirs["OUTPUT_DIR"] / "b.mp4").write_bytes(b"x" * 500)
    (_isolated_content_dirs["MUSIC_DIR"] / "t.wav").write_bytes(b"x" * 250)
    stream = _isolated_content_dirs["MUSIC_DIR"] / "stream"
    stream.mkdir()
    (stream / "s.wav").write_bytes(b"x" * 70)
    sub = _isolated_content_dirs["OUTPUT_DIR"] / "tmp_x"
    sub.mkdir()
    (sub / "c.mp4").write_bytes(b"x" * 100)

    breakdown = system_admin.disk_usage_breakdown()
    assert breakdown["Finished videos"] == 1600
    assert breakdown["Render tracks"] == 250
    assert breakdown["Live stream library"] == 70
    assert breakdown["Visual loops"] == 0
    assert breakdown["Thumbnails, logs, samples"] == 0


def test_disk_usage_breakdown_handles_missing_directory(tmp_path, monkeypatch):
    for name in ("OUTPUT_DIR", "MUSIC_DIR", "VISUALS_DIR", "ASSETS_DIR"):
        monkeypatch.setattr(config, name, str(tmp_path / f"missing_{name}"))
    assert set(system_admin.disk_usage_breakdown().values()) == {0}


# ── Tailscale / TLS cert status ───────────────────────────────────────────────
def test_tailscale_status_none_when_binary_missing(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("tailscale")

    monkeypatch.setattr(system_admin.subprocess, "run", fake_run)
    assert system_admin.tailscale_status() is None


def test_tailscale_status_parses_self_and_peers(monkeypatch):
    payload = {
        "Self": {"HostName": "lofi-box", "TailscaleIPs": ["100.64.0.1"], "Online": True},
        "Peer": {"a": {}, "b": {}, "c": {}},
    }

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(system_admin.subprocess, "run", fake_run)
    st = system_admin.tailscale_status()
    assert st == {
        "hostname": "lofi-box", "tailscale_ip": "100.64.0.1",
        "peer_count": 3, "online": True,
    }


def test_tailscale_status_none_on_bad_json(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="not json", stderr="")

    monkeypatch.setattr(system_admin.subprocess, "run", fake_run)
    assert system_admin.tailscale_status() is None


def test_cert_status_none_when_not_configured(monkeypatch):
    monkeypatch.setattr(config, "SSL_CERTFILE", "")
    assert system_admin.cert_status() is None


def test_cert_status_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SSL_CERTFILE", str(tmp_path / "nope.pem"))
    assert system_admin.cert_status() is None


def test_cert_status_none_when_openssl_missing(tmp_path, monkeypatch):
    cert = tmp_path / "cert.pem"
    cert.write_text("fake cert")
    monkeypatch.setattr(config, "SSL_CERTFILE", str(cert))

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("openssl")

    monkeypatch.setattr(system_admin.subprocess, "run", fake_run)
    assert system_admin.cert_status() is None


def test_cert_status_flags_expiring_soon(tmp_path, monkeypatch):
    cert = tmp_path / "cert.pem"
    cert.write_text("fake cert")
    monkeypatch.setattr(config, "SSL_CERTFILE", str(cert))

    expiry = datetime.now(timezone.utc) + timedelta(days=5)
    enddate = expiry.strftime("%b %d %H:%M:%S %Y GMT")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=f"notAfter={enddate}\n", stderr="")

    monkeypatch.setattr(system_admin.subprocess, "run", fake_run)
    st = system_admin.cert_status()
    assert st is not None
    assert st["expiring_soon"] is True
    assert 0 < st["days_left"] <= 6


def test_cert_status_not_expiring_when_far_out(tmp_path, monkeypatch):
    cert = tmp_path / "cert.pem"
    cert.write_text("fake cert")
    monkeypatch.setattr(config, "SSL_CERTFILE", str(cert))

    expiry = datetime.now(timezone.utc) + timedelta(days=90)
    enddate = expiry.strftime("%b %d %H:%M:%S %Y GMT")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=f"notAfter={enddate}\n", stderr="")

    monkeypatch.setattr(system_admin.subprocess, "run", fake_run)
    st = system_admin.cert_status()
    assert st["expiring_soon"] is False


# ── Restart ────────────────────────────────────────────────────────────────
def test_restart_webui_invokes_systemctl_and_logs(monkeypatch, _isolated_audit_log):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(system_admin.subprocess, "run", fake_run)
    system_admin.restart_webui()

    assert calls == [["systemctl", "--user", "restart", "lofi-webui.service"]]
    entries = system_admin.audit_log_tail()
    assert entries[0]["action"] == "webui_restart"


def test_restart_webui_raises_on_systemctl_failure(monkeypatch, _isolated_audit_log):
    def fake_run(cmd, **kwargs):
        if kwargs.get("check"):
            raise subprocess.CalledProcessError(1, cmd, output="", stderr="unit not found")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unit not found")

    monkeypatch.setattr(system_admin.subprocess, "run", fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        system_admin.restart_webui()
    # Audit entry is still written -- it's logged before the systemctl call fires.
    assert system_admin.audit_log_tail()[0]["action"] == "webui_restart"


# ── Config backup / restore / delete ─────────────────────────────────────────
@pytest.fixture
def _isolated_backup_env(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    backups = tmp_path / "backups"
    monkeypatch.setattr(config, "ROOT", str(root))
    monkeypatch.setattr(system_admin, "BACKUP_DIR", str(backups))
    monkeypatch.setattr(system_admin, "AUDIT_LOG", str(tmp_path / "admin_audit.jsonl"))
    return root, backups


def test_create_backup_copies_only_existing_files(_isolated_backup_env):
    root, backups = _isolated_backup_env
    (root / "token.json").write_text('{"t": 1}')
    (root / ".env").write_text("A=1\n")
    # upload_log.json deliberately absent.

    result = system_admin.create_backup()
    assert set(result["files"]) == {"token.json", ".env"}
    dest = backups / result["name"]
    assert (dest / "token.json").read_text() == '{"t": 1}'
    assert (dest / ".env").read_text() == "A=1\n"
    assert not (dest / "upload_log.json").exists()


def test_create_backup_empty_when_nothing_present(_isolated_backup_env):
    result = system_admin.create_backup()
    assert result["files"] == []


def test_list_backups_returns_newest_first(_isolated_backup_env):
    root, backups = _isolated_backup_env
    for name in ("20260101_000000", "20260201_000000"):
        d = backups / name
        d.mkdir(parents=True)
        (d / "token.json").write_text("x")
    names = [b["name"] for b in system_admin.list_backups()]
    assert names == ["20260201_000000", "20260101_000000"]


def test_list_backups_empty_when_no_backup_dir(_isolated_backup_env):
    assert system_admin.list_backups() == []


def test_restore_backup_copies_files_back_to_root(_isolated_backup_env):
    root, backups = _isolated_backup_env
    d = backups / "20260101_000000"
    d.mkdir(parents=True)
    (d / "token.json").write_text('{"restored": true}')

    restored = system_admin.restore_backup("20260101_000000")
    assert restored == ["token.json"]
    assert (root / "token.json").read_text() == '{"restored": true}'


def test_restore_backup_raises_for_unknown_name(_isolated_backup_env):
    with pytest.raises(ValueError):
        system_admin.restore_backup("does-not-exist")


def test_restore_backup_rejects_path_traversal(_isolated_backup_env):
    with pytest.raises(ValueError):
        system_admin.restore_backup("../../etc")


def test_delete_backup_removes_directory(_isolated_backup_env):
    root, backups = _isolated_backup_env
    d = backups / "20260101_000000"
    d.mkdir(parents=True)
    (d / "token.json").write_text("x")

    assert system_admin.delete_backup("20260101_000000") is True
    assert not d.exists()


def test_delete_backup_rejects_path_traversal(_isolated_backup_env):
    assert system_admin.delete_backup("../../etc") is False


def test_delete_backup_false_for_unknown_name(_isolated_backup_env):
    assert system_admin.delete_backup("nope") is False


def test_backup_actions_write_audit_entries(_isolated_backup_env):
    root, backups = _isolated_backup_env
    (root / "token.json").write_text("x")

    system_admin.create_backup()
    name = system_admin.list_backups()[0]["name"]
    system_admin.restore_backup(name)
    system_admin.delete_backup(name)

    actions = [e["action"] for e in system_admin.audit_log_tail()]
    assert actions == ["config_backup_delete", "config_restore", "config_backup"]
