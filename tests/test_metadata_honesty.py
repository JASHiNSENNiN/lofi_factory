"""Video metadata must describe the video: real chapters, relevant tags,
grammatical copy, no claims the channel can't back up."""
import contextlib
import io
import random
import re

import pytest

from scripts import generate_seo as g
from scripts import assemble_video as av


def _concepts(n=200):
    for i in range(n):
        random.seed(i)
        with contextlib.redirect_stdout(io.StringIO()):
            c = g.pick_concept(None)
        yield c, g.build_description(c, "1 hour")


def test_descriptions_have_no_mad_lib_grammar():
    bad = re.compile(r"\b(a|an|the) (any|your|wherever|a|an|the)\b|\.\.|\A\s", re.I)
    for _c, d in _concepts():
        assert not bad.search(d), d


def test_descriptions_carry_no_invented_chapters_or_claims():
    for _c, d in _concepts(60):
        assert "CHAPTERS" not in d
        assert not re.search(r"^\d+:\d\d", d, re.M)       # no timestamps before assembly
        assert "weekly" not in d and "No algorithm" not in d


def test_hashtags_are_unique_and_few():
    for _c, d in _concepts(60):
        tags = re.findall(r"#\w+", d)
        assert len(tags) == len(set(tags)) <= 4


def test_tags_only_name_the_videos_own_genre():
    other_genres = {"lofi phonk", "dark lofi", "lofi jazz", "chillhop", "vaporwave"}
    concept = {"genre_label": "lo-fi hip hop", "tags_extra": ["3am lofi"], "pillar": "temporal"}
    tags = g.build_tags(concept, "1 hour")
    assert len(tags) <= g._MAX_TAGS
    assert not other_genres & {t.lower() for t in tags}
    assert "anxiety" not in " ".join(tags)


def test_season_labels_only_in_their_season():
    assert not g._in_season("summer night", month=10)
    assert g._in_season("autumn dusk", month=10)
    assert g._in_season("3am", month=1)


def test_tracklist_uses_real_start_times():
    playlist = [("/x/a.wav", 200.0), ("/x/b.wav", 185.5), ("/x/c.wav", 210.0)]
    tracks = av.build_tracklist(playlist, 500.0)
    assert [t["start"] for t in tracks] == [0.0, 200.0, 385.5]
    desc = g.with_tracklist("intro\n\n─────\nfooter", tracks)
    assert "0:00 a\n3:20 b\n6:25 c" in desc
    assert desc.index("TRACKLIST") < desc.index("─────")


def test_tracklist_skips_a_track_that_would_start_in_the_fade():
    tracks = av.build_tracklist([("/x/a.wav", 595.0), ("/x/b.wav", 200.0)], 600.0)
    assert len(tracks) == 1


def test_stream_key_never_reaches_logs():
    from scripts.stream_live import redact_stream_key
    from webui.jobs import Job
    line = "rtmp://a.rtmp.youtube.com/live2/abcd-efgh-ijkl-mnop: Broken pipe"
    assert "abcd" not in redact_stream_key(line)
    job = Job(id="x", name="live", cmd=["python"])
    job._emit_line(line)
    assert "abcd" not in job.lines[-1]


def test_schedule_times_are_converted_to_utc():
    import publish
    assert publish._to_rfc3339_utc("2026-05-16T20:00:00+02:00") == "2026-05-16T18:00:00.000Z"
    assert publish._to_rfc3339_utc("2026-05-16T20:00:00") == "2026-05-16T20:00:00.000Z"
    assert publish._to_rfc3339_utc("tomorrow") is None


@pytest.mark.parametrize("code,recorded", [(0, None), (1, False)])
def test_auto_upload_exit_is_recorded(monkeypatch, tmp_path, code, recorded):
    """cmd_upload exits on refusals; auto mode must still record the result
    (and treat 'already on YouTube' as done, not failed)."""
    import argparse
    import publish
    out = tmp_path / "output"
    out.mkdir()
    monkeypatch.setattr(publish, "ROOT", str(tmp_path))
    results = []
    monkeypatch.setattr(publish, "_record_auto_result", lambda success: results.append(success))

    def fake_run(cmd, **kw):
        (out / "lofi_new.mp4").write_bytes(b"x")
        return argparse.Namespace(returncode=0)
    monkeypatch.setattr(publish.subprocess, "run", fake_run)

    def fake_upload(args):
        raise SystemExit(code)
    monkeypatch.setattr(publish, "cmd_upload", fake_upload)
    import scripts.cleanup
    monkeypatch.setattr(scripts.cleanup, "cleanup_after_upload", lambda *a: 0)

    args = argparse.Namespace(duration="1 hour", loop=True)
    publish._run_auto_once(args)
    if recorded is None:
        assert results == [True]
    else:
        assert results == [False]


def test_jobs_get_their_own_scope_only_under_systemd(monkeypatch):
    from webui import jobs
    monkeypatch.setattr(jobs, "_scope_ok", None)
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    assert jobs._scope_prefix() == []
    monkeypatch.setattr(jobs, "_scope_ok", True)
    prefix = jobs._scope_prefix()
    assert prefix[:3] == ["systemd-run", "--user", "--scope"]
    assert f"MemoryMax={jobs.JOB_MEMORY_MAX}" in prefix and prefix[-1] == "--"


def test_description_opens_with_what_people_search():
    line = g._search_line("chillhop", "1 hour", "reading")
    assert line == "1 hour of chillhop lofi beats for reading, studying and working."
    assert g._search_line("lofi jazz", "30 min", "studying").startswith("30 min of lofi jazz beats")


def test_tags_carry_the_genres_search_phrasings():
    tags = g.build_tags({"genre_label": "chillhop", "activity": "reading"}, "1 hour")
    assert {"chillhop", "chillhop lofi mix", "chillhop lofi 1 hour",
            "chillhop lofi for reading"} <= set(tags)


class _FakeYT:
    def __init__(self, existing=()):
        self.existing = list(existing)
        self.created = []

    def playlists(self):
        return self

    def list(self, **kw):
        items = [{"id": i, "snippet": {"title": t}} for i, t in self.existing]
        return _Exec({"items": items})

    def insert(self, part, body):
        self.created.append(body["snippet"]["title"])
        return _Exec({"id": "PLnew", "snippet": body["snippet"]})


class _Exec:
    def __init__(self, r):
        self.r = r

    def execute(self):
        return self.r


def test_genre_playlists_are_opt_in(tmp_path):
    from scripts import playlist_curation as pc
    yt = _FakeYT()
    assert pc.genre_playlist_id(yt, "chillhop lofi", env={}, cache_path=str(tmp_path / "c.json")) is None
    assert yt.created == []


def test_genre_playlist_is_reused_then_created_once(tmp_path):
    from scripts import playlist_curation as pc
    env = {"YT_GENRE_PLAYLISTS": "1"}
    cache = str(tmp_path / "c.json")
    yt = _FakeYT(existing=[("PLold", pc.genre_playlist_title("chillhop lofi"))])
    assert pc.genre_playlist_id(yt, "chillhop lofi", env=env, cache_path=cache) == "PLold"
    assert yt.created == []
    yt2 = _FakeYT()
    assert pc.genre_playlist_id(yt2, "lofi jazz", env=env, cache_path=cache) == "PLnew"
    assert pc.genre_playlist_id(yt2, "lofi jazz", env=env, cache_path=cache) == "PLnew"
    assert len(yt2.created) == 1          # second call came from the cache
