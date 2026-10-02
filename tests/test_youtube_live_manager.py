"""Live title updates must keep the broadcast description."""
import time

from scripts import youtube_live_manager as ylm


class _Exec:
    def __init__(self, result=None, sink=None, body=None):
        self.result, self.sink, self.body = result, sink, body

    def execute(self):
        if self.sink is not None:
            self.sink.append(self.body)
        return self.result


class _Broadcasts:
    def __init__(self):
        self.updates = []

    def list(self, part, id):
        return _Exec({"items": [{"snippet": {"title": "old", "description": "keep me",
                                             "scheduledStartTime": "2026-01-01T00:00:00Z"}}]})

    def update(self, part, body):
        return _Exec(sink=self.updates, body=body)


class _YT:
    def __init__(self):
        self.b = _Broadcasts()

    def liveBroadcasts(self):
        return self.b


def test_title_update_keeps_description(monkeypatch):
    monkeypatch.setattr(ylm, "_TITLE_COOLDOWN", 0)
    real_sleep = time.sleep
    monkeypatch.setattr(ylm.time, "sleep", lambda s: real_sleep(0.01))
    yt = _YT()
    updater = ylm.LiveTitleUpdater(yt, "bid", "2026-01-01T00:00:00Z")
    updater.set_track("Amber glow", "lofi_jazz")
    for _ in range(200):
        if yt.b.updates:
            break
        real_sleep(0.01)
    updater.stop()
    snippet = yt.b.updates[0]["snippet"]
    assert snippet["title"].startswith("lofi hip hop radio") and snippet["title"].endswith("Amber glow")
    assert snippet["description"] == "keep me"


def test_title_cooldown_fits_the_daily_quota():
    updates_per_day = 86400 / ylm._TITLE_COOLDOWN
    assert updates_per_day * 51 < 3000


def test_radio_title_keeps_the_searched_phrase_first():
    base = ylm.radio_title("lofi_house")
    assert base.startswith("lofi hip hop radio") and "house" not in base.lower()
    t = ylm.now_playing_title(base, "Until the Small Hours")
    assert t.startswith(base) and t.endswith("Until the Small Hours") and len(t) <= 100
    long = ylm.now_playing_title(base, "x" * 300)
    assert long.startswith(base) and len(long) <= 100


def test_stream_accepts_every_visual_theme():
    import subprocess
    import sys
    from scripts.visual_v2.themes import ALL_THEMES
    out = subprocess.run([sys.executable, "scripts/stream_live.py", "--help"],
                         capture_output=True, text=True, timeout=60).stdout
    assert all(t in out for t in ALL_THEMES)


def test_stream_uses_its_own_radio_background(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, "scripts")
    import stream_live as sl
    import scripts.visual_v2 as vv
    monkeypatch.setattr(sl, "STREAM_VISUALS_DIR", str(tmp_path / "stream"))
    calls = []

    def fake_generate(**kw):
        calls.append(kw)
        out = tmp_path / "stream" / f"bg_{kw['theme_name']}_20261002_000000.mp4"
        out.parent.mkdir(exist_ok=True)
        out.write_bytes(b"x")
        return str(out), kw["theme_name"]

    monkeypatch.setattr(vv, "generate_visual", fake_generate)
    first = sl.ensure_radio_visual("cozy_rain")
    again = sl.ensure_radio_visual("cozy_rain")
    assert first == again and len(calls) == 1                 # rendered once, then reused
    assert calls[0]["track_title"] == sl.RADIO_SESSION         # no video's session name
    assert calls[0]["genre"] == sl.RADIO_BADGE                 # no single genre on a mixed stream
