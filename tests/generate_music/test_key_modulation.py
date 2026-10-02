"""
Tests for in-track key modulation (maybe_modulate_key / _transpose_events)
-- new research this session, no prior research/theory/*.md doc covers
this. The "truck driver modulation": rare, form-gated, whole-step key rise
into the final theme statement.
"""
import random

import mido
import pytest

import scripts.composer as gmg
from scripts.composer import (
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


# ── build_midi() end-to-end wiring ──────────────────────────────────────────
# maybe_modulate_key/_transpose_events are real and covered above; this
# covers the actual integration point: build_midi()'s _apply_modulation_tail,
# applied to piano_ev/bass_ev/mel_ev/pad_ev/cmelo_ev/texture_ev but NOT
# drum_ev (note numbers select drum voices, not pitches) or sustain_ev
# (CC64 pedal tuples -- a different shape than the 4-tuple note events
# _transpose_events assumes).

@pytest.fixture
def _isolated_music_dir(tmp_path, monkeypatch):
    """build_midi() writes to music/.params_history.json etc. as a side
    effect -- redirect to tmp_path (mirrors test_build_midi_integration.py's
    isolated_music_dir fixture) so this never touches real project state."""
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    monkeypatch.setattr(gmg, "MUSIC_DIR", str(music_dir))
    monkeypatch.setattr(gmg, "_PARAMS_HISTORY_FILE", str(music_dir / ".params_history.json"))
    monkeypatch.setattr(gmg, "_MELODY_HISTORY_FILE", str(music_dir / ".melody_history.json"))
    monkeypatch.setattr(gmg, "_RECIPE_LOG_FILE", str(music_dir / ".recipe_log.jsonl"))
    return music_dir


def _channel_notes(path, channel):
    """(abs_tick, note) for every note_on in `channel`, sorted by tick."""
    mid = mido.MidiFile(path)
    notes = []
    for track in mid.tracks:
        abs_t = 0
        for msg in track:
            abs_t += msg.time
            if msg.type == 'note_on' and msg.velocity > 0 and msg.channel == channel:
                notes.append((abs_t, msg.note))
    notes.sort(key=lambda x: x[0])
    return notes


def _has_sustain_cc(path, channel=0):
    mid = mido.MidiFile(path)
    return any(msg.type == 'control_change' and msg.channel == channel and msg.control == 64
               for track in mid.tracks for msg in track)


def test_modulation_wiring_transposes_only_the_piano_tail(_isolated_music_dir, tmp_path, monkeypatch):
    # Pin form_name deterministically to 'build' (lofi_drill's mapped form,
    # eligible for modulation) by disabling the ~25% generative-form-grammar
    # override -- without this, an unlucky seed could roll a form where the
    # forced section index below doesn't correspond to a real 'A' section.
    monkeypatch.setattr(gmg, 'generate_song_form',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('disabled for test')))

    FORCE_IDX, FORCE_SEMI = 3, 2   # 'build' form: index 3 is the 2nd 'A' section

    random.seed(0)
    params = gmg.pick_params(genre_hint='lofi_drill')
    assert params['sub_genre'] == 'lofi_drill'

    monkeypatch.setattr(gmg, 'maybe_modulate_key', lambda form, form_name, seed=None: None)
    random.seed(0)
    gmg.build_midi(params, str(tmp_path / 'base.mid'))
    base_piano = _channel_notes(str(tmp_path / 'base.mid'), channel=0)
    base_drums = _channel_notes(str(tmp_path / 'base.mid'), channel=9)

    monkeypatch.setattr(gmg, 'maybe_modulate_key',
                        lambda form, form_name, seed=None: (FORCE_IDX, FORCE_SEMI))
    random.seed(0)
    gmg.build_midi(params, str(tmp_path / 'mod.mid'))
    mod_piano = _channel_notes(str(tmp_path / 'mod.mid'), channel=0)
    mod_drums = _channel_notes(str(tmp_path / 'mod.mid'), channel=9)

    # Same random-draw sequence in both runs (the monkeypatched function
    # itself consumes no randomness either way) -- everything upstream of
    # the modulation decision should be byte-identical, so the two note
    # lists must line up 1:1 in count and tick position.
    assert len(base_piano) == len(mod_piano) > 0
    assert [t for t, _ in base_piano] == [t for t, _ in mod_piano]

    diffs = [m - b for (_, b), (_, m) in zip(base_piano, mod_piano)]
    first_shifted = next((i for i, d in enumerate(diffs) if d != 0), None)
    assert first_shifted is not None, "modulation never reached the piano track"
    assert all(d == 0 for d in diffs[:first_shifted]), "notes before the boundary must be untouched"
    assert all(d == FORCE_SEMI for d in diffs[first_shifted:]), "notes at/after the boundary must shift by FORCE_SEMI"

    # Drums are excluded from transposition entirely -- identical throughout.
    assert base_drums == mod_drums

    # sustain_ev (CC64) must still be present and build_midi() must not have
    # raised -- proves sustain_ev was excluded from _transpose_events rather
    # than fed to it (which would IndexError on its 3-tuple shape).
    assert _has_sustain_cc(str(tmp_path / 'mod.mid'), channel=0)


def test_no_modulation_leaves_output_byte_identical(_isolated_music_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(gmg, 'generate_song_form',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('disabled for test')))
    monkeypatch.setattr(gmg, 'maybe_modulate_key', lambda form, form_name, seed=None: None)

    random.seed(0)
    params = gmg.pick_params(genre_hint='lofi_drill')
    random.seed(0)
    gmg.build_midi(params, str(tmp_path / 'a.mid'))
    random.seed(0)
    gmg.build_midi(params, str(tmp_path / 'b.mid'))

    assert _channel_notes(str(tmp_path / 'a.mid'), 0) == _channel_notes(str(tmp_path / 'b.mid'), 0)
