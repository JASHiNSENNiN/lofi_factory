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
from collections import deque

from webui import config
from webui.app import (
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
def test_job_manager_marks_success_on_zero_exit():
    async def run():
        mgr = JobManager()
        job = await mgr.run("ok", ["-c", "pass"])
        for _ in range(50):
            await asyncio.sleep(0.05)
            if not job.running:
                break
        return job

    job = asyncio.run(run())
    assert job.status == "success"
    assert job.returncode == 0


def test_job_manager_marks_failed_on_nonzero_exit():
    async def run():
        mgr = JobManager()
        job = await mgr.run("fail", ["-c", "import sys; sys.exit(1)"])
        for _ in range(50):
            await asyncio.sleep(0.05)
            if not job.running:
                break
        return mgr, job

    mgr, job = asyncio.run(run())
    assert job.status == "failed"
    assert not mgr.is_busy()
