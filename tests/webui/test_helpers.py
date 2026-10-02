"""
Regression tests for webui/ pure-logic helpers.

Zero test coverage here was flagged as a real gap during a webui overhaul session
(a NiceGUI upload-API mismatch shipped silently for months as a result). These
tests target the functions most likely to regress silently: log parsing, .env
editing, analytics computation, and job status transitions -- not full page
rendering, which would need nicegui.testing's browser-driven User fixture.
"""
from __future__ import annotations

import asyncio
import json
from collections import deque

import pytest

from webui import config
from webui.app import (
    _card_from_artifacts,
    _latest_ffmpeg_progress,
    _parse_ffmpeg_progress,
    _stage_from_lines,
    _target_secs,
)
from webui.jobs import Job, JobManager
from scripts import analytics as analytics_mod


def _job_with_lines(lines: list[str]) -> Job:
    j = Job(id="t", name="test", cmd=[])
    j.lines = deque(lines)
    return j


# ── ffmpeg progress / stage parsing (ported from dashboard.py) ────────────────
def test_parse_ffmpeg_progress_extracts_fields():
    line = "frame= 1300 fps=24.0 q=-1.0 size=  130000kB time=00:13:00.00 bitrate=8000.0kbits/s speed=1.01x"
    parsed = _parse_ffmpeg_progress(line)
    assert parsed is not None
    assert parsed["time"] == "00:13:00.00"
    assert parsed["speed"] == "1.01x"


def test_parse_ffmpeg_progress_ignores_non_stats_lines():
    assert _parse_ffmpeg_progress("[1/5] Rendering visual...") is None
    assert _parse_ffmpeg_progress("") is None


def test_stage_from_lines_picks_most_recent_marker():
    job = _job_with_lines([
        "[1/5] Rendering visual...",
        "[2/5] Generating music...",
        "[ASSEMBLE] Duration: 2 hours (7200s)",
        "frame= 100 fps=24.0 time=00:01:00.00 speed=1.0x",
    ])
    assert _stage_from_lines(job) == "Assembling video"


def test_stage_from_lines_none_when_no_markers_seen_yet():
    job = _job_with_lines(["some unrelated startup log line"])
    assert _stage_from_lines(job) is None


def test_target_secs_parses_duration_marker():
    job = _job_with_lines(["[ASSEMBLE] Duration: 2 hours (7200s)"])
    assert _target_secs(job) == 7200


def test_target_secs_none_without_marker():
    job = _job_with_lines(["nothing relevant here"])
    assert _target_secs(job) is None


def test_latest_ffmpeg_progress_returns_most_recent():
    job = _job_with_lines([
        "frame= 100 fps=24.0 time=00:01:00.00 speed=1.0x",
        "frame= 200 fps=24.0 time=00:02:00.00 speed=1.0x",
    ])
    parsed = _latest_ffmpeg_progress(job)
    assert parsed is not None
    assert parsed["time"] == "00:02:00.00"


def test_progress_percent_calculation_matches_target():
    job = _job_with_lines([
        "[ASSEMBLE] Duration: 2 hours (7200s)",
        "frame= 100 fps=24.0 time=00:12:00.00 speed=1.0x",
    ])
    fp = _latest_ffmpeg_progress(job)
    target = _target_secs(job)
    hh, mm, ss = (int(float(x)) for x in fp["time"].split(":")[:3])
    pct = min((hh * 3600 + mm * 60 + ss) / target, 1.0)
    assert abs(pct - 0.10) < 1e-9  # 12 min / 120 min = 10%


# ── .env editing ────────────────────────────────────────────────────────────
def test_env_write_then_read_roundtrip(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING_KEY=keep-me\n")
    monkeypatch.setattr(config, "ENV_FILE", str(env_file))

    config.write_env_value("NEW_KEY", "hello")
    values = config.read_env_file()

    assert values["NEW_KEY"] == "hello"
    assert values["EXISTING_KEY"] == "keep-me"  # untouched


def test_env_write_updates_existing_key_in_place(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\nB=2\nC=3\n")
    monkeypatch.setattr(config, "ENV_FILE", str(env_file))

    config.write_env_value("B", "changed")
    lines = env_file.read_text().splitlines()

    assert lines == ["A=1", "B=changed", "C=3"]  # order preserved, only B changed


def test_env_write_sets_restrictive_permissions(tmp_path, monkeypatch):
    import os
    env_file = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_FILE", str(env_file))

    config.write_env_value("SECRET", "x")

    assert oct(os.stat(env_file).st_mode)[-3:] == "600"


def test_env_write_rejects_newline_in_value(tmp_path, monkeypatch):
    # A newline in the value would inject extra, uncontrolled lines into .env
    # (e.g. a pasted multi-line value silently adding unrelated KEY=VALUE entries).
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING=1\n")
    monkeypatch.setattr(config, "ENV_FILE", str(env_file))

    import pytest
    with pytest.raises(ValueError):
        config.write_env_value("EVIL", "safe\nINJECTED_KEY=injected")

    # File must be untouched -- reject before any write happens.
    assert env_file.read_text() == "EXISTING=1\n"


# ── analytics pillar-stats computation ─────────────────────────────────────
def test_compute_pillar_stats_empty():
    result = analytics_mod.compute_pillar_stats({})
    assert result == {"by_pillar": [], "channel_avg_ctr": 0, "n_total": 0}


def test_compute_pillar_stats_sorts_best_ctr_first():
    fake = {
        "v1": {"pillar": "temporal", "videoThumbnailImpressionsClickRate": 0.05,
               "estimatedMinutesWatched": 100, "views": 300},
        "v2": {"pillar": "aesthetic", "videoThumbnailImpressionsClickRate": 0.02,
               "estimatedMinutesWatched": 50, "views": 100},
    }
    result = analytics_mod.compute_pillar_stats(fake)
    assert [r["pillar"] for r in result["by_pillar"]] == ["temporal", "aesthetic"]
    assert result["n_total"] == 2


def test_compute_pillar_stats_marks_above_below_average():
    fake = {
        "v1": {"pillar": "high", "videoThumbnailImpressionsClickRate": 0.10,
               "estimatedMinutesWatched": 1, "views": 1},
        "v2": {"pillar": "low", "videoThumbnailImpressionsClickRate": 0.01,
               "estimatedMinutesWatched": 1, "views": 1},
    }
    result = analytics_mod.compute_pillar_stats(fake)
    by_pillar = {r["pillar"]: r for r in result["by_pillar"]}
    assert by_pillar["high"]["marker"] == "▲"
    assert by_pillar["low"]["marker"] == "▼"


# ── JobManager status transitions ──────────────────────────────────────────
# Every JobManager() below passes an explicit tmp_path history_path -- since
# JobManager now persists each finished job to disk (see webui/jobs.py's
# _append_history_file()), an unscoped JobManager() would otherwise write
# real entries into this repo's assets/job_history.jsonl on every test run.
def test_job_manager_marks_success_on_zero_exit(tmp_path):
    async def run():
        mgr = JobManager(history_path=str(tmp_path / "job_history.jsonl"))
        job = await mgr.run("ok", ["-c", "pass"])
        for _ in range(50):
            await asyncio.sleep(0.05)
            if not job.running:
                break
        return job

    job = asyncio.run(run())
    assert job.status == "success"
    assert job.returncode == 0


def test_job_manager_parses_result_line_into_artifacts(tmp_path):
    async def run():
        mgr = JobManager(history_path=str(tmp_path / "job_history.jsonl"))
        job = await mgr.run("ok", [
            "-c",
            "import json; print('[RESULT] ' + json.dumps("
            "{'video': 'output/lofi_x.mp4', 'thumb': 'assets/thumb_x.jpg', "
            "'thumb_alt': '', 'seo': 'assets/seo_x.json'}))",
        ])
        for _ in range(50):
            await asyncio.sleep(0.05)
            if not job.running:
                break
        return job

    job = asyncio.run(run())
    assert job.status == "success"
    assert job.artifacts == {
        "video": "output/lofi_x.mp4", "thumb": "assets/thumb_x.jpg",
        "thumb_alt": "", "seo": "assets/seo_x.json",
    }


def test_job_manager_artifacts_empty_when_no_result_line(tmp_path):
    async def run():
        mgr = JobManager(history_path=str(tmp_path / "job_history.jsonl"))
        job = await mgr.run("ok", ["-c", "print('no result line here')"])
        for _ in range(50):
            await asyncio.sleep(0.05)
            if not job.running:
                break
        return job

    job = asyncio.run(run())
    assert job.artifacts == {}


def test_card_from_artifacts_builds_openable_card():
    j = Job(id="t", name="render", cmd=[], status="success")
    j.artifacts = {
        "video": "output/lofi_x.mp4", "thumb": "assets/thumb_x.jpg",
        "thumb_alt": "", "seo": "assets/seo_x.json",
    }
    card = _card_from_artifacts(j)
    assert card == {
        "theme": "", "dt": None,
        "thumb": "assets/thumb_x.jpg", "thumb_name": "thumb_x.jpg",
        "title": "render", "url": None, "video_id": None,
        "video_file": "lofi_x.mp4", "when": "",
    }


def test_card_from_artifacts_none_without_video():
    j = Job(id="t", name="render", cmd=[], status="success")
    assert _card_from_artifacts(j) is None


def test_job_manager_marks_failed_on_nonzero_exit(tmp_path):
    async def run():
        mgr = JobManager(history_path=str(tmp_path / "job_history.jsonl"))
        job = await mgr.run("fail", ["-c", "import sys; sys.exit(1)"])
        for _ in range(50):
            await asyncio.sleep(0.05)
            if not job.running:
                break
        return mgr, job

    mgr, job = asyncio.run(run())
    assert job.status == "failed"
    assert not mgr.is_busy()


# ── persistent job history (survives a webui restart) ──────────────────────
def test_finished_job_appended_to_history_file(tmp_path):
    hist_file = tmp_path / "job_history.jsonl"

    async def run():
        mgr = JobManager(history_path=str(hist_file))
        job = await mgr.run("ok", ["-c", "pass"])
        for _ in range(50):
            await asyncio.sleep(0.05)
            if not job.running:
                break
        return job

    job = asyncio.run(run())
    assert hist_file.exists()
    lines = [line for line in hist_file.read_text().splitlines() if line.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["id"] == job.id
    assert rec["name"] == "ok"
    assert rec["status"] == "success"
    assert rec["returncode"] == 0
    assert rec["slot"] == "main"


def test_history_survives_fresh_jobmanager_construction(tmp_path):
    hist_file = tmp_path / "job_history.jsonl"

    async def run_one(name, code):
        mgr = JobManager(history_path=str(hist_file))
        job = await mgr.run(name, ["-c", f"import sys; sys.exit({code})"])
        for _ in range(50):
            await asyncio.sleep(0.05)
            if not job.running:
                break
        return job

    job1 = asyncio.run(run_one("first", 0))
    job2 = asyncio.run(run_one("second", 1))

    # A brand-new JobManager (simulating a webui restart) picks history back
    # up from disk without ever having run a job itself.
    fresh = JobManager(history_path=str(hist_file))
    assert [j.id for j in fresh.history] == [job2.id, job1.id]  # most-recent-first
    assert fresh.history[0].name == "second"
    assert fresh.history[0].status == "failed"
    assert fresh.history[1].name == "first"
    assert fresh.history[1].status == "success"
    # Reloaded jobs are usable by the UI even without their old log lines.
    assert list(fresh.history[0].lines) == []
    assert fresh.history[0].duration >= 0


def test_load_history_file_caps_at_limit(tmp_path):
    hist_file = tmp_path / "job_history.jsonl"
    with open(hist_file, "w") as f:
        for i in range(25):
            f.write(json.dumps({
                "id": f"job-{i}", "name": "n", "cmd": ["python", "run.py"],
                "status": "success", "slot": "main", "returncode": 0,
                "started_at": float(i), "finished_at": float(i) + 1, "artifacts": {},
            }) + "\n")

    mgr = JobManager(history_path=str(hist_file))
    assert len(mgr.history) == 20
    # Most-recent-first, and "most recent" means latest lines in the file.
    assert mgr.history[0].id == "job-24"
    assert mgr.history[-1].id == "job-5"


def test_missing_history_file_starts_empty(tmp_path):
    mgr = JobManager(history_path=str(tmp_path / "nonexistent.jsonl"))
    assert mgr.history == []


def test_corrupt_history_line_is_skipped_not_fatal(tmp_path):
    hist_file = tmp_path / "job_history.jsonl"
    hist_file.write_text(
        '{"id": "good", "name": "n", "cmd": [], "status": "success", "slot": "main", '
        '"returncode": 0, "started_at": 1.0, "finished_at": 2.0, "artifacts": {}}\n'
        "{not valid json\n"
    )
    mgr = JobManager(history_path=str(hist_file))
    assert [j.id for j in mgr.history] == ["good"]


# ── retry (re-run a failed job with its exact original cmd/slot) ────────────
def test_retry_reruns_failed_job_with_same_cmd_and_slot(tmp_path):
    async def run():
        mgr = JobManager(history_path=str(tmp_path / "job_history.jsonl"))
        job = await mgr.run("fail", ["-c", "import sys; sys.exit(3)"], slot="main")
        for _ in range(50):
            await asyncio.sleep(0.05)
            if not job.running:
                break
        assert job.status == "failed"

        retried = await mgr.retry(job.id)
        for _ in range(50):
            await asyncio.sleep(0.05)
            if not retried.running:
                break
        return job, retried

    job, retried = asyncio.run(run())
    # A genuinely new Job object -- job.id has 1-second granularity so it can
    # collide with the original when retried immediately, but it's still a
    # fresh run (new Job instance/process), not a mutation of the old one.
    assert retried is not job
    assert retried.cmd == job.cmd  # exact same [python, *args]
    assert retried.name == job.name
    assert retried.slot == "main"
    assert retried.status == "failed"  # exit(3) again -> still fails, same behavior


def test_retry_raises_for_unknown_job_id(tmp_path):
    async def run():
        mgr = JobManager(history_path=str(tmp_path / "job_history.jsonl"))
        with pytest.raises(ValueError):
            await mgr.retry("does-not-exist")

    asyncio.run(run())


def test_retry_refuses_a_successful_job(tmp_path):
    async def run():
        mgr = JobManager(history_path=str(tmp_path / "job_history.jsonl"))
        job = await mgr.run("ok", ["-c", "pass"])
        for _ in range(50):
            await asyncio.sleep(0.05)
            if not job.running:
                break
        assert job.status == "success"
        with pytest.raises(ValueError):
            await mgr.retry(job.id)

    asyncio.run(run())


def test_stats_warmer_refreshes_caches_without_raising(monkeypatch):
    from webui import stats
    calls = []
    monkeypatch.setattr(stats, "channel_stats", lambda force=False: calls.append("ch"))
    monkeypatch.setattr(stats, "traffic_sources", lambda force=False: calls.append("tr"))
    monkeypatch.setattr(stats, "subscriber_growth", lambda force=False: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(stats, "revenue_available", lambda: False)
    monkeypatch.setattr(stats, "library", lambda limit=200: [{"video_id": "abc"}, {"video_id": None}])
    monkeypatch.setattr(stats, "video_engagement", lambda vids, force=False: calls.append(("eng", vids, force)))
    stats.warm_caches()
    assert calls == ["ch", "tr", ("eng", ["abc"], True)]
    assert stats.WARM_EVERY_SECS < stats._TTL       # caches never expire while the panel runs
