from unittest.mock import patch

import scripts.stream_live as stream_live


def test_dead_nowplaying_file_constants_are_gone():
    # Regression guard for the Phase 5 cleanup: these wrote to hardcoded
    # POSIX-only /tmp paths that nothing in the codebase ever read.
    assert not hasattr(stream_live, "NOWPLAYING_FILE")
    assert not hasattr(stream_live, "GENRE_FILE")
    assert not hasattr(stream_live, "_write_nowplaying")


def test_send_alert_goes_through_the_panels_alert_module():
    from webui import alerts
    with patch.object(alerts, "send_sync") as send:
        stream_live._send_alert("test message")
    send.assert_called_once()
    assert "test message" in send.call_args[0][1]


def test_send_alert_never_raises():
    from webui import alerts
    with patch.object(alerts, "send_sync", side_effect=Exception("network down")):
        stream_live._send_alert("test message")  # must not raise


def test_alert_threshold_constants_are_sane():
    assert stream_live._ALERT_AFTER_ATTEMPTS > 0
    assert stream_live._ALERT_REPEAT_EVERY > 0


def test_stop_request_ends_the_encoder(monkeypatch):
    """SIGTERM only sets _user_interrupted; the watch loop must act on it, or
    the encoder runs until systemd kills it and the broadcast never ends."""
    import subprocess
    import sys
    import time
    procs = []
    real_popen = subprocess.Popen

    def fake_popen(cmd, **kw):
        p = real_popen([sys.executable, "-c", "import time; time.sleep(60)"], **kw)
        procs.append(p)
        return p
    monkeypatch.setattr(stream_live.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(stream_live, "build_eq_filtergraph", lambda theme: "null")
    monkeypatch.setattr(stream_live, "_user_interrupted", True)
    t0 = time.monotonic()
    rc = stream_live.stream_once("v.mp4", "p.txt", "rtmp://x/y/z",
                                 visual_playlist_path="vis.txt")
    assert rc == 0
    assert time.monotonic() - t0 < 15
    assert procs and procs[0].poll() is not None
