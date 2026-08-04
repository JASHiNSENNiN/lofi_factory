from scripts.generate_seo import _THEME_GEO_TAGS, build_tags


def test_theme_geo_tags_only_applied_for_the_matching_theme():
    concept = {"tags_extra": ["study lofi", "chill beats"]}
    neon_tags = build_tags(concept, "2 hours", theme_name="neon_tokyo")
    other_tags = build_tags(concept, "2 hours", theme_name="cozy_rain")
    default_tags = build_tags(concept, "2 hours")

    assert any(t in neon_tags for t in _THEME_GEO_TAGS["neon_tokyo"])
    assert not any(t in other_tags for t in _THEME_GEO_TAGS["neon_tokyo"])
    assert not any(t in default_tags for t in _THEME_GEO_TAGS["neon_tokyo"])


def test_theme_geo_tags_only_defined_for_narrow_set_of_themes():
    # Deliberately narrow -- only themes with an unambiguous, already-
    # established cultural identity through their own visual aesthetic.
    assert set(_THEME_GEO_TAGS.keys()) == {"neon_tokyo", "sakura_night"}


def test_build_tags_still_respects_char_budget_with_geo_tags():
    concept = {"tags_extra": ["study lofi", "chill beats"]}
    tags = build_tags(concept, "2 hours", theme_name="neon_tokyo")
    joined_len = sum(len(t) for t in tags) + max(0, len(tags) - 1)
    assert joined_len <= 490


def test_build_tags_unknown_theme_does_not_raise():
    concept = {"tags_extra": []}
    tags = build_tags(concept, "2 hours", theme_name="not_a_real_theme")
    assert isinstance(tags, list)
