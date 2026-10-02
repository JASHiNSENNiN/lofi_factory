# lofi_factory

An automated lofi-music YouTube pipeline: composes original lofi tracks
(procedural MIDI rendered through a General MIDI soundfont, with drums
layered from free CC0 one-shot samples; no existing songs are sampled),
renders a looping background video, assembles a full video, and uploads it
to YouTube on a schedule, or streams live. There are no AI or LLM calls
anywhere in the code. The default composer (`scripts/composer.py`) uses
curated and Markov-walk chord progressions, motif-based melodies, Euclidean
and pattern-table drums and a key/clash filter; the experimental v2 composer
(`--music-v2`, off by default) adds genetic-algorithm/simulated-annealing
voice-leading and L-system melodies. Nothing is trained on a corpus; the only
"learning" is a small Markov table built from the pipeline's own past
melodies. `tests/test_no_ai.py` fails the build if AI code creeps back in.

AI is trash. Algorithm is art.

The channel-growth side is similarly procedural/statistical rather than
black-box: Beta-posterior weights (from a composite engagement score at a
fixed video age) bias concept pillars, title variants and sub-genres; a
Bonferroni-corrected two-proportion z-test flags videos whose CTR is
well below the channel's and swaps in their alternate thumbnail; CUSUM
flags viral moments; simple exponential smoothing forecasts 7/30-day views. With roughly
one upload a day these signals take months to mean anything, so treat
them as weak nudges, not findings.
See `scripts/analytics.py`, `scripts/bandit.py`.

## Quick start

```bash
python -m venv venv
venv/bin/pip install -r requirements.lock   # exact tested versions (requirements.txt = ranges)
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
python run.py                          # full pipeline, random theme, 1-hour video
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
tracks locally (`--skip-upload`) — the YouTube credentials
only matter once you're actually uploading or streaming.

| Variable | Required for | Notes |
|---|---|---|
| `YT_STREAM_KEY` | live streaming | YouTube RTMP stream key (fallback path — see `scripts/youtube_live_manager.py` for the API-managed alternative) |
| `YT_CHANNEL_ID` | upload/analytics | |
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
python -m venv .venv && .venv/bin/pip install -r requirements.lock -r requirements-dev.txt ruff
python -m pytest              # fast suite (default), ~1,100 tests
python -m pytest -m slow      # + full-resolution Gray-Scott / production-scale tests
ruff check .                  # undefined names / dead imports (same gate as CI)
```

CI (`.github/workflows/ci.yml`) runs the lint gate and the full suite on
every push, including `tests/test_no_ai.py`, which fails if any AI/LLM
library or service shows up anywhere in the code, and
`tests/generate_music/test_musical_correctness.py`, which checks chord
voicings, melody/chord key agreement, clashes, melody density and track
length on generated output.

## Deploying

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for the VPS setup runbook
(`deploy/setup.sh`, systemd services, day-2 operations).

## Project layout

- `run.py` — the core pipeline (visual → music → SEO → thumbnail → assemble → upload)
- `publish.py` — CLI wrapper: one-off runs, the daily `auto-service`, upload/Shorts/playlist management
- `scripts/composer.py` / `generate_music_v2.py` — procedural MIDI composers (v2 adds GA/simulated-annealing voice-leading with species-counterpoint rules, better humanization)
- `scripts/harmony_engine.py` — table-driven functional-harmony (tonic/subdominant/dominant) progression grammar
- `scripts/visual_v2/` — procedural background video generation (noise fields, particles, post-FX)
- `scripts/lofi_fx.py` — Pedalboard-based audio FX chain (vinyl crackle, tape wobble, stereo widening, sub-bass saturation, per-track LUFS mastering, optional kick→bass sidechain ducking)
- `scripts/track_quality.py` — MIDI-structural gates + audio-domain gates (clipping/silence/LUFS/spectral balance) on the rendered WAV
- `scripts/stream_live.py` — 24/7 live-stream mode
- `scripts/generate_shorts.py` — auto-clips a 9:16 highlight from the assembled video and uploads it as a Short
- `scripts/analytics.py` / `scripts/bandit.py` — longitudinal analytics, underperformer thumbnail swaps, Beta-posterior weighting, CUSUM change-point detection, forecasting
- `scripts/posting_time.py` — recommends posting hour/day from historical upload+view data
- `scripts/playlist_curation.py` — pillar-based playlist auto-assignment
- `webui/` — NiceGUI-based web control panel (analytics dashboard, content calendar, automation controls)
- `deploy/` — systemd units + setup script
- `tests/` — pytest suite for the algorithmic core
