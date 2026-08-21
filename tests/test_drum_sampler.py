import numpy as np
import pytest
import soundfile as sf

from scripts.drum_sampler import (
    _ASSET_DIR,
    _bjorklund,
    _build_loop,
    _hihat,
    _kick,
    _load,
    _mix_at,
    _pick_sample,
    _snare,
    _synth_hihat,
    _synth_kick,
    _synth_snare,
    generate_euclidean_pat_dict,
    layer_drum_break,
    SR,
)


# ── Bjorklund / Euclidean rhythm ──────────────────────────────────────────────

def test_bjorklund_length_and_onset_count():
    for k, n in [(3, 8), (2, 3), (4, 16), (5, 16), (8, 8)]:
        pattern = _bjorklund(k, n)
        assert len(pattern) == n
        assert sum(pattern) == k


def test_bjorklund_zero_onsets_is_all_rests():
    assert _bjorklund(0, 8) == [0] * 8


def test_bjorklund_first_step_is_always_an_onset_when_k_positive():
    # The module rotates the raw pattern so the first onset lands on step 0 --
    # matching generate_music_gemini.py's Euclidean generator convention.
    for k, n in [(3, 8), (2, 3), (5, 16)]:
        pattern = _bjorklund(k, n)
        assert pattern[0] == 1


def test_generate_euclidean_pat_dict_shape_and_keys():
    for energy in (0.0, 0.5, 1.0):
        pat = generate_euclidean_pat_dict(energy)
        assert set(pat.keys()) == {"k", "s", "h"}
        for voice in pat.values():
            assert len(voice) == 16
            assert all(v in (0.0, 0.9, 0.6, 1.0) or v == 0.0 for v in voice)


def test_generate_euclidean_pat_dict_higher_energy_has_more_onsets():
    low = generate_euclidean_pat_dict(0.0)
    high = generate_euclidean_pat_dict(1.0)
    low_onsets = sum(1 for v in low["k"] if v > 0) + sum(1 for v in low["h"] if v > 0)
    high_onsets = sum(1 for v in high["k"] if v > 0) + sum(1 for v in high["h"] if v > 0)
    assert high_onsets >= low_onsets


def test_generate_euclidean_snare_favors_the_backbeat():
    # The rotation-search should land at least one snare onset on step 4 or 12
    # (the backbeat) more often than not, across many trials.
    hits = 0
    trials = 30
    for _ in range(trials):
        pat = generate_euclidean_pat_dict(energy=0.5)
        if pat["s"][4] > 0 or pat["s"][12] > 0:
            hits += 1
    assert hits / trials > 0.5


# ── mix_at boundary safety ────────────────────────────────────────────────────

def test_mix_at_normal_placement():
    buf = np.zeros(10, dtype=np.float32)
    _mix_at(buf, np.array([1.0, 1.0, 1.0], dtype=np.float32), 2)
    assert list(buf[2:5]) == [1.0, 1.0, 1.0]


def test_mix_at_negative_position_is_a_safe_noop():
    buf = np.zeros(10, dtype=np.float32)
    _mix_at(buf, np.array([1.0, 1.0], dtype=np.float32), -1)
    assert np.all(buf == 0.0)


def test_mix_at_source_overruns_buffer_end_without_crashing():
    buf = np.zeros(5, dtype=np.float32)
    _mix_at(buf, np.array([1.0] * 10, dtype=np.float32), 3)
    assert list(buf) == [0.0, 0.0, 0.0, 1.0, 1.0]


def test_mix_at_empty_source_is_a_safe_noop():
    buf = np.zeros(5, dtype=np.float32)
    _mix_at(buf, np.array([], dtype=np.float32), 2)
    assert np.all(buf == 0.0)


# ── synthesis fallbacks ───────────────────────────────────────────────────────

def test_synth_kick_shape_dtype_and_no_nan():
    for style in ("standard", "808", "room", "tight", "jazz"):
        hit = _synth_kick(bpm=80, style=style)
        assert hit.dtype == np.float32
        assert hit.ndim == 1
        assert len(hit) > 0
        assert not np.isnan(hit).any()


def test_synth_snare_shape_dtype_and_no_nan():
    for style in ("standard", "tight", "snappy", "brush"):
        hit = _synth_snare(style)
        assert hit.dtype == np.float32
        assert not np.isnan(hit).any()
        assert np.max(np.abs(hit)) <= 1.0 + 1e-6


def test_synth_hihat_closed_shorter_than_open():
    # Closed hats are a short, tight burst; open hats ring out longer -- the
    # duration difference is the whole point of having both.
    closed = _synth_hihat(open=False)
    lengths_open = [len(_synth_hihat(open=True)) for _ in range(10)]
    assert len(closed) < min(lengths_open)


# ── sample loading ────────────────────────────────────────────────────────────

def test_load_missing_file_returns_none_without_raising():
    assert _load("not-a-real-file.wav") is None


def test_load_real_kick_sample_if_present():
    # assets/drums/ ships real CC0 samples in this repo -- if they're present,
    # confirm they load as mono float32 at the module's target sample rate.
    import os
    if not os.path.isfile(os.path.join(_ASSET_DIR, "vintage-kick-01.wav")):
        pytest.skip("assets/drums/vintage-kick-01.wav not present in this checkout")
    audio = _load("vintage-kick-01.wav")
    assert audio is not None
    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert len(audio) > 0


def test_pick_sample_returns_none_for_all_missing_files():
    assert _pick_sample(["missing-a.wav", "missing-b.wav"]) is None


def test_pick_sample_returns_a_copy_not_the_cached_array():
    import os
    if not os.path.isfile(os.path.join(_ASSET_DIR, "vintage-kick-01.wav")):
        pytest.skip("assets/drums/vintage-kick-01.wav not present in this checkout")
    first = _pick_sample(["vintage-kick-01.wav"])
    first[0] = 999.0
    second = _pick_sample(["vintage-kick-01.wav"])
    assert second[0] != 999.0


# ── hit builders (real sample or synthesis, either is valid) ─────────────────

def test_kick_snare_hihat_builders_produce_valid_audio():
    kick = _kick(bpm=80, style="standard")
    snare = _snare(style="standard")
    chat = _hihat(open=False)
    ohat = _hihat(open=True)
    for hit in (kick, snare, chat, ohat):
        assert hit.dtype == np.float32
        assert len(hit) > 0
        assert not np.isnan(hit).any()


# ── loop / full break ─────────────────────────────────────────────────────────

def test_build_loop_has_expected_sample_length():
    bpm, n_bars = 80, 4
    loop = _build_loop(bpm, "chillhop", n_bars=n_bars, swing=0.6)
    beat_sec = 60.0 / bpm
    expected = int(SR * beat_sec * 4 * n_bars)
    assert len(loop) == expected
    assert loop.dtype == np.float32
    assert not np.isnan(loop).any()


def test_build_loop_runs_for_every_subgenre_pattern_style_without_crashing():
    for sub_genre in ("chillhop", "hip_hop_lofi", "lofi_phonk", "lofi_jazz",
                       "totally_unknown_subgenre"):
        loop = _build_loop(80, sub_genre, n_bars=1, swing=0.58)
        assert not np.isnan(loop).any()


def test_layer_drum_break_writes_valid_output(tmp_path):
    sr = SR
    seconds = 5
    silence = np.zeros((sr * seconds, 2), dtype=np.float32)
    base_wav = tmp_path / "base.wav"
    sf.write(str(base_wav), silence, sr, subtype="PCM_16")

    out_wav = tmp_path / "out.wav"
    layer_drum_break(str(base_wav), str(out_wav), bpm=80, sub_genre="chillhop",
                     volume=0.22, swing=0.6)

    assert out_wav.exists()
    result, out_sr = sf.read(str(out_wav), dtype="float32", always_2d=True)
    assert out_sr == sr
    assert result.shape[0] == sr * seconds
    assert not np.isnan(result).any()
    # Base was silent -- the drum layer must actually be audible in the output.
    assert np.sqrt(np.mean(result ** 2)) > 1e-4


def test_layer_drum_break_never_exceeds_peak_safety_ceiling(tmp_path):
    sr = SR
    seconds = 3
    loud = (0.9 * np.sin(2 * np.pi * 220 * np.arange(sr * seconds) / sr)).astype(np.float32)
    base = np.stack([loud, loud], axis=1)
    base_wav = tmp_path / "base.wav"
    sf.write(str(base_wav), base, sr, subtype="PCM_16")

    out_wav = tmp_path / "out.wav"
    layer_drum_break(str(base_wav), str(out_wav), bpm=90, sub_genre="hip_hop_lofi",
                     volume=0.3, swing=0.62)

    result, _ = sf.read(str(out_wav), dtype="float32", always_2d=True)
    assert np.max(np.abs(result)) <= 0.95 + 1e-3


def test_layer_drum_break_in_place_is_safe(tmp_path):
    # The docstring claims src == dst is safe (reads fully before writing).
    sr = SR
    silence = np.zeros((sr * 3, 2), dtype=np.float32)
    wav_path = tmp_path / "track.wav"
    sf.write(str(wav_path), silence, sr, subtype="PCM_16")

    layer_drum_break(str(wav_path), str(wav_path), bpm=80, sub_genre="chillhop")

    result, _ = sf.read(str(wav_path), dtype="float32", always_2d=True)
    assert not np.isnan(result).any()
    assert np.sqrt(np.mean(result ** 2)) > 1e-4
