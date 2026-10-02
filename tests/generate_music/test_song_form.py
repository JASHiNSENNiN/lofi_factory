"""
Tests for the generative song-form grammar (Stage 3 item 8):
generate_song_form(), an additional, more varied alternative to the 5
hand-authored _SONG_FORMS entries.
"""

from scripts.composer import (
    _FORM_GRAMMAR_MAX_TOTAL_LOOPS,
    _SONG_FORMS,
    generate_song_form,
)

_VALID_LABELS = {'I', 'A', 'BR', 'B', 'O'}


def test_returns_same_shape_as_curated_forms():
    form = generate_song_form(seed=1)
    assert isinstance(form, list)
    assert all(isinstance(item, tuple) and len(item) == 2 for item in form)
    for label, loops in form:
        assert label in _VALID_LABELS
        assert isinstance(loops, int)
        assert loops >= 1


def test_starts_with_intro_ends_with_outro():
    for seed in range(20):
        form = generate_song_form(seed=seed)
        assert form[0][0] == 'I'
        assert form[-1][0] == 'O'


def test_always_contains_at_least_one_a_and_one_b_section():
    # The grammar 'I (A (BR? B)+)+ O' guarantees this structurally -- the
    # first top-level group always fires at least once, and always includes
    # an A followed by at least one B.
    for seed in range(30):
        form = generate_song_form(seed=seed)
        labels = [l for l, _ in form]
        assert 'A' in labels
        assert 'B' in labels


def test_deterministic_with_seed():
    a = generate_song_form(seed=7)
    b = generate_song_form(seed=7)
    assert a == b


def test_varies_across_seeds():
    forms = {tuple(generate_song_form(seed=s)) for s in range(20)}
    assert len(forms) > 5   # genuinely varied, not just 1-2 shapes recurring


def test_total_loops_stays_bounded_not_degenerate():
    # No "wildly long" structure -- total loop count must stay in the same
    # order of magnitude as the curated forms (max 16) despite the grammar
    # allowing multiple (A (BR? B)+) repeats.
    curated_max = max(sum(n for _, n in form) for form in _SONG_FORMS.values())
    for seed in range(50):
        form = generate_song_form(seed=seed)
        total = sum(n for _, n in form)
        assert total <= _FORM_GRAMMAR_MAX_TOTAL_LOOPS + 4  # small outro-overshoot allowance
        assert total <= curated_max * 2   # same order of magnitude as hand-authored forms


def test_no_zero_or_negative_loop_counts():
    for seed in range(50):
        form = generate_song_form(seed=seed)
        assert all(loops >= 1 for _label, loops in form)


def test_break_sections_never_open_or_close_the_form():
    # 'BR' is only ever inserted between an A and its following B inside a
    # group -- it must never be the first or last section.
    for seed in range(50):
        form = generate_song_form(seed=seed)
        labels = [l for l, _ in form]
        assert labels[0] != 'BR'
        assert labels[-1] != 'BR'


def test_unseeded_call_does_not_raise():
    form = generate_song_form()
    assert form[0][0] == 'I' and form[-1][0] == 'O'
