"""
Structural checks that generated output actually reads as "lofi" and not
just "valid MIDI that happens to pass the quality gate." No audio renderer
is available on this machine (no FluidSynth), so this can't listen to the
result -- instead it pins down the parametric/harmonic signatures that
distinguish lofi/jazz-hop from generic pop or EDM: tempo range, swung
(non-quantized) timing, chill jazz-family instrumentation, and an
extended/altered chord vocabulary (7ths/9ths, not plain triads).
"""
import random

import scripts.composer as gmg
from scripts.composer import (
    GM_EP2,
    GM_RHODES,
    GM_VIBRAPHONE,
    GM_WARM_PAD,
    VOICING_OPTIONS,
    _SUBGENRE_CONFIG,
    _SWING_DEFAULT,
    _SWING_RANGE,
)

# Widely-cited lofi hip-hop / chillhop tempo envelope. Anything outside this
# reads as a different genre (drum & bass, ambient drone, etc.).
_LOFI_BPM_FLOOR, _LOFI_BPM_CEILING = 55, 105

# Deliberate, documented per-subgenre ceiling overrides -- not a bug, a real
# genre-tempo fact the generic 55-105 lofi envelope was never designed to
# cover:
#   lofi_house: research/subgenres/lofi_house.md -- real "lofi house" (Mall
#     Grab/DJ Boring/Ross From Friends/DJ Seinfeld) runs at house's standard
#     ~115-126 BPM four-on-the-floor tempo, not the 70-90 lofi-hip-hop range.
#     Clamping it into [55,105] would misrepresent the actual genre.
#   city_pop: research/subgenres/city_pop.md -- "city pop lives in the
#     95-120 BPM range, with mid-tempo groove being a defining
#     characteristic," distinctly faster than lofi hip-hop; capped at 108
#     (below full disco/funk 120) to stay lofi-compatible while still
#     honoring the real convention.
_BPM_CEILING_OVERRIDES = {
    'lofi_house': 128,
    'city_pop': 108,
}

# Chill, jazz-family instrument voices lofi is built on -- deliberately
# excludes synth leads, distortion guitar, brass sections, etc.
_LOFI_CHORD_INSTRUMENTS = {GM_RHODES, GM_EP2, GM_VIBRAPHONE, GM_WARM_PAD}

_JAZZY_MARKERS = ('7', '9', '11', '13', 'dim', 'aug')


def test_every_subgenre_bpm_range_is_within_lofi_tempo_envelope():
    for name, cfg in _SUBGENRE_CONFIG.items():
        lo, hi = cfg['bpm']
        ceiling = _BPM_CEILING_OVERRIDES.get(name, _LOFI_BPM_CEILING)
        assert _LOFI_BPM_FLOOR <= lo <= hi <= ceiling, (
            f"{name}: bpm range {cfg['bpm']} outside lofi envelope "
            f"[{_LOFI_BPM_FLOOR}, {ceiling}]"
        )


def test_every_subgenre_uses_a_chill_chord_instrument():
    for name, cfg in _SUBGENRE_CONFIG.items():
        assert cfg['piano'] in _LOFI_CHORD_INSTRUMENTS, (
            f"{name}: piano program {cfg['piano']} isn't in the lofi "
            f"chord-instrument set {_LOFI_CHORD_INSTRUMENTS}"
        )


def test_chord_vocabulary_is_dominated_by_extended_jazz_chords():
    # A generic pop/rock progression is mostly plain major/minor triads.
    # Lofi/jazz-hop's defining harmonic signature is 7ths/9ths/11ths/13ths.
    extended = [c for c in VOICING_OPTIONS if any(m in c for m in _JAZZY_MARKERS)]
    assert len(extended) / len(VOICING_OPTIONS) >= 0.8


def test_swing_range_never_goes_below_straight_timing():
    # 0.5 == perfectly straight (no swing bias); ranges may legitimately
    # touch it -- ambient/lofi_classical/vaporwave lean on a straighter,
    # more rubato/mechanical feel than boom-bap-derived lofi hip-hop's
    # signature "drunk" swing -- but must never dip below it (negative
    # swing bias reads as a timing bug, not a genre choice).
    all_ranges = list(_SWING_RANGE.values()) + [_SWING_DEFAULT]
    for lo, hi in all_ranges:
        assert lo >= 0.5, f"swing range ({lo}, {hi}) dips below straight timing"
        assert hi >= lo


def test_generated_tracks_stay_within_genre_bounds_across_many_seeds(tmp_path, monkeypatch):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    monkeypatch.setattr(gmg, "MUSIC_DIR", str(music_dir))
    monkeypatch.setattr(gmg, "_PARAMS_HISTORY_FILE", str(music_dir / ".params_history.json"))
    monkeypatch.setattr(gmg, "_MELODY_HISTORY_FILE", str(music_dir / ".melody_history.json"))
    monkeypatch.setattr(gmg, "_RECIPE_LOG_FILE", str(music_dir / ".recipe_log.jsonl"))

    for seed in range(15):
        random.seed(seed)
        params = gmg.pick_params()
        ceiling = _BPM_CEILING_OVERRIDES.get(params.get('sub_genre'), _LOFI_BPM_CEILING)
        assert _LOFI_BPM_FLOOR <= params['bpm'] <= ceiling
        assert params['swing'] >= 0.5
