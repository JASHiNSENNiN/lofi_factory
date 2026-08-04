from scripts.generate_thumbnail_cozy import _derive_short_title, _SHORT_TITLE_MAX_CHARS


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
