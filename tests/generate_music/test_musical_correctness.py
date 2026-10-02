"""Regression tests for musical errors found in the audit: wrong chord
voicings, V chords spelled as major 7ths, melody/chord key mismatches,
semitone clashes, near-silent melodies, over-long tracks, the intro bass
running a chord behind, and the drum break playing over every section."""
import io
import contextlib
import random
import re

import numpy as np
import pytest
import soundfile as sf

from scripts import composer as g
from scripts import drum_sampler

_ROOTS = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'Eb': 3, 'E': 4, 'F': 5, 'F#': 6,
          'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'Bb': 10, 'B': 11}
# Chord tones plus idiomatic tensions per chord quality.
_ALLOWED = {
    'maj7': {0, 4, 7, 11, 2, 9}, 'maj9': {0, 4, 7, 11, 2, 9}, 'maj7s': {0, 4, 7, 11, 2, 6},
    'maj6': {0, 4, 7, 9, 2}, 'm7': {0, 3, 7, 10, 2, 5}, 'm9': {0, 3, 7, 10, 2, 5},
    'm11': {0, 3, 7, 10, 2, 5}, 'm6': {0, 3, 7, 9, 2}, 'madd9': {0, 3, 7, 2},
    'm7b5': {0, 3, 6, 10, 5, 8}, 'msus4': {0, 5, 7, 10, 2},
    '7': {0, 4, 7, 10, 2, 9}, '9': {0, 4, 7, 10, 2, 9}, '13': {0, 4, 7, 10, 2, 9},
    '7b9': {0, 4, 7, 10, 1, 8}, '7alt': {0, 4, 10, 1, 3, 6, 8},
}


def _quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


@pytest.mark.parametrize("name", sorted(g.VOICING_OPTIONS))
def test_every_voicing_matches_its_chord_symbol(name):
    m = re.match(r'^([A-G][#b]?)(.*)$', name)
    root, quality = _ROOTS[m.group(1)], m.group(2)
    allowed = _ALLOWED[quality]
    for voicing in g.VOICING_OPTIONS[name]:
        foreign = {(n - root) % 12 for n in voicing} - allowed
        assert not foreign, f"{name} voicing {voicing} has foreign intervals {foreign}"


def test_no_dominant_chord_spelled_as_major_seventh_in_c_major():
    # In C major the V chord is G7/G13, never Gmaj7 (its F# is outside the key).
    for prog, key in zip(g.PROGRESSIONS, g.PROGRESSION_KEY):
        if key == 'C':
            assert 'Gmaj7' not in [c for c, _ in prog], prog


def test_progression_fits_key():
    assert g.progression_fits_key([('Cmaj9', 2), ('Am9', 2), ('Fmaj9', 2), ('G13', 2)], 'C')
    assert not g.progression_fits_key([('Ebmaj7', 2), ('Bbmaj7', 2), ('Abmaj7', 2)], 'C')


def test_all_tracks_of_a_video_share_genre_and_key_follows_progression():
    random.seed(3)
    sets = _quiet(g._build_diverse_params, 6)
    assert len({p['sub_genre'] for p in sets}) == 1
    for p in sets:
        assert p['key'] == g.PROGRESSION_KEY[p['progression']]


def test_each_track_gets_its_own_title_and_the_first_keeps_the_concept():
    random.seed(5)
    sets = _quiet(g._build_diverse_params, 6, concept_hint='rain on the window')
    moods = [p['mood'] for p in sets]
    assert moods[0] == 'rain on the window'
    assert len(set(moods)) == len(moods)


def test_genre_hint_applies_to_every_track():
    random.seed(4)
    sets = _quiet(g._build_diverse_params, 4, genre_hint='jazz_cafe')
    assert {p['sub_genre'] for p in sets} == {'jazz_cafe'}


def test_fix_melodic_clashes_moves_minor_ninth_onto_chord_tone():
    piano = [(0, 60, 80, 1920), (0, 64, 80, 1920), (0, 67, 80, 1920)]   # C major
    mel = [(0, 73, 80, 480),     # C#: a semitone above C -> clash
           (480, 74, 80, 480),   # D: a ninth, fine
           (960, 61, 80, 60)]    # short C#: passing note, left alone
    fixed, n = g.fix_melodic_clashes(mel, piano)
    assert n == 1
    assert [e[1] for e in fixed] == [72, 74, 61]


def test_fit_form_length_keeps_tracks_between_two_and_four_minutes():
    for bpm in (58, 70, 85, 110):
        for prog_bars in (4, 8, 16):
            for form in g._SONG_FORMS.values():
                fitted = g.fit_form_length(form, prog_bars, bpm)
                secs = g.form_seconds(fitted, prog_bars, bpm)
                loop = prog_bars * 240.0 / bpm
                assert secs <= g.TRACK_MAX_SECS or all(
                    n == 1 for label, n in fitted if label in ('A', 'B', 'BR'))
                assert secs >= g.TRACK_MIN_SECS - loop
                assert [lbl for lbl, _ in fitted] == [lbl for lbl, _ in form]


def test_melody_plays_in_most_main_section_bars():
    random.seed(9)
    prog = [('Am7', 2), ('Fmaj7', 2), ('Cmaj7', 2), ('G7', 2)]
    root = g.KEY_ROOTS['Am']
    ev = g.build_melody(root, 0, 32, 0.6, 80, 'medium', 'pent', progression=prog, prog_bars=8)
    bars_with_notes = {e[0] // g.BAR for e in ev}
    # It used to advance by the phrase's note count in bars: ~1 phrase per 8 bars.
    assert len(bars_with_notes) >= 16


def test_intro_bass_stays_in_sync_with_the_chords():
    prog = [('Fmaj9', 2), ('G13', 2), ('Em7', 2), ('Am9', 2)]
    random.seed(1)
    full = g.build_bass(prog, 0, 1, 0.6, 80)
    # Same filter build_midi uses for the intro: enter at bar 2, stay in section.
    intro = [e for e in full if 2 * g.BAR - g.S16 <= e[0] < 8 * g.BAR]
    for t, note, _v, _d in intro:
        bar = t // g.BAR
        chord = prog[min(3, bar // 2)][0]
        if t % g.BAR < g.S16:   # beat-1 hits are roots
            assert note == g.BASS_ROOTS[chord]


def test_full_beat_spans_cover_only_a_and_b_sections():
    form = [('I', 1), ('A', 2), ('BR', 1), ('B', 2), ('O', 1)]
    spans = g.full_beat_spans(form, 8, 80, sr=1000)
    bar = 240.0 / 80 * 1000
    assert spans == [(int(8 * bar), int(24 * bar)), (int(32 * bar), int(48 * bar))]


def test_drum_break_is_silent_outside_spans(tmp_path):
    sr = drum_sampler.SR
    n = sr * 8
    base = np.zeros((n, 2), dtype=np.float32) + 0.01
    src = tmp_path / "base.wav"
    sf.write(src, base, sr)
    out = tmp_path / "out.wav"
    drum_sampler.layer_drum_break(str(src), str(out), bpm=90, spans=[(sr * 4, n)])
    mixed, _ = sf.read(out, dtype="float32")
    head = mixed[: sr * 4 - sr // 10]
    assert np.max(np.abs(head - head.mean())) < 1e-3          # only the flat base
    assert np.max(np.abs(mixed[sr * 5:])) > 0.02              # drums in the span
    assert np.max(np.abs(mixed)) <= 10 ** (-1.5 / 20) + 1e-3  # true-peak headroom
