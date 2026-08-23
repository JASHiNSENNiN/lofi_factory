"""
Regression tests for the render/queue dialogs' composition controls
(sub-genre / mood / engine) added alongside theme/duration/privacy.

render_dialog() and queue_dialog() build their run.py/publish.py argv via
the shared webui.app._build_render_args() helper (see webui/app.py) --
exercising that pure function directly is the same "no full NiceGUI dialog
rendering" approach test_helpers.py already documents for this codebase
(full page rendering would need nicegui.testing's browser-driven User
fixture, which isn't wired up here).
"""
from __future__ import annotations

from webui import config
from webui.app import (
    _build_render_args,
    _ENGINE_SELECT_OPTIONS,
    _subgenre_select_options,
)


# ── _build_render_args: defaults ────────────────────────────────────────────
def test_render_only_defaults_omit_all_new_flags():
    args = _build_render_args(upload=False, theme="random", duration="2 hours",
                               privacy="public")
    assert args == ["run.py", "--skip-upload", "--duration", "2 hours"]


def test_upload_defaults_omit_all_new_flags():
    args = _build_render_args(upload=True, theme="random", duration="2 hours",
                               privacy="public")
    assert args == ["publish.py", "auto", "--privacy", "public", "--duration", "2 hours"]


# ── sub-genre ────────────────────────────────────────────────────────────────
def test_non_auto_subgenre_appends_flag():
    args = _build_render_args(upload=False, theme="random", duration="1 hour",
                               privacy="public", subgenre="lofi_house")
    assert "--sub-genre" in args
    assert args[args.index("--sub-genre") + 1] == "lofi_house"


def test_auto_subgenre_omits_flag():
    args = _build_render_args(upload=False, theme="random", duration="1 hour",
                               privacy="public", subgenre="auto")
    assert "--sub-genre" not in args


# ── mood ─────────────────────────────────────────────────────────────────────
def test_nonempty_mood_appends_flag():
    args = _build_render_args(upload=False, theme="random", duration="1 hour",
                               privacy="public", mood="rainy study session")
    assert "--mood" in args
    assert args[args.index("--mood") + 1] == "rainy study session"


def test_empty_mood_omits_flag():
    args = _build_render_args(upload=False, theme="random", duration="1 hour",
                               privacy="public", mood="")
    assert "--mood" not in args


# ── engine (3-state, matches run.py's BooleanOptionalAction) ────────────────
def test_engine_auto_omits_both_music_v2_flags():
    args = _build_render_args(upload=False, theme="random", duration="1 hour",
                               privacy="public", engine="auto")
    assert "--music-v2" not in args
    assert "--no-music-v2" not in args


def test_engine_v2_appends_music_v2_flag():
    args = _build_render_args(upload=False, theme="random", duration="1 hour",
                               privacy="public", engine="v2")
    assert "--music-v2" in args
    assert "--no-music-v2" not in args


def test_engine_v1_appends_no_music_v2_flag():
    args = _build_render_args(upload=False, theme="random", duration="1 hour",
                               privacy="public", engine="v1")
    assert "--no-music-v2" in args
    assert "--music-v2" not in args


# ── theme still behaves as before (random omitted, explicit passed) ─────────
def test_explicit_theme_still_appends_flag():
    args = _build_render_args(upload=False, theme="vaporwave", duration="1 hour",
                               privacy="public")
    assert "--theme" in args
    assert args[args.index("--theme") + 1] == "vaporwave"


# ── all controls combined, both upload branches ──────────────────────────────
def test_all_new_controls_combined_render_only():
    args = _build_render_args(upload=False, theme="vaporwave", duration="3 hours",
                               privacy="unlisted", subgenre="dark_lofi",
                               mood="late night city drive", engine="v2")
    assert args == [
        "run.py", "--skip-upload", "--duration", "3 hours",
        "--theme", "vaporwave", "--sub-genre", "dark_lofi",
        "--mood", "late night city drive", "--music-v2",
    ]


def test_all_new_controls_combined_render_and_upload():
    args = _build_render_args(upload=True, theme="vaporwave", duration="3 hours",
                               privacy="unlisted", subgenre="dark_lofi",
                               mood="late night city drive", engine="v1")
    assert args == [
        "publish.py", "auto", "--privacy", "unlisted", "--duration", "3 hours",
        "--theme", "vaporwave", "--sub-genre", "dark_lofi",
        "--mood", "late night city drive", "--no-music-v2",
    ]


# ── option catalogs feeding the ui.select widgets ────────────────────────────
def test_subgenre_select_options_default_to_auto_and_include_all_keys():
    opts = _subgenre_select_options()
    assert opts["auto"] == "Auto (algorithm picks)"
    keys = config.subgenre_choices()
    assert len(keys) == 29
    for k in keys:
        assert k in opts
        assert opts[k] == k.replace("_", " ").title()


def test_engine_select_options_are_exactly_the_3_states():
    assert set(_ENGINE_SELECT_OPTIONS) == {"auto", "v1", "v2"}
    assert _ENGINE_SELECT_OPTIONS["auto"] == "Auto (bandit-selected)"


# ── config.subgenre_choices() itself ─────────────────────────────────────────
def test_subgenre_choices_are_sorted_and_unique():
    keys = config.subgenre_choices()
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys))


def test_subgenre_choices_include_known_keys():
    keys = set(config.subgenre_choices())
    assert "lofi_house" in keys
    assert "dark_lofi" in keys
