"""
Regression coverage for the storytelling-arc + instrument revamp:
  A. melody instrument no longer literal GM Acoustic Grand Piano
  B. bridge ('BR') section is a real reharmonization, not a repeat of `prog`
  C/D. tension-driven density ('dense' tier + phrase-probability) actually
       produces denser output than the neutral baseline, and the build-up
       fill helper produces a real velocity ramp
"""
import random

import scripts.generate_music_gemini as gmg
from scripts.generate_music_gemini import (
    PROGRESSIONS,
    _SUBGENRE_CONFIG,
    _bridge_progression,
    build_buildup_fill,
    build_melody,
)

_ALL_SUBGENRES = list(_SUBGENRE_CONFIG)


def test_no_subgenre_uses_gm_piano_for_melody():
    for name, cfg in _SUBGENRE_CONFIG.items():
        assert cfg['melody'] != 0, f"{name}: melody instrument still GM Acoustic Grand Piano"


def test_melody_instrument_differs_from_chord_instrument_for_previously_broken_subgenres():
    fixed = {'chillhop', 'hip_hop_lofi', 'lo_fi_funk', 'neo_soul', 'bossa_lofi',
             'dark_lofi', 'lofi_phonk', 'city_pop', 'study_lofi'}
    for name in fixed:
        cfg = _SUBGENRE_CONFIG[name]
        assert cfg['melody'] != cfg['piano'], (
            f"{name}: melody and chord instruments are the same program "
            f"({cfg['melody']}) -- still stacking one timbre"
        )


def test_bridge_progression_differs_from_main_progression():
    for idx, prog in enumerate(PROGRESSIONS):
        random.seed(idx)
        bridge = _bridge_progression('Am', prog)
        chord_names = [c for c, _ in prog]
        bridge_names = [c for c, _ in bridge]
        assert bridge_names != chord_names, (
            f"PROGRESSIONS[{idx}] bridge is identical to the main progression: {chord_names}"
        )


def test_bridge_progression_stays_in_valid_dur_tuple_shape():
    prog = PROGRESSIONS[0]
    bridge = _bridge_progression('C', prog)
    assert bridge, "bridge progression must not be empty"
    for chord_name, dur in bridge:
        assert isinstance(chord_name, str)
        assert isinstance(dur, int) and dur >= 1


def test_dense_tension_melody_produces_more_notes_than_medium_baseline():
    # Directly pins the mechanism the climax loop relies on (Part D): the
    # 'dense' density tier + tension=1.0 should read as busier than the
    # existing 'medium'/tension=0.5 (neutral) baseline, on average across
    # many seeds (single-seed comparisons are too noisy given the
    # probabilistic phrase-trigger roll).
    dense_counts = []
    medium_counts = []
    for trial in range(30):
        random.seed(trial)
        dense_counts.append(len(build_melody(57, 0, 8, 0.6, 80, 'dense', 'pent', tension=1.0)))
        random.seed(trial)
        medium_counts.append(len(build_melody(57, 0, 8, 0.6, 80, 'medium', 'pent', tension=0.5)))
    assert sum(dense_counts) > sum(medium_counts), (
        f"dense/tension=1.0 ({sum(dense_counts)} notes) not denser than "
        f"medium/tension=0.5 ({sum(medium_counts)} notes) across 30 trials"
    )


def test_build_buildup_fill_ramps_velocity_upward():
    random.seed(0)
    events = build_buildup_fill(end_bar=8, num_bars=2, swing=0.6, bpm=80)
    assert events, "build_buildup_fill produced no events"
    first_half = [e for e in events if e[0] < 8 * gmg.BAR - gmg.BAR]
    second_half = [e for e in events if e[0] >= 8 * gmg.BAR - gmg.BAR]
    assert first_half and second_half
    avg_first = sum(e[2] for e in first_half) / len(first_half)
    avg_second = sum(e[2] for e in second_half) / len(second_half)
    assert avg_second > avg_first, "velocity should ramp up toward the end of the fill"


def test_build_buildup_fill_is_denser_in_final_bar():
    random.seed(0)
    events = build_buildup_fill(end_bar=8, num_bars=2, swing=0.6, bpm=80)
    first_bar_hits = [e for e in events if e[0] < 7 * gmg.BAR]
    last_bar_hits  = [e for e in events if e[0] >= 7 * gmg.BAR]
    assert len(last_bar_hits) >= len(first_bar_hits), (
        "subdivision density should ramp up (more hits) toward the end of the fill"
    )
