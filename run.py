"""
run.py — Lo-fi Factory Master Runner
=====================================
Runs the full pipeline:
  1. Generate visual (lo-fi radio interface — visual_v2 package)
  2. Generate/use music tracks
  3. Generate SEO (title, description, tags)
  4. Generate thumbnail
  5. Assemble final video  (or start live stream with --stream)
  6. Upload to YouTube (optional)

Usage:
  python run.py                          # Full pipeline, random theme, 1hr video
  python run.py --theme winter_snow      # Specific theme
  python run.py --duration "1 hour"      # Specific duration
  python run.py --skip-visual            # Skip visual gen (use existing)
  python run.py --skip-upload            # Skip YouTube upload
  python run.py --visual-seed 42         # Reproducible render
  python run.py --stream                 # Live stream to YouTube instead of upload
  python run.py --stream --stream-test   # Test stream locally (60s → output/stream_test.mp4)

Available themes:
  cozy_rain, midnight_cafe, purple_dusk, amber_night, winter_snow,
  autumn_study, spring_dawn, neon_tokyo, summer_lofi, blue_hour,
  forest_rain, sakura_night, vaporwave, lofi_house, lofi_classical,
  bedroom_pop, lofi_rnb
Available durations: "1 hour", "2 hours", "3 hours", "all night"
"""

import os
import sys
import argparse
import fcntl
import random

sys.path.insert(0, os.path.dirname(__file__))

ROOT = os.path.dirname(__file__)
_LOCK_PATH = os.path.join(ROOT, ".pipeline.lock")


def _acquire_pipeline_lock():
    """
    Refuse to start a second pipeline run while one is already in progress.
    Without this, the 24/7 auto-upload loop (lofi-auto.service) and a manual
    render from the web UI / dashboard could run concurrently — both would
    fight over GPU/CPU and could confuse the "which video is new" detection
    used when uploading. Returns the open lock file (keep it referenced for
    the lifetime of the run — closing it releases the lock).
    """
    lock_file = open(_LOCK_PATH, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("[run.py] Another pipeline run is already in progress "
              f"(lock held: {_LOCK_PATH}).")
        print("          If this is the 24/7 auto-upload loop, wait for it to finish or stop it:")
        print("          python publish.py auto-service stop")
        sys.exit(1)
    return lock_file

# Load .env if present (stream key, channel ID, etc.)
_env_path = os.path.join(ROOT, ".env")
if os.path.exists(_env_path):
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path, override=False)  # override=False: real env vars take precedence
    except ImportError:
        pass


def main():
    parser = argparse.ArgumentParser(description="Lo-fi Factory — Full Pipeline")
    from scripts.visual_v2.themes import ALL_THEMES

    parser.add_argument("--theme", choices=ALL_THEMES,
                        default=None, help="Visual theme (default: random)")
    parser.add_argument("--duration", default=None,
                        choices=["30 min", "45 min", "1 hour", "90 min",
                                 "2 hours", "3 hours", "4 hours", "5 hours",
                                 "8 hours", "10 hours", "all night"])
    # Three-state: None (default) = let the engagement-analytics engine
    # bandit (scripts.analytics.engine_weights()) choose v1 vs v2, weighted
    # by which has performed better (neutral 50/50 with no data yet).
    # --music-v2/--no-music-v2 explicitly force v2/v1, which always wins
    # over the bandit (explicit flag > auto-selection). BooleanOptionalAction
    # (not plain store_true) is what makes the "not passed at all" state
    # distinguishable from "explicitly forced off".
    parser.add_argument("--music-v2", action=argparse.BooleanOptionalAction, default=None,
                        help="Use v2 beta music generator (improved voice leading, melody, bass, humanization). "
                             "Omit to let the engagement-analytics bandit pick v1/v2 automatically; "
                             "--no-music-v2 forces v1.")
    parser.add_argument("--music-count", type=int, default=None,
                        help="Number of tracks to generate (default: enough to fill the duration without repeats)")
    parser.add_argument("--skip-visual", action="store_true",
                        help="Skip visual generation (use existing visual)")
    parser.add_argument("--skip-music", action="store_true",
                        help="Skip music generation (use existing files in music/)")
    parser.add_argument("--skip-upload", action="store_true",
                        help="Skip YouTube upload step")
    parser.add_argument("--visual-seed", type=int, default=None,
                        help="Seed for visual scene layout (random if omitted — use to reproduce a specific render)")
    parser.add_argument("--stream", action="store_true",
                        help="Live stream to YouTube instead of assembling a file")
    parser.add_argument("--stream-test", action="store_true",
                        help="With --stream: encode 60s locally instead of pushing to YouTube")
    # Lazy import: genre_presets.load_all() only globs+parses config/genres/*.yaml
    # (no soundfont-pool filesystem scan, unlike importing composer
    # at module top level) — cheap enough to pay even when --sub-genre is never
    # used, and keeps run.py's own module-level footprint unchanged.
    from scripts.genre_presets import load_all as _load_all_subgenres
    _sub_genre_choices = ["auto"] + sorted(_load_all_subgenres().keys())
    parser.add_argument("--sub-genre", choices=_sub_genre_choices, default="auto",
                        help="Force a specific sub-genre instead of letting the algorithm/concept "
                             "pick one (default: auto). See config/genres/ for the full list.")
    parser.add_argument("--mood", default=None,
                        help="Free-text mood/concept phrase override for the music generator "
                             "(default: derived from the auto-generated video concept).")
    args = parser.parse_args()

    _pipeline_lock = _acquire_pipeline_lock()  # noqa: F841 — held for the life of this run

    # Genre → preferred visual theme mapping.
    # Keeps visual world consistent with the music genre when theme not forced.
    _GENRE_THEME = {
        "lo-fi hip hop":   None,          # any theme
        "lofi jazz":       "midnight_cafe",
        "chillhop":        "cozy_rain",
        "bossa nova lofi": "summer_lofi",
        "neo-soul lofi":   "lofi_rnb",
        "lofi ambient":    "blue_hour",
        "city pop lofi":   "neon_tokyo",
        "dark lofi":       "midnight_cafe",
        # New research-driven subgenres' SEO labels (scripts/generate_seo.py
        # _SUBGENRE_TO_GENRE_LABEL) -- "lofi ambient" (sleep_lofi's label)
        # already maps to blue_hour above, so no entry needed for it here.
        # lofi_drill/lofi_world have no SEO label at all (see the comment in
        # generate_seo.py), so there was no existing pattern to check against
        # for them -- these two are added because a genuinely good visual
        # fit already exists in scripts/visual_v2/themes.py.
        "lofi garage":     "lofi_house",   # nocturnal/moody neon-blue night fits UKG-adjacent mood
        "synthwave lofi":  "vaporwave",    # 80s neon retro palette is the closest existing visual match
    }

    # Default matches what the unattended run can actually render in time
    # (see publish._dynamic_max_safe_duration).
    duration_was_set = args.duration is not None
    duration = args.duration or "1 hour"
    args.duration = duration
    from scripts.assemble_video import DURATION_MAP, tracks_for_duration
    music_count = (args.music_count if args.music_count is not None
                   else tracks_for_duration(DURATION_MAP[duration]))

    # ── TREND RESEARCH (feeds concept + title + tags) ──────────
    print("\n  Fetching trend data...")
    trends = None
    try:
        from scripts.trend_research import get_trend_snapshot
        trends = get_trend_snapshot()
    except Exception as _te:
        print(f"  [Trends] skipped ({_te})")

    # ── CONCEPT (generated once, shared by music + SEO) ────────
    print("\n  Generating video concept...")
    from scripts.generate_seo import pick_concept
    concept = pick_concept(trends)
    concept_hint = concept.get("concept") or concept.get("mood_line")
    genre_hint   = concept.get("genre_label") or ""

    # Explicit CLI overrides win over the auto-picked concept.
    if args.sub_genre != "auto":
        genre_hint = args.sub_genre
    if args.mood:
        concept_hint = args.mood

    # Theme: use --theme if set, otherwise derive from genre, else random
    if args.theme:
        theme = args.theme
    else:
        preferred = _GENRE_THEME.get(genre_hint)
        theme = preferred if preferred else random.choice(ALL_THEMES)

    print("=" * 60)
    print("  LO-FI FACTORY")
    print(f"  Theme:    {theme}")
    print(f"  Duration: {duration}{'' if duration_was_set else ' (default)'}")
    print(f"  Genre:    {genre_hint or 'lo-fi hip hop'}")
    print(f"  Concept:  {concept_hint or '(random)'}")
    print("=" * 60)

    # ── STEP 1: Music ──────────────────────────────────────────
    generated_tracks = []
    if not args.skip_music:
        print("\n[1/5] Generating music...")
        if args.music_v2 is None:
            # No explicit --music-v2/--no-music-v2 on the CLI — let the
            # engagement-analytics engine bandit choose (neutral 50/50
            # when there's no/insufficient data yet). try/except-guarded
            # the same way every other optional analytics-feedback layer
            # is (sub_genre_weights()/bpm_bucket_weights() above) — a
            # missing/corrupt analytics log must never block a render.
            try:
                from scripts.analytics import engine_weights
                _ew = engine_weights()
                use_v2 = random.choices(
                    ["v1", "v2"], weights=[_ew.get("v1", 1.0), _ew.get("v2", 1.0)], k=1,
                )[0] == "v2"
            except Exception as _eng_e:
                print(f"  [run] Engine bandit selection failed ({_eng_e}) — defaulting to v1")
                use_v2 = False
        else:
            use_v2 = args.music_v2  # explicit flag wins over the bandit
        if use_v2:
            from scripts.generate_music_v2 import generate_tracks
            print("[run] Using music generator v2 (beta)")
        else:
            from scripts.composer import generate_tracks
        generated_tracks = generate_tracks(count=music_count, concept_hint=concept_hint, genre_hint=genre_hint)
    else:
        print("\n[1/5] Skipping music generation (using existing files)")

    # Align concept genre_label + mood_line with what was actually generated.
    # pick_concept() guesses the genre up-front; the algorithm may pick a different
    # sub_genre. Read the first track's .meta.json sidecar to correct the concept.
    #
    # Also stash sub_genre/bpm/music_engine (the fields the composition
    # bandits — sub_genre_weights()/bpm_bucket_weights()/engine_weights() —
    # need to learn from) onto local vars here, the same way genre_label
    # flows through `concept` above, so they can be copied onto `seo` right
    # after generate_seo() runs and from there into upload_log.json's
    # per-video entry (see scripts/upload_youtube.py's / publish.py's
    # log-append). Defaults are the pre-existing-behavior-safe ones for
    # tracks generated before this metadata existed.
    music_sub_genre = ""
    music_bpm = None
    music_engine = "v1"
    if generated_tracks:
        import json as _json
        meta_path = generated_tracks[0] + ".meta.json"
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as _mf:
                    _meta = _json.load(_mf)
                from scripts.generate_seo import concept_from_music_params
                concept = concept_from_music_params(
                    music_sub_genre=_meta.get("genre", ""),
                    music_mood=_meta.get("title", ""),
                    base_concept=concept,
                )
                music_sub_genre = _meta.get("genre", "") or ""
                music_bpm = _meta.get("bpm")
                music_engine = _meta.get("music_engine") or "v1"
                print(f"  [SEO] Aligned to music: genre={concept['genre_label']!r} mood={concept['mood_line']!r}")
            except Exception as _e:
                print(f"  [SEO] Alignment skipped ({_e})")

    # ── STEP 2b: Visual ────────────────────────────────────────
    # Rendered after the music so its genre badge names the genre that
    # actually plays (every track in a video shares one sub-genre).
    # Derive short now-playing title + genre from the concept for the UI panel
    np_title = concept.get("mood_line") or concept.get("concept") or "lofi dreams"
    np_genre = concept.get("genre_label", "lo-fi hip hop")

    if not args.skip_visual:
        vis_secs = 60
        print("\n[2/5] Generating lo-fi visual (radio interface)...")
        from scripts.visual_v2 import generate_visual
        visual_path, theme = generate_visual(
            theme_name=theme, duration_secs=vis_secs,
            visual_seed=args.visual_seed,
            track_title=np_title, genre=np_genre,
        )
    else:
        print("\n[2/5] Skipping visual generation (using existing)")
        import glob
        visuals = glob.glob(os.path.join(ROOT, "visuals", "bg_*.mp4"))
        visual_path = max(visuals, key=os.path.getmtime) if visuals else None
        if not visual_path:
            print("  WARNING: No visual found. Assembler will generate a gradient fallback.")

    # ── STEP 3: SEO ────────────────────────────────────────────
    print("\n[3/5] Generating SEO metadata...")
    from scripts.generate_seo import generate_seo
    seo, seo_path = generate_seo(theme_name=theme, duration=duration,
                                  concept=concept,
                                  trends=trends)

    # Stash composition-selection metadata (sub_genre/bpm/music_engine) onto
    # `seo` -- the same dict pillar/duration already ride on into
    # upload_log.json -- so scripts/upload_youtube.py's / publish.py's
    # log-append can read them the same way they read seo.get("pillar", ...).
    # generate_seo() already wrote `seo` to seo_path before returning, so
    # re-dump it here too: this is the file a *separate* later
    # `publish.py upload` process (a different run, reading from disk) would
    # load, not just this in-process run's in-memory `seo` used below.
    seo["sub_genre"]    = music_sub_genre
    seo["bpm"]           = music_bpm
    seo["music_engine"]  = music_engine
    try:
        import json as _json  # may not have been imported yet (e.g. --skip-music)
        with open(seo_path, "w") as _sf:
            _json.dump(seo, _sf, indent=2, ensure_ascii=False)
    except Exception as _se:
        print(f"  [SEO] Could not persist composition metadata to {seo_path}: {_se}")

    # ── STEP 4: Thumbnail ──────────────────────────────────────
    print("\n[4/5] Generating thumbnail...")
    import time
    from scripts.generate_thumbnail_cozy import generate_thumbnail
    thumb_variant = int(time.time()) % 100
    thumb_path, thumb_title = generate_thumbnail(
        theme_name=theme,
        duration=args.duration,
        title=seo.get("title"),
        variant=thumb_variant
    )

    # Also generate a real alt variant for analytics.swap_low_ctr_thumbnails()
    # -- that feature existed but had nothing to swap to (no alt thumbnail was
    # ever produced). Different title-template variant + RNG seed so it's a
    # genuinely different candidate, not a near-duplicate. Renamed to sit next
    # to the primary thumbnail (thumb_..._alt.jpg) so publish.py's logged
    # thumb_file + "_alt" suffix finds it later without any timestamp guessing.
    try:
        alt_raw_path, _ = generate_thumbnail(
            theme_name=theme,
            duration=args.duration,
            title=seo.get("title"),
            variant=thumb_variant + 1,
        )
        alt_path = thumb_path.rsplit(".", 1)[0] + "_alt.jpg"
        os.replace(alt_raw_path, alt_path)
    except Exception as _e:
        print(f"  [THUMB] alt variant skipped ({_e})")

    # ── STEP 5: Assemble or Stream ─────────────────────────────
    if args.stream:
        print("\n[5/5] Starting live stream...")
        from scripts.stream_live import stream, build_music_list
        import tempfile, shutil
        if not visual_path:
            print("  ERROR: No visual file found. Generate one first:")
            print("    python run.py --skip-music --skip-upload")
            sys.exit(1)

        # Build YouTube setup callable (fresh broadcast per reconnect)
        yt_setup_fn   = None
        fallback_rtmp = ""
        if not args.stream_test:
            try:
                from scripts.youtube_live_manager import setup_live_stream as _yt_setup
                _theme_cap = theme
                def yt_setup_fn():
                    return _yt_setup(theme_name=_theme_cap)
            except Exception:
                pass
            if not yt_setup_fn:
                stream_key = os.environ.get("YT_STREAM_KEY", "")
                if not stream_key:
                    print("  ERROR: No YouTube credentials found.")
                    print("  Auth:  python scripts/upload_youtube.py --auth")
                    print("  Or:    export YT_STREAM_KEY='xxxx-xxxx-xxxx-xxxx'")
                    print("  Or:    python run.py --stream-test")
                    sys.exit(1)
                fallback_rtmp = f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"

        tmp_dir = tempfile.mkdtemp(prefix="lofi_stream_")
        try:
            playlist_path, tracks = build_music_list(tmp_dir)
            stream(
                visual_path=visual_path,
                playlist_path=playlist_path,
                rtmp_url=fallback_rtmp,
                theme_name=theme,
                test_secs=60 if args.stream_test else None,
                tracks=tracks,
                concept_hint=concept_hint,
                yt_setup_fn=yt_setup_fn,
            )
        except Exception as e:
            print(f"  ERROR: Stream failed: {e}")
            sys.exit(1)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        print("\n" + "=" * 60)
        print("  STREAM ENDED")
        print(f"  Theme: {theme}")
        print("=" * 60)
        return

    print("\n[5/5] Assembling final video...")
    from scripts.assemble_video import assemble
    video_path = assemble(theme_name=theme, duration_label=args.duration, visual_path=visual_path, music_files=generated_tracks)

    # ── STEP 6: Upload ─────────────────────────────────────────
    upload_ok = False
    if not args.skip_upload:
        print("\n[+] Uploading to YouTube...")
        try:
            from scripts.upload_youtube import get_authenticated_service, upload_video
            youtube = get_authenticated_service()
            video_id, url = upload_video(youtube, video_path, seo, thumb_path)
            print(f"\n✓ Live: {url}")
            upload_ok = True
            # Write upload log so analytics.py can track this upload
            import datetime as _dt, json as _json
            from scripts.fileutil import append_json_list
            append_json_list(os.path.join(ROOT, "upload_log.json"), {
                "type":             "upload",
                "video_id":         video_id,
                "url":              url,
                "title":                    seo.get("title", ""),
                "title_variants":           seo.get("title_variants", [seo.get("title", "")]),
                "title_variant_strategies": seo.get("title_variant_strategies", []),
                "title_chosen_idx":         seo.get("title_chosen_idx", 0),
                "title_chosen_strategy":    seo.get("title_chosen_strategy"),
                "pillar":           seo.get("pillar", ""),
                "concept":          seo.get("concept", ""),
                "seo_ref":          seo.get("ref_id", ""),
                "video_file":       os.path.basename(video_path),
                # Composition-selection feedback — see scripts/analytics.py's
                # sub_genre_weights()/bpm_bucket_weights()/engine_weights().
                # Defaults mirror sync_analytics()'s container-construction
                # defaults so an older-format seo dict (missing these keys)
                # never crashes this log-append.
                "sub_genre":        seo.get("sub_genre", ""),
                "bpm":              seo.get("bpm"),
                "music_engine":     seo.get("music_engine") or "v1",
                "timestamp":        _dt.datetime.now(_dt.timezone.utc).isoformat(),
            })
        except SystemExit:
            print("  Upload skipped (auth not set up yet)")
        except Exception as e:
            print(f"  Upload failed: {e}")
            print("  Video is ready at:", video_path)
    else:
        print("\n[+] Upload skipped.")

    # ── STEP 7: Cleanup old files (prevent disk fill) ──────────
    if upload_ok:
        from scripts.cleanup import cleanup_after_upload
        cleanup_after_upload(ROOT, video_path)

    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE")
    print(f"  Video:     {video_path}")
    print(f"  Thumbnail: {thumb_path}")
    print(f"  SEO:       {seo_path}")
    print(f"  Title:     {seo['title']}")
    print("=" * 60)

    # Machine-readable summary of what this run produced, for the webui's
    # JobManager to parse (see webui/jobs.py's _pump()) -- gives it an exact
    # artifact list instead of relying on stats.py's fuzzy nearest-timestamp
    # join for anything rendered from now on.
    _alt_guess = thumb_path.rsplit(".", 1)[0] + "_alt.jpg"
    _result = {
        "video": video_path,
        "thumb": thumb_path,
        "thumb_alt": _alt_guess if os.path.exists(_alt_guess) else "",
        "seo": seo_path,
    }
    print(f"[RESULT] {_json.dumps(_result)}")


if __name__ == "__main__":
    main()
