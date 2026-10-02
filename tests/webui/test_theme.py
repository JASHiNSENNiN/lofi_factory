"""
Regression tests for webui/theme.py's pure-logic design-token helpers.

Covers the graduated color-scale generator (the Radix-ui/colors *methodology*
adaptation -- see theme.py's module docstring) and the structural helpers
behind theme.card() / theme.data_row(), which app.py now routes every card
and pseudo-table row through instead of hand-rolling divergent
`ui.element("div").classes("studio-card ...")` / `ui.row().style("min-width:...")`
one-offs. These test the plain-Python logic split out of the NiceGUI-element-
creating functions (no live NiceGUI client/page context needed), matching the
existing convention in test_helpers.py.
"""
from __future__ import annotations

import pytest

from webui import theme


# ── generate_scale() ─────────────────────────────────────────────────────────
def test_generate_scale_has_12_steps():
    scale = theme.generate_scale("#e8a45c")
    assert set(scale.keys()) == set(range(1, 13))


def test_generate_scale_step9_is_the_exact_base_hex():
    scale = theme.generate_scale("#E8A45C")
    assert scale[9] == "#e8a45c"


def test_generate_scale_all_steps_are_valid_hex():
    scale = theme.generate_scale(theme.SECONDARY)
    for hexv in scale.values():
        assert hexv.startswith("#")
        assert len(hexv) == 7
        int(hexv[1:], 16)  # raises ValueError if not valid hex


def _luminance(hex_color: str) -> float:
    """Standard (IEC 61966-2-1) relative-luminance calc, used only to sanity-
    check the generated scale's lightness ordering in this test file."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = lin(r), lin(g), lin(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_generate_scale_low_steps_are_darker_than_high_steps():
    # Dark-theme curve: step 1 (near-bg tint) must be darker than step 12
    # (high-contrast text) for every base hue -- otherwise the "text" end of
    # the scale wouldn't actually read as text against this app's dark bg.
    for base in (theme.PRIMARY, theme.SECONDARY, theme.TEAL, theme.ROSE, theme.INFO):
        scale = theme.generate_scale(base)
        assert _luminance(scale[1]) < _luminance(scale[12])


def test_generate_scale_preserves_hue_family():
    # Every step's hue should stay close to the base hue (not drift to an
    # unrelated color) -- hue-agnostic so it holds for whatever PRIMARY/etc.
    # currently is, rather than hardcoding one palette's RGB channel order.
    for base in (theme.PRIMARY, theme.SECONDARY, theme.TEAL, theme.ROSE, theme.INFO):
        base_hue, _, _ = theme._hex_to_hsl(base)
        scale = theme.generate_scale(base)
        for step in (5, 7, 9, 11):
            step_hue, _, _ = theme._hex_to_hsl(scale[step])
            delta = min(abs(step_hue - base_hue), 1 - abs(step_hue - base_hue))
            assert delta < 0.03, f"{base} step {step} hue drifted: {base_hue} -> {step_hue}"


def test_scale_lookup_matches_generated_dict():
    assert theme.scale("amber", 9) == theme.SCALES["amber"][9]
    assert theme.scale("teal", 1) == theme.SCALES["teal"][1]


def test_scales_dict_covers_all_five_hues():
    assert set(theme.SCALES.keys()) == {"amber", "lavender", "teal", "rose", "info"}


# ── theme.card() class composition ──────────────────────────────────────────
def test_card_classes_defaults_to_full_width():
    assert theme._card_classes("", None) == "studio-card w-full"


def test_card_classes_appends_extra_classes():
    result = theme._card_classes("gap-3 mt-2", None)
    assert result == "studio-card w-full gap-3 mt-2"


def test_card_classes_omits_w_full_when_explicit_width_given():
    # A dialog wanting a fixed w-96 shouldn't also get a conflicting w-full.
    result = theme._card_classes("w-96 gap-3", None)
    assert "w-full" not in result
    assert "w-96" in result


def test_card_classes_omits_w_full_for_max_width_utility():
    result = theme._card_classes("max-w-lg gap-3", None)
    assert "w-full" not in result
    assert "max-w-lg" in result


def test_card_classes_tone_modifier():
    result = theme._card_classes("", "amber")
    assert "studio-card--amber" in result
    assert "w-full" in result


# ── theme.data_row() cell resolution ────────────────────────────────────────
def test_data_row_cells_basic_text_structure():
    resolved = theme._data_row_cells([{"text": "Hello"}])
    assert resolved == [{"kind": "text", "value": "Hello", "classes": "text-body"}]


def test_data_row_cells_header_uses_label_role_by_default():
    resolved = theme._data_row_cells([{"text": "Title"}], header=True)
    assert resolved[0]["classes"] == "text-label"


def test_data_row_cells_width_token_maps_to_col_class():
    resolved = theme._data_row_cells([{"text": "x", "width": "lg"}])
    assert "dcol-lg" in resolved[0]["classes"]


def test_data_row_cells_grow_width_token():
    resolved = theme._data_row_cells([{"text": "x", "width": "grow"}])
    assert "dcol-grow" in resolved[0]["classes"]


def test_data_row_cells_rejects_unknown_width():
    with pytest.raises(ValueError):
        theme._data_row_cells([{"text": "x", "width": "huge"}])


def test_data_row_cells_color_class_appended():
    resolved = theme._data_row_cells([{"text": "x", "color": "text-rose"}])
    assert "text-rose" in resolved[0]["classes"]


def test_data_row_cells_custom_classes_override_default():
    resolved = theme._data_row_cells([{"text": "x", "classes": "font-bold"}])
    assert resolved[0]["classes"] == "font-bold"


def test_data_row_cells_icon_cell_uses_icon_kind():
    resolved = theme._data_row_cells([{"icon": "swap_horiz", "color": "text-amber"}])
    assert resolved[0] == {"kind": "icon", "value": "swap_horiz", "classes": "text-amber"}


def test_data_row_cells_icon_cell_default_classes_empty():
    # Icon cells shouldn't inherit the text-body/text-label default (that's a
    # font-sizing role, meaningless on a ui.icon()).
    resolved = theme._data_row_cells([{"icon": "sync"}])
    assert resolved[0]["classes"] == ""


def test_data_row_cells_multiple_cells_preserve_order():
    resolved = theme._data_row_cells([{"text": "a"}, {"text": "b"}, {"icon": "help"}])
    assert [r["value"] for r in resolved] == ["a", "b", "help"]
    assert [r["kind"] for r in resolved] == ["text", "text", "icon"]
