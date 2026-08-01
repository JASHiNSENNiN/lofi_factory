"""
generate.py — Abstract Lo-fi Radio Interface visual generator.

Usage:
    from scripts.visual_v2 import generate_visual
    path, theme = generate_visual("neon_tokyo", duration_secs=30,
                                  visual_seed=42, track_title="midnight drive",
                                  genre="lo-fi hip hop")
"""

import os
import datetime
import random
import subprocess
import numpy as np

from .config import W, H, FPS, VISUALS_DIR
from .themes import THEMES, ALL_THEMES
from .noise import looping_noise
from .static_layers import (
    make_gradient_bg, make_star_field, make_scanlines,
    make_vignette, make_star_twinkle,
)
from .scene import (
    make_grid_overlay,
    make_vinyl_body, make_vinyl_label_frames,
    draw_vinyl, draw_tone_arm,
    draw_now_playing, draw_header, draw_divider,
    paste_img_rgba,
)
from .character import EQVisualizer, OscilloscopeBar
from .particles import FloatingOrbs, MusicNotes
from .cozy_fx import build_fx
from .postfx import (
    apply_bloom, film_grain, warm_grade,
    apply_vignette, apply_scanlines, draw_watermark,
    chromatic_aberration,
)


def generate_visual(theme_name: str = "cozy_rain",
                    duration_secs: int = 30,
                    fps: int = FPS,
                    visual_seed: int = None,
                    track_title: str = "lofi dreams",
                    genre: str = "lo-fi hip hop",
                    use_ai_bg: bool = False,
                    regen_bg: bool = False) -> tuple:
    """
    Render an abstract lo-fi radio interface loop video.
    Returns (output_path, theme_name).
    """
    if theme_name not in THEMES:
        theme_name = "cozy_rain"
    if visual_seed is None:
        visual_seed = random.randint(0, 99999)

    n_frames = duration_secs * fps
    ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(VISUALS_DIR, f"bg_{theme_name}_{ts}.mp4")

    print(f"[VISUAL v2] theme={theme_name} | seed={visual_seed} | "
          f"{n_frames} frames @ {fps}fps | {duration_secs}s")
    print("  Pre-rendering static layers...")

    # ── Background: AI scene or programmatic gradient ───────────────────────
    bg_grad = None
    if use_ai_bg:
        from .ai_background import generate_bg_scene
        scene_variant = (visual_seed // 333) % 3  # 0=interior 1=exterior 2=closeup
        bg_grad = generate_bg_scene(
            theme_name, force_regen=regen_bg, variant=scene_variant
        )
    if bg_grad is None:
        bg_grad = make_gradient_bg(theme_name, seed=visual_seed)
    star_field  = make_star_field(theme_name, seed=visual_seed)
    scanlines   = make_scanlines(strength=0.055)
    vignette    = make_vignette(strength=0.38)
    grid_ov     = make_grid_overlay(theme_name)        # RGBA
    star_twinkle = make_star_twinkle(n_frames, seed=visual_seed + 11)

    # ── Vinyl record ────────────────────────────────────────────────────────
    vinyl_body   = make_vinyl_body(theme_name)          # RGBA
    vinyl_labels = make_vinyl_label_frames(theme_name)  # list of RGBA arrays

    # ── EQ & oscilloscope ───────────────────────────────────────────────────
    eq  = EQVisualizer(n_frames, rng_seed=visual_seed + 7)
    osc = OscilloscopeBar(n_frames, rng_seed=visual_seed + 33)

    # ── Cozy atmosphere FX (rain / candle / steam / fireflies / etc.) ───────
    cozy_effects = build_fx(theme_name, n_frames, rng_seed=visual_seed + 200)

    # ── Particles ───────────────────────────────────────────────────────────
    orbs  = FloatingOrbs(rng_seed=visual_seed + 55)
    notes = MusicNotes(rng_seed=visual_seed + 77)

    # ── FFmpeg pipe ──────────────────────────────────────────────────────────
    ffcmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{W}x{H}", "-pix_fmt", "rgb24",
        "-r", str(fps), "-i", "pipe:0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", "18", "-preset", "fast",
        "-movflags", "+faststart",
        out_path,
    ]
    # stderr goes to a log file rather than DEVNULL (previously silently
    # discarded) or PIPE (risks a classic pipe-buffer deadlock here, since
    # nothing concurrently drains it while we're blocked writing frames to
    # stdin) — deleted on success, kept and surfaced on failure.
    ffmpeg_log_path = out_path + ".ffmpeg.log"
    ffmpeg_log = open(ffmpeg_log_path, "wb")
    proc = subprocess.Popen(ffcmd, stdin=subprocess.PIPE, stderr=ffmpeg_log)

    print("  Rendering frames...")
    try:
        for f_idx in range(n_frames):
            t = f_idx / fps

            # ── 1. Background gradient ──────────────────────────────────────
            frame = bg_grad.copy()

            # ── 2. Stars (with twinkle) ─────────────────────────────────────
            twink = float(star_twinkle[f_idx])
            frame = np.clip(
                frame.astype(np.float32)
                + star_field.astype(np.float32) * twink,
                0, 255
            ).astype(np.uint8)

            # ── 3. Perspective grid overlay (subtle — skip on AI bg) ────────
            if not use_ai_bg:
                grid_alpha = grid_ov[:, :, 3:4].astype(np.float32) / 255.0
                frame = np.clip(
                    frame.astype(np.float32) * (1 - grid_alpha)
                    + grid_ov[:, :, :3].astype(np.float32) * grid_alpha,
                    0, 255
                ).astype(np.uint8)

            # ── 3b. Cozy atmosphere FX ──────────────────────────────────────
            for fx in cozy_effects:
                frame = fx.render(frame, t)

            # ── 4. Floating orbs ────────────────────────────────────────────
            orbs.update(t)
            orbs.render(frame, theme_name)

            # ── 5. Vinyl record + tone arm ──────────────────────────────────
            draw_vinyl(frame, vinyl_body, vinyl_labels, f_idx, theme_name)
            draw_tone_arm(frame, f_idx, fps)

            # ── 6. EQ spectrum bars ─────────────────────────────────────────
            eq.render(frame, f_idx, theme_name)

            # ── 7. Oscilloscope strip ───────────────────────────────────────
            osc.render(frame, f_idx, theme_name)

            # ── 8. Now-playing panel ────────────────────────────────────────
            draw_now_playing(frame, track_title, genre, f_idx, n_frames, theme_name)

            # ── 9. Divider line ─────────────────────────────────────────────
            draw_divider(frame, theme_name)

            # ── 10. Music notes ─────────────────────────────────────────────
            notes.update()
            notes.render(frame, theme_name)

            # ── 11. Header bar ──────────────────────────────────────────────
            draw_header(frame, t, theme_name)

            # ── 12. Post-processing ─────────────────────────────────────────
            frame = warm_grade(frame, theme_name)
            frame = apply_bloom(frame, threshold=148, strength=0.32, radius=16)
            frame = apply_scanlines(frame, scanlines)
            frame = apply_vignette(frame, vignette)
            frame = film_grain(frame, strength=3.2)
            # Subtle chromatic aberration (retro screen edge distortion)
            frame = chromatic_aberration(frame, shift=3)

            # ── 13. Watermark ────────────────────────────────────────────────
            draw_watermark(frame)

            proc.stdin.write(frame.tobytes())

            if f_idx % (fps * 5) == 0:
                pct = f_idx * 100 // n_frames
                print(f"  {pct:3d}%  ({f_idx}/{n_frames})")

    finally:
        proc.stdin.close()
        proc.wait()
        ffmpeg_log.close()
        if proc.returncode != 0:
            print(f"  [ffmpeg] ERROR (exit code {proc.returncode}) — log: {ffmpeg_log_path}")
            try:
                with open(ffmpeg_log_path, "r", errors="replace") as _lf:
                    tail = _lf.read()[-2000:]
                print(f"  [ffmpeg] last output:\n{tail}")
            except OSError:
                pass
        else:
            try:
                os.remove(ffmpeg_log_path)
            except OSError:
                pass

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"[VISUAL v2] Done: {out_path} ({size_mb:.1f} MB)")
    return out_path, theme_name


if __name__ == "__main__":
    import sys
    theme    = sys.argv[1] if len(sys.argv) > 1 else "cozy_rain"
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    seed     = int(sys.argv[3]) if len(sys.argv) > 3 else None
    title    = sys.argv[4] if len(sys.argv) > 4 else "lofi dreams"
    genre    = sys.argv[5] if len(sys.argv) > 5 else "lo-fi hip hop"
    generate_visual(theme, duration_secs=duration, visual_seed=seed,
                    track_title=title, genre=genre)
