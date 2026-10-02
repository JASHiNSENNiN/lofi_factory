"""
harmony_engine.py — functional-harmony (Roman-numeral) progression generator.

Generation is a table-driven tonic/subdominant/dominant walk with optional
secondary dominants (generate_functional_progression); it does not need
music21. music21 is only used by the two checking helpers below
(validate_roman_numerals, realize_numeral_pitches), which the tests use to
confirm the hand-written tables agree with real Roman-numeral theory. It is
imported lazily there and is a dev-only dependency (requirements-dev.txt).

This is layered ON TOP OF the existing curated 51-entry `PROGRESSIONS` table
and its Markov-chain walk (`generate_progression` in composer.py)
— NOT a replacement. It is one more alternate progression source, selected
per-track with a small probability from `pick_params()`, exactly like the
existing Euclidean-drum-pattern and Markov-progression toggles. When it is
not selected, or music21 is unavailable, or generation fails for any reason,
callers fall back to the pre-existing progression sources — daily unattended
runs must never break over this.

Design: rather than let music21 invent arbitrary chord spellings (which the
rest of the pipeline's fixed VOICING_OPTIONS/BASS_ROOTS tables would not
have voicings for), each supported "tonal center" maps every diatonic and
secondary-dominant Roman numeral to one of the EXACT chord-symbol strings
already present in composer.py's VOICING_OPTIONS table. music21
is used to validate/realize the harmony (confirm each numeral is a legitimate
resolution in that key, and to pin down real functional relationships like
"the dominant of ii" or "the applied V of the relative major"), while the
concrete chord symbols returned stay inside the pipeline's existing,
hand-voiced vocabulary — so generated progressions always render with real
(not default-fallback) voicings downstream.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

def _music21():
    """Import music21 on first use (heavy: ~0.25 s and >100 MB, and only the
    checking helpers need it)."""
    try:
        from music21 import roman, key as m21key
    except ImportError as e:
        raise HarmonyEngineUnavailable("music21 is not installed (pip install -r requirements-dev.txt)") from e
    return roman, m21key


class HarmonyEngineUnavailable(RuntimeError):
    """Raised when music21 is not importable."""


# ─── TONAL CENTERS ─────────────────────────────────────────────────────────
# Each tonal center is a (major key name) covering both that major key and
# its relative minor. Chord symbols are drawn only from
# composer.VOICING_OPTIONS so every generated progression has a
# real existing voicing. Degrees with no matching table entry are simply
# omitted (the grammar walk skips to another degree in the same function).

# major-mode: degree -> list of chord-symbol options
_MAJOR_DEGREE_CHORDS: dict[str, dict[str, list[str]]] = {
    'C': {
        'I': ['Cmaj7', 'Cmaj9'], 'ii': ['Dm7', 'Dm9'], 'iii': ['Em7'],
        'IV': ['Fmaj7', 'Fmaj9', 'Fmaj7s'], 'V': ['G7', 'G7b9'],
        'vi': ['Am7', 'Am9'], 'viio': ['Bm7b5'],
    },
    'F': {
        'I': ['Fmaj7', 'Fmaj9'], 'ii': ['Gm7', 'Gm9'], 'iii': ['Am7'],
        'IV': ['Bbmaj7'], 'V': ['C7'], 'vi': ['Dm7', 'Dm9'],
    },
    'Bb': {
        'I': ['Bbmaj7'], 'ii': ['Cm7'], 'iii': ['Dm7', 'Dm9'],
        'IV': ['Ebmaj7'], 'V': ['F7'], 'vi': ['Gm7', 'Gm9'],
    },
    'Eb': {
        'I': ['Ebmaj7'], 'ii': ['Fm7'], 'iii': ['Gm7', 'Gm9'],
        'V': ['Bb7'], 'vi': ['Cm7'],
    },
}

# major-mode secondary dominants: target degree -> applied-dominant symbol(s)
_MAJOR_SECONDARY_DOMS: dict[str, dict[str, list[str]]] = {
    'C':  {'ii': ['A7'], 'IV': ['C7'], 'V': ['D7', 'D9'], 'vi': ['E7', 'E7b9']},
    'F':  {'ii': ['D7', 'D9'], 'IV': ['F7'], 'V': ['G7'], 'vi': ['A7']},
    'Bb': {'ii': ['G7'], 'IV': ['Bb7'], 'V': ['C7'], 'vi': ['D7', 'D9']},
    'Eb': {'ii': ['C7'], 'V': ['F7'], 'vi': ['G7']},
}

# minor-mode (relative natural/harmonic minor of the same tonal center):
# degree -> chord-symbol options. 'V' uses the harmonic-minor (raised leading
# tone) dominant, matching how the curated table already voices minor-key
# dominants (e.g. E7/E7b9 resolving to Am7).
_MINOR_DEGREE_CHORDS: dict[str, dict[str, list[str]]] = {
    'C': {  # A minor
        'i': ['Am7', 'Am9'], 'iio': ['Bm7b5'], 'III': ['Cmaj7', 'Cmaj9'],
        'iv': ['Dm7', 'Dm9'], 'V': ['E7', 'E7b9'], 'VI': ['Fmaj7', 'Fmaj9'],
        'VII': ['G7'],
    },
    'F': {  # D minor
        'i': ['Dm7', 'Dm9'], 'III': ['Fmaj7', 'Fmaj9'], 'iv': ['Gm7', 'Gm9'],
        'V': ['A7'], 'VI': ['Bbmaj7'], 'VII': ['Cmaj7'],
    },
    'Bb': {  # G minor
        'i': ['Gm7', 'Gm9'], 'III': ['Bbmaj7'], 'iv': ['Cm7'],
        'V': ['D7', 'D9'], 'VI': ['Ebmaj7'], 'VII': ['Fmaj7'],
    },
    'Eb': {  # C minor
        'i': ['Cm7'], 'III': ['Ebmaj7'], 'iv': ['Fm7'], 'V': ['G7'],
        'VII': ['Bbmaj7'],
    },
}

_MINOR_SECONDARY_DOMS: dict[str, dict[str, list[str]]] = {
    'C':  {'iv': ['A7'], 'III': ['G7'], 'VI': ['C7']},
    'F':  {'iv': ['D7'], 'III': ['C7'], 'VI': ['F7']},
    'Bb': {'iv': ['G7'], 'III': ['F7'], 'VI': ['Bb7']},
    'Eb': {'iv': ['C7'], 'III': ['Bb7'], 'VII': ['F7']},
}

# Functional groupings driving the T(onic)-S(ubdominant)-D(ominant) walk.
_MAJOR_FUNCTIONS = {'T': ['I', 'vi'], 'S': ['ii', 'IV'], 'D': ['V', 'viio']}
_MINOR_FUNCTIONS = {'T': ['i', 'III'], 'S': ['iv', 'iio'], 'D': ['V', 'VII']}

# T -> S -> D -> T is the classical functional-harmony backbone; small
# probabilities of same-function repeats and D->S "backtracking" keep it from
# being perfectly mechanical.
_FUNCTION_TRANSITIONS = {
    'T': {'S': 0.55, 'D': 0.25, 'T': 0.20},
    'S': {'D': 0.65, 'S': 0.15, 'T': 0.20},
    'D': {'T': 0.75, 'S': 0.10, 'D': 0.15},
}

TONAL_CENTERS = tuple(_MAJOR_DEGREE_CHORDS.keys())

# Map the pipeline's existing KEY_ROOTS-style key names to the nearest
# supported tonal center + mode. Keys not covered by the curated chord
# vocabulary fall back to the tonal center whose major-scale pitch-class is
# closest on the circle of fifths (a reasonable "sounds nearby" default —
# the pipeline already treats `key` loosely for progression purposes; see
# composer.py's own note that voicings can be "modal" for a
# major key paired with a minor-flavoured progression index).
_CENTER_PITCH_CLASS = {'C': 0, 'F': 5, 'Bb': 10, 'Eb': 3}
_KEY_TO_CENTER_MODE: dict[str, tuple[str, str]] = {
    'Am': ('C', 'minor'), 'C': ('C', 'major'),
    'Dm': ('F', 'minor'), 'F': ('F', 'major'),
    'Gm': ('Bb', 'minor'), 'Bb': ('Bb', 'major'),
    'Cm': ('Eb', 'minor'), 'Ebm': ('Eb', 'minor'),
    'Em': ('C', 'minor'),   # closest by pitch-class distance
    'Bm': ('C', 'minor'),
    'F#m': ('F', 'minor'),
    'D': ('F', 'major'),
    'A': ('C', 'major'),
    'G': ('F', 'major'),
}


def center_for_key(key_name: str) -> tuple[str, str]:
    """Map a pipeline key name (e.g. 'Am', 'C', 'Gm') to (tonal_center, mode)."""
    if key_name in _KEY_TO_CENTER_MODE:
        return _KEY_TO_CENTER_MODE[key_name]
    return 'C', 'minor' if key_name.endswith('m') else 'major'


@dataclass
class HarmonyProgression:
    chords: list[tuple[str, int]]       # (chord_symbol, duration_bars) — same
                                         # shape as PROGRESSIONS entries
    roman_numerals: list[str]           # parallel list of Roman-numeral labels
    tonal_center: str
    mode: str

    def __len__(self) -> int:
        return len(self.chords)


def _pick_degree(functions: dict[str, list[str]], available: dict[str, list[str]],
                  function_key: str, rng: random.Random) -> str | None:
    candidates = [d for d in functions[function_key] if d in available]
    if not candidates:
        # fall back to any available degree at all (keeps the walk alive
        # even for tonal centers with sparse coverage, e.g. 'Eb')
        candidates = list(available.keys())
    return rng.choice(candidates) if candidates else None


def generate_functional_progression(
    tonal_center: str = 'C',
    mode: str = 'major',
    length: int = 4,
    seed: int | None = None,
    secondary_dominant_prob: float = 0.35,
    default_duration_bars: int = 2,
) -> HarmonyProgression:
    """
    Generate a fresh chord progression by walking a classical T-S-D
    functional-harmony grammar (music21-validated) in the given tonal
    center/mode, with probabilistic secondary-dominant tonicization.

    `length` is the number of primary (non-tonicizing) harmonic slots —
    matching generate_progression()'s length semantics. Inserted secondary
    dominants add extra entries, so the returned progression can be longer.

    Deterministic when `seed` is given (uses a local Random instance so it
    does not disturb the pipeline's global random stream).
    """
    if tonal_center not in _MAJOR_DEGREE_CHORDS:
        tonal_center = 'C'
    rng = random.Random(seed) if seed is not None else random

    if mode == 'minor':
        degree_chords = _MINOR_DEGREE_CHORDS[tonal_center]
        secondary_doms = _MINOR_SECONDARY_DOMS.get(tonal_center, {})
        functions = _MINOR_FUNCTIONS
        start_func = 'T'
    else:
        mode = 'major'
        degree_chords = _MAJOR_DEGREE_CHORDS[tonal_center]
        secondary_doms = _MAJOR_SECONDARY_DOMS.get(tonal_center, {})
        functions = _MAJOR_FUNCTIONS
        start_func = 'T'

    chords: list[tuple[str, int]] = []
    numerals: list[str] = []

    cur_func = start_func
    length = max(1, length)
    for i in range(length):
        degree = _pick_degree(functions, degree_chords, cur_func, rng)
        if degree is None:
            break
        symbol = rng.choice(degree_chords[degree])
        duration = default_duration_bars

        # Tonicization: insert the applied dominant of this degree as its
        # own 1-bar chord immediately before it (never on the very first
        # slot — nothing to tonicize away from yet).
        if i > 0 and degree in secondary_doms and duration >= 2 and \
                rng.random() < secondary_dominant_prob:
            sub_symbol = rng.choice(secondary_doms[degree])
            chords.append((sub_symbol, 1))
            numerals.append(f'V7/{degree}')
            duration -= 1

        chords.append((symbol, duration))
        numerals.append(degree)

        cur_func = rng.choices(
            list(_FUNCTION_TRANSITIONS[cur_func].keys()),
            weights=list(_FUNCTION_TRANSITIONS[cur_func].values()),
            k=1,
        )[0]

    if not chords:
        # Degenerate fallback: bare tonic, still musically valid.
        tonic_degree = functions['T'][0]
        tonic_symbol = next(iter(degree_chords.get(tonic_degree, degree_chords[list(degree_chords)[0]])))
        chords = [(tonic_symbol, default_duration_bars)]
        numerals = [tonic_degree]

    return HarmonyProgression(chords=chords, roman_numerals=numerals,
                               tonal_center=tonal_center, mode=mode)


def validate_roman_numerals(tonal_center: str, mode: str, numerals: list[str]) -> bool:
    """
    True iff every Roman numeral in `numerals` parses as a legitimate chord
    in the given (tonal_center, mode) key via music21's RomanNumeral —
    i.e. this really is a valid Roman-numeral sequence in that key, not just
    a list of plausible-looking strings.
    """
    roman, m21key = _music21()
    tonic = tonal_center
    k = m21key.Key(tonic, 'minor' if mode == 'minor' else 'major')
    for numeral in numerals:
        try:
            roman.RomanNumeral(numeral, k)
        except Exception:
            return False
    return True


def realize_numeral_pitches(tonal_center: str, mode: str, numeral: str) -> list[int]:
    """
    Return the MIDI pitch classes (0-11, one octave, root-position) music21
    computes for `numeral` in the given key — used by tests to cross-check
    that the hand-built chord-symbol tables agree with real Roman-numeral
    theory, and available for callers that want ground-truth pitch content
    rather than the table-driven chord symbol.
    """
    roman, m21key = _music21()
    k = m21key.Key(tonal_center, 'minor' if mode == 'minor' else 'major')
    rn = roman.RomanNumeral(numeral, k)
    return sorted({p.midi % 12 for p in rn.pitches})
