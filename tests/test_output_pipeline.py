"""Regression tests for the assembly and live-stream fixes: enough unique
music, no silent fallback to unrelated files, strict durations, and the
stream keeping its own library."""
import os

import pytest

from scripts import assemble_video as av
from scripts import stream_live as sl


@pytest.fixture
def fake_durations(monkeypatch):
    durations = {}
    monkeypatch.setattr(av, "get_audio_duration", lambda p: durations.get(p, 0.0))
    return durations


def _touch(path):
    path.write_bytes(b"x")
    return str(path)


def test_tracks_for_duration_covers_the_video_without_repeats():
    for secs in (1800, 3600, 7200):
        assert av.tracks_for_duration(secs) * av.AVG_TRACK_SECS >= secs


def test_generated_tracks_are_used_and_nothing_else(tmp_path, monkeypatch, fake_durations):
    monkeypatch.setattr(av, "MUSIC_DIR", str(tmp_path))
    stray = _touch(tmp_path / "old_upload_track.wav")
    fake_durations[stray] = 300
    mine = [_touch(tmp_path / f"t{i}.wav") for i in range(3)]
    for p in mine:
        fake_durations[p] = 200
    playlist = av.pick_music_files(500, force_files=mine)
    assert {p for p, _ in playlist} <= set(mine)


def test_unusable_generated_tracks_raise_instead_of_falling_back(tmp_path, monkeypatch, fake_durations):
    monkeypatch.setattr(av, "MUSIC_DIR", str(tmp_path))
    fake_durations[_touch(tmp_path / "old.wav")] = 300
    broken = _touch(tmp_path / "broken.wav")          # duration 0 -> unusable
    with pytest.raises(FileNotFoundError):
        av.pick_music_files(600, force_files=[broken])


def test_repeats_warn_and_never_play_a_track_twice_in_a_row(tmp_path, fake_durations, capsys):
    tracks = [_touch(tmp_path / f"t{i}.wav") for i in range(3)]
    for p in tracks:
        fake_durations[p] = 100
    playlist = av.pick_music_files(1000, force_files=tracks)
    names = [p for p, _ in playlist]
    assert all(a != b for a, b in zip(names, names[1:]))
    assert "tracks will repeat" in capsys.readouterr().out


def test_unknown_duration_label_is_an_error():
    with pytest.raises(ValueError):
        av.assemble(duration_label="2 hourz")


def test_stream_library_is_separate_from_render_music():
    assert os.path.normpath(sl.MUSIC_DIR) == os.path.join(os.path.normpath(av.MUSIC_DIR), "stream")


def test_stream_prune_keeps_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "MUSIC_DIR", str(tmp_path))
    monkeypatch.setattr(sl, "_BG_GEN_MAX_TRACKS", 2)
    paths = []
    for i in range(4):
        p = tmp_path / f"track_{i}.wav"
        p.write_bytes(b"x")
        os.utime(p, (1000 + i, 1000 + i))
        paths.append(p)
    sl._prune_old_tracks()
    assert sorted(x.name for x in tmp_path.iterdir()) == ["track_2.wav", "track_3.wav"]


def test_stream_playlist_order_is_what_the_monitor_follows(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "MUSIC_DIR", str(tmp_path))
    for i in range(5):
        (tmp_path / f"track_{i}.wav").write_bytes(b"x")
    list_path, order = sl.build_music_list(str(tmp_path))
    with open(list_path) as f:
        listed = [line.split("'")[1] for line in f]
    assert listed == [os.path.abspath(p) for p in order]
