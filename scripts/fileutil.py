"""Crash-safe file writes and JSON loading for the pipeline's state files.

Writing a file in place truncates it first, so a crash or a full disk
mid-write leaves it empty or half-written. These helpers write a temporary
file next to the target and rename it over the original, which is atomic
on POSIX filesystems.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile


def atomic_write_text(path: str, text: str, mode: int | None = None) -> None:
    """Replace `path` with `text` atomically. `mode` sets permissions before
    any content is written (use 0o600 for secrets)."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=os.path.basename(path))
    try:
        if mode is not None:
            os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: str, data, mode: int | None = None, **dump_kwargs) -> None:
    dump_kwargs.setdefault("indent", 2)
    atomic_write_text(path, json.dumps(data, **dump_kwargs), mode=mode)


class CorruptStateFile(RuntimeError):
    """A state file exists but can't be parsed. Raised instead of returning an
    empty default, because the caller would then overwrite real data."""


def load_json_or_quarantine(path: str, default):
    """Load JSON from `path`. Missing file -> `default`. Unparseable file ->
    copied aside to `<path>.corrupt-<n>` and CorruptStateFile raised, so the
    original is never silently replaced by an empty structure."""
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        n = 1
        while os.path.exists(f"{path}.corrupt-{n}"):
            n += 1
        shutil.copy2(path, f"{path}.corrupt-{n}")
        raise CorruptStateFile(f"{path} is unreadable ({e}); a copy was saved as "
                               f"{path}.corrupt-{n}. Fix or remove it to continue.") from e


def preserve_if_corrupt(path: str) -> None:
    """If `path` exists but isn't valid JSON, copy it aside first, so a
    writer that rebuilt its data from an empty default can't destroy it."""
    try:
        load_json_or_quarantine(path, None)
    except CorruptStateFile as e:
        print(f"[state] {e}")


def append_json_list(path: str, entry) -> None:
    """Append `entry` to the JSON list stored at `path`, atomically. An
    unreadable file is preserved as a .corrupt-N copy, never overwritten."""
    try:
        items = load_json_or_quarantine(path, [])
    except CorruptStateFile as e:
        print(f"[state] {e}")
        items = []
    if not isinstance(items, list):
        raise ValueError(f"{path} does not hold a JSON list")
    items.append(entry)
    atomic_write_json(path, items)
