"""
Coverage for Feature 3 -- continuous arpeggiator (research/subgenres/
lofi_synthwave.md: "the arpeggio is explicitly the melodic engine of
synthwave -- a repeating note sequence built from the chord tones of each
chord, running continuously...typically an LFO-synced 16th-note...pattern").

build_arpeggio() reuses VOICING_OPTIONS (the same chord-tone table
build_chords()/build_pad() use) and produces a note for every subdivision
slot across the progression's bars -- no rests, no phrase/motif
development -- structurally distinct from build_melody()'s phrase-based,
rest-having engine.
"""
import random

from scripts.composer import (
    PROGRESSIONS,
    VOICING_OPTIONS,
    _CONTINUOUS_ARP_GENRES,
    build_arpeggio,
    build_melody,
)

# [('Am9',4),('Cmaj9',4)] -- a simple 2-chord, 8-bar vamp; easy to reason
# about tone cycling and total step counts.
_PROG = PROGRESSIONS[19]
_PROG_BARS = sum(d for _, d in _PROG)


def test_arpeggio_produces_a_note_for_every_subdivision_slot():
    random.seed(1)
    events = build_arpeggio(_PROG, 0, 1, 0.54, 90, subdivision=16, octave_range=2)
    assert len(events) == _PROG_BARS * 16


def test_arpeggio_notes_are_drawn_from_the_chord_tone_set():
    random.seed(1)
    events = build_arpeggio(_PROG, 0, 1, 0.54, 90, pattern='up', subdivision=16, octave_range=2)
    cursor = 0
    for chord_name, dur_bars in _PROG:
        voicing = VOICING_OPTIONS[chord_name][0]
        allowed_pcs = {n % 12 for n in voicing}
        bar_events = [e for e in events if cursor * 16 <= _grid_of(e) < (cursor + dur_bars) * 16]
        assert bar_events, f"expected arp events for {chord_name}"
        assert all(e[1] % 12 in allowed_pcs for e in bar_events), (
            f"{chord_name}: found a note outside its chord-tone pitch classes"
        )
        cursor += dur_bars


def _grid_of(event):
    # Recover an approximate 16th-grid position from an event's absolute
    # tick for bucketing by bar -- good enough at subdivision=16 where the
    # step and the 16th-grid coincide (S16 = PPQN // 4 = 120 ticks).
    from scripts.composer import S16
    return round(event[0] / S16)


def test_arpeggio_pattern_up_vs_down_produces_different_note_order():
    random.seed(2)
    up = build_arpeggio(_PROG, 0, 1, 0.54, 90, pattern='up', subdivision=16, octave_range=1)
    random.seed(2)
    down = build_arpeggio(_PROG, 0, 1, 0.54, 90, pattern='down', subdivision=16, octave_range=1)
    up_notes = [e[1] for e in up]
    down_notes = [e[1] for e in down]
    assert up_notes != down_notes
    # 'down' should start on the highest tone of the first chord's voicing.
    first_chord_tones = sorted(set(VOICING_OPTIONS[_PROG[0][0]][0]))
    assert down_notes[0] == first_chord_tones[-1]
    assert up_notes[0] == first_chord_tones[0]


def test_arpeggio_cycles_continuously_without_rests_across_multiple_octaves():
    random.seed(4)
    events = build_arpeggio(_PROG, 0, 1, 0.54, 90, pattern='up', subdivision=16, octave_range=2)
    ticks = sorted(e[0] for e in events)
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    # Every gap should be roughly one subdivision step (S16=120 ticks @ 16
    # steps/bar) -- no multi-step silent gaps the way build_melody()'s
    # rest-driven phrasing would leave.
    from scripts.composer import S16
    assert max(gaps) < S16 * 2
    notes = {e[1] for e in events}
    first_chord_tones = sorted(set(VOICING_OPTIONS[_PROG[0][0]][0]))
    # octave_range=2 should introduce at least one tone an octave above the
    # base voicing.
    assert any(n == t + 12 for n in notes for t in first_chord_tones)


def test_arpeggio_is_denser_and_rest_free_compared_to_phrase_based_melody():
    random.seed(5)
    arp_events = build_arpeggio(_PROG, 0, 1, 0.54, 90, subdivision=16, octave_range=2)
    random.seed(5)
    melody_events = build_melody(57, 0, _PROG_BARS, 0.54, 90, density='sparse', scale='major')
    assert len(arp_events) > len(melody_events) * 3


def test_lofi_synthwave_is_registered_in_continuous_arp_genres():
    assert 'lofi_synthwave' in _CONTINUOUS_ARP_GENRES
    assert 'lofi_drill' not in _CONTINUOUS_ARP_GENRES
    assert 'lofi_garage' not in _CONTINUOUS_ARP_GENRES
