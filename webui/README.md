# Lo-fi Factory — Web Control Panel

A NiceGUI web app that wraps the existing `run.py` / `publish.py` pipeline:
connect YouTube in-browser, generate + upload videos, manage live streams, run
lofi-inator, browse history, and configure yt-dlp cookies — with live logs.

It **shells out** to the same CLI commands you already use, so there is no
duplicated pipeline logic.

```
python webui.py        # serves on WEBUI_HOST:WEBUI_PORT (default 127.0.0.1:8080)
```

## One-time setup

### 1. Set a password (required)
The panel controls your live channel and is exposed publicly via the tunnel, so
a password is mandatory. In `.env`:
```
WEBUI_PASSWORD=something-strong
PUBLIC_BASE_URL=https://lofi.yourdomain.com   # your Cloudflare Tunnel hostname
```
`WEBUI_SECRET` was already generated for you (keeps you logged in across restarts).

### 2. Create a **Web** OAuth client (required for tunnel login)
Your current `client_secret.json` is a **Desktop** client — Google only allows
loopback redirects for those, which can't work through a public tunnel URL.

1. Google Cloud Console → APIs & Services → Credentials → **Create credentials →
   OAuth client ID → Web application**.
2. Under **Authorized redirect URIs**, add exactly:
   ```
   https://lofi.yourdomain.com/youtube/callback
   ```
   (the Settings tab shows this exact string for your `PUBLIC_BASE_URL`).
3. Download the JSON and replace `client_secret.json` in the repo root.
4. Add your Google account as a **Test user** on the OAuth consent screen
   (or publish the app).

The Settings tab warns you while a Desktop client is still in place.

### 3. Expose it with Cloudflare Tunnel
```
cloudflared tunnel --url http://127.0.0.1:8080
# or a named tunnel mapped to lofi.yourdomain.com
```
Point the tunnel hostname at `WEBUI_HOST:WEBUI_PORT`.

### 4. (Optional) yt-dlp cookies for audio downloads
YouTube bot-gates server IPs, so lofi-inator **audio covers** need cookies.
Export a Netscape `cookies.txt` from a browser logged into YouTube and upload it
in the **Settings** tab. Without it, the trending scrape still works (metadata
only) and audio covers fall back to MIDI generation.

## Running as a service (auto-start)

Everything is wired through systemd **user** services (no root for the app) plus
a Cloudflare named tunnel. One installer does the mechanical parts:

```
bash deploy/setup.sh
```

It is idempotent and:
1. installs `cloudflared` to `~/.local/bin` (if missing),
2. installs + enables `lofi-webui.service` (auto-restart, starts at boot),
3. enables user lingering (`sudo loginctl enable-linger` — boot without login),
4. once you've run `cloudflared tunnel login`, creates the `lofi` tunnel, writes
   `~/.cloudflared/config.yml`, routes DNS, and enables `cloudflared-lofi.service`.

Manual bits it can't do for you:
- **`~/.local/bin/cloudflared tunnel login`** — opens a browser, pick your domain.
- Set `PUBLIC_BASE_URL` in `.env` to the hostname you'll use, then re-run setup.sh.

Handy commands:
```
systemctl --user status  lofi-webui cloudflared-lofi
systemctl --user restart lofi-webui            # after editing .env
journalctl --user -u lofi-webui -f             # live logs
journalctl --user -u cloudflared-lofi -f
```

Unit files live in `deploy/` and are copied to `~/.config/systemd/user/`.

## Tabs
| Tab | What it does | Underlying command |
|-----|--------------|--------------------|
| Generate | Render a video, optionally upload | `run.py --skip-upload` / `publish.py auto` |
| Upload | Upload the latest rendered video | `publish.py upload` |
| Live | Start / end / status of live stream | `publish.py live` / `end` / `status` |
| lofi-inator | Trending → lofi cover → upload | `publish.py lofi-inator` |
| History | Past uploads from `upload_log.json` | (read-only) |
| Settings | YouTube connect, redirect URI, cookies | OAuth + cookie upload |
