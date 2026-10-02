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
pitch relationships (and therefore the "detuned" character) unchanged. What
this module DOES add, as a genuine mix-bus effect (see _apply_wow_flutter),
is tape wow & flutter -- real transport-speed modulation via a variable-delay
line, not per-note detuning, but the same "not quite in tune with itself"
territory and, unlike per-note detune, entirely legitimate to add post-render.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:   # annotations only; numpy is imported where it's used
    import numpy as np

import random
import os
from scipy.signal import lfilter as _lfilter, resample_poly as _resample_poly

from scripts import genre_presets

# Per-genre FX presets — tuned to feel different, not just be different numbers
# lpf: Moog ladder LPF cutoff Hz (lower = more muffled/vintage)
# bits: bitcrusher depth (lower = more grit, 8=MPC2000, 12=Akai S950, 16=clean)
# room: reverb room size 0-1
# wet: reverb wet mix
# wobble_depth: tape wobble amount 0-1
# compress_ratio: compression ratio
# vinyl: vinyl crackle amplitude
# Loaded from config/genres/*.yaml (see scripts/genre_presets.py).
_GENRE_PRESETS: dict[str, dict] = genre_presets.build_genre_fx_presets()

_DEFAULT_PRESET = {"lpf": 10000, "bits": 11, "room": 0.40, "wet": 0.22, "wobble_depth": 0.18, "compress_ratio": 2.8, "vinyl": 0.12}

# Genres that use real impulse-response reverb when IR files are present.
# Jazz/piano genres benefit most — acoustic room reflections are more natural than
# algorithmic Schroeder reverb for these instruments.
#
# The room impulses are synthesized (see _synthesize_room_ir), like the
# plate: no third-party impulse files, so no redistribution terms to meet.
# Convolution is done with scipy (see _convolve_ir).
_IR_GENRES = genre_presets.build_ir_genres()
_IR_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "ir")

# Genres that want a kick-triggered sidechain "pump" (see
# _apply_kick_sidechain_duck) — a standard house/hip-hop mix technique, but
# wrong for anything meant to sound spacious/acoustic/unpumped. Most genres
# do NOT want this, matching the existing _GSM_GENRES/_IR_GENRES pattern of
# a small opt-in membership set rather than a per-preset flag on all 22
# entries in _GENRE_PRESETS.
_SIDECHAIN_DUCK_GENRES = genre_presets.build_sidechain_duck_genres()
# {genre_key: 'house' | 'hiphop'} for genres in _SIDECHAIN_DUCK_GENRES --
# which duck character each wants (see _DUCK_PROFILES near
# _apply_kick_sidechain_duck for the attack/release/depth values).
_DUCK_PROFILES_BY_GENRE = genre_presets.build_duck_profiles()

# Per-track mastering LUFS target (see _apply_lufs_mastering). Deliberately
# set BELOW assemble_video.py's final video-level loudnorm target of -14
# LUFS (assemble_video.py's `loudnorm=I=-14:LRA=11:TP=-1` pass) so the two
# normalization stages cooperate instead of fighting: that pass runs once,
# on the assembled video's mixed-down audio (which can layer this track
# with others / narration / SFX), and ffmpeg's loudnorm filter is a genuine
# two-pass dynamics processor with a true-peak limiter, not just a gain
# trim. If a per-track pass already pushed hard to -14 LUFS, summing
# several such tracks could push true peaks over the limiter's ceiling
# before it can react cleanly, or leave loudnorm nothing to work with.
# Targeting a conservative few LU under (-17) keeps each track's own
# dynamics/peaks sane and leaves headroom for the video-level pass to do
# its job without needing to pull level down hard (audible pumping).
# Matches track_quality.py's AUDIO_LUFS_TARGET_DEFAULT — kept as two
# independently-set constants (mastering here targets it; the quality gate
# there only sanity-checks it, generously) rather than a cross-module
# import, to keep track_quality.py's MIDI/audio-gate logic decoupled from
# this FX-chain module's dependencies.
_TRACK_LUFS_TARGET = -17.0


def apply_lofi_fx(wav_in: str, wav_out: str, sub_genre: str | None = None,
                  bpm: int = 80, energy: str = "medium",
                  transitions: list[tuple[int, str]] | None = None) -> None:
    """
    Apply lo-fi FX chain using Pedalboard.
    Each sub_genre has distinct settings — dark_lofi sounds gritty and muffled,
    cozy_cafe sounds warm and airy, vaporwave sounds degraded and washed.
    Jazz/piano genres use convolution reverb from real room IRs (assets/ir/) when present.
    Falls back to the legacy ffmpeg chain if pedalboard import fails.

    `transitions`: optional list of (sample_position, fx_name) from
    composer.build_midi()'s section_transitions return value
    (see section_transition_fx_for) -- ignored by the ffmpeg fallback, which
    is a bare-bones legacy path with no numpy-array FX of its own.
    """
    try:
        _apply_pedalboard(wav_in, wav_out, sub_genre, bpm, energy, transitions=transitions)
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
_GSM_GENRES = {"dark_lofi", "lofi_phonk", "vaporwave", "ambient", "lofi_drill"}
# Sample-rate target per genre group — lower = more vintage aliasing
_SR_TARGET: dict[str, int] = {
    "dark_lofi": 22050, "lofi_phonk": 22050,
    "vaporwave": 22050, "hip_hop_lofi": 22050, "lofi_drill": 22050,
    "lofi_house": 24000, "chillhop": 24000, "chill_beats": 24000,
    "lo_fi_funk": 24000, "nujabes": 24000,
}
_SR_DEFAULT = 26000  # brighter genres stay at 26kHz


def _apply_pedalboard(wav_in: str, wav_out: str, sub_genre: str | None,
                      bpm: int, energy: str,
                      transitions: list[tuple[int, str]] | None = None) -> None:
    import numpy as np
    import soundfile as sf
    from pedalboard import (
        Pedalboard, Bitcrush, Compressor, Reverb,
        HighpassFilter, LowpassFilter, Gain, Resample,
        GSMFullRateCompressor, PeakFilter,
    )

    preset = dict(_GENRE_PRESETS.get(sub_genre or "", _DEFAULT_PRESET))

    # Small random variation within genre character so tracks aren't 100% identical
    lpf      = preset["lpf"]      + random.randint(-400, 400)
    bits     = preset["bits"]     + random.choice([-1, 0, 0, 1])
    room     = min(0.95, preset["room"]     + random.uniform(-0.05, 0.05))
    wet      = min(0.50, preset["wet"]      + random.uniform(-0.03, 0.03))
    depth    = min(0.45, preset["wobble_depth"] + random.uniform(-0.03, 0.03))
    c_ratio  = preset["compress_ratio"]
    vinyl_vol = preset["vinyl"]   + random.uniform(-0.02, 0.02)
    presence_db = preset.get("presence_db", 0.0)
    warmth_db   = preset.get("warmth_db", 0.0)
    sr_target = _SR_TARGET.get(sub_genre or "", _SR_DEFAULT)

    # Energy scales wow/flutter depth (more wobble = more energy) and compression
    energy_scale = {"low": 0.65, "medium": 1.0, "high": 1.35}.get(energy, 1.0)
    depth  = round(min(0.45, depth * energy_scale), 3)
    c_ratio = c_ratio * energy_scale

    # Full-band tape saturation wet mix (research/theory/mixing-texture.md
    # item 6): derived from the genre's existing "grit" signal (lower
    # bitcrush bits / lower lowpass cutoff both already vary by genre, dark/
    # hip-hop genres already sitting lower on both per item 8's analysis)
    # rather than a new hardcoded genre list -- boom-bap-leaning genres land
    # near 20% wet, clean/ambient genres near 5%.
    _bits_grit = 1.0 - (bits - 6) / (16 - 6)
    _lpf_grit  = 1.0 - min(1.0, max(0.0, (lpf - 4000) / (12000 - 4000)))
    _grit = max(0.0, min(1.0, (_bits_grit + _lpf_grit) / 2))
    tape_sat_mix = 0.05 + _grit * (0.20 - 0.05)

    # Chain is split around _apply_wow_flutter (a hand-rolled variable-delay
    # effect, not a Pedalboard plugin — Pedalboard has no wow/flutter unit)
    # so it sits in the same signal-chain position the old Chorus stage did:
    # after the bitcrush/resample grit, before the lowpass/reverb tail.
    board_pre = Pedalboard([
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
    ])
    board_post = Pedalboard([
        LowpassFilter(cutoff_frequency_hz=max(4000, lpf)),
        Reverb(
            room_size=room,
            damping=0.65,
            wet_level=wet,
            dry_level=1.0 - wet,
            width=0.7,
        ),
        # Per-subgenre EQ conventions (research/theory/mixing-texture.md
        # item 8): presence_db is a 3-5kHz cut (boom-bap/hip-hop genres get
        # a small negative value to tame digital harshness), warmth_db is a
        # 100-200Hz boost (same genres). Both default to 0.0 (no-op
        # PeakFilter) for any genre that doesn't set them.
        PeakFilter(cutoff_frequency_hz=4000, gain_db=presence_db, q=1.0),
        PeakFilter(cutoff_frequency_hz=150,  gain_db=warmth_db,   q=0.9),
        Gain(gain_db=-1.5),
    ])

    audio, sr = sf.read(wav_in, dtype="float32", always_2d=True)
    # Pedalboard expects (channels, samples)
    audio_in = audio.T

    processed = board_pre(audio_in, sr, reset=True)
    processed = _apply_wow_flutter(processed, sr, depth)
    # Static tape-head EQ coloration, distinct from the time-varying
    # wow/flutter modulation just above (research/theory/mixing-texture.md
    # item 1's second finding) -- same "tape transport character" family,
    # applied together before the broader lowpass/reverb shaping below.
    processed = _apply_head_bump(processed, sr, depth)
    processed = board_post(processed, sr, reset=True)

    # GSM codec artifacts for dark/phonk/vaporwave — old Nokia phone grit.
    # Mixed at 25% wet so it adds texture without demolishing the stereo image.
    if sub_genre in _GSM_GENRES:
        gsm_board = Pedalboard([GSMFullRateCompressor()])
        gsm_out = gsm_board(processed, sr, reset=True)
        processed = processed * 0.75 + gsm_out * 0.25

    # IR convolution reverb for jazz/piano genres (room/hall character) and
    # boom-bap/hip-hop-lofi genres (procedural plate character, see
    # _PLATE_IR_GENRES) — replaces algorithmic Reverb above when a genre-
    # appropriate IR is present in assets/ir/. 40% wet: adds authentic
    # room/hardware-reverb acoustics without washing out the dry signal.
    if sub_genre in _IR_GENRES or sub_genre in _PLATE_IR_GENRES:
        ir_wet = _apply_ir_reverb(processed, sr, sub_genre=sub_genre)
        if ir_wet is not None:
            processed = processed * 0.60 + ir_wet * 0.40

    # Gated reverb -- 80s-drum-machine punch for lofi_synthwave specifically
    # (see _GATED_REVERB_GENRES / _apply_gated_reverb).
    if sub_genre in _GATED_REVERB_GENRES:
        processed = _apply_gated_reverb(processed, sr)

    # Section-boundary transition FX (research/theory/arrangement-structure.md
    # gap #1) -- each entry is (sample_position, fx_name), computed by
    # build_midi() from the track's actual song-form section boundaries via
    # section_transition_fx_for(). Applied here, before the polish stages
    # below (stereo width/sub-bass/tape-saturation/sidechain/crackle/
    # mastering), same chain position as gated reverb just above -- these
    # are structural/arrangement effects, not final polish, so everything
    # after this point (including LUFS mastering) measures/acts on the
    # fully-arranged signal. Each FX function clamps its own sample
    # position internally, so an out-of-range entry is a silent no-op
    # rather than a crash.
    if transitions:
        for _at_sample, _fx_name in transitions:
            if _fx_name == 'vinyl_stop':
                processed = _apply_vinyl_stop(processed, sr, _at_sample)
            elif _fx_name == 'reverse_riser':
                processed = _apply_reverse_riser(processed, sr, _at_sample)
            elif _fx_name == 'filter_lowpass_sweep':
                processed = _apply_filter_sweep(processed, sr, _at_sample, direction='down')

    # Stereo widening (mid-side) -- the main chain above has no dry-signal
    # stereo-field control beyond Reverb's wet-tail width.
    processed = _apply_stereo_width(processed, random.uniform(*_STEREO_WIDTH_RANGE))

    # Sub-bass warmth/saturation, parallel-mixed under the low end.
    processed = _apply_sub_bass_saturation(processed, sr)

    # Full-band tape saturation (research/theory/mixing-texture.md item 6)
    # -- genuinely distinct in scope from the sub-bass-only stage just
    # above (full spectrum vs. <150Hz); mix % derived from genre grit, see
    # tape_sat_mix above.
    processed = _apply_tape_saturation(processed, sr, tape_sat_mix)

    # Kick-triggered sidechain "pump" -- gated per-genre (see
    # _SIDECHAIN_DUCK_GENRES) with a genre-appropriate profile (see
    # _DUCK_PROFILES_BY_GENRE / _DUCK_PROFILES: house wants an audible
    # pump, hip-hop wants the duck inaudible-as-an-effect). Applied before
    # the vinyl crackle layer (crackle shouldn't itself get ducked) and
    # before LUFS mastering (so loudness is measured/targeted on the final
    # dynamics, not pre-duck).
    if sub_genre in _SIDECHAIN_DUCK_GENRES:
        duck_profile = _DUCK_PROFILES_BY_GENRE.get(sub_genre, 'hiphop')
        processed = _apply_kick_sidechain_duck(processed, sr, profile=duck_profile)

    # Add vinyl crackle (white noise shaped like old record surface)
    if vinyl_vol > 0.01:
        crackle = _make_crackle(processed.shape[1], vinyl_vol, sr)
        processed = processed + crackle

    # Multiband + parallel mastering glue (see _apply_multiband_glue) --
    # runs before the LUFS/peak-ceiling stage below, matching the
    # "multiband after EQ, before the limiter" mastering-chain convention.
    processed = _apply_multiband_glue(processed, sr)

    # Per-track mastering: target a conservative LUFS level (see
    # _TRACK_LUFS_TARGET for why -17 and not -14) rather than only
    # peak-normalizing. Supplements, not replaces, the peak-safety ceiling
    # immediately below -- LUFS targeting controls overall perceived
    # loudness, the peak ceiling is a hard clip-safety net for any track
    # whose transients are peaky enough to exceed 0dBFS even at a
    # conservative integrated loudness.
    processed = _apply_lufs_mastering(processed, sr)

    # Final peak-safety ceiling: -1.5 dBFS sample peak, so inter-sample peaks
    # after AAC encoding stay under YouTube's -1 dBTP.
    peak = np.max(np.abs(processed)) + 1e-9
    ceiling = 10 ** (-1.5 / 20)
    if peak > ceiling:
        processed = processed * (ceiling / peak)

    sf.write(wav_out, processed.T, sr, subtype="PCM_16")


# ── Tape wow & flutter ───────────────────────────────────────────────────────
# Two LFOs modulate a fractional-sample variable-delay line: "wow" is slow
# drift from uneven reel/capstan rotation (real tape: roughly 0.5-2 Hz),
# "flutter" is faster jitter from transport mechanics (roughly 4-10 Hz).
# These are transport-speed artifacts, not tempo-linked, so — unlike the old
# Chorus stage's bpm-aware rate — there's no bpm dependence here.
_WOW_HZ_RANGE     = (0.6, 1.4)
_FLUTTER_HZ_RANGE = (5.0, 9.0)
_WOW_FLUTTER_MIX  = 0.65   # wow (slow) vs flutter (fast) blend, wow-dominant

# %WRMS (weighted RMS speed deviation, DIN/NAB/CCIR/JIS standard) anchor
# points for the depth mapping below -- research/theory/mixing-texture.md
# item 1. Real specs: hi-fi cassette decks <=+-0.2% WRMS, non-hi-fi cassette
# <=+-0.4%, a studio reel-to-reel (Otari MX5050-III-2 @ 15ips) ~0.09%,
# consumer reel-to-reel (60s/70s @ 7.5ips) ~0.25%. "Clean" preset character
# anchors to the hi-fi/studio end; "gritty consumer cassette" anchors to the
# non-hi-fi end.
_WRMS_CLEAN_PCT  = 0.125   # midpoint of 0.1-0.15% WRMS
_WRMS_GRITTY_PCT = 0.35    # midpoint of 0.3-0.4% WRMS
# %WRMS translates to raw peak pitch/speed deviation at roughly 2-3x the RMS
# figure (real-world tape-spec convention cited in the research) -- use the
# midpoint of that cited range.
_WRMS_TO_PEAK_RATIO = 2.5


def _wow_flutter_depth_ms(depth: float) -> float:
    """
    Map the genre preset's 0-0.45 wobble_depth knob onto a %WRMS-anchored
    delay-line depth in ms, instead of the previous flat, unanchored
    0.5-3.5ms curve (research/theory/mixing-texture.md item 1: "the depth
    range isn't anchored to any real spec").

    `depth` linearly selects a %WRMS value between the clean and gritty
    anchor points above, converts to peak speed deviation via
    _WRMS_TO_PEAK_RATIO, then maps that onto ms -- calibrated so gritty-
    cassette character (depth near 0.45) lands in the same ms ballpark the
    prior flat mapping's upper end did (the research doc's own cross-check:
    ~0.3-0.4% WRMS implies ~0.8-1.2% peak deviation, "the same ballpark the
    code already targets"). The audible result is intentionally similar to
    before -- what changes is that the curve is now derived from a
    documented real-world spec instead of being an arbitrary constant.
    """
    d = min(0.45, max(0.0, depth))
    wrms_pct = _WRMS_CLEAN_PCT + (d / 0.45) * (_WRMS_GRITTY_PCT - _WRMS_CLEAN_PCT)
    peak_pct = wrms_pct * _WRMS_TO_PEAK_RATIO
    peak_pct_min = _WRMS_CLEAN_PCT * _WRMS_TO_PEAK_RATIO
    peak_pct_max = _WRMS_GRITTY_PCT * _WRMS_TO_PEAK_RATIO
    frac = (peak_pct - peak_pct_min) / (peak_pct_max - peak_pct_min)
    return 0.5 + max(0.0, min(1.0, frac)) * 3.0


def _apply_wow_flutter(audio: "np.ndarray", sr: int, depth: float) -> "np.ndarray":
    """
    `audio` is (channels, samples). `depth` is the genre preset's
    wobble_depth value (0-0.45, already energy-scaled by the caller) —
    mapped to a %WRMS-anchored modulation depth via _wow_flutter_depth_ms()
    (see that function for the real-tape-spec derivation).

    Implementation: offset the read position (in fractional samples) by the
    wow+flutter LFO blend, then linearly interpolate the signal at that
    position — a variable-delay line, the standard way to implement this
    effect. Fully vectorized (no per-sample Python loop) via numpy fancy
    indexing for the interpolation gather.
    """
    import numpy as np

    n_samples = audio.shape[1]
    if n_samples < 4:
        return audio

    depth_ms = _wow_flutter_depth_ms(depth)
    depth_samples = depth_ms / 1000.0 * sr

    wow_hz     = random.uniform(*_WOW_HZ_RANGE)
    flutter_hz = random.uniform(*_FLUTTER_HZ_RANGE)
    t = np.arange(n_samples, dtype=np.float64) / sr
    wow     = np.sin(2 * np.pi * wow_hz * t + random.uniform(0, 2 * np.pi))
    flutter = np.sin(2 * np.pi * flutter_hz * t + random.uniform(0, 2 * np.pi))
    mod = (_WOW_FLUTTER_MIX * wow + (1.0 - _WOW_FLUTTER_MIX) * flutter) * depth_samples

    # Offset into the past (a delay line reads history, never the future) so
    # the modulation never needs samples that don't exist yet -- shift the
    # whole curve back by its own max depth so the read index stays
    # non-negative even at the wow/flutter blend's most negative excursion.
    read_idx = np.arange(n_samples, dtype=np.float64) - depth_samples - mod
    read_idx = np.clip(read_idx, 0, n_samples - 1)
    idx_floor = np.floor(read_idx).astype(np.int64)
    idx_ceil  = np.minimum(idx_floor + 1, n_samples - 1)
    frac = (read_idx - idx_floor).astype(np.float32)

    out = np.empty_like(audio)
    for ch in range(audio.shape[0]):
        out[ch] = audio[ch, idx_floor] * (1.0 - frac) + audio[ch, idx_ceil] * frac
    return out.astype(np.float32)


# ── Section-boundary transition FX ───────────────────────────────────────────
# research/theory/arrangement-structure.md: vinyl stop / reverse riser /
# filter sweep, the standard lofi/hip-hop section-transition vocabulary,
# previously entirely unmodeled anywhere in this codebase. Each function
# applies its effect to a short window of `audio` ending at `at_sample` (the
# section-boundary point) -- content at/after `at_sample` is left untouched
# so the next section picks up normally; only the window leading into the
# boundary is affected. See composer.py's
# _SECTION_TRANSITION_FX for which effect pairs with which section-boundary
# label pair, and that module's note on the remaining per-track pipeline
# wiring (converting a section's bar offset to `at_sample` and calling
# these) is not done yet.

def _apply_vinyl_stop(audio: "np.ndarray", sr: int, at_sample: int,
                      duration_s: float = 0.6) -> "np.ndarray":
    """
    Record-player-losing-power effect: the `duration_s` window ending at
    `at_sample` is read at a progressively slowing rate (playback speed
    eases from 1.0 down to ~0.15 -- real vinyl physics pulls pitch AND
    tempo down together, not just a volume fade), via the same fractional-
    sample variable-delay-line interpolation _apply_wow_flutter uses,
    fading to near-silence over the final ~15% of the window (the needle
    lifting). Audio at/after `at_sample` is untouched -- the next section
    resumes normally, this only affects the hand-off into it.
    """
    import numpy as np

    n_samples = audio.shape[1]
    at_sample = max(0, min(n_samples, at_sample))
    win = min(int(duration_s * sr), at_sample)
    if win < 4:
        return audio

    start = at_sample - win
    out = audio.copy()

    # Speed curve: 1.0 (normal) at window start -> ~0.15 (nearly stopped) at
    # at_sample, eased (not linear) so the slowdown accelerates toward the
    # end, matching how a stopping turntable actually decelerates.
    t = np.linspace(0.0, 1.0, win, dtype=np.float64)
    speed = 1.0 - 0.85 * (t ** 2)
    read_pos = start + np.cumsum(speed)
    read_pos = np.clip(read_pos, 0, n_samples - 1)
    idx_floor = np.floor(read_pos).astype(np.int64)
    idx_ceil  = np.minimum(idx_floor + 1, n_samples - 1)
    frac = (read_pos - idx_floor).astype(np.float32)

    fade_len = max(1, int(win * 0.15))
    fade = np.concatenate([np.ones(win - fade_len, dtype=np.float32),
                           np.linspace(1.0, 0.0, fade_len, dtype=np.float32)])

    for ch in range(audio.shape[0]):
        stretched = audio[ch, idx_floor] * (1.0 - frac) + audio[ch, idx_ceil] * frac
        out[ch, start:at_sample] = stretched * fade
    return out.astype(np.float32)


def _apply_reverse_riser(audio: "np.ndarray", sr: int, at_sample: int,
                         duration_s: float = 1.0, amplitude: float = 0.25) -> "np.ndarray":
    """
    Reversed filtered-noise swell building INTO the transition point: a
    highpassed noise burst whose amplitude ramps up from silence to
    `amplitude` across `duration_s`, landing right at `at_sample` -- the
    standard hip-hop/electronic "riser" pulling the listener into the next
    section, added under (not replacing) the existing audio in that window.
    """
    import numpy as np

    n_samples = audio.shape[1]
    at_sample = max(0, min(n_samples, at_sample))
    win = min(int(duration_s * sr), at_sample)
    if win < 4:
        return audio

    start = at_sample - win
    noise = np.random.randn(win).astype(np.float32)
    # Highpass (remove content below ~800Hz) for the bright "swoosh"
    # character risers conventionally have, via the same one-pole technique
    # used elsewhere in this module (here as a high-pass: signal minus its
    # own lowpassed version).
    alpha = float(np.exp(-2.0 * np.pi * 800.0 / sr))
    lowpassed = _lfilter([1.0 - alpha], [1.0, -alpha], noise).astype(np.float32)
    highpassed = noise - lowpassed

    ramp = np.linspace(0.0, 1.0, win, dtype=np.float32) ** 1.5   # accelerating build
    riser = highpassed * ramp * amplitude

    out = audio.copy()
    for ch in range(audio.shape[0]):
        out[ch, start:at_sample] = out[ch, start:at_sample] + riser
    return out.astype(np.float32)


def _apply_filter_sweep(audio: "np.ndarray", sr: int, at_sample: int,
                        duration_s: float = 1.5, direction: str = "down") -> "np.ndarray":
    """
    Automated lowpass-cutoff sweep leading into the transition point:
    `direction='down'` (the common breakdown-entry sweep) ramps the cutoff
    from wide-open down to a muffled ~400Hz by `at_sample`; `'up'` does the
    reverse (building out of a breakdown). Block-based (not a continuously
    modulated single filter) -- short overlapping chunks each get their own
    static one-pole lowpass coefficient and are crossfaded, a simpler and
    more numerically robust approximation of a swept filter than modulating
    IIR coefficients sample-by-sample.
    """
    import numpy as np

    n_samples = audio.shape[1]
    at_sample = max(0, min(n_samples, at_sample))
    win = min(int(duration_s * sr), at_sample)
    if win < 64:
        return audio

    start = at_sample - win
    n_blocks = max(4, win // 1024)
    block_len = win // n_blocks
    cutoffs = np.linspace(12000.0, 400.0, n_blocks)
    if direction == "up":
        cutoffs = cutoffs[::-1]

    out = audio.copy()
    for ch in range(audio.shape[0]):
        segment = audio[ch, start:start + block_len * n_blocks].copy()
        filtered = np.empty_like(segment)
        for b in range(n_blocks):
            lo, hi = b * block_len, (b + 1) * block_len
            alpha = float(np.exp(-2.0 * np.pi * cutoffs[b] / sr))
            filtered[lo:hi] = _lfilter([1.0 - alpha], [1.0, -alpha], segment[lo:hi])
        out[ch, start:start + block_len * n_blocks] = filtered
    return out.astype(np.float32)


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


def _apply_head_bump(audio: "np.ndarray", sr: int, wobble_depth: float) -> "np.ndarray":
    """
    Static (non-time-varying) resonant EQ boost around 50-70Hz simulating
    tape playback "head bump" -- real tape-head pole-piece/gap-length
    geometry interacting with wavelengths near the gap length (research/
    theory/mixing-texture.md item 1), a currently-missing effect distinct
    from the time-varying wow/flutter modulation above.

    Center frequency/gain are implied by the same wobble_depth the genre
    preset already sets: a higher wobble depth implies a lower/more
    consumer-grade implied tape speed, whose head bump sits lower (nearer
    50Hz) and more pronounced (nearer +4dB) than a cleaner, higher-speed
    transport's (nearer 70Hz / +2dB).
    """
    from pedalboard import Pedalboard, PeakFilter

    d = min(0.45, max(0.0, wobble_depth))
    center_hz = 70.0 - (d / 0.45) * 20.0   # clean (d~0) -> 70Hz, gritty (d~0.45) -> 50Hz
    gain_db   = 2.0 + (d / 0.45) * 2.0     # +2dB clean -> +4dB gritty
    board = Pedalboard([PeakFilter(cutoff_frequency_hz=center_hz, gain_db=gain_db, q=1.2)])
    return board(audio, sr, reset=True)


# Full-band tape saturation: gentler drive than the sub-bass-only stage
# since it's applied across the whole spectrum, not a band-limited signal.
_TAPE_SATURATION_DRIVE_DB   = 8.0
_TAPE_SATURATION_OVERSAMPLE = 2


def _apply_tape_saturation(audio: "np.ndarray", sr: int, mix: float) -> "np.ndarray":
    """
    Full-band tape saturation -- a genuinely distinct effect from
    _apply_sub_bass_saturation (band-limited to <150Hz): tape's magnetic
    hysteresis behaves as a broadly symmetric soft clipper (tanh-like),
    producing mostly odd harmonics that read as warmth/presence rather than
    "buzz," unlike tube saturation's asymmetric even-harmonic character
    (research/theory/mixing-texture.md item 6). Same tanh-drive pattern as
    the sub-bass function, but applied full-spectrum instead of pre-filtered.

    `mix` is the wet blend (0-1) -- research doc: ~10-20% for boom-bap-
    leaning genres, ~5-10% for ambient/piano genres; the caller decides
    which based on genre.

    Full-band waveshaping can generate harmonics above Nyquist that alias
    back as inharmonic noise -- the sub-bass function mostly dodges this by
    only driving already-lowpassed content, so this one oversamples 2x
    (polyphase resampling) before the tanh nonlinearity and downsamples
    back afterward, specifically to avoid that.
    """
    import numpy as np

    if mix <= 0.0:
        return audio

    up = _resample_poly(audio, _TAPE_SATURATION_OVERSAMPLE, 1, axis=-1)
    drive = 10 ** (_TAPE_SATURATION_DRIVE_DB / 20.0)
    saturated_up = (np.tanh(up * drive) / np.tanh(drive)).astype(np.float32)
    saturated = _resample_poly(saturated_up, 1, _TAPE_SATURATION_OVERSAMPLE, axis=-1)

    # resample_poly's up/down round-trip can differ by a sample or two from
    # the input length -- trim/pad so the blend below stays sample-aligned.
    n = audio.shape[-1]
    if saturated.shape[-1] > n:
        saturated = saturated[..., :n]
    elif saturated.shape[-1] < n:
        pad = n - saturated.shape[-1]
        saturated = np.pad(saturated, ((0, 0), (0, pad)), mode='edge')

    return (audio * (1.0 - mix) + saturated * mix).astype(np.float32)


# ── Per-track LUFS mastering ─────────────────────────────────────────────────

_LUFS_MAX_GAIN_DB = 12.0   # cap so a bad/edge-case measurement can't apply a wild correction


def _apply_lufs_mastering(audio: "np.ndarray", sr: int,
                          target_lufs: float = _TRACK_LUFS_TARGET) -> "np.ndarray":
    """
    Measure integrated loudness (pyloudnorm, MIT license) and apply a single
    broadband gain to bring the track to `target_lufs` -- this REPLACES the
    old peak-only normalization as the primary loudness decision; the
    peak-safety ceiling still applied right after this in _apply_pedalboard
    is now just a clip-safety net, not the loudness target itself.

    `audio` is (channels, samples) (this module's convention throughout,
    matching Pedalboard); pyloudnorm expects (samples,) or
    (samples, channels), so the array is transposed for measurement only.

    Falls back to a no-op (returning `audio` unchanged) if pyloudnorm is
    unavailable, or the measurement isn't usable (e.g. -inf integrated
    loudness for near-silent audio) -- the caller's peak-normalize step
    still runs afterward either way, so a track is never left un-normalized.
    """
    import numpy as np
    try:
        import pyloudnorm as pyln
    except ImportError:
        return audio

    audio_for_meter = audio.T.astype(np.float64)
    try:
        meter = pyln.Meter(sr)
        loudness = meter.integrated_loudness(audio_for_meter)
    except Exception:
        return audio
    if loudness is None or not np.isfinite(loudness):
        return audio

    gain_db = max(-_LUFS_MAX_GAIN_DB, min(_LUFS_MAX_GAIN_DB, target_lufs - loudness))
    gain_linear = 10 ** (gain_db / 20.0)
    return (audio * gain_linear).astype(np.float32)


# ── Multiband + parallel mastering-chain compression ─────────────────────────
# A 2-band crossover at 120-200Hz (isolating kick/bass from everything above) is a
# common mastering-chain multiband setup, used as a problem-solving/glue
# tool after EQ and before the limiter -- here, before the LUFS-mastering +
# peak-ceiling stage that already plays that "limiter" role. Parallel
# compression (blending a compressed copy back under the dry signal) adds
# density without fully sacrificing transient dynamics. NOTE: unlike
# presence_db/warmth_db, the research found no genre-specific guidance for
# these parameters -- applied gently/universally (light ratios, modest
# parallel blend) as a subtle mastering "glue" rather than genre-tuned;
# real listening-test iteration to differentiate by genre is legitimate
# follow-up work, flagged rather than guessed at here.
_MULTIBAND_CROSSOVER_HZ = 150.0


def _apply_multiband_glue(audio: "np.ndarray", sr: int,
                          low_ratio: float = 3.0, high_ratio: float = 2.0,
                          parallel_mix: float = 0.25) -> "np.ndarray":
    """
    Split at _MULTIBAND_CROSSOVER_HZ, compress each band independently
    (Pedalboard Compressor), recombine, then parallel-blend the compressed
    signal back under the original dry signal at `parallel_mix`.
    """
    import numpy as np
    from pedalboard import Pedalboard, Compressor
    from scipy.signal import butter, sosfilt

    sos_low = butter(2, _MULTIBAND_CROSSOVER_HZ, btype='lowpass', fs=sr, output='sos')
    low_band = sosfilt(sos_low, audio, axis=-1).astype(np.float32)
    high_band = (audio - low_band).astype(np.float32)

    low_board = Pedalboard([Compressor(threshold_db=-18, ratio=low_ratio,
                                        attack_ms=15, release_ms=150)])
    high_board = Pedalboard([Compressor(threshold_db=-16, ratio=high_ratio,
                                         attack_ms=8, release_ms=120)])

    low_compressed = low_board(low_band, sr, reset=True)
    high_compressed = high_board(high_band, sr, reset=True)
    compressed = low_compressed + high_compressed

    return (audio * (1.0 - parallel_mix) + compressed * parallel_mix).astype(np.float32)


# ── Kick-triggered sidechain ducking ─────────────────────────────────────────

_DUCK_KICK_BAND_HZ   = (45.0, 120.0)  # kick fundamental range
_DUCK_TRIGGER_FRAC   = 0.22           # fraction of the kick envelope's own peak needed to trigger

# Two duck profiles instead of one shared hardcoded triple (research/theory/
# mixing-texture.md item 4): house wants an audible rhythmic pump (slower
# release, deeper duck, commonly timed to a quarter note); hip-hop wants the
# duck inaudible-as-an-effect, just kick/bass punch and separation (fast
# attack, much shorter release, shallower duck). 'hiphop' also serves as the
# fallback for any genre that opts into sidechain_duck without picking a
# profile (see genre_presets.build_duck_profiles()), matching this module's
# original single hardcoded character.
_DUCK_PROFILES: dict[str, dict[str, float]] = {
    'house':  {'attack_ms': 2.0, 'release_ms': 200.0, 'duck_db': 5.5},
    'hiphop': {'attack_ms': 3.0, 'release_ms': 60.0,  'duck_db': 2.5},
}


def _kick_envelope(mono: "np.ndarray", sr: int, attack_ms: float, release_ms: float) -> "np.ndarray":
    """
    Fast-attack/slow-release envelope of the kick-band content in `mono`:
    bandpass to the kick fundamental range, rectify, then take the
    per-sample MAX of two one-pole lowpass filters with different time
    constants (a fully-vectorized, well-known trick for an asymmetric
    attack/release envelope follower without a per-sample Python loop --
    the fast filter tracks the rising transient quickly, the slow filter
    holds the level up during the transient's decay).
    """
    import numpy as np
    from scipy.signal import butter, sosfilt

    low_hz, high_hz = _DUCK_KICK_BAND_HZ
    sos = butter(2, [low_hz, high_hz], btype='bandpass', fs=sr, output='sos')
    band = sosfilt(sos, mono)
    rectified = np.abs(band)

    alpha_attack  = np.exp(-1.0 / (attack_ms  / 1000.0 * sr))
    alpha_release = np.exp(-1.0 / (release_ms / 1000.0 * sr))
    fast = _lfilter([1.0 - alpha_attack],  [1.0, -alpha_attack],  rectified)
    slow = _lfilter([1.0 - alpha_release], [1.0, -alpha_release], rectified)
    return np.maximum(fast, slow).astype(np.float32)


def _apply_kick_sidechain_duck(audio: "np.ndarray", sr: int,
                               profile: str = 'hiphop') -> "np.ndarray":
    """
    Self-sidechain "pump": detect kick-band transients from the mix itself
    and duck the FULL mix gain briefly after each one -- the classic
    kick-triggered ducking house/hip-hop producers apply to bass/pads,
    adapted to this pipeline's single mixed-down stereo file (this FX-chain
    stage only ever sees the final render, not isolated stems, so the kick
    "sidechain send" is derived from the mix's own low end rather than a
    real separate kick track). Gated behind a per-genre flag by the caller
    (_SIDECHAIN_DUCK_GENRES) since the pumping character is wrong for
    anything meant to sound spacious/unpumped.

    `profile` selects attack/release/depth from _DUCK_PROFILES ('house' or
    'hiphop' -- see that dict's comment for the genre-convention rationale).

    `audio` is (channels, samples). Returns the same shape.
    """
    import numpy as np

    params = _DUCK_PROFILES.get(profile, _DUCK_PROFILES['hiphop'])
    mono = audio.mean(axis=0)
    envelope = _kick_envelope(mono, sr, params['attack_ms'], params['release_ms'])
    env_peak = float(np.max(envelope)) + 1e-9
    env_norm = envelope / env_peak

    # Below the trigger fraction, no ducking at all -- avoids constant low-level
    # gain wobble from bass/pad energy that happens to sit in the kick band.
    triggered = np.where(env_norm > _DUCK_TRIGGER_FRAC, env_norm, 0.0)
    if not np.any(triggered):
        return audio

    duck_depth = triggered / (float(np.max(triggered)) + 1e-9)   # renormalize 0..1 on trigger content
    gain_floor = 10 ** (-params['duck_db'] / 20.0)
    gain_curve = (1.0 - duck_depth * (1.0 - gain_floor)).astype(np.float32)

    return (audio * gain_curve[np.newaxis, :]).astype(np.float32)


# Vintage-hardware-reverb IR (plate character) -- procedurally synthesized
# (see _synthesize_plate_ir()) rather than sourced from a third-party pack
# (the research doc names Convology XT's free set as an alternative), to
# stay dependency-free/procedural, matching this project's no-external-
# black-box-assets posture. Distinct, historically-correct reference
# texture for boom-bap/SP-1200-era production (research/theory/
# mixing-texture.md items 5+7), vs. the existing acoustic-room/hall IRs
# (assets/ir/*.wav from Voxengo's pack) the original jazz/piano-gated
# _IR_GENRES set already uses -- kept as a separate pool so boom-bap genres
# never randomly draw a salon/hall IR and jazz/piano genres never draw the
# plate.
_PLATE_IR_FILENAME = "procedural_plate.wav"
_PLATE_IR_GENRES = {"hip_hop_lofi", "chillhop", "lo_fi_funk", "lofi_drill", "lofi_phonk"}


def _synthesize_plate_ir(sr: int = 44100, duration_s: float = 1.1) -> "np.ndarray":
    """
    Procedurally synthesize a basic plate-reverb-style impulse response:
    dense exponentially-decaying filtered noise, a standard, well-understood
    approximation of plate-reverb character (bright, dense, fast-decaying,
    with the low end rolled off since a real metal plate doesn't reproduce
    it well) -- see the module-level comment above _PLATE_IR_FILENAME for
    why this is synthesized rather than sourced from a third-party pack.
    """
    import numpy as np
    n = int(sr * duration_s)
    t = np.arange(n, dtype=np.float64) / sr
    noise = np.random.randn(n).astype(np.float64)
    decay = np.exp(-t / 0.35)   # shorter/denser decay than a room/hall IR
    ir = noise * decay
    alpha = np.exp(-2.0 * np.pi * 300.0 / sr)   # gentle ~300Hz high-pass
    ir = ir - _lfilter([1.0 - alpha], [1.0, -alpha], ir)
    ir = ir / (float(np.max(np.abs(ir))) + 1e-9) * 0.9
    return ir.astype(np.float32)


# Procedural room impulses: (file name, RT60 seconds, pre-delay ms, damping Hz).
# Small room / chamber / hall characters, replacing the third-party files.
_ROOM_IRS = (
    ("procedural_room.wav",    0.45, 6,  6500.0),
    ("procedural_chamber.wav", 1.0,  14, 5000.0),
    ("procedural_hall.wav",    2.0,  25, 3800.0),
)


def _synthesize_room_ir(rt60: float, predelay_ms: float, damping_hz: float,
                        sr: int = 44100, seed: int = 0) -> "np.ndarray":
    """Room-style impulse response: a few discrete early reflections, then a
    noise tail decaying 60 dB over rt60 and darkening as it decays (air and
    wall absorption take the highs first)."""
    import numpy as np
    rng = np.random.default_rng(seed)
    n = int(sr * (rt60 * 1.2 + predelay_ms / 1000))
    ir = np.zeros(n, dtype=np.float64)
    start = int(sr * predelay_ms / 1000)
    ir[0] = 1.0                                           # direct sound
    for _ in range(8):                                    # early reflections
        k = start + int(rng.uniform(0, 0.04) * sr)
        if k < n:
            ir[k] += rng.uniform(0.25, 0.6) * rng.choice([-1, 1])
    t = np.arange(n - start, dtype=np.float64) / sr
    tail = rng.standard_normal(n - start) * np.exp(-6.91 * t / rt60) * 0.35
    alpha = np.exp(-2.0 * np.pi * damping_hz / sr)        # one-pole low-pass
    tail = _lfilter([1.0 - alpha], [1.0, -alpha], tail)
    ir[start:] += tail
    ir = ir / (float(np.max(np.abs(ir))) + 1e-9) * 0.9
    return ir.astype(np.float32)


def _ensure_room_ir_files() -> list[str]:
    """Write the procedural room impulses to assets/ir/ once and return their paths."""
    import soundfile as sf
    os.makedirs(_IR_DIR, exist_ok=True)
    paths = []
    for seed, (name, rt60, predelay, damping) in enumerate(_ROOM_IRS):
        path = os.path.join(_IR_DIR, name)
        if not os.path.exists(path):
            sf.write(path, _synthesize_room_ir(rt60, predelay, damping, seed=seed), 44100,
                     subtype="PCM_16")
        paths.append(path)
    return paths


def _ensure_plate_ir_file() -> str:
    """Write the procedural plate IR to assets/ir/ once (idempotent -- skips
    synthesis if the file already exists on disk) and return its path, so
    _apply_ir_reverb()'s file-based selection can pick it up like any other
    IR file in that directory."""
    import soundfile as sf
    path = os.path.join(_IR_DIR, _PLATE_IR_FILENAME)
    if not os.path.exists(path):
        os.makedirs(_IR_DIR, exist_ok=True)
        sf.write(path, _synthesize_plate_ir(), 44100, subtype="PCM_16")
    return path


# Gated reverb (research/theory/rhythm-groove.md follow-up research this
# session closed for lofi_synthwave's self-flagged gap: "would benefit from
# a follow-up research pass, particularly on gated-reverb drum-machine
# production technique"). The single most identity-defining 80s/synthwave
# drum effect (Phil Collins "In the Air Tonight"-style): a loud reverb send
# on transients, cut short by a noise gate instead of left to decay
# naturally. Genre-gated -- wrong character for anything not going for that
# specific punchy-80s-drum-machine sound.
_GATED_REVERB_GENRES = {"lofi_synthwave"}
_GATE_HOLD_MS = 120.0   # how long the gated reverb tail stays open before hard-cutting


def _apply_gated_reverb(audio: "np.ndarray", sr: int, mix: float = 0.35) -> "np.ndarray":
    """
    Detect transients (snare/clap frequency band), build a full/wet reverb
    tail via Pedalboard's Reverb, then hard-gate that WET signal only to
    _GATE_HOLD_MS after each transient onset before blending back under the
    dry signal -- the gate is what makes this "gated reverb" rather than
    just "a lot of reverb."
    """
    import numpy as np
    from pedalboard import Pedalboard, Reverb
    from scipy.signal import butter, sosfilt

    mono = audio.mean(axis=0)
    sos = butter(2, [1500.0, 6000.0], btype='bandpass', fs=sr, output='sos')
    band = np.abs(sosfilt(sos, mono))
    alpha_attack  = np.exp(-1.0 / (3.0  / 1000.0 * sr))
    alpha_release = np.exp(-1.0 / (25.0 / 1000.0 * sr))
    fast = _lfilter([1.0 - alpha_attack],  [1.0, -alpha_attack],  band)
    slow = _lfilter([1.0 - alpha_release], [1.0, -alpha_release], band)
    envelope = np.maximum(fast, slow)
    peak = float(np.max(envelope)) + 1e-9
    env_norm = envelope / peak
    triggered = env_norm > 0.3
    onset_idx = np.where(triggered & ~np.roll(triggered, 1))[0]

    reverb_board = Pedalboard([Reverb(room_size=0.9, damping=0.2,
                                       wet_level=1.0, dry_level=0.0, width=1.0)])
    wet = reverb_board(audio, sr, reset=True)

    hold_samples = int(_GATE_HOLD_MS / 1000.0 * sr)
    gate = np.zeros(audio.shape[1], dtype=np.float32)
    for idx in onset_idx:
        gate[idx:idx + hold_samples] = 1.0

    gated_wet = wet * gate[np.newaxis, :]
    return (audio * (1.0 - mix) + gated_wet * mix).astype(np.float32)


def _apply_ir_reverb(audio: "np.ndarray", sr: int,
                     sub_genre: str | None = None) -> "np.ndarray | None":
    """
    Apply convolution reverb using an IR file from assets/ir/. `sub_genre`
    in _PLATE_IR_GENRES uses the procedural plate IR specifically
    (synthesizing it on first use); every other genre randomly picks among
    the remaining (room/hall/salon-character) files, excluding the plate --
    keeps the two IR "pools" from mixing across the boom-bap/jazz-piano
    genre split they're each tuned for. Returns the wet signal (same shape
    as input), or None if no IR file is usable.
    """

    if sub_genre in _PLATE_IR_GENRES:
        ir_path = _ensure_plate_ir_file()
    else:
        ir_path = random.choice(_ensure_room_ir_files())

    try:
        return _convolve_ir(audio, sr, ir_path)
    except Exception:
        return None


def _resample(x: "np.ndarray", orig_sr: int, target_sr: int) -> "np.ndarray":
    """Polyphase resampling along the last axis (scipy; replaces librosa)."""
    from math import gcd
    import numpy as np
    from scipy.signal import resample_poly
    if orig_sr == target_sr:
        return x
    g = gcd(int(orig_sr), int(target_sr))
    return resample_poly(x, target_sr // g, orig_sr // g, axis=-1).astype(np.float32)


def _convolve_ir(audio: "np.ndarray", sr: int, ir_path: str) -> "np.ndarray":
    """Convolution reverb, channel by channel, peak-normalised to 0.5 and cut
    to the input length: the same result audiomentations' ApplyImpulseResponse
    gave, without that dependency. `audio` is (channels, samples) or 1-D."""
    import numpy as np
    import soundfile as sf
    from scipy.signal import fftconvolve
    ir, ir_sr = sf.read(ir_path, dtype="float32", always_2d=True)
    ir = _resample(ir.T, ir_sr, sr)                    # (ir_channels, n)
    if audio.ndim == 1:
        ir = ir.mean(axis=0, keepdims=True)
    samples = np.atleast_2d(audio.astype(np.float32))
    wet = np.stack([fftconvolve(ch, ir[i % len(ir)])[: samples.shape[1]]
                    for i, ch in enumerate(samples)]).astype(np.float32)
    peak = float(np.max(np.abs(wet)))
    if peak > 0:
        wet *= 0.5 / peak
    return wet[0] if audio.ndim == 1 else wet


def _make_crackle(n_samples: int, amplitude: float, sr: int = 44100) -> "np.ndarray":
    """
    Generate vinyl crackle as 3 additive layers instead of the previous 2
    (research/theory/mixing-texture.md item 2's documented academic
    gramophone-noise-synthesis decomposition): hiss (parametric-EQ-filtered
    white noise, here a ~1kHz one-pole lowpass), pops (sparse impulses,
    unchanged), and rumble (a new extra-lowpassed sub-40Hz noise layer
    tracking turntable wow -- pairs naturally with the sub-bass saturation
    stage's <150Hz band).
    """
    import numpy as np

    # Hiss: ~1kHz-lowpassed noise floor.
    hiss = np.random.randn(n_samples).astype(np.float32)
    alpha_hiss = 0.92
    hiss = _lfilter([1.0 - alpha_hiss], [1.0, -alpha_hiss], hiss).astype(np.float32)

    # Pops: sparse crackle impulses.
    n_pops = max(1, int(n_samples / 44100 * random.randint(3, 12)))
    for _ in range(n_pops):
        pos = random.randint(0, n_samples - 1)
        width = random.randint(2, 8)
        hiss[pos:pos + width] += random.uniform(0.3, 0.9)

    # Rumble: sub-40Hz lowpassed noise, mixed in modestly under the hiss/pop
    # layer -- rumble is felt more than heard on most playback systems, per
    # the documented 3-layer decomposition.
    rumble = np.random.randn(n_samples).astype(np.float32)
    alpha_rumble = float(np.exp(-2.0 * np.pi * 40.0 / sr))
    rumble = _lfilter([1.0 - alpha_rumble], [1.0, -alpha_rumble], rumble).astype(np.float32)

    combined = hiss + rumble * 0.5
    return combined.reshape(1, -1) * amplitude


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
