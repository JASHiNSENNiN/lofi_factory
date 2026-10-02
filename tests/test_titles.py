"""Titles: short, scene-first, keyword early, grammatical, seasonal, and
trend-aware without ever saying something the video isn't."""
import random
import re

import pytest

from scripts import titles

_THEMES = sorted(titles.SCENES)


@pytest.mark.parametrize("strategy", titles.STRATEGIES)
def test_titles_fit_mobile_and_lead_with_the_scene_or_genre(strategy):
    rng = random.Random(1)
    for theme in _THEMES:
        for genre in ("lo-fi hip hop", "chillhop", "bossa nova lofi"):
            title, thumb = titles.build(strategy, theme=theme, genre=genre, activity="reading",
                                        duration="1 hour", rng=rng, month=10)
            assert 25 <= len(title) <= 62, title
            g = "lofi hip hop" if genre == "lo-fi hip hop" else genre
            assert g in title
            assert title.index(g) < 40          # the searched keyword early
            assert len(thumb.split()) <= 4
            assert titles.EMOJI[theme] in title


def test_scene_phrases_are_short_lowercase_and_unique():
    allp = [p for ps in titles.SCENES.values() for p in ps]
    assert len(allp) == len(set(allp))
    for p in allp:
        assert p == p.lower() and len(p.split()) <= 4
        assert not re.search(r"\b(a|an|the) (a|an|the)\b", p)


def test_seasonal_scenes_only_in_season():
    rng = random.Random(3)
    october = {titles.pick_scene("winter_snow", month=10, rng=rng) for _ in range(40)}
    assert "first snow of winter" not in october
    january = {titles.pick_scene("winter_snow", month=1, rng=rng) for _ in range(60)}
    assert "first snow of winter" in january
    # a spring theme in autumn falls back to a daytime phrase, never "late night"
    assert "night" not in titles.pick_scene("spring_dawn", month=10, rng=rng)


def test_trends_reweight_but_never_add_words():
    trends = {"trending_titles": ["cozy rain lofi to study to", "rain sounds lofi"] * 5}
    rng = random.Random(4)
    picks = [titles.pick_scene("cozy_rain", trends, month=10, rng=rng) for _ in range(300)]
    rainy = sum("rain" in p for p in picks) / len(picks)
    assert rainy > 0.8                           # 4 of 5 phrases mention rain; boosted
    assert set(picks) <= set(titles.SCENES["cozy_rain"])


def test_moment_titles_only_use_activities_that_read_well():
    title, _ = titles.build("moment", theme="cozy_rain", genre="lofi jazz",
                            activity="first week of classes", duration="1 hour",
                            rng=random.Random(5), month=10)
    assert title.startswith("studying ")


def test_generate_seo_gives_the_thumbnail_the_titles_scene(tmp_path, monkeypatch):
    import io
    import contextlib
    from scripts import generate_seo as g
    monkeypatch.setattr(g, "ASSETS_DIR", str(tmp_path))
    random.seed(7)
    with contextlib.redirect_stdout(io.StringIO()):
        seo, _ = g.generate_seo(theme_name="cozy_rain", duration="1 hour")
    assert seo["thumb_text"]
    assert seo["thumb_text"] in seo["title"] or seo["title"].startswith("lofi") \
        or seo["title"].split(" ")[0] in ("chillhop", "lofi")


def test_radio_form_names_what_the_music_is_for():
    import random
    from scripts import titles
    rng = random.Random(0)
    sleep, _ = titles.build("radio", theme="blue_hour", genre="sleep lofi",
                            activity="studying", duration="1 hour", rng=rng)
    ambient, _ = titles.build("radio", theme="blue_hour", genre="ambient lofi",
                              activity="studying", duration="1 hour", rng=rng)
    assert "study" not in sleep and "sleep" in sleep
    assert "beats" not in ambient


def test_scene_phrases_fit_the_thumbnail_and_moment_text_falls_back():
    import random
    from scripts import titles
    assert max(len(p) for ps in titles.SCENES.values() for p in ps) <= titles.THUMB_MAX_CHARS
    _, thumb = titles.build("moment", theme="cozy_rain", genre="lofi jazz",
                            activity="interview prep", duration="1 hour", rng=random.Random(3))
    assert len(thumb) <= titles.THUMB_MAX_CHARS


def test_theme_fits_the_genre_and_the_season():
    import random
    from scripts import titles
    rng = random.Random(0)
    for _ in range(50):
        assert titles.theme_for_genre("sleep_lofi", month=7, rng=rng) in ("blue_hour", "forest_rain")
        assert titles.theme_for_genre("hip_hop_lofi", month=7, rng=rng) not in ("winter_snow", "sakura_night")
        assert titles.theme_for_genre("anime_lofi", month=10, rng=rng) != "sakura_night"


def test_published_titles_are_not_reused():
    from scripts.generate_seo import generate_title_variants
    concept = {"theme": "cozy_rain", "genre_label": "lofi jazz", "activity": "studying"}
    first, _ = generate_title_variants(concept, "1 hour", n=3, taken=set())
    again, _ = generate_title_variants(concept, "1 hour", n=3, taken=set(first))
    assert again and not set(again) & set(first)


def test_each_title_is_credited_to_the_form_that_built_it():
    from scripts.generate_seo import generate_title_variants
    concept = {"theme": "cozy_rain", "genre_label": "lofi jazz", "activity": "studying"}
    titles_, forms = generate_title_variants(concept, "1 hour", n=3, taken=set())
    for t, form in zip(titles_, forms):
        assert ("beats to" in t) == (form == "radio")


def test_description_never_contradicts_the_pictures_time_of_day():
    import random
    from scripts.generate_seo import build_description
    random.seed(0)
    concept = {"pillar": "aesthetic", "theme": "neon_tokyo", "genre_label": "city pop lofi",
               "activity": "coding", "time_label": "sunday morning",
               "mood_line": "wildflowers and afternoon light through curtains"}
    for _ in range(30):
        d = build_description(concept, "1 hour", scene="neon city at 2am").lower()
        assert "afternoon" not in d and "morning" not in d
        assert "neon city at 2am" in d


def test_track_names_are_grammatical_song_titles():
    import random
    import re
    from scripts import composer
    random.seed(7)
    names = [composer._compose_mood_phrase(s) for s in ("sleep_lofi", "lofi_jazz", "city_pop", "")
             for _ in range(200)]
    for n in names:
        low = n.lower()
        assert not re.search(r"\b(a|the) (a|the)\b", low), n            # "the a rainy..."
        assert not re.search(r"^\w+ (a|the) ", low) or low.split()[0] in (
            "the", "until", "still") or " the " in low or low.split()[1] in ("on", "in", "at", "by", "down", "of", "and"), n
        words = [w for w in low.split() if w not in composer._SMALL_WORDS]
        assert len(set(words)) == len(words), n
        assert n[0].isupper()
    # A whole video concept never becomes a track name; a short --mood does.
    assert composer._pick_mood_phrase("cottagecore · wildflowers, afternoon light") != \
        "cottagecore · wildflowers, afternoon light"
    assert composer._pick_mood_phrase("rainy jazz") == "Rainy Jazz"
