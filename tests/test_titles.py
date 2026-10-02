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
