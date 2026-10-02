"""Each genre keeps the things that define it: its own drum groove, bass,
instruments and tempo. Values follow research/genres.md."""
import contextlib
import io
import random

import pytest

with contextlib.redirect_stdout(io.StringIO()):
    from scripts import composer as g
from scripts import drum_sampler as ds
from scripts import gm_instruments as gm


def _params(genre, seed):
    random.seed(seed)
    with contextlib.redirect_stdout(io.StringIO()):
        return g.pick_params(genre_hint=genre)


@pytest.mark.parametrize("genre", sorted(set(g._SUBGENRE_CONFIG) - g._GENERATED_DRUM_GENRES))
def test_curated_genres_never_get_generic_generated_drums(genre):
    for seed in range(12):
        p = _params(genre, seed)
        assert p.get("drum_pattern_a_source") in (None, "polyrhythm")
        assert p.get("drum_pattern_b_source") in (None, "polyrhythm")


def test_house_is_four_on_the_floor():
    for idx in g._SUBGENRE_CONFIG["lofi_house"]["drum_pats"]:
        kick = g.DRUM_PATTERNS[idx][g.KICK]
        assert all(kick[s] for s in (0, 4, 8, 12))


def test_bossa_plays_a_two_bar_clave_with_no_backbeat():
    pat = g.DRUM_PATTERNS[g._SUBGENRE_CONFIG["bossa_lofi"]["drum_pats"][0]]
    assert len(pat[g.RIM]) == 32
    hits = [i for i, v in enumerate(pat[g.RIM]) if v]
    assert hits == [0, 6, 12, 16 + 4, 16 + 10]          # 3-2 bossa clave
    assert not any(pat.get(g.SNARE, [0]))


def test_two_bar_patterns_alternate_bars():
    pat = g.DRUM_PATTERNS[18]
    ev = g.build_drums(pat, 0, 2, 0.5, 80, allow_generated=False)
    bar = 16 * g.S16
    rims = sorted(t for t, n, _v, _d in ev if n == g.RIM)
    assert any(t < bar for t in rims) and any(t >= bar for t in rims)
    first, second = [t % bar // g.S16 for t in rims if t < bar], [t % bar // g.S16 for t in rims if t >= bar]
    assert first != second


def test_phonk_has_a_real_cowbell_and_808_glide():
    assert any(g.COWBELL in g.DRUM_PATTERNS[i] for i in g._SUBGENRE_CONFIG["lofi_phonk"]["drum_pats"])
    assert "lofi_phonk" in g._GLIDE_808_GENRES
    assert g._BASS_PROGRAMS["lofi_phonk"] == gm.GM_SYNTH_BASS_2


@pytest.mark.parametrize("genre,program", [
    ("piano_lofi", gm.GM_ACOUSTIC_GRAND), ("lofi_synthwave", gm.GM_POLYSYNTH_PAD),
    ("bossa_lofi", gm.GM_GUITAR_NYLON), ("neo_soul", gm.GM_RHODES),
])
def test_genre_lead_instruments(genre, program):
    assert g._SUBGENRE_CONFIG[genre]["piano"] == program


@pytest.mark.parametrize("genre,bass", [
    ("lofi_jazz", gm.GM_ACOUSTIC_BASS), ("bossa_lofi", gm.GM_ACOUSTIC_BASS),
    ("city_pop", gm.GM_SLAP_BASS), ("lofi_house", gm.GM_SYNTH_BASS_1),
    ("neo_soul", gm.GM_FINGER_BASS),
])
def test_genre_bass(genre, bass):
    assert g._BASS_PROGRAMS[genre] == bass


def test_jazz_walks_and_ambient_is_beatless():
    assert _params("lofi_jazz", 1)["bass_walking"] is True
    assert "ambient" in g._BEATLESS_GENRES


def test_sample_layer_doubles_the_midi_pattern():
    midi = g.DRUM_PATTERNS[17]                    # house
    pat = ds.pattern_from_midi(midi)
    assert [i for i, v in enumerate(pat["k"]) if v] == [0, 4, 8, 12]
    assert [i for i, v in enumerate(pat["s"]) if v] == [4, 12]      # clap counts as snare
    trip = ds.pattern_from_midi(midi, chh_triplet=True)
    assert not any(trip["h"])


def test_span_labels_follow_the_form():
    form = [('I', 1), ('A', 2), ('BR', 1), ('B', 2), ('A', 1), ('O', 1)]
    assert g.full_beat_span_labels(form) == ['A', 'B']        # B and the last A are adjacent
    assert len(g.full_beat_spans(form, 4, 80)) == 2


def test_tempos_spread_over_the_range_not_piled_on_its_ends():
    import collections
    c = collections.Counter(_params("lofi_jazz", s)["bpm"] for s in range(120))
    lo, hi = g._SUBGENRE_CONFIG["lofi_jazz"]["bpm"]
    assert (c[lo] + c[hi]) / 120 < 0.2      # was ~45%
    assert all(lo <= b <= hi for b in c)


def test_every_genre_is_published_under_its_own_name():
    from scripts.generate_seo import _SUBGENRE_TO_GENRE_LABEL as labels
    assert set(g._SUBGENRE_CONFIG) <= set(labels)
    assert labels["lofi_house"] == "lofi house"
    assert labels["lofi_phonk"] == "lofi phonk"
    assert "jazz" not in labels["piano_lofi"] and "jazz" not in labels["anime_lofi"]
