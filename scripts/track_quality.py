"""
track_quality.py — objective quality gate for procedurally-generated tracks.

Computes a small set of hard pass/fail checks directly from the MIDI event
lists ((t, note, vel, dur) tuples) that build_midi()/build_midi_v2() already
produce, BEFORE rendering to audio. Used to catch degenerate generations (a
stuck melody, an empty drum pattern, a collapsed voicing) before they reach
a real daily-upload audience.

Deliberately a set of simple pass/fail gates rather than one hand-tuned
composite score — easier to reason about and debug from the recipe log than
a formula with weights that have never been calibrated against real output
(nothing in this pipeline has been executed end-to-end at the time this was
written).
"""

from __future__ import annotations

import math
from collections import Counter

PPQN = 480
BAR = PPQN * 4
S16 = PPQN // 4   # ticks per 16th-note step

MIN_QUALITY_SCORE = 0.8
MAX_RETRIES = 2

# Sub-genres where a narrower melodic pitch range is intentional, not degenerate.
_NARROW_RANGE_SUBGENRES = {'ambient', 'piano_lofi', 'chill_beats'}

KICK_NOTE = 36
SNARE_NOTES = (38, 40)


def _pitch_class_entropy(mel_ev: list[tuple]) -> float:
    """Shannon entropy (bits) of the melody's pitch-class distribution.
    Near 0 means the melody is stuck on essentially one pitch class."""
    if not mel_ev:
        return 0.0
    pcs = [note % 12 for (_t, note, _v, _d) in mel_ev]
    counts = Counter(pcs)
    total = len(pcs)
    entropy = 0.0
    for c in counts.values():
        p = c / total
        entropy -= p * math.log2(p)
    return entropy


def _melody_rest_ratio(mel_ev: list[tuple], active_bars: int) -> float:
    """Fraction of 16th-note steps in the active span with no melody onset."""
    if active_bars <= 0:
        return 0.0
    total_steps = active_bars * 16
    onset_steps = {int(t) // S16 for (t, _n, _v, _d) in mel_ev}
    return 1.0 - (len(onset_steps) / total_steps)


def _longest_empty_span_frac(mel_ev: list[tuple], active_bars: int) -> float:
    """
    Longest contiguous run of empty 16th-note steps, as a fraction of the
    active span — catches a generator that produces a few bars then silently
    stalls, which an average rest ratio can miss.
    """
    if active_bars <= 0:
        return 0.0
    total_steps = active_bars * 16
    onset_steps = sorted({
        int(t) // S16 for (t, _n, _v, _d) in mel_ev
        if 0 <= int(t) // S16 < total_steps
    })
    if not onset_steps:
        return 1.0
    longest = onset_steps[0]  # gap before the first onset
    for a, b in zip(onset_steps, onset_steps[1:]):
        longest = max(longest, b - a - 1)
    longest = max(longest, total_steps - 1 - onset_steps[-1])  # gap after the last onset
    return longest / total_steps


def _pitch_range(mel_ev: list[tuple]) -> int:
    if not mel_ev:
        return 0
    notes = [note for (_t, note, _v, _d) in mel_ev]
    return max(notes) - min(notes)


def score_track_quality(mel_ev: list[tuple], piano_ev: list[tuple], drum_ev: list[tuple],
                         active_bars: int, sub_genre: str | None = None) -> tuple[float, list[str]]:
    """
    Score a generated track against 5 hard pass/fail gates.

    Returns (score, failures): score is the fraction of gates passed (in
    [0,1]); failures lists which gates failed (for the recipe log / debugging).
    """
    failures: list[str] = []

    if _pitch_class_entropy(mel_ev) < 0.5:
        failures.append('low_pitch_entropy')

    if _melody_rest_ratio(mel_ev, active_bars) > 0.97:
        failures.append('melody_too_sparse')

    if _longest_empty_span_frac(mel_ev, active_bars) > 0.40:
        failures.append('melody_long_silence')

    min_acceptable_range = 1 if sub_genre in _NARROW_RANGE_SUBGENRES else 3
    if not mel_ev or _pitch_range(mel_ev) < min_acceptable_range:
        failures.append('flat_pitch_range')

    has_kick = any(note == KICK_NOTE for (_t, note, _v, _d) in drum_ev)
    has_snare = any(note in SNARE_NOTES for (_t, note, _v, _d) in drum_ev)
    if not (has_kick and has_snare and piano_ev):
        failures.append('drum_or_piano_empty')

    n_gates = 5
    score = (n_gates - len(failures)) / n_gates
    return score, failures
