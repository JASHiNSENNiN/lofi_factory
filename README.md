# lofi_factory

An automated lofi-music YouTube pipeline: generates original lofi tracks
(procedural MIDI composition, no sampling of existing recordings), renders
atmospheric background video, assembles a full video, and uploads it to
YouTube on a daily schedule — or streams live 24/7. No AI/LLM calls by
default; the generative core (Euclidean rhythms, Markov chord/melody
chains, genetic-algorithm voice-leading, Perlin/Gray-Scott visuals) is
entirely procedural. LLM calls (Groq/Gemini) exist only as an explicit
opt-in failsafe — see [Environment variables](#environment-variables).

## Quick start

```bash
python -m venv venv
venv/bin/pip install -r requirements.txt   # + requirements-dev.txt for tests
cp .env.example .env                        # fill in the keys you need — see below
python run.py --skip-upload --duration "1 hour"
```

Requires **Python 3.10+**, **ffmpeg**, and **FluidSynth** on `PATH` (all
three are what actually render/encode a track — nothing here works without
them). On Debian/Ubuntu:

```bash
sudo apt install python3-venv python3-dev build-essential ffmpeg fluidsynth libsndfile1
```

## Running it

```bash
python run.py                          # full pipeline, random theme, 2hr video
python run.py --theme winter_snow      # specific theme
python run.py --duration "1 hour"      # specific duration
python run.py --skip-upload            # generate only, don't upload
python run.py --music-v2               # use the GA-voice-leading music engine (beta)
python scripts/stream_live.py          # 24/7 live stream instead of a single upload
```

`publish.py auto` is what the daily scheduled run actually invokes — see
[DEPLOYMENT.md](DEPLOYMENT.md) for the systemd timer that runs it, and
`python publish.py --help` for the full CLI (auto-service control, one-off
uploads, the non-systemd cron fallback).

## Environment variables

All read from `.env` in the repo root. Nothing here is required to generate
tracks locally (`--skip-upload`) — the LLM keys and YouTube credentials
only matter once you're actually uploading or streaming.

| Variable | Required for | Notes |
|---|---|---|
| `YT_STREAM_KEY` | live streaming | YouTube RTMP stream key (fallback path — see `scripts/youtube_live_manager.py` for the API-managed alternative) |
| `YT_CHANNEL_ID` | upload/analytics | |
| `LOFI_LLM_FAILSAFE` | — | Set to `1` to allow Groq/Gemini calls as a fallback when the procedural generators fail. **Unset by default** — the pipeline is fully procedural without it. |
| `GROQ_API_KEY`, `GEMINI_API_KEY`, `GEMINI_API_KEY_BACKUP` | LLM failsafe only | Ignored unless `LOFI_LLM_FAILSAFE=1` |
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` | `lofi_inator` cover-song metadata lookup | Optional |
| `YTDLP_COOKIES` | trending-topic scraping | Optional, path to a cookies file |
| `LOFI_STREAM_ALERT_WEBHOOK` | live streaming | Optional Slack/Discord-compatible webhook, pinged after repeated stream reconnect failures |
| `WEBUI_PASSWORD` | web control panel | **Mandatory** if you run `webui.py` — it's exposed publicly via the Cloudflare tunnel in `deploy/setup.sh` |
| `WEBUI_SECRET` | web control panel | Session-cookie signing key; auto-generated per boot (logs everyone out on restart) if unset |
| `WEBUI_HOST`, `WEBUI_PORT` | web control panel | Default `127.0.0.1:8080` |
| `PUBLIC_BASE_URL` | web control panel OAuth | The public hostname reached through the Cloudflare tunnel, e.g. `https://lofi.example.com` — used to derive the Google OAuth redirect URI |

## Testing

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
python -m pytest              # fast suite (default), 138+ tests
python -m pytest -m slow      # + full-resolution Gray-Scott / production-scale tests
```

See [tests/](tests/) — covers the algorithmic core (Euclidean rhythms,
Markov generation, GA voice-leading, noise fields, quality gate) directly;
audio rendering and video encoding aren't covered here since they need
FluidSynth/ffmpeg on the actual deploy target, not this dev environment.

## Deploying

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for the VPS setup runbook
(`deploy/setup.sh`, systemd services, day-2 operations).

## Project layout

- `run.py` — the core pipeline (visual → music → SEO → thumbnail → assemble → upload)
- `publish.py` — CLI wrapper: one-off runs, the daily `auto-service`, upload management
- `scripts/generate_music_gemini.py` / `generate_music_v2.py` — procedural MIDI composers (v2 adds GA voice-leading, better humanization)
- `scripts/visual_v2/` — procedural background video generation (noise fields, particles, post-FX)
- `scripts/lofi_fx.py` — Pedalboard-based audio FX chain (vinyl crackle, tape wobble, stereo widening, sub-bass saturation)
- `scripts/stream_live.py` — 24/7 live-stream mode
- `scripts/lofi_inator/` — optional cover-song-inspired track generation (procedural DNA extraction, no audio scraping)
- `webui/` — NiceGUI-based web control panel
- `deploy/` — systemd units + setup script
- `tests/` — pytest suite for the algorithmic core
