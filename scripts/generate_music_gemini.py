"""
generate_music_gemini.py — v3 (Alive Edition)
==============================================
Every track is unique. Infinite combinations guaranteed by:
  · Groq picks personality (key, progression, bpm, swing, mood, density, energy)
  · Multiple voicings per chord — rotates randomly each hit
  · 4 drum patterns + per-bar mutation + fills at section boundaries
  · Hi-hat 16th-note runs every 4 bars for energy bursts
  · Quiet pad layer (strings) under chords for depth
  · Sparse / dense melody toggle per track
  · Syncopated bass with walking fill option
  · All timing + velocity fully humanized per instrument

Math: 5 keys × 8 progressions × 15 BPMs × 10 swing values
      × 4² drum combos × voicing variants × melody/bass randomness
      = effectively infinite unique tracks
"""

import os, sys, time, random, json, subprocess, tempfile

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

MUSIC_DIR = os.path.join(os.path.dirname(__file__), '..', 'music')
os.makedirs(MUSIC_DIR, exist_ok=True)

_ROOT = os.path.join(os.path.dirname(__file__), '..')
# Prefer MuseScore General (much better instruments than FluidR3_GM) if available
_MUSESCORE_SF = os.path.join(_ROOT, 'assets', 'soundfonts', 'MuseScore_General.sf3')
_DEFAULT_SF   = _MUSESCORE_SF if os.path.exists(_MUSESCORE_SF) else '/usr/share/soundfonts/FluidR3_GM.sf2'
SOUNDFONT = os.getenv('SOUNDFONT', _DEFAULT_SF)
GROQ_KEY  = os.getenv('GROQ_API_KEY')

# Soundfont rotation pool — different timbre every track.
# Checks both project assets/ and system /usr/share/soundfonts/; skips empty files.
_SF_DIR  = os.path.join(_ROOT, 'assets', 'soundfonts')
_SF_POOL: list[str] = []
for _sf_name, _sf_w, _sf_fallback in [
    ('MuseScore_General.sf3', 4, None),                          # best: SF3 quality
    ('GeneralUser_GS.sf2',    3, None),                          # GS, varied kits
    ('FluidR3_GS.sf2',        2, '/usr/share/soundfonts/FluidR3_GS.sf2'),  # GS system SF
    ('FluidR3_GM.sf2',        1, '/usr/share/soundfonts/FluidR3_GM.sf2'),  # GM baseline
]:
    for _candidate in [os.path.join(_SF_DIR, _sf_name), _sf_fallback]:
        if _candidate and os.path.isfile(_candidate) and os.path.getsize(_candidate) > 500_000:
            _SF_POOL.extend([_candidate] * _sf_w)
            break  # use first valid candidate
if not _SF_POOL:
    _SF_POOL = [SOUNDFONT]  # fallback to env/default


def _pick_soundfont() -> str:
    """Pick a random soundfont, weighted towards higher quality."""
    return random.choice(_SF_POOL)

# ─── CONSTANTS ────────────────────────────────────────────────────────────────

PPQN = 480
BAR  = PPQN * 4   # 1920 ticks
S16  = PPQN // 4  # 120 ticks per 16th note

# GM Programs (0-indexed)
GM_RHODES     = 4
GM_EP2        = 5
GM_VIBRAPHONE = 11
GM_BASS       = 32
GM_STRINGS    = 48
GM_WARM_PAD   = 89

# New instruments for genre diversity
GM_MARIMBA        = 12   # summer_vibes, city_pop accent
GM_GUITAR_NYLON   = 24   # bossa_lofi, piano_lofi counter melody
GM_GUITAR_JAZZ    = 26   # lofi_jazz, jazz_cafe comping texture
GM_ORGAN_ROCK     = 17   # neo_soul, lo_fi_funk stabs (drawbar organ)
GM_MUTED_TRUMPET  = 59   # nujabes, jazz_cafe, lofi_jazz fills
GM_CELLO          = 42   # dark_lofi, piano_lofi, ambient pad voice
GM_FLUTE          = 73   # ambient, morning_lofi, bossa_lofi whisper

# ─── SUB-GENRE CONFIG TABLE ───────────────────────────────────────────────────
# Unified per-sub-genre settings — replaces scattered inline dicts.
# 'piano'/'melody': GM program. 'scale': biased pool. 'drum_pats': preferred indices.
# 'bpm': (lo, hi). 'progs': preferred progression indices. 'energy': force or None.

_SUBGENRE_CONFIG = {
    # ── Hip-hop / beat ───────────────────────────────────────────────────────────
    'chillhop':     {'piano': GM_RHODES,    'melody': 0,            'cmelo': GM_WARM_PAD,
                     'scale': ['pent','dorian','natural_minor'],
                     'drum_pats': [0,1,2,13], 'bpm': (76,88), 'energy': None,
                     'progs': [0,1,7,10,11,13,33,38,44,45]},
    'hip_hop_lofi': {'piano': GM_RHODES,    'melody': 0,            'cmelo': GM_ORGAN_ROCK,
                     'scale': ['pent','dorian','mixo','blues'],
                     'drum_pats': [0,2,6,11,14], 'bpm': (78,92), 'energy': None,
                     'progs': [0,1,3,10,11,38,39,45]},
    'lo_fi_funk':   {'piano': GM_EP2,       'melody': 0,            'cmelo': GM_ORGAN_ROCK,
                     'scale': ['mixo','pent','blues'],
                     'drum_pats': [5,8,12,14], 'bpm': (82,96), 'energy': 'high',
                     'progs': [26,27,10,11,3,38,45]},
    'chill_beats':  {'piano': GM_WARM_PAD,  'melody': GM_VIBRAPHONE,'cmelo': GM_WARM_PAD,
                     'scale': ['pent','dorian','natural_minor'],
                     'drum_pats': [1,7,9,10,13], 'bpm': (62,76), 'energy': 'low',
                     'progs': [7,12,13,19,20,33,35,36]},
    'lofi_house':   {'piano': GM_EP2,       'melody': GM_VIBRAPHONE,'cmelo': GM_GUITAR_JAZZ,
                     'scale': ['dorian','pent','major'],
                     'drum_pats': [6,8,11], 'bpm': (88,100), 'energy': 'medium',
                     'progs': [3,0,1,10,33,46]},
    # ── Jazz / soul ───────────────────────────────────────────────────────────────
    'lofi_jazz':    {'piano': GM_EP2,       'melody': GM_VIBRAPHONE,'cmelo': GM_MUTED_TRUMPET,
                     'scale': ['dorian','natural_minor'],
                     'drum_pats': [1,3,10,13], 'bpm': (70,84), 'energy': None,
                     'progs': [2,5,6,28,31,32,33,34,39,40]},
    'jazz_cafe':    {'piano': GM_EP2,       'melody': GM_VIBRAPHONE,'cmelo': GM_MUTED_TRUMPET,
                     'scale': ['dorian','major_pent','major'],
                     'drum_pats': [3,1,10,13], 'bpm': (78,94), 'energy': None,
                     'progs': [2,5,8,26,6,28,31,33,34,45]},
    'nujabes':      {'piano': GM_RHODES,    'melody': GM_VIBRAPHONE,'cmelo': GM_MUTED_TRUMPET,
                     'scale': ['dorian','pent','lydian','natural_minor'],
                     'drum_pats': [1,0,10,14], 'bpm': (80,92), 'energy': None,
                     'progs': [6,2,28,32,37,39,40]},
    'neo_soul':     {'piano': GM_EP2,       'melody': 0,            'cmelo': GM_CELLO,
                     'scale': ['dorian','pent','blues','natural_minor'],
                     'drum_pats': [2,5,8,12], 'bpm': (72,86), 'energy': None,
                     'progs': [10,11,27,38,40,45]},
    'bossa_lofi':   {'piano': GM_VIBRAPHONE,'melody': 0,            'cmelo': GM_GUITAR_NYLON,
                     'scale': ['pent','dorian','major'],
                     'drum_pats': [4,12], 'bpm': (74,88), 'energy': None,
                     'progs': [8,9,29,33,34,44]},
    'lofi_rnb':     {'piano': GM_EP2,       'melody': GM_MUTED_TRUMPET,'cmelo': GM_CELLO,
                     'scale': ['dorian','pent','mixo','blues'],
                     'drum_pats': [2,5,8,12], 'bpm': (70,84), 'energy': None,
                     'progs': [10,11,3,0,6,27,38,40,45]},
    # ── Dark / moody ─────────────────────────────────────────────────────────────
    'dark_lofi':    {'piano': GM_RHODES,    'melody': 0,            'cmelo': GM_CELLO,
                     'scale': ['phryg','pent','natural_minor','harmonic_minor','blues'],
                     'drum_pats': [0,2,5,9,14], 'bpm': (65,80), 'energy': None,
                     'progs': [14,15,3,31,39,41,42,43]},
    'lofi_phonk':   {'piano': GM_RHODES,    'melody': 0,            'cmelo': GM_CELLO,
                     'scale': ['phryg','pent','natural_minor'],
                     'drum_pats': [0,2,5,9,11,14], 'bpm': (65,78), 'energy': None,
                     'progs': [14,15,3,7,41,42,43]},
    'vaporwave':    {'piano': GM_WARM_PAD,  'melody': GM_WARM_PAD,  'cmelo': GM_STRINGS,
                     'scale': ['lydian','major','whole_tone'],
                     'drum_pats': [7,9,11], 'bpm': (58,74), 'energy': 'low',
                     'progs': [12,13,19,7,20,35,37,50]},
    'ambient':      {'piano': GM_WARM_PAD,  'melody': GM_WARM_PAD,  'cmelo': GM_FLUTE,
                     'scale': ['pent','natural_minor','whole_tone'],
                     'drum_pats': [7,9,13], 'bpm': (58,74), 'energy': 'low',
                     'progs': [12,13,7,19,35,36]},
    # ── Cozy / bright ────────────────────────────────────────────────────────────
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
                     'progs': [16,17,22,18,44,46,49]},
    'city_pop':     {'piano': GM_EP2,       'melody': 0,            'cmelo': GM_GUITAR_JAZZ,
                     'scale': ['major_pent','pent','major'],
                     'drum_pats': [0,6,8,12], 'bpm': (78,92), 'energy': None,
                     'progs': [8,4,18,29,44,46,48,49]},
    'study_lofi':   {'piano': GM_RHODES,    'melody': 0,            'cmelo': GM_WARM_PAD,
                     'scale': ['pent','dorian','major_pent','major'],
                     'drum_pats': [0,1,9,13], 'bpm': (74,90), 'energy': 'medium',
                     'progs': [0,1,7,22,16,28,33,35,44,46]},
    # ── Acoustic / classical ─────────────────────────────────────────────────────
    'piano_lofi':   {'piano': GM_EP2,       'melody': GM_VIBRAPHONE,'cmelo': GM_CELLO,
                     'scale': ['major_pent','pent','dorian','major'],
                     'drum_pats': [7,9,13], 'bpm': (66,84), 'energy': 'low',
                     'progs': [22,16,12,7,20,25,35,36,46]},
    'lofi_classical':{'piano': GM_EP2,      'melody': GM_CELLO,     'cmelo': GM_STRINGS,
                     'scale': ['major','lydian','major_pent','harmonic_minor'],
                     'drum_pats': [7,9,13], 'bpm': (58,78), 'energy': 'low',
                     'progs': [16,17,18,22,25,35,46,50]},
}

# Per-genre swing ranges. Heavy hip-hop swings hard (0.72); bossa/classical nearly
# straight (0.52). This alone creates huge perceived variety across the 24 genres.
_SWING_RANGE: dict[str, tuple[float, float]] = {
    'lofi_phonk':    (0.62, 0.73),   # massive trap swing
    'dark_lofi':     (0.62, 0.71),   # heavy laid-back pocket
    'nujabes':       (0.61, 0.69),   # j-dilla-ish moderate-heavy
    'hip_hop_lofi':  (0.61, 0.69),
    'lo_fi_funk':    (0.60, 0.69),   # funky swing
    'neo_soul':      (0.60, 0.68),
    'lofi_rnb':      (0.59, 0.68),
    'lofi_jazz':     (0.58, 0.68),   # jazz swing, variable
    'chillhop':      (0.59, 0.67),
    'chill_beats':   (0.58, 0.66),
    'study_lofi':    (0.58, 0.66),
    'cozy_cafe':     (0.58, 0.66),
    'jazz_cafe':     (0.57, 0.65),
    'bedroom_pop':   (0.58, 0.65),
    'summer_vibes':  (0.59, 0.66),
    'morning_lofi':  (0.57, 0.65),
    'anime_lofi':    (0.57, 0.65),
    'lofi_house':    (0.54, 0.61),   # house = mostly straight
    'city_pop':      (0.55, 0.63),
    'bossa_lofi':    (0.52, 0.60),   # bossa is 8th-note straight
    'piano_lofi':    (0.53, 0.63),
    'lofi_classical':(0.50, 0.57),   # classical straight
    'ambient':       (0.50, 0.60),   # minimal swing
    'vaporwave':     (0.50, 0.60),   # electronic, straight
}
_SWING_DEFAULT = (0.58, 0.68)

# Cozy/bright sub-genres for the channel identity bias (2× base weight in picker)
_COZY_SUBGENRES: frozenset[str] = frozenset({
    "cozy_cafe", "anime_lofi", "summer_vibes", "study_lofi",
    "morning_lofi", "jazz_cafe", "piano_lofi", "bedroom_pop",
    "lofi_rnb", "lofi_classical", "lofi_house", "chillhop",
})

# Per-sub-genre FX biasing. NOTE: no longer consumed anywhere (the in-file apply_lofi_fx()
# that used this was removed in favor of scripts/lofi_fx.py, which has its own separate
# _GENRE_PRESETS). generate_music_v2.py still imports this name but doesn't use it either.
# Left in place pending a follow-up dead-import cleanup pass.
_SUBGENRE_FX = {
    'chillhop':     {'bits': [11,12,13],  'lpf': (9500,12000),  'vinyl_vol': (0.06,0.12),  'tremolo_d': (0.05,0.10)},
    'morning_lofi': {'bits': [12,13,14],  'lpf': (10000,13000), 'vinyl_vol': (0.03,0.08),  'tremolo_d': (0.05,0.10)},
    'hip_hop_lofi': {'bits': [10,11,12],  'lpf': (8500,11000),  'vinyl_vol': (0.08,0.18),  'tremolo_d': (0.04,0.08)},
    'chill_beats':  {'bits': [12,13,14],  'lpf': (10000,13000), 'vinyl_vol': (0.04,0.10),  'tremolo_d': (0.06,0.11)},
    'dark_lofi':    {'bits': [8,9,10],    'lpf': (7000,9500),   'vinyl_vol': (0.12,0.22),  'tremolo_d': (0.08,0.13)},
    'lofi_phonk':   {'bits': [8,9,10],    'lpf': (7000,9000),   'vinyl_vol': (0.15,0.25),  'tremolo_d': (0.09,0.14)},
    'ambient':      {'bits': [12,13,14],  'lpf': (11000,14000), 'vinyl_vol': (0.03,0.06),  'tremolo_d': (0.04,0.08)},
    'city_pop':     {'bits': [12,13,14],  'lpf': (10500,13000), 'vinyl_vol': (0.04,0.08),  'tremolo_d': (0.04,0.08)},
    'nujabes':      {'bits': [10,11,12],  'lpf': (9000,11500),  'vinyl_vol': (0.08,0.16),  'tremolo_d': (0.06,0.11)},
    'lofi_jazz':    {'bits': [11,12,12],  'lpf': (9500,12000),  'vinyl_vol': (0.06,0.14),  'tremolo_d': (0.06,0.10)},
    # Cozy / bright — higher LPF, cleaner bits, less crackle = more "air" in the sound
    'cozy_cafe':    {'bits': [12,13,14],  'lpf': (11000,14000), 'vinyl_vol': (0.03,0.07),  'tremolo_d': (0.04,0.08)},
    'anime_lofi':   {'bits': [12,13,14],  'lpf': (11000,14500), 'vinyl_vol': (0.02,0.06),  'tremolo_d': (0.04,0.08)},
    'summer_vibes': {'bits': [12,13,14],  'lpf': (10500,14000), 'vinyl_vol': (0.04,0.09),  'tremolo_d': (0.05,0.09)},
    'study_lofi':   {'bits': [11,12,13],  'lpf': (9500,12000),  'vinyl_vol': (0.05,0.12),  'tremolo_d': (0.05,0.10)},
    'jazz_cafe':    {'bits': [11,12,12],  'lpf': (9500,12500),  'vinyl_vol': (0.05,0.12),  'tremolo_d': (0.05,0.09)},
    'piano_lofi':   {'bits': [13,14,14],  'lpf': (12000,15000), 'vinyl_vol': (0.02,0.05),  'tremolo_d': (0.03,0.07)},
    'lo_fi_funk':   {'bits': [10,11,12],  'lpf': (9000,11500),  'vinyl_vol': (0.10,0.18),  'tremolo_d': (0.06,0.10)},
    # Acoustic-instrument genres — cleaner FX preserves natural timbre
    'bossa_lofi':   {'bits': [13,14,14],  'lpf': (12000,15500), 'vinyl_vol': (0.03,0.08),  'tremolo_d': (0.03,0.07)},
    'neo_soul':     {'bits': [11,12,13],  'lpf': (10000,13000), 'vinyl_vol': (0.06,0.12),  'tremolo_d': (0.05,0.09)},
    # New subgenres
    'vaporwave':    {'bits': [9,10,11],   'lpf': (7500,9500),   'vinyl_vol': (0.07,0.14),  'tremolo_d': (0.08,0.13)},
    'lofi_house':   {'bits': [12,13,13],  'lpf': (10500,13000), 'vinyl_vol': (0.04,0.09),  'tremolo_d': (0.05,0.09)},
    'lofi_classical':{'bits': [14,14,15], 'lpf': (13000,16000), 'vinyl_vol': (0.02,0.05),  'tremolo_d': (0.03,0.06)},
    'bedroom_pop':  {'bits': [12,13,14],  'lpf': (11500,14000), 'vinyl_vol': (0.03,0.07),  'tremolo_d': (0.04,0.08)},
    'lofi_rnb':     {'bits': [11,12,12],  'lpf': (10000,12500), 'vinyl_vol': (0.05,0.11),  'tremolo_d': (0.05,0.09)},
}

# GM Drum notes (channel 9)
KICK  = 36
SNARE = 38
RIM   = 37
CHH   = 42
OHH   = 46
RIDE  = 51
CRASH = 49

# ─── MULTIPLE VOICINGS PER CHORD ─────────────────────────────────────────────
# Each chord has 3-4 voicing options. build_chords picks randomly each time.
# This alone guarantees no two bars sound identical.

VOICING_OPTIONS = {
    'Am7':   [[57,60,64,67], [60,64,67,69], [52,57,64,67], [57,60,64,67,71], [64,67,69,72]],
    'Am9':   [[57,60,64,67,71], [60,64,67,71], [52,60,64,71], [57,64,69,71]],
    'Dm7':   [[50,53,57,60], [53,57,60,62], [50,53,57,60,64], [45,50,57,60], [53,57,62,65]],
    'Dm9':   [[50,53,57,60,64], [53,57,60,64], [50,57,60,64], [53,60,62,65]],
    'Em7':   [[52,55,59,62], [55,59,62,64], [52,59,62,67], [55,59,64,67]],
    'Gm7':   [[55,58,62,65], [58,62,65,67], [55,62,65,70], [50,55,62,65], [58,65,67,70]],
    'Gm9':   [[55,58,62,65,69], [58,62,65,69], [55,62,69,70], [50,62,65,69], [58,65,69,74]],
    'Cm7':   [[48,51,55,58], [51,55,58,60], [48,55,58,63], [44,48,55,58], [51,58,60,63]],
    'Fm7':   [[53,56,60,63], [56,60,63,65], [53,60,63,68], [48,53,60,63], [56,63,65,68]],
    'Bm7b5': [[59,62,65,69], [62,65,69,71], [59,65,69,74], [62,65,71,74]],
    'Cmaj7': [[60,64,67,71], [64,67,71,72], [55,60,67,71], [60,67,71,76], [64,71,72,76]],
    'Cmaj9': [[60,64,67,71,74], [64,67,71,74], [60,67,71,74], [55,67,71,74]],
    'Fmaj7': [[53,57,60,64], [57,60,64,65], [53,60,64,69], [57,64,65,69], [53,60,69,72]],
    'Fmaj9': [[53,57,60,64,67], [57,60,64,67], [53,60,67,69], [57,64,67,72], [53,67,69,72]],
    'Fmaj7s':[[53,57,64,71], [57,64,71,72], [53,64,69,71]],  # Lydian #11
    'Gmaj7': [[55,59,62,66], [59,62,66,67], [55,62,66,71], [59,66,67,71], [55,62,71,74]],
    'Bbmaj7':[[58,62,65,69], [62,65,69,70], [58,65,69,74], [62,69,70,74]],
    'Ebmaj7':[[63,67,70,74], [67,70,74,75], [63,70,74,79], [67,74,75,79]],
    'G7':    [[55,59,62,65], [59,62,65,67], [55,62,65,71], [59,65,67,71]],
    'G7b9':  [[55,59,65,68], [59,65,68,71], [55,65,68,71]],
    'E7':    [[52,56,59,62], [56,59,62,64], [52,59,62,68], [56,62,64,68]],
    'E7b9':  [[52,56,65,68], [56,65,68,71], [52,65,68,74]],
    'C7':    [[48,52,55,58], [52,55,58,60], [48,55,58,63], [52,58,60,63]],
    'Bb7':   [[58,62,65,68], [62,65,68,70], [58,65,68,74], [62,68,70,74]],
    'D7':    [[50,54,57,60], [54,57,60,62], [50,57,60,66], [54,60,62,66]],
    'D9':    [[50,54,57,60,64], [54,57,60,64], [50,57,60,64,69]],
    # Secondary dominant voicings used in new progressions
    'F7':    [[53,57,60,63], [57,60,63,65], [53,60,63,68], [57,63,65,68]],
    'A7':    [[57,61,64,67], [61,64,67,69], [57,64,67,73], [61,67,69,73]],
}

# Bass root notes (octave 2)
BASS_ROOTS = {
    'Am7':45,'Am9':45,'Dm7':38,'Dm9':38,'Em7':40,'Gm7':43,'Gm9':43,
    'Cm7':48,'Fm7':41,'Bm7b5':47,'Cmaj7':48,'Cmaj9':48,'Fmaj7':41,
    'Fmaj9':41,'Fmaj7s':41,'Gmaj7':43,'Bbmaj7':46,'Ebmaj7':51,
    'G7':43,'G7b9':43,'E7':40,'E7b9':40,'C7':48,'Bb7':46,
    'D7':38,'D9':38,
    'F7':41,'A7':45,
}

# Guide tone offsets from root: (3rd_semitones, 7th_semitones)
# 3rd defines major/minor quality; 7th defines chord type (maj7 vs dom7 vs min7)
_GUIDE_TONES = {
    'Am7':   (3, 10), 'Am9':   (3, 10),
    'Dm7':   (3, 10), 'Dm9':   (3, 10),
    'Em7':   (3, 10), 'Gm7':   (3, 10), 'Gm9':   (3, 10),
    'Cm7':   (3, 10), 'Fm7':   (3, 10), 'Bm7b5': (3, 10),
    'Cmaj7': (4, 11), 'Cmaj9': (4, 11),
    'Fmaj7': (4, 11), 'Fmaj9': (4, 11), 'Fmaj7s': (4, 11),
    'Gmaj7': (4, 11), 'Bbmaj7': (4, 11), 'Ebmaj7': (4, 11),
    'G7':    (4, 10), 'G7b9':  (4, 10),
    'E7':    (4, 10), 'E7b9':  (4, 10),
    'C7':    (4, 10), 'Bb7':   (4, 10),
    'D7':    (4, 10), 'D9':    (4, 10),
    'F7':    (4, 10), 'A7':    (4, 10),
}

# ─── CHORD PROGRESSIONS ───────────────────────────────────────────────────────

PROGRESSIONS = [
    [('Am7',2),('Gmaj7',2),('Fmaj7',2),('Gmaj7',2)],   # 0  classic lo-fi
    [('Am7',2),('Fmaj7',2),('Cmaj7',2),('G7',2)],       # 1  study session
    [('Bm7b5',1),('E7b9',1),('Am7',2)],                 # 2  jazz ii-V-i
    [('Am7',2),('Dm7',2),('G7',2),('Cmaj7',2)],         # 3  modal minor cycle
    [('Fmaj7',2),('G7',2),('Am7',2),('Em7',2)],         # 4  resolution arc
    [('Dm9',2),('Gm7',2),('Cmaj9',2),('Fmaj9',2)],      # 5  deep jazz Dm
    [('Am9',2),('Em7',2),('Fmaj7s',2),('G7b9',2)],      # 6  Nujabes / Lydian
    [('Am7',4),('Fmaj7',4)],                             # 7  minimal vamp
    # Bossa nova / city pop influenced
    [('Fmaj9',2),('Em7',2),('Ebmaj7',2),('Dm9',2)],     # 8  descending city pop
    [('Cmaj9',2),('Fmaj9',2),('Bb7',2),('Ebmaj7',2)],   # 9  bossa-jazz cycle
    # Neo-soul / R&B tinged
    [('Am7',1),('G7',1),('Fmaj7',1),('E7b9',1)],        # 10 neo-soul quarter turns
    [('Dm9',2),('Am9',2),('Gm9',2),('Cmaj9',2)],        # 11 neo-soul sus cycle
    # Modal / ambient
    [('Cmaj7',3),('Fmaj9',1)],                           # 12 ambient slow drift
    [('Am7',2),('Dm9',2),('Em7',2),('Am7',2)],           # 13 cycling Dorian Am
    # Dark / melancholic
    [('Cm7',2),('Fm7',2),('Bbmaj7',2),('Gm7',2)],       # 14 dark Cm cycle
    [('Gm7',2),('Fmaj7',2),('Ebmaj7',2),('Cm7',2)],     # 15 dark descending
    # Morning / bright major progressions
    [('Cmaj9',2),('Am9',2),('Fmaj9',2),('G7',2)],       # 16 morning I-vi-IV-V in C
    [('Fmaj9',2),('Cmaj9',2),('Am9',2),('Gmaj7',2)],    # 17 floating morning major
    [('Gmaj7',2),('Em7',2),('Am9',2),('Fmaj7',2)],      # 18 G major arc (I-vi-ii-IV)
    # Chill vamps
    [('Am9',4),('Cmaj9',4)],                             # 19 chill 2-chord vamp
    [('Fmaj9',2),('Em7',2),('Dm9',2),('Cmaj9',2)],      # 20 descending chill IV-iii-ii-I
    # Bright / cozy major progressions
    [('Fmaj9',2),('Gmaj7',2),('Am9',2),('Cmaj9',2)],    # 21 IV-V-vi-I uplifting
    [('Cmaj9',2),('Gmaj7',2),('Am9',2),('Fmaj9',2)],    # 22 I-V-vi-IV (iconic cozy pop loop)
    [('Gmaj7',2),('Cmaj9',2),('Fmaj9',2),('Cmaj9',2)],  # 23 V-I-IV-I resolution arc
    [('Am9',1),('Gmaj7',1),('Fmaj9',1),('Cmaj9',1)],    # 24 quick major turn (quarter note chords)
    [('Cmaj9',2),('Em7',2),('Fmaj9',2),('Gmaj7',2)],    # 25 I-iii-IV-V warm major build
    # Funk / soul
    [('Dm9',1),('G7',1),('Cmaj9',1),('Fmaj9',1)],       # 26 ii-V-I-IV jazz-funk turn
    [('Am9',2),('Fmaj9',2),('G7',2),('Am9',2)],          # 27 neo-soul groove vamp
    # Jazz major turnarounds (C/G/F major key contexts)
    [('Cmaj7',2),('Am9',2),('Dm9',2),('G7',2)],          # 28 I-vi-ii-V jazz (C major)
    [('Fmaj9',2),('Em7',2),('Am9',2),('D7',2)],           # 29 IV-iii-vi-V (G major arc)
    [('Gm9',2),('Cm7',2),('Fmaj9',2),('Bbmaj7',2)],      # 30 minor gospel cycle (F context)
    # Extended jazz cycles
    [('Fm7',2),('Bb7',2),('Ebmaj7',2),('Cm7',2)],        # 31 Cm/Fm jazz cycle (European)
    [('Bm7b5',1),('E7b9',1),('Am7',2),('D7',2)],          # 32 extended ii-V-i with deceptive
    [('Dm9',1),('G7',1),('Cmaj9',1),('Am9',1)],           # 33 ii-V-I-vi quick rotation
    [('Gm9',2),('C7',2),('Fmaj9',2),('Ebmaj7',2)],        # 34 Gm-C7-Fmaj9 reharmonized
    # Modal / minimal drifts
    [('Fmaj9',4),('Cmaj9',4)],                             # 35 2-chord Lydian drift (meditative)
    [('Am7',3),('Cmaj9',1)],                               # 36 ultra-minimal Am vamp
    [('Am9',2),('Fmaj7s',2),('Gmaj7',2),('Em7',2)],       # 37 Lydian floating arc
    # Soul / funk depth
    [('Dm9',2),('Am9',2),('Fmaj9',2),('G7',2)],           # 38 Dm funk cycle
    [('Am7',1),('Bm7b5',1),('E7b9',1),('Am7',1)],         # 39 minor with tritone sub
    [('Fmaj9',2),('Em7',2),('Am9',2),('Dm9',2)],          # 40 IV-iii-vi-ii descending soul
    # Dark minor vamps
    [('Cm7',4),('Gm7',4)],                                 # 41 minimal dark Cm vamp
    [('Gm7',2),('Cm7',2),('Bbmaj7',2),('Ebmaj7',2)],      # 42 Gm gospel/soul cycle
    [('Am7',2),('G7',1),('Fmaj7',1),('E7',2),('Am7',2)],  # 43 flamenco descent E7 resolve
    # Bright round-the-clock major
    [('Gmaj7',2),('Am9',2),('Cmaj9',2),('Fmaj9',2)],      # 44 G major round
    [('Fmaj9',1),('Em7',1),('Am9',1),('D7',1)],            # 45 quick 4-chord IV-iii-vi-V
    [('Cmaj9',2),('Fmaj9',2),('Gmaj7',2),('Am9',2)],       # 46 I-IV-V-vi in C
    [('Bbmaj7',2),('Gm9',2),('Cm7',2),('Ebmaj7',2)],       # 47 Bb major jazz swing
    # City pop / modern Japanese
    [('Fmaj9',2),('Gmaj7',2),('Em7',2),('Am9',2)],         # 48 IV-V-iii-vi city pop
    [('Cmaj9',2),('Em7',2),('Gmaj7',1),('Am9',1)],          # 49 I-iii-V-vi city pop
    [('Ebmaj7',2),('Bbmaj7',2),('Gm7',2),('Cm7',2)],        # 50 Eb warm jazz cycle
]

# Secondary dominant / tritone substitutions — applied by maybe_sub_chord()
# key = chord being approached; value = (substitute_chord, probability)
_SEC_DOM_SUBS = {
    'Fmaj7':  ('C7',   0.15),   # C7 → Fmaj7 (V7/IV)
    'Fmaj9':  ('C7',   0.15),
    'Am7':    ('E7',   0.12),   # E7 → Am7 (V7/vi)
    'Am9':    ('E7',   0.12),
    'Cmaj7':  ('G7',   0.10),   # G7 → Cmaj7 (V7/I)
    'Cmaj9':  ('G7',   0.10),
    'G7':     ('Bb7',  0.08),   # Bb7 = tritone sub for G7 (shares 3rd/7th enharmonically)
    'G7b9':   ('Bb7',  0.08),
    'Ebmaj7': ('Bb7',  0.10),   # Bb7 → Ebmaj7 (V7/I in Eb)
    'Gm7':    ('D7',   0.10),   # D7 → Gm7 (V7/iv)
    'Gm9':    ('D7',   0.10),
    'Cm7':    ('G7',   0.10),   # G7 → Cm7 (V7/iv in Fm context)
    'Dm7':    ('A7',   0.09),   # A7 → Dm7 (V7/ii)
    'Dm9':    ('A7',   0.09),
    'Bbmaj7': ('F7',   0.09),   # F7 → Bbmaj7 (V7/I in Bb)
}

def maybe_sub_chord(chord_name, position_in_prog):
    """Occasionally replace chord with secondary dominant or tritone sub.
    Never subs position 0 (preserves tonic feel at start of progression)."""
    if position_in_prog == 0:
        return chord_name
    sub_info = _SEC_DOM_SUBS.get(chord_name)
    if sub_info and random.random() < sub_info[1]:
        return sub_info[0]
    return chord_name

# ─── EUCLIDEAN RHYTHM (Bjorklund/Toussaint) ──────────────────────────────────

def _bjorklund(k, n):
    """Euclidean rhythm E(k,n): distribute k onsets evenly over n steps."""
    pattern, level = [], 0
    for _ in range(n):
        level += k
        if level >= n:
            level -= n
            pattern.append(1)
        else:
            pattern.append(0)
    # Rotate so first onset lands on step 0
    if 1 in pattern:
        first = pattern.index(1)
        pattern = pattern[first:] + pattern[:first]
    return pattern

# Pre-computed euclidean hi-hat patterns (1 = onset, 0 = rest, 16 steps)
_EUCL_HATS = {
    'tresillo':  (_bjorklund(3,  8) * 2),   # [1,0,0,1,0,0,1,0] × 2 = 16 steps
    'cinquillo': (_bjorklund(5,  8) * 2),   # dense Cuban feel
    'bossa16':   (_bjorklund(3, 16)),        # sparse bossa
    'clave':     (_bjorklund(5, 16)),        # clave approximation
}

_DRUM_ENERGY_TO_FLOAT = {'low': 0.25, 'medium': 0.55, 'high': 0.85}


def generate_euclidean_drum_pattern(energy: float, complexity: float = 0.5,
                                     seed: int | None = None) -> dict:
    """
    Generate a full 16-step drum pattern parametrically via Bjorklund's
    Euclidean-rhythm algorithm, generalizing the 4 fixed _EUCL_HATS presets
    (which only ever cover the hi-hat, as a rare fixed-pattern override) into
    a continuous family driven by energy/complexity floats in [0,1]. Returns
    a dict in the same {DRUM_NOTE: [16 velocities]} format as DRUM_PATTERNS
    entries, so it's a drop-in alternative to a curated pattern.
    """
    rng = random.Random(seed) if seed is not None else random
    energy = max(0.0, min(1.0, energy))
    complexity = max(0.0, min(1.0, complexity))
    n = 16

    # Kick onset count scales with energy: sparse/grounded at low energy,
    # busier and more driving at high energy. +-1 jitter so repeated calls at
    # the same energy/complexity still produce genuinely different patterns
    # rather than a deterministic 1:1 mapping.
    k_kick = max(2, min(6, round(2 + energy * 4) + rng.choice([-1, 0, 0, 1])))
    kick_pat = _bjorklund(k_kick, n)

    # Snare: rotation-search all 16 rotations of a Euclidean pattern and keep
    # whichever maximizes overlap with the backbeat (steps 4, 12) — this keeps
    # the genre-defining backbeat feel even though the pattern is Euclidean-derived.
    k_snare = (2 if energy < 0.5 else 3) + rng.choice([0, 0, 1])
    snare_base = _bjorklund(k_snare, n)
    backbeat = {4, 12}
    best_rot, best_score = snare_base, -1
    for r in range(n):
        rotated = snare_base[r:] + snare_base[:r]
        score = sum(1 for step in backbeat if rotated[step])
        if score > best_score:
            best_rot, best_score = rotated, score
    snare_pat = best_rot

    # Hats/rim: onset density scales with complexity.
    k_chh = max(5, min(11, round(5 + complexity * 6) + rng.choice([-1, 0, 0, 1])))
    chh_pat = _bjorklund(k_chh, n)
    k_ohh = max(1, round(2 + energy * 2) + rng.choice([-1, 0, 0]))
    ohh_pat = _bjorklund(max(1, k_ohh), n)
    k_rim = max(0, round(complexity * 3) + rng.choice([-1, 0, 1]))
    rim_pat = _bjorklund(k_rim, n) if k_rim > 0 else [0] * n

    def _velocities(onsets: list[int], base_vel: int, accent_vel: int) -> list[int]:
        """Inter-onset-interval weighting: an onset preceded by a longer gap
        reads as perceptually stronger (Toussaint's metric-complexity idea),
        so give it proportionally more velocity than a densely-packed onset,
        instead of a flat velocity for every hit."""
        vels = [0] * n
        onset_steps = [i for i, on in enumerate(onsets) if on]
        if not onset_steps:
            return vels
        for idx, step in enumerate(onset_steps):
            prev_step = onset_steps[idx - 1] if idx > 0 else onset_steps[-1] - n
            gap = step - prev_step
            gap_frac = max(0.0, min(1.0, gap / (n / 2)))
            vels[step] = int(base_vel + gap_frac * (accent_vel - base_vel))
        return vels

    return {
        KICK:  _velocities(kick_pat,  60, 95),
        SNARE: _velocities(snare_pat, 65, 90),
        CHH:   _velocities(chh_pat,   40, 72),
        OHH:   _velocities(ohh_pat,   45, 70),
        RIM:   _velocities(rim_pat,   28, 42),
    }


# ─── DRUM PATTERNS (16-step) ──────────────────────────────────────────────────

DRUM_PATTERNS = [
    # A: Classic lo-fi — 2-and-4 snare, swung hats
    {KICK: [90,0,0,0,  0,0,78,0,  0,0,0,0,  0,0,72,0],
     SNARE:[0,0,0,0,  85,0,0,0,  0,0,0,0,  88,0,0,0],
     RIM:  [0,0,0,0,  0,0,0,0,  0,0,36,0,  0,0,0,42],
     CHH:  [72,0,50,0,70,0,50,0,74,0,48,0,70,0,0,0],
     OHH:  [0,0,0,0,  0,0,0,0,  0,0,0,0,  0,0,70,0]},
    # B: Nujabes — sparse kick, ghost snares, steady hats
    {KICK: [92,0,0,0,  0,0,0,0,  0,0,80,0,  0,0,0,0],
     SNARE:[0,0,0,0,  88,0,0,38,  0,0,0,0,  90,0,35,0],
     RIM:  [0]*16,
     CHH:  [75,0,50,0,72,0,48,0,75,0,50,0,72,0,48,0],
     OHH:  [0]*16},
    # C: J Dilla drunk — off-grid kick, wonky hats
    {KICK: [88,0,0,22,  0,0,82,0,  0,0,0,0,  0,75,0,0],
     SNARE:[0,0,0,0,  85,0,0,0,  36,0,0,0,  90,0,0,32],
     RIM:  [0]*16,
     CHH:  [70,0,62,65,0,58,0,55,68,0,60,0,65,68,0,58],
     OHH:  [0]*16},
    # D: Minimal jazz (ride) — very open, brush feel
    {KICK: [88,0,0,0,  0,0,0,0,  82,0,0,0,  0,0,0,0],
     SNARE:[0,0,0,0,  0,0,0,0,  0,0,0,0,  82,0,0,0],
     RIM:  [0]*16,
     CHH:  [0]*16,
     OHH:  [0]*16,
     RIDE: [62,0,52,0,58,0,50,0,62,0,52,0,58,0,50,0]},
    # E: Bossa nova influenced — syncopated kick, rim cross-stick
    {KICK: [85,0,0,0,  0,0,75,0,  0,0,85,0,  0,0,0,0],
     SNARE:[0]*16,
     RIM:  [0,0,0,0,  72,0,0,0,  0,0,0,0,  68,0,32,0],
     CHH:  [62,0,55,0,58,0,52,0,60,0,52,0,55,0,48,0],
     OHH:  [0,0,0,0,  0,68,0,0,  0,0,0,0,  0,65,0,0]},
    # F: Neo-soul / thick — double kick, heavy snare, open hats
    {KICK: [92,0,0,0,  78,0,0,0,  0,0,88,0,  0,82,0,0],
     SNARE:[0,0,0,0,  90,0,0,38,  0,0,0,0,  92,0,42,0],
     RIM:  [0]*16,
     CHH:  [60,55,52,0,58,50,0,55,60,52,0,55,58,0,52,0],
     OHH:  [0,0,0,0,  0,0,72,0,  0,0,0,0,  0,0,68,0]},
    # G: Hip Hop Tight — hard kicks 1+3, punchy snare 2+4, 16th hats, minimal swing
    {KICK: [95,0,0,0,  0,0,0,0,  92,0,0,0,  0,0,0,0],
     SNARE:[0,0,0,0,  90,0,0,0,  0,0,0,0,  88,0,0,0],
     CHH:  [65,0,60,0,62,0,58,0,65,0,60,0,62,0,58,0],
     OHH:  [0,0,0,0,  0,0,0,48,  0,0,0,0,  0,0,0,48],
     RIM:  [0]*16},
    # H: Chill Sparse — ghost kick beat 1, very soft snare bar 4, 8th hats, breathing space
    {KICK: [72,0,0,0,  0,0,0,0,  0,0,0,0,  0,0,0,0],
     SNARE:[0,0,0,0,  0,0,0,0,  0,0,0,0,  52,0,0,0],
     CHH:  [50,0,0,45,0,0,46,0,50,0,0,44,0,0,46,0],
     OHH:  [0,0,0,0,  0,0,0,0,  0,0,0,0,  0,62,0,0],
     RIM:  [0]*16},
    # I: Funk Groove — syncopated kick, ghost snares, upbeat 16th hats, open hat accents
    {KICK: [92,0,0,0,  0,80,0,0,  85,0,0,0,  0,0,78,0],
     SNARE:[0,0,0,30,  88,0,0,32,  0,0,30,0,  90,0,35,0],
     CHH:  [70,60,65,0,68,62,0,60,70,62,65,0,68,0,62,58],
     OHH:  [0,0,0,0,  0,0,75,0,  0,0,0,0,  0,72,0,0],
     RIM:  [0]*16},
    # J: Half-time lo-fi — snare ONLY on beat 3 (step 8), very spacious feel
    # Most relaxed pattern: wide-open pocket, perfect for piano_lofi / ambient / chill_beats
    {KICK: [88,0,0,0,  0,0,0,0,  0,0,60,0,  0,0,0,0],
     SNARE:[0,0,0,0,  0,0,0,0,  85,0,0,0,  0,0,0,0],
     RIM:  [0,0,0,0,  32,0,0,0,  0,0,0,0,  0,0,28,0],
     CHH:  [52,0,44,0,48,0,44,0,50,0,44,0,46,0,42,0],
     OHH:  [0,0,0,0,  0,0,58,0,  0,0,0,0,  0,0,55,0]},
    # K: Brushed jazz — ride-led, ultra-low velocity kick/snare, true jazz trio feel
    {KICK: [55,0,0,0,  0,0,0,0,  42,0,0,0,  0,0,0,0],
     SNARE:[0,0,0,0,  38,0,0,22,  0,0,0,0,  40,0,25,0],
     RIM:  [0,0,22,0,  0,0,18,0,  0,0,22,0,  0,0,18,0],
     CHH:  [0]*16,
     RIDE: [52,0,42,0,48,0,40,0,50,0,42,0,48,0,40,0],
     OHH:  [0,0,0,0,  0,52,0,0,  0,0,0,0,  0,50,0,0]},
    # L: Trap lo-fi half-time — huge kick beat 1, snare on 3 only, rapid trap hat rolls
    {KICK: [95,0,0,0,  0,0,0,0,  0,0,0,0,  0,0,0,0],
     SNARE:[0,0,0,0,  0,0,0,0,  90,0,0,0,  0,0,42,0],
     CHH:  [62,60,62,60,60,62,58,62,60,62,60,60,62,58,60,62],
     OHH:  [0,0,0,0,  0,0,0,52,  0,0,0,0,  0,0,0,48],
     RIM:  [0]*16},
    # M: Afrobeat-inflected — 3+3+2 rhythmic grouping, syncopated snare
    {KICK: [90,0,0,85,  0,0,80,0,  0,82,0,0,  80,0,0,0],
     SNARE:[0,0,0,0,  82,0,0,0,  0,0,80,0,  0,88,0,0],
     RIM:  [0,0,35,0,  0,0,0,40,  0,0,0,35,  0,0,0,0],
     CHH:  [65,0,58,0,62,0,55,0,65,0,58,0,62,0,55,0],
     OHH:  [0,0,0,0,  0,70,0,0,  0,0,0,0,  0,65,0,0]},
    # N: Floating jazz duo — ultra sparse, ride-led, maximum breathing room
    {KICK: [52,0,0,0,  0,0,0,0,  0,0,42,0,  0,0,0,0],
     SNARE:[0]*16,
     RIM:  [0,0,0,30,  0,55,0,0,  0,0,0,28,  0,50,0,0],
     CHH:  [0]*16,
     RIDE: [58,0,48,0,52,0,44,0,58,0,48,0,52,0,44,50],
     OHH:  [0,0,0,0,  0,62,0,0,  0,0,0,0,  0,0,58,0]},
    # O: Broken beat — unexpected snare placement, fractured pocket (Squarepusher-lite)
    {KICK: [90,0,0,0,  0,0,88,0,  0,82,0,0,  0,0,0,78],
     SNARE:[0,0,0,0,  0,85,0,0,  0,0,0,88,  0,0,82,0],
     CHH:  [68,0,58,62,0,55,0,60,65,0,55,0,60,58,0,52],
     OHH:  [0,0,0,0,  72,0,0,0,  0,0,0,0,  68,0,0,0],
     RIM:  [0]*16},
]

# Drum fills (1 bar of 16 steps — fire at last bar of a section)
DRUM_FILLS = [
    # Fill A: kick/snare run into next section
    {KICK: [0,0,0,0,  88,0,0,0,  85,0,90,0,  92,0,95,0],
     SNARE:[0,0,0,0,  0,80,0,78,  0,82,0,85,  88,90,92,95],
     CHH:  [60,55,52,50,55,52,50,48,55,50,48,45,50,48,45,42]},
    # Fill B: hat roll
    {CHH:  [75,72,70,68,72,70,68,65,70,68,65,62,68,65,62,60],
     KICK: [88,0,0,0,  0,0,0,0,  0,0,0,0,  0,0,0,90],
     SNARE:[0]*16},
    # Fill C: ghost snare build
    {SNARE:[25,0,30,0, 35,0,40,0, 50,0,60,0, 80,85,90,95],
     KICK: [88,0,0,0,  0,0,0,0,  82,0,0,0,  0,0,0,0],
     CHH:  [60,0,55,0,58,0,52,0,55,0,50,0,52,0,48,0]},
]

# ─── SCALES / KEYS ────────────────────────────────────────────────────────────

KEY_ROOTS = {
    # Minor keys
    'Am': 57,   # A minor  — the classic lofi anchor
    'Dm': 62,   # D minor  — melancholic, jazz-adjacent
    'Em': 64,   # E minor  — atmospheric, emotional
    'Gm': 67,   # G minor  — soul, deep
    'Cm': 60,   # C minor  — dark, cinematic
    'F#m': 66,  # F# minor — dark electronic, modern lofi
    'Bm':  71,  # B minor  — ethereal, nujabes territory
    'Ebm': 63,  # Eb minor — neo-soul depth, jazz standard
    # Major keys
    'C':  60,   # C major  — morning_lofi, cozy_cafe, anime_lofi
    'G':  55,   # G major  — summer_vibes, study_lofi
    'F':  53,   # F major  — city_pop, jazz_cafe
    'D':  62,   # D major  — bossa, bright morning
    'Bb': 58,   # Bb major — jazz cafe warmth, neo-soul
    'A':  69,   # A major  — energetic, bedroom pop
}

def get_pentatonic(root):
    notes = []
    for oct_off in range(3):
        for i in [0,3,5,7,10]:
            n = root + i + oct_off*12
            if 57 <= n <= 84:
                notes.append(n)
    return sorted(set(notes))

def get_dorian(root):
    """Dorian mode — jazzier, slightly brighter than natural minor."""
    notes = []
    for oct_off in range(3):
        for i in [0,2,3,5,7,9,10]:
            n = root + i + oct_off*12
            if 57 <= n <= 84:
                notes.append(n)
    return sorted(set(notes))

def get_phrygian(root):
    """Phrygian mode — dark, exotic; characteristic b2 gives Mediterranean/flamenco edge."""
    notes = []
    for oct_off in range(3):
        for i in [0,1,3,5,7,8,10]:
            n = root + i + oct_off*12
            if 53 <= n <= 86:
                notes.append(n)
    return sorted(set(notes))

def get_major(root):
    """Major scale — bright, resolved, forward motion."""
    notes = []
    for oct_off in range(3):
        for i in [0, 2, 4, 5, 7, 9, 11]:
            n = root + i + oct_off * 12
            if 53 <= n <= 86:
                notes.append(n)
    return sorted(set(notes))

def get_lydian(root):
    """Lydian mode — raised 4th gives floating, ethereal, Nujabes spiritual quality."""
    notes = []
    for oct_off in range(3):
        for i in [0, 2, 4, 6, 7, 9, 11]:
            n = root + i + oct_off * 12
            if 53 <= n <= 86:
                notes.append(n)
    return sorted(set(notes))

def get_natural_minor(root):
    """Natural minor (Aeolian) — b6 makes it darker/sadder than Dorian."""
    notes = []
    for oct_off in range(3):
        for i in [0, 2, 3, 5, 7, 8, 10]:
            n = root + i + oct_off * 12
            if 53 <= n <= 86:
                notes.append(n)
    return sorted(set(notes))

def get_harmonic_minor(root):
    """Harmonic minor — raised 7th adds classical tension, Arabic/flamenco edge."""
    notes = []
    for oct_off in range(3):
        for i in [0, 2, 3, 5, 7, 8, 11]:
            n = root + i + oct_off * 12
            if 53 <= n <= 86:
                notes.append(n)
    return sorted(set(notes))

def get_blues(root):
    """Blues scale — minor pent + b5 blue note. Expressively dark and funky."""
    notes = []
    for oct_off in range(3):
        for i in [0, 3, 5, 6, 7, 10]:
            n = root + i + oct_off * 12
            if 53 <= n <= 86:
                notes.append(n)
    return sorted(set(notes))

def get_whole_tone(root):
    """Whole-tone scale — dreamy, unresolved, Debussy/vaporwave floating."""
    notes = []
    for oct_off in range(3):
        for i in [0, 2, 4, 6, 8, 10]:
            n = root + i + oct_off * 12
            if 53 <= n <= 86:
                notes.append(n)
    return sorted(set(notes))


# ─── MOTIF ENGINE ─────────────────────────────────────────────────────────────

def generate_motif(scale_notes, length=4):
    """Pick a short motif from scale notes using stepwise motion (feels natural)."""
    if not scale_notes:
        return []
    start = random.randint(len(scale_notes)//4, max(len(scale_notes)//4, 3*len(scale_notes)//4))
    motif = [scale_notes[start]]
    for _ in range(length - 1):
        idx = scale_notes.index(motif[-1])
        step = random.choice([-2, -1, -1, 0, 1, 1, 2])
        motif.append(scale_notes[max(0, min(len(scale_notes)-1, idx+step))])
    return motif


def vary_motif(motif, scale_notes, variation):
    """Return a variation of the motif (retrograde, invert, transpose, or nudge)."""
    if not motif or not scale_notes:
        return motif or []

    def _idx(n):
        return scale_notes.index(n) if n in scale_notes else len(scale_notes) // 2

    if variation == 'retrograde':
        return list(reversed(motif))

    if variation == 'invert':
        ref = motif[0]
        lo, hi = scale_notes[0], scale_notes[-1]
        return [max(lo, min(hi, ref - (n - ref))) for n in motif]

    if variation == 'transpose_up':
        return [scale_notes[min(len(scale_notes)-1, _idx(n)+1)] for n in motif]

    # 'default': small random nudge — preserves shape without being identical
    shift = random.choice([-1, 0, 0, 1])
    return [scale_notes[max(0, min(len(scale_notes)-1, _idx(n)+shift))] for n in motif]


# ─── UTILITY ──────────────────────────────────────────────────────────────────

def grid_tick(grid_16th, swing):
    base = grid_16th * S16
    if grid_16th % 2 == 1:
        base += int((swing - 0.5) * 2 * S16)
    return base

def jitter(tick, ms, bpm):
    tpm = (PPQN * bpm) / 60000.0
    return max(0, tick + int(random.uniform(-ms, ms) * tpm))

def v(base, var):
    return max(1, min(127, base + random.randint(-var, var)))

def abs_to_track(events, channel, program=None, cc_events=None, bank_msb=None):
    """
    Convert absolute-tick note events to a MIDI track.
    events:    list of (abs_tick, note, velocity, duration)
    cc_events: optional list of (abs_tick, control, value) for CC messages (e.g. sustain pedal)
    bank_msb:  if set, send CC0=bank_msb + CC32=0 before program_change (GS drum kit select)
    """
    import mido
    track = mido.MidiTrack()
    if bank_msb is not None:
        track.append(mido.Message('control_change', channel=channel, control=0,  value=bank_msb, time=0))
        track.append(mido.Message('control_change', channel=channel, control=32, value=0,        time=0))
    if program is not None:
        track.append(mido.Message('program_change', channel=channel, program=program, time=0))
    msgs = []
    for abs_tick, note, velocity, dur in events:
        on  = max(0, int(abs_tick))
        off = max(on+1, int(abs_tick+dur))
        msgs.append((on,  0, 'note_on',  note, max(1,velocity)))
        msgs.append((off, 1, 'note_off', note, 0))
    if cc_events:
        for abs_tick, control, value in cc_events:
            msgs.append((max(0, int(abs_tick)), 0, 'cc', control, value))
    msgs.sort(key=lambda x:(x[0],x[1]))
    prev = 0
    for item in msgs:
        t, _, mtype = item[0], item[1], item[2]
        if mtype == 'cc':
            track.append(mido.Message('control_change', channel=channel,
                                      control=item[3], value=item[4], time=t-prev))
        else:
            track.append(mido.Message(mtype, channel=channel,
                                      note=item[3], velocity=item[4], time=t-prev))
        prev = t
    track.append(mido.MetaMessage('end_of_track', time=0))
    return track

def build_sustain_pedal(progression, start_bar, num_loops, swing, bpm):
    """
    CC64 sustain pedal events for piano — pedal on at chord start, off at chord end.
    Makes Rhodes ring naturally through chord changes rather than cutting dry.
    Returns list of (abs_tick, control=64, value) CC tuples.
    """
    events = []
    cursor = start_bar
    for _ in range(max(1, num_loops)):
        for chord_name, dur_bars in progression:
            on_t  = grid_tick(cursor * 16, swing)
            # Release pedal one 16th before next chord lands (avoids harmonic smear)
            off_t = grid_tick((cursor + dur_bars) * 16, swing) - S16 // 2
            events.append((on_t,  64, 127))   # sustain on
            events.append((off_t, 64, 0))     # sustain off
            cursor += dur_bars
    return events


# ─── BUILDERS ─────────────────────────────────────────────────────────────────

def build_drums(pattern, start_bar, num_bars, swing, bpm, fill_bars=None):
    """
    Build drum events. fill_bars = set of bar numbers that get a fill
    instead of the regular pattern. Every 4 bars gets a hi-hat 16th run.
    Per-bar mutation: 8% chance each step is dropped or added for variation.
    """
    events = []
    fill_bars = fill_bars or set()
    fill_template = random.choice(DRUM_FILLS)
    # Euclidean hi-hat: 15% chance of polyrhythmic CHH pattern per section
    eucl_hat = random.choice(list(_EUCL_HATS.values())) if random.random() < 0.15 else None
    # Independent second Euclidean layer for OHH/RIM (10% chance, own pattern
    # and own target channel, layered on top of whatever CHH is doing).
    eucl_layer2 = random.choice(list(_EUCL_HATS.values())) if random.random() < 0.10 else None
    eucl_layer2_note = random.choice([OHH, RIM]) if eucl_layer2 is not None else None

    for bar in range(num_bars):
        abs_bar = start_bar + bar
        use_fill = abs_bar in fill_bars

        # Every 4 bars: add 16th hat run on last beat (steps 12-15)
        hat_run = (bar % 4 == 3)

        for step in range(16):
            grid = abs_bar * 16 + step

            src = fill_template if use_fill else pattern

            for drum_note, vels in src.items():
                # Per-element swing: hi-hats/ride are tighter (less swing) than
                # kick/snare — creates the J Dilla polyrhythmic push-pull feel.
                # Research: "Different swing percentages on different drum elements
                # for organic polyrhythmic feel (56% hat vs 66% kick)."
                elem_swing = swing * (0.92 if drum_note in (CHH, RIDE) else 1.0)
                base_t = grid_tick(grid, elem_swing)

                # Off-beat hi-hat lazy drag (15-28ms behind grid) — lo-fi laid-back feel.
                # 8th-note off-beats are at steps 2,6,10,14 (step % 4 == 2).
                # Dragging these slightly late creates the sleepy, heavy pocket.
                # (Early rush = nervous/urgent; late drag = relaxed/heavy)
                if drum_note == CHH and step % 4 == 2:
                    drag_ticks = int(random.uniform(15, 28) * (PPQN * bpm) / 60000.0)
                    base_t = base_t + drag_ticks

                vel_val = vels[step % 16]

                # Euclidean CHH override (replaces fixed pattern with polyrhythm)
                if eucl_hat is not None and drum_note == CHH and not use_fill:
                    vel_val = 55 if eucl_hat[step % len(eucl_hat)] else 0

                # Independent second Euclidean layer (OHH or RIM) — a different
                # polyrhythm than whatever CHH is doing, for extra texture.
                if (eucl_layer2 is not None and drum_note == eucl_layer2_note
                        and not use_fill):
                    vel_val = 45 if eucl_layer2[step % len(eucl_layer2)] else 0

                # Per-bar mutation: occasionally drop or ghost a hit
                if not use_fill:
                    if vel_val > 0 and random.random() < 0.06:
                        vel_val = 0  # drop hit
                    elif vel_val == 0 and drum_note == CHH and random.random() < 0.05:
                        vel_val = 35  # occasional ghost hat

                # Hi-hat 16th run on last beat every 4 bars
                if hat_run and drum_note == CHH and step >= 12:
                    vel_val = max(vel_val, v(55, 10))

                if vel_val > 0:
                    t = jitter(base_t, 4, bpm)
                    events.append((t, drum_note, v(vel_val, 8), 25))

    return events


def _chord_pcs_at_bar(progression, bar, prog_bars):
    """Return the pitch-class set of the chord playing at the given absolute bar."""
    bar_in_prog = bar % max(1, prog_bars)
    cursor = 0
    for chord_name, dur in progression:
        if bar_in_prog < cursor + dur:
            voicing = VOICING_OPTIONS.get(chord_name, [[60, 64, 67]])[0]
            return {n % 12 for n in voicing}
        cursor += dur
    return set()


def _voice_lead_choice(chord_name, prev_top=None):
    """Pick the voicing whose top note is closest to prev_top (smooth voice leading).
    Falls back to random choice if prev_top is None or chord has no voicings."""
    options = VOICING_OPTIONS.get(chord_name, [[60, 64, 67]])
    if prev_top is None:
        return random.choice(options)
    return min(options, key=lambda vv: abs(vv[-1] - prev_top))


def build_chords(progression, start_bar, num_loops, swing, bpm):
    """
    Chords with:
    - Voice-leading voicing: top note moves minimally between chords
    - Strum effect (5-12ms spread)
    - Top note louder (melody voice)
    - 50% comp hit on beat 3
    - Occasional secondary dominant substitution
    """
    events = []
    cursor = start_bar
    prev_top = None
    for _ in range(max(1, num_loops)):
        for chord_idx, (chord_name, dur_bars) in enumerate(progression):
            # Occasional secondary dominant or tritone substitution
            chord_name = maybe_sub_chord(chord_name, chord_idx)
            # Voice-leading: pick voicing with top note closest to previous chord top note
            voicing  = _voice_lead_choice(chord_name, prev_top)
            prev_top = voicing[-1]

            base_t   = grid_tick(cursor * 16, swing)
            note_dur = int(dur_bars * BAR * 0.88)

            for i, note in enumerate(voicing):
                strum_t = int(i * random.uniform(5,12) * (PPQN*bpm)/60000)
                t = jitter(base_t, 14, bpm) + strum_t
                if i == len(voicing)-1: vel_val = v(78, 10)   # top note
                elif i == 0:            vel_val = v(58,  8)   # bottom
                else:                   vel_val = v(66, 10)   # inner
                events.append((t, note, vel_val, note_dur))

            # Comp hit beat 3 (50%)
            if dur_bars >= 2 and random.random() < 0.5:
                b3_t = grid_tick(cursor*16 + 8, swing)
                for note in voicing[-3:]:
                    events.append((jitter(b3_t,16,bpm), note, v(50,10), int(BAR*0.45)))

            # Occasional beat 2 comp hit (25%)
            if dur_bars >= 2 and random.random() < 0.25:
                b2_t = grid_tick(cursor*16 + 4, swing)
                for note in voicing[-2:]:
                    events.append((jitter(b2_t,16,bpm), note, v(44,8), int(BAR*0.30)))

            cursor += dur_bars
    return events


def build_pad(progression, start_bar, num_loops, swing, bpm):
    """
    Very quiet string pad — holds root + 5th for full chord duration.
    Adds depth without cluttering the mix.
    """
    events = []
    cursor = start_bar
    for _ in range(max(1, num_loops)):
        for chord_name, dur_bars in progression:
            root = BASS_ROOTS.get(chord_name, 45) + 12  # one octave up from bass
            fifth = root + 7
            base_t   = grid_tick(cursor * 16, swing)
            note_dur = int(dur_bars * BAR * 0.98)  # near-legato
            for note in [root, fifth]:
                t = jitter(base_t, 20, bpm)
                events.append((t, note, v(38, 8), note_dur))  # very quiet
            cursor += dur_bars
    return events


def build_bass(progression, start_bar, num_loops, swing, bpm, walking=False):
    """
    Bass line with:
    - Root on beat 1 (always)
    - Fifth on beat 2-and (syncopated, 70%)
    - Occasional passing note on beat 4-and
    - walking=True: occasional 4-note walking line in last bar of progression
    """
    events = []
    cursor = start_bar
    for loop in range(max(1, num_loops)):
        prog_bars = sum(d for _,d in progression)
        for chord_idx, (chord_name, dur_bars) in enumerate(progression):
            root  = BASS_ROOTS.get(chord_name, 45)
            is_last_bar_of_loop = (chord_idx == len(progression)-1)

            # Chromatic approach: semitone below next chord's root (jazz bass standard).
            # Fall back to whole-tone (root+2) if the interval is awkward (>5 semitones).
            next_chord_name = progression[(chord_idx + 1) % len(progression)][0]
            next_root = BASS_ROOTS.get(next_chord_name, root)
            approach = next_root - 1
            if abs(approach - root) > 5:
                approach = root + 2

            # Guide tones for walking bass (3rd and 7th instead of root+fifth)
            third_off, seventh_off = _GUIDE_TONES.get(chord_name, (3, 10))
            beat2_note = root + (third_off if walking else 7)   # 3rd (jazz) or fifth (pop)
            beat3_note = root + (seventh_off if walking else 0)  # 7th (jazz) or root (pop)

            for bar in range(dur_bars):
                abs_bar = cursor + bar
                last_bar = is_last_bar_of_loop and bar == dur_bars-1

                # Walking bass fill in last bar of progression (if enabled, 40% chance)
                if walking and last_bar and random.random() < 0.40:
                    # 4 quarter-note walk — descending preferred (chill effect),
                    # ascending approach used 40% to create tension-release arc.
                    if random.random() < 0.60:
                        # Descending (melancholic, chill)
                        walk_notes = [root+7, root+5, root+2, root]
                    else:
                        # Ascending (approach from below, then jump)
                        walk_notes = [root, root+2, root+4, root+7]
                        random.shuffle(walk_notes[1:])  # keep root first, vary rest
                    for beat, note in enumerate(walk_notes):
                        t = jitter(grid_tick(abs_bar*16 + beat*4, swing), 8, bpm)
                        events.append((t, note, v(72,10), int(PPQN*0.85)))
                else:
                    # Beat 1: root
                    t1 = jitter(grid_tick(abs_bar*16, swing), 8, bpm)
                    events.append((t1, root, v(80,10), int(BAR*0.82)))
                    # Beat 2-and: guide tone (3rd when walking, fifth otherwise) 70%
                    if random.random() < 0.70:
                        t2 = jitter(grid_tick(abs_bar*16+6, swing), 8, bpm)
                        events.append((t2, beat2_note, v(68,12), int(BAR*0.35)))
                    # Beat 3: guide tone (7th when walking, root otherwise) 35%
                    if random.random() < 0.35:
                        t3 = jitter(grid_tick(abs_bar*16+8, swing), 8, bpm)
                        events.append((t3, beat3_note, v(72,10), int(BAR*0.40)))
                    # Beat 4-and passing (20%) — chromatic approach to next chord root
                    if random.random() < 0.20:
                        t4 = jitter(grid_tick(abs_bar*16+14, swing), 8, bpm)
                        events.append((t4, approach, v(60,10), int(S16*1.5)))

            cursor += dur_bars
    return events


def build_melody(key_root, start_bar, num_bars, swing, bpm, density='sparse', scale='pent',
                 motif=None, progression=None, prog_bars=None):
    """
    Motif-based melody with phi-point (0.618) contour arc + chord-aware phrase starts.
    Develops a 3-5 note motif through retrograde/inversion/transposition variations.
    Climax velocity peaks at ~61.8% through phrase. First note of each phrase snaps to
    the nearest chord tone (60% chance) so melody lands convincingly on the harmony.
    """
    if scale == 'dorian':
        notes_scale = get_dorian(key_root)
    elif scale == 'phryg':
        notes_scale = get_phrygian(key_root)
    elif scale == 'major_pent':
        notes_scale = [n for oct_off in range(3)
                       for i in [0, 2, 4, 7, 9]
                       for n in [key_root + i + oct_off * 12]
                       if 53 <= key_root + i + oct_off * 12 <= 86]
    elif scale == 'mixo':
        notes_scale = [n for oct_off in range(3)
                       for i in [0, 2, 4, 5, 7, 9, 10]
                       for n in [key_root + i + oct_off * 12]
                       if 53 <= key_root + i + oct_off * 12 <= 86]
    elif scale == 'major':
        notes_scale = get_major(key_root)
    elif scale == 'lydian':
        notes_scale = get_lydian(key_root)
    elif scale == 'natural_minor':
        notes_scale = get_natural_minor(key_root)
    elif scale == 'harmonic_minor':
        notes_scale = get_harmonic_minor(key_root)
    elif scale == 'blues':
        notes_scale = get_blues(key_root)
    elif scale == 'whole_tone':
        notes_scale = get_whole_tone(key_root)
    else:
        notes_scale = get_pentatonic(key_root)
    if not notes_scale:
        return []

    if motif is None:
        motif = generate_motif(notes_scale, length=random.randint(3, 5))

    VARIATIONS = ['retrograde', 'transpose_up', 'invert', 'default', 'default']
    var_idx = 0
    events = []
    bar = start_bar
    rest_min = 2 if density == 'sparse' else 1

    while bar < start_bar + num_bars:
        if random.random() < 0.72:
            phrase_notes = vary_motif(motif, notes_scale, VARIATIONS[var_idx % len(VARIATIONS)])
            var_idx += 1
            phrase_len   = len(phrase_notes)
            phrase_start = bar * 16 + random.randint(0, 5)

            for i, note in enumerate(phrase_notes):
                g = phrase_start + i * random.randint(2, 5)
                if g >= (start_bar + num_bars) * 16:
                    break

                # Phi-point contour: ascending before 0.618, descending after
                pos = i / max(1, phrase_len - 1)
                if pos < 0.618:
                    step = random.choice([-1, 0, 1, 1, 2])
                else:
                    step = random.choice([-2, -2, -1, -1, 0])
                idx = notes_scale.index(note) if note in notes_scale else len(notes_scale)//2
                idx = max(0, min(len(notes_scale)-1, idx + step))
                note = notes_scale[idx]

                # Chord-aware phrase start: snap first note to nearest chord tone (60%).
                # Ensures each phrase "lands" on a note that fits the active harmony.
                if i == 0 and progression and prog_bars and random.random() < 0.60:
                    chord_pcs = _chord_pcs_at_bar(progression, bar, prog_bars)
                    chord_scale = [n for n in notes_scale if n % 12 in chord_pcs]
                    if chord_scale:
                        note = min(chord_scale, key=lambda n: abs(n - note))

                # Velocity arc: louder near phi-point climax
                climax_dist = abs(pos - 0.618)
                vel_arc = int(12 * (1.0 - climax_dist))
                beat_pos  = g % 16
                vel_bonus = 8 if beat_pos == 0 else (4 if beat_pos == 8 else 0)

                t   = jitter(grid_tick(g, swing), 22, bpm)

                # Grace note: acciaccatura — leading-tone approach 1 step below main note
                # 15% chance on first note of each phrase; adds jazz phrasing feel
                if i == 0 and random.random() < 0.15 and len(notes_scale) > 2:
                    n_idx = notes_scale.index(note) if note in notes_scale else len(notes_scale)//2
                    gn_idx = max(0, n_idx - 1)
                    grace_note = notes_scale[gn_idx]
                    grace_t = max(0, t - int(S16 * 0.35))
                    events.append((grace_t, grace_note, v(38, 6), int(S16 * 0.30)))
                dur = int(BAR * random.uniform(0.22, 0.72))
                if random.random() < 0.30:
                    dur = int(dur * 1.5)
                events.append((t, note, v(70 + vel_bonus + vel_arc, 13), dur))

            bar += phrase_len + random.randint(rest_min, rest_min + 3)
        else:
            bar += random.randint(2, 5)

    return events

def build_intro_hats(start_bar: int, num_bars: int, swing: float, bpm: int) -> list:
    """
    Soft quarter-note hi-hat pulse for intro/outro sections.
    Gives a rhythmic pulse without full drums — eliminates dead air.
    Velocity ramps up from ~28 to ~48 over num_bars for a natural swell.
    """
    events = []
    for bar in range(num_bars):
        frac = bar / max(1, num_bars - 1)
        vel_base = int(28 + 20 * frac)
        for beat in [0, 4, 8, 12]:   # quarter notes
            t = jitter(grid_tick((start_bar + bar) * 16 + beat, swing), 5, bpm)
            events.append((t, CHH, v(vel_base, 6), 28))
    return events


def build_break_hats(start_bar: int, num_bars: int, swing: float, bpm: int) -> list:
    """
    Sparse open-hat pulse for break sections — keeps energy up without snare.
    Also adds quiet rim ghost notes for texture.
    """
    events = []
    for bar in range(num_bars):
        for beat in [0, 8]:           # half-note open hats
            t = jitter(grid_tick((start_bar + bar) * 16 + beat, swing), 6, bpm)
            events.append((t, OHH, v(38, 10), 35))
        for beat in [4, 12]:          # ghost rim between
            if random.random() < 0.55:
                t = jitter(grid_tick((start_bar + bar) * 16 + beat, swing), 8, bpm)
                events.append((t, RIM, v(22, 6), 20))
    return events


def build_counter_melody(key_root: int, start_bar: int, num_bars: int,
                         swing: float, bpm: int) -> list:
    """
    Answering melody in lower register (root-12). Fills silence between
    main melody phrases. 1-2 short phrases per num_bars section.
    Very sparse — complements without cluttering.
    """
    notes_low = get_pentatonic(key_root - 12)
    if not notes_low:
        notes_low = get_pentatonic(key_root)
    events = []
    bar = start_bar
    while bar < start_bar + num_bars - 1:
        if random.random() < 0.60:
            phrase_len = random.randint(1, 3)
            phrase_start = bar * 16 + random.randint(0, 6)
            prev_note = random.choice(notes_low)
            for i in range(phrase_len):
                g = phrase_start + i * random.randint(3, 6)
                if g >= (start_bar + num_bars) * 16:
                    break
                idx  = notes_low.index(prev_note) if prev_note in notes_low else len(notes_low) // 2
                step = random.choice([-1, -1, 0, 1, 1])
                idx  = max(0, min(len(notes_low) - 1, idx + step))
                note = notes_low[idx]
                t    = jitter(grid_tick(g, swing), 28, bpm)
                dur  = int(BAR * random.uniform(0.65, 1.55))
                events.append((t, note, v(44, 10), dur))
                prev_note = note
            bar += phrase_len + random.randint(2, 5)
        else:
            bar += random.randint(2, 4)
    return events


# ─── PARAMETER SELECTION ──────────────────────────────────────────────────────

# ---------------------------------------------------------------------------
# Procedural mood-phrase composer — generates unique phrases, never repeats
# ---------------------------------------------------------------------------
_MOOD_WORDS: dict[str, tuple[str, ...]] = {
    'adj_texture':  ('worn', 'hollow', 'amber', 'pale', 'thick', 'smooth', 'heavy',
                     'thin', 'distant', 'muted', 'cracked', 'dim', 'loose', 'bleached',
                     'frayed', 'corroded', 'lacquered', 'oxidized', 'chalky', 'matte',
                     'grained', 'washed-out', 'raw', 'spare', 'flat', 'rough',
                     'translucent', 'porous', 'layered', 'compressed'),
    'adj_feeling':  ('tired', 'restless', 'borrowed', 'lost', 'empty', 'broken',
                     'aching', 'unhurried', 'uneasy', 'half-awake', 'bare', 'residual',
                     'suspended', 'provisional', 'overdue', 'unfinished', 'peripheral',
                     'off-beat', 'misplaced', 'tangential', 'stubborn', 'overcast',
                     'untethered', 'spent', 'exact', 'specific'),
    'noun_sensory': ('light', 'smoke', 'static', 'groove', 'hum', 'pulse', 'echo',
                     'rhythm', 'silence', 'noise', 'dust', 'fog', 'shadow', 'breath',
                     'glow', 'grain', 'hiss', 'crackle', 'resonance', 'drift',
                     'diesel', 'chalk', 'copper', 'tar', 'ozone', 'rust', 'resin',
                     'frequency', 'current', 'signal', 'pressure', 'interference',
                     'feedback', 'static', 'flux', 'charge'),
    'noun_place':   ('street', 'window', 'hallway', 'staircase', 'rooftop', 'kitchen',
                     'doorway', 'alley', 'overpass', 'library', 'laundromat', 'bus stop',
                     'fire escape', 'turnstile', 'underpass', 'server room', 'tollbooth',
                     'waiting room', 'loading dock', 'parking structure', 'switchboard',
                     'copy room', 'basement', 'corridor', 'storage unit', 'phone booth',
                     'breakroom', 'transit hub', 'side entrance'),
    'noun_time':    ('morning', 'evening', 'afternoon', 'tuesday', 'sunday', 'winter',
                     'autumn', 'hour', 'moment', 'monday', 'late november', 'early march',
                     'the small hours', '3am', 'dusk', 'dawn', 'a thursday in october',
                     'the hour before the test', 'last tuesday', 'two weeks ago',
                     'the end of the fiscal quarter', 'shift change', 'closing time',
                     'the week before moving out', 'fourth period', 'overtime'),
    'noun_abstract':('weight', 'feeling', 'grief', 'longing', 'distance', 'ache',
                     'doubt', 'void', 'space', 'gravity', 'texture', 'absence',
                     'motion', 'stillness', 'blur', 'residue', 'friction', 'inertia',
                     'pressure', 'threshold', 'margin', 'recursion', 'latency',
                     'interference', 'drift', 'entropy', 'voltage', 'frequency',
                     'amplitude', 'lag', 'overhead', 'clearance'),
    'verb_ing':     ('falling', 'echoing', 'waiting', 'breathing', 'floating',
                     'turning', 'leaking', 'blooming', 'slowing', 'humming', 'settling',
                     'dissolving', 'lingering', 'stretching', 'wandering', 'unraveling',
                     'compressing', 'accumulating', 'transmitting', 'buffering',
                     'oscillating', 'receding', 'converging', 'circling', 'stalling',
                     'iterating', 'looping', 'clipping', 'saturating'),
    'verb_past':    ('stayed', 'opened', 'closed', 'fell', 'crept', 'settled',
                     'broke', 'leaned', 'hummed', 'spilled', 'held', 'kept',
                     'let go', 'carried on', 'clocked out', 'ran out', 'reset',
                     'overran', 'missed', 'stalled', 'accumulated', 'exceeded'),
    'prep':         ('through', 'beneath', 'beside', 'beyond', 'under', 'across',
                     'within', 'over', 'against', 'between', 'along', 'past',
                     'around', 'toward', 'behind', 'inside', 'adjacent to',
                     'in spite of', 'at the edge of', 'two floors above'),
    'det':          ('the', 'a', 'that', 'this'),
}

# Genre-specific word tints — pull toward sonic character without hardcoding titles
_MOOD_TINTS: dict[str, dict[str, tuple[str, ...]]] = {
    'dark_lofi':      {'adj_texture': ('hollow', 'heavy', 'dim', 'cracked', 'cold', 'frayed', 'distant'),
                       'noun_sensory': ('shadow', 'static', 'hiss', 'fog', 'silence', 'echo', 'drone')},
    'lofi_phonk':     {'adj_texture': ('heavy', 'thick', 'raw', 'hollow', 'cracked'),
                       'noun_sensory': ('pulse', 'static', 'echo', 'noise', 'hiss', 'bass')},
    'vaporwave':      {'adj_texture': ('pale', 'faded', 'hollow', 'bleached', 'distant', 'thin'),
                       'noun_sensory': ('glow', 'echo', 'drift', 'resonance', 'haze', 'static')},
    'summer_vibes':   {'adj_texture': ('warm', 'golden', 'bright', 'smooth', 'light', 'soft'),
                       'noun_sensory': ('light', 'warmth', 'glow', 'breath', 'melody', 'rhythm')},
    'cozy_cafe':      {'adj_texture': ('warm', 'amber', 'gentle', 'soft', 'quiet'),
                       'noun_sensory': ('warmth', 'hum', 'light', 'melody', 'breath', 'grain')},
    'jazz_cafe':      {'adj_texture': ('warm', 'smooth', 'amber', 'gentle', 'tender'),
                       'noun_sensory': ('melody', 'groove', 'warmth', 'hum', 'pulse', 'breath')},
    'bossa_lofi':     {'adj_texture': ('warm', 'soft', 'gentle', 'golden', 'smooth'),
                       'noun_sensory': ('melody', 'warmth', 'breath', 'light', 'glow', 'groove')},
    'study_lofi':     {'adj_texture': ('quiet', 'still', 'soft', 'gentle', 'slow', 'dim'),
                       'noun_sensory': ('hum', 'light', 'silence', 'grain', 'warmth', 'echo')},
    'morning_lofi':   {'adj_texture': ('soft', 'golden', 'gentle', 'warm', 'pale', 'still'),
                       'noun_sensory': ('light', 'warmth', 'glow', 'breath', 'melody', 'hum')},
    'lofi_classical': {'adj_texture': ('tender', 'still', 'gentle', 'soft', 'pale', 'quiet'),
                       'noun_sensory': ('melody', 'resonance', 'silence', 'warmth', 'echo', 'grain')},
    'anime_lofi':     {'adj_texture': ('soft', 'golden', 'gentle', 'warm', 'tender', 'dim'),
                       'noun_sensory': ('light', 'melody', 'warmth', 'glow', 'echo', 'breath')},
    'lofi_rnb':       {'adj_texture': ('warm', 'smooth', 'soft', 'tender', 'slow', 'heavy'),
                       'noun_sensory': ('groove', 'warmth', 'pulse', 'melody', 'breath', 'hum')},
    'lo_fi_funk':     {'adj_texture': ('warm', 'thick', 'smooth', 'heavy', 'loose', 'slow'),
                       'noun_sensory': ('groove', 'pulse', 'rhythm', 'bass', 'warmth', 'hum')},
    'hip_hop_lofi':   {'adj_texture': ('heavy', 'warm', 'thick', 'slow', 'hollow', 'dim'),
                       'noun_sensory': ('pulse', 'bass', 'groove', 'echo', 'hum', 'static')},
    'chillhop':       {'adj_texture': ('warm', 'smooth', 'soft', 'slow', 'golden', 'gentle'),
                       'noun_sensory': ('groove', 'warmth', 'hum', 'melody', 'pulse', 'breath')},
}

_MOOD_PATTERNS: tuple[str, ...] = (
    '{adj_texture} {noun_sensory}',
    '{det} {noun_abstract} of {noun_time}',
    '{noun_sensory} {prep} {det} {noun_place}',
    '{adj_texture} {noun_time} on {det} {adj_feeling} {noun_place}',
    '{det} {adj_texture} {noun_sensory}',
    '{noun_sensory} {prep} {noun_abstract}',
    '{verb_ing} {prep} {det} {noun_sensory}',
    '{noun_time}, {adj_texture} and {adj_feeling}',
    '{det} {noun_place} {verb_past} {adj_texture}',
    '{adj_texture} {noun_place}, {adj_feeling} {noun_sensory}',
    '{verb_ing} like {det} {adj_texture} {noun_abstract}',
    '{det} {noun_abstract} {verb_past} {prep} {det} {noun_place}',
    '{noun_time} {noun_sensory} on {det} {adj_feeling} {noun_place}',
    '{adj_feeling} {noun_abstract}, {adj_texture} {noun_sensory}',
    'when {det} {noun_place} {verb_past} {adj_texture}',
    'all that {adj_texture} {noun_abstract}',
    '{det} last {noun_sensory} of {noun_time}',
    'lost {prep} {det} {adj_texture} {noun_place}',
    'still {verb_ing} {prep} {det} {noun_abstract}',
    '{adj_texture} {noun_sensory} {prep} {det} {noun_place}',
)


def _compose_mood_phrase(sub_genre: str = '') -> str:
    """Generate a unique mood phrase by combining word banks — never repeats fixed strings."""
    import re as _re
    tint = _MOOD_TINTS.get(sub_genre, {})
    pattern = random.choice(_MOOD_PATTERNS)

    def _pick(m: '_re.Match') -> str:  # type: ignore[name-defined]
        pool = tint.get(m.group(1)) or _MOOD_WORDS.get(m.group(1)) or ('',)
        return random.choice(pool)

    result = _re.sub(r'\{([^}]+)\}', _pick, pattern)
    return result[0].upper() + result[1:]


_PARAMS_HISTORY_FILE = os.path.join(MUSIC_DIR, '.params_history.json')
_HISTORY_MAXLEN = 30  # keep last N genre+key+prog combos to steer away from


def _load_params_history() -> list[dict]:
    try:
        with open(_PARAMS_HISTORY_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_params_history(params: dict) -> None:
    history = _load_params_history()
    history.append({
        'sub_genre':   params.get('sub_genre', ''),
        'key':         params.get('key', ''),
        'progression': params.get('progression', ''),
        'mood':        params.get('mood', ''),
    })
    history = history[-_HISTORY_MAXLEN:]
    try:
        os.makedirs(os.path.dirname(_PARAMS_HISTORY_FILE), exist_ok=True)
        with open(_PARAMS_HISTORY_FILE, 'w') as f:
            json.dump(history, f)
    except OSError:
        pass


# ─── ALGORITHMIC PARAM HELPERS ────────────────────────────────────────────────

def _pick_subgenre_weighted(history: list[dict]) -> str:
    """Inverse-frequency weighted sub-genre selection.

    Underused genres get picked more often; cozy/bright genres keep 2× base
    weight to preserve the channel identity. Guarantees diversity across sessions.
    """
    from collections import Counter
    counts = Counter(h.get('sub_genre', '') for h in history)
    all_subs = list(_SUBGENRE_CONFIG.keys())
    weights = [
        (2.0 if s in _COZY_SUBGENRES else 1.0) / (counts.get(s, 0) + 1)
        for s in all_subs
    ]
    return random.choices(all_subs, weights=weights, k=1)[0]


def _pick_key_avoiding_recent(sub: str, history: list[dict]) -> str:
    """Pick a key that hasn't been used for this sub-genre in the last 8 picks."""
    all_keys = list(KEY_ROOTS.keys())
    recent = {h['key'] for h in history[-8:] if h.get('sub_genre') == sub and h.get('key')}
    available = [k for k in all_keys if k not in recent] or all_keys
    return random.choice(available)


def _pick_progression_avoiding_recent(sub: str, key: str, cfg: dict, history: list[dict]) -> int:
    """Pick a progression not recently used for this (sub_genre, key) pair."""
    recent: set[int] = set()
    for h in history[-10:]:
        if h.get('sub_genre') == sub and h.get('key') == key:
            raw = h.get('progression', '')
            if str(raw).lstrip('-').isdigit():
                recent.add(int(raw))
    available = [p for p in cfg['progs'] if p not in recent] or list(cfg['progs'])
    return random.choice(available)


def _resolve_genre_hint(hint: str) -> str | None:
    """Map a free-text genre hint to a known sub_genre key, or None."""
    normalized = hint.lower().replace(' ', '_').replace('-', '_')
    # Exact match
    if normalized in _SUBGENRE_CONFIG:
        return normalized
    # Match ignoring underscores ("lo-fi jazz" → "lofi_jazz")
    norm_bare = normalized.replace('_', '')
    for s in _SUBGENRE_CONFIG:
        if s.replace('_', '') == norm_bare:
            print(f"  [params] genre_hint '{hint}' resolved to '{s}'")
            return s
    # Substring fallback
    match = next((s for s in _SUBGENRE_CONFIG if normalized in s or s in normalized), None)
    if match:
        print(f"  [params] genre_hint '{hint}' resolved to '{match}'")
    return match


def _pick_mood_phrase(concept_hint: str | None = None, sub_genre: str = '',
                      history: list[dict] | None = None) -> str:
    """Poetic mood phrase. Procedural composer is primary (combinatorial word-bank
    generator — thousands of unique phrases per genre, never repeats fixed strings).
    Groq LLM is only ever used as an explicit opt-in failsafe (LOFI_LLM_FAILSAFE=1)
    if the procedural composer can't produce a fresh, non-repeated phrase."""
    if concept_hint:
        return concept_hint

    recent = {h['mood'] for h in (history or [])[-10:] if h.get('mood')}
    phrase = _compose_mood_phrase(sub_genre)
    for _ in range(5):
        if phrase not in recent:
            return phrase
        phrase = _compose_mood_phrase(sub_genre)

    if os.getenv('LOFI_LLM_FAILSAFE') == '1' and GROQ_KEY:
        try:
            from groq import Groq
            genre_txt = f' Genre: {sub_genre.replace("_", " ")}.' if sub_genre else ''
            recent = [h['mood'] for h in (history or [])[-10:] if h.get('mood')]
            avoid_txt = (' Avoid these already-used phrases: '
                         + '; '.join(f'"{p}"' for p in recent[-5:]) + '.') if recent else ''
            resp = Groq(api_key=GROQ_KEY).chat.completions.create(
                model='llama-3.3-70b-versatile',
                messages=[{'role': 'user', 'content':
                    f'Write ONE short poetic phrase (4-8 words) for a lo-fi music track.{genre_txt}'
                    f'{avoid_txt} '
                    'Rules: concrete image or sensation, unexpected angle, no clichés. '
                    'BANNED words (any form): rain, whisper, forgotten, soft, fade, cassette, '
                    'vinyl, warmth, cozy, peaceful, dreamy, melancholy, nostalgia, gentle, '
                    'midnight, moonlit, hazy, haze, lofi, lo-fi. '
                    'Output ONLY the phrase. No quotes. No punctuation at end.'
                }],
                max_tokens=25,
                temperature=1.5,
                presence_penalty=1.0,
            )
            phrase = (resp.choices[0].message.content
                      .strip().split('\n')[0].strip().strip('"\' ').rstrip('.,'))
            _banned = {'rain','rainy','raining','whisper','whispers','forgotten','forgetting',
                       'soft','softly','fading','fade','faded','cassette','vinyl','warmth',
                       'cozy','peaceful','dreamy','melancholy','nostalgia','gentle','midnight',
                       'moonlit','hazy','haze','lofi','lo-fi'}
            words_lc = {w.lower().strip('s') for w in phrase.split()}
            if (any(c in phrase for c in '{}[]:')
                    or not (3 <= len(phrase.split()) <= 12)
                    or words_lc & _banned):
                raise ValueError('banned/bad phrase')
            return phrase
        except Exception:
            pass
    return _compose_mood_phrase(sub_genre)


def pick_params(concept_hint: str | None = None, genre_hint: str | None = None) -> dict:
    history = _load_params_history()

    sub = (_resolve_genre_hint(genre_hint) if genre_hint else None) or _pick_subgenre_weighted(history)
    cfg  = _SUBGENRE_CONFIG[sub]
    key  = _pick_key_avoiding_recent(sub, history)
    prog = _pick_progression_avoiding_recent(sub, key, cfg, history)

    n_pats = len(DRUM_PATTERNS)
    pat_a  = random.choice(cfg['drum_pats']) % n_pats
    other  = [p % n_pats for p in cfg['drum_pats'] if p % n_pats != pat_a] or [pat_a]
    pat_b  = random.choice(other)

    sw_lo, sw_hi = _SWING_RANGE.get(sub, _SWING_DEFAULT)
    drum_energy = cfg.get('energy') or random.choice(['low', 'medium', 'high'])
    params = {
        'key':            key,
        'progression':    prog,
        'bpm':            random.randint(*cfg['bpm']),
        'swing':          round(random.uniform(sw_lo, sw_hi), 2),
        'mood':           _pick_mood_phrase(concept_hint, sub_genre=sub, history=history),
        'melody_density': random.choice(['sparse', 'medium']),
        'melody_scale':   random.choice(cfg['scale']),
        'bass_walking':   random.random() < 0.4,
        'drum_pattern_a': pat_a,
        'drum_pattern_b': pat_b,
        'drum_energy':    drum_energy,
        'sub_genre':      sub,
    }

    # ~20% independent chance each for A/B drum sections to use a freshly
    # generated Euclidean pattern instead of the curated table — the curated
    # table stays the ~80% reliable default.
    energy_f = _DRUM_ENERGY_TO_FLOAT.get(drum_energy, 0.55)
    complexity_f = round(random.uniform(0.3, 0.8), 2)
    if random.random() < 0.20:
        params['drum_pattern_a_generated'] = generate_euclidean_drum_pattern(energy_f, complexity_f)
    if random.random() < 0.20:
        params['drum_pattern_b_generated'] = generate_euclidean_drum_pattern(energy_f, complexity_f)

    if key in ('C', 'G', 'F') and prog < 16:
        print(f"  [params] NOTE: major key '{key}' with minor prog {prog} — voicings will be modal")
    print(f"  [params] key={key} bpm={params['bpm']} prog={prog} sub={sub} mood='{params['mood']}'")

    _save_params_history(params)
    return params

# ─── MIDI BUILDER ─────────────────────────────────────────────────────────────

# ─── TENSION ARC ──────────────────────────────────────────────────────────────

def _tension(bar, total_bars):
    """
    Piecewise tension curve: 0.0 = relaxed, 1.0 = peak.
    Intro (0-20%) rises gently; main section builds; B section peaks; outro releases.
    """
    p = bar / max(1, total_bars)
    if p < 0.20:
        return 0.20 + p * 1.50          # 0.20 → 0.50
    elif p < 0.60:
        return 0.50 + (p - 0.20) * 1.25  # 0.50 → 1.00
    elif p < 0.75:
        return 1.00                      # peak (B section)
    else:
        return max(0.05, 1.00 - (p - 0.75) * 3.80)  # 1.00 → ~0.05


def _apply_tension_to_drums(drum_ev, total_bars, base_mult=1.0):
    """Scale drum velocity by per-bar tension — loud at B section, quiet in intro."""
    return [
        (t, n, max(1, min(127, int(vel * base_mult * (0.70 + 0.45 * _tension(t // BAR, total_bars))))), d)
        for t, n, vel, d in drum_ev
    ]


# ─── SONG FORMS ───────────────────────────────────────────────────────────────

# Form = list of (section_label, num_prog_loops)
# Labels: 'I'=intro, 'A'=A section, 'BR'=break, 'B'=B section, 'O'=outro
_SONG_FORMS = {
    'standard': [('I',1),('A',4),('BR',1),('B',4),('O',1)],   # 1+4+1+4+1 = 11 loops
    'ambient':  [('I',2),('A',6),('BR',2),('B',4),('O',2)],   # longer drift = 16
    'funk':     [('I',2),('A',6),('BR',1),('B',6),('O',1)],   # energy-forward = 16
    'minimal':  [('A',2),('BR',1),('B',2)],                    # tight = 5 loops
    'extended': [('I',1),('A',4),('BR',2),('B',6),('O',2)],   # long nujabes = 15
}
_FORM_BY_SUBGENRE = {
    'ambient':        'ambient',
    'chill_beats':    'ambient',
    'piano_lofi':     'ambient',
    'vaporwave':      'ambient',   # long dreamy drift
    'lofi_classical': 'extended',  # refined, needs space
    'lo_fi_funk':     'funk',
    'hip_hop_lofi':   'funk',
    'lofi_house':     'funk',      # rhythmic energy-forward
    'nujabes':        'extended',
    'lofi_jazz':      'extended',
}

# Secondary genre-specific instrument texture layer
# (program, style) — style controls rhythm pattern for that instrument character
_SUBGENRE_TEXTURE = {
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
}


def build_texture(program, progression, start_bar, num_bars, swing, bpm, style):
    """
    Sparse secondary-instrument accent layer tuned to instrument character.
    Fires 50% probability per track (controlled by caller). Channel 5.

    Styles:
      'strum'  — guitar upstroke chord fragments on off-beats (4-and, 3-and)
      'stab'   — organ 2-note root+5th stabs on beat 2 or 4
      'breath' — flute long tones on chord root at phrase starts
      'pop'    — marimba bright attacks on root/3rd, mostly off-beat
      'fill'   — trumpet 2-3 note jazz fill at end of every 4-bar phrase
    """
    events = []
    prog_bars = sum(d for _, d in progression)

    for bar in range(start_bar, start_bar + num_bars):
        # Map absolute bar to the correct chord, respecting each chord's duration
        bar_in_cycle = (bar - start_bar) % prog_bars
        cursor, chord_name = 0, progression[0][0]
        for cn, dur in progression:
            if bar_in_cycle < cursor + dur:
                chord_name = cn
                break
            cursor += dur
        root_pc = BASS_ROOTS.get(chord_name, 48) % 12
        root_mid = 48 + root_pc  # octave 3
        fifth    = root_mid + 7

        if style == 'strum':
            # Off-beat chord fragment on step 10 (3-and) and 14 (4-and)
            for step in [10, 14]:
                if random.random() < 0.55:
                    t = jitter(grid_tick(bar * 16 + step, swing), 18, bpm)
                    vel = v(55, 10)
                    events.append((t, root_mid, vel, int(S16 * 0.6)))
                    events.append((t + 10, root_mid + 4, v(48, 8), int(S16 * 0.5)))

        elif style == 'stab':
            # Beat 2 (step 4) or beat 4 (step 12), staccato 2-note
            step = random.choice([4, 12])
            if random.random() < 0.60:
                t = jitter(grid_tick(bar * 16 + step, swing), 15, bpm)
                vel = v(60, 10)
                events.append((t, root_mid, vel, int(S16 * 0.35)))
                events.append((t, fifth,    vel, int(S16 * 0.35)))

        elif style == 'breath':
            # Long tone on chord root at start of every 2nd bar
            if (bar - start_bar) % 2 == 0 and random.random() < 0.65:
                t = jitter(grid_tick(bar * 16, swing), 20, bpm)
                events.append((t, root_mid + 12, v(45, 8), int(BAR * 1.8)))

        elif style == 'pop':
            # Short bright attacks on root/3rd, off-beat
            for step in [2, 6, 10, 14]:
                if random.random() < 0.35:
                    note = root_mid if random.random() < 0.6 else root_mid + 4
                    t = jitter(grid_tick(bar * 16 + step, swing), 12, bpm)
                    events.append((t, note + 12, v(65, 10), int(S16 * 0.4)))

        elif style == 'fill':
            # 2-3 note jazz fill at last bar of every 4-bar phrase
            if (bar - start_bar) % 4 == 3 and random.random() < 0.70:
                fill_notes = [root_mid + 12, root_mid + 14, root_mid + 16]
                for fi, fn in enumerate(fill_notes[:random.randint(2, 3)]):
                    t = jitter(grid_tick(bar * 16 + 10 + fi * 2, swing), 18, bpm)
                    events.append((t, fn, v(55, 10), int(S16 * 0.55)))

    return events


# GM/GS drum kit program numbers for percussion channel (ch 9).
# 0=Standard, 8=Room, 16=Power, 24=Electronic, 25=TR-808, 32=Jazz, 40=Brush.
# Non-zero programs are ignored by GM-only soundfonts (falls back to Standard),
# but GS/SF3 soundfonts select a genuinely different drum kit — audible variety.
_SUBGENRE_DRUM_KITS: dict[str, list[int]] = {
    'hip_hop_lofi': [0, 24, 25],   # Standard / Electronic / TR-808
    'lofi_phonk':   [24, 25],      # Electronic / TR-808 for phonk character
    'dark_lofi':    [0, 8],        # Standard / Room (darker, more reverb)
    'nujabes':      [0, 32],       # Standard / Jazz kit
    'lofi_jazz':    [32, 40],      # Jazz / Brush kit
    'jazz_cafe':    [32, 40],
    'bossa_lofi':   [40, 32],      # Brush / Jazz
    'ambient':      [40, 8],       # Brush / Room (very soft)
    'piano_lofi':   [40, 32],
    'lofi_classical': [40, 32],
    'vaporwave':    [24, 0],       # Electronic / Standard
    'neo_soul':     [0, 8],
    'chill_beats':  [0, 8],
    'lo_fi_funk':   [0, 16],       # Standard / Power (punchy)
}
_DEFAULT_DRUM_KIT_POOL = [0, 0, 0, 8, 32]  # mostly Standard, occasional variety

# Scale modal lift for break section: shift to relative major 35% of the time
_SCALE_MODAL_LIFT = {
    'pent':   'major_pent',
    'dorian': 'major_pent',
    'phryg':  'pent',         # partial lift — stays somewhat dark
    'major':  'lydian',       # major → Lydian = dreamy lift (raised 4th floats)
    'lydian': 'major',        # Lydian → back to grounded major
}


def build_midi(params, output_path):
    import mido

    bpm       = int(params['bpm'])
    prog_idx  = int(params['progression']) % len(PROGRESSIONS)
    key       = params.get('key', 'Am')
    swing     = float(params.get('swing', 0.58))
    mood      = params.get('mood', '')
    density   = params.get('melody_density', 'sparse')
    scale     = params.get('melody_scale', 'pent')
    walking   = bool(params.get('bass_walking', False))
    energy    = params.get('drum_energy', 'medium')
    sub_genre = params.get('sub_genre', 'chillhop')

    prog      = PROGRESSIONS[prog_idx]
    prog_bars = sum(d for _,d in prog)
    key_root  = KEY_ROOTS.get(key, 57)

    # Drum pattern selection (Groq picks specific patterns now)
    pat_a_idx = int(params.get('drum_pattern_a', random.randint(0, len(DRUM_PATTERNS)-1)))
    pat_b_idx = int(params.get('drum_pattern_b', random.randint(0, len(DRUM_PATTERNS)-1)))
    # A freshly-generated Euclidean pattern (see generate_euclidean_drum_pattern,
    # set ~20% of the time in pick_params) takes priority over the curated table.
    pat_a = params.get('drum_pattern_a_generated') or DRUM_PATTERNS[pat_a_idx % len(DRUM_PATTERNS)]
    pat_b = params.get('drum_pattern_b_generated') or DRUM_PATTERNS[pat_b_idx % len(DRUM_PATTERNS)]

    # Sub-genre config (piano/melody programs, forced energy)
    _cfg = _SUBGENRE_CONFIG.get(sub_genre, {})
    piano_prog = _cfg.get('piano', GM_RHODES)
    mel_prog   = _cfg.get('melody', 0)
    forced_energy = _cfg.get('energy')
    if forced_energy:
        energy = forced_energy

    # Drum energy modifier
    energy_mult = {'low': 0.78, 'medium': 1.0, 'high': 1.20}.get(energy, 1.0)

    # ── Song form ───────────────────────────────────────────────
    form_name = _FORM_BY_SUBGENRE.get(sub_genre, 'standard')
    form = _SONG_FORMS[form_name]

    # Total bars and fill bars (last bar before each section transition)
    TOTAL = sum(prog_bars * n for _, n in form)
    fill_bars = set()
    c = 0
    for _sec, _n in form:
        c += prog_bars * _n
        fill_bars.add(c - 1)

    # ── Break scale modulation (35% → relative major lift) ──────
    break_scale    = scale
    break_key_root = key_root
    if random.random() < 0.35 and scale in _SCALE_MODAL_LIFT:
        break_scale    = _SCALE_MODAL_LIFT[scale]
        break_key_root = key_root + 3   # relative major (+3 semitones: Am→C, Dm→F)

    # ── Motif: generate once, shared across all melody sections ─
    if scale == 'dorian':
        _motif_scale = get_dorian(key_root)
    elif scale == 'phryg':
        _motif_scale = get_phrygian(key_root)
    elif scale == 'major':
        _motif_scale = get_major(key_root)
    elif scale == 'lydian':
        _motif_scale = get_lydian(key_root)
    else:
        _motif_scale = get_pentatonic(key_root)
    track_motif = generate_motif(_motif_scale) if _motif_scale else None

    print(f"  BPM={bpm} key={key} prog={prog_idx} swing={int(swing*100)}% "
          f"energy={energy} sub={sub_genre} walk={walking} form={form_name} mood='{mood}' | {TOTAL} bars")

    # ── Build events ────────────────────────────────────────────
    piano_ev    = []
    bass_ev     = []
    drum_ev     = []
    mel_ev      = []
    pad_ev      = []
    cmelo_ev    = []
    texture_ev  = []
    sustain_ev  = []

    cursor = 0
    for sec_label, n_loops in form:
        sec_start = cursor
        sec_bars  = prog_bars * n_loops

        if sec_label == 'I':
            piano_ev   += build_chords(prog, sec_start, n_loops, swing, bpm)
            pad_ev     += build_pad(prog, sec_start, n_loops, swing, bpm)
            sustain_ev += build_sustain_pedal(prog, sec_start, n_loops, swing, bpm)
            bass_s = sec_start + min(2, prog_bars - 1)
            bass_ev += build_bass(prog, bass_s, 1, swing, bpm, False)
            hat_s = sec_start + min(2, prog_bars - 1)
            hat_b = sec_bars - (hat_s - sec_start)
            if hat_b > 0:
                drum_ev += build_intro_hats(hat_s, hat_b, swing, bpm)
            cmelo_ev += build_counter_melody(key_root, sec_start, sec_bars, swing, bpm)

        elif sec_label == 'A':
            piano_ev   += build_chords(prog, sec_start, n_loops, swing, bpm)
            bass_ev    += build_bass(prog, sec_start, n_loops, swing, bpm, walking)
            drum_ev    += build_drums(pat_a, sec_start, sec_bars, swing, bpm, fill_bars)
            pad_ev     += build_pad(prog, sec_start, n_loops, swing, bpm)
            mel_ev     += build_melody(key_root, sec_start, sec_bars, swing, bpm,
                                       'sparse', scale, motif=track_motif,
                                       progression=prog, prog_bars=prog_bars)
            sustain_ev += build_sustain_pedal(prog, sec_start, n_loops, swing, bpm)
            _tex = _SUBGENRE_TEXTURE.get(sub_genre)
            if _tex and random.random() < 0.50:
                texture_ev += build_texture(_tex[0], prog, sec_start, sec_bars, swing, bpm, _tex[1])

        elif sec_label == 'BR':
            piano_ev   += build_chords(prog, sec_start, n_loops, swing, bpm)
            bass_ev    += build_bass(prog, sec_start, n_loops, swing, bpm, walking)
            pad_ev     += build_pad(prog, sec_start, n_loops, swing, bpm)
            drum_ev    += build_break_hats(sec_start, sec_bars, swing, bpm)
            cmelo_ev   += build_counter_melody(break_key_root, sec_start, sec_bars, swing, bpm)
            sustain_ev += build_sustain_pedal(prog, sec_start, n_loops, swing, bpm)

        elif sec_label == 'B':
            piano_ev   += build_chords(prog, sec_start, n_loops, swing, bpm)
            bass_ev    += build_bass(prog, sec_start, n_loops, swing, bpm, walking)
            drum_ev    += build_drums(pat_b, sec_start, sec_bars, swing, bpm, fill_bars)
            pad_ev     += build_pad(prog, sec_start, n_loops, swing, bpm)
            mel_ev     += build_melody(key_root, sec_start, sec_bars, swing, bpm,
                                       'medium', scale, motif=track_motif,
                                       progression=prog, prog_bars=prog_bars)
            if sec_bars > prog_bars:
                cmelo_ev += build_counter_melody(key_root, sec_start + prog_bars,
                                                 sec_bars - prog_bars, swing, bpm)
            sustain_ev += build_sustain_pedal(prog, sec_start, n_loops, swing, bpm)
            _tex = _SUBGENRE_TEXTURE.get(sub_genre)
            if _tex and random.random() < 0.50:
                texture_ev += build_texture(_tex[0], prog, sec_start, sec_bars, swing, bpm, _tex[1])

        elif sec_label == 'O':
            piano_ev   += build_chords(prog, sec_start, n_loops, swing, bpm)
            bass_ev    += build_bass(prog, sec_start, n_loops, swing, bpm, False)
            pad_ev     += build_pad(prog, sec_start, n_loops, swing, bpm)
            cmelo_ev   += build_counter_melody(key_root, sec_start, sec_bars, swing, bpm)
            sustain_ev += build_sustain_pedal(prog, sec_start, n_loops, swing, bpm)
            od_bars = max(1, sec_bars // 2)
            od_raw  = build_drums(pat_a, sec_start, od_bars, swing, bpm)
            n_od = len(od_raw)
            od_raw = [(ev[0], ev[1], max(1, int(ev[2] * (1.0 - (i / max(1, n_od)) * 0.75))), ev[3])
                      for i, ev in enumerate(od_raw)]
            drum_ev += od_raw
            if sec_bars - od_bars > 0:
                drum_ev += build_intro_hats(sec_start + od_bars, sec_bars - od_bars, swing, bpm)

        cursor += sec_bars

    # ── Tension arc: replaces flat energy_mult with per-bar dynamic curve ──────
    drum_ev = _apply_tension_to_drums(drum_ev, TOTAL, energy_mult)

    # ── Assemble MIDI ───────────────────────────────────────────
    mid = mido.MidiFile(type=1, ticks_per_beat=PPQN)

    t0 = mido.MidiTrack()
    mid.tracks.append(t0)
    t0.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(bpm), time=0))
    t0.append(mido.MetaMessage('time_signature', numerator=4, denominator=4,
                               clocks_per_click=24, notated_32nd_notes_per_beat=8, time=0))
    t0.append(mido.MetaMessage('end_of_track', time=0))

    # Piano gets sustain pedal CC64 — adds natural ring to chord changes
    mid.tracks.append(abs_to_track(piano_ev, channel=0, program=piano_prog,
                                   cc_events=sustain_ev))
    # Bass program varies by sub-genre: fretless for jazz, synth bass for house/phonk,
    # slap for funk. Falls back to acoustic bass (32) for everything else.
    _BASS_PROG = {
        'lofi_jazz': 35, 'bossa_lofi': 35, 'jazz_cafe': 35, 'piano_lofi': 35,
        'hip_hop_lofi': 38, 'lofi_phonk': 38, 'lofi_house': 38, 'vaporwave': 38,
        'lo_fi_funk': 36, 'neo_soul': 36,
    }
    bass_prog = _BASS_PROG.get(sub_genre, GM_BASS)
    mid.tracks.append(abs_to_track(bass_ev, channel=1, program=bass_prog))
    # Rotate drum kit per track — GS/SF3 soundfonts honor non-zero kits;
    # GM-only soundfonts silently fall back to Standard (program 0).
    drum_kit = random.choice(_SUBGENRE_DRUM_KITS.get(sub_genre, _DEFAULT_DRUM_KIT_POOL))
    mid.tracks.append(abs_to_track(drum_ev, channel=9, program=drum_kit,
                                   bank_msb=127 if drum_kit != 0 else None))
    if mel_ev:
        mid.tracks.append(abs_to_track(mel_ev,    channel=2, program=mel_prog))
    # Pad: always present — fills air throughout
    mid.tracks.append(abs_to_track(pad_ev,    channel=3, program=GM_STRINGS))
    # Counter melody: instrument chosen per sub-genre
    if cmelo_ev:
        cmelo_prog = _cfg.get('cmelo', GM_WARM_PAD)
        mid.tracks.append(abs_to_track(cmelo_ev, channel=4, program=cmelo_prog))
    # Texture layer: secondary genre-specific instrument (guitar/organ/flute/marimba/trumpet)
    if texture_ev:
        tex_prog = _SUBGENRE_TEXTURE[sub_genre][0] if sub_genre in _SUBGENRE_TEXTURE else GM_WARM_PAD
        mid.tracks.append(abs_to_track(texture_ev, channel=5, program=tex_prog))

    mid.save(output_path)
    return output_path

# ─── RENDER ───────────────────────────────────────────────────────────────────

def midi_to_wav(midi_path: str, wav_path: str, soundfont: str | None = None) -> None:
    sf = soundfont or _pick_soundfont()
    # subprocess with capture_output=True — zero ALSA/Jack noise, isolated from parent process.
    # pyfluidsynth was tried here but its start() triggers PortAudio initialisation on this system,
    # which calls C-level abort() on assertion failure — uncatchable by Python exceptions.
    subprocess.run([
        'fluidsynth', '-ni',
        '-F', wav_path, '-r', '44100', '-T', 'wav', '-O', 's16',
        '-R', '0',           # disable FluidSynth reverb (pedalboard chain handles reverb)
        '-o', 'synth.reverb.active=no',
        '-C', '0',           # disable chorus (adds shimmer — not lo-fi)
        '-g', '3.0',         # raised gain: default 0.85 left signal at ~4% full scale,
                             # causing bitcrusher to quantize to only ~21-46 levels (noise).
                             # 3.0 brings signal to ~15% full scale for clean bit-reduction.
        sf, midi_path,
    ], check=True, capture_output=True)


# ─── ENTRY ────────────────────────────────────────────────────────────────────

def generate_track(index=0, concept_hint: str = None, genre_hint: str = None, song_dna: dict = None):
    print(f"\n[Track {index+1}] Picking parameters...")
    if song_dna is not None:
        # lofi-inator: use pre-computed musical DNA instead of random Groq params
        params = dict(song_dna)
        # Add minor per-track variation so tracks in the same cover aren't identical
        params['drum_pattern_b'] = (params.get('drum_pattern_b', 3) + index) % len(DRUM_PATTERNS)
        params['swing'] = round(min(0.70, max(0.58, params.get('swing', 0.62) + random.uniform(-0.03, 0.03))), 2)
        print(f"  [DNA] bpm={params.get('bpm')} key={params.get('key')} sub={params.get('sub_genre')}")
    else:
        params = pick_params(concept_hint=concept_hint, genre_hint=genre_hint)

    with tempfile.TemporaryDirectory() as tmp:
        midi_path = os.path.join(tmp, 'track.mid')
        raw_wav   = os.path.join(tmp, 'raw.wav')

        print(f"  [MIDI] Building...")
        build_midi(params, midi_path)
        chosen_sf = _pick_soundfont()
        print(f"  [FluidSynth] Rendering ({os.path.basename(chosen_sf)})...")
        midi_to_wav(midi_path, raw_wav, soundfont=chosen_sf)
        print(f"  [FX] Lo-fi chain ({params.get('sub_genre', '?')})...")
        ts = int(time.time())
        out = os.path.join(MUSIC_DIR, f'track_{ts}_{index:02d}.wav')
        from scripts.lofi_fx import apply_lofi_fx as _lofi_fx

        _lofi_fx(raw_wav, out,
                 sub_genre=params.get('sub_genre'),
                 bpm=params.get('bpm', 80),
                 energy=params.get('drum_energy', 'medium'))

        # Layer synthesized drum break — real FM+noise drums on top of the
        # MIDI render so every track has a different acoustic character.
        try:
            from scripts.drum_sampler import layer_drum_break as _layer_drums
            print(f"  [DRUMS] Layering synthetic breaks ({params.get('sub_genre', '?')})...")
            _layer_drums(out, out,
                         bpm=params.get('bpm', 80),
                         sub_genre=params.get('sub_genre', 'chillhop'),
                         volume=0.22,
                         swing=float(params.get('swing', 0.62)))
        except Exception as _de:
            print(f"  [DRUMS] Skipped ({_de})")

    # Save sidecar metadata for stream now-playing display
    with open(out + ".meta.json", "w", encoding="utf-8") as _mf:
        json.dump({
            "title": params.get("mood", "lofi dreams"),
            "genre": params.get("sub_genre", "lo-fi hip hop"),
        }, _mf)

    print(f"  ✓ {out} ({os.path.getsize(out)//1024//1024} MB)")
    return out


def _build_diverse_params(count: int, concept_hint=None, genre_hint=None) -> list[dict]:
    """
    Pre-compute N diverse param dicts for a multi-track video.
    Track 0: call pick_params (Groq or random) as anchor.
    Tracks 1+: random fallback with forced sub-genre + key rotation so no two
               adjacent tracks share the same sub-genre or key.
    This replaces calling pick_params() N times with the same prompt (which
    produces near-identical Groq outputs and monotonous-sounding videos).
    """
    all_keys  = list(KEY_ROOTS.keys())
    all_subs  = list(_SUBGENRE_CONFIG.keys())
    n_pats    = len(DRUM_PATTERNS)

    # Track 0: anchor via Groq
    anchor = pick_params(concept_hint=concept_hint, genre_hint=genre_hint)
    param_sets = [anchor]

    if count == 1:
        return param_sets

    # Build rotation pools — shuffle to avoid always starting at the same place
    sub_pool  = [s for s in all_subs if s != anchor.get('sub_genre')]
    key_pool  = [k for k in all_keys if k != anchor.get('key')]
    random.shuffle(sub_pool)
    random.shuffle(key_pool)

    for i in range(1, count):
        # Rotate sub-genre pool
        if not sub_pool:
            sub_pool = [s for s in all_subs if s != param_sets[-1].get('sub_genre')]
            random.shuffle(sub_pool)
        sub = sub_pool.pop(0)

        # Rotate key pool
        if not key_pool:
            key_pool = [k for k in all_keys if k != param_sets[-1].get('key')]
            random.shuffle(key_pool)
        key = key_pool.pop(0)

        cfg     = _SUBGENRE_CONFIG[sub]
        pat_a   = random.choice(cfg['drum_pats']) % n_pats
        others  = [p % n_pats for p in cfg['drum_pats'] if p % n_pats != pat_a] or [pat_a]
        pat_b   = random.choice(others)

        # Alternate mood/concept so long videos have a light/dark arc
        mood = concept_hint or anchor.get('mood', 'lofi dreams')
        if i % 4 == 2:
            mood = random.choice([
                '3am and the city is finally quiet',
                'borrowed light from a window across the street',
                'the weight of almost',
            ])
        elif i % 4 == 0:
            mood = random.choice([
                'sunday morning light through the curtains',
                'slow mornings that taste like possibility',
                'the groove that keeps you moving forward',
            ])

        diverse_energy = cfg.get('energy') or random.choice(['low', 'medium', 'high'])
        track_params = {
            'key':            key,
            'progression':    random.choice(cfg['progs']),
            'bpm':            random.randint(*cfg['bpm']),
            'swing':          round(random.uniform(0.58, 0.68), 2),
            'mood':           mood,
            'melody_density': random.choice(['sparse', 'medium']),
            'melody_scale':   random.choice(cfg['scale']),
            'bass_walking':   random.random() < 0.4,
            'drum_pattern_a': pat_a,
            'drum_pattern_b': pat_b,
            'drum_energy':    diverse_energy,
            'sub_genre':      sub,
        }
        # Same ~20% independent chance for a generated Euclidean pattern as
        # the single-track pick_params() path — see generate_euclidean_drum_pattern.
        energy_f = _DRUM_ENERGY_TO_FLOAT.get(diverse_energy, 0.55)
        complexity_f = round(random.uniform(0.3, 0.8), 2)
        if random.random() < 0.20:
            track_params['drum_pattern_a_generated'] = generate_euclidean_drum_pattern(energy_f, complexity_f)
        if random.random() < 0.20:
            track_params['drum_pattern_b_generated'] = generate_euclidean_drum_pattern(energy_f, complexity_f)
        param_sets.append(track_params)

    return param_sets


def generate_tracks(count=3, concept_hint: str = None, genre_hint: str = None, song_dna: dict = None):
    import concurrent.futures
    print(f"[MUSIC] Generating {count} track(s)...")

    # For standard generation (no song_dna), pre-compute diverse params per track
    # so each track has a unique sub-genre, key, BPM, and progression.
    # Without this, all N tracks call pick_params() with the same prompt → identical Groq output.
    if song_dna is None and count > 1:
        param_sets = _build_diverse_params(count, concept_hint, genre_hint)
        print(f"  [MUSIC] Track plan: {' → '.join(p['sub_genre'] for p in param_sets)}")
    else:
        param_sets = None

    # Parallel generation — FluidSynth and ffmpeg are subprocess calls so
    # threads release the GIL; 3 workers caps CPU without overwhelming Groq.
    workers = min(count, 3)
    paths = []

    def _run(i):
        dna = param_sets[i] if param_sets else song_dna
        chint = None if param_sets else concept_hint
        ghint = None if param_sets else genre_hint
        return generate_track(i, concept_hint=chint, genre_hint=ghint, song_dna=dna)

    if workers <= 1:
        for i in range(count):
            try:
                paths.append(_run(i))
            except Exception as e:
                print(f"  [ERROR] Track {i}: {e}")
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_run, i): i for i in range(count)}
            for fut in concurrent.futures.as_completed(futs):
                i = futs[fut]
                try:
                    paths.append(fut.result())
                except Exception as e:
                    print(f"  [ERROR] Track {i}: {e}")

    print(f"\n[MUSIC] {len(paths)}/{count} tracks ready.")
    return paths


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    generate_tracks(n)
