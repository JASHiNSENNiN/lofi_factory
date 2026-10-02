import pytest

isobar = pytest.importorskip("isobar")

from scripts.composer import _build_self_markov, _markov_next_pitch_class


def test_build_self_markov_values_are_lists_of_successors():
    nodes = _build_self_markov([[0, 4, 7, 0, 4], [2, 5, 9, 2]])
    assert isinstance(nodes, dict)
    for value in nodes.values():
        assert isinstance(value, list)
        assert all(isinstance(pc, int) for pc in value)


def test_build_self_markov_tracks_do_not_cross_contaminate():
    # learner.last is reset between tracks, so a transition never bridges
    # across two unrelated input tracks -- the single most important
    # behavioral guarantee this function claims.
    nodes = _build_self_markov([[0, 0, 0], [7, 7, 7]])
    assert 7 not in nodes.get(0, [])
    assert 0 not in nodes.get(7, [])


def test_build_self_markov_empty_history():
    assert _build_self_markov([]) == {}


def test_markov_next_pitch_class_filters_to_scale():
    results = {
        _markov_next_pitch_class({0: [2, 2, 4]}, prev_pc=0, scale_pcs={2, 4, 7})
        for _ in range(30)
    }
    assert results <= {2, 4}
    assert results  # actually produced at least one value


def test_markov_next_pitch_class_returns_none_when_successor_not_in_scale():
    assert _markov_next_pitch_class({0: [2]}, prev_pc=0, scale_pcs={9}) is None


def test_markov_next_pitch_class_returns_none_on_empty_table():
    assert _markov_next_pitch_class({}, prev_pc=0, scale_pcs={0}) is None


def test_markov_next_pitch_class_accepts_dict_of_counts_shape():
    # The separate MidiDNA.markov_melody_nodes path produces {pc: {succ: count}}
    # rather than the list-of-successors shape _build_self_markov produces --
    # both must be handled.
    results = {
        _markov_next_pitch_class({0: {2: 3, 4: 1}}, prev_pc=0, scale_pcs={2, 4})
        for _ in range(30)
    }
    assert results <= {2, 4}
    assert results


def test_markov_table_is_key_relative():
    # Degree 0 -> degree 7 (tonic to fifth). In D (root 2) that's D -> A.
    nodes = {0: [7]}
    assert _markov_next_pitch_class(nodes, prev_pc=2, scale_pcs={9}, root_pc=2) == 9
    # In C the same table means C -> G.
    assert _markov_next_pitch_class(nodes, prev_pc=0, scale_pcs={7}, root_pc=0) == 7
