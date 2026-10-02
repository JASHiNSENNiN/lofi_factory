"""State files must survive crashes and corruption; cleanup must run after
uploads without touching the stream library or thumbnails still needed for
A/B swaps; manual uploads must pair the right SEO/thumbnail with a video."""
import json
import os
import time

import pytest

import publish
from scripts import cleanup, fileutil


def test_append_json_list_preserves_a_corrupt_file(tmp_path):
    path = tmp_path / "upload_log.json"
    path.write_text('[{"video_id": "a"}, {"video_id": ')    # truncated mid-write
    fileutil.append_json_list(str(path), {"video_id": "b"})
    assert json.loads(path.read_text()) == [{"video_id": "b"}]
    saved = tmp_path / "upload_log.json.corrupt-1"
    assert saved.read_text().startswith('[{"video_id": "a"}')


def test_atomic_write_sets_mode_before_content(tmp_path):
    path = tmp_path / "secret.json"
    fileutil.atomic_write_json(str(path), {"k": 1}, mode=0o600)
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    assert json.loads(path.read_text()) == {"k": 1}


def _age(path, days):
    t = time.time() - days * 86400
    os.utime(path, (t, t))


def test_cleanup_keeps_stream_library_and_recent_thumbnails(tmp_path):
    for d in ("music/stream", "assets", "visuals", "output"):
        (tmp_path / d).mkdir(parents=True)
    stream_track = tmp_path / "music/stream/track_1.wav"
    stream_track.write_bytes(b"x")
    video = tmp_path / "output/lofi_1.mp4"
    video.write_bytes(b"x" * 100)
    recent_alt = tmp_path / "assets/thumb_a_alt.jpg"
    recent_alt.write_bytes(b"x")
    _age(recent_alt, 20)
    old_thumb = tmp_path / "assets/thumb_b.jpg"
    old_thumb.write_bytes(b"x")
    _age(old_thumb, 60)

    cleanup.cleanup_after_upload(str(tmp_path), str(video))

    assert not video.exists()
    assert stream_track.exists()
    assert recent_alt.exists()          # still inside the 7-30 day swap window
    assert not old_thumb.exists()


def test_paired_asset_skips_alternates_and_later_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(publish, "ROOT", str(tmp_path))
    (tmp_path / "assets").mkdir()
    (tmp_path / "output").mkdir()
    primary = tmp_path / "assets/thumb_x_1.jpg"
    alt = tmp_path / "assets/thumb_x_1_alt.jpg"
    video = tmp_path / "output/lofi_1.mp4"
    later = tmp_path / "assets/thumb_y_2.jpg"
    for i, p in enumerate((primary, alt, video, later)):
        p.write_bytes(b"x")
        os.utime(p, (1000 + i * 600, 1000 + i * 600))
    assert publish.paired_asset("thumb_*.jpg", str(video)) == str(primary)


def test_find_latest_valid_video_never_deletes_and_skips_in_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(publish, "ROOT", str(tmp_path))
    (tmp_path / "output").mkdir()
    rendering = tmp_path / "output/lofi_new.mp4"
    rendering.write_bytes(b"partial")
    done = tmp_path / "output/lofi_old.mp4"
    done.write_bytes(b"done")
    _age(done, 1)
    monkeypatch.setattr(publish, "get_video_duration",
                        lambda p: 3600.0 if p.endswith("old.mp4") else 0.0)
    assert publish.find_latest_valid_video() == str(done)
    assert rendering.exists()
