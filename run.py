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
  python run.py                          # Full pipeline, random theme, 2hr video
  python run.py --theme winter_snow      # Specific theme
  python run.py --duration "1 hour"      # Specific duration
  python run.py --skip-visual            # Skip visual gen (use existing)
  python run.py --skip-upload            # Skip YouTube upload
  python run.py --music-mode mock        # Mock music (test without GPU)
  python run.py --music-mode colab       # Print Colab code for music gen
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


def _cleanup_old_files(root: str, uploaded_video: str,
                        keep_visuals: int = 2,
                        keep_music: int = 10,
                        keep_assets: int = 5) -> None:
    """Delete uploaded video + prune old files to free disk space."""
    import glob as _glob

    freed = 0

    def _prune(pattern: str, keep: int) -> int:
        files = sorted(_glob.glob(pattern), key=os.path.getmtime, reverse=True)
        removed = 0
        for f in files[keep:]:
            try:
                sz = os.path.getsize(f)
                os.remove(f)
                removed += sz
            except OSError:
                pass
        return removed

    # Delete the uploaded video (already on YouTube, largest file)
    if uploaded_video and os.path.exists(uploaded_video):
        try:
            freed += os.path.getsize(uploaded_video)
            os.remove(uploaded_video)
        except OSError:
            pass

    # Keep only N most-recent visuals (bg loops, reusable)
    freed += _prune(os.path.join(root, "visuals", "bg_*.mp4"), keep_visuals)

    # Keep only N most-recent music tracks
    freed += _prune(os.path.join(root, "music", "*.wav"), keep_music)
    freed += _prune(os.path.join(root, "music", "*.mp3"), keep_music)

    # Keep only N most-recent assets (thumbnails + SEO JSON)
    freed += _prune(os.path.join(root, "assets", "thumb_*.png"), keep_assets)
    freed += _prune(os.path.join(root, "assets", "thumb_*.jpg"), keep_assets)
    freed += _prune(os.path.join(root, "assets", "seo_*.json"), keep_assets)

    if freed:
        print(f"\n[cleanup] Freed {freed / 1_048_576:.1f} MB of disk space.")


def main():
    parser = argparse.ArgumentParser(description="Lo-fi Factory — Full Pipeline")
    from scripts.visual_v2.themes import ALL_THEMES

    parser.add_argument("--theme", choices=ALL_THEMES,
                        default=None, help="Visual theme (default: random)")
    ALL_DURATIONS  = ["30 min", "45 min", "1 hour", "90 min", "2 hours", "3 hours", "4 hours", "8 hours", "10 hours"]
    # Weighted for MAXIMUM WATCH TIME (= ad revenue + YPP progress):
    # 8h/10h catch overnight sleepers/studiers — single view = 8-10h watch time
    # 2-4h sweet spot for study sessions
    # Short durations de-prioritised (low watch time per view)
    DURATION_WEIGHTS = [1, 2, 8, 4, 18, 18, 16, 20, 13]
    # Auto-scale track count so each duration has enough variety (~5 min/track)
    DURATION_MUSIC_COUNT = {
        "30 min": 2, "45 min": 3, "1 hour": 4, "90 min": 6,
        "2 hours": 8, "3 hours": 12, "4 hours": 15, "5 hours": 18, "8 hours": 25, "10 hours": 30, "all night": 25,
    }
    parser.add_argument("--duration", default=None,
                        choices=["30 min", "45 min", "1 hour", "90 min",
                                 "2 hours", "3 hours", "4 hours", "5 hours",
                                 "8 hours", "10 hours", "all night"])
    parser.add_argument("--music-mode", default="midi",
                        choices=["mock", "midi", "local", "colab"],
                        help="midi=MIDI+FluidSynth via Groq (default), mock=placeholder, local=GPU MusicGen, colab=print Colab code")
    parser.add_argument("--music-v2", action="store_true",
                        help="Use v2 beta music generator (improved voice leading, melody, bass, humanization)")
    parser.add_argument("--music-count", type=int, default=None,
                        help="Number of tracks to generate (default: auto-scaled to duration)")
    parser.add_argument("--skip-visual", action="store_true",
                        help="Skip visual generation (use existing visual)")
    parser.add_argument("--skip-music", action="store_true",
                        help="Skip music generation (use existing files in music/)")
    parser.add_argument("--skip-upload", action="store_true",
                        help="Skip YouTube upload step")
    parser.add_argument("--use-ollama", action="store_true",
                        help="Use local Ollama to enhance SEO description")
    parser.add_argument("--visual-seed", type=int, default=None,
                        help="Seed for visual scene layout (random if omitted — use to reproduce a specific render)")
    parser.add_argument("--ai-bg", action="store_true",
                        help="Use an AI-generated (Pollinations.ai) background scene instead of the "
                             "procedural gradient background. Off by default.")
    parser.add_argument("--regen-bg", action="store_true",
                        help="Force regenerate the AI background even if a cached version exists")
    parser.add_argument("--stream", action="store_true",
                        help="Live stream to YouTube instead of assembling a file")
    parser.add_argument("--stream-test", action="store_true",
                        help="With --stream: encode 60s locally instead of pushing to YouTube")
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
    }

    duration_was_set = args.duration is not None
    if duration_was_set:
        duration = args.duration
    else:
        # Combine the hand-tuned strategic prior (DURATION_WEIGHTS) with a
        # performance-informed multiplier from real watch-time data, same
        # 0.5x-2.0x/needs-5-samples pattern generate_seo.py's pillar weighting
        # already uses -- nudges toward durations that actually retain viewers
        # rather than replacing the strategic prior outright.
        from scripts.assemble_video import DURATION_MAP
        from scripts.analytics import duration_weights as _duration_weights
        _dw = _duration_weights(DURATION_MAP)
        combined_weights = [w * _dw.get(d, 1.0) for d, w in zip(ALL_DURATIONS, DURATION_WEIGHTS)]
        duration = random.choices(ALL_DURATIONS, weights=combined_weights, k=1)[0]
    args.duration    = duration
    music_count      = args.music_count if args.music_count is not None else DURATION_MUSIC_COUNT.get(duration, 6)

    # ── TREND RESEARCH (feeds concept + title + tags) ──────────
    print("\n  Fetching trend data...")
    trends = None
    try:
        from scripts.trend_research import get_trend_snapshot
        trends = get_trend_snapshot()
    except Exception as _te:
        print(f"  [Trends] skipped ({_te})")

    suggested_theme = trends.get("suggested_theme", None) if trends else None

    # ── CONCEPT (generated once, shared by music + SEO) ────────
    print("\n  Generating video concept...")
    from scripts.generate_seo import pick_concept
    concept = pick_concept(trends)
    concept_hint = concept.get("concept") or concept.get("mood_line")
    genre_hint   = concept.get("genre_label") or ""

    # Theme: use --theme if set, otherwise derive from genre, else random
    if args.theme:
        theme = args.theme
    else:
        preferred = _GENRE_THEME.get(genre_hint)
        theme = preferred if preferred else random.choice(ALL_THEMES)

    print("=" * 60)
    print("  LO-FI FACTORY")
    print(f"  Theme:    {theme}")
    print(f"  Duration: {duration}{'' if duration_was_set else ' (random)'}")
    print(f"  Music:    {args.music_mode}")
    print(f"  Genre:    {genre_hint or 'lo-fi hip hop'}")
    print(f"  Concept:  {concept_hint or '(random)'}")
    print("=" * 60)

    # ── STEP 1: Visual ─────────────────────────────────────────
    # Derive short now-playing title + genre from the concept for the UI panel
    np_title = concept.get("mood_line") or concept.get("concept") or "lofi dreams"
    np_genre = concept.get("genre_label", "lo-fi hip hop")

    if not args.skip_visual:
        vis_secs = 60
        print("\n[1/5] Generating lo-fi visual (radio interface)...")
        from scripts.visual_v2 import generate_visual
        visual_path, theme = generate_visual(
            theme_name=theme, duration_secs=vis_secs,
            visual_seed=args.visual_seed,
            track_title=np_title, genre=np_genre,
            use_ai_bg=args.ai_bg,
            regen_bg=args.regen_bg,
        )
    else:
        print("\n[1/5] Skipping visual generation (using existing)")
        import glob
        visuals = glob.glob(os.path.join(ROOT, "visuals", "bg_*.mp4"))
        visual_path = visuals[0] if visuals else None
        if not visual_path:
            print("  WARNING: No visual found. Assembler will generate a gradient fallback.")

    # ── STEP 2: Music ──────────────────────────────────────────
    generated_tracks = []
    if not args.skip_music:
        print(f"\n[2/5] Music mode: {args.music_mode}")

        if args.music_mode == "midi":
            if args.music_v2:
                from scripts.generate_music_v2 import generate_tracks
                print("[run] Using music generator v2 (beta)")
            else:
                from scripts.generate_music_gemini import generate_tracks
            generated_tracks = generate_tracks(count=music_count, concept_hint=concept_hint, genre_hint=genre_hint)
        elif args.music_mode == "mock":
            from scripts.generate_music import generate_mock
            generated_tracks = generate_mock(count=music_count, duration_secs=300)
        elif args.music_mode == "local":
            from scripts.generate_music import generate_local
            generated_tracks = generate_local(count=music_count, duration_secs=300)
        elif args.music_mode == "colab":
            from scripts.generate_music import print_colab_code
            print_colab_code(count=10)
            print("\n[!] Colab mode: drop your .wav/.mp3 files into music/ then re-run with --skip-music")
            sys.exit(0)
    else:
        print("\n[2/5] Skipping music generation (using existing files)")

    # Align concept genre_label + mood_line with what was actually generated.
    # pick_concept() guesses the genre up-front; the algorithm may pick a different
    # sub_genre. Read the first track's .meta.json sidecar to correct the concept.
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
                print(f"  [SEO] Aligned to music: genre={concept['genre_label']!r} mood={concept['mood_line']!r}")
            except Exception as _e:
                print(f"  [SEO] Alignment skipped ({_e})")

    # ── STEP 3: SEO ────────────────────────────────────────────
    print("\n[3/5] Generating SEO metadata...")
    from scripts.generate_seo import generate_seo
    seo, seo_path = generate_seo(theme_name=theme, duration=args.duration,
                                  use_ollama=args.use_ollama, concept=concept,
                                  trends=trends)

    # ── STEP 4: Thumbnail ──────────────────────────────────────
    print("\n[4/5] Generating thumbnail...")
    import time
    from scripts.generate_thumbnail_cozy import generate_thumbnail
    thumb_variant = int(time.time()) % 100
    thumb_path, thumb_title = generate_thumbnail(
        theme_name=suggested_theme or theme,
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
            theme_name=suggested_theme or theme,
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
            _log_path = os.path.join(ROOT, "upload_log.json")
            _log = []
            if os.path.exists(_log_path):
                with open(_log_path) as _f:
                    try: _log = _json.load(_f)
                    except Exception: pass
            _log.append({
                "type":             "upload",
                "video_id":         video_id,
                "url":              url,
                "title":            seo.get("title", ""),
                "title_variants":   seo.get("title_variants", [seo.get("title", "")]),
                "title_chosen_idx": seo.get("title_chosen_idx", 0),
                "pillar":           seo.get("pillar", ""),
                "concept":          seo.get("concept", ""),
                "seo_ref":          seo.get("ref_id", ""),
                "video_file":       os.path.basename(video_path),
                "timestamp":        _dt.datetime.now(_dt.timezone.utc).isoformat(),
            })
            with open(_log_path, "w") as _f:
                _json.dump(_log, _f, indent=2)
        except SystemExit:
            print("  Upload skipped (auth not set up yet)")
        except Exception as e:
            print(f"  Upload failed: {e}")
            print("  Video is ready at:", video_path)
    else:
        print("\n[+] Upload skipped.")

    # ── STEP 7: Cleanup old files (prevent disk fill) ──────────
    if upload_ok:
        _cleanup_old_files(ROOT, video_path)

    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE")
    print(f"  Video:     {video_path}")
    print(f"  Thumbnail: {thumb_path}")
    print(f"  SEO:       {seo_path}")
    print(f"  Title:     {seo['title']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
