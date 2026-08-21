"""
euclidean.py — Bjorklund's Euclidean-rhythm algorithm, E(k, n).

Previously implemented twice, identically, in generate_music_gemini.py (the
MIDI-layer rhythm generator) and drum_sampler.py (the audio-layer sample
generator) — drum_sampler.py's copy was deliberately kept local rather than
importing generate_music_gemini.py to stay dependency-free of the (much
heavier) MIDI-generation module. This tiny leaf module gives both call sites
a single source of truth without creating that dependency: generate_music_
gemini.py already imports FROM drum_sampler.py (for layer_drum_break), so
the reverse import would have been circular anyway.
"""

from __future__ import annotations


def bjorklund(k: int, n: int) -> list[int]:
    """Distribute k onsets as evenly as possible over n steps (1 = onset, 0 =
    rest), rotated so the first onset lands on step 0."""
    pattern, level = [], 0
    for _ in range(n):
        level += k
        if level >= n:
            level -= n
            pattern.append(1)
        else:
            pattern.append(0)
    if 1 in pattern:
        first = pattern.index(1)
        pattern = pattern[first:] + pattern[:first]
    return pattern
