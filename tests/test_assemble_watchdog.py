"""
Regression tests for assemble_video.py's ffmpeg stall watchdog.

A real render deadlocked in production: all 38 x264 worker threads permanently
blocked on a futex, with the process never exiting and file/CPU progress frozen
for 14+ minutes. The single-timeout subprocess.run() this replaced would have
waited out the full timeout (hours) before killing it. These tests cover the
watchdog that replaced it and catches that class of hang in minutes instead.
"""
import os
import subprocess
import tempfile
import time

from scripts.assemble_video import (
    _HardTimeout,
    _StallTimeout,
    _tail_progress_secs,
    _wait_with_stall_watchdog,
)


def test_tail_progress_secs_parses_latest_carriage_return_line():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        f.write("some header\n")
        f.write("frame=100 time=00:01:00.00 speed=1.0x\r")
        f.write("frame=200 time=00:02:30.50 speed=1.0x\r")
        path = f.name
    try:
        assert abs(_tail_progress_secs(path) - 150.5) < 0.01
    finally:
        os.unlink(path)


def test_tail_progress_secs_none_without_a_time_marker():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        f.write("nothing relevant here\n")
        path = f.name
    try:
        assert _tail_progress_secs(path) is None
    finally:
        os.unlink(path)


def test_watchdog_returns_exit_code_on_clean_completion():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        log_path = f.name
    try:
        with open(log_path, "w") as log_fh:
            proc = subprocess.Popen(["python3", "-c", "pass"], stdout=log_fh, stderr=log_fh)
            rc = _wait_with_stall_watchdog(proc, log_path, target_secs=60)
        assert rc == 0
    finally:
        os.unlink(log_path)


def test_watchdog_kills_and_raises_on_genuine_stall():
    # Simulates the real deadlock: progress reported once, then the process hangs.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        log_path = f.name
    try:
        with open(log_path, "w") as log_fh:
            proc = subprocess.Popen([
                "python3", "-c",
                "import sys, time\n"
                "sys.stdout.write('frame=100 time=00:00:05.00 speed=1.0x\\r')\n"
                "sys.stdout.flush()\n"
                "time.sleep(600)\n",
            ], stdout=log_fh, stderr=log_fh)
            start = time.time()
            try:
                _wait_with_stall_watchdog(proc, log_path, target_secs=3600,
                                          stall_secs=2, poll_interval=0.5)
                assert False, "expected _StallTimeout"
            except _StallTimeout as e:
                elapsed = time.time() - start
                assert elapsed < 10, f"stall detection took too long: {elapsed}s"
                assert e.last_progress == 5.0
                assert proc.poll() is not None, "process should have been killed"
    finally:
        os.unlink(log_path)


def test_watchdog_hard_timeout_backstop_even_with_trickling_progress():
    # Backstop for the progress parser itself being wrong -- fires on wall-clock
    # time regardless, so a bug in stall detection can't cause an infinite wait.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        log_path = f.name
    try:
        with open(log_path, "w") as log_fh:
            proc = subprocess.Popen(["python3", "-c", "import time; time.sleep(600)"],
                                    stdout=log_fh, stderr=log_fh)
            start = time.time()
            try:
                _wait_with_stall_watchdog(proc, log_path, target_secs=3600,
                                          stall_secs=9999, poll_interval=0.5,
                                          hard_timeout_secs=2)
                assert False, "expected _HardTimeout"
            except _HardTimeout:
                elapsed = time.time() - start
                assert elapsed < 10, f"hard timeout took too long: {elapsed}s"
                assert proc.poll() is not None, "process should have been killed"
    finally:
        os.unlink(log_path)
