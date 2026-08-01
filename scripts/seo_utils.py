"""
seo_utils.py — shared helpers used by generate_seo.py, lofi_inator/seo.py, and
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


def trim_tags_to_budget(tags: list[str], limit: int) -> list[str]:
    """
    Trim a tag list so the tags, joined with ", " (YouTube's actual join format),
    fit within `limit` characters. Removes the LONGEST tag repeatedly rather than
    trimming from the end, so short high-intent tags (e.g. "lofi", "study music")
    survive over long, low-value ones.
    """
    kept = list(tags)
    while kept and sum(len(t) for t in kept) + len(kept) - 1 > limit:
        longest = max(range(len(kept)), key=lambda i: len(kept[i]))
        kept.pop(longest)
    return kept
