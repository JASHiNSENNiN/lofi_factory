"""
Unit tests for scripts/generate_shorts.py.

No real ffmpeg/soundfile/YouTube calls: highlight-window selection is tested
against synthetic RMS curves (pure function, no file I/O), and the ffmpeg /
upload boundaries are monkeypatched out for the pipeline-orchestration tests
-- same pattern as tests/test_vaapi_fallback.py's subprocess.run mocking and
tests/test_stream_live.py's mocked network calls.
"""
from __future__ import annotations

import os

import pytest

from scripts import generate_shorts as gs


# ─────────────────────────────────────────────────────────────────────────────
# pick_highlight_window — pure logic over synthetic loudness data
# ─────────────────────────────────────────────────────────────────────────────
def test_short_track_returns_whole_track():
    # Track shorter than the requested window -- nothing to compare, just
    # use the whole thing.
    rms = [0.1, 0.2, 0.3]
    times = [0.0, 1.0, 2.0]
    start, end = gs.pick_highlight_window(rms, times, total_secs=3.0, window_secs=58.0)
    assert start == 0.0
    assert end == 3.0


def test_empty_curve_falls_back_to_start():
    start, end = gs.pick_highlight_window([], [], total_secs=120.0, window_secs=58.0)
    assert start == 0.0
    assert end == 58.0


def test_picks_the_loudest_window():
    # 120s track, 1s hops. Energy spikes for a 10s span in the middle
    # (40..50s) -- that should win over the quiet start/end.
    times = list(range(120))
    rms = [0.05] * 120
    for t in range(40, 50):
        rms[t] = 0.9
    start, end = gs.pick_highlight_window(rms, times, total_secs=120.0, window_secs=10.0)
    assert 38 <= start <= 42  # window fully covering the loud span wins
    assert end == start + 10.0


def test_window_never_exceeds_total_duration():
    times = list(range(70))
    rms = [0.1] * 70
    rms[65] = 0.99  # loudest point is near the very end
    start, end = gs.pick_highlight_window(rms, times, total_secs=70.0, window_secs=58.0)
    assert end <= 70.0
    assert end - start == 58.0


def test_uniform_energy_picks_earliest_window_deterministically():
    times = list(range(100))
    rms = [0.3] * 100
    start, end = gs.pick_highlight_window(rms, times, total_secs=100.0, window_secs=58.0)
    assert start == 0.0
    assert end == 58.0


def test_zero_duration_track_returns_zero_window():
    start, end = gs.pick_highlight_window([], [], total_secs=0.0, window_secs=58.0)
    assert start == 0.0
    assert end == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# build_shorts_metadata — pure
# ─────────────────────────────────────────────────────────────────────────────
def test_metadata_appends_shorts_tag_to_title():
    seo = {"title": "lofi beats for late-night coding sessions", "description": "chill vibes"}
    meta = gs.build_shorts_metadata(seo)
    assert meta["title"].endswith("#Shorts")
    assert len(meta["title"]) <= 100


def test_metadata_title_override_wins():
    seo = {"title": "original title"}
    meta = gs.build_shorts_metadata(seo, title_override="custom short title")
    assert meta["title"].startswith("custom short title")


def test_metadata_truncates_long_title_to_100_chars():
    seo = {"title": "x" * 200}
    meta = gs.build_shorts_metadata(seo)
    assert len(meta["title"]) <= 100
    assert meta["title"].endswith("#Shorts")


def test_metadata_ensures_shorts_hashtag_in_description():
    seo = {"title": "t", "description": "no hashtag here"}
    meta = gs.build_shorts_metadata(seo)
    assert "#shorts" in meta["description"].lower()


def test_metadata_preserves_existing_shorts_hashtag():
    seo = {"title": "t", "description": "already has #Shorts in it"}
    meta = gs.build_shorts_metadata(seo)
    assert meta["description"].count("#Shorts") + meta["description"].lower().count("#shorts") >= 1


def test_metadata_ensures_shorts_tag_present():
    seo = {"title": "t", "tags": ["lofi", "chill"]}
    meta = gs.build_shorts_metadata(seo)
    assert any(t.lower() == "shorts" for t in meta["tags"])
    assert "lofi" in meta["tags"]


def test_metadata_defaults_when_seo_empty():
    meta = gs.build_shorts_metadata({})
    assert meta["title"].endswith("#Shorts")
    assert meta["privacy"] == "public"
    assert meta["made_for_kids"] is False


def test_metadata_privacy_carried_from_seo():
    meta = gs.build_shorts_metadata({"title": "t", "privacy": "unlisted"})
    assert meta["privacy"] == "unlisted"


# ─────────────────────────────────────────────────────────────────────────────
# crosspost — opt-in stub, must never fake success
# ─────────────────────────────────────────────────────────────────────────────
def test_crosspost_noop_by_default(monkeypatch):
    monkeypatch.setattr(gs, "CROSSPOST_ENABLED", False)
    result = gs.crosspost("output/shorts/x_short.mp4", platforms=["tiktok"])
    assert result["attempted"] is False
    assert "CROSSPOST_ENABLED" in result["reason"]


def test_crosspost_raises_not_implemented_when_enabled(monkeypatch):
    monkeypatch.setattr(gs, "CROSSPOST_ENABLED", True)
    with pytest.raises(NotImplementedError):
        gs.crosspost("output/shorts/x_short.mp4", platforms=["tiktok", "instagram"])


# ─────────────────────────────────────────────────────────────────────────────
# ffmpeg boundary — mocked subprocess, no real ffmpeg invocation required
# ─────────────────────────────────────────────────────────────────────────────
def test_build_vertical_clip_invokes_ffmpeg_with_crop_filter(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(gs.subprocess, "run", fake_run)
    out_path = str(tmp_path / "shorts" / "clip.mp4")
    gs.build_vertical_clip("input.mp4", out_path, 10.0, 20.0)

    assert len(calls) == 1
    cmd = calls[0]
    assert "ffmpeg" in cmd
    assert "1080:1920" in " ".join(cmd) or "1080" in cmd and "1920" in cmd
    assert os.path.isdir(os.path.dirname(out_path))  # parent dir created


def test_get_video_duration_parses_ffprobe_output(monkeypatch):
    class R:
        stdout = "123.45\n"

    monkeypatch.setattr(gs.subprocess, "run", lambda *a, **k: R())
    assert gs.get_video_duration("x.mp4") == 123.45


def test_get_video_duration_returns_zero_on_bad_output(monkeypatch):
    class R:
        stdout = "not a number"

    monkeypatch.setattr(gs.subprocess, "run", lambda *a, **k: R())
    assert gs.get_video_duration("x.mp4") == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# run_pipeline orchestration — everything I/O-ish mocked out
# ─────────────────────────────────────────────────────────────────────────────
def test_run_pipeline_raises_when_no_video_found(tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "OUTPUT_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        gs.run_pipeline(video_path=None, upload=False)


def test_run_pipeline_save_only_skips_upload(monkeypatch, tmp_path):
    video = tmp_path / "lofi_test.mp4"
    video.write_text("fake video bytes")

    monkeypatch.setattr(gs, "extract_audio_track", lambda video_path, out_wav: None)
    monkeypatch.setattr(gs, "select_highlight_window", lambda *a, **k: (5.0, 63.0))
    monkeypatch.setattr(gs, "get_video_duration", lambda path: 600.0)
    monkeypatch.setattr(gs, "build_vertical_clip", lambda *a, **k: None)

    result = gs.run_pipeline(video_path=str(video), upload=False,
                              out_path=str(tmp_path / "out_short.mp4"))

    assert result["uploaded"] is False
    assert result["video_id"] is None
    assert result["window"] == {"start_sec": 5.0, "end_sec": 63.0}
    assert result["clip_path"] == str(tmp_path / "out_short.mp4")


def test_run_pipeline_uploads_with_provided_youtube_client(monkeypatch, tmp_path):
    video = tmp_path / "lofi_test.mp4"
    video.write_text("fake video bytes")

    monkeypatch.setattr(gs, "extract_audio_track", lambda video_path, out_wav: None)
    monkeypatch.setattr(gs, "select_highlight_window", lambda *a, **k: (0.0, 58.0))
    monkeypatch.setattr(gs, "get_video_duration", lambda path: 600.0)
    monkeypatch.setattr(gs, "build_vertical_clip", lambda *a, **k: None)

    upload_calls = []

    def fake_upload_video(youtube, video_path, seo, thumb_path, publish_at=None):
        upload_calls.append((video_path, seo["title"]))
        return "abc123", "https://youtube.com/watch?v=abc123"

    monkeypatch.setitem(
        __import__("sys").modules, "scripts.upload_youtube",
        type("M", (), {"upload_video": staticmethod(fake_upload_video),
                        "get_authenticated_service": staticmethod(lambda: object())})(),
    )

    result = gs.run_pipeline(video_path=str(video), upload=True, youtube=object(),
                              out_path=str(tmp_path / "out_short.mp4"))

    assert result["uploaded"] is True
    assert result["video_id"] == "abc123"
    assert result["url"] == "https://youtube.com/watch?v=abc123"
    assert len(upload_calls) == 1
    assert upload_calls[0][1].endswith("#Shorts")


def test_run_pipeline_attempts_crosspost_when_platforms_given(monkeypatch, tmp_path):
    video = tmp_path / "lofi_test.mp4"
    video.write_text("fake video bytes")

    monkeypatch.setattr(gs, "extract_audio_track", lambda video_path, out_wav: None)
    monkeypatch.setattr(gs, "select_highlight_window", lambda *a, **k: (0.0, 58.0))
    monkeypatch.setattr(gs, "get_video_duration", lambda path: 600.0)
    monkeypatch.setattr(gs, "build_vertical_clip", lambda *a, **k: None)

    def fake_upload_video(youtube, video_path, seo, thumb_path, publish_at=None):
        return "abc123", "https://youtube.com/watch?v=abc123"

    monkeypatch.setitem(
        __import__("sys").modules, "scripts.upload_youtube",
        type("M", (), {"upload_video": staticmethod(fake_upload_video),
                        "get_authenticated_service": staticmethod(lambda: object())})(),
    )

    crosspost_calls = []
    monkeypatch.setattr(gs, "crosspost", lambda path, platforms=None: crosspost_calls.append(platforms) or {"attempted": False})

    result = gs.run_pipeline(video_path=str(video), upload=True, youtube=object(),
                              out_path=str(tmp_path / "out_short.mp4"),
                              crosspost_platforms=["tiktok"])

    assert crosspost_calls == [["tiktok"]]
    assert result["crosspost"] == {"attempted": False}


def test_short_never_claims_the_long_videos_length_or_carries_its_ref():
    seo = {"title": "rain on the window 🌧️ [lofi hip hop · 1 hour]", "duration": "1 hour",
           "genre_label": "lofi hip hop", "thumb_text": "rain on the window",
           "description": "Long text\n\nTRACKLIST\n0:00 A\n12:00 B\n\nlofi:20261002_101010_ab12"}
    meta = gs.build_shorts_metadata(seo)
    assert meta["title"] == "rain on the window 🌧️ [lofi hip hop] #Shorts"
    assert "lofi:" not in meta["description"] and "TRACKLIST" not in meta["description"]
    assert "a 1 hour lofi hip hop mix" in meta["description"]
    radio = gs.build_shorts_metadata({"title": "jazz hop 🌙 calm beats to study & relax to · 2 hours"})
    assert "hours" not in radio["title"]
