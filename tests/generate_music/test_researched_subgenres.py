"""
Regression coverage for the 3 research-driven candidate subgenres added in
config/genres/sleep_lofi.yaml, lofi_garage.yaml, lofi_synthwave.yaml (see
research/subgenres/sleep_lofi.md, lofi_garage.md, lofi_synthwave.md).
Follows test_new_subgenres.py's pattern for lofi_drill/lofi_world. Also
covers the one Task-5 drum-groove addition (new curated pattern Q, wired
into the existing lofi_phonk subgenre) since it landed in the same pass.
"""
import random

import mido
import pytest

import scripts.generate_music_gemini as gmg
from scripts.generate_music_gemini import (
    CHH,
    KICK,
    PPQN,
    SNARE,
    DRUM_PATTERNS,
    GM_EP2,
    GM_MARIMBA,
    GM_ORGAN_ROCK,
    GM_RHODES,
    GM_STRINGS,
    GM_VIBRAPHONE,
    GM_WARM_PAD,
    PROGRESSIONS,
    _PITCHWHEEL_NOTE,
    _SUBGENRE_CONFIG,
    _SUBGENRE_TEXTURE,
    _SWING_RANGE,
    grid_tick,
)

_NEW_SUBGENRES = ('sleep_lofi', 'lofi_garage', 'lofi_synthwave')

# Same envelope test_genre_authenticity.py uses for the rest of the roster --
# none of these 3 needed a BPM-ceiling override (unlike lofi_house/city_pop).
_LOFI_BPM_FLOOR, _LOFI_BPM_CEILING = 55, 105

# Chord-instrument allowlist test_genre_authenticity.py enforces for every
# subgenre's piano_program.
_LOFI_CHORD_INSTRUMENTS = {GM_RHODES, GM_EP2, GM_VIBRAPHONE, GM_WARM_PAD}


def test_new_subgenres_are_registered():
    for name in _NEW_SUBGENRES:
        assert name in _SUBGENRE_CONFIG
        assert name in _SWING_RANGE


def test_new_subgenre_bpm_ranges_are_within_lofi_tempo_envelope():
    for name in _NEW_SUBGENRES:
        lo, hi = _SUBGENRE_CONFIG[name]['bpm']
        assert _LOFI_BPM_FLOOR <= lo <= hi <= _LOFI_BPM_CEILING, (
            f"{name}: bpm range {(lo, hi)} outside lofi envelope "
            f"[{_LOFI_BPM_FLOOR}, {_LOFI_BPM_CEILING}]"
        )


def test_new_subgenre_drum_pattern_indices_are_valid():
    for name in _NEW_SUBGENRES:
        for idx in _SUBGENRE_CONFIG[name]['drum_pats']:
            assert 0 <= idx < len(DRUM_PATTERNS), f"{name}: drum pattern index {idx} out of range"


def test_new_subgenre_progression_indices_are_valid():
    for name in _NEW_SUBGENRES:
        for idx in _SUBGENRE_CONFIG[name]['progs']:
            assert 0 <= idx < len(PROGRESSIONS), f"{name}: progression index {idx} out of range"


def test_new_subgenres_use_a_chill_chord_instrument():
    for name in _NEW_SUBGENRES:
        piano = _SUBGENRE_CONFIG[name]['piano']
        assert piano in _LOFI_CHORD_INSTRUMENTS, (
            f"{name}: piano program {piano} isn't in the lofi chord-instrument "
            f"set {_LOFI_CHORD_INSTRUMENTS}"
        )


def test_new_subgenre_swing_ranges_never_dip_below_straight_timing():
    for name in _NEW_SUBGENRES:
        lo, hi = _SWING_RANGE[name]
        assert lo >= 0.5, f"{name}: swing range ({lo}, {hi}) dips below straight timing"
        assert hi >= lo


def test_sleep_lofi_uses_smooth_envelope_non_percussive_voices():
    # research/subgenres/sleep_lofi.md: "music built from smooth-envelope
    # instruments is fundamentally less arousing than music with percussive
    # attack-heavy sounds" -- piano/melody/countermelody should all be pad/
    # mallet/EP voices, and its progression pool should be the roster's most
    # static (single held chords / long 2-chord vamps only).
    cfg = _SUBGENRE_CONFIG['sleep_lofi']
    assert cfg['piano'] == GM_WARM_PAD
    assert cfg['melody'] == GM_RHODES
    assert cfg['cmelo'] == GM_VIBRAPHONE
    assert _SUBGENRE_TEXTURE['sleep_lofi'][1] == 'breath'


def test_lofi_garage_has_a_distinct_harmonic_fingerprint_from_lofi_house():
    # research/subgenres/lofi_garage.md: "jazzy 7ths and minor 9ths, classic
    # organ riffs, lo-fi pads, and housey piano chords" -- a genuinely
    # different instrument palette from lofi_house's GM_VIBRAPHONE melody.
    garage = _SUBGENRE_CONFIG['lofi_garage']
    house = _SUBGENRE_CONFIG['lofi_house']
    assert garage['melody'] == GM_ORGAN_ROCK
    assert garage['melody'] != house['melody']
    # Heaviest swing band in the roster, now backed by an actual per-hit
    # micro-timing engine (see test_lofi_garage_is_in_micro_swing_genres in
    # test_engine_feature_micro_swing.py) rather than only approximated by
    # a uniform swing_range.
    lo, hi = _SWING_RANGE['lofi_garage']
    all_other_highs = [h for name, (_, h) in _SWING_RANGE.items() if name != 'lofi_garage']
    assert hi >= max(all_other_highs)
    assert 'lofi_garage' in gmg._MICRO_SWING_GENRES


def test_lofi_synthwave_uses_a_lydian_leaning_scale_and_prog_pool():
    # research/subgenres/lofi_synthwave.md: simple 2-3 chord loops, lydian
    # color, continuous chord-tone arpeggiator as the melodic engine (see
    # test_engine_feature_arpeggiator.py for the arpeggiator itself).
    cfg = _SUBGENRE_CONFIG['lofi_synthwave']
    assert 'lydian' in cfg['scale']
    assert cfg['cmelo'] == GM_STRINGS
    assert _SUBGENRE_TEXTURE['lofi_synthwave'] == (GM_MARIMBA, 'pop')
    assert 'lofi_synthwave' in gmg._CONTINUOUS_ARP_GENRES


def test_drum_pattern_q_phonk_hat_roll_has_expected_shape():
    # research/theory/rhythm-groove.md Task 5: new curated pattern (index 16)
    # -- straight-8th hat base + a roll-burst on the bar's back quarter +
    # cowbell-style RIM accents, referenced from lofi_phonk.yaml.
    from scripts.generate_music_gemini import CHH, KICK, OHH, RIM, SNARE
    pattern = DRUM_PATTERNS[16]
    for voice in (KICK, SNARE, CHH, RIM):
        assert voice in pattern
        assert len(pattern[voice]) == 16
        assert all(0 <= v <= 127 for v in pattern[voice])
    # The roll burst: the last 4 steps of CHH should be denser/louder than
    # the steady 8th-note base earlier in the bar.
    chh = pattern[CHH]
    assert all(v > 0 for v in chh[-4:]), "expected a hit on every one of the last 4 steps (roll burst)"
    assert chh[-1] > chh[0], "roll burst should build in velocity toward the end of the bar"
    # Cowbell-style RIM accents on the "and" of 2 and 4 (steps 6, 14).
    assert pattern[RIM][6] > 0 and pattern[RIM][14] > 0
    assert 16 in _SUBGENRE_CONFIG['lofi_phonk']['drum_pats']


def test_pick_params_works_for_all_3_new_subgenres_across_many_seeds():
    for name in _NEW_SUBGENRES:
        for seed in range(10):
            random.seed(seed)
            params = gmg.pick_params(genre_hint=name)
            assert params['sub_genre'] == name
            lo, hi = _SUBGENRE_CONFIG[name]['bpm']
            assert lo <= params['bpm'] <= hi
            assert params['swing'] >= 0.5


# ── End-to-end: build_midi() actually exercises each subgenre's new engine
# feature (Feature 1/2/3 -- 808 glide bass, per-voice micro-swing drums,
# continuous arpeggiator melody), not just the unit-level builder functions
# tested in test_engine_feature_808_glide.py / _micro_swing.py / _arpeggiator.py.

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


def _track_for_channel(mid, channel):
    for track in mid.tracks:
        if any(getattr(m, 'channel', None) == channel for m in track):
            return track
    return None


def test_lofi_drill_build_midi_bass_track_has_pitch_bend_events(_isolated_music_dir, tmp_path):
    random.seed(0)
    params = gmg.pick_params(genre_hint='lofi_drill')
    assert params['sub_genre'] == 'lofi_drill'
    out_path = tmp_path / 'drill.mid'
    gmg.build_midi(params, str(out_path))

    mid = mido.MidiFile(str(out_path))
    bass_track = _track_for_channel(mid, 1)
    assert bass_track is not None
    assert any(m.type == 'pitchwheel' for m in bass_track), (
        "lofi_drill's rendered bass track should contain pitch-bend (808 glide) events"
    )
    # RPN pitch-bend-range setup should precede the first pitchwheel message.
    types = [m.type for m in bass_track if m.type in ('control_change', 'pitchwheel')]
    first_bend = types.index('pitchwheel')
    assert 'control_change' in types[:first_bend]


def test_lofi_garage_build_midi_drum_track_shows_per_voice_micro_timing(_isolated_music_dir, tmp_path):
    random.seed(0)
    params = gmg.pick_params(genre_hint='lofi_garage')
    assert params['sub_genre'] == 'lofi_garage'
    out_path = tmp_path / 'garage.mid'
    gmg.build_midi(params, str(out_path))

    mid = mido.MidiFile(str(out_path))
    drum_track = _track_for_channel(mid, 9)
    assert drum_track is not None

    bpm, swing = params['bpm'], params['swing']
    ticks_per_ms = (PPQN * bpm) / 60_000.0
    abs_t = 0
    by_voice = {KICK: [], SNARE: [], CHH: []}
    for m in drum_track:
        abs_t += m.time
        if m.type == 'note_on' and m.velocity > 0 and m.note in by_voice:
            # Local search around the linear estimate (grid_tick is roughly
            # g*S16, monotonic in g) -- cheap and correct at any track length,
            # unlike scanning a fixed exhaustive range.
            approx_g = round(abs_t / (PPQN // 4))
            best_grid = min(range(max(0, approx_g - 4), approx_g + 5),
                            key=lambda g: abs(grid_tick(g, swing) - abs_t))
            by_voice[m.note].append((abs_t - grid_tick(best_grid, swing)) / ticks_per_ms)

    assert all(len(v) >= 4 for v in by_voice.values()), (
        f"expected several hits per voice to compare, got {[len(v) for v in by_voice.values()]}"
    )
    # Kick should stay closer to the grid (tighter, near-zero-bias micro_swing
    # profile) than the hats (widest jitter + latest push -- 2-step's
    # off-grid hi-hat signature) -- print for the smoke-test inspection too.
    import statistics
    kick_std = statistics.pstdev(by_voice[KICK])
    hat_std = statistics.pstdev(by_voice[CHH])
    print(f"  [lofi_garage micro-swing] kick std={kick_std:.2f}ms hat std={hat_std:.2f}ms "
          f"kick sample={by_voice[KICK][:4]} hat sample={by_voice[CHH][:4]}")
    assert kick_std < hat_std


def test_lofi_synthwave_build_midi_lead_track_is_a_dense_continuous_run(_isolated_music_dir, tmp_path):
    random.seed(0)
    params = gmg.pick_params(genre_hint='lofi_synthwave')
    assert params['sub_genre'] == 'lofi_synthwave'
    out_path = tmp_path / 'synthwave.mid'
    gmg.build_midi(params, str(out_path))

    mid = mido.MidiFile(str(out_path))
    lead_track = _track_for_channel(mid, 2)
    assert lead_track is not None, "expected a melody track on channel 2"

    abs_t, ons = 0, []
    for m in lead_track:
        abs_t += m.time
        if m.type == 'note_on' and m.velocity > 0:
            ons.append(abs_t)
    assert len(ons) > 20, "arpeggiator should produce many notes, not a sparse phrase melody"
    gaps = [b - a for a, b in zip(ons, ons[1:])]
    from scripts.generate_music_gemini import S16
    # A phrase-based build_melody() lead routinely leaves multi-bar rests
    # between phrases; a continuous arpeggiator should be tight-gapped almost
    # everywhere -- allow for the handful of real section-boundary gaps
    # (e.g. the 'BR' bridge section, which channel 2 doesn't cover) without
    # letting the overall run be sparse/phrase-like.
    tight_frac = sum(1 for g in gaps if g < S16 * 2) / len(gaps)
    assert tight_frac > 0.9, (
        f"expected a dense, near-continuous run of arpeggio notes, got only "
        f"{tight_frac:.0%} of inter-note gaps under a subdivision step"
    )
