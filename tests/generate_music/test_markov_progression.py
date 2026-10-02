import random

from scripts.composer import (
    VOICING_OPTIONS,
    _build_progression_markov,
    _JAZZY_MARKERS,
    generate_progression,
    maybe_sub_chord,
)


def test_build_progression_markov_shape():
    markov = _build_progression_markov()
    assert set(markov.keys()) == {'transitions', 'start_counts', 'duration_counts'}
    assert markov['transitions']
    for successors in markov['transitions'].values():
        assert successors
        assert all(isinstance(v, int) for v in successors.values())


def test_build_progression_markov_is_cached():
    # module-level cache: repeated calls return the same object, not a rebuild
    assert _build_progression_markov() is _build_progression_markov()


def test_generate_progression_respects_seed_chord():
    prog = generate_progression(length=4, jazziness=0.5, seed_chord='Am7')
    assert len(prog) == 4
    # position 0 is never substituted by maybe_sub_chord, so the first
    # element must be the literal seed chord.
    assert prog[0][0] == 'Am7'


def test_generate_progression_entries_are_valid():
    prog = generate_progression(length=8, jazziness=0.3, seed_chord='Dm7')
    for chord_name, dur in prog:
        assert chord_name in VOICING_OPTIONS
        assert isinstance(dur, int) and dur > 0


def test_generate_progression_length_one_does_not_crash():
    prog = generate_progression(length=1)
    assert len(prog) == 1


def test_generate_progression_unknown_seed_chord_falls_back():
    # 'NotAChord' isn't in the Markov table's transition keys, so it should
    # fall back to a weighted-random start rather than raising.
    prog = generate_progression(length=4, seed_chord='NotAChord')
    assert len(prog) == 4
    assert prog[0][0] != 'NotAChord'


def test_jazziness_increases_fraction_of_jazzy_chords():
    # Statistical property over many seeded trials, not a single sample --
    # a one-shot comparison would be flaky given the weighted random choice.
    def jazzy_fraction(jazziness, trials=150):
        total = jazzy = 0
        for i in range(trials):
            random.seed(i)
            for chord_name, _dur in generate_progression(length=6, jazziness=jazziness):
                total += 1
                if any(marker in chord_name for marker in _JAZZY_MARKERS):
                    jazzy += 1
        return jazzy / total

    low = jazzy_fraction(0.0)
    high = jazzy_fraction(1.0)
    assert high >= low


def test_maybe_sub_chord_never_changes_position_zero():
    for i in range(50):
        random.seed(i)
        assert maybe_sub_chord('Dm7', 0) == 'Dm7'
