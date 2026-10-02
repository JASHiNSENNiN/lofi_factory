# Deployment runbook

Deploying lofi_factory to a Debian/Ubuntu VPS for daily unattended
render+upload, or 24/7 live streaming. Written for a single-user personal
box, not a shared/multi-tenant server — the hardening section below is
scoped accordingly (see [Assumptions](#assumptions)).

## Assumptions

- Fresh **Debian or Ubuntu** VPS, systemd present, you have sudo.
- Everything runs as **systemd *user* services** under one non-root login
  (`systemctl --user ...`), not root-level system services — that's what
  `deploy/setup.sh` installs and what the unit files in `deploy/` assume.
  `loginctl enable-linger` is what makes user services start at boot
  without an active login session; `setup.sh` enables it for you.
- The web control panel is reached through a **Cloudflare Tunnel**, not a
  directly exposed port — `deploy/setup.sh` sets this up. If you don't want
  that, two alternatives:
  - SSH port-forwarding: skip step 5 below, `ssh -L 8080:localhost:8080 you@vps`.
  - **Tailscale-only** (no public exposure at all, no tunnel setup, works from
    any device on your tailnet): set `WEBUI_HOST` in `.env` to the box's
    Tailscale IP (`tailscale ip -4`) instead of `127.0.0.1`, firewall the
    port to just the tailscale interface (`sudo ufw allow in on tailscale0
    to any port 8080 proto tcp`), and set `PUBLIC_BASE_URL` to
    `http://<tailscale-ip>:8080` (needed even without a public tunnel — the
    YouTube OAuth redirect URI is derived from it, and without it OAuth only
    works from a browser running on the box itself). Skip the `cloudflared`
    parts of step 5 entirely; `setup.sh` detects there's no tunnel to set up
    and stops gracefully on its own once it gets there.
- This box is dedicated to this pipeline. The hardening steps below are the
  sensible baseline for that, not a full CIS-benchmark server audit.

## Prerequisites

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential \
    ffmpeg fluidsynth libsndfile1 git curl ufw fail2ban unattended-upgrades
```

`build-essential` matters here specifically because a couple of Python
dependencies (`python-rtmidi`, `pedalboard`) are native extensions without
guaranteed prebuilt wheels for every platform — without a compiler present,
`pip install -r requirements.txt` fails partway through.

## First-time setup

```bash
git clone https://github.com/JASHiNSENNiN/lofi_factory.git
cd lofi_factory
python3 -m venv venv                    # NOT .venv -- deploy/*.service hardcode venv/bin/python
venv/bin/pip install -r requirements.txt

cp .env.example .env
nano .env                               # fill in YT_STREAM_KEY, WEBUI_PASSWORD, etc. -- see README.md

python -m pytest                        # sanity check before anything touches YouTube
bash deploy/setup.sh                    # installs + enables the systemd services below
```

`setup.sh` is idempotent — safe to re-run after pulling updates or fixing
`.env` values.

## What `deploy/setup.sh` installs

| Unit | Purpose | Enabled |
|---|---|---|
| `lofi-webui.service` | NiceGUI control panel (`webui.py`) | immediately, `Restart=always` |
| `lofi-auto.timer` + `.service` | Daily render+upload (`publish.py auto`) | immediately — the timer just arms the schedule, the first real run is at the next scheduled time, not on enable |
| `cloudflared-lofi.service` | Public tunnel for the control panel | once you've run `cloudflared tunnel login` and set `PUBLIC_BASE_URL` |

`setup.sh` also applies a small OS hardening baseline (last step): UFW
allowing only SSH inbound, Fail2Ban for SSH, `unattended-upgrades` for
security patches — each skips gracefully with a warning if its package
isn't installed rather than failing the whole run (they're in the
[Prerequisites](#prerequisites) apt list above, so a fresh box gets all
three). This is intentionally the sensible baseline for a single-purpose
personal box, not a full security audit.

**Before trusting the auto-upload timer with a real schedule**, run the
smoke-test procedure below at least once — `setup.sh` enabling the timer
immediately is safe (it does nothing until the scheduled time), but don't
let it fire against a config you haven't verified.

## Smoke test (run once, before trusting daily auto-upload)

```bash
# 15-20 consecutive generate-only runs -- exercises the probabilistic
# generation paths enough times to surface a rare failure directly,
# instead of it silently aborting a real scheduled run weeks later.
for i in $(seq 1 15); do
  venv/bin/python run.py --skip-upload --duration "1 hour" || break
done

# GA voice-leading engine has essentially zero production run history --
# validate it explicitly at least once.
venv/bin/python run.py --skip-upload --music-v2 --duration "1 hour"

# One full timing run to confirm render time fits comfortably inside
# whatever schedule interval you set (auto-service schedule, below).
time venv/bin/python run.py --skip-upload --duration "2 hours"
```

## Day-2 operations

```bash
python publish.py auto-service status              # armed? next run? last run?
python publish.py auto-service schedule --start 0 --every-hours 6   # 6/8/12/24 only
python publish.py auto-service run-now              # trigger a run immediately
python publish.py auto-service logs                 # follow via journalctl
python publish.py auto-service stop                 # halt the timer
python publish.py auto-service disable              # don't start at boot either

journalctl --user -u lofi-auto -f                   # same thing, direct
journalctl --user -u lofi-webui -f
systemctl --user restart lofi-webui

```

**Rollback**: `git log --oneline`, `git checkout <previous-commit>`,
`venv/bin/pip install -r requirements.txt` (in case deps changed),
`systemctl --user restart lofi-webui` — `lofi-auto.service` is `Type=oneshot`
so there's nothing to restart there, it just picks up the new code on its
next scheduled run.

**If the Python process itself crashes** (not just ffmpeg — an unhandled
exception, OOM): `lofi-webui.service` has `Restart=always` so systemd
brings it back. `lofi-auto.service` is oneshot and only runs when the timer
fires, so there's nothing to "crash" between runs. `scripts/stream_live.py`
(live-stream mode, not the daily upload) has its own in-process reconnect
loop for ffmpeg/RTMP drops, but explicitly does *not* recover from the
Python process itself dying — if you run it directly (not via a service
unit), a crash needs a supervisor one layer up; wrap it in its own
`systemd --user` unit with `Restart=always` if you run it long-term.

## Resource limits

`lofi-auto.service` and `lofi-webui.service` set `MemoryHigh=`/`MemoryMax=`
so a runaway ffmpeg encode or stuck generation loop can't OOM the whole
box — relevant on a low-end VPS (this pipeline is tuned throughout for
low-thread-count hardware, see `stream_live.py`'s encoding comments).
Adjust the values in `deploy/lofi-auto.service` /
`deploy/lofi-webui.service` to your actual VPS RAM before copying them in
via `setup.sh` if your plan is smaller than ~2GB.

## Troubleshooting

| Symptom | Check |
|---|---|
| `auto-service status` says "not installed" | Re-run `bash deploy/setup.sh` |
| Timer armed but never runs | `systemctl --user list-timers`, check the box wasn't asleep/off at the scheduled time (`Persistent=true` catches up on next boot, but only if the box was actually down, not just busy) |
| Upload fails with an auth error | Re-run OAuth setup: see `python publish.py --help`'s SETUP section, or `python publish.py --auth` |
| `pip install` fails on `python-rtmidi`/`pedalboard` | Missing `build-essential` — see [Prerequisites](#prerequisites) |
| Web panel unreachable | `systemctl --user status cloudflared-lofi`, confirm `PUBLIC_BASE_URL` in `.env` matches the tunnel's DNS route |
| Stream keeps reconnecting | Check `LOFI_STREAM_ALERT_WEBHOOK` alerts if configured, otherwise `journalctl --user -u <the stream's unit> -f` for the ffmpeg stderr lines `stream_live.py` surfaces on stall/error |
