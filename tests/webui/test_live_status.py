"""The Live page sees both live systems and only ever signals the right process."""
import json
import os
import subprocess
import sys

from webui import config, data


def _write(tmp_path, name, obj):
    (tmp_path / name).write_text(json.dumps(obj))


def test_offline_when_no_state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", str(tmp_path))
    assert data.live_status() is None


def test_single_video_stream(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", str(tmp_path))
    _write(tmp_path, "live_state.json", {"ffmpeg_pid": os.getpid(), "title": "t"})
    st = data.live_status()
    assert st["mode"] == "single" and st["alive"]


def test_247_stream_and_stale_detection(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", str(tmp_path))
    _write(tmp_path, "stream_state.json", {"pid": 2 ** 22 + 11})
    st = data.live_status()
    assert st["mode"] == "24/7" and not st["alive"]
    data.clear_247_state()
    assert data.live_status() is None


def test_stop_247_only_signals_a_stream_process(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", str(tmp_path))
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        _write(tmp_path, "stream_state.json", {"pid": other.pid})
        assert data.stop_247_stream() is False          # not stream_live / --stream
        assert other.poll() is None
    finally:
        other.kill()
        other.wait()
    fake = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "--stream"])
    try:
        _write(tmp_path, "stream_state.json", {"pid": fake.pid})
        assert data.stop_247_stream() is True
        assert fake.wait(timeout=10) != 0
    finally:
        if fake.poll() is None:
            fake.kill()
