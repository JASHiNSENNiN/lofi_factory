"""
Tests for the sparse modal drone progression added for lofi_world (Phase
11 step 1) -- research/subgenres/lofi_world.md: harmony should stay
minimal/modal (a held drone or simple sus/add9 vamp) rather than the jazz
ii-V-I turnarounds appropriate to lofi_jazz/jazz_cafe, so a phrygian-
dominant/dorian melodic line can carry the expressive weight instead of
chord movement.
"""
from scripts.composer import (
    BASS_ROOTS,
    PROGRESSION_KEY,
    PROGRESSIONS,
    VOICING_OPTIONS,
    _GUIDE_TONES,
    _voice_lead_choice,
    build_chords,
)


def test_drone_chords_present_in_all_lookup_tables():
    for chord in ("Amadd9", "Dmsus4"):
        assert chord in VOICING_OPTIONS
        assert chord in BASS_ROOTS
        assert chord in _GUIDE_TONES


def test_amadd9_has_no_seventh_and_includes_the_ninth():
    # Amadd9 = A minor triad + 9th, no 7th at all -- distinct from Am7/Am9.
    voicing = VOICING_OPTIONS["Amadd9"][0]
    pitch_classes = {n % 12 for n in voicing}
    root_pc = BASS_ROOTS["Amadd9"] % 12
    ninth_pc = (root_pc + 2) % 12
    seventh_pc = (root_pc + 10) % 12
    assert ninth_pc in pitch_classes
    assert seventh_pc not in pitch_classes


def test_dmsus4_has_no_third():
    # A sus chord's whole identity is the absent 3rd -- assert neither the
    # major nor minor 3rd pitch class appears.
    voicing = VOICING_OPTIONS["Dmsus4"][0]
    pitch_classes = {n % 12 for n in voicing}
    root_pc = BASS_ROOTS["Dmsus4"] % 12
    minor_third_pc = (root_pc + 3) % 12
    major_third_pc = (root_pc + 4) % 12
    assert minor_third_pc not in pitch_classes
    assert major_third_pc not in pitch_classes


def test_drone_progression_exists_and_uses_long_holds():
    drone_prog = PROGRESSIONS[59]
    chord_names = [c for c, _ in drone_prog]
    assert "Amadd9" in chord_names
    assert "Dmsus4" in chord_names
    # "A drone holds, it doesn't cycle" -- every chord duration should be a
    # genuinely long hold (4+ bars), not a quick jazz-turnaround-style
    # 1-2 bar change.
    assert all(dur >= 4 for _, dur in drone_prog)


def test_progression_key_stays_length_matched():
    assert len(PROGRESSION_KEY) == len(PROGRESSIONS)
    assert PROGRESSION_KEY[59] == "Am"


def test_drone_progression_resolves_via_voice_lead_choice():
    drone_prog = PROGRESSIONS[59]
    prev_top = None
    for chord_name, _dur in drone_prog:
        voicing = _voice_lead_choice(chord_name, prev_top)
        assert voicing
        prev_top = voicing[-1]


def test_drone_progression_works_through_build_chords():
    events = build_chords(PROGRESSIONS[59], start_bar=0, num_loops=1, swing=0.6, bpm=76)
    assert events
