from PIL import Image

from scripts.generate_thumbnail_cozy import (
    _derive_short_title,
    _SHORT_TITLE_MAX_CHARS,
    LAYOUT_NAMES,
    _select_layout,
    _select_side,
    _check_card_legibility,
    _contrast_ratio,
    _check_brightness,
    generate_thumbnail,
)


def test_none_and_empty_title_fall_back():
    assert _derive_short_title(None) is None
    assert _derive_short_title("") is None


def test_too_short_result_falls_back():
    assert _derive_short_title("x") is None


def test_strips_leading_genre_tag_and_trailing_em_dash_duration():
    title = "lofi hip hop · the quiet hour — 3 hours"
    assert _derive_short_title(title) == "the quiet hour"


def test_strips_leading_tag_and_trailing_parenthetical_duration():
    title = "lofi hip hop · after the storm (10 minutes ago)"
    assert _derive_short_title(title) == "after the storm"


def test_never_cuts_a_clause_into_a_half_phrase():
    # Cutting "you said five more minutes" to fit gave "you said five more";
    # with no whole clause short enough, it falls back to the theme phrases.
    assert _derive_short_title("lofi hip hop · you said five more minutes — 1 hour") is None
    assert _derive_short_title("lofi · made for tired but focused nights") is None


def test_result_never_exceeds_max_chars():
    title = ("lofi hip hop · a genuinely extremely long descriptive clause "
              "that goes way past the thumbnail budget — 2 hours")
    result = _derive_short_title(title)
    assert result is None or len(result) <= _SHORT_TITLE_MAX_CHARS


def test_truncation_never_leaves_a_dangling_open_paren():
    title = "lofi hip hop · purple dusk focus (the deep work kind) — 2 hours"
    result = _derive_short_title(title)
    assert result is None or result.count("(") <= result.count(")")


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


# ── Scene silhouette selection ───────────────────────────────────────────────


# ── Scene / card collision avoidance ─────────────────────────────────────────


# ── Whole-frame brightness check ─────────────────────────────────────────────

def test_brightness_check_passes_midtone_fixture():
    img = Image.new("RGB", (200, 150), (90, 90, 100))
    ok, luma = _check_brightness(img)
    assert ok is True
    assert luma > 0


def test_brightness_check_fails_near_black_and_near_white_fixtures():
    black_ok, black_luma = _check_brightness(Image.new("RGB", (200, 150), (0, 0, 0)))
    white_ok, white_luma = _check_brightness(Image.new("RGB", (200, 150), (255, 255, 255)))
    assert black_ok is False
    assert white_ok is False
    assert black_luma < white_luma


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


# ── Room scene (scripts/thumbnail_scene.py) ──────────────────────────────────
def test_window_goes_opposite_the_title():
    from scripts.thumbnail_scene import window_side_for
    assert window_side_for("thirds", "left") == "right"
    assert window_side_for("edge", "right") == "left"
    assert window_side_for("centered", "left") == "center"


def test_room_shows_the_themes_view_through_the_window():
    import numpy as np
    from PIL import Image
    from scripts import generate_thumbnail_cozy as gtc
    from scripts.thumbnail_scene import _window_box, draw_room

    def window_mean(theme):
        img = Image.new("RGB", (gtc.TW, gtc.TH), gtc.THEMES[theme]["bg_top"])
        draw_room(img, gtc.THEMES[theme], theme, "right", np.random.default_rng(1))
        x0, y0, x1, y1 = _window_box("right", gtc.TW, gtc.TH)
        return np.asarray(img.crop((x0, y0, x1, y1)), dtype=float).mean(axis=(0, 1))

    summer, night = window_mean("summer_lofi"), window_mean("midnight_cafe")
    assert summer.mean() > night.mean() + 30          # a sunset is brighter than a night city
    snow = window_mean("winter_snow")
    assert snow[2] > snow[0]                           # snowy night reads blue


def test_room_has_no_dark_halo_rings_around_the_moon():
    import numpy as np
    from scripts import generate_thumbnail_cozy as gtc
    from scripts.thumbnail_scene import _view_layer
    layer = _view_layer("moon", gtc.THEMES["lofi_classical"], 400, 300, np.random.default_rng(2))
    assert layer.mode == "RGB"     # opaque: translucent shapes blend, never punch holes
