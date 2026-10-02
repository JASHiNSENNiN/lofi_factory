"""
seo_utils.py — shared helpers used by generate_seo.py and
scripts/upload_youtube.py, which each independently reimplemented the same
timestamp-formatting and tag-budget-trimming logic.
"""

from __future__ import annotations


def format_timestamp(secs: int) -> str:
    """Format seconds as a YouTube chapter timestamp: H:MM:SS if >= 1 hour, else M:SS."""
    secs = int(secs)
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _yt_tag_len(tag: str) -> int:
    """A tag's contribution to YouTube's internal 500-char tags budget.

    YouTube treats the tags list as a single comma-separated string and
    quote-wraps any tag containing a space (to disambiguate it from the
    comma separator) -- so a space-containing tag actually costs len(tag)+2,
    not len(tag). Undercounting this is what let past tag sets slip through
    this budget check while still getting rejected by the real API with
    "The request metadata specifies invalid video keywords." (invalidTags).
    """
    return len(tag) + 2 if " " in tag else len(tag)


def trim_tags_to_budget(tags: list[str], limit: int) -> list[str]:
    """
    Trim a tag list so the tags fit within `limit` characters using YouTube's
    actual accounting (see _yt_tag_len) for how tags are joined/quoted, not
    a naive ", ".join() length. Removes the LONGEST tag repeatedly rather
    than trimming from the end, so short high-intent tags (e.g. "lofi",
    "study music") survive over long, low-value ones.
    """
    kept = list(tags)
    while kept and sum(_yt_tag_len(t) for t in kept) + len(kept) - 1 > limit:
        longest = max(range(len(kept)), key=lambda i: _yt_tag_len(kept[i]))
        kept.pop(longest)
    return kept
