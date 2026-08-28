import random

from scripts.generate_seo import (
    _TITLE_PATTERNS_BY_PILLAR,
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


# ── benefit_list replaced curiosity_gap's vlog-clickbait crutch phrases ────
def test_build_title_benefit_list_replaces_curiosity_gap_crutch_phrases():
    _FORBIDDEN = ("nobody admits", "nobody tells you", "nobody mentions",
                  "nobody warned", "nobody explains", "turns out")
    all_patterns = [
        p
        for pillar_patterns in _TITLE_PATTERNS_BY_PILLAR.values()
        for plist in pillar_patterns.values()
        for p in plist
    ]
    lowered = [p.lower() for p in all_patterns]
    for phrase in _FORBIDDEN:
        assert not any(phrase in p for p in lowered), (
            f"crutch phrase {phrase!r} still present in a title template"
        )
    assert "curiosity_gap" not in HOOK_STRATEGIES
    assert "benefit_list" in HOOK_STRATEGIES


def test_build_title_benefit_list_patterns_format_cleanly():
    random.seed(7)
    for pillar in _PILLARS:
        concept = _concept_for_pillar(pillar)
        for _ in range(8):
            title = build_title(concept, "1 hour", strategy="benefit_list")
            assert "{" not in title and "}" not in title
            assert len(title) > 0


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
def test_benefit_tail_uses_trend_ranked_signals_when_available(monkeypatch):
    import scripts.trend_research as trend_research_mod

    monkeypatch.setattr(
        trend_research_mod, "extract_title_benefit_signals",
        lambda snapshot, top_k=3: ["sleep", "unwind", "chill"],
    )
    tail = generate_seo_mod._benefit_tail(trends={"trending_titles": ["placeholder"]})
    assert tail
    assert all(word in ("sleep", "unwind", "chill") for word in tail.split(", "))


def test_benefit_tail_falls_back_to_static_vocab_without_trends():
    tail = generate_seo_mod._benefit_tail(trends=None)
    assert tail
    assert all(word in generate_seo_mod._BENEFIT_KEYWORDS for word in tail.split(", "))


# ── genre mentions extended to all 5 pillars (genre-variety bug fix) ───────
def test_genre_referencing_templates_keep_literal_seo_keyword_prefix():
    # Every template that references {genre} must ALSO carry a literal
    # "lofi"/"lo-fi"/"study music" token in the fixed (non-{genre}) part of
    # the string -- some real genre_label values (e.g. "chillhop") don't
    # contain "lofi" as a substring, so {genre} alone can't be relied on to
    # satisfy the SEO-keyword-in-first-35-chars convention.
    _SEO_KEYWORDS = ("lofi", "lo-fi", "study music")
    for pillar, strategies in _TITLE_PATTERNS_BY_PILLAR.items():
        for strategy, templates in strategies.items():
            for template in templates:
                if "{genre}" not in template:
                    continue
                fixed_text = template.replace("{genre}", "").lower()
                assert any(kw in fixed_text for kw in _SEO_KEYWORDS), (
                    f"{pillar}/{strategy} template references {{genre}} without a "
                    f"literal SEO keyword elsewhere: {template!r}"
                )


def test_all_five_pillars_have_at_least_one_genre_referencing_template_per_strategy():
    for pillar, strategies in _TITLE_PATTERNS_BY_PILLAR.items():
        for strategy, templates in strategies.items():
            assert any("{genre}" in t for t in templates), (
                f"{pillar}/{strategy} has no genre-referencing template"
            )


# ── concept_from_music_params() genre alignment (genre-variety bug fix) ────
def test_concept_from_music_params_preserves_cross_genre_pool_pick():
    base = _concept_for_pillar("cross_genre")
    base["genre_label"] = "bossa nova lofi"  # CROSS_GENRE_POOL's deliberate pick
    updated = concept_from_music_params(
        music_sub_genre="hip_hop_lofi",  # would map to "lo-fi hip hop" if applied
        music_mood="a completely different generated mood entirely",
        base_concept=base,
    )
    assert updated["genre_label"] == "bossa nova lofi"


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
    assert desc.lstrip().startswith("lo-fi hip hop")


def test_build_title_forwards_trends_into_benefit_tail(monkeypatch):
    captured = {}

    def fake_benefit_tail(trends=None):
        captured["trends"] = trends
        return "study, focus"

    monkeypatch.setattr(generate_seo_mod, "_benefit_tail", fake_benefit_tail)
    concept = _concept_for_pillar("temporal")
    sentinel_trends = {"trending_titles": ["x"]}
    build_title(concept, "1 hour", strategy="benefit_list", trends=sentinel_trends)
    assert captured["trends"] is sentinel_trends
