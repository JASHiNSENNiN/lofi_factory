"""Cancelling a job must stop its child processes too and must not be
reported (or alerted) as a failure."""
import asyncio
import os
import time

from webui import alerts, jobs


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill(0); check its state.
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split()[2] != "Z"
    except FileNotFoundError:
        return False


def test_cancel_kills_children_and_is_not_a_failure(tmp_path, monkeypatch):
    sent = []

    async def fake_alert(job):
        sent.append(job.id)

    monkeypatch.setattr(alerts, "send_job_failure", fake_alert)
    pidfile = tmp_path / "child.pid"
    script = (
        "import subprocess, time\n"
        "p = subprocess.Popen(['sleep', '60'])\n"
        f"open({str(pidfile)!r}, 'w').write(str(p.pid))\n"
        "time.sleep(60)\n"
    )

    async def scenario():
        manager = jobs.JobManager(history_path=str(tmp_path / "history.jsonl"))
        job = await manager.run("render", ["-c", script])
        for _ in range(100):
            if pidfile.exists() and pidfile.read_text():
                break
            await asyncio.sleep(0.05)
        child = int(pidfile.read_text())
        await manager.cancel()
        for _ in range(100):
            if not job.running:
                break
            await asyncio.sleep(0.05)
        return job, child

    job, child = asyncio.run(scenario())
    time.sleep(0.2)
    assert job.status == "cancelled"
    assert not _alive(child), "the job's child process survived cancel"
    assert sent == []


def test_job_ids_are_unique_within_the_same_second(tmp_path):
    async def scenario():
        manager = jobs.JobManager(history_path=str(tmp_path / "h.jsonl"))
        a = await manager.run("render", ["-c", "pass"])
        await asyncio.sleep(0.3)
        b = await manager.run("render", ["-c", "pass"])
        await asyncio.sleep(0.3)
        return a.id, b.id

    a, b = asyncio.run(scenario())
    assert a != b


def test_failure_summary_prefers_the_error_line():
    from webui.jobs import _failure_summary
    lines = ["[END] Ending broadcast", "[ERROR] No active broadcast found.",
             "  To list broadcasts: python publish.py status", ""]
    assert _failure_summary(lines) == "[ERROR] No active broadcast found."
    assert _failure_summary(["a", "b"]) == "b"
    assert _failure_summary([]) == ""
