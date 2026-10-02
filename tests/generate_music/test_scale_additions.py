"""
Regression coverage for the four scales research/theory/scales-modes-gaps.md
identified as missing: melodic minor (jazz minor), locrian, altered
(super-locrian), and bebop dominant. Mirrors the style of
test_new_subgenres.py's test_phrygian_dominant_has_the_right_intervals.
"""
from scripts.composer import (
    build_melody,
    get_altered,
    get_bebop_dominant,
    get_locrian,
    get_melodic_minor,
    _resolve_scale,
)


def test_melodic_minor_has_the_right_intervals():
    # 1, 2, b3, 4, 5, 6, 7 -- major scale with a minor 3rd (raised 6th AND
    # 7th vs. natural minor, unlike harmonic_minor which only raises the 7th).
    notes = get_melodic_minor(60)  # root = C
    pitch_classes = sorted({n % 12 for n in notes})
    assert pitch_classes == [0, 2, 3, 5, 7, 9, 11]


def test_locrian_has_the_right_intervals():
    # 1, b2, b3, 4, b5, b6, b7 -- the only diatonic major-scale mode with a
    # diminished 5th (half-diminished color, pairs with Bm7b5).
    notes = get_locrian(60)
    pitch_classes = sorted({n % 12 for n in notes})
    assert pitch_classes == [0, 1, 3, 5, 6, 8, 10]


def test_altered_has_the_right_intervals():
    # 1, b9, #9, 3, b5, b13, b7 -- every degree but the root flattened
    # relative to major; structurally distinct from phryg_dom (natural 5th).
    notes = get_altered(60)
    pitch_classes = sorted({n % 12 for n in notes})
    assert pitch_classes == [0, 1, 3, 4, 6, 8, 10]


def test_bebop_dominant_has_the_right_intervals():
    # Mixolydian (1,2,3,4,5,6,b7) plus a chromatic passing major-7th between
    # b7 and the octave root -- 8 notes, the only 8-note scale in the file.
    notes = get_bebop_dominant(60)
    pitch_classes = sorted({n % 12 for n in notes})
    assert pitch_classes == [0, 2, 4, 5, 7, 9, 10, 11]


def test_new_scales_are_structurally_distinct_from_existing_exotic_scales():
    # altered (dim 5th) must not collapse onto phryg_dom (natural 5th) even
    # though both are "exotic dominant" scales built from the same root.
    altered_pcs = {n % 12 for n in get_altered(60)}
    assert 6 in altered_pcs   # b5/#11 present
    assert 7 not in altered_pcs  # natural 5th absent


def test_resolve_scale_dispatches_all_four_new_scale_names():
    for name, fn in [
        ('melodic_minor', get_melodic_minor),
        ('locrian', get_locrian),
        ('altered', get_altered),
        ('bebop_dominant', get_bebop_dominant),
    ]:
        assert _resolve_scale(name, 60) == fn(60)


def test_build_melody_accepts_each_new_scale_without_raising():
    for name in ('melodic_minor', 'locrian', 'altered', 'bebop_dominant'):
        events = build_melody(60, 0, 8, 0.6, 80, density='medium', scale=name)
        assert isinstance(events, list)
