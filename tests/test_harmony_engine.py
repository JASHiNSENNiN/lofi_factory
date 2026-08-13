import pytest

music21 = pytest.importorskip("music21")

from scripts.harmony_engine import (
    TONAL_CENTERS,
    HarmonyProgression,
    center_for_key,
    generate_functional_progression,
    realize_numeral_pitches,
    validate_roman_numerals,
)


# ── generate_functional_progression ──────────────────────────────────────────

@pytest.mark.parametrize("center", TONAL_CENTERS)
@pytest.mark.parametrize("mode", ["major", "minor"])
def test_generated_progression_is_nonempty(center, mode):
    hp = generate_functional_progression(center, mode, length=4, seed=1)
    assert isinstance(hp, HarmonyProgression)
    assert len(hp.chords) >= 1
    assert len(hp.chords) == len(hp.roman_numerals)


@pytest.mark.parametrize("center", TONAL_CENTERS)
@pytest.mark.parametrize("mode", ["major", "minor"])
def test_generated_progression_is_valid_roman_numeral_sequence(center, mode):
    for seed in range(6):
        hp = generate_functional_progression(center, mode, length=5, seed=seed)
        assert validate_roman_numerals(center, mode, hp.roman_numerals), (
            f"invalid roman numerals for {center} {mode} seed={seed}: {hp.roman_numerals}"
        )


def test_generated_progression_deterministic_with_seed():
    a = generate_functional_progression('C', 'major', length=6, seed=42)
    b = generate_functional_progression('C', 'major', length=6, seed=42)
    assert a.chords == b.chords
    assert a.roman_numerals == b.roman_numerals


def test_generated_progression_varies_with_seed():
    seen = set()
    for seed in range(10):
        hp = generate_functional_progression('C', 'major', length=5, seed=seed)
        seen.add(tuple(hp.chords))
    assert len(seen) > 1


def test_chord_symbols_come_from_existing_voicing_table():
    # Every chord symbol the harmony engine emits must already exist in the
    # pipeline's VOICING_OPTIONS table, so generated progressions always get
    # a real (not default-fallback) voicing downstream.
    from scripts.generate_music_gemini import VOICING_OPTIONS
    for center in TONAL_CENTERS:
        for mode in ("major", "minor"):
            for seed in range(5):
                hp = generate_functional_progression(center, mode, length=6, seed=seed)
                for symbol, _dur in hp.chords:
                    assert symbol in VOICING_OPTIONS, f"{symbol} missing from VOICING_OPTIONS"


def test_durations_are_positive_and_sane():
    for seed in range(5):
        hp = generate_functional_progression('Bb', 'major', length=5, seed=seed)
        for _symbol, dur in hp.chords:
            assert 1 <= dur <= 4


def test_secondary_dominant_prob_zero_never_tonicizes():
    for seed in range(10):
        hp = generate_functional_progression('C', 'major', length=6, seed=seed,
                                               secondary_dominant_prob=0.0)
        assert all('/' not in rn for rn in hp.roman_numerals)


def test_secondary_dominant_prob_one_tonicizes_when_available():
    # With prob=1.0 and a long enough progression, at least one applied
    # dominant should appear (many degrees do have a mapped secondary dom).
    found_any = False
    for seed in range(15):
        hp = generate_functional_progression('C', 'major', length=8, seed=seed,
                                               secondary_dominant_prob=1.0)
        if any('/' in rn for rn in hp.roman_numerals):
            found_any = True
            break
    assert found_any


def test_unknown_tonal_center_falls_back_to_c():
    hp = generate_functional_progression('Zz', 'major', length=3, seed=1)
    assert hp.tonal_center == 'C'


# ── center_for_key ────────────────────────────────────────────────────────────

def test_center_for_key_known_keys():
    assert center_for_key('Am') == ('C', 'minor')
    assert center_for_key('C') == ('C', 'major')
    assert center_for_key('Gm') == ('Bb', 'minor')
    assert center_for_key('Bb') == ('Bb', 'major')


def test_center_for_key_unknown_key_has_sane_fallback():
    center, mode = center_for_key('Xm')
    assert center in TONAL_CENTERS
    assert mode == 'minor'


# ── realize_numeral_pitches (cross-check against music21 ground truth) ────────

def test_realize_numeral_pitches_matches_expected_chord_tones():
    # I in C major must contain C and G pitch classes (0 and 7).
    pcs = realize_numeral_pitches('C', 'major', 'I')
    assert 0 in pcs and 7 in pcs

    # V/vi in C major is an applied dominant of A minor -> E7 -> contains E (4).
    pcs2 = realize_numeral_pitches('C', 'major', 'V7/vi')
    assert 4 in pcs2


def test_validate_roman_numerals_rejects_garbage():
    assert validate_roman_numerals('C', 'major', ['I', 'IV', 'V']) is True
    assert validate_roman_numerals('C', 'major', ['I', 'not-a-numeral']) is False
