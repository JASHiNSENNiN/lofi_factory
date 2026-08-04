"""
lofi_fx.py — Pedalboard-based lo-fi FX chain.
Replaces the ffmpeg acrusher/aecho/atremolo chain with Spotify's Pedalboard library,
which gives per-genre character through proper resonant filters, real compression,
and pitch-wobble that actually sounds like tape.

Falls back to the legacy ffmpeg chain if pedalboard is not available.

Note on "instrument detuning": commonly cited as a lofi-authenticity technique,
but it's fundamentally a per-note MIDI-generation-time effect (each instrument
pitch-bent slightly relative to the others), not something a final-mix
post-processing stage like this one can add after the fact -- a whole-mix
pitch shift here would just transpose everything together, leaving relative
pitch relationships (and therefore the "detuned" character) unchanged. The
existing Chorus stage below is the standard post-processing approximation of
that same "slightly out of tune" character (continuous micro pitch-modulation
via a short delay line), so no separate detune stage was added here.
"""

from __future__ import annotations

import random
import os
from scipy.signal import lfilter as _lfilter

# Per-genre FX presets — tuned to feel different, not just be different numbers
# lpf: Moog ladder LPF cutoff Hz (lower = more muffled/vintage)
# bits: bitcrusher depth (lower = more grit, 8=MPC2000, 12=Akai S950, 16=clean)
# room: reverb room size 0-1
# wet: reverb wet mix
# chorus_depth: tape wobble amount 0-1
# compress_ratio: compression ratio
# vinyl: vinyl crackle amplitude
_GENRE_PRESETS: dict[str, dict] = {
    # ── Dark / moody ─────────────────────────────────────────────────────────
    "dark_lofi":     {"lpf": 7500,  "bits": 9,  "room": 0.5, "wet": 0.28, "chorus_depth": 0.25, "compress_ratio": 3.5, "vinyl": 0.18},
    "lofi_phonk":    {"lpf": 7000,  "bits": 8,  "room": 0.4, "wet": 0.22, "chorus_depth": 0.30, "compress_ratio": 4.0, "vinyl": 0.22},
    "vaporwave":     {"lpf": 8000,  "bits": 9,  "room": 0.6, "wet": 0.35, "chorus_depth": 0.28, "compress_ratio": 3.0, "vinyl": 0.14},
    "ambient":       {"lpf": 12000, "bits": 13, "room": 0.7, "wet": 0.40, "chorus_depth": 0.12, "compress_ratio": 2.0, "vinyl": 0.05},
    # ── Jazz / soul ───────────────────────────────────────────────────────────
    "lofi_jazz":     {"lpf": 10000, "bits": 11, "room": 0.4, "wet": 0.22, "chorus_depth": 0.18, "compress_ratio": 2.8, "vinyl": 0.10},
    "jazz_cafe":     {"lpf": 11000, "bits": 12, "room": 0.4, "wet": 0.20, "chorus_depth": 0.15, "compress_ratio": 2.5, "vinyl": 0.08},
    "nujabes":       {"lpf": 10000, "bits": 11, "room": 0.45,"wet": 0.25, "chorus_depth": 0.20, "compress_ratio": 2.8, "vinyl": 0.12},
    "neo_soul":      {"lpf": 11000, "bits": 12, "room": 0.4, "wet": 0.22, "chorus_depth": 0.16, "compress_ratio": 2.5, "vinyl": 0.09},
    "bossa_lofi":    {"lpf": 12500, "bits": 13, "room": 0.35,"wet": 0.18, "chorus_depth": 0.12, "compress_ratio": 2.2, "vinyl": 0.06},
    "lofi_rnb":      {"lpf": 11000, "bits": 11, "room": 0.4, "wet": 0.22, "chorus_depth": 0.18, "compress_ratio": 2.8, "vinyl": 0.10},
    # ── Hip-hop / beat ───────────────────────────────────────────────────────
    "chillhop":      {"lpf": 9500,  "bits": 11, "room": 0.35,"wet": 0.20, "chorus_depth": 0.18, "compress_ratio": 3.0, "vinyl": 0.12},
    "hip_hop_lofi":  {"lpf": 9000,  "bits": 10, "room": 0.35,"wet": 0.18, "chorus_depth": 0.20, "compress_ratio": 3.5, "vinyl": 0.15},
    "lo_fi_funk":    {"lpf": 9500,  "bits": 10, "room": 0.35,"wet": 0.18, "chorus_depth": 0.22, "compress_ratio": 3.5, "vinyl": 0.14},
    "chill_beats":   {"lpf": 11000, "bits": 12, "room": 0.45,"wet": 0.25, "chorus_depth": 0.14, "compress_ratio": 2.5, "vinyl": 0.08},
    "lofi_house":    {"lpf": 11000, "bits": 12, "room": 0.4, "wet": 0.20, "chorus_depth": 0.15, "compress_ratio": 3.0, "vinyl": 0.09},
    # ── Cozy / bright ────────────────────────────────────────────────────────
    "cozy_cafe":     {"lpf": 13000, "bits": 13, "room": 0.35,"wet": 0.18, "chorus_depth": 0.12, "compress_ratio": 2.2, "vinyl": 0.06},
    "morning_lofi":  {"lpf": 13000, "bits": 13, "room": 0.3, "wet": 0.15, "chorus_depth": 0.10, "compress_ratio": 2.0, "vinyl": 0.05},
    "anime_lofi":    {"lpf": 13500, "bits": 14, "room": 0.3, "wet": 0.15, "chorus_depth": 0.10, "compress_ratio": 2.0, "vinyl": 0.04},
    "summer_vibes":  {"lpf": 13000, "bits": 13, "room": 0.3, "wet": 0.16, "chorus_depth": 0.11, "compress_ratio": 2.0, "vinyl": 0.05},
    "bedroom_pop":   {"lpf": 13000, "bits": 13, "room": 0.35,"wet": 0.18, "chorus_depth": 0.13, "compress_ratio": 2.2, "vinyl": 0.06},
    "city_pop":      {"lpf": 13000, "bits": 13, "room": 0.3, "wet": 0.16, "chorus_depth": 0.12, "compress_ratio": 2.2, "vinyl": 0.06},
    "study_lofi":    {"lpf": 11000, "bits": 12, "room": 0.38,"wet": 0.20, "chorus_depth": 0.14, "compress_ratio": 2.5, "vinyl": 0.09},
    # ── Acoustic / classical ─────────────────────────────────────────────────
    "piano_lofi":    {"lpf": 14000, "bits": 14, "room": 0.45,"wet": 0.25, "chorus_depth": 0.08, "compress_ratio": 1.8, "vinyl": 0.04},
    "lofi_classical":{"lpf": 15000, "bits": 15, "room": 0.50,"wet": 0.28, "chorus_depth": 0.06, "compress_ratio": 1.6, "vinyl": 0.03},
}

_DEFAULT_PRESET = {"lpf": 10000, "bits": 11, "room": 0.40, "wet": 0.22, "chorus_depth": 0.18, "compress_ratio": 2.8, "vinyl": 0.12}

# Genres that use real impulse-response reverb when IR files are present.
# Jazz/piano genres benefit most — acoustic room reflections are more natural than
# algorithmic Schroeder reverb for these instruments.
_IR_GENRES = {"lofi_jazz", "jazz_cafe", "piano_lofi", "lofi_classical", "bossa_lofi", "neo_soul"}
_IR_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "ir")


def apply_lofi_fx(wav_in: str, wav_out: str, sub_genre: str | None = None,
                  bpm: int = 80, energy: str = "medium") -> None:
    """
    Apply lo-fi FX chain using Pedalboard.
    Each sub_genre has distinct settings — dark_lofi sounds gritty and muffled,
    cozy_cafe sounds warm and airy, vaporwave sounds degraded and washed.
    Jazz/piano genres use convolution reverb from real room IRs (assets/ir/) when present.
    Falls back to the legacy ffmpeg chain if pedalboard import fails.
    """
    try:
        _apply_pedalboard(wav_in, wav_out, sub_genre, bpm, energy)
    except ImportError:
        _apply_ffmpeg_fallback(wav_in, wav_out, sub_genre, bpm, energy)


# Stereo width applied after the main FX chain: Pedalboard has no dedicated
# widener plugin, so this is a hand-rolled mid-side technique (M=(L+R)/2,
# S=(L-R)/2, scale S, recombine) -- the chain's only prior stereo-field
# control was Reverb(width=0.7), which shapes the reverb tail only, not the
# dry signal. >1.0 widens, 1.0 is a no-op, kept modest to avoid mono-fold
# phase issues on typical playback systems.
_STEREO_WIDTH_RANGE = (1.05, 1.20)

# Sub-bass warmth/saturation: a parallel-processed, band-limited soft
# distortion mixed back under the low end, approximating the "muffled bass"
# / "distorted sub-bass harmonics" character called out as a lofi production
# staple -- distinct from the main chain's full-band Bitcrush/LowpassFilter,
# which shape the whole mix rather than the bass specifically.
_SUB_BASS_CUTOFF_HZ = 150
_SUB_BASS_DRIVE_DB  = 14.0
_SUB_BASS_MIX       = 0.22

# Genres that benefit from GSM codec degradation (authentic mobile-phone grit)
_GSM_GENRES = {"dark_lofi", "lofi_phonk", "vaporwave", "ambient"}
# Sample-rate target per genre group — lower = more vintage aliasing
_SR_TARGET: dict[str, int] = {
    "dark_lofi": 22050, "lofi_phonk": 22050,
    "vaporwave": 22050, "hip_hop_lofi": 22050,
    "lofi_house": 24000, "chillhop": 24000, "chill_beats": 24000,
    "lo_fi_funk": 24000, "nujabes": 24000,
}
_SR_DEFAULT = 26000  # brighter genres stay at 26kHz


def _apply_pedalboard(wav_in: str, wav_out: str, sub_genre: str | None,
                      bpm: int, energy: str) -> None:
    import numpy as np
    import soundfile as sf
    from pedalboard import (
        Pedalboard, Bitcrush, Compressor, Reverb,
        HighpassFilter, LowpassFilter, Chorus, Gain, Resample,
        GSMFullRateCompressor,
    )

    preset = dict(_GENRE_PRESETS.get(sub_genre or "", _DEFAULT_PRESET))

    # Small random variation within genre character so tracks aren't 100% identical
    lpf      = preset["lpf"]      + random.randint(-400, 400)
    bits     = preset["bits"]     + random.choice([-1, 0, 0, 1])
    room     = min(0.95, preset["room"]     + random.uniform(-0.05, 0.05))
    wet      = min(0.50, preset["wet"]      + random.uniform(-0.03, 0.03))
    depth    = min(0.45, preset["chorus_depth"] + random.uniform(-0.03, 0.03))
    c_ratio  = preset["compress_ratio"]
    vinyl_vol = preset["vinyl"]   + random.uniform(-0.02, 0.02)
    sr_target = _SR_TARGET.get(sub_genre or "", _SR_DEFAULT)

    # Energy scales chorus depth (more wobble = more energy) and compression
    energy_scale = {"low": 0.65, "medium": 1.0, "high": 1.35}.get(energy, 1.0)
    depth  = round(min(0.45, depth * energy_scale), 3)
    c_ratio = c_ratio * energy_scale

    # BPM-aware chorus rate: faster = tighter wobble
    chorus_rate = round(0.35 + (bpm - 70) * 0.008, 2)

    board = Pedalboard([
        HighpassFilter(cutoff_frequency_hz=80),
        Compressor(
            threshold_db=-20,
            ratio=c_ratio,
            attack_ms=10,
            release_ms=200,
        ),
        # Vintage sampler aliasing: downsample to target SR then back up.
        # Fills the gap vs the ffmpeg chain which always did aresample=22050.
        Resample(target_sample_rate=sr_target),
        Bitcrush(bit_depth=max(6, min(16, bits))),
        Chorus(
            rate_hz=chorus_rate,
            depth=depth,
            centre_delay_ms=8.0,
            feedback=0.0,
            mix=0.40,
        ),
        LowpassFilter(cutoff_frequency_hz=max(4000, lpf)),
        Reverb(
            room_size=room,
            damping=0.65,
            wet_level=wet,
            dry_level=1.0 - wet,
            width=0.7,
        ),
        Gain(gain_db=-1.5),
    ])

    audio, sr = sf.read(wav_in, dtype="float32", always_2d=True)
    # Pedalboard expects (channels, samples)
    audio_in = audio.T

    processed = board(audio_in, sr, reset=True)

    # GSM codec artifacts for dark/phonk/vaporwave — old Nokia phone grit.
    # Mixed at 25% wet so it adds texture without demolishing the stereo image.
    if sub_genre in _GSM_GENRES:
        gsm_board = Pedalboard([GSMFullRateCompressor()])
        gsm_out = gsm_board(processed, sr, reset=True)
        processed = processed * 0.75 + gsm_out * 0.25

    # IR convolution reverb for jazz/piano genres — replaces algorithmic Reverb above
    # when real room IR files are present in assets/ir/.
    # 40% wet: adds authentic room acoustics without washing out the dry signal.
    if sub_genre in _IR_GENRES:
        ir_wet = _apply_ir_reverb(processed, sr)
        if ir_wet is not None:
            processed = processed * 0.60 + ir_wet * 0.40

    # Stereo widening (mid-side) -- the main chain above has no dry-signal
    # stereo-field control beyond Reverb's wet-tail width.
    processed = _apply_stereo_width(processed, random.uniform(*_STEREO_WIDTH_RANGE))

    # Sub-bass warmth/saturation, parallel-mixed under the low end.
    processed = _apply_sub_bass_saturation(processed, sr)

    # Add vinyl crackle (white noise shaped like old record surface)
    if vinyl_vol > 0.01:
        crackle = _make_crackle(processed.shape[1], vinyl_vol)
        processed = processed + crackle

    # Normalize to -1dB peak
    peak = np.max(np.abs(processed)) + 1e-9
    if peak > 0.89:
        processed = processed * (0.89 / peak)

    sf.write(wav_out, processed.T, sr, subtype="PCM_16")


def _apply_stereo_width(audio: "np.ndarray", width: float) -> "np.ndarray":
    """
    Mid-side stereo widening. `audio` is (channels, samples). No-op for
    anything other than exactly 2 channels (mono input, or an unexpected
    channel count, both pass through unchanged rather than guessing).
    """
    import numpy as np

    if audio.shape[0] != 2:
        return audio
    left, right = audio[0], audio[1]
    mid  = (left + right) * 0.5
    side = (left - right) * 0.5 * width
    widened_left  = mid + side
    widened_right = mid - side
    return np.stack([widened_left, widened_right])


def _apply_sub_bass_saturation(audio: "np.ndarray", sr: int) -> "np.ndarray":
    """
    Parallel-processed sub-bass warmth: isolate content below
    _SUB_BASS_CUTOFF_HZ with a cheap one-pole lowpass, drive it through soft
    (tanh) saturation, and mix a modest amount back under the full-band
    signal -- approximates "muffled"/"distorted sub-bass" character without
    touching the rest of the frequency spectrum, unlike the main chain's
    full-band Bitcrush/LowpassFilter.
    """
    import numpy as np

    alpha = np.exp(-2.0 * np.pi * _SUB_BASS_CUTOFF_HZ / sr)
    lowpassed = _lfilter([1.0 - alpha], [1.0, -alpha], audio, axis=-1).astype(np.float32)

    drive = 10 ** (_SUB_BASS_DRIVE_DB / 20.0)
    saturated = (np.tanh(lowpassed * drive) / np.tanh(drive)).astype(np.float32)

    return (audio + (saturated - lowpassed) * _SUB_BASS_MIX).astype(np.float32)


def _apply_ir_reverb(audio: "np.ndarray", sr: int) -> "np.ndarray | None":
    """
    Apply convolution reverb using a randomly chosen IR file from assets/ir/.
    Returns the wet signal (same shape as input), or None if no IR files exist
    or audiomentations is unavailable.
    """
    import glob as _glob
    ir_files = _glob.glob(os.path.join(_IR_DIR, "*.wav")) + _glob.glob(os.path.join(_IR_DIR, "*.flac"))
    if not ir_files:
        return None
    try:
        import numpy as np
        from audiomentations import ApplyImpulseResponse
        ir_path = random.choice(ir_files)
        # ApplyImpulseResponse expects (channels, samples) float32 numpy array
        transform = ApplyImpulseResponse(ir_paths=[ir_path], p=1.0, leave_length_unchanged=True)
        wet = transform(audio.copy().astype(np.float32), sample_rate=sr)
        return wet
    except Exception:
        return None


def _make_crackle(n_samples: int, amplitude: float) -> "np.ndarray":
    """Generate sparse vinyl crackle as impulses + pink-ish noise."""
    import numpy as np
    noise = np.random.randn(n_samples).astype(np.float32)
    # 1-pole LP at ~1kHz via scipy (54× faster than Python loop for long audio)
    alpha = 0.92
    noise = _lfilter([1.0 - alpha], [1.0, -alpha], noise).astype(np.float32)
    # Sparse crackle impulses (pops)
    n_pops = max(1, int(n_samples / 44100 * random.randint(3, 12)))
    for _ in range(n_pops):
        pos = random.randint(0, n_samples - 1)
        width = random.randint(2, 8)
        noise[pos:pos + width] += random.uniform(0.3, 0.9)
    return noise.reshape(1, -1) * amplitude


def _apply_ffmpeg_fallback(wav_in: str, wav_out: str, sub_genre: str | None,
                           bpm: int, energy: str) -> None:
    """Legacy ffmpeg chain — only used if pedalboard is not installed."""
    import subprocess, random as _r

    bits     = _r.choice([10, 11, 12])
    lpf      = _r.randint(8500, 11000)
    bpm_scale = 80.0 / max(60, bpm)
    echo_d1  = max(20, int(35 * bpm_scale))
    echo_d2  = max(40, int(65 * bpm_scale))
    vinyl_amp = round(_r.uniform(0.025, 0.055), 3)
    vinyl_vol = round(_r.uniform(0.10, 0.20), 3)

    filt = (
        f"aresample=22050,"
        f"acrusher=bits={bits}:mode=lin:aa=1,"
        f"acompressor=threshold=0.3:ratio=3:attack=10:release=200,"
        f"atremolo=f=4.5:d=0.10,"
        f"lowpass=f={lpf}:poles=2,"
        f"aecho=0.8:0.6:{echo_d1}|{echo_d2}:0.3|0.2,"
        f"volume=0.85"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", wav_in, "-af", filt, wav_out],
        check=True, capture_output=True,
    )
