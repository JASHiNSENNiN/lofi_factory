from PIL import Image

from scripts.generate_thumbnail_cozy import (
    _derive_short_title,
    _SHORT_TITLE_MAX_CHARS,
    LAYOUT_NAMES,
    _select_layout,
    _select_side,
    _check_card_legibility,
    _contrast_ratio,
    SCENE_POOL,
    _select_scene,
    _scene_slot,
    _check_scene_card_collision,
    _draw_scene_silhouette,
    _card_geometry,
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

def test_scene_selection_is_deterministic_for_same_inputs():
    for theme in ("cozy_rain", "neon_tokyo", "winter_snow", "vaporwave"):
        for variant in range(5):
            first  = _select_scene(theme, variant)
            second = _select_scene(theme, variant)
            assert first == second
            assert first in SCENE_POOL.get(theme, ())


def test_scene_selection_varies_across_variants():
    seen = {_select_scene("cozy_rain", v) for v in range(12)}
    assert len(seen) > 1


def test_ab_variant_pair_can_use_different_scenes():
    # Not a hard guarantee like layout (scene pools are only 3 wide and
    # variant deltas of 1 can land on the same index), but across a spread
    # of themes/variants the A/B pair should show real variety somewhere.
    diffs = sum(
        1
        for theme in SCENE_POOL
        for variant in range(0, 6)
        if _select_scene(theme, variant) != _select_scene(theme, variant + 1)
    )
    assert diffs > 0


# ── Scene / card collision avoidance ─────────────────────────────────────────

def test_check_scene_card_collision_detects_overlap():
    card = (500, 500, 800, 600)
    assert _check_scene_card_collision((600, 520, 700, 580), card) is True
    assert _check_scene_card_collision((0, 0, 100, 100), card) is False
    assert _check_scene_card_collision(None, card) is False


def test_draw_scene_silhouette_never_overlaps_the_real_card_geometry():
    # Exercises the actual runtime path: compute the real card bbox via
    # `_card_geometry` (what `generate_thumbnail` does before drawing the
    # scene), then confirm whatever `_draw_scene_silhouette` returns -- a
    # bbox, or None if it chose to skip -- never overlaps that card.
    import numpy as np
    from PIL import ImageDraw
    from scripts.generate_thumbnail_cozy import TW, TH

    titles = ["a genuinely long night of study and soft rain on the window",
              "short one", "the deadline blinked first and then blinked again"]
    for theme in list(SCENE_POOL)[:8]:
        for variant in range(4):
            layout = _select_layout(theme, variant)
            side   = _select_side(theme, variant)
            title  = titles[variant % len(titles)]
            img  = Image.new("RGB", (TW, TH), (0, 0, 0))
            draw = ImageDraw.Draw(img, "RGBA")
            geom = _card_geometry(draw, theme, title, "2 hours", layout, side)
            card_bbox = (geom["card_x"], geom["card_y"],
                         geom["card_x"] + geom["card_w"], geom["card_y"] + geom["card_h"])
            rng = np.random.default_rng(0)
            _, scene_bbox = _draw_scene_silhouette(
                img, theme, layout, side, variant, rng, avoid_bbox=card_bbox,
            )
            assert not _check_scene_card_collision(scene_bbox, card_bbox)


def test_scene_slot_sits_on_the_side_opposite_the_card():
    # thirds/edge layouts place the card on `side`; the scene slot should be
    # on the opposite horizontal half of the frame.
    from scripts.generate_thumbnail_cozy import TW
    for layout in ("thirds", "edge"):
        cx_left, *_ = _scene_slot(layout, "left")
        cx_right, *_ = _scene_slot(layout, "right")
        assert cx_left > TW / 2   # card on the left -> scene on the right
        assert cx_right < TW / 2  # card on the right -> scene on the left


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
