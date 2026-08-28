"""
Coverage for the tala-cycle polymetric overlay (research/subgenres/
lofi_world.md: "tala rhythmic cycles" alongside gamaka and drone/modal
harmony -- Phase 11's "true time-signature support" item).

build_tala_overlay() is a genuinely odd-meter (7-beat Rupak Tal, 3+2+2)
generator with its OWN independent tick grid (PPQN per beat, nothing
derived from BAR/S16/grid_tick()) -- deliberately NOT a change to the
shared 4/4 BAR/grid_tick()/DRUM_PATTERNS machinery every other genre
depends on. See its module comment in generate_music_gemini.py for the
full rationale on why this is a safe overlay rather than a full
variable-time-signature retrofit.
"""
import random

import mido
import pytest

import scripts.generate_music_gemini as gmg
from scripts import genre_presets
from scripts.generate_music_gemini import (
    BAR,
    KEY_ROOTS,
    PPQN,
    _TALA_BEAT_GROUPS,
    _TALA_OVERLAY_GENRES,
    _tala_cycle_ticks,
    build_tala_overlay,
)

_KEY_ROOT = KEY_ROOTS['Am']


# ── _tala_cycle_ticks / _TALA_BEAT_GROUPS ───────────────────────────────────

def test_tala_beat_groups_sum_to_seven():
    assert sum(_TALA_BEAT_GROUPS) == 7
    assert _TALA_BEAT_GROUPS == (3, 2, 2)


def test_tala_cycle_ticks_is_seven_beats_not_reachable_by_subdividing_bar():
    assert _tala_cycle_ticks() == 7 * PPQN
    # BAR is 4 beats -- the tala cycle is a genuinely different length, not
    # a divisor/multiple of BAR (which a same-meter regrouping would be).
    assert BAR % _tala_cycle_ticks() != 0
    assert _tala_cycle_ticks() % BAR != 0


# ── build_tala_overlay ───────────────────────────────────────────────────────

def test_unknown_scale_name_falls_back_like_build_melody_does():
    # _resolve_scale() always falls back to a real scale for any string
    # (same convention build_melody()/build_counter_melody() rely on), so
    # this never actually hits the `not notes_scale` guard -- it just
    # confirms an unrecognized name doesn't crash and still produces output.
    random.seed(1)
    events = build_tala_overlay(_KEY_ROOT, 'not_a_real_scale', 0, 10000, bpm=80)
    assert events


def test_empty_scale_result_is_a_safe_noop(monkeypatch):
    # Directly exercises the `not notes_scale` guard build_melody() also
    # has, in case _resolve_scale() is ever changed to return empty for
    # some input -- defensive, same as the sibling guard it mirrors.
    monkeypatch.setattr(gmg, '_resolve_scale', lambda scale, root: [])
    assert gmg.build_tala_overlay(_KEY_ROOT, 'dorian', 0, 10000, bpm=80) == []


def test_returns_empty_for_non_positive_duration():
    assert build_tala_overlay(_KEY_ROOT, 'dorian', 0, 0, bpm=80) == []
    assert build_tala_overlay(_KEY_ROOT, 'dorian', 0, -100, bpm=80) == []


def test_all_events_land_within_the_requested_window():
    random.seed(1)
    start, duration = 4800, 4 * _tala_cycle_ticks()
    events = build_tala_overlay(_KEY_ROOT, 'dorian', start, duration, bpm=80)
    assert events
    for t, _note, _vel, _dur in events:
        assert start <= t < start + duration


def test_events_are_well_formed_four_tuples():
    random.seed(2)
    events = build_tala_overlay(_KEY_ROOT, 'dorian', 0, 3 * _tala_cycle_ticks(), bpm=80)
    assert events
    for ev in events:
        assert len(ev) == 4
        t, note, vel, dur = ev
        assert isinstance(t, int) and t >= 0
        assert 0 < vel <= 127
        assert dur >= 1


def test_multiple_cycles_populate_the_full_requested_span():
    # Duration spanning 3 full cycles -- expect events distributed across
    # more than just the first cycle, not all clustered at the start.
    random.seed(3)
    cycle = _tala_cycle_ticks()
    events = build_tala_overlay(_KEY_ROOT, 'dorian', 0, 3 * cycle, bpm=80)
    ticks = [t for t, *_ in events]
    assert any(t < cycle for t in ticks)
    assert any(cycle <= t < 2 * cycle for t in ticks)
    assert any(2 * cycle <= t < 3 * cycle for t in ticks)


def test_first_beat_group_is_quieter_than_the_others_on_average():
    # Rupak Tal's defining "empty" downbeat: first group (3 beats) should
    # read as de-accented relative to the other two groups.
    random.seed(4)
    cycle = _tala_cycle_ticks()
    events = build_tala_overlay(_KEY_ROOT, 'dorian', 0, 40 * cycle, bpm=80)
    first_group_end = 3 * PPQN
    first_vels, other_vels = [], []
    for t, _note, vel, _dur in events:
        pos_in_cycle = t % cycle
        (first_vels if pos_in_cycle < first_group_end else other_vels).append(vel)
    assert first_vels and other_vels
    assert sum(first_vels) / len(first_vels) < sum(other_vels) / len(other_vels)


def test_first_beat_group_rests_more_often_than_the_others():
    random.seed(5)
    cycle = _tala_cycle_ticks()
    events = build_tala_overlay(_KEY_ROOT, 'dorian', 0, 60 * cycle, bpm=80)
    first_group_end = 3 * PPQN
    first_hits = sum(1 for t, *_ in events if t % cycle < first_group_end)
    other_hits = sum(1 for t, *_ in events if t % cycle >= first_group_end)
    n_cycles = 60
    # 1 possible onset in the first group per cycle, 2 possible onsets
    # (one per remaining beat-group) in "other" per cycle.
    first_rate = first_hits / n_cycles
    other_rate = other_hits / (n_cycles * 2)
    assert first_rate < other_rate


def test_bpm_does_not_change_tick_positions():
    # Ticks are tempo-independent throughout this module (same reason BAR
    # itself isn't a function of bpm) -- only the humanization jitter
    # amount (in ticks) scales with bpm, not the underlying grid.
    random.seed(6)
    events_slow = build_tala_overlay(_KEY_ROOT, 'dorian', 0, 2 * _tala_cycle_ticks(), bpm=60)
    random.seed(6)
    events_fast = build_tala_overlay(_KEY_ROOT, 'dorian', 0, 2 * _tala_cycle_ticks(), bpm=160)
    # Same random draws, same nominal grid positions before jitter -- exact
    # tick equality isn't guaranteed (jitter scales with bpm), but onset
    # COUNT and note/velocity choices (unaffected by bpm) must match.
    assert len(events_slow) == len(events_fast)
    assert [e[1] for e in events_slow] == [e[1] for e in events_fast]   # notes
    assert [e[2] for e in events_slow] == [e[2] for e in events_fast]   # velocities


# ── genre registration ───────────────────────────────────────────────────────

def test_lofi_world_is_registered_in_tala_overlay_genres():
    assert 'lofi_world' in _TALA_OVERLAY_GENRES
    assert genre_presets.build_tala_overlay_genres() == _TALA_OVERLAY_GENRES


def test_tala_overlay_genres_is_a_small_opt_in_set_not_a_default():
    assert 'lofi_drill' not in _TALA_OVERLAY_GENRES
    assert 'chillhop' not in _TALA_OVERLAY_GENRES
    assert 'nujabes' not in _TALA_OVERLAY_GENRES
    assert len(_TALA_OVERLAY_GENRES) <= 3


# ── build_midi() end-to-end wiring ──────────────────────────────────────────

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


def test_build_midi_calls_tala_overlay_for_lofi_world_across_a_seeded_sweep(
        _isolated_music_dir, tmp_path, monkeypatch):
    real_fn = gmg.build_tala_overlay
    call_results = []

    def _spy(*a, **k):
        result = real_fn(*a, **k)
        call_results.append(result)
        return result

    monkeypatch.setattr(gmg, 'build_tala_overlay', _spy)

    for seed in range(20):
        random.seed(seed)
        params = gmg.pick_params(genre_hint='lofi_world')
        assert params['sub_genre'] == 'lofi_world'
        gmg.build_midi(params, str(tmp_path / f'world_{seed}.mid'))

    assert call_results, "build_tala_overlay was never called for lofi_world across the sweep"
    assert any(r for r in call_results), "build_tala_overlay never produced any events across the sweep"


def test_build_midi_never_calls_tala_overlay_for_a_non_opted_in_genre(
        _isolated_music_dir, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(gmg, 'build_tala_overlay', lambda *a, **k: calls.append(1) or [])

    for seed in range(10):
        random.seed(seed)
        params = gmg.pick_params(genre_hint='lofi_drill')
        gmg.build_midi(params, str(tmp_path / f'drill_{seed}.mid'))

    assert not calls, "build_tala_overlay must never fire for a genre not in _TALA_OVERLAY_GENRES"


def test_lofi_world_build_midi_produces_a_valid_midi_file_with_tala_overlay_wired(
        _isolated_music_dir, tmp_path):
    # End-to-end sanity: the wiring doesn't break MIDI assembly even when
    # texture_ev picks up extra tala-overlay events.
    random.seed(0)
    params = gmg.pick_params(genre_hint='lofi_world')
    out_path = tmp_path / 'world.mid'
    gmg.build_midi(params, str(out_path))
    mid = mido.MidiFile(str(out_path))
    assert mid.type == 1
    assert mid.ticks_per_beat == PPQN
