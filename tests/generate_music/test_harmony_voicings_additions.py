"""
Tests for research/theory/harmony-voicings.md's remaining "Concrete
additions" table entries -- everything EXCEPT the modal-interchange
progressions, minor ii-V-i siblings, and dedicated Db7 tritone-sub target,
which were already implemented in the Aug 23 "Composition-quality overhaul"
(confirmed present: VOICING_OPTIONS['Amaj7'/'Dmaj7'], the F#m7b5/B7b9/
G#m7b5/C#7b9/C#m7b5/F#7b9/Fm7b5/Bb7b9/Am7b5/D7b9 minor-ii-V-i chords,
PROGRESSIONS #51-58, and _SEC_DOM_SUBS['G7']'s Db7 entry).

Covers what was genuinely still missing: G13, G7alt, Am11, Dm11, Am6,
Cmaj6, and quartal voicings appended as alternates to Dm7/Am7.
"""

from scripts.generate_music_gemini import (
    BASS_ROOTS,
    VOICING_OPTIONS,
    _GUIDE_TONES,
    _voice_lead_choice,
    _voice_lead_progression_best,
    build_chords,
)

_NEW_CHORDS = ["G13", "G7alt", "Am11", "Dm11", "Am6", "Cmaj6"]


def test_new_chord_symbols_present_in_all_three_lookup_tables():
    for chord in _NEW_CHORDS:
        assert chord in VOICING_OPTIONS, f"{chord} missing from VOICING_OPTIONS"
        assert chord in BASS_ROOTS, f"{chord} missing from BASS_ROOTS"
        assert chord in _GUIDE_TONES, f"{chord} missing from _GUIDE_TONES"


def test_new_chord_voicings_are_ascending_and_nonempty():
    for chord in _NEW_CHORDS:
        options = VOICING_OPTIONS[chord]
        assert options
        for voicing in options:
            assert voicing == sorted(voicing)
            assert len(voicing) >= 3


def test_sixth_chords_use_six_not_seven_in_guide_tone_second_slot():
    # Am6/Cmaj6 have no 7th -- the research doc's "(3,9)-style (6th not
    # 7th)" note means the guide-tone tuple's second slot holds the 6th's
    # semitone offset (9) instead of a 7th (10 or 11).
    assert _GUIDE_TONES["Am6"] == (3, 9)
    assert _GUIDE_TONES["Cmaj6"] == (4, 9)


def test_g13_and_g7alt_share_g7s_root_and_guide_shape():
    assert BASS_ROOTS["G13"] == BASS_ROOTS["G7"]
    assert BASS_ROOTS["G7alt"] == BASS_ROOTS["G7"]
    assert _GUIDE_TONES["G13"] == _GUIDE_TONES["G7"]
    assert _GUIDE_TONES["G7alt"] == _GUIDE_TONES["G7"]


def test_new_chords_resolve_via_voice_lead_choice_without_raising():
    for chord in _NEW_CHORDS:
        voicing = _voice_lead_choice(chord, prev_top=64)
        assert voicing


def test_new_chords_resolve_via_whole_progression_optimizer():
    progression = [(c, 2) for c in _NEW_CHORDS]
    voicings, winner = _voice_lead_progression_best(progression, pop_size=8, generations=8)
    assert len(voicings) == len(_NEW_CHORDS)
    assert winner in ("ga", "annealing")


def test_new_chords_work_end_to_end_through_build_chords():
    progression = [("Am7", 2), ("G13", 2), ("Cmaj6", 2), ("G7alt", 2)]
    events = build_chords(progression, start_bar=0, num_loops=1, swing=0.5, bpm=80)
    assert events


# ── quartal voicings (Dm7/Am7 alternates, not new symbols) ─────────────────

def test_quartal_voicing_present_as_dm7_alternate():
    assert [50, 55, 60, 65] in VOICING_OPTIONS["Dm7"]


def test_quartal_voicing_present_as_am7_alternate():
    assert [57, 62, 67, 72] in VOICING_OPTIONS["Am7"]


def test_quartal_voicings_stack_in_fourths():
    for voicing in ([50, 55, 60, 65], [57, 62, 67, 72]):
        intervals = [voicing[i + 1] - voicing[i] for i in range(len(voicing) - 1)]
        assert all(iv == 5 for iv in intervals)   # perfect 4th = 5 semitones


def test_dm7_and_am7_still_have_their_original_voicings_too():
    # The quartal addition must be additive, not a replacement.
    assert len(VOICING_OPTIONS["Dm7"]) >= 6
    assert len(VOICING_OPTIONS["Am7"]) >= 6
