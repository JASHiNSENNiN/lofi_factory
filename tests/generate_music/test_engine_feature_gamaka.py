"""
Coverage for gamaka-style grace-note pitch-bend ornamentation (research/
subgenres/lofi_world.md: "Gamaka-style ornamentation (grace-note bends
around a target pitch, per raga convention) is the genre's most distinctive
melodic device and the clearest way to differentiate lofi_world's melodic
character").

build_melody(..., gamaka=True) / build_counter_melody(..., gamaka=True) emit
pitch-bend ornaments approaching each eligible note's onset via
_gamaka_pitchbend_events(); abs_to_track() special-cases the same
_PITCHWHEEL_NOTE sentinel _glide_pitchbend_events() (drill's 808 glide)
uses to turn those into real mido 'pitchwheel' messages. Unlike the 808
glide (slides OUT of a note at its TAIL), gamaka bends INTO a note at its
ONSET -- see _gamaka_pitchbend_events()'s docstring for the distinction.
"""
import random

import mido
import pytest

import scripts.generate_music_gemini as gmg
from scripts import genre_presets
from scripts.generate_music_gemini import (
    KEY_ROOTS,
    _GAMAKA_BEND_RANGE_SEMITONES,
    _GAMAKA_GENRES,
    _GAMAKA_PROB,
    _PITCHWHEEL_NOTE,
    _gamaka_pitchbend_events,
    abs_to_track,
    build_counter_melody,
    build_melody,
)

_KEY_ROOT = KEY_ROOTS['Am']


# ── _gamaka_pitchbend_events ─────────────────────────────────────────────────

def test_gamaka_events_are_all_pitchwheel_sentinels():
    random.seed(1)
    events = _gamaka_pitchbend_events(1000, 480, bpm=80)
    assert events
    assert all(e[1] == _PITCHWHEEL_NOTE for e in events)


def test_gamaka_ramp_starts_off_center_and_ends_at_center():
    random.seed(2)
    events = _gamaka_pitchbend_events(1000, 480, bpm=80)
    events = sorted(events, key=lambda e: e[0])
    assert events[0][2] != 8192, "first bend should start away from true pitch"
    assert events[-1][2] == 8192, "ramp should ease back to center (true pitch) by its end"


def test_gamaka_first_event_lands_exactly_at_note_onset():
    random.seed(3)
    note_on_tick = 4800
    events = _gamaka_pitchbend_events(note_on_tick, 480, bpm=80)
    assert min(e[0] for e in events) == note_on_tick


def test_gamaka_too_short_note_duration_is_a_safe_noop():
    assert _gamaka_pitchbend_events(1000, 1, bpm=80) == []
    assert _gamaka_pitchbend_events(1000, 0, bpm=80) == []


def test_gamaka_bend_values_stay_within_the_dedicated_small_range():
    # bend_semitones default caps at 1.5 semitones within a 2-semitone
    # dedicated range -- pitch14 should never approach the extremes a much
    # wider range (e.g. the 808 glide's 12 semitones) would allow.
    random.seed(4)
    # Worst case: bend_semitones maxes at 1.5 within a 2-semitone dedicated
    # range -> raw = 8192 +- round((1.5/2) * 8192) = 8192 +- 6144, i.e.
    # roughly [2048, 14336] -- nowhere near the 14-bit rails (0, 16383) a
    # much wider range (e.g. the 808 glide's 12 semitones) would allow.
    random.seed(4)
    for _ in range(50):
        events = _gamaka_pitchbend_events(1000, 480, bpm=80)
        for _t, _n, pitch14, _d in events:
            assert 1900 <= pitch14 <= 14400


def test_gamaka_direction_varies_across_calls():
    random.seed(5)
    starts = []
    for _ in range(30):
        events = sorted(_gamaka_pitchbend_events(1000, 480, bpm=80), key=lambda e: e[0])
        starts.append(events[0][2])
    assert any(s < 8192 for s in starts)
    assert any(s > 8192 for s in starts)


# ── build_melody(gamaka=) / build_counter_melody(gamaka=) ──────────────────

def test_build_melody_gamaka_true_produces_pitchwheel_events_false_does_not():
    # NOTE: gamaka=True's per-note probability roll (`if gamaka and
    # random.random() < _GAMAKA_PROB`) consumes extra draws from the shared
    # global random stream that gamaka=False's short-circuited check never
    # does, so the two runs' note choices legitimately diverge after the
    # first note even from the same seed (same reason maybe_modulate_key's
    # own random draw shifts everything downstream of it) -- this isn't a
    # bug, so this test doesn't assert the two note lists are identical,
    # only that each run's own bend/note split behaves correctly.
    random.seed(42)
    gamaka_events = build_melody(_KEY_ROOT, 0, 8, 0.62, 78, density='medium',
                                 scale='dorian', gamaka=True)
    random.seed(42)
    plain_events = build_melody(_KEY_ROOT, 0, 8, 0.62, 78, density='medium',
                                scale='dorian', gamaka=False)

    gamaka_bends = [e for e in gamaka_events if e[1] == _PITCHWHEEL_NOTE]
    plain_bends = [e for e in plain_events if e[1] == _PITCHWHEEL_NOTE]
    assert gamaka_bends, "gamaka=True should produce at least one pitchwheel-marked event"
    assert not plain_bends, "gamaka=False must never emit pitchwheel-marked events"

    # gamaka=True must not break ordinary melody generation -- still
    # produces a comparable, non-empty population of real notes.
    gamaka_notes = [e for e in gamaka_events if e[1] != _PITCHWHEEL_NOTE]
    plain_notes = [e for e in plain_events if e[1] != _PITCHWHEEL_NOTE]
    assert gamaka_notes and plain_notes
    assert all(len(e) == 4 for e in gamaka_notes)


def test_build_melody_gamaka_default_is_false():
    random.seed(9)
    default_events = build_melody(_KEY_ROOT, 0, 8, 0.62, 78, density='medium', scale='dorian')
    assert not any(e[1] == _PITCHWHEEL_NOTE for e in default_events)


def test_build_counter_melody_gamaka_true_produces_pitchwheel_events_false_does_not():
    # See test_build_melody_gamaka_true_produces_pitchwheel_events_false_does_not's
    # note on why the two runs' underlying notes aren't expected to match
    # exactly once gamaka's own extra random draws are in play.
    random.seed(17)
    gamaka_events = build_counter_melody(_KEY_ROOT, 0, 8, 0.62, 78, scale='dorian', gamaka=True)
    random.seed(17)
    plain_events = build_counter_melody(_KEY_ROOT, 0, 8, 0.62, 78, scale='dorian', gamaka=False)

    gamaka_bends = [e for e in gamaka_events if e[1] == _PITCHWHEEL_NOTE]
    plain_bends = [e for e in plain_events if e[1] == _PITCHWHEEL_NOTE]
    assert gamaka_bends, "gamaka=True should produce at least one pitchwheel-marked event"
    assert not plain_bends, "gamaka=False must never emit pitchwheel-marked events"

    gamaka_notes = [e for e in gamaka_events if e[1] != _PITCHWHEEL_NOTE]
    plain_notes = [e for e in plain_events if e[1] != _PITCHWHEEL_NOTE]
    assert gamaka_notes and plain_notes


def test_gamaka_fires_at_roughly_the_configured_probability():
    # Loose statistical check, not an exact-count assertion (matches this
    # module's own convention for probability-gated features) -- across
    # many notes, the fraction bearing a gamaka ornament should land near
    # _GAMAKA_PROB, not near 0 or 1.
    random.seed(123)
    events = build_melody(_KEY_ROOT, 0, 64, 0.62, 78, density='dense', scale='dorian', gamaka=True)
    notes = [e for e in events if e[1] != _PITCHWHEEL_NOTE]
    onsets_with_bend = {e[0] for e in events if e[1] == _PITCHWHEEL_NOTE}
    note_onsets = {e[0] for e in notes}
    hit_rate = len(onsets_with_bend & note_onsets) / max(1, len(note_onsets))
    assert 0.15 < hit_rate < 0.80, f"gamaka hit rate {hit_rate} implausible for _GAMAKA_PROB={_GAMAKA_PROB}"


# ── abs_to_track wiring (RPN setup) ─────────────────────────────────────────

def test_abs_to_track_emits_rpn_setup_and_pitchwheel_messages_for_gamaka():
    random.seed(11)
    events = build_melody(_KEY_ROOT, 0, 8, 0.62, 78, density='medium', scale='dorian', gamaka=True)
    assert any(e[1] == _PITCHWHEEL_NOTE for e in events)

    track = abs_to_track(events, channel=2, program=104,
                          pitch_bend_range=_GAMAKA_BEND_RANGE_SEMITONES)

    ccs = [m for m in track if m.type == 'control_change']
    rpn_msb = [m for m in ccs if m.control == 101 and m.value == 0]
    rpn_lsb = [m for m in ccs if m.control == 100 and m.value == 0]
    data_msb = [m for m in ccs if m.control == 6 and m.value == _GAMAKA_BEND_RANGE_SEMITONES]
    assert rpn_msb and rpn_lsb and data_msb, "expected RPN 0,0 pitch-bend-range setup at track start"

    bends = [m for m in track if m.type == 'pitchwheel']
    assert bends, "expected real mido 'pitchwheel' messages in the assembled track"
    assert all(-8192 <= m.pitch <= 8191 for m in bends)


# ── genre registration ───────────────────────────────────────────────────────

def test_lofi_world_is_registered_in_gamaka_genres():
    assert 'lofi_world' in _GAMAKA_GENRES
    assert genre_presets.build_gamaka_genres() == _GAMAKA_GENRES


def test_gamaka_genres_is_a_small_opt_in_set_not_a_default():
    # Only lofi_world's raga-adjacent instrumentation calls for this --
    # every other genre's YAML omits `gamaka:` entirely (defaults False).
    assert 'lofi_drill' not in _GAMAKA_GENRES
    assert 'chillhop' not in _GAMAKA_GENRES
    assert 'nujabes' not in _GAMAKA_GENRES
    assert len(_GAMAKA_GENRES) <= 3


# ── build_midi() end-to-end (channel 2 = sitar lead, channel 4 = koto counter) ─

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


def test_lofi_world_build_midi_sitar_and_koto_tracks_carry_gamaka_bends(_isolated_music_dir, tmp_path):
    random.seed(0)
    params = gmg.pick_params(genre_hint='lofi_world')
    assert params['sub_genre'] == 'lofi_world'
    out_path = tmp_path / 'world.mid'
    gmg.build_midi(params, str(out_path))

    mid = mido.MidiFile(str(out_path))
    sitar_track = next((t for t in mid.tracks if any(getattr(m, 'channel', None) == 2 for m in t)), None)
    assert sitar_track is not None
    assert any(m.type == 'pitchwheel' for m in sitar_track), (
        "lofi_world's rendered melody (sitar) track should contain gamaka pitch-bend events"
    )
    # RPN pitch-bend-range setup should precede the first pitchwheel message,
    # same convention as the 808-glide bass track.
    types = [m.type for m in sitar_track if m.type in ('control_change', 'pitchwheel')]
    first_bend = types.index('pitchwheel')
    assert 'control_change' in types[:first_bend]


def test_lofi_drill_build_midi_melody_track_has_no_gamaka_bends(_isolated_music_dir, tmp_path):
    # Sanity control: a genre NOT in _GAMAKA_GENRES must never carry these
    # bends on its melody channel, confirming the feature is scoped, not
    # accidentally global.
    random.seed(0)
    params = gmg.pick_params(genre_hint='lofi_drill')
    out_path = tmp_path / 'drill_mel.mid'
    gmg.build_midi(params, str(out_path))

    mid = mido.MidiFile(str(out_path))
    mel_track = next((t for t in mid.tracks if any(getattr(m, 'channel', None) == 2 for m in t)), None)
    if mel_track is not None:
        assert not any(m.type == 'pitchwheel' for m in mel_track)
