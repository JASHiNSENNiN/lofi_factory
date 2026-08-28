"""
Snapshot-equivalence test for the config/genres/*.yaml refactor.

Every table below is HAND-TYPED from the pre-refactor literal dicts/sets
that used to live in scripts/generate_music_gemini.py and scripts/lofi_fx.py
(as of `git show HEAD:...` at the time this test was written) — NOT derived
from the new YAML files. This is deliberate: re-deriving the "expected"
values from the same YAML that scripts/genre_presets.py parses would make
this test tautological and unable to catch a bug in the migration (e.g. a
transposed field, a dropped subgenre, a wrong fallback).

If a table below and scripts/genre_presets.py's build_*() output ever
diverge, that means either the YAML data drifted from the original Python
literals, or the loader has a bug — both are real regressions this test
exists to catch.

DELIBERATE EXCEPTION: the "wire progressions 51-58 into subgenre configs"
research pass (research/subgenres/*.md-driven additions to config/genres/
*.yaml's composition.progression_indices) intentionally appended new indices
to 10 subgenres' progression pools — a real content change, not drift/bug.
Those 10 entries' 'progs' lists below have been hand-updated to match the
new YAML (each addition documented with its rationale as a comment in the
corresponding config/genres/<key>.yaml), so this test still catches any
*other* accidental divergence for those subgenres. Affected keys: chillhop,
hip_hop_lofi, lofi_jazz, bedroom_pop, bossa_lofi, city_pop, vaporwave,
lofi_classical, neo_soul, lofi_rnb.
"""

from scripts import genre_presets
from scripts.gm_instruments import (
    GM_BASS,  # noqa: F401  (unused directly but documents full GM set available)
    GM_CELLO,
    GM_EP2,
    GM_FLUTE,
    GM_GUITAR_JAZZ,
    GM_GUITAR_NYLON,
    GM_KALIMBA,
    GM_KOTO,
    GM_MARIMBA,
    GM_MUTED_TRUMPET,
    GM_ORGAN_ROCK,
    GM_RHODES,
    GM_SITAR,
    GM_STRINGS,
    GM_VIBRAPHONE,
    GM_WARM_PAD,
)

# ─── generate_music_gemini._SUBGENRE_CONFIG (pre-refactor literal) ───────────
EXPECTED_SUBGENRE_CONFIG = {
    'chillhop':     {'piano': GM_RHODES,    'melody': GM_GUITAR_NYLON,'cmelo': GM_WARM_PAD,
                     'scale': ['pent','dorian','natural_minor'],
                     'drum_pats': [0,1,2,13], 'bpm': (76,88), 'energy': None,
                     'progs': [0,1,7,10,11,13,33,38,44,45,57,58]},
    'hip_hop_lofi': {'piano': GM_RHODES,    'melody': GM_MUTED_TRUMPET,'cmelo': GM_ORGAN_ROCK,
                     'scale': ['pent','dorian','mixo','blues'],
                     'drum_pats': [0,2,6,11,14], 'bpm': (78,92), 'energy': None,
                     'progs': [0,1,3,10,11,38,39,45,53]},
    'lo_fi_funk':   {'piano': GM_EP2,       'melody': GM_GUITAR_JAZZ,'cmelo': GM_ORGAN_ROCK,
                     'scale': ['mixo','pent','blues'],
                     'drum_pats': [5,8,12,14], 'bpm': (82,96), 'energy': 'high',
                     'progs': [26,27,10,11,3,38,45]},
    'chill_beats':  {'piano': GM_WARM_PAD,  'melody': GM_VIBRAPHONE,'cmelo': GM_WARM_PAD,
                     'scale': ['pent','dorian','natural_minor'],
                     'drum_pats': [1,7,9,10,13], 'bpm': (62,76), 'energy': 'low',
                     'progs': [7,12,13,19,20,33,35,36]},
    'lofi_house':   {'piano': GM_EP2,       'melody': GM_VIBRAPHONE,'cmelo': GM_GUITAR_JAZZ,
                     'scale': ['dorian','pent','major'],
                     # BPM raised per research/subgenres/lofi_house.md -- see
                     # config/genres/lofi_house.yaml comment.
                     'drum_pats': [6,8,11], 'bpm': (110,128), 'energy': 'medium',
                     'progs': [3,0,1,10,33,46]},
    'lofi_jazz':    {'piano': GM_EP2,       'melody': GM_VIBRAPHONE,'cmelo': GM_MUTED_TRUMPET,
                     'scale': ['dorian','natural_minor'],
                     'drum_pats': [1,3,10,13], 'bpm': (70,84), 'energy': None,
                     'progs': [2,5,6,28,31,32,33,34,39,40,54,55,56]},
    'jazz_cafe':    {'piano': GM_EP2,       'melody': GM_VIBRAPHONE,'cmelo': GM_MUTED_TRUMPET,
                     'scale': ['dorian','major_pent','major'],
                     'drum_pats': [3,1,10,13], 'bpm': (78,94), 'energy': None,
                     'progs': [2,5,8,26,6,28,31,33,34,45]},
    'nujabes':      {'piano': GM_RHODES,    'melody': GM_VIBRAPHONE,'cmelo': GM_MUTED_TRUMPET,
                     'scale': ['dorian','pent','lydian','natural_minor'],
                     'drum_pats': [1,0,10,14], 'bpm': (80,92), 'energy': None,
                     'progs': [6,2,28,32,37,39,40]},
    'neo_soul':     {'piano': GM_EP2,       'melody': GM_MUTED_TRUMPET,'cmelo': GM_CELLO,
                     'scale': ['dorian','pent','blues','natural_minor'],
                     'drum_pats': [2,5,8,12], 'bpm': (72,86), 'energy': None,
                     'progs': [10,11,27,38,40,45,56]},
    'bossa_lofi':   {'piano': GM_VIBRAPHONE,'melody': GM_FLUTE,     'cmelo': GM_GUITAR_NYLON,
                     'scale': ['pent','dorian','major'],
                     'drum_pats': [4,12], 'bpm': (74,88), 'energy': None,
                     'progs': [8,9,29,33,34,44,52]},
    'lofi_rnb':     {'piano': GM_EP2,       'melody': GM_MUTED_TRUMPET,'cmelo': GM_CELLO,
                     'scale': ['dorian','pent','mixo','blues'],
                     'drum_pats': [2,5,8,12], 'bpm': (70,84), 'energy': None,
                     'progs': [10,11,3,0,6,27,38,40,45,56]},
    'dark_lofi':    {'piano': GM_RHODES,    'melody': GM_GUITAR_JAZZ,'cmelo': GM_CELLO,
                     'scale': ['phryg','pent','natural_minor','harmonic_minor','blues'],
                     'drum_pats': [0,2,5,9,14], 'bpm': (65,80), 'energy': None,
                     'progs': [14,15,3,31,39,41,42,43]},
    'lofi_phonk':   {'piano': GM_RHODES,    'melody': GM_ORGAN_ROCK,'cmelo': GM_CELLO,
                     'scale': ['phryg','pent','natural_minor'],
                     # BPM raised per research/subgenres/lofi_phonk.md -- see
                     # config/genres/lofi_phonk.yaml comment.
                     # +16: new pattern Q "phonk hat-roll cell" per
                     # research/theory/rhythm-groove.md -- see
                     # config/genres/lofi_phonk.yaml comment.
                     'drum_pats': [0,2,5,9,11,14,16], 'bpm': (75,90), 'energy': None,
                     'progs': [14,15,3,7,41,42,43]},
    'vaporwave':    {'piano': GM_WARM_PAD,  'melody': GM_WARM_PAD,  'cmelo': GM_STRINGS,
                     'scale': ['lydian','major','whole_tone'],
                     'drum_pats': [7,9,11], 'bpm': (58,74), 'energy': 'low',
                     'progs': [12,13,19,7,20,35,37,50,57]},
    'ambient':      {'piano': GM_WARM_PAD,  'melody': GM_WARM_PAD,  'cmelo': GM_FLUTE,
                     'scale': ['pent','natural_minor','whole_tone'],
                     'drum_pats': [7,9,13], 'bpm': (58,74), 'energy': 'low',
                     'progs': [12,13,7,19,35,36]},
    'cozy_cafe':    {'piano': GM_EP2,       'melody': GM_VIBRAPHONE,'cmelo': GM_VIBRAPHONE,
                     'scale': ['major_pent','pent','dorian','major'],
                     'drum_pats': [0,4,10,13], 'bpm': (76,92), 'energy': None,
                     'progs': [22,21,16,17,25,28,44,45,46]},
    'morning_lofi': {'piano': GM_EP2,       'melody': GM_VIBRAPHONE,'cmelo': GM_FLUTE,
                     'scale': ['major_pent','pent','major'],
                     'drum_pats': [0,4,7,13], 'bpm': (72,86), 'energy': 'low',
                     'progs': [16,17,18,4,9,28,44,45,46,49]},
    'anime_lofi':   {'piano': GM_EP2,       'melody': GM_VIBRAPHONE,'cmelo': GM_VIBRAPHONE,
                     'scale': ['major_pent','pent','major'],
                     'drum_pats': [0,1,4,13], 'bpm': (80,94), 'energy': None,
                     'progs': [22,25,16,18,24,44,45,46,49]},
    'summer_vibes': {'piano': GM_VIBRAPHONE,'melody': GM_VIBRAPHONE,'cmelo': GM_MARIMBA,
                     'scale': ['major_pent','pent','major'],
                     'drum_pats': [4,8,12], 'bpm': (80,94), 'energy': None,
                     'progs': [22,21,23,16,18,44,45,46,48]},
    'bedroom_pop':  {'piano': GM_VIBRAPHONE,'melody': GM_GUITAR_NYLON,'cmelo': GM_FLUTE,
                     'scale': ['major_pent','major','pent'],
                     'drum_pats': [0,4,7,13], 'bpm': (78,92), 'energy': None,
                     'progs': [16,17,22,18,44,46,49,51]},
    'city_pop':     {'piano': GM_EP2,       'melody': GM_FLUTE,     'cmelo': GM_GUITAR_JAZZ,
                     'scale': ['major_pent','pent','major'],
                     # BPM raised per research/subgenres/city_pop.md -- see
                     # config/genres/city_pop.yaml comment.
                     'drum_pats': [0,6,8,12], 'bpm': (90,108), 'energy': None,
                     'progs': [8,4,18,29,44,46,48,49,57]},
    'study_lofi':   {'piano': GM_RHODES,    'melody': GM_MARIMBA,   'cmelo': GM_WARM_PAD,
                     'scale': ['pent','dorian','major_pent','major'],
                     'drum_pats': [0,1,9,13], 'bpm': (74,90), 'energy': 'medium',
                     'progs': [0,1,7,22,16,28,33,35,44,46]},
    'piano_lofi':   {'piano': GM_EP2,       'melody': GM_VIBRAPHONE,'cmelo': GM_CELLO,
                     'scale': ['major_pent','pent','dorian','major'],
                     'drum_pats': [7,9,13], 'bpm': (66,84), 'energy': 'low',
                     'progs': [22,16,12,7,20,25,35,36,46]},
    'lofi_classical':{'piano': GM_EP2,      'melody': GM_CELLO,     'cmelo': GM_STRINGS,
                     'scale': ['major','lydian','major_pent','harmonic_minor'],
                     'drum_pats': [7,9,13], 'bpm': (58,78), 'energy': 'low',
                     'progs': [16,17,18,22,25,35,46,50,57]},
    'lofi_drill':   {'piano': GM_RHODES,    'melody': GM_ORGAN_ROCK,'cmelo': GM_CELLO,
                     'scale': ['natural_minor','harmonic_minor','phryg','pent'],
                     'drum_pats': [15,11,2,9], 'bpm': (72,88), 'energy': 'high',
                     'progs': [14,15,41,42,43,7,39]},
    'lofi_world':   {'piano': GM_RHODES,    'melody': GM_SITAR,     'cmelo': GM_KOTO,
                     'scale': ['dorian','phryg_dom','pent','natural_minor'],
                     'drum_pats': [12,4,3,9], 'bpm': (70,86), 'energy': None,
                     # 59 = sparse modal drone (Amadd9/Dmsus4), added Phase 11 2026-08-26
                     'progs': [13,0,7,3,38,10,32,39,59]},
    # 3 new research-driven subgenres (config/genres/sleep_lofi.yaml,
    # lofi_garage.yaml, lofi_synthwave.yaml) -- not "pre-refactor" (they never
    # existed pre-refactor), added here following the same precedent as
    # lofi_drill/lofi_world so this test keeps catching accidental drift for
    # the whole roster, not just the original 24.
    'sleep_lofi':   {'piano': GM_WARM_PAD,  'melody': GM_RHODES,    'cmelo': GM_VIBRAPHONE,
                     'scale': ['pent','natural_minor','dorian'],
                     'drum_pats': [7,9,13], 'bpm': (58,68), 'energy': 'low',
                     'progs': [12,19,35,36,7]},
    'lofi_garage':  {'piano': GM_EP2,       'melody': GM_ORGAN_ROCK,'cmelo': GM_WARM_PAD,
                     'scale': ['dorian','natural_minor','pent'],
                     'drum_pats': [2,8,12,14], 'bpm': (66,76), 'energy': None,
                     'progs': [0,10,11,33,38]},
    'lofi_synthwave':{'piano': GM_WARM_PAD, 'melody': GM_VIBRAPHONE,'cmelo': GM_STRINGS,
                     'scale': ['dorian','natural_minor','major','lydian'],
                     'drum_pats': [6,0,8], 'bpm': (78,100), 'energy': 'medium',
                     'progs': [19,35,37,17,44]},
}

# ─── generate_music_gemini._SWING_RANGE (pre-refactor literal, minus the
# _SWING_DEFAULT fallback which isn't per-subgenre data) ─────────────────────
EXPECTED_SWING_RANGE = {
    'lofi_drill':    (0.63, 0.74),
    'lofi_phonk':    (0.62, 0.73),
    'dark_lofi':     (0.62, 0.71),
    'nujabes':       (0.61, 0.69),
    'hip_hop_lofi':  (0.61, 0.69),
    'lo_fi_funk':    (0.60, 0.69),
    'neo_soul':      (0.60, 0.68),
    'lofi_rnb':      (0.59, 0.68),
    'lofi_jazz':     (0.58, 0.68),
    'chillhop':      (0.59, 0.67),
    'chill_beats':   (0.58, 0.66),
    'study_lofi':    (0.58, 0.66),
    'cozy_cafe':     (0.58, 0.66),
    'jazz_cafe':     (0.57, 0.65),
    'bedroom_pop':   (0.58, 0.65),
    'summer_vibes':  (0.59, 0.66),
    'morning_lofi':  (0.57, 0.65),
    'anime_lofi':    (0.57, 0.65),
    # lofi_house/city_pop: BPM/swing corrections from research/subgenres/
    # lofi_house.md and city_pop.md -- see comments in the corresponding
    # config/genres/*.yaml. Real, deliberate content changes, not drift.
    'lofi_house':    (0.52, 0.62),
    'city_pop':      (0.53, 0.60),
    'bossa_lofi':    (0.52, 0.60),
    'piano_lofi':    (0.53, 0.63),
    'lofi_classical':(0.50, 0.57),
    'ambient':       (0.50, 0.60),
    'vaporwave':     (0.50, 0.60),
    'lofi_world':    (0.58, 0.68),
    'sleep_lofi':    (0.5, 0.56),
    'lofi_garage':   (0.66, 0.76),
    'lofi_synthwave':(0.5, 0.58),
}

# ─── generate_music_gemini._COZY_SUBGENRES (pre-refactor literal) ───────────
EXPECTED_COZY_SUBGENRES = frozenset({
    "cozy_cafe", "anime_lofi", "summer_vibes", "study_lofi",
    "morning_lofi", "jazz_cafe", "piano_lofi", "bedroom_pop",
    "lofi_rnb", "lofi_classical", "lofi_house", "chillhop",
})

# ─── generate_music_gemini._SUBGENRE_TEXTURE (pre-refactor literal) ─────────
EXPECTED_SUBGENRE_TEXTURE = {
    'bossa_lofi':     (GM_GUITAR_NYLON, 'strum'),
    'lofi_jazz':      (GM_GUITAR_JAZZ,  'strum'),
    'jazz_cafe':      (GM_GUITAR_JAZZ,  'strum'),
    'neo_soul':       (GM_ORGAN_ROCK,   'stab'),
    'lo_fi_funk':     (GM_ORGAN_ROCK,   'stab'),
    'lofi_house':     (GM_ORGAN_ROCK,   'stab'),
    'morning_lofi':   (GM_FLUTE,        'breath'),
    'ambient':        (GM_FLUTE,        'breath'),
    'vaporwave':      (GM_FLUTE,        'breath'),
    'lofi_classical': (GM_FLUTE,        'breath'),
    'bedroom_pop':    (GM_GUITAR_NYLON, 'strum'),
    'lofi_rnb':       (GM_GUITAR_JAZZ,  'strum'),
    'summer_vibes':   (GM_MARIMBA,      'pop'),
    'city_pop':       (GM_MARIMBA,      'pop'),
    'nujabes':        (GM_MUTED_TRUMPET,'fill'),
    'lofi_drill':     (GM_ORGAN_ROCK,   'stab'),
    'lofi_world':     (GM_KALIMBA,      'pop'),
    'sleep_lofi':     (GM_FLUTE,        'breath'),
    'lofi_garage':    (GM_VIBRAPHONE,   'stab'),
    'lofi_synthwave': (GM_MARIMBA,      'pop'),
}

# ─── generate_music_gemini._SUBGENRE_DRUM_KITS (pre-refactor literal) ───────
EXPECTED_SUBGENRE_DRUM_KITS = {
    'hip_hop_lofi': [0, 24, 25],
    'lofi_phonk':   [24, 25],
    'dark_lofi':    [0, 8],
    'nujabes':      [0, 32],
    'lofi_jazz':    [32, 40],
    'jazz_cafe':    [32, 40],
    'bossa_lofi':   [40, 32],
    'ambient':      [40, 8],
    'piano_lofi':   [40, 32],
    'lofi_classical': [40, 32],
    'vaporwave':    [24, 0],
    'neo_soul':     [0, 8],
    'chill_beats':  [0, 8],
    'lo_fi_funk':   [0, 16],
}

# ─── generate_music_gemini._FORM_BY_SUBGENRE (pre-refactor literal) ─────────
EXPECTED_FORM_BY_SUBGENRE = {
    'ambient':        'ambient',
    'chill_beats':    'ambient',
    'piano_lofi':     'ambient',
    'vaporwave':      'ambient',
    'lofi_classical': 'extended',
    'lo_fi_funk':     'funk',
    'hip_hop_lofi':   'funk',
    'lofi_house':     'funk',
    'nujabes':        'extended',
    'lofi_jazz':      'extended',
    # New song forms from research/theory/arrangement-structure.md -- see
    # comments in the corresponding config/genres/*.yaml. jazz_cafe was
    # recommended alongside bossa_lofi (both jazz-standard-rooted) but was
    # missed in that pass -- fixed 2026-08-26.
    'bossa_lofi':     'aaba',
    'jazz_cafe':      'aaba',
    'lofi_drill':     'build',
    'lofi_phonk':     'build',
    'sleep_lofi':     'ambient',
    'lofi_garage':    'funk',
    'lofi_synthwave': 'funk',
}

# ─── lofi_fx._GENRE_PRESETS (pre-refactor literal) ───────────────────────────
# presence_db/warmth_db (research/theory/mixing-texture.md item 8, added
# 2026-08-26): 0.0/0.0 (no-op) for every genre except the boom-bap-leaning
# ones the research specifically calls out, which get a small 3-5kHz cut /
# 100-200Hz boost -- see config/genres/{genre}.yaml's mix: block.
EXPECTED_GENRE_FX_PRESETS = {
    "dark_lofi":     {"lpf": 7500,  "bits": 9,  "room": 0.5, "wet": 0.28, "wobble_depth": 0.25, "compress_ratio": 3.5, "vinyl": 0.18, "presence_db": 0.0, "warmth_db": 0.0},
    "lofi_phonk":    {"lpf": 7000,  "bits": 8,  "room": 0.4, "wet": 0.22, "wobble_depth": 0.30, "compress_ratio": 4.0, "vinyl": 0.22, "presence_db": -2.0, "warmth_db": 1.5},
    "vaporwave":     {"lpf": 8000,  "bits": 9,  "room": 0.6, "wet": 0.35, "wobble_depth": 0.28, "compress_ratio": 3.0, "vinyl": 0.14, "presence_db": 0.0, "warmth_db": 0.0},
    "ambient":       {"lpf": 12000, "bits": 13, "room": 0.7, "wet": 0.40, "wobble_depth": 0.12, "compress_ratio": 2.0, "vinyl": 0.05, "presence_db": 0.0, "warmth_db": 0.0},
    "lofi_jazz":     {"lpf": 10000, "bits": 11, "room": 0.4, "wet": 0.22, "wobble_depth": 0.18, "compress_ratio": 2.8, "vinyl": 0.10, "presence_db": 0.0, "warmth_db": 0.0},
    "jazz_cafe":     {"lpf": 11000, "bits": 12, "room": 0.4, "wet": 0.20, "wobble_depth": 0.15, "compress_ratio": 2.5, "vinyl": 0.08, "presence_db": 0.0, "warmth_db": 0.0},
    "nujabes":       {"lpf": 10000, "bits": 11, "room": 0.45,"wet": 0.25, "wobble_depth": 0.20, "compress_ratio": 2.8, "vinyl": 0.12, "presence_db": 0.0, "warmth_db": 0.0},
    "neo_soul":      {"lpf": 11000, "bits": 12, "room": 0.4, "wet": 0.22, "wobble_depth": 0.16, "compress_ratio": 2.5, "vinyl": 0.09, "presence_db": 0.0, "warmth_db": 0.0},
    "bossa_lofi":    {"lpf": 12500, "bits": 13, "room": 0.35,"wet": 0.18, "wobble_depth": 0.12, "compress_ratio": 2.2, "vinyl": 0.06, "presence_db": 0.0, "warmth_db": 0.0},
    "lofi_rnb":      {"lpf": 11000, "bits": 11, "room": 0.4, "wet": 0.22, "wobble_depth": 0.18, "compress_ratio": 2.8, "vinyl": 0.10, "presence_db": 0.0, "warmth_db": 0.0},
    "chillhop":      {"lpf": 9500,  "bits": 11, "room": 0.35,"wet": 0.20, "wobble_depth": 0.18, "compress_ratio": 3.0, "vinyl": 0.12, "presence_db": -1.0, "warmth_db": 1.0},
    "hip_hop_lofi":  {"lpf": 9000,  "bits": 10, "room": 0.35,"wet": 0.18, "wobble_depth": 0.20, "compress_ratio": 3.5, "vinyl": 0.15, "presence_db": -1.5, "warmth_db": 1.5},
    "lo_fi_funk":    {"lpf": 9500,  "bits": 10, "room": 0.35,"wet": 0.18, "wobble_depth": 0.22, "compress_ratio": 3.5, "vinyl": 0.14, "presence_db": -1.5, "warmth_db": 1.5},
    "chill_beats":   {"lpf": 11000, "bits": 12, "room": 0.45,"wet": 0.25, "wobble_depth": 0.14, "compress_ratio": 2.5, "vinyl": 0.08, "presence_db": 0.0, "warmth_db": 0.0},
    "lofi_house":    {"lpf": 11000, "bits": 12, "room": 0.4, "wet": 0.20, "wobble_depth": 0.15, "compress_ratio": 3.0, "vinyl": 0.09, "presence_db": 0.0, "warmth_db": 0.0},
    "cozy_cafe":     {"lpf": 13000, "bits": 13, "room": 0.35,"wet": 0.18, "wobble_depth": 0.12, "compress_ratio": 2.2, "vinyl": 0.06, "presence_db": 0.0, "warmth_db": 0.0},
    "morning_lofi":  {"lpf": 13000, "bits": 13, "room": 0.3, "wet": 0.15, "wobble_depth": 0.10, "compress_ratio": 2.0, "vinyl": 0.05, "presence_db": 0.0, "warmth_db": 0.0},
    "anime_lofi":    {"lpf": 13500, "bits": 14, "room": 0.3, "wet": 0.15, "wobble_depth": 0.10, "compress_ratio": 2.0, "vinyl": 0.04, "presence_db": 0.0, "warmth_db": 0.0},
    "summer_vibes":  {"lpf": 13000, "bits": 13, "room": 0.3, "wet": 0.16, "wobble_depth": 0.11, "compress_ratio": 2.0, "vinyl": 0.05, "presence_db": 0.0, "warmth_db": 0.0},
    "bedroom_pop":   {"lpf": 13000, "bits": 13, "room": 0.35,"wet": 0.18, "wobble_depth": 0.13, "compress_ratio": 2.2, "vinyl": 0.06, "presence_db": 0.0, "warmth_db": 0.0},
    "city_pop":      {"lpf": 13000, "bits": 13, "room": 0.3, "wet": 0.16, "wobble_depth": 0.12, "compress_ratio": 2.2, "vinyl": 0.06, "presence_db": 0.0, "warmth_db": 0.0},
    "study_lofi":    {"lpf": 11000, "bits": 12, "room": 0.38,"wet": 0.20, "wobble_depth": 0.14, "compress_ratio": 2.5, "vinyl": 0.09, "presence_db": 0.0, "warmth_db": 0.0},
    "piano_lofi":    {"lpf": 14000, "bits": 14, "room": 0.45,"wet": 0.25, "wobble_depth": 0.08, "compress_ratio": 1.8, "vinyl": 0.04, "presence_db": 0.0, "warmth_db": 0.0},
    "lofi_classical":{"lpf": 15000, "bits": 15, "room": 0.50,"wet": 0.28, "wobble_depth": 0.06, "compress_ratio": 1.6, "vinyl": 0.03, "presence_db": 0.0, "warmth_db": 0.0},
    "lofi_drill":    {"lpf": 7200,  "bits": 8,  "room": 0.35,"wet": 0.20, "wobble_depth": 0.28, "compress_ratio": 4.2, "vinyl": 0.20, "presence_db": -1.5, "warmth_db": 1.5},
    "lofi_world":    {"lpf": 10500, "bits": 12, "room": 0.42,"wet": 0.24, "wobble_depth": 0.16, "compress_ratio": 2.6, "vinyl": 0.09, "presence_db": 0.0, "warmth_db": 0.0},
    "sleep_lofi":    {"lpf": 7000,  "bits": 10, "room": 0.75,"wet": 0.45, "wobble_depth": 0.10, "compress_ratio": 1.8, "vinyl": 0.04, "presence_db": 0.0, "warmth_db": 0.0},
    "lofi_garage":   {"lpf": 10000, "bits": 11, "room": 0.4, "wet": 0.22, "wobble_depth": 0.14, "compress_ratio": 3.2, "vinyl": 0.08, "presence_db": 0.0, "warmth_db": 0.0},
    "lofi_synthwave":{"lpf": 13500, "bits": 13, "room": 0.5, "wet": 0.28, "wobble_depth": 0.08, "compress_ratio": 3.5, "vinyl": 0.05, "presence_db": 0.0, "warmth_db": 0.0},
}

# ─── lofi_fx._IR_GENRES / _SIDECHAIN_DUCK_GENRES (pre-refactor literal) ─────
# Grew by 5 (chillhop, hip_hop_lofi, lo_fi_funk, lofi_drill, lofi_phonk) when
# research/theory/mixing-texture.md item 7 (2026-08-26) gave those genres
# use_ir_reverb: true so they can use the new procedural plate IR.
EXPECTED_IR_GENRES = {"lofi_jazz", "jazz_cafe", "piano_lofi", "lofi_classical", "bossa_lofi", "neo_soul", "lofi_world",
                      "sleep_lofi", "lofi_synthwave", "chillhop", "hip_hop_lofi", "lo_fi_funk", "lofi_drill", "lofi_phonk"}
EXPECTED_SIDECHAIN_DUCK_GENRES = {"lofi_house", "lo_fi_funk", "hip_hop_lofi", "chillhop", "lofi_drill",
                                  "lofi_garage", "lofi_synthwave"}


def test_subgenre_config_matches_pre_refactor_literal():
    assert genre_presets.build_subgenre_config() == EXPECTED_SUBGENRE_CONFIG


def test_swing_range_matches_pre_refactor_literal():
    assert genre_presets.build_swing_range() == EXPECTED_SWING_RANGE


def test_cozy_subgenres_matches_pre_refactor_literal():
    result = genre_presets.build_cozy_subgenres()
    assert isinstance(result, frozenset)
    assert result == EXPECTED_COZY_SUBGENRES


def test_subgenre_texture_matches_pre_refactor_literal():
    assert genre_presets.build_subgenre_texture() == EXPECTED_SUBGENRE_TEXTURE


def test_subgenre_drum_kits_matches_pre_refactor_literal():
    assert genre_presets.build_subgenre_drum_kits() == EXPECTED_SUBGENRE_DRUM_KITS


def test_form_overrides_matches_pre_refactor_literal():
    assert genre_presets.build_form_overrides() == EXPECTED_FORM_BY_SUBGENRE


def test_genre_fx_presets_matches_pre_refactor_literal():
    assert genre_presets.build_genre_fx_presets() == EXPECTED_GENRE_FX_PRESETS


def test_ir_genres_matches_pre_refactor_literal():
    assert genre_presets.build_ir_genres() == EXPECTED_IR_GENRES


def test_sidechain_duck_genres_matches_pre_refactor_literal():
    assert genre_presets.build_sidechain_duck_genres() == EXPECTED_SIDECHAIN_DUCK_GENRES


def test_subgenre_pat_matches_pre_refactor_literal():
    # drum_sampler._SUBGENRE_PAT mapped subgenre -> one of 5 named pattern-
    # template dicts by direct object reference. build_subgenre_pat() takes
    # a name->object registry and must reproduce that exact mapping.
    standard, boom_bap, trap808, jazz, dusty = object(), object(), object(), object(), object()
    registry = {
        "standard": standard, "boom_bap": boom_bap, "808_trap": trap808,
        "jazz": jazz, "dusty": dusty,
    }
    expected = {
        "hip_hop_lofi": boom_bap, "nujabes": boom_bap, "dark_lofi": boom_bap,
        "chillhop": dusty,        "study_lofi": dusty,
        "lofi_phonk": trap808,    "vaporwave": trap808,   "lofi_drill": trap808,
        "lofi_jazz": jazz,        "jazz_cafe": jazz,
        "bossa_lofi": jazz,       "ambient": jazz,
        "piano_lofi": jazz,       "lofi_classical": jazz,
        "lofi_synthwave": standard,
    }
    result = genre_presets.build_subgenre_pat(registry)
    assert result == expected
    # also confirm identity is preserved (not just equality) since the real
    # call sites pass live dict objects and expect the same object back
    for key, obj in expected.items():
        assert result[key] is obj
