"""
system_admin.py — data-gathering + side-effect helpers for the System page
(webui/app.py's ``view_system``): resource monitor (CPU/RAM/disk via
psutil), optional GPU utilization (nvidia-smi/vainfo), a disk-usage
breakdown by content directory, Tailscale/TLS-cert status, config
backup/restore, and an append-only admin audit log.

Every function here is synchronous and does blocking I/O (psutil sampling,
subprocess calls, file copies) by design -- NiceGUI runs a single-threaded
event loop, so callers MUST wrap these in ``asyncio.to_thread(...)`` (see
webui/automation.py's ``tail_logs`` / app.py's ``view_system`` for the
pattern). Nothing in this module touches ``nicegui.ui``.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone

from . import config

AUDIT_LOG = os.path.join(config.ASSETS_DIR, "admin_audit.jsonl")
BACKUP_DIR = os.path.join(config.ROOT, "backups")
# Whichever of these exist get copied -- files that don't exist yet (e.g. no
# token.json before the first YouTube login) are silently skipped, not errors.
BACKUP_FILES = ("token.json", ".env", "upload_log.json")


# ─────────────────────────────────────────────────────────────────────────────
# Admin audit log — append-only JSONL, one line per admin action
# ─────────────────────────────────────────────────────────────────────────────
def audit_log(action: str, detail: dict | None = None) -> None:
    """Append one record to assets/admin_audit.jsonl. Best-effort: a logging
    failure (e.g. disk full) must never block the admin action it records."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": action,
        "detail": detail or {},
    }
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
        with open(AUDIT_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def audit_log_tail(n: int = 50) -> list[dict]:
    """Most-recent-first, up to n entries. A corrupt/partial line (e.g. the
    process died mid-write) is skipped rather than failing the whole read."""
    if not os.path.exists(AUDIT_LOG):
        return []
    entries: list[dict] = []
    try:
        with open(AUDIT_LOG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return list(reversed(entries))[:n]


# ─────────────────────────────────────────────────────────────────────────────
# Resource monitor (CPU / RAM / disk)
# ─────────────────────────────────────────────────────────────────────────────
def resource_snapshot() -> dict:
    """CPU/RAM/disk snapshot via psutil, for the repo's filesystem. Blocking
    -- psutil.cpu_percent(interval=...) sleeps to sample -- call via
    asyncio.to_thread."""
    import psutil

    cpu_percent = psutil.cpu_percent(interval=0.3)
    vm = psutil.virtual_memory()
    du = shutil.disk_usage(config.ROOT)
    return {
        "cpu_percent": cpu_percent,
        "ram_used_gb": round(vm.used / 1_073_741_824, 2),
        "ram_total_gb": round(vm.total / 1_073_741_824, 2),
        "ram_percent": vm.percent,
        "disk_used_gb": round(du.used / 1_073_741_824, 2),
        "disk_total_gb": round(du.total / 1_073_741_824, 2),
        "disk_percent": round(du.used / du.total * 100, 1) if du.total else 0.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GPU (best-effort — degrades to None if no supported binary is present)
# ─────────────────────────────────────────────────────────────────────────────
def gpu_snapshot() -> dict | None:
    """GPU utilization via nvidia-smi (NVIDIA, has real load numbers) or
    vainfo (VAAPI, presence-only -- it doesn't report live utilization).
    Returns None if neither binary exists or both fail, so the caller can
    hide the panel entirely on a GPU-less box instead of showing a broken
    one."""
    snap = _nvidia_smi_snapshot()
    if snap is not None:
        return snap
    return _vainfo_snapshot()


def _nvidia_smi_snapshot() -> dict | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, OSError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    line = out.stdout.strip().splitlines()[0]
    try:
        util, mem_used, mem_total = (float(x.strip()) for x in line.split(","))
    except ValueError:
        return None
    return {
        "backend": "nvidia-smi", "util_percent": util,
        "mem_used_mb": mem_used, "mem_total_mb": mem_total,
    }


def _vainfo_snapshot() -> dict | None:
    try:
        out = subprocess.run(["vainfo"], capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, OSError):
        return None
    if out.returncode != 0:
        return None
    driver_line = next((ln for ln in out.stdout.splitlines() if "driver" in ln.lower()), "")
    return {
        "backend": "vaapi", "util_percent": None,
        "info": driver_line.strip() or "VAAPI available",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Disk-usage breakdown by content directory
# ─────────────────────────────────────────────────────────────────────────────
def _dir_size_bytes(path: str) -> int:
    """Recursive byte total for a directory. Best-effort per-file -- a race
    with an in-progress render deleting/replacing a file doesn't abort the
    whole scan, it just skips that one entry."""
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return total


def disk_usage_breakdown() -> dict[str, int]:
    """Byte totals for the factory's main content directories."""
    dirs = {
        "output": config.OUTPUT_DIR,
        "music": config.MUSIC_DIR,
        "visuals": config.VISUALS_DIR,
        "assets": config.ASSETS_DIR,
    }
    return {
        name: _dir_size_bytes(path) if os.path.isdir(path) else 0
        for name, path in dirs.items()
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tailscale / TLS cert status
# ─────────────────────────────────────────────────────────────────────────────
CERT_EXPIRY_WARNING_DAYS = 14


def tailscale_status() -> dict | None:
    """Hostname, tailnet IP, and peer count from `tailscale status --json`.
    None if the binary isn't installed, the daemon isn't reachable, or the
    output can't be parsed -- the caller hides the panel in that case."""
    try:
        out = subprocess.run(["tailscale", "status", "--json"],
                              capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, OSError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    try:
        parsed = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None
    self_node = parsed.get("Self") or {}
    peers = parsed.get("Peer") or {}
    return {
        "hostname": self_node.get("HostName") or self_node.get("DNSName") or "?",
        "tailscale_ip": (self_node.get("TailscaleIPs") or [None])[0],
        "peer_count": len(peers),
        "online": self_node.get("Online", True),
    }


def cert_status() -> dict | None:
    """TLS cert expiry for config.SSL_CERTFILE, via `openssl x509
    -enddate`. None if no cert is configured, the file is missing, or
    openssl isn't installed."""
    cert = config.SSL_CERTFILE
    if not cert or not os.path.exists(cert):
        return None
    try:
        out = subprocess.run(["openssl", "x509", "-enddate", "-noout", "-in", cert],
                              capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, OSError):
        return None
    if out.returncode != 0:
        return None
    line = out.stdout.strip()  # "notAfter=Aug 20 12:00:00 2026 GMT"
    if "=" not in line:
        return None
    raw = line.split("=", 1)[1].strip()
    try:
        expiry = datetime.strptime(raw, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    days_left = (expiry - datetime.now(timezone.utc)).total_seconds() / 86400
    return {
        "path": cert,
        "expires": expiry.strftime("%Y-%m-%d"),
        "days_left": round(days_left, 1),
        "expiring_soon": days_left <= CERT_EXPIRY_WARNING_DAYS,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Self-service webui restart
# ─────────────────────────────────────────────────────────────────────────────
def restart_webui() -> None:
    """Restart the lofi-webui.service unit. This intentionally kills the
    caller's own connection -- app.py confirms with the user via a dialog
    before calling this. The audit entry is written first so it's recorded
    even if the process is torn down before subprocess.run() returns."""
    audit_log("webui_restart", {})
    subprocess.run(["systemctl", "--user", "restart", "lofi-webui.service"],
                    capture_output=True, text=True, timeout=10, check=True)


# ─────────────────────────────────────────────────────────────────────────────
# Config backup / restore
# ─────────────────────────────────────────────────────────────────────────────
def create_backup() -> dict:
    """Copy whichever of BACKUP_FILES currently exist into
    backups/<timestamp>/ on local disk. Never served to the browser as a
    download -- these are live secrets (OAuth token, .env, upload log)."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_DIR, ts)
    os.makedirs(dest, exist_ok=True)
    copied = []
    for name in BACKUP_FILES:
        src = os.path.join(config.ROOT, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest, name))
            copied.append(name)
    audit_log("config_backup", {"name": ts, "files": copied})
    return {"name": ts, "path": dest, "files": copied}


def list_backups() -> list[dict]:
    """Existing backups, newest first (timestamped names sort lexically)."""
    if not os.path.isdir(BACKUP_DIR):
        return []
    out = []
    for name in sorted(os.listdir(BACKUP_DIR), reverse=True):
        path = os.path.join(BACKUP_DIR, name)
        if not os.path.isdir(path):
            continue
        files = sorted(f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)))
        total = sum(os.path.getsize(os.path.join(path, f)) for f in files)
        out.append({"name": name, "path": path, "files": files, "total_bytes": total})
    return out


def _resolve_backup(name: str) -> str | None:
    """Resolve a backup dir name to a real path inside BACKUP_DIR, refusing
    anything that isn't a direct, existing child -- blocks path traversal
    via a crafted name like '../../etc' reaching outside BACKUP_DIR."""
    if not name or os.sep in name or name in (".", ".."):
        return None
    root = os.path.realpath(BACKUP_DIR)
    path = os.path.realpath(os.path.join(BACKUP_DIR, name))
    if path != os.path.join(root, name) or not os.path.isdir(path):
        return None
    return path


def restore_backup(name: str) -> list[str]:
    """Copy a backup's files back to the repo root, overwriting the current
    ones. Returns the filenames actually restored."""
    path = _resolve_backup(name)
    if path is None:
        raise ValueError(f"No such backup: {name}")
    restored = []
    for fname in BACKUP_FILES:
        src = os.path.join(path, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(config.ROOT, fname))
            restored.append(fname)
    audit_log("config_restore", {"name": name, "files": restored})
    return restored


def delete_backup(name: str) -> bool:
    path = _resolve_backup(name)
    if path is None:
        return False
    shutil.rmtree(path, ignore_errors=True)
    audit_log("config_backup_delete", {"name": name})
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Orphaned scratch-file cleanup — music/visuals leftovers from a killed/failed
# run that never got assembled into an output/ video. Confirmed 2026-08-16: a
# run wedged in mem_cgroup_handle_over_high for 23+ hours left ~3.85GB of
# per-track .wav files across several past failed runs sitting in music/ with
# nothing referencing them, cleaned up by hand once -- this gives that same
# cleanup a repeatable button instead of a manual SSH session next time.
# ─────────────────────────────────────────────────────────────────────────────
# The only files in music/ and visuals/ that are actual scratch (per-run
# generation intermediates); everything else in those two directories is a
# persistent cross-run learning log (recipe/melody/params/audio-quality
# history) that must never be swept up by this.
_SCRATCH_PATTERNS = {
    "music": (config.MUSIC_DIR, ("track_*.wav", "track_*.wav.meta.json")),
    "visuals": (config.VISUALS_DIR, ("bg_*.mp4",)),
}


def orphaned_scratch_files() -> list[dict]:
    """{"path", "size_bytes", "mtime"} for every scratch file currently in
    music/ or visuals/. Caller must confirm nothing is rendering first (see
    clean_orphaned_scratch's docstring) -- otherwise this lists files an
    in-progress run is actively writing, not just true leftovers."""
    out = []
    for _label, (directory, patterns) in _SCRATCH_PATTERNS.items():
        if not os.path.isdir(directory):
            continue
        for pattern in patterns:
            for path in glob.glob(os.path.join(directory, pattern)):
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                out.append({"path": path, "size_bytes": st.st_size, "mtime": st.st_mtime})
    return out


def clean_orphaned_scratch() -> dict:
    """Delete every file orphaned_scratch_files() finds. Caller MUST verify
    nothing is currently rendering first (webui/jobs.py's JobManager.is_busy()
    and the lofi-auto systemd unit both need checking) -- this module doesn't
    import either to avoid a dependency cycle, so that safety check lives at
    the call site, same pattern as app.py's _confirm_delete_render guard."""
    files = orphaned_scratch_files()
    freed = 0
    deleted = 0
    for f in files:
        try:
            os.remove(f["path"])
            freed += f["size_bytes"]
            deleted += 1
        except OSError:
            continue
    audit_log("clean_orphaned_scratch", {"deleted": deleted, "freed_bytes": freed})
    return {"deleted": deleted, "freed_bytes": freed}
