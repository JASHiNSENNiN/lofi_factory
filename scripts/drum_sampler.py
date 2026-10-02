"""
drum_sampler.py — Drum break engine with real sample support.

Priority:
  1. Real CC0 one-shot samples from assets/drums/ (Boochi44/free-drum-samples, CC0)
  2. Synthesis fallback (FM kick, noise snare, filtered hi-hat) when samples absent

Fixes (2026-05-08):
  · Snare peak-normalized (was clipping at 1.4–2.8× on every style)
  · Swing-aware timing — odd 16th steps offset by same formula as MIDI grid_tick()
  · LPF: scipy.signal.lfilter replaces O(n) Python loop (~1400 ms → ~1 ms)
  · LPF cutoff corrected to 6 kHz (was 2 kHz, killed hi-hat sizzle)
  · Hi-hat highpass now uses scipy Butterworth (proper sizzle band)
  · Two independent loops concatenated → 8-bar macro-loop (was single 4-bar loop
    that listeners detect after ~36 s; now ~72 s before repetition is obvious)
  · Real CC0 samples auto-loaded on first use; synthesis used when not present
"""

from __future__ import annotations

import os
import random
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, lfilter

from scripts import genre_presets

SR = 44_100
_PEAK_CEILING = 10 ** (-1.5 / 20)   # -1.5 dBFS
_ASSET_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "drums")

# ─── Sample bank ─────────────────────────────────────────────────────────────

_CACHE: dict[str, np.ndarray | None] = {}


def _load(filename: str) -> np.ndarray | None:
    """Load a WAV one-shot, resampling to 44.1 kHz mono. Cached after first load."""
    if filename in _CACHE:
        return _CACHE[filename]
    path = os.path.join(_ASSET_DIR, filename)
    if not os.path.isfile(path):
        _CACHE[filename] = None
        return None
    try:
        audio, orig_sr = sf.read(path, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if orig_sr != SR:
            from math import gcd
            from scipy.signal import resample_poly
            g = gcd(int(orig_sr), SR)
            audio = resample_poly(audio, SR // g, orig_sr // g)
        _CACHE[filename] = audio.astype(np.float32)
    except Exception:
        _CACHE[filename] = None
    return _CACHE[filename]


def _pick_sample(filenames: list[str]) -> np.ndarray | None:
    """Return a random real sample from the list, or None if none are available."""
    available = [f for f in filenames if _load(f) is not None]
    if not available:
        return None
    return _load(random.choice(available)).copy()


# CC0 sample filenames (Boochi44/free-drum-samples, 03-soulful-vintage kit)
_KICK_FILES  = ["vintage-kick-01.wav", "vintage-kick-02.wav", "vintage-kick-03.wav"]
_SNARE_FILES = ["vintage-snare-01.wav", "vintage-snare-02.wav", "vintage-snare-03.wav"]
# One closed and one open hat: the two extra hat files that used to be
# listed here were byte-identical copies of these.
_CHAT_FILES  = ["ch-lofi.wav"]
_OHAT_FILES  = ["oh00-lofi.wav"]


# ─── Synthesis fallbacks ──────────────────────────────────────────────────────

def _synth_kick(bpm: int, style: str = "standard") -> np.ndarray:
    dur = 0.45
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    p = dict({
        "standard": dict(f0=150, f1=45,  decay=8.0,  punch=0.25),
        "808":      dict(f0=70,  f1=28,  decay=5.0,  punch=0.10),
        "room":     dict(f0=130, f1=50,  decay=6.5,  punch=0.30),
        "tight":    dict(f0=195, f1=58,  decay=12.0, punch=0.40),
        "jazz":     dict(f0=120, f1=42,  decay=9.0,  punch=0.15),
    }.get(style, dict(f0=150, f1=45, decay=8.0, punch=0.25)))
    p["f0"] *= random.uniform(0.90, 1.10)
    p["decay"] *= random.uniform(0.90, 1.10)
    freq   = p["f0"] * np.exp(-p["decay"] * t) + p["f1"]
    signal = np.sin(np.cumsum(freq) / SR * 2 * np.pi)
    amp    = np.exp(-7 * t) * (1.0 - np.exp(-180 * t))
    click  = p["punch"] * np.exp(-120 * t) * np.random.randn(n)
    return ((signal * amp + click) * 0.88).astype(np.float32)


def _synth_snare(style: str = "standard") -> np.ndarray:
    dur = 0.22
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    p = dict({
        "standard": dict(f_body=220, bd=25, nd=18, nr=0.60),
        "tight":    dict(f_body=295, bd=40, nd=30, nr=0.50),
        "snappy":   dict(f_body=250, bd=35, nd=22, nr=0.68),
        "brush":    dict(f_body=185, bd=14, nd=11, nr=0.82),
    }.get(style, dict(f_body=220, bd=25, nd=18, nr=0.60)))
    p["f_body"] *= random.uniform(0.92, 1.08)
    body  = np.sin(2 * np.pi * p["f_body"] * t) * np.exp(-p["bd"] * t)
    noise = np.random.randn(n) * np.exp(-p["nd"] * t)
    click = 0.22 * np.exp(-280 * t) * np.random.randn(n)
    nr    = p["nr"]
    raw   = body * (1 - nr) + noise * nr + click * 0.3
    peak  = float(np.max(np.abs(raw))) + 1e-9
    return (raw / peak * 0.72).astype(np.float32)


def _synth_hihat(open: bool = False) -> np.ndarray:
    dur  = 0.07 if not open else random.uniform(0.14, 0.32)
    n    = int(SR * dur)
    t    = np.linspace(0, dur, n, endpoint=False)
    sos  = butter(2, 6000 / (SR / 2), btype="high", output="sos")
    hp   = sosfilt(sos, np.random.randn(n)).astype(np.float32)
    amp  = np.exp((-28 if not open else -7) * t) * (1.0 - np.exp(-400 * t))
    return (hp * amp * 0.32).astype(np.float32)


# ─── Hit builders (real sample preferred, synthesis fallback) ─────────────────

def _kick(bpm: int, style: str = "standard") -> np.ndarray:
    sample = _pick_sample(_KICK_FILES)
    if sample is not None:
        # Random velocity shaping: scale amplitude + slightly vary decay tail
        gain  = random.uniform(0.75, 1.00)
        n     = len(sample)
        # For '808' style, extend the low-end tail perception by boosting low end
        # (repitching isn't worth it here, so leave as-is)
        return (sample * gain)
    return _synth_kick(bpm, style)


def _snare(style: str = "standard") -> np.ndarray:
    sample = _pick_sample(_SNARE_FILES)
    if sample is not None:
        gain = random.uniform(0.72, 1.00)
        return (sample * gain)
    return _synth_snare(style)


def _hihat(open: bool = False) -> np.ndarray:
    sample = _pick_sample(_OHAT_FILES if open else _CHAT_FILES)
    if sample is not None:
        gain = random.uniform(0.28, 0.45)
        return (sample * gain)
    return _synth_hihat(open)


# ─── Drum patterns ────────────────────────────────────────────────────────────
# 16-step patterns (one bar). 0.0 = rest.

_PAT_STANDARD = {
    "k": [1.0, 0,   0,   0.2, 0,   0,   0,   0,   0.9, 0,   0,   0,   0.3, 0,   0,   0  ],
    "s": [0,   0,   0,   0,   1.0, 0,   0,   0.2, 0,   0,   0,   0,   1.0, 0,   0,   0.1],
    "h": [0.8, 0,   0.6, 0,   0.8, 0,   0.6, 0,   0.8, 0,   0.6, 0,   0.8, 0,   0.6, 0  ],
}
_PAT_BOOM_BAP = {
    "k": [1.0, 0,   0,   0.4, 0,   0,   0,   0,   0.8, 0,   0.3, 0,   0,   0.4, 0,   0  ],
    "s": [0,   0,   0,   0,   0.9, 0,   0.2, 0,   0,   0.1, 0,   0,   0.9, 0,   0,   0.2],
    "h": [0.7, 0,   0.5, 0,   0.7, 0.3, 0.5, 0,   0.7, 0,   0.5, 0.3, 0.7, 0,   0.5, 0.2],
}
_PAT_808_TRAP = {
    "k": [1.0, 0,   0,   0,   0,   0,   0.5, 0,   0,   0.3, 0,   0,   0,   0,   0,   0  ],
    "s": [0,   0,   0,   0,   1.0, 0,   0,   0,   0,   0,   0,   0,   0.9, 0,   0,   0  ],
    "h": [0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6],
}
_PAT_JAZZ = {
    "k": [0.8, 0,   0,   0,   0,   0,   0,   0,   0.7, 0,   0.4, 0,   0,   0,   0,   0  ],
    "s": [0,   0,   0.3, 0,   0.7, 0,   0.2, 0,   0,   0.2, 0,   0,   0.8, 0,   0.3, 0.1],
    "h": [0.5, 0.3, 0.5, 0.3, 0.5, 0.3, 0.5, 0.3, 0.5, 0.3, 0.5, 0.3, 0.5, 0.3, 0.5, 0.3],
}
_PAT_DUSTY = {
    "k": [1.0, 0,   0,   0,   0,   0.3, 0,   0,   0.7, 0,   0,   0.4, 0,   0,   0,   0  ],
    "s": [0,   0,   0.2, 0,   0.9, 0,   0,   0.3, 0,   0,   0.2, 0,   0.9, 0,   0.1, 0  ],
    "h": [0.7, 0.3, 0.7, 0.3, 0.7, 0.3, 0.7, 0.3, 0.7, 0.3, 0.7, 0.3, 0.7, 0.3, 0.7, 0.3],
}

from scripts.euclidean import bjorklund as _bjorklund


def generate_euclidean_pat_dict(energy: float) -> dict:
    """
    Generate a fresh 16-step {'k','s','h'} amplitude-pattern dict via
    Euclidean rhythms, matching the exact format of _PAT_STANDARD etc., as a
    generative alternative to always picking from the fixed 5-pattern table.
    """
    energy = max(0.0, min(1.0, energy))
    n = 16
    k_kick = max(2, min(5, round(2 + energy * 3)))
    k_hat = max(6, min(12, round(6 + energy * 4)))
    kick_pat = _bjorklund(k_kick, n)
    hat_pat = _bjorklund(k_hat, n)

    # Snare: rotation-search for max overlap with the backbeat (steps 4, 12) —
    # same technique used by the MIDI-layer generator in composer.py,
    # so the synthesized layer and the MIDI layer share the same rhythmic logic.
    snare_base = _bjorklund(2, n)
    backbeat = {4, 12}
    best_rot, best_score = snare_base, -1
    for r in range(n):
        rotated = snare_base[r:] + snare_base[:r]
        score = sum(1 for step in backbeat if rotated[step])
        if score > best_score:
            best_rot, best_score = rotated, score

    return {
        "k": [1.0 if v else 0.0 for v in kick_pat],
        "s": [0.9 if v else 0.0 for v in best_rot],
        "h": [0.6 if v else 0.0 for v in hat_pat],
    }


_ALL_PATS = [_PAT_STANDARD, _PAT_BOOM_BAP, _PAT_808_TRAP, _PAT_JAZZ, _PAT_DUSTY]

# Loaded from config/genres/*.yaml (see scripts/genre_presets.py). Subgenres
# absent from the YAML's drum_sampler_pattern field fall back to a random
# pick from _ALL_PATS at call time (unchanged).
_PAT_REGISTRY = {
    "standard": _PAT_STANDARD, "boom_bap": _PAT_BOOM_BAP,
    "808_trap": _PAT_808_TRAP, "jazz": _PAT_JAZZ, "dusty": _PAT_DUSTY,
}
_SUBGENRE_PAT: dict[str, dict] = genre_presets.build_subgenre_pat(_PAT_REGISTRY)


def _mix_at(buf: np.ndarray, src: np.ndarray, pos: int) -> None:
    if pos < 0 or len(src) == 0:
        return
    end     = min(len(buf), pos + len(src))
    src_end = end - pos
    if src_end > 0:
        buf[pos:end] += src[:src_end]


_GM_KICK, _GM_SNARE, _GM_CLAP, _GM_CHH = 36, 38, 39, 42


def pattern_from_midi(midi_pattern: dict, chh_triplet: bool = False) -> dict:
    """{'k','s','h'} amplitudes from a composer MIDI drum pattern (GM note ->
    velocities, 16 steps per bar), so the sample layer doubles the MIDI
    drummer instead of playing a second, unrelated groove. Only voices with
    a matching sample are taken: kick, snare/clap, closed hat. Rim, ride,
    cowbell and shakers stay MIDI-only; triplet hats (drill) can't be
    doubled on this 16-step grid, so they're left out too."""
    length = max(len(v) for v in midi_pattern.values())

    def voice(*notes):
        out = [0.0] * length
        for n in notes:
            for i, vel in enumerate(midi_pattern.get(n, [])):
                out[i] = max(out[i], vel / 127.0)
        return out
    return {"k": voice(_GM_KICK), "s": voice(_GM_SNARE, _GM_CLAP),
            "h": [0.0] * length if chh_triplet else voice(_GM_CHH)}


def _build_loop(bpm: int, sub_genre: str, n_bars: int = 4,
                swing: float = 0.5, pattern: dict | None = None) -> np.ndarray:
    """
    Build one drum loop (n_bars long) with swing-aware timing.

    swing: same ratio as MIDI grid_tick() — 0.5=straight, 0.62=typical lofi.
    Odd 16th-note steps shifted by (swing-0.5)*2*step_sec, matching the MIDI
    render exactly so synthetic and MIDI layers sit in the same rhythmic pocket.
    """
    beat_sec = 60.0 / bpm
    step_sec = beat_sec / 4
    loop     = np.zeros(int(SR * beat_sec * 4 * n_bars), dtype=np.float32)

    # Synthesis style selection (used only when real samples unavailable)
    if sub_genre in ("hip_hop_lofi", "nujabes", "dark_lofi"):
        kick_style, snare_style = "tight", "snappy"
    elif sub_genre in ("lofi_phonk", "vaporwave", "lofi_drill"):
        kick_style, snare_style = "808", "tight"
    elif sub_genre in ("lofi_jazz", "jazz_cafe", "bossa_lofi", "ambient",
                       "piano_lofi", "lofi_classical"):
        kick_style, snare_style = "jazz", "brush"
    else:
        kick_style  = random.choice(["standard", "room", "tight"])
        snare_style = random.choice(["standard", "tight", "snappy"])

    # Build hits — new random sample picked per loop so loops A and B differ
    kick  = _kick(bpm, kick_style)
    snare = _snare(snare_style)
    hat_c = _hihat(False)
    hat_o = _hihat(True)

    # ~35% chance to use a freshly-generated Euclidean pattern instead of the
    # fixed 5-pattern table, for extra rhythmic variety on this synthesis layer
    # (Phase-A adoption bump; started at 20%). This module is intentionally
    # dependency-free of composer.py, so a failure here can't
    # cascade into the MIDI-layer generation — still wrapped defensively since
    # this runs unattended daily.
    if pattern is not None:
        pat = pattern
    else:
        try:
            if random.random() < 0.35:
                pat = generate_euclidean_pat_dict(energy=random.uniform(0.35, 0.85))
            else:
                pat = _SUBGENRE_PAT.get(sub_genre, random.choice(_ALL_PATS))
        except Exception:
            pat = _SUBGENRE_PAT.get(sub_genre, random.choice(_ALL_PATS))

    for step in range(16 * n_bars):
        step_in_bar = step % 16
        swing_off   = (swing - 0.5) * 2 * step_sec if (step % 2 == 1) else 0.0
        jitter      = random.gauss(0, 0.007)
        pos         = max(0, int((step * step_sec + swing_off + jitter) * SR))

        k_v = pat["k"][step % len(pat["k"])] * random.uniform(0.88, 1.00)
        s_v = pat["s"][step % len(pat["s"])] * random.uniform(0.84, 1.00)
        h_v = pat["h"][step % len(pat["h"])] * random.uniform(0.78, 1.00)

        if k_v > 0.01:
            _mix_at(loop, kick * k_v, pos)
        if s_v > 0.01:
            _mix_at(loop, snare * s_v, pos)
        if h_v > 0.01:
            use_open = step_in_bar in (6, 14) and random.random() < 0.25
            _mix_at(loop, (hat_o if use_open else hat_c) * h_v, pos)

    # 6 kHz low-pass for vintage body — scipy lfilter (was O(n) Python loop)
    alpha = 0.575   # 3 dB @ 6 kHz; alpha=0.25 was 2 kHz and killed hi-hat sizzle
    loop  = lfilter([alpha], [1.0, -(1.0 - alpha)], loop).astype(np.float32)

    return loop


def layer_drum_break(
    base_wav: str,
    output_wav: str,
    bpm: int = 80,
    sub_genre: str = "chillhop",
    volume: float = 0.22,
    swing: float = 0.62,
    spans: list[tuple[int, int]] | None = None,
    patterns: tuple[dict, dict] | None = None,
    span_labels: list[str] | None = None,
) -> None:
    """
    Generate a drum break and mix it into base_wav.

    Two independently randomized loops are concatenated (8-bar macro-loop) so the
    audible repeat threshold is ~72 s rather than ~36 s for a single 4-bar loop.
    Real CC0 samples used when present in assets/drums/; synthesis otherwise.

    swing: pass params['swing'] so drums land in the same pocket as the MIDI render.
    spans: (start_sample, end_sample) ranges where the break should play
    (the arrangement's full-beat sections). Outside them it is silent, with
    short fades at the edges. None plays it across the whole file.
    Reads base_wav fully before writing → in-place (src == dst) is safe.
    """
    using_real = any(_load(f) is not None
                     for f in _KICK_FILES + _SNARE_FILES + _CHAT_FILES)
    print(f"    drums: {'real CC0 samples' if using_real else 'synthesis fallback'}")

    audio, _ = sf.read(base_wav, dtype="float32", always_2d=True)
    n_samples = audio.shape[0]

    if patterns is not None and spans:
        # Double the MIDI drummer: each section's own pattern, started at the
        # section's first bar so the layers line up.
        loops = {"A": _build_loop(bpm, sub_genre, 4, swing, pattern=patterns[0]),
                 "B": _build_loop(bpm, sub_genre, 4, swing, pattern=patterns[1])}
        drums = np.zeros(n_samples, dtype=np.float32)
        for i, (start, end) in enumerate(spans):
            start, end = max(0, int(start)), min(n_samples, int(end))
            label = (span_labels[i] if span_labels and i < len(span_labels) else "A")
            loop = loops["B" if label == "B" else "A"]
            if end > start and len(loop):
                reps = int(np.ceil((end - start) / len(loop)))
                drums[start:end] = np.tile(loop, reps)[:end - start]
    else:
        loop_a = _build_loop(bpm, sub_genre, n_bars=4, swing=swing)
        loop_b = _build_loop(bpm, sub_genre, n_bars=4, swing=swing)
        macro  = np.concatenate([loop_a, loop_b])

        if len(macro) == 0:
            return

        n_reps = int(np.ceil(n_samples / len(macro)))
        drums  = np.tile(macro, n_reps)[:n_samples]

    if spans is not None:
        mask = np.zeros(n_samples, dtype=np.float32)
        fade = int(0.03 * SR)
        for start, end in spans:
            start, end = max(0, int(start)), min(n_samples, int(end))
            if end - start <= 2 * fade:
                continue
            mask[start:end] = 1.0
            mask[start:start + fade] = np.linspace(0.0, 1.0, fade, dtype=np.float32)
            mask[end - fade:end] = np.linspace(1.0, 0.0, fade, dtype=np.float32)

    base_rms = float(np.sqrt(np.mean(audio ** 2)))
    drum_rms = float(np.sqrt(np.mean(drums ** 2))) + 1e-9
    # If base is silent use a fixed target RMS of 0.1; otherwise match base level.
    target_rms = base_rms if base_rms > 1e-4 else 0.10
    drums = drums * (target_rms / drum_rms) * volume
    if spans is not None:
        drums = drums * mask

    if audio.shape[1] == 2:
        spread   = random.uniform(-0.08, 0.08)
        drums_st = np.column_stack([drums * (1.0 + spread),
                                    drums * (1.0 - spread)])
        mixed = audio + drums_st
    else:
        mixed = audio + drums.reshape(-1, 1)

    # -1.5 dBFS sample-peak ceiling: leaves room for inter-sample peaks so the
    # AAC-encoded upload stays under YouTube's -1 dBTP.
    peak = float(np.max(np.abs(mixed))) + 1e-9
    if peak > _PEAK_CEILING:
        mixed = mixed * (_PEAK_CEILING / peak)

    sf.write(output_wav, mixed, SR, subtype="PCM_16")
