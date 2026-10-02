"""
Coverage for Feature 1 -- 808 pitch-slide/portamento bass (research/
subgenres/lofi_drill.md: "the sliding/gliding 808 bass...the single most
recognizable production element in modern drill").

build_bass(..., glide=True) emits pitch-bend ornaments on the beat-1 root
hit's tail via _glide_pitchbend_events(); abs_to_track() special-cases a
sentinel note value (_PITCHWHEEL_NOTE) in the events list to turn those
into real mido 'pitchwheel' messages instead of note on/off pairs, and
(when pitch_bend_range is passed) emits an RPN 0,0 pitch-bend-range setup
at track start.
"""
import random


from scripts.composer import (
    PROGRESSIONS,
    _GLIDE_808_GENRES,
    _GLIDE_BEND_RANGE_SEMITONES,
    _PITCHWHEEL_NOTE,
    _bend_semitones_to_pitch14,
    abs_to_track,
    build_bass,
)


def test_glide_true_produces_pitchwheel_events_glide_false_does_not():
    prog = PROGRESSIONS[14]  # dark Cm cycle -- one of lofi_drill's progression_indices
    random.seed(42)
    glide_events = build_bass(prog, 0, 2, 0.65, 75, walking=False, glide=True)
    random.seed(42)
    plain_events = build_bass(prog, 0, 2, 0.65, 75, walking=False, glide=False)

    glide_bends = [e for e in glide_events if e[1] == _PITCHWHEEL_NOTE]
    plain_bends = [e for e in plain_events if e[1] == _PITCHWHEEL_NOTE]

    assert glide_bends, "glide=True should produce at least one pitchwheel-marked event"
    assert not plain_bends, "glide=False must never emit pitchwheel-marked events"
    # glide=True must not remove any of the real note events glide=False produces.
    glide_notes = [e for e in glide_events if e[1] != _PITCHWHEEL_NOTE]
    plain_notes = [e for e in plain_events if e[1] != _PITCHWHEEL_NOTE]
    assert len(glide_notes) == len(plain_notes)


def test_glide_ramp_ends_with_a_reset_to_center():
    prog = PROGRESSIONS[14]
    random.seed(7)
    events = build_bass(prog, 0, 1, 0.65, 75, walking=False, glide=True)
    bends = sorted((e for e in events if e[1] == _PITCHWHEEL_NOTE), key=lambda e: e[0])
    assert bends
    # Group consecutive bends into ramps by proximity and check each ramp's
    # last message resets to center (8192).
    ramps, current = [], [bends[0]]
    for prev, cur in zip(bends, bends[1:]):
        if cur[0] - prev[0] <= 40:
            current.append(cur)
        else:
            ramps.append(current)
            current = [cur]
    ramps.append(current)
    for ramp in ramps:
        assert ramp[-1][2] == 8192, f"ramp should reset to center pitch (8192), got {ramp[-1][2]}"


def test_bend_semitones_to_pitch14_is_centered_and_monotonic():
    assert _bend_semitones_to_pitch14(0) == 8192
    down = _bend_semitones_to_pitch14(-5)
    up = _bend_semitones_to_pitch14(5)
    assert down < 8192 < up
    assert 0 <= down <= 16383
    assert 0 <= up <= 16383


def test_abs_to_track_emits_rpn_setup_and_pitchwheel_messages_for_glide_bass():
    prog = PROGRESSIONS[14]
    random.seed(11)
    events = build_bass(prog, 0, 1, 0.65, 75, walking=False, glide=True)
    assert any(e[1] == _PITCHWHEEL_NOTE for e in events)

    track = abs_to_track(events, channel=1, program=38,
                          pitch_bend_range=_GLIDE_BEND_RANGE_SEMITONES)

    ccs = [m for m in track if m.type == 'control_change']
    rpn_msb = [m for m in ccs if m.control == 101 and m.value == 0]
    rpn_lsb = [m for m in ccs if m.control == 100 and m.value == 0]
    data_msb = [m for m in ccs if m.control == 6 and m.value == _GLIDE_BEND_RANGE_SEMITONES]
    assert rpn_msb and rpn_lsb and data_msb, "expected RPN 0,0 pitch-bend-range setup at track start"

    bends = [m for m in track if m.type == 'pitchwheel']
    assert bends, "expected real mido 'pitchwheel' messages in the assembled track"
    assert all(-8192 <= m.pitch <= 8191 for m in bends)


def test_abs_to_track_omits_rpn_setup_when_pitch_bend_range_not_given():
    events = [(0, 45, 90, 240), (240, 45, 80, 240)]
    track = abs_to_track(events, channel=1, program=38)
    ccs = [m for m in track if m.type == 'control_change']
    assert not any(m.control in (100, 101, 6, 38) for m in ccs)


def test_lofi_drill_is_registered_in_glide_808_genres():
    assert 'lofi_drill' in _GLIDE_808_GENRES
    assert 'lofi_garage' not in _GLIDE_808_GENRES
    assert 'lofi_synthwave' not in _GLIDE_808_GENRES
