import random

from scripts.generate_seo import (
    _TITLE_PATTERNS_BY_PILLAR,
    _THEME_GEO_TAGS,
    HOOK_STRATEGIES,
    build_tags,
    build_title,
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


def test_build_title_strategy_param_draws_only_from_that_strategys_patterns(monkeypatch):
    # Spy on random.choice inside generate_seo to capture exactly which
    # candidate list build_title() picked from for each named strategy --
    # proves no cross-contamination between hook families (e.g. a
    # "curiosity_gap" call never secretly draws a "statement" skeleton).
    captured: list[list[str]] = []
    real_choice = random.choice

    def spy_choice(seq):
        captured.append(list(seq))
        return real_choice(seq)

    monkeypatch.setattr(generate_seo_mod.random, "choice", spy_choice)

    concept = _concept_for_pillar("aesthetic")
    for strategy in HOOK_STRATEGIES:
        captured.clear()
        build_title(concept, "1 hour", strategy=strategy)
        assert captured, "random.choice was never called"
        assert captured[-1] == _TITLE_PATTERNS_BY_PILLAR["aesthetic"][strategy]


def test_build_title_no_strategy_pools_all_families(monkeypatch):
    captured: list[list[str]] = []

    def spy_choice(seq):
        captured.append(list(seq))
        return list(seq)[0]

    monkeypatch.setattr(generate_seo_mod.random, "choice", spy_choice)

    concept = _concept_for_pillar("aesthetic")
    build_title(concept, "1 hour")  # no strategy given

    all_patterns = [
        p for plist in _TITLE_PATTERNS_BY_PILLAR["aesthetic"].values() for p in plist
    ]
    assert sorted(captured[-1]) == sorted(all_patterns)


def test_build_title_unknown_strategy_falls_back_to_pooled_families(monkeypatch):
    captured: list[list[str]] = []

    def spy_choice(seq):
        captured.append(list(seq))
        return list(seq)[0]

    monkeypatch.setattr(generate_seo_mod.random, "choice", spy_choice)

    concept = _concept_for_pillar("temporal")
    build_title(concept, "1 hour", strategy="not_a_real_strategy")

    all_patterns = [
        p for plist in _TITLE_PATTERNS_BY_PILLAR["temporal"].values() for p in plist
    ]
    assert sorted(captured[-1]) == sorted(all_patterns)


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
