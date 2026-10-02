import random

from scripts.generate_seo import (
    _THEME_GEO_TAGS,
    HOOK_STRATEGIES,
    build_description,
    build_tags,
    build_title,
    concept_from_music_params,
    generate_title_variants,
    pick_concept_from_pool,
)
import scripts.generate_seo as generate_seo_mod

_PILLARS = ["temporal", "activity", "emotional", "aesthetic", "cross_genre"]


def _concept_for_pillar(pillar: str) -> dict:
    """A fully-populated concept dict for a given pillar -- enough fields
    that every hook-strategy template for every pillar can .format() cleanly
    (temporal/activity/emotional/aesthetic/cross_genre patterns pull from
    different subsets of these same keys)."""
    return {
        "pillar":      pillar,
        "city":        None,
        "setting":     "a quiet room",
        "time_label":  "3am",
        "mood_line":   "productively sad",
        "activity":    "coding",
        "genre_label": "lofi jazz",
        "aesthetic":   "dark academia",
        "tags_extra":  [],
    }


# ── hook-strategy variety -- the core thing that was broken ────────────────
# Previously generate_title_variants() called build_title() 3x on the same
# concept, drawing from ONE flat pool of skeletons per pillar -- 3 superficial
# re-renderings of the same idea, not 3 distinct creative hooks. These tests
# would have failed against that old implementation (all 3 strategies would
# have come back identical / from the same family).
def test_generate_title_variants_uses_a_distinct_hook_strategy_per_slot():
    random.seed(0)
    for pillar in _PILLARS:
        concept = _concept_for_pillar(pillar)
        titles, strategies = generate_title_variants(concept, "2 hours", n=3)
        assert len(titles) == 3
        assert len(strategies) == 3
        # The old bug: 3 rolls of the same skeleton family. Now must be 3
        # genuinely different hook-strategy families.
        assert len(set(strategies)) == 3
        assert set(strategies) == set(HOOK_STRATEGIES)


def test_generate_title_variants_titles_are_distinct_strings():
    random.seed(1)
    concept = _concept_for_pillar("emotional")
    titles, _strategies = generate_title_variants(concept, "2 hours", n=3)
    assert len(set(titles)) == len(titles) == 3


# ── pool-based generation still produces valid, fully-formatted titles ─────
def test_build_title_no_leftover_placeholders_across_pillars_and_strategies():
    random.seed(5)
    for pillar in _PILLARS:
        concept = _concept_for_pillar(pillar)
        for strategy in list(HOOK_STRATEGIES) + [None]:
            for _ in range(8):
                title = build_title(concept, "3 hours", strategy=strategy)
                assert "{" not in title and "}" not in title
                assert isinstance(title, str) and len(title) > 0


def test_pool_concepts_generate_valid_title_variants_across_pillars():
    random.seed(6)
    for _ in range(20):
        concept = pick_concept_from_pool()
        titles, strategies = generate_title_variants(concept, "2 hours", n=3)
        assert len(titles) == 3
        for t in titles:
            assert "{" not in t and "}" not in t
            assert len(t) > 0
        assert len(set(strategies)) == len(strategies)


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


# ── benefit_list replaced curiosity_gap's vlog-clickbait crutch phrases ────


# ── length-target enforcement (Phase 1) ─────────────────────────────────────
def test_generate_title_variants_prefers_length_target_range(monkeypatch):
    # First candidate returned for a slot is deliberately out of the
    # [_TITLE_TARGET_MIN, _TITLE_TARGET_MAX] range; the second is in range
    # and must be preferred over the first once it's seen.
    too_long = "x" * 90
    in_range = "y" * 55  # deliberately unrealistic -- this test is about the
                         # length-preference mechanism, not title content
    assert generate_seo_mod._TITLE_TARGET_MIN <= len(in_range) <= generate_seo_mod._TITLE_TARGET_MAX
    assert not (generate_seo_mod._TITLE_TARGET_MIN <= len(too_long) <= generate_seo_mod._TITLE_TARGET_MAX)

    calls = {"n": 0}
    canned = [too_long, in_range]

    def fake_build_title(concept, duration, strategy=None, trends=None):
        idx = min(calls["n"], len(canned) - 1)
        calls["n"] += 1
        return canned[idx]

    monkeypatch.setattr(generate_seo_mod, "build_title", fake_build_title)
    concept = _concept_for_pillar("temporal")
    titles, _strategies = generate_title_variants(concept, "1 hour", n=1)
    assert titles[0] == in_range


def test_generate_title_variants_falls_back_when_nothing_lands_in_range(monkeypatch):
    # Every candidate is out of range -- must still return the first valid
    # dedup rather than dropping the slot.
    too_long = "x" * 90

    monkeypatch.setattr(
        generate_seo_mod, "build_title",
        lambda concept, duration, strategy=None, trends=None: too_long,
    )
    concept = _concept_for_pillar("temporal")
    titles, strategies = generate_title_variants(concept, "1 hour", n=1)
    assert titles == [too_long]
    assert len(strategies) == 1


# ── trend-aware {benefits} fill (Phase 2) ───────────────────────────────────


# ── genre mentions extended to all 5 pillars (genre-variety bug fix) ───────


# ── concept_from_music_params() genre alignment (genre-variety bug fix) ────
def test_concept_from_music_params_keeps_cross_genre_wording_when_the_music_matches():
    base = _concept_for_pillar("cross_genre")
    base["genre_label"] = "lofi ambient"      # the pool's wording of `ambient`
    updated = concept_from_music_params(music_sub_genre="ambient", music_mood="",
                                        base_concept=base)
    assert updated["genre_label"] == "lofi ambient"


def test_concept_from_music_params_never_names_a_genre_that_doesnt_play():
    base = _concept_for_pillar("cross_genre")
    base["genre_label"] = "bossa nova lofi"
    updated = concept_from_music_params(music_sub_genre="hip_hop_lofi",
                                        music_mood="", base_concept=base)
    assert updated["genre_label"] == "lo-fi hip hop"


def test_every_cross_genre_pick_reaches_the_music_generator():
    from scripts.composer import _resolve_genre_hint
    from scripts.generate_seo import CROSS_GENRE_POOL
    for label, *_ in CROSS_GENRE_POOL:
        assert _resolve_genre_hint(label), label


def test_concept_from_music_params_still_aligns_other_pillars():
    base = _concept_for_pillar("temporal")
    base["genre_label"] = "lo-fi hip hop"  # the generic pre-generation default
    updated = concept_from_music_params(
        music_sub_genre="lofi_jazz",
        music_mood="",
        base_concept=base,
    )
    assert updated["genre_label"] == "lofi jazz"


def test_concept_from_music_params_unknown_subgenre_leaves_genre_untouched():
    base = _concept_for_pillar("activity")
    base["genre_label"] = "lo-fi hip hop"
    updated = concept_from_music_params(
        music_sub_genre="not_a_real_subgenre",
        music_mood="",
        base_concept=base,
    )
    assert updated["genre_label"] == "lo-fi hip hop"


# ── build_description() genre string (genre-variety bug fix) ───────────────
def test_build_description_reflects_actual_genre_label():
    concept = _concept_for_pillar("aesthetic")
    concept["genre_label"] = "dark lofi"
    desc = build_description(concept, "1 hour")
    assert "dark lofi" in desc
    assert not desc.lstrip().startswith("lo-fi hip hop")


def test_build_description_still_shows_default_when_genre_is_generic():
    concept = _concept_for_pillar("temporal")
    concept["genre_label"] = "lo-fi hip hop"
    desc = build_description(concept, "1 hour")
    assert desc.startswith("1 hour of lo-fi hip hop beats")




def test_corrected_cross_genre_concept_drops_the_old_genres_words():
    base = _concept_for_pillar("cross_genre")
    base.update(genre_label="lofi ambient", mood_line="texture more than melody.",
                tags_extra=["ambient lofi", "atmospheric lofi"])
    updated = concept_from_music_params(music_sub_genre="lofi_house", music_mood="",
                                        base_concept=base)
    assert updated["genre_label"] == "lofi house"
    assert not updated["mood_line"] and not updated["tags_extra"]


def test_sleep_and_ambient_videos_are_not_sold_as_study_beats():
    import random
    from scripts import generate_seo as g
    random.seed(3)
    for genre in ("sleep lofi", "ambient lofi"):
        concept = {"pillar": "activity", "genre_label": genre, "activity": "coding",
                   "mood_line": "", "tags_extra": ["coding lofi"], "theme": "blue_hour"}
        desc = g.build_description({**concept, "activity": "winding down"}, "1 hour", "the blue hour")
        assert "studying" not in desc.split("\n")[0] and "#studymusic" not in desc
        tags = g.build_tags(concept, "1 hour")
        assert f"{genre} beats" not in tags


def test_sentences_start_with_capitals():
    from scripts.generate_seo import _sentence
    assert _sentence("functional. mostly functional. fine") == "Functional. Mostly functional. Fine."


def test_ambiguous_genre_hints_are_not_resolved_arbitrarily():
    from scripts.composer import _resolve_genre_hint
    assert _resolve_genre_hint("lofi") is None          # was anime_lofi
    assert _resolve_genre_hint("jazz") is None          # two jazz genres
    assert _resolve_genre_hint("house") == "lofi_house"
    assert _resolve_genre_hint("jazz hop") == "nujabes"  # a published label
