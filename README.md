# lofi_factory

An automated lofi-music YouTube pipeline: generates original lofi tracks
(procedural MIDI composition, no sampling of existing recordings), renders
atmospheric background video, assembles a full video, and uploads it to
YouTube on a daily schedule — or streams live 24/7. No AI/LLM calls by
default; the generative core (Euclidean/cellular-automata rhythms, Markov
and L-system melodic generation, functional-harmony progressions via
`music21`, genetic-algorithm/simulated-annealing voice-leading with
species-counterpoint rules, Perlin/Gray-Scott visuals) is entirely
procedural — no neural nets, nothing trained on a corpus. LLM calls
(Groq/Gemini) exist only as an explicit opt-in failsafe — see
[Environment variables](#environment-variables).

The channel-growth side is similarly procedural/statistical rather than
black-box: a Thompson Sampling bandit picks concept pillars, durations,
title variants, and thumbnails; a two-proportion z-test gates thumbnail
swaps; CUSUM flags viral moments; `statsmodels` forecasts 7/30-day views.
See `scripts/analytics.py`, `scripts/bandit.py`.

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
python run.py --music-v2               # GA/simulated-annealing voice-leading + species counterpoint
python scripts/stream_live.py          # 24/7 live stream instead of a single upload
python publish.py shorts <video.mp4>   # auto-clip a 9:16 highlight and upload as a Short
python publish.py playlist create "<title>" --confirm-create   # explicit, confirmed playlist creation
```

`publish.py auto` is what the daily scheduled run actually invokes — see
[DEPLOYMENT.md](DEPLOYMENT.md) for the systemd timer that runs it, and
`python publish.py --help` for the full CLI (auto-service control, one-off
uploads, Shorts, playlist management, the non-systemd cron fallback).

The web control panel (`python webui.py`) also has a **content calendar**
page (scheduled + past uploads, batch queue add/reorder/cancel) alongside
the existing analytics/automation views.

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
| `HARMONY_ENGINE_ENABLED` | — | Default on. Set to `0` to disable the `music21`-based functional-harmony progression source (falls back to the original 51-entry table + Markov chain only) |
| `CROSSPOST_ENABLED` | Shorts cross-posting | **Off by default.** TikTok/IG Reels have no free first-party upload API for this use case — enabling this without wiring a real provider just raises a clear error instead of faking an upload. See `crosspost()` in `scripts/generate_shorts.py` |
| `YT_PLAYLIST_TEMPORAL`, `YT_PLAYLIST_ACTIVITY`, `YT_PLAYLIST_EMOTIONAL`, `YT_PLAYLIST_AESTHETIC`, `YT_PLAYLIST_CROSS_GENRE` | playlist auto-curation | Pillar → playlist-ID mapping (data-driven, replaces the old duration-only table). Falls back to legacy `YT_PLAYLIST_STUDY`/`YT_PLAYLIST_SLEEP` per-pillar if unset, so migration is incremental — see `scripts/playlist_curation.py` |

## Testing

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
python -m pytest              # fast suite (default), 450+ tests
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
- `publish.py` — CLI wrapper: one-off runs, the daily `auto-service`, upload/Shorts/playlist management
- `scripts/generate_music_gemini.py` / `generate_music_v2.py` — procedural MIDI composers (v2 adds GA/simulated-annealing voice-leading with species-counterpoint rules, better humanization)
- `scripts/harmony_engine.py` — `music21`-based functional-harmony/Roman-numeral progression generation
- `scripts/visual_v2/` — procedural background video generation (noise fields, particles, post-FX)
- `scripts/lofi_fx.py` — Pedalboard-based audio FX chain (vinyl crackle, tape wobble, stereo widening, sub-bass saturation, per-track LUFS mastering, optional kick→bass sidechain ducking)
- `scripts/track_quality.py` — MIDI-structural gates + audio-domain gates (clipping/silence/LUFS/spectral balance) on the rendered WAV
- `scripts/stream_live.py` — 24/7 live-stream mode
- `scripts/generate_shorts.py` — auto-clips a 9:16 highlight from the assembled video and uploads it as a Short
- `scripts/analytics.py` / `scripts/bandit.py` — longitudinal analytics, A/B significance testing, Thompson Sampling bandit, CUSUM change-point detection, forecasting
- `scripts/posting_time.py` — recommends posting hour/day from historical upload+view data
- `scripts/playlist_curation.py` — pillar-based playlist auto-assignment
- `scripts/lofi_inator/` — optional cover-song-inspired track generation (procedural DNA extraction, no audio scraping)
- `webui/` — NiceGUI-based web control panel (analytics dashboard, content calendar, automation controls)
- `deploy/` — systemd units + setup script
- `tests/` — pytest suite for the algorithmic core
