from scripts.seo_utils import format_timestamp, trim_tags_to_budget


def test_format_timestamp_under_an_hour():
    assert format_timestamp(65) == "1:05"
    assert format_timestamp(0) == "0:00"
    assert format_timestamp(59) == "0:59"


def test_format_timestamp_over_an_hour():
    assert format_timestamp(3661) == "1:01:01"
    assert format_timestamp(3600) == "1:00:00"


def test_trim_tags_to_budget_fits_within_limit():
    tags = ["lofi", "study music", "a very long low-value tag that eats budget"]
    trimmed = trim_tags_to_budget(tags, limit=20)
    joined_len = sum(len(t) for t in trimmed) + max(0, len(trimmed) - 1)
    assert joined_len <= 20


def test_trim_tags_to_budget_drops_longest_first():
    tags = ["lofi", "a very long low-value tag that eats budget", "study"]
    trimmed = trim_tags_to_budget(tags, limit=20)
    assert "lofi" in trimmed
    assert "study" in trimmed
    assert "a very long low-value tag that eats budget" not in trimmed


def test_trim_tags_to_budget_noop_when_already_under_limit():
    tags = ["lofi", "study music"]
    assert trim_tags_to_budget(tags, limit=500) == tags


def test_trim_tags_to_budget_empty_list():
    assert trim_tags_to_budget([], limit=100) == []
