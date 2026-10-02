# lofi_factory — Code Audit

Audit of `main` at `2a0baeb` (81 commits, ~45k lines of Python excluding `research/`).
Written to be fixed against, not to be nice. Every finding names a file and
line so it can be checked. Where something is inferred rather than proven, it
says so.

**Method:** read the pipeline end to end (run → music → visuals → assemble →
upload → analytics → web panel → deploy), ran the full test suite (1002 pass,
4 deselected as slow), ran `ruff` over the non-test code, generated 22 tracks
with the real composer to measure length and register, generated 300 real
titles and their thumbnail text, rendered thumbnails and a background frame
and looked at them, and cross-checked the committed runtime logs in `assets/`
against the code that writes them.

**Severity**
- **P0** — breaks the product's core promise, or risks the channel/account.
- **P1** — real bug that corrupts output, loses data or wastes the box.
- **P2** — design flaw, dead code, misleading docs; costs time later.
- **P3** — hygiene and cleanup.

---

## Verdict

The pipeline runs, and the tests are real. That's the good news.

The bad news:

1. **"No AI" is false.** Six AI code paths ship in the repo, two of them
   ignoring the opt-in flag, and one exists specifically to hide AI art.
2. **The output is far less than it claims.** A daily upload is 1 hour long
   (the encode budget forces it), built from ~16 minutes of unique music
   repeated four times, over a 60-second visual loop. Most of the
   "growth engine" (duration bandit, watch-time weighting) never runs in
   production.
3. **What viewers see is broken.** 40% of thumbnails show a phrase cut off
   mid-sentence ("LOFI HIP HOP FOR"), 1 in 6 titles say "lofi hip hop"
   twice, the on-screen now-playing text scrambles word order, and every
   uploaded video shows a fake "LIVE" badge.
4. **Disk cleanup never runs in production**, and the live stream and
   renders share one `music/` folder that several things delete from.
5. **A "jazz" video isn't jazz.** Only the first track follows the chosen
   sub-genre; the rest are random picks from all 26.
6. **The analytics are statistics cosplay.** "Thompson Sampling" isn't, the
   "A/B test" compares different videos, and the KPI is biased against
   long videos. The thumbnail swap can never find its alternate image.
7. **Channel-risk features:** "lofi cover" titles for songs that aren't in
   the video, "no ads" claims on a channel built for ad revenue,
   anti-bot evasion, and an "undetectable" AI-background module.
8. **The codebase grew by accretion, not design:** 4,400-line files,
   226 blanket `except Exception`, comments that narrate past sessions
   instead of explaining code, and no CI.

---

## 1. AI in a "no AI" codebase (P0)

The README says "AI is trash. Algorithm is art." and that LLMs exist "only as
an explicit opt-in failsafe". Neither holds.

| ID | Where | What | Gate |
|---|---|---|---|
| AI-1 | `scripts/visual_v2/ai_background.py` (656 lines) | Pollinations.ai text-to-image backgrounds | `--ai-bg` (`run.py:166`); **ignores `LOFI_LLM_FAILSAFE`** |
| AI-2 | `scripts/generate_seo.py:1619`, `run.py:162` | Ollama `llama3.2` rewrites descriptions | `--use-ollama`; **ignores `LOFI_LLM_FAILSAFE`** |
| AI-3 | `scripts/generate_music.py` (`print_colab_code`) | Prints a Facebook **MusicGen** Colab notebook | `--music-mode colab` |
| AI-4 | `generate_seo.py`, `trend_research.py`, `lofi_inator/extract.py`, `generate_music_gemini.py:2976`, `publish.py:914,992` | Groq Llama-3.3-70B and Gemini calls | `LOFI_LLM_FAILSAFE=1` |
| AI-5 | `webui/app.py:2610` | UI switch that writes `LOFI_LLM_FAILSAFE=1` | — |
| AI-6 | `requirements.txt` | `groq`, `google-generativeai` installed unconditionally | — |

**AI-7 — The "failsafe" isn't a failsafe.** `pick_concept()`
(`generate_seo.py:1298`) has a docstring saying the procedural pool "is
primary and always used". The code calls Gemini, then Groq, **first**, and
only falls back to the pool if both fail. `publish.py:914` and `:992` do
the same with live titles: `build_title_groq(...) or title` overwrites the
procedural title every time the flag is on. With the flag set, the LLM is
primary, and the docs lie about it.

**AI-8 — The MusicGen hypocrisy.** `generate_music.py`'s docstring brags
that local MusicGen was removed because it "contradicted the project's
stated no-neural-nets design". Fifty lines later, the same file prints
MusicGen code for Colab.

**AI-9 — `ai_background.py` is built to hide AI art.** Its docstring:
"Strategy for an undetectable faceless lo-fi channel", a pipeline that
"strips AI sheen", and overlays placed so "any residual AI artifact is
buried". That is the opposite of the project's stated values, and a
liability if YouTube's disclosure rules ever tighten.

**AI-10 — The main composer is named after an AI it doesn't use.**
`generate_music_gemini.py` is the procedural engine. The name is a fossil,
and it's imported by name from 8+ places.

**AI-11 — The commit history shows AI authorship.** Commit `7eb5c30` is
titled "Finish the design-token migration the overhaul agent didn't
reach". `.gitignore` lists `.claude/`, `.playwright-mcp/` and
`.codebase-memory/`. `bandit.py` cites "the task writeup". 41 comments
reference "this session", "gap #N" or research docs. If "no AI" is meant
to cover how the code was written too, the history disagrees. If it isn't,
the comments still need rewriting (see ARCH-6).

**Fix:** Delete AI-1 through AI-6 outright: the module, the flags, the env
vars, the UI toggle and the two packages. Rename `generate_music_gemini.py`
to `composer.py`. Add a CI grep that fails on `groq|genai|ollama|pollinations|musicgen|audiocraft`.

---

## 2. Output quality: what actually gets uploaded (P0)

**OUT-1 — A daily upload has ~16 minutes of unique music.**
- `publish.py auto` picks the duration from the measured encode speed
  (`_dynamic_max_safe_duration`, `publish.py:337`). The committed
  `assets/.encode_speed_history.json` shows ~0.5x realtime. With the 4-hour
  systemd timeout: `(14400 − 2400) × 0.75 × 0.5 = 4500 s` → **"1 hour"**.
- `run.py:133` assigns **4 tracks** to "1 hour". Measured median track
  length: **~4 minutes** (22 tracks generated; range 122–737 s).
- `pick_music_files()` (`assemble_video.py:72`) shuffles once, then loops
  the same order until the time is filled.
- Result: the same four songs, same order, about four times, over a
  60-second visual loop. Manual "2 hours" renders are ~33 minutes of music
  played 3.5 times; "10 hours" is ~2 hours played 5 times.

**OUT-2 — The duration strategy is dead code in production.**
`DURATION_WEIGHTS` ("Weighted for MAXIMUM WATCH TIME… 8h/10h catch overnight
sleepers", `run.py:126-130`) and the analytics `duration_weights()` bandit
only run when `run.py` is called **without** `--duration`. `publish.py auto`
always passes one (`publish.py:382-383`). The unattended channel never
uses either.

**OUT-3 — Every video is fully re-encoded to burn in a few overlays.**
`apply_vhs_grade()` (`assemble_video.py:580`) pushes the full duration
through `showfreqs` EQ bars, a gaussian-blur glow, a full-frame temporal
`noise` filter, two `drawbox` progress bars and two `drawtext` timestamps,
at 8 Mbps for 720p. That's why encoding runs at 0.5x realtime and why
OUT-1 caps videos at 1 hour. The full-frame grain also burns bitrate that
YouTube's own re-encode turns to mush.
*Fix direction:* drop the per-frame grain. Render the EQ overlay at low
resolution and scale it up, or drop it. Use `-c:v copy` on a pre-encoded
loop wherever nothing on screen is audio-reactive.

**OUT-4 — Track lengths are erratic.** 122 s to 737 s across one
sample. A 12-minute lofi loop is a bug, not a feature.

**OUT-5 — The audio chain is lossy twice and inconsistent.**
- `concat_audio()` (`assemble_video.py:113`) encodes MP3 at 192k, then
  `apply_vhs_grade` re-encodes it to AAC at 192k.
- Loudness handling depends on length: under 30 min gets `loudnorm`,
  30–60 min gets `dynaudnorm`, over 60 min gets nothing.
- The concat demuxer is fed mixed `.mp3/.wav/.flac/.ogg` (`:83`), but it
  requires identical stream parameters.

**OUT-6 — Wrong length when a track is bad.** The playlist is sized to the
target duration, *then* `concat_audio()` drops unreadable or <10 s tracks.
The audio comes out short, and the fade starts at `target − 5`, past the
new end, so the video stops dead with no fade.

**OUT-7 — The fallback silently reuses old or placeholder audio.** With no
`force_files`, `pick_music_files()` globs all of `music/`. That includes
earlier uploads' tracks, the live stream's library, and silent `--mode mock`
placeholders. This is reused content uploaded without a warning.

**OUT-9 — A chosen sub-genre applies to one track only.**
`_build_diverse_params()` (`generate_music_gemini.py:4206`) builds track 0
from `pick_params(genre_hint=...)`, then gives every other track a
**different, random** sub-genre from all 26 (`sub_pool` excludes only the
anchor's genre). Picking "jazz_cafe" in the web panel gets one jazz track
plus, say, phonk, sleep_lofi and lofi_house. The title, thumbnail and
burned-in genre badge all describe track 0 only. Its docstring still says
"call pick_params (Groq or random)".

**OUT-10 — The audio "quality gate" never rejects anything.** After
rendering, `score_audio_quality()` (`generate_music_gemini.py:4179`) scores
clipping, silence, loudness and spectral balance, prints the result,
appends it to a log, and ships the track regardless of the score. It's a
logger named like a gate.

**OUT-8 — `DURATION_MAP.get(label, 7200)`** (`assemble_video.py:757`):
an unknown label silently becomes a 2-hour render instead of an error.

---

## 3. Live stream vs. daily render: they destroy each other (P0/P1)

**LIVE-1 — Shared `music/` folder, several deleters.** *(Corrected in
round 2: `run.py`'s prune only runs on a bare CLI upload — see DISK-1.)*
- The stream keeps a **150-track** library in `music/`
  (`stream_live.py:354`) and prunes to 150 itself (`:358`).
- A bare `python run.py` that uploads by itself prunes `music/*.wav` to
  the **10** newest (`run.py:106-107`). Run during a stream, it deletes
  ~140 files the stream's ffmpeg playlist still references. It also
  leaves the `.meta.json` sidecars behind as orphans.
- The web panel's scratch cleanup deletes every `track_*.wav`, including
  the whole stream library (JOB-6).
- The web panel allows a stream and a render at the same time (separate
  `slot`s in `webui/jobs.py`). Each daily render's tracks land in the
  stream's library and get played there too, so the same music ships on
  both the stream and the uploads.

**LIVE-2 — The playlist refresher is dead code, and the comments
contradict each other.** `_start_playlist_refresher()`
(`stream_live.py:326`) rewrites the concat list every 60 s, and its
docstring says "ffmpeg's -reload 1 … picks up the updated file". The
ffmpeg command at `:600` says "no -reload flag — not supported". The
concat demuxer parses the list once at open, so new tracks are never
heard until ffmpeg restarts. The rewrite is also non-atomic (`open('w')`),
so a reconnect at the wrong moment reads a truncated playlist.

**LIVE-3 — "Now playing" is fiction.** `_start_track_monitor()` (`:286`)
runs its own wall clock over its *own* reshuffled copy of the list. After
the first pass, and after any ffmpeg reconnect, the on-screen title and
the actual audio have nothing to do with each other.

**LIVE-4 — The warm-up can spin forever.** `while _count() < _RADIO_MIN_TRACKS`
(`:408`) has no attempt limit. If `generate_track` keeps failing (missing
soundfont, FluidSynth gone), the stream never starts and the loop never
ends.

**LIVE-5 — Comment says `threads=2`, code says `threads=4`** (`:628-629`).
Comments that lie about tuning numbers are worse than no comments.

**LIVE-6 — No lock between stream and render.** `stream_live.py` doesn't
take `.pipeline.lock`. On the stated i3-7100U (2 cores), a real-time
stream encode, background track generation and a 0.5x-realtime daily
render all compete. Expect a stuttering stream. (Inferred from the code
and hardware notes; not observed live.)

**LIVE-7 — Disk use.** 150 uncompressed WAVs at ~40 MB each is ~6 GB.

---

## 4. Job runner and web panel bugs (P1)

**JOB-1 — Cancel sends a false failure alert.** `JobManager.cancel()`
(`webui/jobs.py:321`) terminates the process. `_pump()` (`:272`) sees exit
code −15, marks the job **failed**, writes failed history and fires the
alert. Only then does `cancel()` set "cancelled". Evidence: the committed
`assets/alerts_log.jsonl` contains "exited with code -15".

**JOB-2 — Cancel leaves ffmpeg and FluidSynth running.** SIGTERM goes to
the `run.py` PID only. `run.py` has no signal handler, and the job isn't
started in its own process group (`start_new_session=True` is missing),
so ffmpeg and FluidSynth children keep writing. Evidence: four
"clean_orphaned_scratch" runs in two days freeing ~1.6 GB
(`assets/admin_audit.jsonl`). The cleanup button treats the symptom.

**JOB-3 — Unreferenced task.** `asyncio.create_task(self._pump(job))`
(`jobs.py:269`) discards the handle. The event loop holds tasks weakly,
so they can be garbage-collected mid-run.

**JOB-4 — Job IDs collide.** `f"{name}-{int(time.time())}"`: a retry
within the same second reuses the ID.

**JOB-5 — The queue can lose data.** `JobQueue._load()` (`jobs.py:389`)
swallows a JSON error and starts empty. The next `_save()` overwrites the
file, and every pending item is gone.

**JOB-6 — Scratch cleanup has a race.** `_confirm_clean_scratch()`
(`webui/app.py:2835`) checks "busy" when the dialog **opens**, not when
"Clean up" is **clicked**. It doesn't check the stream slot, or a manual
CLI `run.py`. `clean_orphaned_scratch()` deletes **every**
`track_*.wav`, not just orphans, including the live stream's whole
library. The `.pipeline.lock` flock is the real "is something rendering?"
signal and it isn't consulted. Failed runs' `output/tmp_*` folders
(holding hour-long `merged.mp4` files, kept "for inspection") are never
cleaned by anything.

**JOB-7 — Dead UI line.** At `webui/app.py:832`, the bare expression
`thumb_status` does nothing; the label renders outside the button row it
was meant to join.

**JOB-8 — `.env` handling** (`webui/config.py:146-184`):
- `write_env_value()` truncates and rewrites `.env` in place: a crash
  mid-write wipes every secret. Use a tmp file and `os.replace`.
- The file is created with the default umask, then `chmod 0600` runs
  afterwards, so it's world-readable for a moment.
- Values aren't quoted. In python-dotenv, ` #` starts a comment in an
  unquoted value, so a password like `abc #1` is saved as `abc`.
- `read_env_file()` doesn't strip quotes, so `KEY="1"` reads back as
  `"1"` and the UI toggle shows "off" while the pipeline sees "on".

**JOB-9 — Manual renders ignore the encode budget.** The web panel offers
"2 hours" and "3 hours" with no timeout. At 0.5x, a 3-hour render occupies
the box for 6+ hours and blocks the daily timer's run via the lock.

---

## 5. Security (P1)

**SEC-1 — The public login has no rate limiting.** `webui/auth.py` uses
one shared password with no attempt counter or lockout, exposed to the
internet through Cloudflare, and it controls a live YouTube channel. Put
Cloudflare Access in front of it, or add a lockout.

**SEC-2 — Non-ASCII passwords crash the login.** `hmac.compare_digest(str, str)`
raises `TypeError` for non-ASCII input, which shows up as a 500 error
instead of "wrong password". Compare `.encode()`d bytes.

**SEC-3 — Sessions die on restart.** `STORAGE_SECRET` is random per boot
unless `WEBUI_SECRET` is set (`config.py:69`), and `setup.sh` never sets
it.

**SEC-4 — `setup.sh` downloads `cloudflared` "latest" with no checksum**,
then runs it as a persistent service.

**SEC-5 — Backups are a folder on the same disk** (`backups/`, holding
`token.json` and `.env` in plain text). They protect against a bad edit,
not against losing the box. Fine as long as it's labeled honestly; the
UI calls it "backup".

The web UI's async handlers were checked for blocking calls; none found.
Credit where due.

---

## 6. Analytics: statistics cosplay (P1)

**STAT-1 — It isn't Thompson Sampling.** `_bandit_weights()`
(`analytics.py:524`) takes each arm's posterior **mean**, divides it by the
pooled mean, clamps it to [0.5, 2.0], and feeds `random.choices`. No
posterior sample is ever drawn, which is the defining step of Thompson
Sampling. `bandit.py`'s `select_arm`/`sample_all` exist but the
production path doesn't use them.

**STAT-2 — The "Jeffreys-ish prior Beta(1,1)" (`bandit.py:13`)** is the
uniform/Laplace prior. Jeffreys is Beta(0.5, 0.5).

**STAT-3 — The thumbnail "A/B test" compares different videos.**
`swap_low_ctr_thumbnails()` (`analytics.py:1038`) z-tests **one video's**
CTR against **all other videos'** pooled CTR. Different topics, ages,
traffic sources and durations, so the test doesn't measure the thumbnail.
It also runs one test per video at p < 0.05 with no
multiple-comparison correction, so ~5% of videos get "significant"
swaps by chance alone.

**STAT-4 — The KPI is biased against long videos.**
`composite_engagement_score()` (`analytics.py:424`) weights
`watch_ratio = avgViewDuration / duration` at 40%. An 8-hour video can
never score like a 30-minute one, so any bandit fed this score
learns "short wins" regardless of the truth.

**STAT-5 — No age normalization.** `latest_metrics()` compares a
3-day-old video against a 60-day-old one directly.

**STAT-6 — Too many bandits, too little data.** Pillar, duration, title
strategy, thumbnail, sub-genre, BPM bucket and engine all learn from the
same ~1 video/day, each needing only `min_samples=5`. The arms are
confounded with each other. This is noise-chasing.

**STAT-7 — A "beta" engine is in production.** `run.py:306-318` lets the
bandit coin-flip between v1 and the generator its own log message calls
"v2 (beta)".

**STAT-8 — Verify the CTR unit (unproven).** All code and tests treat
`videoThumbnailImpressionsClickRate` as a fraction (0.05). If the API
returns a percentage (5.0), then `successes = ctr * impressions`
exceeds trials, the z-test becomes nonsense, and the clamp pins CTR at
1.0 in the KPI. Check one real API response and add a test for it.

**STAT-9 — The feedback loop never runs on a `setup.sh` deploy.**
`deploy/setup.sh` doesn't install `lofi-analytics.timer` or
`lofi-cert-renew.timer`, and neither DEPLOYMENT.md nor the README mention
them. The web UI tells the user swaps run "automatically with the daily
analytics sync (lofi-analytics.timer)" (`webui/app.py:1632`). On a fresh
deploy, that's false: no analytics sync and no thumbnail swaps, so every
bandit stays at its cold-start default forever.

---

## 7. Channel and policy risk (P0)

**POL-1 — "Covers" that aren't covers.** `lofi_inator/seo.py:15-33`
generates titles like "{title} · lofi cover", "{artist} — {title} ·
lo-fi", "{title} slowed + reverb". The "DNA" behind it
(`lofi_inator/models.py`) is a BPM, one of **8** keys, a mood word and a
progression index. Path B (Spotify `/audio-features`) has been closed to
new apps since Spotify's Nov 2024 API change, which the code itself notes
(`lofi_inator/discover.py:30,201`) yet still calls. So in practice, unless
a bitmidi scrape hits, the DNA comes from path C: **keywords in the song
title**. The video contains nothing of the named song. That's
misleading metadata built on artist names, exactly what YouTube's
spam/deceptive-practices policy targets. It also invites "not a cover"
reports. (Commit `719f140` claimed to fix lofi-inator's legal risk; the
titles survived.)

**POL-2 — False claims in descriptions.**
- `generate_seo.py:759,773` says "no ads. no interruptions." on a channel
  whose own code optimizes for "ad revenue + YPP progress"
  (`run.py:127`). Once the channel is monetized, YouTube inserts mid-rolls
  into long videos.
- `:329` says "recorded in a bedroom": nothing is recorded.

**POL-3 — Mass-produced content.** Unattended daily uploads, a looped
60-second visual, ~16 minutes of music repeated (OUT-1), templated
titles, and a 24/7 stream with auto-refreshed titles. That's the profile
YouTube's inauthentic / mass-produced content rules demonetize. This
matters more than any feature in the repo.

**POL-4 — Scraping and evasion.**
- `trend_research.py:275` uses `extract_flat` because it "dodges
  YouTube's 'confirm you're not a bot' gate on server IPs", and
  `YTDLP_COOKIES` can attach a logged-in Google account to the scraping.
  If that's the channel's own account, it's the account at risk. The
  official YouTube Data API is already used in the same module (`:171`),
  which makes the scraping redundant.
- `lofi_inator/extract.py:160` scrapes bitmidi.com (user-uploaded MIDI
  transcriptions of copyrighted songs) with the User-Agent
  `"educational music research"`. A monetized channel isn't educational
  research. It also takes the first search result blindly, so the "DNA"
  is often from the wrong song.

**POL-5 — Shorts are broken visually.** `build_vertical_clip()`
(`generate_shorts.py:172`) center-crops 1280×720 to 9:16. That keeps
x≈437–842, and the now-playing panel spans x=513–1240
(`visual_v2/config.py:28-30`). The title text is sliced in half, the
total-time label disappears, and a 405 px strip is upscaled 2.7x to
1080×1920. The "highlight" is chosen by loudest RMS, which in lofi is
noise, since a mastered lofi track has a nearly flat loudness envelope.

---

## 8. Architecture and code quality (P2)

**ARCH-1 — God files.**
- `scripts/generate_music_gemini.py`: 4,414 lines, 94 functions;
  `build_midi()` alone is 418 lines (`:3668`).
- `webui/app.py`: 3,400 lines.
- `publish.py`: 1,813 lines.
- `generate_seo.py`: 1,686 lines.

**ARCH-2 — Two composers instead of a refactor.** `generate_music_v2.py`
(1,387 lines) is a parallel copy, not an evolution, so every fix needs
doing twice or drifts.

**ARCH-3 — A circular import held together by a lazy import and a
docstring warning** (`genre_presets.py:13-16, 170`).

**ARCH-4 — Two control panels.** `dashboard.py` (terminal UI, launched by
`./lofi`) and `webui/` overlap. Pick one.

**ARCH-5 — Swallowed errors everywhere.** 226 `except Exception` blocks
outside tests, 29 of them bare `pass`. This is *why* the Gemini path was
dead without anyone noticing (DEAD-1). In an unattended pipeline, failures
that only show up as quietly worse output are the worst kind.

**ARCH-6 — Comments narrate history instead of explaining code.** About
17% of the composer is comment lines. Many are change-logs ("Confirmed
2026-08-13…", "previously this was…", "new research this session", "gap
#1"). That belongs in commit messages. Several comments now contradict
the code (LIVE-2, LIVE-5, AI-7).

**ARCH-7 — Stale duplicated catalogs.** `lofi_inator/extract.py:35`
`_VALID_KEYS` lists 8 keys; the composer has 15 (`KEY_ROOTS`,
`generate_music_gemini.py:972`). `_VALID_SUBGENRES` (`:44`) lists 24
and is missing drill, world, garage, synthwave and others. Copy-pasted
lists drift; import the source of truth.

**ARCH-8 — Over-engineering where it can't be heard.** Genetic-algorithm
voice-leading, simulated annealing, species counterpoint, L-systems,
Indian gamaka and tala overlays, and "truck driver" key modulation, all
feeding a genre whose identity is a looped four-chord groove. Key changes
in particular are close to un-lofi. There's no listening test or
blind-preference check anywhere proving any layer improves the result.
Meanwhile OUT-1 (one song repeated four times) goes unaddressed.

**ARCH-9 — Commits mix unrelated changes.** "Composition-quality round 4"
touches SEO, analytics, 10 genre YAMLs, an impulse-response WAV and the
trend cache. That makes bisecting and reverting impossible.

---

## 9. Dead and broken code (P2)

**DEAD-1 — The Gemini code can't run.** `requirements.txt` installs
`google-generativeai`. The code imports `from google import genai`
(`trend_research.py:313`, `generate_seo.py:1010`), which comes from the
separate `google-genai` package. Verified in a clean venv: `ImportError`.
It's caught and returns `None`, so it has never worked. Delete it with
the rest of section 1.

**DEAD-2 — The playlist refresher** (LIVE-2) and the duration
weighting/bandit (OUT-2).

**DEAD-3 — Ruff findings:** 37 unused imports, 33 f-strings with no
placeholders, 16 unused variables, star-import names in the composer
(`GM_*`, F405), a duplicate `ImageFont` import (`visual_v2/postfx.py:122`),
and the useless expression (JOB-7).

**DEAD-4 — `generate_music.py` mock/colab modes.** Mock is test-only;
colab is AI (AI-3). Move mock into `tests/` and delete the rest.

---

## 10. Smaller bugs (P2/P3)

- `upload_youtube.py:148` cuts descriptions at 4,900 **characters**;
  YouTube's limit is 5,000 **bytes**, so emoji or CJK text can still be
  rejected. YouTube also rejects `<` and `>` in descriptions; nothing
  strips them.
- `assemble_video.py:143`: concat list entries are written as
  `file '{path}'` without escaping single quotes.
- `get_audio_duration()` returns `0` on failure and gets called again on
  every loop pass in `pick_music_files()`.
- The auto-state file (`publish.py:298`) and several other JSON state
  files are written in place, not atomically.

---

## 11. Repo hygiene and ops (P3)

- **Runtime state is committed:** `assets/admin_audit.jsonl`,
  `alerts_log.jsonl`, `trend_cache.json` (128 KB, churned by unrelated
  commits), `.auto_run_state.json`, `.vaapi_status.json`,
  `.encode_speed_history.json`, `lofi_inator_log.json`, plus a debug
  screenshot `fixed_calendar.png` at the repo root. Untrack them and add
  them to `.gitignore`.
- **The repo is heavy:** 70 MB of `assets/` (soundfonts, IRs) in git;
  `.git` is 81 MB. Use Git LFS or a download step.
- **File names with spaces** in `assets/ir/` break naive shell use.
- **The systemd units hard-code `/home/jashin/lofi_factory`** (every unit
  in `deploy/`), and `setup.sh` copies them verbatim. Use `%h` (as
  `cloudflared-lofi.service` already does) or template them.
- **`setup.sh` hard-codes port 8080** in the tunnel ingress, even though
  `WEBUI_PORT` is configurable.
- **No CI** (no `.github/`), no pre-commit, no linter config, no
  `pyproject.toml`. The 1,002 tests only run when someone remembers.
- **No lockfile:** all 25 requirements are `>=`. An overnight release of
  `yt-dlp`, `nicegui` or `pedalboard` can break the 00:00 run.

---

## 12. Titles, thumbnails and on-screen text (P0/P1)

Measured by generating 300 titles with the real pool (`pick_concept_from_pool`
+ `build_title`) and running each through the thumbnail's text function,
then rendering thumbnails and a background frame and looking at them.

**TXT-1 — 40% of thumbnails show a broken fragment.**
`_derive_short_title()` (`generate_thumbnail_cozy.py:179`) takes everything
after the first " · ", then cuts at the last whole word that fits. It never
checks what's left. 120 of 300 ended on a dangling word or punctuation
(a conservative count). Real outputs:
`'lo-fi hip hop ·'`, `'lo-fi hip hop,'`, `'1 hour straight of'`,
`'chillhop roots, 1'`, `'lofi · dead of'`, `'lofi hip hop for'`,
`'chill lofi beats to'`. The last two were rendered and appear on the
thumbnail in 80-pixel capitals.

**TXT-2 — The titles themselves are keyword salad.**
- 50 of 300 contain "lofi hip hop"/"lo-fi hip hop" twice:
  `'lofi hip hop · lo-fi hip hop, space station light, side project open — 1 hour'`.
- "lofi lofi" appears outright: `'1 hour of neo soul lofi lofi for essay writing'`.
- Random activity slots produce `'wedding planning beats for chill, study'`
  and `'minecraft cozy light, grad school open'`.
- 6 of 300 claim "no loop", on a video that plays the same 4 tracks four
  times (OUT-1).
- 29 of 300 titles were exact duplicates of another.

**TXT-3 — The on-screen "now playing" text scrambles word order.**
`draw_now_playing()` (`visual_v2/scene.py:298`) loops over the words and
appends each one to line 1 *whenever it still fits*, even after an earlier
word overflowed to line 2. Rendered result for "cyberpunk cafe · neon rain
and coffee made by a robot": line 1 "cyberpunk cafe · neon **by**", line 2
"rain and coffee made a…". Words are moved out of order, and the title is
burned into every frame of the video.

**TXT-4 — Every uploaded video shows a fake "LIVE" badge.** `draw_header()`
(`visual_v2/scene.py:382`) draws a pulsing red dot and "LIVE" on the
background loop used for regular uploads, not just the stream. Claiming a
pre-recorded video is live is misleading to viewers.

**TXT-5 — The on-screen clock is the render time, frozen into a loop.**
The header clock is `datetime.now()` at render time, in the server's time
zone. In a 1-hour video built from a 60-second loop, it shows the same
minute and jumps back every 60 seconds.

**TXT-6 — "Now playing" is one title for the whole video.** The track
title is baked into the 60-second background loop (`run.py:270-280`) from
the concept's mood line, before the music is even generated. Four tracks
play under one fixed title. The genre badge also comes from the concept's
*guess*, so a video can say "lo-fi hip hop" over bossa or phonk (OUT-9).

**TXT-7 — Thumbnail design defects** (seen in rendered output):
- The accent underline runs through the bottom of the title glyphs and
  reads as a strikethrough.
- A stray `*` sits above every title: the ✦ deco mark was replaced with an
  asterisk (`generate_thumbnail_cozy.py:897`).
- "1 HOUR" appears twice (badge and subtitle), and the subtitle "LOFI ·
  1 HOUR" adds nothing.
- The "listener" silhouette is a black blob on a near-black background; it
  reads as a tombstone with headphones. The coffee cup is black on black
  too.
- Overall very dark, heavy grain, nothing that reads at YouTube's small
  grid size.
- The RNG seed uses `hash(theme_name)`, which Python randomizes per
  process, so "same (theme, variant) always renders the same layout" is
  false for the decorative elements.

**TXT-8 — Two channel names.** The video says "Lofi Streams"
(`visual_v2/config.py:62`); the thumbnail watermark says "LOFI FACTORY".
The second also tells viewers, in plain words, that this is a factory.

**TXT-9 — Default upload metadata is risky.** `publish.py:827-828`: when
no SEO file is found, the title becomes "lo-fi beats to study/relax to 🌙",
a near-copy of Lofi Girl's signature title, and the description becomes
"No copyright. Free to use." That grants anyone the right to reupload the
channel's music, and "no copyright" is legally wrong.

---

## 13. OAuth and the YouTube API (P1)

**API-1 — The "monetary analytics" connect flow is broken.**
`monetary_authorization_url()` (`webui/youtube_oauth.py:210`) doesn't save
the PKCE code verifier that google-auth-oauthlib 1.5 generates
automatically. `monetary_handle_callback()` builds a fresh `Flow` with no
verifier, so Google rejects the code exchange ("Missing code verifier").
The main flow had exactly this bug, fixed it, and documented the fix in a
comment 100 lines up (`:124-130`); the fix was never copied to the
monetary flow. Its tests (`tests/webui/test_youtube_oauth_monetary.py`)
replace `Flow` with a fake, so they pass.

**API-2 — The "read-only" monetary token is a full-power token.**
`MONETARY_SCOPES = SCOPES + [...]` (`webui/config.py:55`), and the consent
uses `include_granted_scopes`. `token_monetary.json` carries full YouTube
management rights (upload, delete, edit), despite the comments calling it
a separate opt-in that "never silently upgrades" anything. That's two
full-power tokens on disk instead of one.

**API-3 — The OAuth state check can be skipped.** `handle_callback()`
(`youtube_oauth.py:122`) only rejects a *mismatched* state:
`if _pending_state and state and state != _pending_state`. A callback with
**no** state, or one arriving after a restart (when `_pending_state` is
`None`), is accepted. A logged-in admin opening a crafted callback link
would link someone else's YouTube account to the pipeline. Require the
state to be present and equal. Same in the monetary flow (`:226`).

**API-4 — Scope lists are duplicated in four files** (`webui/config.py`,
`scripts/upload_youtube.py`, `scripts/analytics.py`,
`scripts/youtube_live_manager.py`). They will drift.

**API-5 — Every live title update erases the stream description.**
`LiveTitleUpdater._run()` (`youtube_live_manager.py:381`) calls
`liveBroadcasts().update(part="snippet")` with only the title and start
time. With `part=snippet`, the YouTube API deletes any snippet property
not included, so the description is wiped on every track change. (The
midnight refresh in `publish.py:1012` does include it.)

**API-6 — The live stream eats the daily API quota.** Its own comment
(`youtube_live_manager.py:37`) works out "720/day × 50 units = 36,000",
against a default quota of 10,000 units/day, and waves it off with "live
streams rarely run 24h straight". This one is a 24/7 stream. Once the
quota is spent, the daily upload, thumbnail set and analytics sync all fail
for the rest of the day. The titles it pushes come from the wrong-song
monitor (LIVE-3) anyway.

**API-7 — `"frameRate": "15fps"`** (`youtube_live_manager.py:179`).
YouTube's documented values for `cdn.frameRate` are `30fps`, `60fps` and
`variable`. If the API rejects this, the managed-broadcast path fails and
the stream falls back to the bare stream key. *(Unverified against the live
API.)*

**API-8 — Each upload's duplicate check costs 100 quota units**
(`search().list`, `publish.py:790`) and only looks at the 50 newest
videos.

**API-9 — Manual uploads pair files by "newest".** `publish.py upload`
without explicit paths takes the newest video, the newest `seo_*.json`
(`load_seo`, `:131`) and the newest `thumb_*.jpg` (`:819`) independently.
An `_alt` thumbnail or a web-panel thumbnail regeneration is "newer", so
a video can go up with another video's title and thumbnail.
`find_latest_valid_video()` (`:115`) also **deletes** any video shorter
than 10 minutes, including one a concurrent render is still writing.

---

## 14. Disk and file lifecycle (P1)

**DISK-1 — Production never cleans up.** `_cleanup_old_files()`
(`run.py:74`) is only called when `run.py` itself uploaded (`run.py:535-536`).
The daily timer runs `publish.py auto`, which runs `run.py --skip-upload`
and uploads separately; the web panel does the same. Neither ever prunes.
Every day leaves behind:
- the uploaded video (~3.6 GB for 1 hour at 8 Mbps),
- the track WAVs (~40 MB each), plus their `.meta.json` files,
- the background loop, thumbnails and SEO files.

A 100 GB disk fills in roughly a month. The "Clean up scratch" button and
the disk-usage panel exist because of this.

**DISK-2 — The thumbnail swap can never find its alternate image.**
Even where cleanup does run, it keeps only the 5 newest `thumb_*.jpg`
(primary and `_alt` together, so about 2.5 videos' worth). The swap only
looks at videos 7–30 days old (`analytics.py:1097`). By then the `_alt`
file is long gone, and the swap quietly skips every video. So the
"A/B" feature (STAT-3) is dead twice over.

**DISK-3 — `--skip-visual` picks an arbitrary old background**:
`visuals[0]` from an unsorted glob (`run.py:288`), not the newest.

**DISK-4 — `append_upload_log()`** (`publish.py:139`) resets to an empty
list on any JSON error and then overwrites the file. One corrupt write and
the entire upload history, which every analytics feature reads, is gone.

---

## 15. Round 3: everything else (P1/P2)

Rendered 6 full tracks through FluidSynth and the FX chain (4 v1, 2 v2) and
measured them, rendered a full 60-second background loop and checked its
seam, ran the suite under coverage, and read the remaining modules.

**R3-1 — The money paths are the untested ones.** Coverage is 52% overall,
but it's concentrated on the composer (86–87%) and the FX chain (90%).
What actually touches YouTube is barely tested:
`youtube_live_manager.py` 0%, the whole `lofi_inator/` package 0%,
`upload_youtube.py` 11%, `stream_live.py` 12%, `webui/app.py` 8%,
`assemble_video.py` 31%. 357 mock/monkeypatch uses across 76 test files;
API-1 shows what that hides.

**R3-2 — The audio is technically clean but static.** All six tracks sat
at −16.9 LUFS (one at −18.7) with no clipping, so the mastering works. But
loudness varies only 1.6–3.2 dB (10th–90th percentile of 3-second windows)
across a whole track. The "storytelling tension arc" and section-transition
features are close to inaudible at the level of the mix. One track
(lofi_garage) ran **13.4 minutes** (OUT-4). True peak reached −0.4 dBTP on
one track; the AAC encode will push that over 0 dBTP (YouTube asks for
−1). Every track scored a perfect 1.00 on the built-in gate (OUT-10).

**R3-3 — Track titles are word-bank salad**: "Iterating beyond that
pulse", "Hum along latency", "Untethered grief, porous ozone". These are
what the live stream shows as "now playing" and pushes into the broadcast
title (API-5).

**R3-4 — The music21 "harmony engine" doesn't use music21 to generate
anything.** `generate_functional_progression()` (`harmony_engine.py:181`)
walks hand-written tables. music21 is only called by
`validate_roman_numerals()` and `realize_numeral_pitches()`, which nothing
in production calls. The README's "functional-harmony progressions via
music21" is false, and the project ships a 115 MB dependency that adds
~0.26 s of import time to every track for nothing.

**R3-5 — The drum kit is 8 sounds, two of them duplicated.**
`assets/drums/` has 10 files, but `ch-lofi.wav` and `hi-hat-closed-01.wav`
are byte-identical, and so are `oh00-lofi.wav` and `open-hat-01.wav`. All
26 "genres" share one closed hat, one open hat (cut at 250 ms, so it never
rings open), 3 kicks and 3 snares.

**R3-6 — Bundled assets are missing their licenses.**
- `BebasNeue-Regular.ttf` is under the SIL Open Font License, which requires
  the license text to travel with the font. It isn't in the repo.
- `MuseScore_General.sf3` (MIT) needs its copyright notice included; it
  isn't. `GeneralUser_GS.sf2` has its own license; also absent.
- The drum samples are described as "CC0 from Boochi44" only in a code
  comment.
- The Voxengo IR license (`assets/ir/license.txt`, condition 4b) allows
  redistribution only of **complete and unaltered** copies of the archive.
  The repo ships 3 of its files.

**R3-7 — The background clock runs at render speed.** Confirmed in a
rendered 60-second loop: the header clock reads 23:41 on the first frame
and 23:50 on the last, because it's `datetime.now()` sampled during a
9-minute render. In the final video it races forward 9 minutes every
minute, then jumps back (TXT-5).

**R3-8 — `--visual-seed` doesn't reproduce renders.** The Gray-Scott vs.
noise background choice uses the global, unseeded `random`
(`visual_v2/static_layers.py:50,53`), not the visual seed. The flag's help
text promises "use to reproduce a specific render". Gray-Scott is also
picked only 12% of the time and then mostly covered by UI panels and a
vignette; the README's "Perlin/Gray-Scott visuals" oversells it.

**R3-9 — The background render is slow and huge.** 60 seconds of 720p
took **9 minutes** to render on this machine (Python/PIL compositing every
frame) and produced a **116 MB** intermediate file (15.5 Mbps), which is
then re-encoded twice more (OUT-3). Music notes pop in and out at the loop
seam.

**R3-10 — The documented terminal dashboard crashes on install.**
`dashboard.py` imports `textual` and `rich`; neither is in
`requirements.txt`. `./lofi`, documented in `DEPLOYMENT.md:118`, dies with
`ModuleNotFoundError` on a fresh venv. The file hasn't been touched since
the initial commit.

**R3-11 — Four schedulers, and the docs point to one that doesn't exist.**
A systemd timer, `publish.py auto --loop`, `publish.py cron install`, and
the dashboard's toggles all schedule the same job. Nothing stops cron and
systemd from both running a daily upload. The cron help text says "Prefer
'auto-service install'", but `auto-service` has no `install` action
(`publish.py:1753`). The cron entry doesn't quote the repo path.

**R3-12 — Two opposite playlist policies.** `playlist_curation.py` insists
that creating a public playlist must never happen without an explicit
`confirm=True` from a human. `lofi_inator/registry.py:153` creates a public
playlist silently, and creates another one whenever its cache file goes
missing or corrupt. The curated playlists are keyed on internal SEO buckets
("temporal", "cross_genre") that mean nothing to viewers.

**R3-13 — Posting-time advice is noise presented as a finding.**
`posting_time.py` says it refuses to "dress up a guess as a finding", then
recommends a "best hour" from **3** total samples (`MIN_SAMPLES = 3`), with
single-sample hours allowed. It ranks by total views without adjusting for
video age, so older uploads win. It uses the time the upload *finished*
(hours after the 00:00 timer fires), not the publish time. And since the
timer always fires at the same hour, nearly all data points share one hour.

**R3-14 — The web panel still asks for Google login cookies for a removed
feature.** The Settings card says "Upload a Netscape cookies.txt … no
cookies.txt — downloads fall back to MIDI" (`webui/app.py:2577-2598`). The
only code that used cookies for downloads, `ytdlp_util.download_opts()`,
has no callers. Uploading a logged-in Google session to an
internet-exposed box, for nothing, is a bad trade.

**R3-15 — Alerting is off, and was off for the one recorded failure.**
`assets/alerts_log.jsonl` shows the only logged failure with
`"sent": false, "configured": false`. Alerts are opt-in, `setup.sh` never
asks for a destination, the variable is named `LOFI_STREAM_ALERT_WEBHOOK`
even though it carries every alert, and `notify_auto_failure.py` silently
returns when it's unset. Its docstring says it must work "even if the venv
or app modules are in a bad state", but it imports the `webui` package and
`apprise` from that same venv.

**R3-16 — Comments mention other "agents".** `posting_time.py`'s docstring
says analytics is "owned by a separate agent", and lists schema doubts
"this worktree can't verify". These are leftovers from how the code was
generated, not documentation.

---

## 16. What's actually good

So the fix work keeps these:

- 1,002 passing tests on the algorithmic core.
- `fcntl.flock` pipeline lock (`run.py:44`).
- systemd timers with `MemoryHigh`/`MemoryMax` and a failure-notify unit.
- The encode-speed-aware auto duration, which is a sound idea; it just
  exposes OUT-3.
- The ffmpeg stall watchdog and the VAAPI auto-fallback.
- Path-traversal checks on backup names and the thumbnail swap.
- No secrets anywhere in git history.
- The web UI runs blocking work through `asyncio.to_thread`.

---

## Fix plan

Order matters: stop the damage first, then fix the output, then clean up.

### Phase 0 — Stop the bleeding (one sitting)
1. Delete every AI path and dependency (section 1). Add a CI grep guard.
2. Separate folders: `music/stream/` for the stream library and
   `music/render/<run-id>/` per daily run. Each pruner touches only its
   own folder (LIVE-1).
3. Fix cancel: `start_new_session=True` on the job subprocess,
   `os.killpg` on cancel, set a `cancel_requested` flag that `_pump`
   checks before marking failed or alerting (JOB-1, JOB-2).
4. Remove the "no ads", "recorded in a bedroom", "no loop" and "Free to
   use" copy, the default Lofi Girl-style title, and the "LIVE" badge on
   uploads (POL-2, TXT-2, TXT-4, TXT-9).
5. Make cleanup run after every successful upload, whoever uploads
   (DISK-1). Store the `_alt` thumbnail with the upload record, not in
   the pruned folder (DISK-2).
6. Stop "cover"/"slowed + reverb"/artist-name titles in lofi_inator, or
   disable lofi_inator entirely (POL-1).
7. Login lockout or Cloudflare Access (SEC-1); fix `compare_digest`
   on bytes (SEC-2).
8. Require a present, matching OAuth state (API-3). Send the full snippet
   on live title updates, or stop updating titles (API-5, API-6).

### Phase 1 — Make the uploads worth watching
1. Rework the encode (OUT-3) until a 2-hour render fits the budget.
2. Generate enough music for the duration, with no repeats: target
   unique-music ≥ 90% of video length, and assert it before upload (OUT-1).
3. Clamp track length to a sane range (OUT-4).
4. One audio encode, one loudness strategy for every length, uniform
   inputs before concat (OUT-5).
5. Size the playlist *after* validation, and fail loudly instead of
   falling back to globbing `music/` (OUT-6, OUT-7).
6. Fix Shorts: compose a real 9:16 layout instead of center-cropping
   (POL-5).
7. Keep every track in a video in the chosen sub-genre (OUT-9). Make the
   audio quality gate reject and regenerate (OUT-10).
8. Fix thumbnail text: refuse fragments that end on a function word or
   punctuation, de-duplicate genre words in titles, and add a test that
   runs 1,000 generated titles through both (TXT-1, TXT-2).
9. Fix the now-playing word wrap; drop the burned-in clock; make "now
   playing" either real (per track) or remove it (TXT-3, TXT-5, TXT-6).
10. One channel name everywhere (TXT-8).

### Phase 2 — Honest analytics or none
1. Pick at most two levers (e.g. title strategy, thumbnail) and turn off
   the rest.
2. Either do real Thompson Sampling (sample, argmax) or rename it to
   what it is (STAT-1, STAT-2).
3. Replace the cross-video z-test with YouTube Studio's built-in
   "Test & Compare", or delete it (STAT-3).
4. Normalize the KPI by duration and video age (STAT-4, STAT-5).
5. Verify the CTR unit with a real API response (STAT-8).
6. Install the analytics timer in `setup.sh`, or remove the UI claim
   (STAT-9).
7. Retire v2 or v1; don't coin-flip a beta in production (STAT-7).

### Phase 3 — Structure
1. Split the composer into harmony / melody / drums / arrangement /
   render modules; merge v1 and v2 into it (ARCH-1, ARCH-2), which also
   removes the circular import (ARCH-3).
2. Split `webui/app.py` per view. Delete `dashboard.py` or the web UI
   (ARCH-4).
3. Replace blanket `except Exception` with specific exceptions and
   logging. Anything left must log the traceback (ARCH-5).
4. Rewrite comments to explain *why the code is the way it is*; move the
   history into commit messages (ARCH-6).
5. Import catalogs from one source of truth (ARCH-7).
6. Freeze new composition features until there's a listening test
   (ARCH-8).

### Phase 4 — Hygiene and ops
1. Untrack runtime state; extend `.gitignore` (section 11).
2. Add CI: ruff, pytest and the AI-grep guard on every push.
3. Add a lockfile (`pip-tools` or `uv lock`).
4. Template the systemd units; checksum `cloudflared`; set `WEBUI_SECRET`
   in `setup.sh`.
5. Atomic writes for every JSON state file and `.env` (JOB-5, JOB-8).

---

## Not covered

- **Listening quality.** The music was measured (length, register, MIDI
  structure), not judged by ear. Pitch registers looked sane across the
  10 sampled keys.
- **`generate_music_v2.py`** internals (1,387 lines) beyond its shared
  quality-gate and engine-selection code, and two rendered tracks.
- **`webui/stats.py` and `webui/data.py`** beyond a skim.
- **Anything needing the deployed box or a real account:** live streaming,
  VAAPI, real YouTube API responses (STAT-8, API-7).

---

## Fix status (after the fix commits on this branch)

**Fixed:** every AI/LLM path (section 1, plus a guard test); the music
findings (wrong voicings, V chords as maj7, melody/chord key mismatch on
tracks 2+, semitone clashes, near-silent melody, intro bass offset, key
changes, track length, drum layer over every section, quality gate,
true peak, genre hopping); OUT-1, OUT-4–8; LIVE-1–5, LIVE-7; JOB-1–9;
SEC-1–4; API-1–7, API-9; STAT-1–5, STAT-7–9 (STAT-8 handled defensively);
POL-1, POL-2, POL-4, POL-5; TXT-1–9; DISK-1–4; DEAD-1–4; R3-3, R3-4,
R3-5, R3-6 (except below), R3-7, R3-8, R3-10–R3-16; repo hygiene
(runtime state untracked, CI, lockfile, portable units).

**Partly fixed:**
- OUT-3: film grain removed and bitrate lowered, but the audio-reactive EQ
  overlay still forces a full re-encode of every video.
- STAT-6: two dead bandits removed (duration, engine); pillar/title/
  sub-genre/BPM weighting remains and still learns from ~1 video a day.
- R3-6: MuseScore_General's MIT license text still has to be added next
  to the soundfont (see assets/soundfonts/README.md).

**Not fixed:**
- ARCH-1–3, ARCH-5: the 4,000-line composer, v1/v2 duplication, the
  circular import, and ~220 blanket `except Exception` blocks.
- ARCH-6: only the comments narrating AI sessions were rewritten; the
  change-log style comments remain.
- LIVE-6: no lock between the live stream and a render.
- API-8: the duplicate check still costs 100 quota units per upload.
- POL-3: daily unattended uploads of generated music remain what the
  channel is; the inauthentic-content risk is a product decision.
- SEC-5: backups still live on the same disk.
- Section 10: description byte limit and `<`/`>` stripping.
- Listening tests: the music was measured, not judged by ear.

## Round 4: clicking through the web panel

Every page was opened and every button clicked by a browser script,
during a real render started from the command line.

**Found and fixed:**
- WEB-1: "End stream" ran in the same slot as the stream and was refused
  while a stream was running, so the panel could never end one. End and
  Status now have their own slot.
- WEB-2: `publish.py end` logged in to YouTube before stopping ffmpeg, so
  without a valid token the stream kept running. It now stops ffmpeg
  first, and only after checking the stored PID still belongs to ffmpeg.
- WEB-3: a network error while refreshing the YouTube token deleted
  `token.json`. Only a rejected token is removed now.
- WEB-4: without a token, headless runs (timer, panel jobs) started an
  interactive login server and waited forever. They now exit with a
  message; panel jobs get no stdin.
- WEB-5: the render dialog offered 3 hours and "all night", which don't
  finish in time, defaulted to 2 hours, and offered an "Auto
  (bandit-selected)" composer that no longer exists. A `.env` default
  outside the list made the dialog fail to open.
- WEB-6: "Sync now" blocked the server for the whole sync, said "synced"
  when nothing was fetched, and a missing token killed it with
  `sys.exit` inside the web server.
- WEB-7: channel stats and the device-code login polled YouTube on the
  event loop, freezing the panel for every user.
- WEB-8: file names and video IDs were pasted into raw HTML unescaped.
- WEB-9: a render started outside the panel showed as "idle"; New render,
  sample delete and render delete didn't check for it.
- WEB-10: the System page's three resource bars were stacked on one line,
  the disk chart lumped the stream library in with render scratch, and
  the scratch cleaner called every render track "orphaned".
- WEB-11: failed "status"/"end" clicks sent failure alerts, and a failed
  job's summary showed its last line instead of its error line.
- WEB-12: Settings said changes need a restart (they don't), and render
  defaults really did need one. Copy on Analytics, Settings and
  Automation was rewritten without file names and statistics jargon.
- MUS-1: every track in a video had the same title phrase. Now only the
  first carries the concept; the rest get their own.
- VID-1: the video's progress bar was full from the first frame. It was
  drawn with `drawbox`, where `t` means box thickness, not time. It now
  uses `geq`/`overlay`, which see the frame time. The elapsed time
  printed milliseconds ("00:15:00.000") and didn't match the total's
  format; both now read MM:SS, or H:MM:SS from an hour up.
- VID-2: the channel name appeared twice (header and corner watermark).
- VID-3: the spectrum showed bass only; amplitude is now log-scaled.

A full 30-minute render (`run.py --skip-upload --duration "30 min"`)
completed: 9 tracks, 30:00.0 exactly, 720p24, −17.9 LUFS, LRA 2.4 LU.

## Round 5: whole-project re-check

### Fixed

**Leaks and safety**
- KEY-1: `publish.py live` printed the first 50 characters of the RTMP URL,
  which is 18 of the stream key's 24 characters, into job logs the panel
  stores and shows. `stream_live.py` echoed ffmpeg error lines verbatim, and
  ffmpeg names the full URL on connection errors. Both redact now, and every
  panel job line is redacted before it is stored.
- MEM-1: renders started from the panel ran inside `lofi-webui.service`'s
  cgroup, capped at 768M, while a render needs gigabytes (the scheduled
  unit allows 4G). Under systemd each panel job now runs in its own scope
  with its own limit (`WEBUI_JOB_MEMORY_MAX`, default 4G).
- AUTH-1: `CF-Connecting-IP` was trusted from any client, so anyone reaching
  the panel directly could send a new fake address with every guess and
  never hit the per-client lockout. It is now trusted only from loopback,
  where cloudflared connects.
- AUTH-2: sessions never ended, even after a password change. Sessions now
  carry a fingerprint of the password; changing it logs everyone out.
- TEST-1: the test suite rewrote the real `music/.params_history.json`,
  which steers what the next real video picks. Found by snapshotting file
  times around a full test run; that was the only leak.

**Unattended runs**
- AUTO-1: `cmd_upload` refuses with `sys.exit`, which `except Exception`
  doesn't catch. Failed uploads were never recorded (so the
  fall-back-to-a-lighter-tier logic never triggered), a duplicate (exit 0)
  skipped cleanup, and in `--loop` mode one refusal ended the loop.
- AUTO-2: `run.py` exited 0 after a failed upload ("Upload skipped (auth not
  set up yet)").
- CLI-1: `--skip-music` could never work: an empty track list was taken as
  "use only these tracks". `--skip-visual` reused the newest visual of any
  theme while the thumbnail used another.
- CLI-2: `--schedule-at` with an offset (`+02:00`) produced an invalid
  timestamp, and times in the past were sent to YouTube.

**Metadata honesty** (what every upload says about itself)
- META-1: chapters were invented: keyword phrases at fixed fractions of the
  video ("so a single upload can rank for multiple long-tail queries"),
  unrelated to where tracks change. The assembler now records the real
  track order and start times, and the description gets a tracklist that
  YouTube turns into chapters.
- META-2: the scene line was template mad-libs. Most descriptions read like
  "The wherever you are at summer night hits different" or
  "2am. A any room. Your meditation. This." It is now built from whole
  phrases, and season-specific times only appear in that season.
- META-3: tags were stuffed by design ("fill the full 500-char budget"):
  every video carried other genres' tags (phonk, dark, jazz, chillhop) and
  claims like "study music that actually works" and "calm music for
  anxiety and stress"; up to three of other channels' trending tags were
  copied in through a filter that passed anything containing "music". Now
  at most 15 tags, all about this video.
- META-4: false or broken copy: "New lo-fi drops weekly", "No algorithm. No
  playlist filler.", "freshly composed for this upload" (not true for
  reused tracks), a comment calling the visible ref ID "invisible", a
  leading blank line, duplicate hashtags, generic hashtags that named the
  wrong genre, mood lines cut mid-word, and titles like "1 hour to
  meditation". The description now says plainly that the music comes from
  the channel's own composing software, with CC0 drum samples.
- META-5: a "minecraft cozy" aesthetic put a game's trademark into titles
  and tags of videos unrelated to Minecraft.

**Music**
- MUS-2: tracks of one video repeated progressions (3 of 9 tracks shared
  one); only the previous track was checked. Now the least-used of several
  candidates is taken.
- MUS-3: the "self-referential" melody Markov table was built from absolute
  pitch classes of melodies in different keys, so its nudges were noise.
  It now works in scale degrees relative to each track's key.
- MUS-4: the composer's history files were rewritten unlocked and
  non-atomically by three render threads at once.

**Docs**
- DOC-1: the README said "no sampling of existing recordings" (the drums are
  CC0 recordings) and presented v2-only features as the core.

### Not fixed (decisions or larger work)
- The premise. A box that uploads machine-composed videos daily, with
  titles, thumbnails and copy generated from templates, is what YouTube's
  "inauthentic/repetitious content" monetization policy is written about.
  The code can't fix that.
- 29 "sub-genres" are mostly a BPM range, a drum-pattern list, a scale and
  a GM piano program. `lofi_garage` runs at 66–76 BPM (UK garage is
  ~130); "nujabes" is a real artist's name used as a preset label.
- Thumbnails: dark gradient, a featureless mannequin figure, and big text.
  The A/B "alternate" only changes layout, so the swap test measures little.
- Two unrelated live systems: the panel's Live page drives `publish.py live`
  (loop one finished video), while `run.py --stream` runs `stream_live.py`
  (24/7, generating music). They don't share state, and the panel can't see
  the second.
- Three separate alert paths (`webui/alerts.py`, `stream_live._send_alert`,
  `scripts/notify_auto_failure.py`).
- The OAuth token carries the full `youtube` scope (can delete videos) and
  is copied unencrypted into `backups/`.
- 30 failed logins lock everyone out for 15 minutes (already-logged-in
  sessions keep working).
- Trend research spends 400–800 API quota units every 6 hours and now only
  reorders four keywords in titles.
- Dependencies far heavier than their use: statsmodels for one exponential
  smoothing, audiomentations for one convolution, librosa for one stretch.
- Dead code: `bandit.select_arm`, `analytics.engine_weights`,
  `binarize_above_median`, `harmony_engine.validate_roman_numerals`,
  `realize_numeral_pitches`, `postfx.draw_watermark`, `stats.list_replies`,
  `data.latest_video`, `trend_research.compute_trend_deltas`, among others.
- The panel's first page loads still make cached-but-blocking YouTube calls.

## Round 6: the weak but fixable parts

- Close-cousin genres separated (research/genres.md): study is sparse and
  half-time with a sparse melody; morning is acoustic (steel-string guitar,
  side-stick and shaker pattern U); cozy cafe is a brushed trio (acoustic
  piano, nylon lead, upright, ride); summer is tropical (steel drums, son
  clave and conga pattern V); chill beats is half-time; bedroom pop is a
  straighter drum machine; hip-hop lofi is the tighter, faster end; anime
  lofi gets the "royal road" IV-V-iii-vi (#48, new #60). New YAML field
  `melody_density`.
- Thumbnails: an illustrated room (window with the theme's view, lamp-lit
  desk, mug/plant/books/headphones, sometimes a cat) replaces one small
  silhouette on a dark gradient. The old scene-slot code was removed.
- Live: `stream_live.py` (24/7) writes `stream_state.json`; the Live page
  shows either kind of stream, can start a 24/7 stream, and ends it by
  signalling that process (PID checked). Fixed a real bug on the way:
  SIGTERM only set a flag the encoder loop never read, so a stopped 24/7
  stream kept running and its broadcast was never ended.
- One alert path: `stream_live` now sends through `webui/alerts.py`.
- Panel never waits on YouTube while building a page: comments and
  retention load asynchronously; channel/traffic/subscriber/revenue/
  engagement caches are refreshed in the background every 90 s.
- Dependencies: statsmodels, librosa and audiomentations removed (27 fewer
  packages), replaced by ~30 lines of numpy/scipy; the IR convolution is
  byte-identical to the old output.
- Dead code removed (engine_weights, select_arm, compute_trend_deltas,
  list_replies, draw_watermark, latest_video, subscribe, channel_title,
  auto_service.restart, and more).
- Security: clients that have logged in before skip the global lockout;
  backups are owner-only (0700/0600); trend research refreshes daily.
- CI compiles every file: ruff missed a syntax error introduced this round.
- `live_state.json` lives at the repo root but only `assets/live_state.json`
  was gitignored.

Still not fixable in code: the General MIDI soundfont's sound ceiling, the
YouTube repetitious-content policy, and testing uploads and streams against
a real account.

## Round 7: thumbnails and titles

- Titles (`scripts/titles.py`): three forms, each in the lofi convention
  "scene emoji [genre · length]": a hand-written scene tied to the video's
  visual theme ("rain on the window 🌧️ [lofi hip hop · 1 hour]"), a
  moment ("coding after midnight"), or the radio form ("lofi hip hop 🍂
  autumn beats to study & relax to"). 40–62 characters, keyword early,
  season-filtered (no "first snow" in July). Trends only reweight these
  phrases; they never add a word that doesn't describe the video. The old
  pattern templates (which produced "Lofi For Coding Lofi Beats To Focus")
  and the benefit-keyword extraction were removed.
- The title's scene is also the thumbnail text, so title, thumbnail and
  video loop show the same place.
- Thumbnails (`scripts/thumbnail_scene.py`): rendered at 2× and downscaled.
  One scene per image: a listener seen from behind with headphones (the
  genre's visual convention) in front of a lit window showing the theme's
  view, a desk lamp's warm pool against the cool window light, a few props,
  an optional cat on the sill, fairy lights; then bloom and split-tone
  grading (cool shadows, warm highlights). The window sits opposite the
  text card. Sources: `research/thumbnails-titles.md`.

Not done on purpose: randomising upload times to get around the
repetitious-content policy. That policy judges the videos, not the
schedule, and evading enforcement isn't something this project should do.
