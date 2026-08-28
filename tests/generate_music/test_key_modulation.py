"""
Tests for in-track key modulation (maybe_modulate_key / _transpose_events)
-- new research this session, no prior research/theory/*.md doc covers
this. The "truck driver modulation": rare, form-gated, whole-step key rise
into the final theme statement. See generate_music_gemini.py's module
comment for the scope note on remaining build_midi() pipeline wiring.
"""
import random

from scripts.generate_music_gemini import (
    _PITCHWHEEL_NOTE,
    _transpose_events,
    maybe_modulate_key,
)

_AABA = [('I', 1), ('A', 2), ('A', 2), ('BR', 2), ('A', 2), ('O', 1)]
_BUILD = [('I', 1), ('A', 3), ('BR', 1), ('A', 3), ('BR', 1), ('A', 3), ('O', 1)]
_STANDARD = [('I', 1), ('A', 4), ('BR', 1), ('B', 4), ('O', 1)]
_MINIMAL_VAMP = [('I', 1), ('A', 4)]   # only one 'A' -- no "final statement" to modulate into


def test_ineligible_form_never_modulates():
    for _ in range(50):
        assert maybe_modulate_key(_AABA, 'minimal', seed=random.randint(0, 10000)) is None


def test_form_with_fewer_than_two_a_sections_never_modulates():
    for seed in range(50):
        assert maybe_modulate_key(_MINIMAL_VAMP, 'build', seed=seed) is None


def test_eligible_form_modulates_sometimes_not_always():
    results = [maybe_modulate_key(_AABA, 'aaba', seed=s) for s in range(300)]
    modulated = [r for r in results if r is not None]
    assert 0 < len(modulated) < len(results)   # neither never nor always


def test_modulation_targets_the_last_a_section():
    # Force a hit by trying many seeds until one modulates, then check the
    # returned index really is the LAST 'A' in the form.
    hit = None
    for seed in range(300):
        result = maybe_modulate_key(_AABA, 'aaba', seed=seed)
        if result is not None:
            hit = result
            break
    assert hit is not None
    sec_idx, semitones = hit
    last_a_idx = max(i for i, (label, _) in enumerate(_AABA) if label == 'A')
    assert sec_idx == last_a_idx
    assert semitones in (1, 2)


def test_build_form_also_eligible():
    results = [maybe_modulate_key(_BUILD, 'build', seed=s) for s in range(300)]
    assert any(r is not None for r in results)


def test_deterministic_with_seed():
    a = maybe_modulate_key(_AABA, 'aaba', seed=99)
    b = maybe_modulate_key(_AABA, 'aaba', seed=99)
    assert a == b


def test_whole_step_more_common_than_half_step():
    hits = [r[1] for r in
            (maybe_modulate_key(_AABA, 'aaba', seed=s) for s in range(1000))
            if r is not None]
    assert hits   # sanity: got some hits over 1000 seeds at 12% probability
    assert hits.count(2) > hits.count(1)


# ── _transpose_events ────────────────────────────────────────────────────────

def test_transpose_shifts_real_notes():
    events = [(0, 60, 80, 100), (100, 64, 70, 100)]
    result = _transpose_events(events, 2)
    assert result == [(0, 62, 80, 100), (100, 66, 70, 100)]


def test_transpose_zero_is_identity():
    events = [(0, 60, 80, 100)]
    assert _transpose_events(events, 0) == events


def test_transpose_leaves_pitchwheel_sentinel_events_untouched():
    events = [(0, 60, 80, 100), (50, _PITCHWHEEL_NOTE, 8192, 0)]
    result = _transpose_events(events, 5)
    assert result[0] == (0, 65, 80, 100)
    assert result[1] == (50, _PITCHWHEEL_NOTE, 8192, 0)


def test_transpose_empty_events_is_safe():
    assert _transpose_events([], 3) == []
