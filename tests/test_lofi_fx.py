import numpy as np
import pytest

import scripts.lofi_fx as lofi_fx
from scripts.lofi_fx import (
    _apply_gated_reverb,
    _apply_head_bump,
    _apply_ir_reverb,
    _apply_kick_sidechain_duck,
    _apply_lufs_mastering,
    _apply_multiband_glue,
    _apply_pedalboard,
    _apply_stereo_width,
    _apply_sub_bass_saturation,
    _apply_tape_saturation,
    _apply_wow_flutter,
    _DUCK_PROFILES,
    _GATED_REVERB_GENRES,
    _GENRE_PRESETS,
    _IR_GENRES,
    _kick_envelope,
    _make_crackle,
    _PLATE_IR_GENRES,
    _SIDECHAIN_DUCK_GENRES,
    _TRACK_LUFS_TARGET,
    _wow_flutter_depth_ms,
    apply_lofi_fx,
)

pyln = pytest.importorskip("pyloudnorm")
sf = pytest.importorskip("soundfile")


def _sine_stereo(freq=220.0, seconds=2, sr=44100, amplitude=0.3):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    tone = (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([tone, tone]), sr


def _independent_stereo(n=44100 * 2, sr=44100, seed=0):
    rng = np.random.default_rng(seed)
    left = rng.standard_normal(n).astype(np.float32) * 0.1
    right = rng.standard_normal(n).astype(np.float32) * 0.1
    return np.stack([left, right]), sr


def test_stereo_width_identity_at_width_one():
    stereo, _ = _independent_stereo()
    result = _apply_stereo_width(stereo, 1.0)
    assert np.allclose(result, stereo, atol=1e-5)


def test_stereo_width_mono_passthrough():
    mono = np.stack([np.zeros(1000, dtype=np.float32)])
    result = _apply_stereo_width(mono, 1.5)
    assert np.array_equal(result, mono)


def test_stereo_width_scales_side_signal_by_width_factor():
    stereo, _ = _independent_stereo()
    left, right = stereo[0], stereo[1]
    side_before = (left - right) * 0.5

    widened = _apply_stereo_width(stereo, 1.15)
    side_after = (widened[0] - widened[1]) * 0.5

    ratio = np.sqrt(np.mean(side_after ** 2)) / np.sqrt(np.mean(side_before ** 2))
    assert abs(ratio - 1.15) < 1e-3


def test_stereo_width_preserves_mid_signal():
    stereo, _ = _independent_stereo()
    left, right = stereo[0], stereo[1]
    mid_before = (left + right) * 0.5

    widened = _apply_stereo_width(stereo, 1.15)
    mid_after = (widened[0] + widened[1]) * 0.5

    assert np.allclose(mid_before, mid_after, atol=1e-5)


def test_stereo_width_output_shape_and_dtype_match_input():
    stereo, _ = _independent_stereo()
    result = _apply_stereo_width(stereo, 1.1)
    assert result.shape == stereo.shape
    assert result.dtype == np.float32


def test_sub_bass_saturation_shape_dtype_and_no_nan():
    stereo, sr = _independent_stereo()
    result = _apply_sub_bass_saturation(stereo, sr)
    assert result.shape == stereo.shape
    assert result.dtype == np.float32
    assert not np.isnan(result).any()


def test_sub_bass_saturation_actually_changes_the_signal():
    stereo, sr = _independent_stereo()
    result = _apply_sub_bass_saturation(stereo, sr)
    assert not np.allclose(result, stereo)


def test_sub_bass_saturation_does_not_blow_up_peak_level():
    stereo, sr = _independent_stereo()
    result = _apply_sub_bass_saturation(stereo, sr)
    # Parallel-mixed at a modest wet amount -- shouldn't wildly inflate peak
    # level relative to the input, which stayed well under 1.0 (0.1 amplitude
    # random noise).
    assert np.max(np.abs(result)) < 1.0


# ── per-track LUFS mastering (Stage 3 item 7) ────────────────────────────────

def _pink_stereo(seconds=6, sr=44100, seed=0, amplitude=0.05):
    """RMS-normalized pink-ish noise, (channels, samples) -- this module's
    Pedalboard-style array convention (channel-first), unlike
    track_quality.py's (samples, channels) soundfile convention."""
    rng = np.random.default_rng(seed)
    n = int(sr * seconds)
    white = rng.standard_normal(n)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    freqs = freqs.copy()
    freqs[0] = freqs[1] if len(freqs) > 1 else 1.0
    pink = np.fft.irfft(spectrum / np.sqrt(freqs), n)
    rms = np.sqrt(np.mean(pink ** 2))
    pink = (pink / (rms + 1e-9) * amplitude).astype(np.float32)
    return np.stack([pink, pink]), sr


def test_lufs_mastering_hits_target_within_small_tolerance():
    stereo, sr = _pink_stereo(amplitude=0.03)   # start quiet, well under target
    mastered = _apply_lufs_mastering(stereo, sr)

    meter = pyln.Meter(sr)
    measured = meter.integrated_loudness(mastered.T.astype(np.float64))
    assert abs(measured - _TRACK_LUFS_TARGET) < 0.5


def test_lufs_mastering_raises_a_quiet_track():
    stereo, sr = _pink_stereo(amplitude=0.01)
    mastered = _apply_lufs_mastering(stereo, sr)
    assert np.sqrt(np.mean(mastered ** 2)) > np.sqrt(np.mean(stereo ** 2))


def test_lufs_mastering_lowers_a_loud_track():
    stereo, sr = _pink_stereo(amplitude=0.6)
    mastered = _apply_lufs_mastering(stereo, sr)
    assert np.sqrt(np.mean(mastered ** 2)) < np.sqrt(np.mean(stereo ** 2))


def test_lufs_mastering_silent_audio_is_a_safe_noop():
    silent = np.zeros((2, 44100 * 3), dtype=np.float32)
    result = _apply_lufs_mastering(silent, 44100)
    assert np.max(np.abs(result)) == 0.0
    assert not np.isnan(result).any()


def test_lufs_mastering_preserves_shape_and_dtype():
    stereo, sr = _pink_stereo()
    result = _apply_lufs_mastering(stereo, sr)
    assert result.shape == stereo.shape
    assert result.dtype == np.float32


def test_track_lufs_target_leaves_headroom_under_video_level_target():
    # Coordination check: the per-track target must sit BELOW (quieter than)
    # assemble_video.py's -14 LUFS video-level pass, per the documented
    # headroom rationale -- not fighting it by already being as loud or louder.
    assert _TRACK_LUFS_TARGET < -14.0


# ── kick-triggered sidechain ducking (Stage 3 item 7) ────────────────────────

def _kick_and_sustain_mix(seconds=4, sr=44100, kick_every=0.5):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    kick_gate = np.zeros_like(t)
    for onset in np.arange(0, seconds, kick_every):
        idx = int(onset * sr)
        kick_gate[idx:idx + int(0.01 * sr)] = 1.0
    kick = kick_gate * np.sin(2 * np.pi * 60 * t) * 0.6
    sustain = 0.15 * np.sin(2 * np.pi * 300 * t)
    mix = (kick + sustain).astype(np.float32)
    return np.stack([mix, mix]), sr


def test_sidechain_duck_reduces_level_shortly_after_a_kick_hit():
    stereo, sr = _kick_and_sustain_mix()
    ducked = _apply_kick_sidechain_duck(stereo, sr)

    onset_idx = int(1.0 * sr)
    window = slice(onset_idx + 300, onset_idx + 4000)   # just after the kick, still in the duck's release
    before_rms = np.sqrt(np.mean(stereo[0, window] ** 2))
    after_rms = np.sqrt(np.mean(ducked[0, window] ** 2))
    assert after_rms < before_rms


def test_sidechain_duck_preserves_shape_dtype_and_has_no_nan():
    stereo, sr = _kick_and_sustain_mix()
    result = _apply_kick_sidechain_duck(stereo, sr)
    assert result.shape == stereo.shape
    assert result.dtype == np.float32
    assert not np.isnan(result).any()


def test_sidechain_duck_on_silence_is_a_safe_noop():
    silent = np.zeros((2, 44100 * 2), dtype=np.float32)
    result = _apply_kick_sidechain_duck(silent, 44100)
    assert np.max(np.abs(result)) == 0.0


def test_sidechain_duck_never_increases_peak_level():
    stereo, sr = _kick_and_sustain_mix()
    ducked = _apply_kick_sidechain_duck(stereo, sr)
    assert np.max(np.abs(ducked)) <= np.max(np.abs(stereo)) + 1e-6


def test_kick_envelope_peaks_near_kick_onsets():
    _, sr = _kick_and_sustain_mix()
    stereo, sr = _kick_and_sustain_mix()
    mono = stereo.mean(axis=0)
    envelope = _kick_envelope(mono, sr, attack_ms=3.0, release_ms=60.0)

    onset_idx = int(1.0 * sr)
    near_kick = envelope[onset_idx:onset_idx + 500].max()
    far_from_kick = envelope[onset_idx + 15000:onset_idx + 18000].max()
    assert near_kick > far_from_kick


def test_sidechain_duck_gate_genre_membership_is_a_small_opt_in_set():
    # Documents/locks the "most genres do NOT want pumping" design intent
    # (see _SIDECHAIN_DUCK_GENRES's comment) -- most of the ~22 genre
    # presets must remain outside this set.
    assert 0 < len(_SIDECHAIN_DUCK_GENRES) < 10
    assert "lofi_house" in _SIDECHAIN_DUCK_GENRES
    assert "lofi_classical" not in _SIDECHAIN_DUCK_GENRES
    assert "ambient" not in _SIDECHAIN_DUCK_GENRES


# ── tape wow & flutter ────────────────────────────────────────────────────────

def test_wow_flutter_shape_dtype_and_no_nan():
    stereo, sr = _independent_stereo()
    result = _apply_wow_flutter(stereo, sr, depth=0.2)
    assert result.shape == stereo.shape
    assert result.dtype == np.float32
    assert not np.isnan(result).any()


def test_wow_flutter_actually_modulates_a_tone():
    stereo, sr = _sine_stereo()
    result = _apply_wow_flutter(stereo, sr, depth=0.3)
    assert not np.allclose(result, stereo, atol=1e-3)


def test_wow_flutter_never_exceeds_input_peak():
    # Linear interpolation between two real samples is a convex combination
    # of the two, so the output can never exceed the input's own peak --
    # this is a delay/interpolation effect, not a gain stage.
    stereo, sr = _sine_stereo(amplitude=0.5)
    result = _apply_wow_flutter(stereo, sr, depth=0.45)
    assert np.max(np.abs(result)) <= np.max(np.abs(stereo)) + 1e-6


def test_wow_flutter_silence_is_a_safe_noop():
    silent = np.zeros((2, 44100 * 2), dtype=np.float32)
    result = _apply_wow_flutter(silent, 44100, depth=0.3)
    assert np.max(np.abs(result)) == 0.0


def test_wow_flutter_too_short_input_is_a_safe_passthrough():
    tiny = np.zeros((2, 2), dtype=np.float32)
    result = _apply_wow_flutter(tiny, 44100, depth=0.3)
    assert result.shape == tiny.shape


# ── end-to-end FX chain ───────────────────────────────────────────────────────
# Previously untested: README.md's rationale for excluding audio tests
# ("need FluidSynth/ffmpeg on the actual deploy target") doesn't actually
# apply to the Pedalboard chain here -- it takes a numpy buffer in and needs
# no system binary, unlike the FluidSynth-render and ffmpeg-encode steps.

def test_apply_lofi_fx_runs_end_to_end_for_every_genre_preset(tmp_path):
    stereo, sr = _sine_stereo(seconds=3)
    wav_in = tmp_path / "in.wav"
    sf.write(str(wav_in), stereo.T, sr, subtype="PCM_16")

    for sub_genre in list(_GENRE_PRESETS) + [None]:
        wav_out = tmp_path / f"out_{sub_genre}.wav"
        apply_lofi_fx(str(wav_in), str(wav_out), sub_genre=sub_genre, bpm=80, energy="medium")
        assert wav_out.exists()
        result, _out_sr = sf.read(str(wav_out), dtype="float32", always_2d=True)
        assert not np.isnan(result).any()
        assert np.max(np.abs(result)) <= 1.0 + 1e-6


def test_apply_lofi_fx_output_is_not_silent(tmp_path):
    stereo, sr = _sine_stereo(seconds=2, amplitude=0.4)
    wav_in = tmp_path / "in.wav"
    sf.write(str(wav_in), stereo.T, sr, subtype="PCM_16")
    wav_out = tmp_path / "out.wav"

    apply_lofi_fx(str(wav_in), str(wav_out), sub_genre="chillhop", bpm=82, energy="medium")
    result, _sr = sf.read(str(wav_out), dtype="float32", always_2d=True)
    assert np.sqrt(np.mean(result ** 2)) > 1e-4


# ── IR convolution reverb (assets/ir/*.wav) ──────────────────────────────────
# Previously dead on three independent fronts: assets/ir/ didn't exist, the
# audiomentations dependency wasn't declared, and even with both present the
# ApplyImpulseResponse call used a kwarg (`ir_paths`) that doesn't exist on
# the actual API (`ir_path`, singular) -- silently swallowed by this
# function's own except-and-return-None.

def test_ir_reverb_finds_real_files_and_returns_wet_audio():
    stereo, sr = _sine_stereo(seconds=2, amplitude=0.3)
    wet = _apply_ir_reverb(stereo, sr)
    assert wet is not None
    assert wet.shape == stereo.shape
    assert not np.isnan(wet).any()
    assert np.max(np.abs(wet)) > 0.0


def test_ir_genres_gate_is_a_small_opt_in_set():
    # Grew from <10 to 14/29 when research/theory/mixing-texture.md item 7
    # (2026-08-26) added use_ir_reverb: true to 5 boom-bap genres so they
    # can use the new procedural plate IR (_PLATE_IR_GENRES) -- still a
    # genuine minority/opt-in set, not "most genres."
    assert 0 < len(_IR_GENRES) < 15
    assert "lofi_jazz" in _IR_GENRES
    assert "hip_hop_lofi" in _IR_GENRES   # opted in for the plate IR (item 7)
    assert "lofi_house" not in _IR_GENRES


def test_apply_lofi_fx_respects_energy_levels(tmp_path):
    stereo, sr = _sine_stereo(seconds=2)
    wav_in = tmp_path / "in.wav"
    sf.write(str(wav_in), stereo.T, sr, subtype="PCM_16")

    for energy in ("low", "medium", "high"):
        wav_out = tmp_path / f"out_{energy}.wav"
        apply_lofi_fx(str(wav_in), str(wav_out), sub_genre="dark_lofi", bpm=75, energy=energy)
        result, _sr = sf.read(str(wav_out), dtype="float32", always_2d=True)
        assert not np.isnan(result).any()


# ── research/theory/mixing-texture.md backlog (2026-08-26) ─────────────────

def _band_energy(mono: np.ndarray, sr: int, low_hz: float, high_hz: float) -> float:
    spectrum = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(len(mono), d=1.0 / sr)
    band = (freqs >= low_hz) & (freqs <= high_hz)
    return float(np.sum(spectrum[band] ** 2))


# ── item 1: %WRMS-anchored wow/flutter depth ────────────────────────────────

def test_wow_flutter_depth_ms_increases_with_depth():
    lo = _wow_flutter_depth_ms(0.0)
    mid = _wow_flutter_depth_ms(0.2)
    hi = _wow_flutter_depth_ms(0.45)
    assert lo < mid < hi


def test_wow_flutter_depth_ms_stays_in_documented_ms_range():
    # Calibrated to land in roughly the same ms ballpark as the prior flat
    # 0.5-3.5ms mapping (see _wow_flutter_depth_ms's docstring).
    for d in (0.0, 0.1, 0.2, 0.3, 0.45):
        ms = _wow_flutter_depth_ms(d)
        assert 0.4 <= ms <= 3.6


def test_wow_flutter_depth_ms_clamps_out_of_range_input():
    assert _wow_flutter_depth_ms(-1.0) == _wow_flutter_depth_ms(0.0)
    assert _wow_flutter_depth_ms(10.0) == _wow_flutter_depth_ms(0.45)


# ── item 2: static head-bump EQ ──────────────────────────────────────────────

def test_head_bump_boosts_50_70hz_band_energy():
    stereo, sr = _independent_stereo(n=44100 * 2)
    boosted = _apply_head_bump(stereo, sr, wobble_depth=0.3)
    before = _band_energy(stereo[0], sr, 50, 70)
    after = _band_energy(boosted[0], sr, 50, 70)
    assert after > before


def test_head_bump_preserves_shape_dtype_and_has_no_nan():
    stereo, sr = _independent_stereo()
    boosted = _apply_head_bump(stereo, sr, wobble_depth=0.2)
    assert boosted.shape == stereo.shape
    assert boosted.dtype == np.float32
    assert not np.isnan(boosted).any()


def test_head_bump_center_and_gain_track_wobble_depth():
    # Gritty (high wobble_depth) should push more energy into the LOW end
    # of the 50-70Hz band (center shifts toward 50Hz) with a bigger boost
    # than clean (low wobble_depth), per _apply_head_bump's docstring.
    stereo, sr = _independent_stereo(n=44100 * 2)
    clean = _apply_head_bump(stereo, sr, wobble_depth=0.0)
    gritty = _apply_head_bump(stereo, sr, wobble_depth=0.45)
    clean_low = _band_energy(clean[0], sr, 45, 55)
    gritty_low = _band_energy(gritty[0], sr, 45, 55)
    assert gritty_low > clean_low


# ── item 3: 3-layer crackle (hiss / pop / rumble) ────────────────────────────

def test_crackle_has_energy_in_new_sub_40hz_rumble_band():
    sr = 44100
    crackle = _make_crackle(sr * 2, amplitude=1.0, sr=sr)
    assert crackle.shape == (1, sr * 2)
    rumble_energy = _band_energy(crackle[0], sr, 5, 40)
    assert rumble_energy > 0.0


def test_crackle_preserves_prior_hiss_and_pop_character():
    sr = 44100
    crackle = _make_crackle(sr * 2, amplitude=1.0, sr=sr)
    # Hiss: real energy well above the new rumble band (the ~1kHz-lowpassed
    # noise floor is still broadband up to ~1kHz).
    hiss_energy = _band_energy(crackle[0], sr, 200, 900)
    assert hiss_energy > 0.0
    # Pops: sparse high-amplitude impulses should still produce some samples
    # well above the ambient noise floor's typical magnitude.
    assert np.max(np.abs(crackle)) > 3 * np.std(crackle)


def test_crackle_scales_with_amplitude():
    sr = 44100
    quiet = _make_crackle(sr, amplitude=0.05, sr=sr)
    loud = _make_crackle(sr, amplitude=0.5, sr=sr)
    assert np.std(loud) > np.std(quiet)


# ── item 4: full-band tape saturation ────────────────────────────────────────

def test_tape_saturation_zero_mix_is_a_noop():
    stereo, sr = _independent_stereo()
    result = _apply_tape_saturation(stereo, sr, mix=0.0)
    assert np.array_equal(result, stereo)


def test_tape_saturation_preserves_shape_dtype_and_has_no_nan():
    stereo, sr = _independent_stereo()
    result = _apply_tape_saturation(stereo, sr, mix=0.15)
    assert result.shape == stereo.shape
    assert result.dtype == np.float32
    assert not np.isnan(result).any()


def test_tape_saturation_does_not_blow_up_near_nyquist():
    # The oversample-then-downsample round trip must not dump aliased
    # energy near Nyquist -- a broadband input driven through an
    # un-oversampled tanh would show a large increase here.
    stereo, sr = _independent_stereo(n=44100 * 2)
    result = _apply_tape_saturation(stereo, sr, mix=0.3)
    near_nyquist_before = _band_energy(stereo[0], sr, sr * 0.45, sr * 0.5)
    near_nyquist_after = _band_energy(result[0], sr, sr * 0.45, sr * 0.5)
    # Some increase from the drive is expected (it's still adding harmonic
    # content); it must not be wildly disproportionate to the input energy
    # there, which would indicate un-managed aliasing.
    assert near_nyquist_after < near_nyquist_before * 50 + 1e-6


def test_tape_saturation_moderate_mix_stays_bounded():
    stereo, sr = _sine_stereo(freq=220.0, amplitude=0.5)
    result = _apply_tape_saturation(stereo, sr, mix=0.2)
    assert np.max(np.abs(result)) < 2.0   # tanh-bounded, no runaway gain


# ── item 5: split house/hip-hop duck profiles ────────────────────────────────

def test_duck_profiles_house_is_slower_and_deeper_than_hiphop():
    house, hiphop = _DUCK_PROFILES['house'], _DUCK_PROFILES['hiphop']
    assert house['release_ms'] > hiphop['release_ms']
    assert house['duck_db'] > hiphop['duck_db']


def test_duck_profile_selection_changes_output():
    stereo, sr = _kick_and_sustain_mix()
    house_out = _apply_kick_sidechain_duck(stereo, sr, profile='house')
    hiphop_out = _apply_kick_sidechain_duck(stereo, sr, profile='hiphop')
    assert not np.array_equal(house_out, hiphop_out)


def test_duck_profile_unknown_falls_back_to_hiphop():
    stereo, sr = _kick_and_sustain_mix()
    default_out = _apply_kick_sidechain_duck(stereo, sr)
    hiphop_out = _apply_kick_sidechain_duck(stereo, sr, profile='hiphop')
    unknown_out = _apply_kick_sidechain_duck(stereo, sr, profile='not_a_real_profile')
    assert np.array_equal(default_out, hiphop_out)
    assert np.array_equal(unknown_out, hiphop_out)


# ── item 6: presence_db / warmth_db genre-preset fields ──────────────────────

def test_presence_and_warmth_default_to_zero_for_unset_genres():
    # Most genre YAMLs don't set these -- genre_presets.build_genre_fx_presets()
    # must default both to 0.0 (no-op) rather than raising/omitting the keys.
    for key, preset in _GENRE_PRESETS.items():
        assert 'presence_db' in preset and 'warmth_db' in preset

    unset_preset = _GENRE_PRESETS.get('piano_lofi', {})
    assert unset_preset.get('presence_db', 0.0) == 0.0


def test_presence_and_warmth_set_for_boom_bap_genres():
    preset = _GENRE_PRESETS['hip_hop_lofi']
    assert preset['presence_db'] < 0.0   # a cut, not a boost
    assert preset['warmth_db'] > 0.0     # a boost


# ── item 7: procedural plate/spring IR ───────────────────────────────────────

def test_plate_ir_genres_are_boom_bap_leaning_and_disjoint_from_room_ir_use():
    assert _PLATE_IR_GENRES
    assert "hip_hop_lofi" in _PLATE_IR_GENRES
    assert "lofi_jazz" not in _PLATE_IR_GENRES   # jazz/piano keep room/hall IRs


def test_ir_reverb_uses_plate_ir_for_plate_genre():
    stereo, sr = _sine_stereo(seconds=1)
    wet = _apply_ir_reverb(stereo, sr, sub_genre="hip_hop_lofi")
    assert wet is not None
    assert wet.shape == stereo.shape
    assert not np.isnan(wet).any()


def test_ir_reverb_still_works_for_room_genre_with_sub_genre_kwarg():
    stereo, sr = _sine_stereo(seconds=1)
    wet = _apply_ir_reverb(stereo, sr, sub_genre="lofi_jazz")
    assert wet is not None
    assert wet.shape == stereo.shape


# ── Phase 7: gated reverb (lofi_synthwave) ──────────────────────────────────

def _snare_hits_mix(seconds=3, sr=44100, hit_every=0.5):
    # Sparse bursts of noise bandpassed into the snare/clap-ish 1.5-6kHz
    # range _apply_gated_reverb's transient detector looks at, over a quiet
    # sustained tone -- gives the gate real onsets to trigger on.
    from scipy.signal import butter, sosfilt
    rng = np.random.default_rng(0)
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    noise = rng.standard_normal(len(t)).astype(np.float32)
    sos = butter(2, [1500.0, 6000.0], btype='bandpass', fs=sr, output='sos')
    band = sosfilt(sos, noise).astype(np.float32)
    gate = np.zeros_like(t)
    for onset in np.arange(0, seconds, hit_every):
        idx = int(onset * sr)
        gate[idx:idx + int(0.01 * sr)] = 1.0
    hits = gate * band * 0.6
    sustain = 0.1 * np.sin(2 * np.pi * 200 * t)
    mix = (hits + sustain).astype(np.float32)
    return np.stack([mix, mix]), sr


def test_gated_reverb_preserves_shape_dtype_and_no_nan():
    stereo, sr = _snare_hits_mix()
    result = _apply_gated_reverb(stereo, sr)
    assert result.shape == stereo.shape
    assert result.dtype == np.float32
    assert not np.isnan(result).any()


def test_gated_reverb_tail_is_shorter_than_natural_decay():
    # A plain (ungated) Reverb tail keeps ringing well past _GATE_HOLD_MS
    # after the last transient; the gated version must not.
    from pedalboard import Pedalboard, Reverb
    stereo, sr = _snare_hits_mix(seconds=2, hit_every=5.0)  # one isolated hit
    gated = _apply_gated_reverb(stereo, sr, mix=1.0)

    ungated_board = Pedalboard([Reverb(room_size=0.9, damping=0.2,
                                        wet_level=1.0, dry_level=0.0, width=1.0)])
    ungated_wet = ungated_board(stereo, sr, reset=True)

    hit_sample = int(0.01 * sr)
    far_after_ms = 400
    far_idx = hit_sample + int(far_after_ms / 1000.0 * sr)
    assert abs(gated[0, far_idx]) <= abs(ungated_wet[0, far_idx]) + 1e-6


def test_gated_reverb_zero_mix_is_close_to_dry():
    stereo, sr = _snare_hits_mix()
    result = _apply_gated_reverb(stereo, sr, mix=0.0)
    assert np.allclose(result, stereo, atol=1e-5)


def test_gated_reverb_genres_is_scoped_to_synthwave():
    assert "lofi_synthwave" in _GATED_REVERB_GENRES
    assert "lofi_jazz" not in _GATED_REVERB_GENRES


def test_apply_lofi_fx_runs_for_synthwave_with_gated_reverb(tmp_path):
    stereo, sr = _sine_stereo(seconds=1)
    wav_in = tmp_path / "in.wav"
    sf.write(str(wav_in), stereo.T, sr, subtype="PCM_16")
    wav_out = tmp_path / "out.wav"
    apply_lofi_fx(str(wav_in), str(wav_out), sub_genre="lofi_synthwave", bpm=95, energy="medium")
    result, _sr = sf.read(str(wav_out), dtype="float32", always_2d=True)
    assert not np.isnan(result).any()


# ── Phase 8: multiband + parallel mastering glue ────────────────────────────

def test_multiband_glue_preserves_shape_dtype_and_no_nan():
    stereo, sr = _independent_stereo()
    result = _apply_multiband_glue(stereo, sr)
    assert result.shape == stereo.shape
    assert result.dtype == np.float32
    assert not np.isnan(result).any()


def test_multiband_glue_zero_parallel_mix_is_a_noop():
    stereo, sr = _independent_stereo()
    result = _apply_multiband_glue(stereo, sr, parallel_mix=0.0)
    assert np.allclose(result, stereo, atol=1e-5)


def test_multiband_glue_reduces_dynamic_range_of_a_transient_signal():
    sr = 44100
    t = np.linspace(0, 2, sr * 2, endpoint=False)
    quiet = 0.05 * np.sin(2 * np.pi * 200 * t)
    loud = quiet.copy()
    loud[sr // 2:sr // 2 + 2000] += 0.8   # one loud transient burst
    stereo = np.stack([loud, loud]).astype(np.float32)

    result = _apply_multiband_glue(stereo, sr, low_ratio=6.0, high_ratio=6.0, parallel_mix=1.0)
    original_range = np.max(np.abs(stereo)) - np.mean(np.abs(quiet))
    result_range = np.max(np.abs(result)) - np.mean(np.abs(quiet))
    assert result_range <= original_range


def test_multiband_glue_does_not_blow_up_silence():
    silent = np.zeros((2, 44100), dtype=np.float32)
    result = _apply_multiband_glue(silent, 44100)
    assert np.max(np.abs(result)) < 1e-3


def test_apply_lofi_fx_output_still_valid_with_multiband_glue(tmp_path):
    stereo, sr = _sine_stereo(seconds=1)
    wav_in = tmp_path / "in.wav"
    sf.write(str(wav_in), stereo.T, sr, subtype="PCM_16")
    wav_out = tmp_path / "out.wav"
    apply_lofi_fx(str(wav_in), str(wav_out), sub_genre="hip_hop_lofi", bpm=80, energy="medium")
    result, _sr = sf.read(str(wav_out), dtype="float32", always_2d=True)
    assert not np.isnan(result).any()
    assert np.max(np.abs(result)) <= 1.0


# ── section-transition FX wiring (research/theory/arrangement-structure.md
# gap #1 -- build_midi()'s section_transitions return value threaded through
# apply_lofi_fx() into _apply_pedalboard(), which is the piece under test
# here; the 3 FX functions themselves are unit-tested in
# tests/generate_music/test_arrangement_transition_fx.py) ─────────────────

def test_transitions_none_does_not_call_any_transition_fx(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(lofi_fx, "_apply_vinyl_stop", lambda *a, **k: calls.append("vinyl_stop") or a[0])
    monkeypatch.setattr(lofi_fx, "_apply_reverse_riser", lambda *a, **k: calls.append("reverse_riser") or a[0])
    monkeypatch.setattr(lofi_fx, "_apply_filter_sweep", lambda *a, **k: calls.append("filter_sweep") or a[0])

    stereo, sr = _sine_stereo(seconds=1)
    wav_in = tmp_path / "in.wav"
    sf.write(str(wav_in), stereo.T, sr, subtype="PCM_16")
    wav_out = tmp_path / "out.wav"
    apply_lofi_fx(str(wav_in), str(wav_out), sub_genre="chillhop", bpm=80, energy="medium",
                  transitions=None)
    assert calls == []


def test_transitions_empty_list_does_not_call_any_transition_fx(monkeypatch, tmp_path):
    monkeypatch.setattr(lofi_fx, "_apply_vinyl_stop", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(lofi_fx, "_apply_reverse_riser", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(lofi_fx, "_apply_filter_sweep", lambda *a, **k: (_ for _ in ()).throw(AssertionError))

    stereo, sr = _sine_stereo(seconds=1)
    wav_in = tmp_path / "in.wav"
    sf.write(str(wav_in), stereo.T, sr, subtype="PCM_16")
    wav_out = tmp_path / "out.wav"
    apply_lofi_fx(str(wav_in), str(wav_out), sub_genre="chillhop", bpm=80, energy="medium",
                  transitions=[])
    # no assertion raised => none of the 3 spies fired


def test_transitions_dispatches_each_fx_name_to_its_function(monkeypatch, tmp_path):
    calls = []

    def _spy_vinyl(audio, sr, at_sample, *a, **k):
        calls.append(("vinyl_stop", at_sample))
        return audio

    def _spy_riser(audio, sr, at_sample, *a, **k):
        calls.append(("reverse_riser", at_sample))
        return audio

    def _spy_sweep(audio, sr, at_sample, *a, **k):
        calls.append(("filter_lowpass_sweep", at_sample, k.get("direction")))
        return audio

    monkeypatch.setattr(lofi_fx, "_apply_vinyl_stop", _spy_vinyl)
    monkeypatch.setattr(lofi_fx, "_apply_reverse_riser", _spy_riser)
    monkeypatch.setattr(lofi_fx, "_apply_filter_sweep", _spy_sweep)

    stereo, sr = _sine_stereo(seconds=2)
    wav_in = tmp_path / "in.wav"
    sf.write(str(wav_in), stereo.T, sr, subtype="PCM_16")
    wav_out = tmp_path / "out.wav"
    transitions = [(10000, "vinyl_stop"), (20000, "reverse_riser"), (30000, "filter_lowpass_sweep")]
    apply_lofi_fx(str(wav_in), str(wav_out), sub_genre="chillhop", bpm=80, energy="medium",
                  transitions=transitions)

    fired = {c[0] for c in calls}
    assert fired == {"vinyl_stop", "reverse_riser", "filter_lowpass_sweep"}
    at_samples = {c[0]: c[1] for c in calls}
    assert at_samples["vinyl_stop"] == 10000
    assert at_samples["reverse_riser"] == 20000
    assert at_samples["filter_lowpass_sweep"] == 30000
    sweep_call = next(c for c in calls if c[0] == "filter_lowpass_sweep")
    assert sweep_call[2] == "down"


def test_transitions_unknown_fx_name_is_silently_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr(lofi_fx, "_apply_vinyl_stop", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(lofi_fx, "_apply_reverse_riser", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(lofi_fx, "_apply_filter_sweep", lambda *a, **k: (_ for _ in ()).throw(AssertionError))

    stereo, sr = _sine_stereo(seconds=1)
    wav_in = tmp_path / "in.wav"
    sf.write(str(wav_in), stereo.T, sr, subtype="PCM_16")
    wav_out = tmp_path / "out.wav"
    # No FX named this way exists -- should be a silent no-op, not a crash.
    apply_lofi_fx(str(wav_in), str(wav_out), sub_genre="chillhop", bpm=80, energy="medium",
                  transitions=[(5000, "not_a_real_fx")])
    result, _sr = sf.read(str(wav_out), dtype="float32", always_2d=True)
    assert not np.isnan(result).any()


def test_apply_pedalboard_transitions_param_defaults_to_none(tmp_path):
    # Direct call with no transitions kwarg at all -- the wiring must be
    # fully optional, matching every other genre-gated stage in this chain.
    stereo, sr = _sine_stereo(seconds=1)
    wav_in = tmp_path / "in.wav"
    sf.write(str(wav_in), stereo.T, sr, subtype="PCM_16")
    wav_out = tmp_path / "out.wav"
    _apply_pedalboard(str(wav_in), str(wav_out), "chillhop", 80, "medium")
    result, _sr = sf.read(str(wav_out), dtype="float32", always_2d=True)
    assert not np.isnan(result).any()
