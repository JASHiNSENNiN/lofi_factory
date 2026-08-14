from PIL import Image

from scripts.generate_thumbnail_cozy import (
    _derive_short_title,
    _SHORT_TITLE_MAX_CHARS,
    LAYOUT_NAMES,
    _select_layout,
    _select_side,
    _check_card_legibility,
    _contrast_ratio,
    generate_thumbnail,
)


def test_none_and_empty_title_fall_back():
    assert _derive_short_title(None) is None
    assert _derive_short_title("") is None


def test_too_short_result_falls_back():
    assert _derive_short_title("x") is None


def test_strips_leading_genre_tag_and_trailing_em_dash_duration():
    title = "lofi hip hop · the deadline blinked first — 3 hours"
    assert _derive_short_title(title) == "the deadline blinked first"


def test_strips_leading_tag_and_trailing_parenthetical_duration():
    title = "lofi hip hop · you said five more minutes (10 minutes ago)"
    assert _derive_short_title(title) == "you said five more minutes"


def test_result_never_exceeds_max_chars():
    title = ("lofi hip hop · a genuinely extremely long descriptive clause "
              "that goes way past the thumbnail budget — 2 hours")
    result = _derive_short_title(title)
    assert result is not None
    assert len(result) <= _SHORT_TITLE_MAX_CHARS


def test_truncation_never_leaves_a_dangling_open_paren():
    title = "lofi hip hop · purple dusk focus (the deep work kind) — 2 hours"
    result = _derive_short_title(title)
    assert result is not None
    assert result.count("(") <= result.count(")")


def test_handles_title_with_no_genre_tag_separator():
    result = _derive_short_title("a title with no separator at all")
    assert result is None or len(result) <= _SHORT_TITLE_MAX_CHARS


# ── Layout selection ────────────────────────────────────────────────────────

def test_layout_selection_is_deterministic_for_same_inputs():
    for theme in ("cozy_rain", "neon_tokyo", "winter_snow", "vaporwave"):
        for variant in range(5):
            first  = _select_layout(theme, variant)
            second = _select_layout(theme, variant)
            assert first == second
            assert first in LAYOUT_NAMES


def test_side_selection_is_deterministic_for_same_inputs():
    for theme in ("cozy_rain", "neon_tokyo"):
        for variant in range(5):
            first  = _select_side(theme, variant)
            second = _select_side(theme, variant)
            assert first == second
            assert first in ("left", "right")


def test_layout_selection_varies_across_variants():
    # Across a reasonable sample of variants for a fixed theme, more than
    # one distinct layout should be selected (real variety, not one layout
    # dominating every draw).
    seen = {_select_layout("cozy_rain", v) for v in range(12)}
    assert len(seen) > 1


def test_layout_selection_varies_across_themes():
    # Different theme names (same variant) should not all collapse onto the
    # same layout either.
    themes = list(
        __import__("scripts.generate_thumbnail_cozy", fromlist=["THEMES"]).THEMES
    )
    seen = {_select_layout(t, 0) for t in themes}
    assert len(seen) > 1


def test_ab_variant_pair_always_uses_different_layouts():
    # run.py generates the primary thumbnail with `thumb_variant` and the
    # `_alt` A/B candidate with `thumb_variant + 1`. Those two calls must
    # land on genuinely different compositions, not just different noise.
    for theme in ("cozy_rain", "neon_tokyo", "winter_snow", "sakura_night"):
        for variant in range(0, 50):
            assert _select_layout(theme, variant) != _select_layout(theme, variant + 1)


# ── Small-size legibility check ──────────────────────────────────────────────

def test_legibility_check_passes_high_contrast_fixture():
    # Dark card background, light/warm text color -- easily readable.
    img = Image.new("RGB", (400, 300), (10, 10, 14))
    ok, ratio = _check_card_legibility(img, (40, 40, 360, 260), (240, 230, 210))
    assert ok is True
    assert ratio >= 3.0


def test_legibility_check_fails_low_contrast_fixture():
    # Card background nearly identical to the nominal text color -- text
    # would wash out into the card, especially once downsampled.
    img = Image.new("RGB", (400, 300), (235, 225, 205))
    ok, ratio = _check_card_legibility(img, (40, 40, 360, 260), (240, 230, 210))
    assert ok is False
    assert ratio < 3.0


def test_contrast_ratio_is_symmetric_and_bounded():
    ratio_a = _contrast_ratio((255, 255, 255), (0, 0, 0))
    ratio_b = _contrast_ratio((0, 0, 0), (255, 255, 255))
    assert ratio_a == ratio_b
    assert ratio_a > 20   # black/white is WCAG-max ~21
    assert _contrast_ratio((100, 100, 100), (100, 100, 100)) == 1.0


# ── End-to-end: A/B variant pair renders genuinely different compositions ──

def test_generate_thumbnail_ab_pair_uses_different_layouts(tmp_path, monkeypatch):
    import scripts.generate_thumbnail_cozy as gtc

    monkeypatch.setattr(gtc, "ASSETS_DIR", str(tmp_path))

    title = "lofi hip hop · a quiet study night with soft piano — 2 hours"
    variant = 4  # arbitrary, matches run.py's `thumb_variant` usage

    primary_path, _ = generate_thumbnail(
        theme_name="cozy_rain", duration="2 hours", title=title, variant=variant
    )
    alt_path, _ = generate_thumbnail(
        theme_name="cozy_rain", duration="2 hours", title=title, variant=variant + 1
    )

    assert primary_path != alt_path
    assert gtc._select_layout("cozy_rain", variant) != gtc._select_layout("cozy_rain", variant + 1)
    # Both renders should succeed and produce real image files.
    for p in (primary_path, alt_path):
        with Image.open(p) as img:
            assert img.size == (gtc.TW, gtc.TH)
