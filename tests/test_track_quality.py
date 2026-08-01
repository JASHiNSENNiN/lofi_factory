from scripts.track_quality import (
    KICK_NOTE,
    SNARE_NOTES,
    _longest_empty_span_frac,
    _melody_rest_ratio,
    _NARROW_RANGE_SUBGENRES,
    _pitch_class_entropy,
    _pitch_range,
    score_track_quality,
)

S16 = 120  # ticks per 16th note (PPQN=480 // 4)


def _dense_melody(n_steps=64, pitches=range(60, 68)):
    pitches = list(pitches)
    return [(i * S16, pitches[i % len(pitches)], 80, S16) for i in range(n_steps)]


def _good_drum_ev():
    return [(0, KICK_NOTE, 100, S16), (S16 * 4, SNARE_NOTES[0], 100, S16)]


def _good_piano_ev():
    return [(0, 60, 70, 480)]


# ── _pitch_class_entropy ─────────────────────────────────────────────────────

def test_pitch_class_entropy_empty():
    assert _pitch_class_entropy([]) == 0.0


def test_pitch_class_entropy_single_pitch_class():
    mel = [(i * S16, 60, 80, S16) for i in range(20)]
    assert _pitch_class_entropy(mel) == 0.0


def test_pitch_class_entropy_four_even_classes():
    # pitch classes 0,3,6,9 in equal proportion -> log2(4) == 2.0 bits
    mel = [(i * S16, 60 + (i % 4) * 3, 80, S16) for i in range(40)]
    assert _pitch_class_entropy(mel) == 2.0


# ── _melody_rest_ratio ───────────────────────────────────────────────────────

def test_melody_rest_ratio_no_onsets():
    assert _melody_rest_ratio([], active_bars=4) == 1.0


def test_melody_rest_ratio_active_bars_zero():
    assert _melody_rest_ratio([], active_bars=0) == 0.0


def test_melody_rest_ratio_fully_dense():
    assert _melody_rest_ratio(_dense_melody(64), active_bars=4) == 0.0


# ── _longest_empty_span_frac ─────────────────────────────────────────────────

def test_longest_empty_span_frac_active_bars_zero():
    assert _longest_empty_span_frac([], active_bars=0) == 0.0


def test_longest_empty_span_frac_plays_once_then_stalls():
    # Onsets only at step 0 and step 63 of a 64-step (4-bar) span: the ~62-step
    # gap between them should dominate, catching what an average rest ratio
    # (which would read as "3% rest") would miss entirely.
    mel = [(0, 60, 80, S16), (63 * S16, 62, 80, S16)]
    frac = _longest_empty_span_frac(mel, active_bars=4)
    assert frac > 0.9


def test_longest_empty_span_frac_no_gaps():
    assert _longest_empty_span_frac(_dense_melody(64), active_bars=4) == 0.0


# ── _pitch_range ──────────────────────────────────────────────────────────────

def test_pitch_range_empty():
    assert _pitch_range([]) == 0


def test_pitch_range_basic():
    mel = [(0, 60, 80, 10), (0, 72, 80, 10)]
    assert _pitch_range(mel) == 12


# ── score_track_quality: golden fixtures ─────────────────────────────────────

def test_score_known_good_track_passes_all_gates():
    score, failures = score_track_quality(
        _dense_melody(64), _good_piano_ev(), _good_drum_ev(), active_bars=4,
    )
    assert (score, failures) == (1.0, [])


def test_score_stuck_melody_fails_entropy_and_range():
    mel = [(i * S16, 60, 80, S16) for i in range(20)]
    _, failures = score_track_quality(
        mel, _good_piano_ev(), _good_drum_ev(), active_bars=4,
    )
    assert 'low_pitch_entropy' in failures
    assert 'flat_pitch_range' in failures


def test_score_empty_drums_fails_drum_or_piano_empty():
    _, failures = score_track_quality(
        _dense_melody(64), _good_piano_ev(), [], active_bars=4,
    )
    assert 'drum_or_piano_empty' in failures


def test_score_fully_empty_track_does_not_trigger_sparse_or_silence_gates():
    # active_bars=0 short-circuits _melody_rest_ratio and _longest_empty_span_frac
    # to 0.0 (not 1.0) -- a real subtlety worth pinning down so a future refactor
    # doesn't silently change this behavior.
    score, failures = score_track_quality([], [], [], active_bars=0)
    assert 'melody_too_sparse' not in failures
    assert 'melody_long_silence' not in failures
    assert 'low_pitch_entropy' in failures
    assert 'flat_pitch_range' in failures
    assert 'drum_or_piano_empty' in failures
    assert score == 0.4


# ── _NARROW_RANGE_SUBGENRES gate ─────────────────────────────────────────────

def test_narrow_range_subgenre_tolerates_range_one():
    mel = [(0, 60, 80, 100), (100, 61, 80, 100)]  # pitch_range == 1
    assert 'ambient' in _NARROW_RANGE_SUBGENRES
    _, failures = score_track_quality(
        mel, _good_piano_ev(), _good_drum_ev(), active_bars=4, sub_genre='ambient',
    )
    assert 'flat_pitch_range' not in failures


def test_default_subgenre_rejects_range_one():
    mel = [(0, 60, 80, 100), (100, 61, 80, 100)]  # same pitch_range == 1
    _, failures = score_track_quality(
        mel, _good_piano_ev(), _good_drum_ev(), active_bars=4, sub_genre=None,
    )
    assert 'flat_pitch_range' in failures
