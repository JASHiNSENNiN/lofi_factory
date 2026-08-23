"""
Regression coverage for the two subgenres research surfaced as missing from
the existing 24: drill/trap-adjacent lofi and world/ethnic-fusion lofi.
"""
import random

from scripts.generate_music_gemini import (
    CHH, KICK, OHH, RIM, SNARE,
    DRUM_PATTERNS,
    GM_KALIMBA,
    GM_KOTO,
    GM_SITAR,
    PROGRESSIONS,
    _GLIDE_808_GENRES,
    _SUBGENRE_CONFIG,
    _SUBGENRE_TEXTURE,
    _SWING_RANGE,
    get_phrygian_dominant,
)


def test_phrygian_dominant_has_the_right_intervals():
    # 1, b2, 3, 4, 5, b6, b7 -- major 3rd distinguishes it from plain Phrygian
    # (get_phrygian's all-minor 1,b2,b3,4,5,b6,b7).
    notes = get_phrygian_dominant(60)  # root = C
    pitch_classes = sorted({n % 12 for n in notes})
    assert pitch_classes == [0, 1, 4, 5, 7, 8, 10]


def test_lofi_drill_and_lofi_world_are_registered():
    assert 'lofi_drill' in _SUBGENRE_CONFIG
    assert 'lofi_world' in _SUBGENRE_CONFIG
    assert 'lofi_drill' in _SWING_RANGE
    assert 'lofi_world' in _SWING_RANGE


def test_lofi_drill_uses_808_glide_bass():
    # research/subgenres/lofi_drill.md: "the sliding/gliding 808 bass...the
    # single most recognizable production element in modern drill" -- see
    # test_engine_feature_808_glide.py for the feature itself.
    assert 'lofi_drill' in _GLIDE_808_GENRES
    assert 'lofi_world' not in _GLIDE_808_GENRES


def test_new_subgenre_drum_pattern_indices_are_valid():
    for name in ('lofi_drill', 'lofi_world'):
        for idx in _SUBGENRE_CONFIG[name]['drum_pats']:
            assert 0 <= idx < len(DRUM_PATTERNS), f"{name}: drum pattern index {idx} out of range"


def test_new_subgenre_progression_indices_are_valid():
    for name in ('lofi_drill', 'lofi_world'):
        for idx in _SUBGENRE_CONFIG[name]['progs']:
            assert 0 <= idx < len(PROGRESSIONS), f"{name}: progression index {idx} out of range"


def test_drum_pattern_p_drill_bounce_has_expected_shape():
    pattern = DRUM_PATTERNS[15]
    for voice in (KICK, SNARE, CHH):
        assert voice in pattern
        assert len(pattern[voice]) == 16
        assert all(0 <= v <= 127 for v in pattern[voice])
    # It's meant to actually be a bounce/roll, not silence.
    assert sum(1 for v in pattern[KICK] if v > 0) >= 2
    assert sum(1 for v in pattern[CHH] if v > 0) >= 8


def test_lofi_world_uses_ethnic_instrument_voices():
    cfg = _SUBGENRE_CONFIG['lofi_world']
    assert cfg['melody'] == GM_SITAR
    assert cfg['cmelo'] == GM_KOTO
    assert _SUBGENRE_TEXTURE['lofi_world'][0] == GM_KALIMBA


def test_lofi_world_scale_pool_includes_phrygian_dominant():
    assert 'phryg_dom' in _SUBGENRE_CONFIG['lofi_world']['scale']


def test_pick_params_works_for_both_new_subgenres_across_many_seeds():
    import scripts.generate_music_gemini as gmg
    for name in ('lofi_drill', 'lofi_world'):
        for seed in range(10):
            random.seed(seed)
            params = gmg.pick_params(genre_hint=name)
            assert params['sub_genre'] == name
            lo, hi = _SUBGENRE_CONFIG[name]['bpm']
            assert lo <= params['bpm'] <= hi
