import json
import os
import random

import mido
import pytest

import scripts.generate_music_gemini as gmg
import scripts.generate_music_v2 as gmv2
from scripts.track_quality import MIN_QUALITY_SCORE

pytestmark = pytest.mark.integration


@pytest.fixture
def isolated_music_dir(tmp_path, monkeypatch):
    """
    pick_params()/build_midi()/build_midi_v2() write to the real
    music/.params_history.json, music/.melody_history.json, and
    music/.recipe_log.jsonl as a side effect today -- redirect all three to
    tmp_path so running this test suite never pollutes production state or
    makes runs non-reproducible across CI/dev-machine invocations.
    """
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    monkeypatch.setattr(gmg, "MUSIC_DIR", str(music_dir))
    monkeypatch.setattr(gmg, "_PARAMS_HISTORY_FILE", str(music_dir / ".params_history.json"))
    monkeypatch.setattr(gmg, "_MELODY_HISTORY_FILE", str(music_dir / ".melody_history.json"))
    monkeypatch.setattr(gmg, "_RECIPE_LOG_FILE", str(music_dir / ".recipe_log.jsonl"))
    return music_dir


def test_pick_params_returns_well_formed_dict(isolated_music_dir):
    random.seed(0)
    params = gmg.pick_params()
    for field in ('key', 'progression', 'bpm', 'swing', 'sub_genre',
                  'drum_pattern_a', 'drum_pattern_b', 'drum_energy'):
        assert field in params
    assert params['sub_genre'] in gmg._SUBGENRE_CONFIG


def test_build_midi_v2_produces_valid_midi_file(isolated_music_dir, tmp_path):
    random.seed(0)
    params = gmg.pick_params()
    out_path = tmp_path / "out.mid"
    result_path = gmv2.build_midi_v2(params, str(out_path))

    assert os.path.exists(out_path)
    mid = mido.MidiFile(str(out_path))
    assert mid.type == 1
    assert mid.ticks_per_beat == 480


def test_isolated_music_dir_never_touches_real_project_music_dir(isolated_music_dir, tmp_path):
    real_music_dir = os.path.join(os.path.dirname(os.path.dirname(gmg.__file__)), 'music')
    real_params_history = os.path.join(real_music_dir, '.params_history.json')
    existed_before = os.path.exists(real_params_history)

    random.seed(0)
    params = gmg.pick_params()
    gmv2.build_midi_v2(params, str(tmp_path / "out.mid"))

    assert os.path.exists(real_params_history) == existed_before


def test_seeded_sweep_exercises_all_probabilistic_branches(isolated_music_dir, tmp_path):
    # Seed fake melody history so the self-referential Markov branch (needs
    # >=3 prior tracks) has a chance to fire during the sweep.
    with open(isolated_music_dir / ".melody_history.json", "w") as f:
        json.dump([[0, 4, 7, 2, 5, 9] * 3 for _ in range(5)], f)

    seen = {'generated_progression': False, 'drum_pattern_a_generated': False,
            'markov_melody_nodes': False}
    for seed in range(20):
        random.seed(seed)
        params = gmg.pick_params()
        for key in seen:
            if key in params:
                seen[key] = True
        out_path = tmp_path / f"out_{seed}.mid"
        gmv2.build_midi_v2(params, str(out_path))
        mido.MidiFile(str(out_path))  # must parse without error

    assert all(seen.values()), f"branches never fired across 20 seeds: {seen}"


def test_quality_gate_pass_rate_across_seeded_tracks(isolated_music_dir, tmp_path):
    # Recompute nothing by hand: build_midi_v2 already runs the quality gate
    # internally and logs the winning attempt's score to the recipe log --
    # read that back rather than re-deriving it. A poor pass rate here is a
    # real finding worth reporting, not a reason to delete the assertion.
    for seed in range(10):
        random.seed(seed)
        params = gmg.pick_params()
        gmv2.build_midi_v2(params, str(tmp_path / f"out_{seed}.mid"))

    with open(isolated_music_dir / ".recipe_log.jsonl") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    assert len(entries) == 10
    scores = [e['quality_score'] for e in entries]
    pass_rate = sum(s >= MIN_QUALITY_SCORE for s in scores) / len(scores)
    assert pass_rate >= 0.5, f"quality gate pass rate {pass_rate} over scores {scores}"


# ── build_midi() (v1) -- the ENGINE ACTUALLY RUNNING IN PRODUCTION TODAY ────
# publish.py's daily auto-run never passes --music-v2 (see the headline
# finding in the plan doc), so build_midi_v2 being tested above says nothing
# about what a real scheduled run currently produces. This mirrors that
# integration coverage for the engine that's actually live.

def test_build_midi_v1_produces_valid_midi_file(isolated_music_dir, tmp_path):
    random.seed(0)
    params = gmg.pick_params()
    out_path = tmp_path / "out_v1.mid"
    gmg.build_midi(params, str(out_path))

    assert os.path.exists(out_path)
    mid = mido.MidiFile(str(out_path))
    assert mid.type == 1
    assert mid.ticks_per_beat == 480


def test_build_midi_v1_seeded_sweep_exercises_all_probabilistic_branches(isolated_music_dir, tmp_path):
    seen = {'generated_progression': False, 'drum_pattern_a_generated': False}
    for seed in range(15):
        random.seed(seed)
        params = gmg.pick_params()
        for key in seen:
            if key in params:
                seen[key] = True
        out_path = tmp_path / f"out_v1_{seed}.mid"
        gmg.build_midi(params, str(out_path))
        mido.MidiFile(str(out_path))  # must parse without error

    assert all(seen.values()), f"branches never fired across 15 seeds: {seen}"


def test_build_midi_v1_quality_gate_pass_rate_across_seeded_tracks(isolated_music_dir, tmp_path):
    for seed in range(15):
        random.seed(seed)
        params = gmg.pick_params()
        gmg.build_midi(params, str(tmp_path / f"out_v1_{seed}.mid"))

    with open(isolated_music_dir / ".recipe_log.jsonl") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    assert len(entries) == 15
    scores = [e['quality_score'] for e in entries]
    pass_rate = sum(s >= MIN_QUALITY_SCORE for s in scores) / len(scores)
    assert pass_rate >= 0.5, f"quality gate pass rate {pass_rate} over scores {scores}"
