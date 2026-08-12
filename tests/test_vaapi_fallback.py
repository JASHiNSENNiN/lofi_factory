"""
Regression tests for the VAAPI hardware-encode fallback in assemble_video.py.

The happy path (a real encode on a box with a working /dev/dri/renderD128 and
render-group access) was verified manually this session: apply_vhs_grade()
correctly detected hardware, produced a valid h264/aac output matching the
requested duration exactly, and cleaned up its log on success -- not
practical to re-run in CI (needs real GPU access). These tests instead lock
down the fail-closed behavior, which is what protects every deployment
target that *doesn't* have a usable GPU (the common case per DEPLOYMENT.md's
generic-VPS target) from ever being broken by this feature.
"""
from scripts import assemble_video as av


def test_vaapi_unavailable_when_device_missing(monkeypatch):
    av._vaapi_checked = None
    monkeypatch.setattr(av.os.path, "exists", lambda path: False)
    assert av._vaapi_available() is False


def test_vaapi_result_is_cached(monkeypatch):
    av._vaapi_checked = None
    calls = {"n": 0}

    def fake_exists(path):
        calls["n"] += 1
        return False

    monkeypatch.setattr(av.os.path, "exists", fake_exists)
    av._vaapi_available()
    av._vaapi_available()
    av._vaapi_available()
    assert calls["n"] == 1, "should only probe once per process, not every call"


def test_vaapi_fails_closed_on_probe_exception(monkeypatch):
    av._vaapi_checked = None
    monkeypatch.setattr(av.os.path, "exists", lambda path: True)

    def raise_error(*args, **kwargs):
        raise OSError("no such device")

    monkeypatch.setattr(av.subprocess, "run", raise_error)
    assert av._vaapi_available() is False


def test_vaapi_fails_closed_on_nonzero_probe_exit(monkeypatch):
    av._vaapi_checked = None
    monkeypatch.setattr(av.os.path, "exists", lambda path: True)

    class FakeResult:
        returncode = 1

    monkeypatch.setattr(av.subprocess, "run", lambda *a, **k: FakeResult())
    assert av._vaapi_available() is False
