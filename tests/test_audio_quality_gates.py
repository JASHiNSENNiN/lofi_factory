"""
Tests for the audio-domain quality gates in track_quality.py (Stage 3 item
6): clipping detection, extended-silence detection, LUFS measurement, and
spectral-balance sanity. These run on RENDERED audio (synthetic WAV
fixtures here, since FluidSynth output isn't needed to exercise the
algorithmic logic), unlike the pre-existing MIDI-structural gates.
"""

import numpy as np
import pytest

soundfile = pytest.importorskip("soundfile")

from scripts.track_quality import (
    detect_clipping,
    detect_extended_silence,
    measure_lufs,
    score_audio_quality,
    spectral_balance_ok,
)

SR = 44100


def _sine(freq, seconds, sr=SR, amplitude=0.2):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _broadband_music_like(seconds, sr=SR, seed=0, amplitude=0.15):
    """
    Pink noise (1/f power spectrum -> roughly EQUAL energy per octave) as a
    stand-in for real music's broadband spectral spread and RMS-heavy
    loudness profile -- unlike a single pure tone (which concentrates
    virtually all energy in one narrow band) or a handful of sparse
    discrete sine partials (which, being pure tones themselves, don't
    actually spread energy across the log-spaced bands the spectral-balance
    gate checks either). RMS-normalized (not peak-normalized) so the
    amplitude parameter maps predictably to loudness for the LUFS tests.
    """
    n = int(sr * seconds)
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(n)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    freqs = freqs.copy()
    freqs[0] = freqs[1] if len(freqs) > 1 else 1.0   # avoid divide-by-zero at DC
    pink_spectrum = spectrum / np.sqrt(freqs)
    pink = np.fft.irfft(pink_spectrum, n)
    rms = np.sqrt(np.mean(pink ** 2))
    pink = pink / (rms + 1e-9) * amplitude
    return pink.astype(np.float32)


def _write_wav(path, audio, sr=SR):
    soundfile.write(str(path), audio, sr, subtype="PCM_16")


# ── detect_clipping ────────────────────────────────────────────────────────────

def test_clean_signal_is_not_clipped():
    audio = _broadband_music_like(3.0)
    assert detect_clipping(audio) is False


def test_hard_clipped_signal_is_detected():
    audio = _sine(440, 3.0, amplitude=1.5)
    clipped = np.clip(audio, -1.0, 1.0)
    # Force a sustained run at full scale (a real clipped render, not just a
    # couple of true-peak samples).
    assert detect_clipping(clipped) is True


def test_a_few_peak_samples_alone_do_not_trigger_clipping():
    audio = _broadband_music_like(3.0)
    audio[100] = 0.99
    audio[5000] = -0.99
    assert detect_clipping(audio) is False


def test_detect_clipping_handles_stereo_shape():
    mono = np.clip(_sine(440, 2.0, amplitude=1.5), -1.0, 1.0)
    stereo = np.stack([mono, mono], axis=-1)   # (samples, channels)
    assert detect_clipping(stereo) is True


def test_detect_clipping_empty_audio_is_false():
    assert detect_clipping(np.array([])) is False


# ── detect_extended_silence ────────────────────────────────────────────────────

def test_normal_audio_is_not_flagged_silent():
    audio = _broadband_music_like(10.0)
    assert detect_extended_silence(audio, SR) is False


def test_fully_silent_track_is_flagged():
    audio = np.zeros(SR * 15, dtype=np.float32)
    assert detect_extended_silence(audio, SR) is True


def test_short_gap_is_not_flagged_but_long_dropout_is():
    music = _broadband_music_like(5.0)
    short_gap = np.zeros(int(SR * 1.0), dtype=np.float32)   # 1s gap, under the 8s threshold
    long_gap = np.zeros(int(SR * 12.0), dtype=np.float32)   # 12s gap, over the 8s threshold

    with_short_gap = np.concatenate([music, short_gap, music])
    with_long_gap = np.concatenate([music, long_gap, music])

    assert detect_extended_silence(with_short_gap, SR) is False
    assert detect_extended_silence(with_long_gap, SR) is True


def test_empty_audio_is_flagged_silent():
    assert detect_extended_silence(np.array([]), SR) is True


# ── measure_lufs ────────────────────────────────────────────────────────────────

def test_measure_lufs_louder_signal_has_higher_lufs():
    quiet = _broadband_music_like(5.0, amplitude=0.05)
    loud = _broadband_music_like(5.0, amplitude=0.5)
    lufs_quiet = measure_lufs(quiet, SR)
    lufs_loud = measure_lufs(loud, SR)
    assert lufs_quiet is not None and lufs_loud is not None
    assert lufs_loud > lufs_quiet


def test_measure_lufs_returns_finite_value_for_normal_audio():
    audio = _broadband_music_like(5.0)
    lufs = measure_lufs(audio, SR)
    assert lufs is not None
    assert -60.0 < lufs < 0.0


def test_measure_lufs_handles_stereo_shape():
    mono = _broadband_music_like(5.0)
    stereo = np.stack([mono, mono], axis=-1)
    lufs = measure_lufs(stereo, SR)
    assert lufs is not None


# ── spectral_balance_ok ──────────────────────────────────────────────────────

def test_broadband_signal_passes_spectral_balance():
    audio = _broadband_music_like(4.0)
    assert spectral_balance_ok(audio, SR) is True


def test_pure_tone_fails_spectral_balance():
    # A single sustained sine wave concentrates virtually all energy in one
    # narrow band -- the degenerate case this gate targets.
    audio = _sine(440, 4.0, amplitude=0.3)
    assert spectral_balance_ok(audio, SR) is False


def test_spectral_balance_handles_near_empty_audio_without_raising():
    assert spectral_balance_ok(np.array([0.0]), SR) is True


# ── score_audio_quality (integration) ──────────────────────────────────────────

def test_normal_broadband_track_scores_better_than_clipped_and_silent():
    normal = _broadband_music_like(12.0)
    clipped = np.clip(_sine(440, 12.0, amplitude=1.8), -1.0, 1.0)
    silent = np.zeros(SR * 12, dtype=np.float32)

    normal_score, normal_failures = score_audio_quality(normal, SR)
    clipped_score, clipped_failures = score_audio_quality(clipped, SR)
    silent_score, silent_failures = score_audio_quality(silent, SR)

    assert normal_score > clipped_score
    assert normal_score > silent_score
    assert 'clipping_detected' in clipped_failures
    assert 'extended_silence' in silent_failures


def test_score_audio_quality_score_in_valid_range():
    audio = _broadband_music_like(6.0)
    score, failures = score_audio_quality(audio, SR)
    assert 0.0 <= score <= 1.0
    assert isinstance(failures, list)


def test_score_audio_quality_reads_from_real_wav_fixture(tmp_path):
    # Round-trip through an actual WAV file on disk (as the pipeline's
    # rendered tracks would be), not just an in-memory array.
    audio = _broadband_music_like(6.0)
    wav_path = tmp_path / "normal.wav"
    _write_wav(wav_path, audio, SR)

    read_audio, read_sr = soundfile.read(str(wav_path), dtype="float32")
    score, failures = score_audio_quality(read_audio, read_sr)
    assert score > 0.5


def test_score_audio_quality_reads_clipped_wav_fixture(tmp_path):
    audio = np.clip(_sine(440, 6.0, amplitude=1.8), -1.0, 1.0)
    wav_path = tmp_path / "clipped.wav"
    _write_wav(wav_path, audio, SR)

    read_audio, read_sr = soundfile.read(str(wav_path), dtype="float32")
    score, failures = score_audio_quality(read_audio, read_sr)
    assert 'clipping_detected' in failures


def test_score_audio_quality_reads_silent_wav_fixture(tmp_path):
    audio = np.zeros(SR * 10, dtype=np.float32)
    wav_path = tmp_path / "silent.wav"
    _write_wav(wav_path, audio, SR)

    read_audio, read_sr = soundfile.read(str(wav_path), dtype="float32")
    score, failures = score_audio_quality(read_audio, read_sr)
    assert 'extended_silence' in failures
