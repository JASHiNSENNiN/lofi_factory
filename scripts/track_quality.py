"""
track_quality.py — objective quality gate for procedurally-generated tracks.

Two independent sets of gates, run at two different pipeline stages:

  score_track_quality()  — 5 MIDI-structural checks directly from the MIDI
                            event lists ((t, note, vel, dur) tuples) that
                            build_midi()/build_midi_v2() already produce,
                            BEFORE rendering to audio.
  score_audio_quality()  — 4 audio-domain checks (clipping, extended
                            silence, LUFS loudness, spectral balance) on the
                            RENDERED audio, AFTER FluidSynth render + the
                            lofi_fx.py FX chain (see that function's own
                            docstring, further down this file, for exactly
                            where it plugs into generate_track()).

Both exist to catch degenerate generations (a stuck melody, an empty drum
pattern, a collapsed voicing, a clipped or silent render) before they reach
a real daily-upload audience.

Deliberately a set of simple pass/fail gates rather than one hand-tuned
composite score — easier to reason about and debug from the recipe log than
a formula with weights that have never been calibrated against real output
(nothing in this pipeline has been executed end-to-end at the time this was
written).

BLOCKING BEHAVIOR (both gate sets): purely diagnostic. Neither ever blocks
upload, even when a track scores below its MIN_QUALITY_SCORE threshold —
callers keep the best-scoring attempt/existing file and log the failures for
later debugging via the recipe log, rather than dropping a day's video. See
build_midi()'s "Never blocks the daily upload over this" comment in
composer.py for the original rationale, which
score_audio_quality() below deliberately keeps consistent with.
"""

from __future__ import annotations

import math
from collections import Counter

PPQN = 480
BAR = PPQN * 4
S16 = PPQN // 4   # ticks per 16th-note step

MIN_QUALITY_SCORE = 0.8
MAX_RETRIES = 2

# Sub-genres where a narrower melodic pitch range is intentional, not degenerate.
_NARROW_RANGE_SUBGENRES = {'ambient', 'piano_lofi', 'chill_beats'}

KICK_NOTE = 36
SNARE_NOTES = (38, 40)


def _pitch_class_entropy(mel_ev: list[tuple]) -> float:
    """Shannon entropy (bits) of the melody's pitch-class distribution.
    Near 0 means the melody is stuck on essentially one pitch class."""
    if not mel_ev:
        return 0.0
    pcs = [note % 12 for (_t, note, _v, _d) in mel_ev]
    counts = Counter(pcs)
    total = len(pcs)
    entropy = 0.0
    for c in counts.values():
        p = c / total
        entropy -= p * math.log2(p)
    return entropy


def _melody_rest_ratio(mel_ev: list[tuple], active_bars: int) -> float:
    """Fraction of 16th-note steps in the active span with no melody onset."""
    if active_bars <= 0:
        return 0.0
    total_steps = active_bars * 16
    onset_steps = {int(t) // S16 for (t, _n, _v, _d) in mel_ev}
    return 1.0 - (len(onset_steps) / total_steps)


def _longest_empty_span_frac(mel_ev: list[tuple], active_bars: int) -> float:
    """
    Longest contiguous run of empty 16th-note steps, as a fraction of the
    active span — catches a generator that produces a few bars then silently
    stalls, which an average rest ratio can miss.
    """
    if active_bars <= 0:
        return 0.0
    total_steps = active_bars * 16
    onset_steps = sorted({
        int(t) // S16 for (t, _n, _v, _d) in mel_ev
        if 0 <= int(t) // S16 < total_steps
    })
    if not onset_steps:
        return 1.0
    longest = onset_steps[0]  # gap before the first onset
    for a, b in zip(onset_steps, onset_steps[1:]):
        longest = max(longest, b - a - 1)
    longest = max(longest, total_steps - 1 - onset_steps[-1])  # gap after the last onset
    return longest / total_steps


def _pitch_range(mel_ev: list[tuple]) -> int:
    if not mel_ev:
        return 0
    notes = [note for (_t, note, _v, _d) in mel_ev]
    return max(notes) - min(notes)


def score_track_quality(mel_ev: list[tuple], piano_ev: list[tuple], drum_ev: list[tuple],
                         active_bars: int, sub_genre: str | None = None) -> tuple[float, list[str]]:
    """
    Score a generated track against 5 hard pass/fail gates.

    Returns (score, failures): score is the fraction of gates passed (in
    [0,1]); failures lists which gates failed (for the recipe log / debugging).
    """
    failures: list[str] = []

    if _pitch_class_entropy(mel_ev) < 0.5:
        failures.append('low_pitch_entropy')

    if _melody_rest_ratio(mel_ev, active_bars) > 0.97:
        failures.append('melody_too_sparse')

    if _longest_empty_span_frac(mel_ev, active_bars) > 0.40:
        failures.append('melody_long_silence')

    min_acceptable_range = 1 if sub_genre in _NARROW_RANGE_SUBGENRES else 3
    if not mel_ev or _pitch_range(mel_ev) < min_acceptable_range:
        failures.append('flat_pitch_range')

    has_kick = any(note == KICK_NOTE for (_t, note, _v, _d) in drum_ev)
    has_snare = any(note in SNARE_NOTES for (_t, note, _v, _d) in drum_ev)
    if not (has_kick and has_snare and piano_ev):
        failures.append('drum_or_piano_empty')

    n_gates = 5
    score = (n_gates - len(failures)) / n_gates
    return score, failures


# ─── AUDIO-DOMAIN QUALITY GATES ────────────────────────────────────────────
#
# Everything above runs on MIDI event lists, BEFORE any audio is rendered.
# Everything below runs on the RENDERED audio (numpy samples from the WAV
# file) and therefore plugs into the pipeline at a different, LATER stage:
# after FluidSynth render + the lofi_fx.py FX chain, not before it — see
# generate_track() in composer.py / generate_music_v2.py, right
# after the `_lofi_fx(...)` call that produces the final published WAV.
# score_audio_quality() is the audio-domain counterpart of
# score_track_quality() above, in the same "small set of simple pass/fail
# gates, not one hand-tuned composite score" spirit.
#
# BLOCKING BEHAVIOR: purely diagnostic, exactly like the MIDI gates above —
# this module's existing design never blocks upload even when a track scores
# below MIN_QUALITY_SCORE (see build_midi()'s "Never blocks the daily upload
# over this" comment in composer.py); the retry loop just keeps
# the best-scoring attempt. score_audio_quality() follows that same
# philosophy: it is called AFTER the WAV that is going to be uploaded already
# exists (there is nothing left to retry — re-rendering audio is expensive
# and the MIDI-level retry loop already ran), so it can only log/score, not
# gate. Wire it in as a post-hoc quality signal for the recipe log, not a
# blocking check.

import math as _math

PEAK_CLIP_THRESHOLD   = 0.98     # near full-scale (float samples in [-1, 1])
PEAK_CLIP_MAX_FRACTION = 0.0005  # >0.05% of samples at/near full-scale -> flag as clipped

SILENCE_RMS_THRESHOLD_DB = -50.0  # a window this quiet counts as "silent"
SILENCE_WINDOW_SECONDS   = 0.5
SILENCE_MAX_RUN_SECONDS  = 8.0    # longest allowed contiguous silent run

# Matches the per-track mastering target in lofi_fx.py (see there for why
# per-track targets slightly under the video-level -14 LUFS assemble_video.py
# already applies, to leave headroom for that final pass rather than fighting
# it). The audio-quality-gate tolerance is deliberately generous (+-6 LU) —
# this is a "did mastering wildly miss" sanity check, not a mastering
# enforcement mechanism (that's lofi_fx.py's job).
AUDIO_LUFS_TARGET_DEFAULT = -17.0
AUDIO_LUFS_TOLERANCE      = 6.0

SPECTRAL_MAX_BAND_FRACTION = 0.90  # one band holding >90% of spectral energy is a red flag

AUDIO_MIN_QUALITY_SCORE = 0.75


def _to_mono(audio) -> "list | object":
    """Accepts (n,) mono or (n, channels) multi-channel float arrays (the
    soundfile.read()/pyloudnorm convention used throughout this pipeline —
    channels as the LAST axis) and returns a 1-D mono signal."""
    import numpy as np
    arr = np.asarray(audio)
    if arr.ndim == 1:
        return arr
    return arr.mean(axis=-1)


def detect_clipping(audio, threshold: float = PEAK_CLIP_THRESHOLD,
                     max_fraction: float = PEAK_CLIP_MAX_FRACTION) -> bool:
    """
    True if too large a fraction of samples sit at/near full scale — the
    classic clipping signature. A handful of true-peak samples brushing 0dBFS
    is normal after limiting/normalization; a sustained run of them is not.
    """
    import numpy as np
    mono = _to_mono(audio)
    if mono.size == 0:
        return False
    clipped_fraction = float(np.mean(np.abs(mono) >= threshold))
    return clipped_fraction > max_fraction


def detect_extended_silence(audio, sr: int,
                             rms_threshold_db: float = SILENCE_RMS_THRESHOLD_DB,
                             window_seconds: float = SILENCE_WINDOW_SECONDS,
                             max_run_seconds: float = SILENCE_MAX_RUN_SECONDS) -> bool:
    """
    True if there is a contiguous run of near-zero-RMS windows longer than
    `max_run_seconds` anywhere in the track — catches a render that silently
    dropped out partway through (dead soundfont voice, FX-chain crash that
    zeroed a buffer, etc.), which peak-only checks would miss entirely.
    """
    import numpy as np
    mono = _to_mono(audio)
    n = mono.size
    if n == 0 or sr <= 0:
        return True
    window = max(1, int(window_seconds * sr))

    longest_run = 0.0
    current_run = 0.0
    for start in range(0, n, window):
        chunk = mono[start:start + window]
        if chunk.size == 0:
            continue
        rms = float(np.sqrt(np.mean(np.square(chunk.astype(np.float64)))))
        db = 20.0 * _math.log10(rms) if rms > 1e-12 else -120.0
        chunk_seconds = chunk.size / sr
        if db < rms_threshold_db:
            current_run += chunk_seconds
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0.0
    return longest_run > max_run_seconds


def measure_lufs(audio, sr: int) -> float | None:
    """
    Integrated loudness in LUFS via pyloudnorm (MIT license). Returns None
    (rather than raising) if pyloudnorm is unavailable, the audio is too
    short/quiet to produce a stable measurement, or anything else goes
    wrong — this is a diagnostic signal, never a hard requirement for the
    pipeline to keep running.
    """
    try:
        import pyloudnorm as pyln
        import numpy as np
        arr = np.asarray(audio, dtype=np.float64)
        meter = pyln.Meter(sr)
        loudness = meter.integrated_loudness(arr)
        if loudness is None or not _math.isfinite(loudness):
            return None
        return float(loudness)
    except Exception:
        return None


def spectral_balance_ok(audio, sr: int, n_bands: int = 4,
                         max_band_fraction: float = SPECTRAL_MAX_BAND_FRACTION) -> bool:
    """
    Basic spectral-balance sanity check: split the magnitude spectrum into
    `n_bands` roughly-log-spaced bands and confirm no single band holds an
    outsized share of total energy — catches a degenerate render (e.g. a
    stuck oscillator, a filter set to fully close, DC offset dominating a
    near-silent buffer) that concentrates energy in one narrow band instead
    of a normal music-like spread across the spectrum.
    """
    import numpy as np
    mono = np.asarray(_to_mono(audio), dtype=np.float64)
    if mono.size < 2 or sr <= 0:
        return True  # nothing meaningful to analyze; don't flag a false positive

    spectrum = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(mono.size, d=1.0 / sr)
    total_energy = float(np.sum(spectrum ** 2))
    if total_energy <= 1e-12:
        return False  # totally flat spectrum -> effectively silent/degenerate

    # Log-spaced band edges from 20 Hz to Nyquist.
    nyquist = sr / 2.0
    lo = 20.0
    hi = max(lo * 1.01, nyquist)
    edges = np.geomspace(lo, hi, n_bands + 1)

    band_fractions = []
    for i in range(n_bands):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        band_energy = float(np.sum(spectrum[mask] ** 2))
        band_fractions.append(band_energy / total_energy)

    return max(band_fractions) <= max_band_fraction


def score_audio_quality(audio, sr: int, lufs_target: float = AUDIO_LUFS_TARGET_DEFAULT,
                         lufs_tolerance: float = AUDIO_LUFS_TOLERANCE) -> tuple[float, list[str]]:
    """
    Score RENDERED audio against 4 hard pass/fail gates — the audio-domain
    counterpart of score_track_quality() above, run at a different pipeline
    stage (post-render/post-FX, not pre-render). Purely diagnostic: see the
    module-level comment above this section for why this never blocks
    upload, only logs/scores.

    `audio`: float samples, shape (n,) mono or (n, channels) — the
    soundfile.read() convention used throughout this pipeline.

    Returns (score, failures), same shape as score_track_quality().
    """
    failures: list[str] = []

    if detect_clipping(audio):
        failures.append('clipping_detected')

    if detect_extended_silence(audio, sr):
        failures.append('extended_silence')

    lufs = measure_lufs(audio, sr)
    if lufs is not None and abs(lufs - lufs_target) > lufs_tolerance:
        failures.append('lufs_out_of_range')

    if not spectral_balance_ok(audio, sr):
        failures.append('spectral_imbalance')

    n_gates = 4
    score = (n_gates - len(failures)) / n_gates
    return score, failures
