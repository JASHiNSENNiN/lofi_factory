"""Unit tests for webui/data.py's render/sample delete operations."""
from __future__ import annotations

import os

import pytest

from webui import config, data
from webui.jobs import Job, manager


@pytest.fixture(autouse=True)
def _isolated_dirs(tmp_path, monkeypatch):
    for name in ("OUTPUT_DIR", "ASSETS_DIR", "MUSIC_DIR", "VISUALS_DIR"):
        d = tmp_path / name.lower()
        d.mkdir()
        monkeypatch.setattr(config, name, str(d))
    yield
    manager.current = None  # don't leak busy-state into other tests


def _make_render_files() -> dict:
    thumb = os.path.join(config.ASSETS_DIR, "thumb_cozy_rain_20260101_000000.jpg")
    alt = os.path.join(config.ASSETS_DIR, "thumb_cozy_rain_20260101_000000_alt.jpg")
    video = os.path.join(config.OUTPUT_DIR, "lofi_20260101_000000.mp4")
    grade_log = video + ".grade.log"
    tmp_dir = os.path.join(config.OUTPUT_DIR, "tmp_20260101_000000")
    os.makedirs(tmp_dir)
    for p in (thumb, alt, video, grade_log):
        open(p, "w").close()
    open(os.path.join(tmp_dir, "merged.mp4"), "w").close()
    return {
        "theme": "cozy rain", "dt": None, "thumb": thumb,
        "thumb_name": os.path.basename(thumb), "title": "Cozy Rain",
        "url": None, "video_id": None,
        "video_file": os.path.basename(video), "when": "Jan 1, 2026",
    }


def test_manifest_finds_all_owned_files():
    card = _make_render_files()
    manifest = data.render_delete_manifest(card)
    names = {m["name"] for m in manifest}
    assert names == {
        "thumb_cozy_rain_20260101_000000.jpg",
        "thumb_cozy_rain_20260101_000000_alt.jpg",
        "lofi_20260101_000000.mp4",
        "lofi_20260101_000000.mp4.grade.log",
        "merged.mp4",
        "tmp_20260101_000000",
    }


def test_manifest_skips_missing_files():
    card = {"theme": "x", "dt": None, "thumb": "", "thumb_name": "",
            "title": "x", "url": None, "video_id": None,
            "video_file": None, "when": ""}
    assert data.render_delete_manifest(card) == []


def test_delete_render_removes_everything():
    card = _make_render_files()
    removed = data.delete_render(card)
    assert len(removed) == 6
    assert not os.path.exists(card["thumb"])
    assert not os.path.exists(os.path.join(config.OUTPUT_DIR, card["video_file"]))
    assert not os.path.exists(os.path.join(config.OUTPUT_DIR, "tmp_20260101_000000"))


def test_delete_render_refuses_while_job_running():
    card = _make_render_files()
    manager.current = Job(id="t", name="render", cmd=[], status="running")
    with pytest.raises(RuntimeError, match="in progress"):
        data.delete_render(card)
    # Nothing should have been touched.
    assert os.path.exists(card["thumb"])
    assert os.path.exists(os.path.join(config.OUTPUT_DIR, card["video_file"]))


def test_delete_sample_rejects_path_outside_allowed_dirs(tmp_path):
    outside = tmp_path / "outside.wav"
    outside.write_text("x")
    assert data.delete_sample(str(outside)) is False
    assert outside.exists()


def test_delete_sample_removes_file_and_meta_sidecar():
    track = os.path.join(config.MUSIC_DIR, "track_1_00.wav")
    meta = track + ".meta.json"
    open(track, "w").close()
    open(meta, "w").close()
    assert data.delete_sample(track) is True
    assert not os.path.exists(track)
    assert not os.path.exists(meta)
