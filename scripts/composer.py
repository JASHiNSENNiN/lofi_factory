"""
composer.py — v3 (Alive Edition)
==============================================
Every track is unique. Infinite combinations guaranteed by:
  · pick_params() procedurally picks personality (key, progression, bpm, swing,
    density, energy) — fully procedural, no external generators
  · Multiple voicings per chord — rotates randomly each hit
  · 4 drum patterns + per-bar mutation + fills at section boundaries
  · Hi-hat 16th-note runs every 4 bars for energy bursts
  · Quiet pad layer (strings) under chords for depth
  · Sparse / dense melody toggle per track, driven by a per-track tension arc
  · Syncopated bass with walking fill option
  · All timing + velocity fully humanized per instrument

Math: 14 keys × 51 progressions × BPM/swing ranges per sub-genre
      × drum-pattern combos × voicing variants × melody/bass randomness
      = effectively infinite unique tracks
"""

import os, sys, time, random, json, subprocess, tempfile, math, threading
from itertools import product as _iproduct

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

# GM Programs (0-indexed) — moved to scripts/gm_instruments.py (pure relocation)
from scripts.gm_instruments import *  # noqa: F401,F403
from scripts import genre_presets

# ─── SUB-GENRE CONFIG TABLE ───────────────────────────────────────────────────
# Unified per-sub-genre settings — one config/genres/<key>.yaml per subgenre,
# loaded via scripts/genre_presets.py. _SUBGENRE_CONFIG/_SWING_RANGE/
# _COZY_SUBGENRES are built further down (after PROGRESSIONS/DRUM_PATTERNS
# are defined — genre_presets does load-time bounds validation of
# progression_indices/drum_pattern_indices against those tables).
_SWING_DEFAULT = (0.58, 0.68)


# GM Drum notes (channel 9)
KICK  = 36
SNARE = 38
RIM   = 37
CHH   = 42
OHH   = 46
RIDE  = 51
CLAP  = 39
COWBELL = 56
SHAKER = 82
CRASH = 49

# ─── MULTIPLE VOICINGS PER CHORD ─────────────────────────────────────────────
# Each chord has 3-4 voicing options. build_chords picks randomly each time.
# This alone guarantees no two bars sound identical.

VOICING_OPTIONS = {
    # 'q' suffix = a quartal (4ths-stacked) voicing appended as an alternate
    # choice for this existing chord, not a new chord symbol -- research/
    # theory/harmony-voicings.md's quartal-harmony finding: minor chords
    # voice quartally most naturally, idiomatic McCoy Tyner/modal-jazz and
    # neo-soul texture the repo's nujabes/neo-soul-flavored progressions
    # already lean toward.
    'Am7':   [[57,60,64,67], [60,64,67,69], [52,57,64,67], [57,60,64,67,71], [64,67,69,72], [57,62,67,72]],
    'Am9':   [[57,60,64,67,71], [60,64,67,71], [52,60,64,71], [57,64,69,71]],
    'Dm7':   [[50,53,57,60], [53,57,60,62], [50,53,57,60,64], [45,50,57,60], [53,57,62,65], [50,55,60,65]],
    'Dm9':   [[50,53,57,60,64], [53,57,60,64], [50,57,60,64], [53,60,62,65]],
    'Em7':   [[52,55,59,62], [55,59,62,64], [52,59,62,67], [55,59,64,67]],
    'Gm7':   [[55,58,62,65], [58,62,65,67], [55,62,65,70], [50,55,62,65], [58,65,67,70]],
    'Gm9':   [[55,58,62,65,69], [58,62,65,69], [55,62,69,70], [50,62,65,69], [58,65,69,74]],
    'Cm7':   [[48,51,55,58], [51,55,58,60], [48,55,58,63], [46,51,55,60], [51,58,60,63]],
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
    'C7':    [[48,52,55,58], [52,55,58,60], [48,55,58,64], [52,58,62,67]],
    'Bb7':   [[58,62,65,68], [62,65,68,70], [58,65,68,74], [62,68,70,74]],
    'D7':    [[50,54,57,60], [54,57,60,62], [50,57,60,66], [54,60,62,66]],
    'D9':    [[50,54,57,60,64], [54,57,60,64], [50,57,60,64,69]],
    # Secondary dominant voicings used in new progressions
    'F7':    [[53,57,60,63], [57,60,63,65], [53,60,63,69], [57,63,67,72]],
    'A7':    [[57,61,64,67], [61,64,67,69], [57,64,67,73], [61,67,69,73]],

    # Modal-interchange / borrowed-chord additions (research/theory/
    # harmony-voicings.md "Concrete additions") — major-key tonics needed so
    # the orphaned A/D major keys have a real I chord to borrow iv/bIII/bVI/
    # bVII against (those borrowed chords reuse Dm7/Fmaj7/Gmaj7/Cmaj7/Gm7/
    # Bbmaj7, all already present above).
    'Amaj7': [[57,61,64,68], [61,64,68,69], [52,57,64,68], [61,68,69,73]],
    'Dmaj7': [[50,54,57,61], [54,57,61,62], [45,50,57,61], [54,61,62,66]],

    # Minor ii-V-i siblings (research: generalizing the existing Bm7b5-
    # E7b9-Am7 pattern into the previously-orphaned minor keys, plus the
    # Gm-context sibling the research table gives verbatim).
    'F#m7b5': [[54,57,60,64], [57,60,64,66], [54,60,64,69], [57,60,66,69]],
    'B7b9':   [[59,63,69,72], [63,69,72,75], [59,69,72,75]],
    'G#m7b5': [[56,59,62,66], [59,62,66,68], [56,62,66,71], [59,62,68,71]],
    'C#7b9':  [[61,65,71,74], [65,71,74,77], [61,71,74,77]],
    'F#m7':   [[54,57,61,64], [57,61,64,66], [49,54,61,64], [57,61,64,69]],
    'C#m7b5': [[61,64,67,71], [64,67,71,73], [61,67,71,76], [64,67,73,76]],
    'F#7b9':  [[54,58,64,67], [58,64,67,70], [54,64,67,70]],
    'Bm7':    [[59,62,66,69], [62,66,69,71], [54,59,66,69], [62,66,69,74]],
    'Fm7b5':  [[53,56,59,63], [56,59,63,65], [53,59,63,68], [56,59,65,68]],
    'Bb7b9':  [[58,62,68,71], [62,68,71,74], [58,68,71,74]],
    'Ebm7':   [[63,66,70,73], [66,70,73,75], [58,63,70,73], [66,70,73,78]],
    'Am7b5':  [[57,60,63,67], [60,63,67,69], [57,63,67,72], [60,63,69,72]],
    'D7b9':   [[50,54,60,63], [54,60,63,66], [50,60,63,66]],

    # Dedicated tritone-substitution target for G7 (see _SEC_DOM_SUBS below).
    # Bb7 previously served double duty as both a tritone-sub target *and*
    # Eb's diatonic V7 -- Db7 disambiguates true tritone-sub usage.
    'Db7':    [[61,65,68,71], [65,68,71,73], [61,68,71,77], [65,71,73,77]],

    # Extended dominant/minor-11th/6th-chord vocabulary (research/theory/
    # harmony-voicings.md "Concrete additions" table -- the remaining gaps
    # after the modal-interchange/minor-ii-V-i/tritone-sub work above).
    'G13':    [[55,59,62,64,69], [59,62,64,69,71]],   # dominant 13, cheap _CHORD_EXTEND_UP tension option
    'G7alt':  [[55,59,65,68], [59,65,68,70]],          # 7(b9) and 3-b7-b9-#9 altered-dominant voicings
    'Am11':   [[57,60,64,67,72], [60,64,67,72,74]],    # minor 11ths are consonant, no #11 needed
    'Dm11':   [[50,53,57,60,65]],
    'Am6':    [[57,60,64,66], [60,64,66,69]],          # 6th-chord color: softer than maj7/m7, common Rhodes voicing
    'Cmaj6':  [[60,64,67,69]],

    # Sparse modal drone chords (research/subgenres/lofi_world.md, Phase 11
    # step 1): world-fusion harmony sources are explicit that chords should
    # stay minimal/modal -- a held drone or simple sus/add9 vamp rather than
    # jazz ii-V-I turnarounds, to preserve raga/maqam melodic color instead
    # of competing with it. Previously absent -- every existing progression
    # in this table is built from jazz 7th/9th-family chords.
    'Amadd9': [[57,60,64,71]],   # A minor triad + 9th, no 7th -- open, modal, not jazz-functional
    'Dmsus4': [[50,55,57,62]],   # D + sus4 (no 3rd at all) -- ambiguous, drone-like
}

# Bass root notes (octave 2)
BASS_ROOTS = {
    'Am7':45,'Am9':45,'Dm7':38,'Dm9':38,'Em7':40,'Gm7':43,'Gm9':43,
    'Cm7':48,'Fm7':41,'Bm7b5':47,'Cmaj7':48,'Cmaj9':48,'Fmaj7':41,
    'Fmaj9':41,'Fmaj7s':41,'Gmaj7':43,'Bbmaj7':46,'Ebmaj7':51,
    'G7':43,'G7b9':43,'E7':40,'E7b9':40,'C7':48,'Bb7':46,
    'D7':38,'D9':38,
    'F7':41,'A7':45,
    # Modal-interchange tonics + minor ii-V-i siblings (see VOICING_OPTIONS
    # comment above) — bass roots follow the file's existing convention of
    # one fixed low-register value per pitch class, shared across every
    # chord quality built on that root (e.g. F#=42 for both F#m7b5/F#m7/F#7b9).
    'Amaj7':45,'Dmaj7':38,
    'F#m7b5':42,'B7b9':47,'G#m7b5':44,'C#7b9':49,'F#m7':42,
    'C#m7b5':49,'F#7b9':42,'Bm7':47,'Fm7b5':41,'Bb7b9':46,'Ebm7':51,
    'Am7b5':45,'D7b9':38,
    'Db7':49,
    # Extended dominant/minor-11th/6th-chord vocabulary (see VOICING_OPTIONS
    # comment above) -- same root pitch class as the existing 7th/9th chord
    # on that root (G13/G7alt share G7's root 43; Am11 shares Am7's 45; etc).
    'G13':43,'G7alt':43,'Am11':45,'Dm11':38,'Am6':45,'Cmaj6':48,
    'Amadd9':45,'Dmsus4':38,
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
    'Amaj7': (4, 11), 'Dmaj7': (4, 11),
    'F#m7b5': (3, 10), 'B7b9':  (4, 10),
    'G#m7b5': (3, 10), 'C#7b9': (4, 10),
    'F#m7':   (3, 10), 'C#m7b5': (3, 10),
    'F#7b9':  (4, 10), 'Bm7':   (3, 10),
    'Fm7b5':  (3, 10), 'Bb7b9': (4, 10),
    'Ebm7':   (3, 10), 'Am7b5': (3, 10), 'D7b9': (4, 10),
    'Db7':    (4, 10),
    # Extended dominant/minor-11th/6th-chord vocabulary. G13/G7alt/Am11/Dm11
    # keep the standard (3rd, 7th) shape -- they're still 7th-family chords
    # with extensions layered on top. Am6/Cmaj6 have no 7th at all, so the
    # second slot holds the 6th's semitone offset (9) in that position
    # instead, per the research doc's "(3,9)-style (6th not 7th)" note.
    'G13':    (4, 10), 'G7alt': (4, 10),
    'Am11':   (3, 10), 'Dm11':  (3, 10),
    'Am6':    (3, 9),  'Cmaj6': (4, 9),
    # Sus/add9 drone chords -- no real "3rd defines quality" for a sus
    # chord, but a (interval, 9th) tuple keeps every VOICING_OPTIONS key
    # consistently present in this table.
    'Amadd9': (3, 14), 'Dmsus4': (5, 14),
}

# Tension-driven chord-extension escalation (build_chords()'s `tension` param):
# near peak tension, a plain 7th chord can upgrade to its denser 9th-family
# equivalent. Every entry here is a real VOICING_OPTIONS/BASS_ROOTS/
# _GUIDE_TONES key already — no new voicings introduced.
_CHORD_EXTEND_UP = {
    'Am7': 'Am9', 'Dm7': 'Dm9', 'Gm7': 'Gm9', 'Cmaj7': 'Cmaj9',
    'Fmaj7': 'Fmaj9', 'G7': 'G7b9', 'D7': 'D9', 'E7': 'E7b9',
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
    [('Fmaj9',2),('Cmaj9',2),('Am9',2),('G13',2)],    # 17 floating morning major
    [('Gmaj7',2),('Em7',2),('Am9',2),('Fmaj7',2)],      # 18 G major arc (I-vi-ii-IV)
    # Chill vamps
    [('Am9',4),('Cmaj9',4)],                             # 19 chill 2-chord vamp
    [('Fmaj9',2),('Em7',2),('Dm9',2),('Cmaj9',2)],      # 20 descending chill IV-iii-ii-I
    # Bright / cozy major progressions
    [('Fmaj9',2),('G13',2),('Am9',2),('Cmaj9',2)],    # 21 IV-V-vi-I uplifting
    [('Cmaj9',2),('G13',2),('Am9',2),('Fmaj9',2)],    # 22 I-V-vi-IV (iconic cozy pop loop)
    [('G13',2),('Cmaj9',2),('Fmaj9',2),('Cmaj9',2)],  # 23 V-I-IV-I resolution arc
    [('Am9',1),('G13',1),('Fmaj9',1),('Cmaj9',1)],    # 24 quick major turn (quarter note chords)
    [('Cmaj9',2),('Em7',2),('Fmaj9',2),('G13',2)],    # 25 I-iii-IV-V warm major build
    # Funk / soul
    [('Dm9',1),('G7',1),('Cmaj9',1),('Fmaj9',1)],       # 26 ii-V-I-IV jazz-funk turn
    [('Am9',2),('Fmaj9',2),('G7',2),('Am9',2)],          # 27 neo-soul groove vamp
    # Jazz major turnarounds (C/G/F major key contexts)
    [('Cmaj7',2),('Am9',2),('Dm9',2),('G7',2)],          # 28 I-vi-ii-V jazz (C major)
    [('Fmaj9',2),('Em7',2),('Am9',2),('D7',2)],           # 29 IV-iii-vi-V (G major arc)
    [('Gm9',2),('Cm7',2),('F7',2),('Bbmaj7',2)],         # 30 vi-ii-V-I gospel cycle in Bb
    # Extended jazz cycles
    [('Fm7',2),('Bb7',2),('Ebmaj7',2),('Cm7',2)],        # 31 Cm/Fm jazz cycle (European)
    [('Bm7b5',1),('E7b9',1),('Am7',2),('D7',2)],          # 32 extended ii-V-i with deceptive
    [('Dm9',1),('G7',1),('Cmaj9',1),('Am9',1)],           # 33 ii-V-I-vi quick rotation
    [('Gm9',2),('C7',2),('Fmaj9',2),('Ebmaj7',2)],        # 34 Gm-C7-Fmaj9 reharmonized
    # Modal / minimal drifts
    [('Fmaj9',4),('Cmaj9',4)],                             # 35 2-chord Lydian drift (meditative)
    [('Am7',3),('Cmaj9',1)],                               # 36 ultra-minimal Am vamp
    [('Am9',2),('Fmaj7s',2),('G13',2),('Em7',2)],       # 37 Lydian floating arc
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
    [('Cmaj9',2),('Fmaj9',2),('G13',2),('Am9',2)],       # 46 I-IV-V-vi in C
    [('Bbmaj7',2),('Gm9',2),('Cm7',2),('Ebmaj7',2)],       # 47 Bb major jazz swing
    # City pop / modern Japanese
    [('Fmaj9',2),('G13',2),('Em7',2),('Am9',2)],         # 48 IV-V-iii-vi city pop
    [('Cmaj9',2),('Em7',2),('G13',1),('Am9',1)],          # 49 I-iii-V-vi city pop
    [('Ebmaj7',2),('Bb7',2),('Gm7',2),('Cm7',2)],        # 50 Eb warm jazz cycle

    # ── Modal-interchange / borrowed-chord + minor ii-V-i additions ──────
    # (research/theory/harmony-voicings.md "Concrete additions" table).
    # Append-only: existing indices 0-50 are untouched. Prioritizes the six
    # keys that were previously orphaned in KEY_ROOTS/PROGRESSION_KEY (Em,
    # F#m, Bm, Ebm, A, D — see the PROGRESSION_KEY comment above) so the
    # existing 14-key palette actually gets exercised.
    [('Amaj7',2),('Cmaj7',1),('Dm7',1),('Fmaj7',1),('Gmaj7',1),('Amaj7',2)],  # 51 A major: I-bIII-iv-bVI-bVII-I (modal interchange)
    [('Dmaj7',2),('Fmaj7',1),('Gm7',1),('Bbmaj7',1),('Cmaj7',1),('Dmaj7',2)], # 52 D major: I-bIII-iv-bVI-bVII-I (modal interchange)
    [('F#m7b5',1),('B7b9',1),('Em7',2)],                    # 53 Em minor ii-V-i
    [('G#m7b5',1),('C#7b9',1),('F#m7',2)],                  # 54 F#m minor ii-V-i
    [('C#m7b5',1),('F#7b9',1),('Bm7',2)],                   # 55 Bm minor ii-V-i
    [('Fm7b5',1),('Bb7b9',1),('Ebm7',2)],                   # 56 Ebm minor ii-V-i
    [('Cmaj9',2),('Ebmaj7',1),('Fm7',1),('Cmaj9',2),('Bbmaj7',2)],  # 57 C major: I-bIII-iv-I-bVII (research example, verbatim)
    [('Am7b5',1),('D7b9',1),('Gm7',2)],                     # 58 Gm minor ii-V-i (second sibling, research example)

    # ── Sparse modal drone (research/subgenres/lofi_world.md, Phase 11) ──
    # Long-held sus/add9 vamp instead of a jazz turnaround -- lets a
    # phrygian-dominant/dorian melodic line (sitar/koto) carry the
    # expressive weight instead of chord movement, per that doc's harmony
    # guidance. Long durations (4+4 bars) are deliberate -- a drone holds,
    # it doesn't cycle through changes.
    [('Amadd9',4),('Dmsus4',4)],                            # 59 sparse modal drone vamp
    # 60: the "royal road" IV-V-iii-vi in G, the signature anime/J-pop move
    # (#48 is the same in C). masterthescore.com, unison.audio.
    [('Cmaj9',2),('D9',2),('Bm7',2),('Em7',2)],             # 60
]

# Real tonal center of each PROGRESSIONS entry (functional-harmony read: which
# chord actually functions as "home" — the first chord for most vamps, but the
# resolution target for progressions that build toward it, e.g. #29's IV-iii-vi-V
# arc lands in G even though it starts on Fmaj9). Parallel to PROGRESSIONS by
# index. This is what pick_params() now derives `key` from — previously `key`
# was picked fully independently of `prog`, which meant a melody scale could be
# built in a key with zero relation to the chords actually playing underneath
# (6 of the old 14 KEY_ROOTS entries — Em, F#m, Bm, Ebm, A, D — were never the
# real center of any progression at all, so picking them was a guaranteed
# mismatch every time).
PROGRESSION_KEY = [
    'Am', 'C',  'Am', 'Am', 'C',  'Dm', 'Am', 'Am', 'F',  'Eb',   #  0- 9
    'Am', 'C',  'C',  'Am', 'Cm', 'Gm', 'C',  'C',  'G',  'Am',   # 10-19
    'C',  'C',  'C',  'C',  'C',  'C',  'C',  'Am', 'C',  'G',    # 20-29
    'Bb', 'Eb', 'Am', 'C',  'F',  'F',  'Am', 'Am', 'Dm', 'Am',   # 30-39
    'C',  'Cm', 'Bb', 'Am', 'G',  'G',  'C',  'Bb', 'C',  'C',    # 40-49
    'Eb',                                                        # 50
    'A',  'D',  'Em', 'F#m', 'Bm', 'Ebm', 'C', 'Gm',             # 51-58
    'Am',                                                        # 59 (sparse modal drone -- Amadd9-centered)
    'G',                                                         # 60 royal road in G
]
assert len(PROGRESSION_KEY) == len(PROGRESSIONS)

# Secondary dominant / tritone substitutions — applied by maybe_sub_chord()
# key = chord being approached; value = (substitute_chord, probability), OR
# a list of such tuples when more than one substitute is available (each
# rolled independently, first hit wins) -- used for G7/G7b9 below, which
# previously pointed only at Bb7. Bb7 is *also* Eb's diatonic V7 (it's the
# real chord of progressions like #9/#31/#42), so a G7 -> Bb7 substitution
# is ambiguous with plain diatonic Eb harmony. Db7 is the "purer"
# unambiguous tritone-sub target (research/theory/harmony-voicings.md):
# it shares no diatonic role anywhere else in PROGRESSIONS, so seeing Db7
# unambiguously signals "tritone substitution happened here."
_SEC_DOM_SUBS = {
    'Fmaj7':  ('C7',   0.15),   # C7 → Fmaj7 (V7/IV)
    'Fmaj9':  ('C7',   0.15),
    'Am7':    ('E7',   0.12),   # E7 → Am7 (V7/vi)
    'Am9':    ('E7',   0.12),
    'Cmaj7':  ('G7',   0.10),   # G7 → Cmaj7 (V7/I)
    'Cmaj9':  ('G7',   0.10),
    # Bb7 = tritone sub for G7 (shares 3rd/7th enharmonically); Db7 = the
    # dedicated, unambiguous tritone-sub target (see comment above).
    'G7':     [('Bb7', 0.08), ('Db7', 0.06)],
    'G7b9':   [('Bb7', 0.08), ('Db7', 0.06)],
    'Ebmaj7': ('Bb7',  0.10),   # Bb7 → Ebmaj7 (V7/I in Eb) -- diatonic use of Bb7, unrelated to the tritone sub above
    'Gm7':    ('D7',   0.10),   # D7 → Gm7 (V7/iv)
    'Gm9':    ('D7',   0.10),
    'Cm7':    ('G7',   0.10),   # G7 → Cm7 (V7/iv in Fm context)
    'Dm7':    ('A7',   0.09),   # A7 → Dm7 (V7/ii)
    'Dm9':    ('A7',   0.09),
    'Bbmaj7': ('F7',   0.09),   # F7 → Bbmaj7 (V7/I in Bb)
}

def maybe_sub_chord(chord_name, position_in_prog):
    """Occasionally replace chord with secondary dominant or tritone sub.
    Never subs position 0 (preserves tonic feel at start of progression).
    _SEC_DOM_SUBS entries are either a single (substitute, probability)
    tuple or a list of them (e.g. G7's Bb7/Db7 pair) -- each candidate is
    rolled independently in order, first hit wins."""
    if position_in_prog == 0:
        return chord_name
    sub_info = _SEC_DOM_SUBS.get(chord_name)
    if not sub_info:
        return chord_name
    candidates = sub_info if isinstance(sub_info, list) else [sub_info]
    for target, prob in candidates:
        if random.random() < prob:
            return target
    return chord_name


# Chord names that appear as secondary-dominant / tritone-sub *targets* in
# _SEC_DOM_SUBS -- i.e. dominant chords that function as tension resolving
# somewhere else, not a diatonic chord in their own right at that moment.
# build_melody() uses this to know when a phrase can reach for get_altered()
# instead of the track's main scale (research/theory/scales-modes-gaps.md:
# altered scale over a dominant == lydian dominant of its tritone-sub root,
# melodically unifying with this substitution machinery).
_SEC_DOM_SUB_TARGETS = {
    target for subs in _SEC_DOM_SUBS.values()
    for target, _ in (subs if isinstance(subs, list) else [subs])
}


# ─── PROCEDURAL PROGRESSION GENERATOR (Markov, mined from curated table) ──────

_PROGRESSION_MARKOV_CACHE: dict | None = None
_JAZZY_MARKERS = ('9', 'b9', '#9', '11', '13', '7b5', '7#5', 'dim', 'aug')


def _build_progression_markov() -> dict:
    """
    Lazily build (and cache) a first-order Markov chain over chord-symbol
    bigrams, mined from the curated PROGRESSIONS table itself — real
    statistical structure learned from 51 hand-composed progressions, not an
    LLM call. Also captures start-chord frequency (which chords tend to open
    a progression) and the empirical bar-duration distribution.
    """
    global _PROGRESSION_MARKOV_CACHE
    if _PROGRESSION_MARKOV_CACHE is not None:
        return _PROGRESSION_MARKOV_CACHE

    transitions: dict[str, dict[str, int]] = {}
    start_counts: dict[str, int] = {}
    duration_counts: dict[int, int] = {}

    for prog in PROGRESSIONS:
        if not prog:
            continue
        start_counts[prog[0][0]] = start_counts.get(prog[0][0], 0) + 1
        for _chord_name, dur in prog:
            duration_counts[dur] = duration_counts.get(dur, 0) + 1
        for i in range(len(prog) - 1):
            cur, nxt = prog[i][0], prog[i + 1][0]
            transitions.setdefault(cur, {})
            transitions[cur][nxt] = transitions[cur].get(nxt, 0) + 1

    _PROGRESSION_MARKOV_CACHE = {
        'transitions': transitions,
        'start_counts': start_counts,
        'duration_counts': duration_counts,
    }
    return _PROGRESSION_MARKOV_CACHE


def generate_progression(length: int = 4, jazziness: float = 0.5,
                          seed_chord: str | None = None) -> list[tuple[str, int]]:
    """
    Procedurally generate a fresh chord progression by walking a Markov chain
    built from the curated PROGRESSIONS table's chord-to-chord transitions —
    real statistical structure, not an LLM call, and not just re-picking a
    whole progression from the fixed 51-entry table. `jazziness` in [0,1]
    biases sampling toward extended/altered chords. Applies the same
    maybe_sub_chord() secondary-dominant substitution used by curated
    progressions, so generated and curated progressions share the same
    harmonic-coloring pass.
    """
    markov = _build_progression_markov()
    transitions     = markov['transitions']
    start_counts    = markov['start_counts']
    duration_counts = markov['duration_counts']

    all_chords = list(transitions.keys()) or list(VOICING_OPTIONS.keys())
    if not all_chords:
        return [('Am7', 4)]

    starts = list(start_counts.keys()) or all_chords
    start_weights = [start_counts.get(c, 1) for c in starts]
    current = (seed_chord if (seed_chord and seed_chord in all_chords)
               else random.choices(starts, weights=start_weights, k=1)[0])

    dur_choices = list(duration_counts.keys()) or [2]
    dur_weights = [duration_counts[d] for d in dur_choices]

    result: list[tuple[str, int]] = []
    for i in range(length):
        chord = maybe_sub_chord(current, i)
        dur   = random.choices(dur_choices, weights=dur_weights, k=1)[0]
        result.append((chord, dur))

        next_options = transitions.get(current)
        if not next_options:
            current = random.choices(starts, weights=start_weights, k=1)[0]
            continue

        candidates = list(next_options.keys())
        weights = [float(next_options[c]) for c in candidates]
        if jazziness > 0:
            weights = [
                w * (1.0 + jazziness * 2.0) if any(m in c for m in _JAZZY_MARKERS) else w
                for c, w in zip(candidates, weights)
            ]
        current = random.choices(candidates, weights=weights, k=1)[0]

    return result

# ─── EUCLIDEAN RHYTHM (Bjorklund/Toussaint) ──────────────────────────────────

from scripts.euclidean import bjorklund as _bjorklund

# Pre-computed euclidean hi-hat patterns (1 = onset, 0 = rest, 16 steps)
_EUCL_HATS = {
    'tresillo':  (_bjorklund(3,  8) * 2),   # [1,0,0,1,0,0,1,0] × 2 = 16 steps
    'cinquillo': (_bjorklund(5,  8) * 2),   # dense Cuban feel
    'bossa16':   (_bjorklund(3, 16)),        # sparse bossa
    'clave':     (_bjorklund(5, 16)),        # clave approximation
    # Dembow (reggaeton) -- research/theory/rhythm-groove.md: tresillo-
    # family pattern, kick-equivalent onsets on steps 0/6, snare-equivalent
    # on steps 2/8 in a 16-step bar. A natural fit for lofi_world's existing
    # elevated swing range ("organic percussive feel, not stiff-straight").
    'dembow':    [1,0,1,0,0,0,1,0, 1,0,0,0,0,0,0,0],
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


# ─── CELLULAR-AUTOMATON RHYTHM (Wolfram elementary CA) ────────────────────────
# An ADDITIONAL procedural rhythm-pattern source, alongside (not replacing)
# the Bjorklund/Euclidean generator above — wired into pick_params() with a
# similar per-track probability, sharing the same
# params['drum_pattern_a_generated']/['drum_pattern_b_generated'] override
# slot so build_midi() consumes it identically either way.

# Classic elementary-CA rules (Wolfram's 1983 paper / "A New Kind of
# Science"), chosen for musically useful onset density:
#   30  — chaotic, aperiodic (good for busier/energetic kick patterns)
#   90  — Sierpinski-triangle fractal via XOR(left, right); self-similar,
#         good for hi-hat texture
#   110 — proven Turing-complete; complex but structured, mid-density
#   184 — traffic/particle-hopping rule; produces steady, roughly-even flow
#   126 — chaotic, high-density, related to rule 30 by left-right reflection
#         (research/theory/rhythm-groove.md: added for hat texture
#         specifically, evaluated for whether its growth curve clusters
#         into burst-like density spikes rather than even density -- a
#         phonk-roll-like shape. Genuinely tuning this by ear is future
#         work; included as a real additional option now, not yet
#         preferentially weighted over the other 4.)
_CA_RULE_POOL = (30, 90, 110, 184, 126)


def _ca_step(rule: int, row: list[int]) -> list[int]:
    """
    One generation of a 1D elementary cellular automaton: each cell's next
    state is f(left, self, right) read off the 8-bit rule table (bit index =
    3-bit neighborhood pattern 0-7, per Wolfram's rule-number convention).
    Circular (wraparound) boundary so the result tiles cleanly onto the
    16-step drum grid, which is itself a repeating loop.
    """
    n = len(row)
    rule_bits = [(rule >> b) & 1 for b in range(8)]
    nxt = [0] * n
    for i in range(n):
        left  = row[(i - 1) % n]
        mid   = row[i]
        right = row[(i + 1) % n]
        pattern = (left << 2) | (mid << 1) | right
        nxt[i] = rule_bits[pattern]
    return nxt


def _ca_evolve(rule: int, width: int, generations: int, seed_row: list[int] | None = None) -> list[int]:
    """Evolve an elementary CA for `generations` steps from a single-cell
    seed (the classic elementary-CA starting condition) and return the final
    generation's binary row."""
    row = seed_row[:] if seed_row is not None else [0] * width
    if seed_row is None:
        row[width // 2] = 1
    for _ in range(max(0, generations)):
        row = _ca_step(rule, row)
    return row


def _ioi_velocities(onsets: list[int], base_vel: int, accent_vel: int, n: int = 16) -> list[int]:
    """Inter-onset-interval velocity weighting (see generate_euclidean_drum_pattern's
    identical technique) — a longer gap before an onset reads as perceptually
    stronger, so it gets proportionally more velocity than a densely-packed one."""
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


def generate_ca_drum_pattern(energy: float, complexity: float = 0.5,
                              rule: int | None = None, seed: int | None = None) -> dict:
    """
    Generate a full 16-step drum pattern from a Wolfram elementary cellular
    automaton (1D binary array, next-generation cell = f(left, self, right)
    read off an 8-bit rule table — rule-30/rule-90 style). A second,
    independent procedural rhythm-pattern source alongside
    generate_euclidean_drum_pattern — same {DRUM_NOTE: [16 velocities]}
    output shape, so it's an equally valid drop-in for
    params['drum_pattern_a_generated']/['drum_pattern_b_generated'].

    Kick comes from evolving the chosen rule for a `complexity`-scaled number
    of generations from the classic single-cell seed. Snare continues
    evolving the SAME automaton run a few more generations (so it's
    correlated with, but distinct from, the kick — like a later "slice" of
    the same unfolding pattern). Hats use rule 90 specifically (the
    Sierpinski-triangle fractal via XOR(left, right)) run for more
    generations, scaled by complexity, for denser texture. Any degenerate
    (all-zero) row — common for some rule/generation-count combinations,
    since several elementary CA rules die out to a fixed point — falls back
    to a minimal onset so the pattern is never completely silent.
    """
    rng = random.Random(seed) if seed is not None else random
    energy = max(0.0, min(1.0, energy))
    complexity = max(0.0, min(1.0, complexity))
    n = 16
    rule = rule if rule is not None else rng.choice(_CA_RULE_POOL)

    kick_generations = max(2, min(10, round(3 + complexity * 6)))
    kick_row = _ca_evolve(rule, n, kick_generations)
    if not any(kick_row):
        kick_row = [0] * n
        kick_row[0] = 1

    snare_row = _ca_step(rule, _ca_step(rule, kick_row))
    if not any(snare_row):
        snare_row = [0] * n
        snare_row[n // 2] = 1

    hat_generations = max(3, min(12, round(4 + complexity * 8)))
    hat_row = _ca_evolve(90, n, hat_generations)
    if not any(hat_row):
        hat_row = [1 if i % 2 == 0 else 0 for i in range(n)]

    rim_row = _ca_step(rule, snare_row)

    return {
        KICK:  _ioi_velocities(kick_row,  int(58 + energy * 32), int(80 + energy * 15), n),
        SNARE: _ioi_velocities(snare_row, 62, 90, n),
        CHH:   _ioi_velocities(hat_row,   38, 68, n),
        OHH:   [0] * n,
        RIM:   _ioi_velocities(rim_row,   24, 40, n),
    }


def generate_polyrhythm_pattern(energy: float = 0.55, ratio: tuple[int, int] = (3, 4),
                                 seed: int | None = None) -> dict:
    """
    A THIRD procedural rhythm-pattern source, alongside (not replacing) the
    Euclidean and cellular-automaton generators above -- same
    {DRUM_NOTE: [16 velocities]} output shape, so it's an equally valid
    drop-in for params['drum_pattern_a_generated']/['drum_pattern_b_generated'].

    Implements a genuine 3-against-4 cross-rhythm (not a time-signature
    change -- see the module's odd-meter discussion elsewhere): KICK/SNARE
    stay on the standard 4-pulse quarter-note grid (steps 0/4/8/12), while
    CHH follows an INDEPENDENT `ratio[0]`-pulse cycle spaced evenly across
    the same 16-step bar via modulo arithmetic -- two simultaneous cyclic
    pulse trains at a 3:4 period ratio, the standard definition of a
    cross-rhythm/hemiola (research/theory/rhythm-groove.md: "not currently
    represented and is a distinct technique from what's implemented" --
    the existing _EUCL_HATS presets fold everything into one 16-step
    additive grouping instead of two independently-cycling pulse trains).
    """
    n = 16
    rng = random.Random(seed) if seed is not None else random
    pulses, base = ratio

    kick_row = [0] * n
    for i in range(base):
        kick_row[round(i * n / base) % n] = 1

    snare_row = [0] * n
    snare_row[n // 2] = 1   # backbeat anchor, independent of either pulse train

    # The cross-rhythm layer: `pulses` evenly-spaced onsets across the same
    # 16-step bar as the 4-pulse kick above -- lands off the quarter-note
    # grid by construction whenever pulses/base isn't itself a multiple of 4.
    hat_row = [0] * n
    for i in range(pulses):
        hat_row[round(i * n / pulses) % n] = 1

    return {
        KICK:  _ioi_velocities(kick_row,  int(60 + energy * 30), int(82 + energy * 13), n),
        SNARE: _ioi_velocities(snare_row, 65, 88, n),
        CHH:   _ioi_velocities(hat_row,   42, 66, n),
        OHH:   [0] * n,
        RIM:   [0] * n,
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
    # P: Drill bounce — offbeat/syncopated kick (808-slide feel, not just beat 1),
    # snare on 3 with a ghost, hat roll that builds density across the back half
    # of the bar rather than staying uniform like L's steady trap hats.
    {KICK: [95,0,0,0,  0,0,78,0,  0,0,85,0,  0,72,0,0],
     SNARE:[0,0,0,0,  0,0,0,0,  92,0,0,0,  0,0,40,0],
     CHH:  [58,0,55,0,58,0,55,0,62,60,65,62,68,65,70,72],
     OHH:  [0,0,0,0,  0,0,0,0,  0,0,0,0,  0,0,0,60],
     RIM:  [0]*16},
    # Q: Phonk hat-roll cell -- research/theory/rhythm-groove.md "Concrete
    # additions": straight 8th-note hat base with a dense roll-burst on the
    # last quarter of the bar (steps 12-15, the finest density this 16-step
    # grid can express as an approximation of the genre's real 32nd/64th-note
    # hat rolls), plus a pitched-cowbell-style RIM voice on the "and" of 2
    # and 4 (steps 6, 14) as the genre-defining accent voice distinct from
    # the hats. A genuinely new curated pattern, not reachable by tuning
    # generate_euclidean_drum_pattern()'s k/n or the CA rule pool.
    {KICK: [92,0,0,0,  0,0,80,0,  0,0,86,0,  0,0,0,70],
     SNARE:[0,0,0,0,  0,0,0,0,  90,0,0,0,  0,0,38,0],
     CHH:  [55,0,55,0,55,0,55,0,55,0,55,0,60,68,76,85],
     OHH:  [0,0,0,0,  55,0,0,0,  0,0,0,0,  0,0,0,0],
     # Cowbell, not rim: the cowbell line is phonk's signature voice (GM 56).
     COWBELL:[0,0,0,0,  0,0,62,0,  0,0,0,0,  0,0,66,0]},
    # R: House four-on-the-floor -- kick on every beat, clap on 2 and 4,
    # open hat on every off-beat 8th, light closed 16ths. lofi_house had no
    # four-on-the-floor pattern at all before (it drew hip-hop/funk/trap).
    {KICK: [100,0,0,0,  96,0,0,0,  98,0,0,0,  96,0,0,0],
     CLAP: [0,0,0,0,  86,0,0,0,  0,0,0,0,  88,0,0,0],
     SNARE:[0,0,0,0,  40,0,0,0,  0,0,0,0,  42,0,0,0],
     CHH:  [46,0,0,34,  46,0,0,34,  46,0,0,34,  46,0,0,34],
     OHH:  [0,0,70,0,  0,0,68,0,  0,0,70,0,  0,0,68,0]},
    # S: Bossa nova (two bars, 32 steps). Bass drum on 1 and 3 with soft
    # pickups on the "and" of 2 and 4; steady soft 8th hats; side-stick
    # plays the 3-2 bossa clave (bar 1: 1, 2&, 4 / bar 2: 2, 3&). No
    # backbeat snare. (kickdrum.io/patterns/bossa-nova, tunableapp.com)
    {KICK: [80,0,0,0,  0,0,52,0,  78,0,0,0,  0,0,54,0] * 2,
     RIM:  [72,0,0,0,  0,0,68,0,  0,0,0,0,  70,0,0,0,
            0,0,0,0,  70,0,0,0,  0,0,68,0,  0,0,0,0],
     CHH:  [46,0,38,0,  44,0,38,0,  46,0,38,0,  44,0,38,0] * 2,
     SHAKER:[0,30,0,30,  0,30,0,30,  0,30,0,30,  0,30,0,30] * 2},
    # T: Synthwave -- steady four-on-the-floor kick, a big snare (plus clap)
    # on 2 and 4, straight 8th hats. (orphiq.com, ujam.com synthwave guides)
    {KICK: [98,0,0,0,  92,0,0,0,  96,0,0,0,  92,0,0,0],
     SNARE:[0,0,0,0,  100,0,0,0,  0,0,0,0,  100,0,0,0],
     CLAP: [0,0,0,0,  64,0,0,0,  0,0,0,0,  66,0,0,0],
     CHH:  [58,0,52,0,  58,0,52,0,  58,0,52,0,  58,0,52,0]},
    # U: Acoustic morning -- soft kick on 1 and the "and" of 2, side-stick on
    # 2 and 4 instead of a snare, a shaker carrying the 16ths. A coffee-shop
    # acoustic kit rather than a boom-bap one.
    {KICK: [72,0,0,0,  0,0,56,0,  66,0,0,0,  0,0,0,0],
     RIM:  [0,0,0,0,  64,0,0,0,  0,0,0,0,  62,0,0,30],
     SHAKER:[44,22,34,22,  44,22,34,22,  44,22,34,22,  44,22,34,22]},
    # V: Tropical / summer -- clave on the son 3-2 pattern over two bars,
    # conga tumbao (open tones on the "and" of 4), steady shaker, light
    # kick. GM conga notes 62/63/64.
    {KICK:  [78,0,0,0,  0,0,0,0,  70,0,0,0,  0,0,0,0] * 2,
     75:    [74,0,0,74,  0,0,74,0,  0,0,0,0,  0,0,0,0,
             0,0,0,0,  74,0,0,0,  74,0,0,0,  0,0,0,0],
     62:    [0,0,0,0,  52,0,0,0,  0,0,0,0,  52,0,0,0] * 2,
     63:    [0,0,0,0,  0,0,0,0,  0,0,0,0,  0,0,70,70] * 2,
     64:    [0,0,0,0,  0,0,0,0,  0,0,58,0,  0,0,0,0] * 2,
     SHAKER:[40,0,30,0,  40,0,30,0,  40,0,30,0,  40,0,30,0] * 2},
]

# Index of pattern Q above -- the only pattern _scale_roll_intensity() acts
# on (its back-quarter CHH steps 12-15 are the hand-authored "roll burst").
_PHONK_ROLL_PATTERN_IDX = 16
_PHONK_ROLL_STEPS = (12, 13, 14, 15)
_PHONK_ROLL_FLAT_VEL = 55     # matches the pattern's own steady-8th level (steps 0-11)
_PHONK_ROLL_FULL_VELS = (60, 68, 76, 85)   # the ramp as hand-authored


def _scale_roll_intensity(pattern: dict, density: float) -> dict:
    """
    Scale pattern Q's back-quarter hat-roll (steps 12-15) between "flat, no
    roll" (density=0, same level as the rest of the bar) and "full ramp as
    authored" (density=1) -- research/theory/rhythm-groove.md: phonk's
    bounce comes from swing + off-grid placement + roll density as three
    separate, independently-tunable levers, not just swing. Returns an
    unmodified reference to `pattern` for any other pattern (only pattern
    Q's specific hand-authored roll shape is meaningful to scale this way).
    """
    if pattern is not DRUM_PATTERNS[_PHONK_ROLL_PATTERN_IDX] or CHH not in pattern:
        return pattern
    density = max(0.0, density)
    scaled = dict(pattern)
    chh = list(pattern[CHH])
    for i, step in enumerate(_PHONK_ROLL_STEPS):
        full = _PHONK_ROLL_FULL_VELS[i]
        chh[step] = int(round(_PHONK_ROLL_FLAT_VEL + (full - _PHONK_ROLL_FLAT_VEL) * density))
    scaled[CHH] = chh
    return scaled


# {genre_key: float} from config/genres/*.yaml's roll_density field --
# currently only lofi_phonk sets one.
_ROLL_DENSITY_BY_GENRE: dict[str, float] = genre_presets.build_roll_density()

# ─── Per-subgenre tables, loaded from config/genres/*.yaml ───────────────────
# Placed here (after PROGRESSIONS/DRUM_PATTERNS/VOICING_OPTIONS) because
# genre_presets.load_all() bounds-validates progression_indices/
# drum_pattern_indices against PROGRESSIONS/DRUM_PATTERNS at load time.
_SUBGENRE_CONFIG = genre_presets.build_subgenre_config()
_SWING_RANGE: dict[str, tuple[float, float]] = genre_presets.build_swing_range()
_COZY_SUBGENRES: frozenset[str] = genre_presets.build_cozy_subgenres()
# New engine-feature membership sets (same pattern as _IR_GENRES/
# _SIDECHAIN_DUCK_GENRES in lofi_fx.py): which subgenres opt into the
# 808 pitch-slide bass, per-voice micro-timing drum swing, and continuous
# arpeggiator melody engine, respectively.
_GLIDE_808_GENRES: set = genre_presets.build_glide_808_genres()
_MICRO_SWING_GENRES: set = genre_presets.build_micro_swing_genres()
_CONTINUOUS_ARP_GENRES: set = genre_presets.build_continuous_arp_genres()
_CHH_TRIPLET_GENRES: set = genre_presets.build_chh_triplet_genres()
_GAMAKA_GENRES: set = genre_presets.build_gamaka_genres()
_TALA_OVERLAY_GENRES: set = genre_presets.build_tala_overlay_genres()
# Genre-identity controls (config/genres/README.md).
_GENERATED_DRUM_GENRES: set = genre_presets.build_generated_drum_genres()
_BEATLESS_GENRES: set = genre_presets.build_beatless_genres()
_WALKING_BASS: dict = genre_presets.build_walking_bass()
_BASS_PROGRAMS: dict = genre_presets.build_bass_programs()
_PAD_PROGRAMS: dict = genre_presets.build_pad_programs()
_MELODY_DENSITY: dict = genre_presets.build_melody_density()

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
    'Eb': 63,   # Eb major — bossa/jazz cycles that land in Eb (see PROGRESSION_KEY)
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

def get_phrygian_dominant(root):
    """Phrygian dominant (5th mode of harmonic minor) — b2 and b6 like
    Phrygian, but a major 3rd instead of minor: the maqam-Hijaz/flamenco
    "Spanish" color, distinct from get_phrygian's all-minor Mediterranean
    darkness. Used by the lofi_world sub-genre for a genuinely different
    exotic-scale flavor rather than reusing plain Phrygian."""
    notes = []
    for oct_off in range(3):
        for i in [0, 1, 4, 5, 7, 8, 10]:
            n = root + i + oct_off * 12
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

def get_melodic_minor(root):
    """Melodic minor (jazz minor) — raised 6th AND 7th vs. natural minor
    (harmonic_minor only raises the 7th). Jazz convention: same ascending
    and descending. Color for m(maj7)/m6/m9/m6-9 chords; also the parent
    scale of locrian-nat2/lydian-dominant/altered (see research/theory/
    scales-modes-gaps.md)."""
    notes = []
    for oct_off in range(3):
        for i in [0, 2, 3, 5, 7, 9, 11]:
            n = root + i + oct_off * 12
            if 53 <= n <= 86:
                notes.append(n)
    return sorted(set(notes))

def get_locrian(root):
    """Locrian mode — the only diatonic major-scale mode previously missing
    from this file. Diminished 5th gives a built-in half-diminished color;
    pairs with the existing Bm7b5 chord (progressions #2, #32, #39)."""
    notes = []
    for oct_off in range(3):
        for i in [0, 1, 3, 5, 6, 8, 10]:
            n = root + i + oct_off * 12
            if 53 <= n <= 86:
                notes.append(n)
    return sorted(set(notes))

def get_altered(root):
    """Altered / super-locrian scale (7th mode of melodic minor) — b9, #9,
    b5/#11, b13/#5, b7: every degree but the root is flattened relative to
    major. Standard color over 7alt/7b9/7#9 dominants; melodically unifies
    with _SEC_DOM_SUBS' tritone substitutions (altered scale on a dominant
    == lydian dominant of that dominant's tritone-sub root)."""
    notes = []
    for oct_off in range(3):
        for i in [0, 1, 3, 4, 6, 8, 10]:
            n = root + i + oct_off * 12
            if 53 <= n <= 86:
                notes.append(n)
    return sorted(set(notes))

def get_bebop_dominant(root):
    """Bebop dominant scale — Mixolydian plus a chromatic passing major-7th
    between b7 and the octave root (8 notes). The extra tone is a rhythmic-
    alignment device: playing continuous 8th/16th runs from a chord tone
    keeps chord tones landing on strong beats, since an 8-note scale divides
    evenly into common beat groupings where a 7-note scale doesn't. Used for
    dense/fast melody passages over any dominant 7 chord."""
    notes = []
    for oct_off in range(3):
        for i in [0, 2, 4, 5, 7, 9, 10, 11]:
            n = root + i + oct_off * 12
            if 53 <= n <= 86:
                notes.append(n)
    return sorted(set(notes))


def _resolve_scale(scale, root):
    """Canonical scale-name -> note-list dispatch, shared by build_melody(),
    build_counter_melody(), and build_midi()'s motif-seed scale selection so
    every new scale only needs to be wired in once. Mirrors the elif chain
    that used to be duplicated (and, in build_midi()'s case, only partially
    duplicated) at each call site."""
    if scale == 'dorian':
        return get_dorian(root)
    elif scale == 'phryg':
        return get_phrygian(root)
    elif scale == 'phryg_dom':
        return get_phrygian_dominant(root)
    elif scale == 'major_pent':
        return [n for oct_off in range(3)
                for i in [0, 2, 4, 7, 9]
                for n in [root + i + oct_off * 12]
                if 53 <= root + i + oct_off * 12 <= 86]
    elif scale == 'mixo':
        return [n for oct_off in range(3)
                for i in [0, 2, 4, 5, 7, 9, 10]
                for n in [root + i + oct_off * 12]
                if 53 <= root + i + oct_off * 12 <= 86]
    elif scale == 'major':
        return get_major(root)
    elif scale == 'lydian':
        return get_lydian(root)
    elif scale == 'natural_minor':
        return get_natural_minor(root)
    elif scale == 'harmonic_minor':
        return get_harmonic_minor(root)
    elif scale == 'blues':
        return get_blues(root)
    elif scale == 'whole_tone':
        return get_whole_tone(root)
    elif scale == 'melodic_minor':
        return get_melodic_minor(root)
    elif scale == 'locrian':
        return get_locrian(root)
    elif scale == 'altered':
        return get_altered(root)
    elif scale == 'bebop_dominant':
        return get_bebop_dominant(root)
    else:
        return get_pentatonic(root)


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


# Duration multiplier applied at build_melody()'s `dur = ...` call site when
# a phrase's variation is 'augment' -- vary_motif() only returns pitches
# (durations are assigned per-note in build_melody), so augmentation is
# communicated back to the caller via this lookup rather than a return value.
# Every variation not listed here implicitly scales by 1.0 (unchanged).
_VARIATION_DUR_SCALE = {'augment': 1.75}


def vary_motif(motif, scale_notes, variation):
    """Return a variation of the motif (retrograde, invert, transpose,
    augment, fragment, or nudge)."""
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

    if variation == 'augment':
        # Classical augmentation: pitches unchanged, note durations stretched
        # by the caller (see _VARIATION_DUR_SCALE / build_melody's dur= line).
        return list(motif)

    if variation == 'fragment':
        # Fragmentation: repeat a short sub-cell (first 2 notes) instead of
        # playing the full motif -- a standard Liszt/Berlioz-era thematic-
        # transformation technique, alongside retrograde/inversion, that was
        # previously entirely absent (only whole-motif variations existed).
        cell = motif[:2] if len(motif) >= 2 else motif[:]
        return cell * 2

    # 'default': small random nudge — preserves shape without being identical
    shift = random.choice([-1, 0, 0, 1])
    return [scale_notes[max(0, min(len(scale_notes)-1, _idx(n)+shift))] for n in motif]


# ── L-system motif generator ────────────────────────────────────────────────
# Lindenmayer-system generative grammar (Prusinkiewicz & Lindenmayer, "The
# Algorithmic Beauty of Plants") applied to melody instead of plant geometry:
# an axiom string is iteratively expanded via per-symbol production rules,
# then the resulting symbol string is interpreted as a sequence of melodic
# operations on a scale-degree cursor. Ported from generate_music_v2.py
# (Aug 13 "Stage 3"), which had this working and tested but only in the beta
# engine -- v1 gets it here as an ADDITIONAL probabilistic source alongside
# generate_motif() (see its call sites), not a replacement.

# Melodic alphabet:
#   U - step up one scale degree      D - step down one scale degree
#   S - repeat (sustain) current note T - transpose (toggle +1 octave)
#   [ - push (save) cursor state      ] - pop (restore) cursor state —
#       classic Lindenmayer bracketed-branching notation, giving the
#       melody a "return to a home note" character instead of a pure
#       one-way random walk.
_LSYSTEM_PRESETS: list[tuple[str, dict[str, str]]] = [
    ('U', {'U': 'UDU', 'D': 'DUD'}),            # symmetric zigzag fractal
    ('U', {'U': 'U[D]U', 'D': 'D[U]D'}),        # branching zigzag, returns to branch point
    ('US', {'U': 'US', 'D': 'DS', 'S': 'US'}),  # terraced ascending steps with sustains
    ('U', {'U': 'UUD', 'D': 'DDU'}),            # asymmetric climb
    ('T', {'T': 'UTD', 'U': 'U', 'D': 'D'}),    # octave-anchored motif
]


def _lsystem_expand(axiom: str, rules: dict[str, str], iterations: int, max_len: int = 64) -> str:
    """
    Iteratively expand an L-system axiom via per-symbol production rules.
    Bounded: stops expanding (keeping the last valid generation) once the
    NEXT expansion would exceed `max_len`, so output length stays musically
    bounded rather than growing exponentially the way raw L-system expansion
    normally does (that unbounded growth is the point for plant geometry,
    but a melodic phrase needs a sane, bounded length).
    """
    s = axiom
    for _ in range(max(0, iterations)):
        nxt = ''.join(rules.get(ch, ch) for ch in s)
        if len(nxt) > max_len:
            break
        s = nxt
    return s


def _lsystem_to_pitches(symbols: str, scale_notes: list[int], start_idx: int) -> list[int]:
    """Interpret an L-system symbol string as melodic operations on a
    scale-degree cursor (see the alphabet comment above). Non-melodic
    symbols other than U/D/S/T/[/] are ignored. Emits one pitch per U/D/S/T
    symbol encountered (push/pop only affect state, they emit nothing)."""
    n = len(scale_notes)
    if n == 0:
        return []
    idx = max(0, min(n - 1, start_idx))
    octave_offset = 0
    stack: list[tuple[int, int]] = []
    pitches: list[int] = []
    for ch in symbols:
        if ch == 'U':
            idx = min(n - 1, idx + 1)
            pitches.append(scale_notes[idx] + octave_offset)
        elif ch == 'D':
            idx = max(0, idx - 1)
            pitches.append(scale_notes[idx] + octave_offset)
        elif ch == 'S':
            pitches.append(scale_notes[idx] + octave_offset)
        elif ch == 'T':
            octave_offset = 12 if octave_offset == 0 else 0   # toggle; avoids runaway octave drift
            pitches.append(scale_notes[idx] + octave_offset)
        elif ch == '[':
            stack.append((idx, octave_offset))
        elif ch == ']':
            if stack:
                idx, octave_offset = stack.pop()
    return pitches


def generate_lsystem_motif(scale_notes: list[int], length: int = 8,
                            seed: int | None = None) -> list[int]:
    """
    Generate a melodic motif via L-system string expansion (see module
    comment above). Picks one of a small pool of axiom+production-rule
    presets, expands it a bounded number of iterations, then walks the
    resulting symbol string as scale-degree operations. Deterministic given
    `seed` (uses a local Random instance so it never disturbs the pipeline's
    global random stream when called with an explicit seed).

    Returns a plain pitch list -- matches generate_motif()'s convention
    (v1 doesn't use v2's Motif wrapper class anywhere).
    """
    if not scale_notes:
        return []
    rng = random.Random(seed) if seed is not None else random
    axiom, rules = rng.choice(_LSYSTEM_PRESETS)
    iterations = rng.choice([2, 3, 3, 4])
    symbols = _lsystem_expand(axiom, rules, iterations, max_len=max(8, length * 4))
    start_idx = rng.randrange(len(scale_notes))
    pitches = _lsystem_to_pitches(symbols, scale_notes, start_idx)
    if not pitches:
        pitches = [scale_notes[start_idx]]
    return pitches[:max(1, length)]


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

# Gaussian humanization — ported from generate_music_v2.py's better-reviewed
# model (real human timing/velocity variance clusters near the target rather
# than spreading flat/uniform). Used selectively (melody/chords/bass), not as
# a blanket replacement for jitter()/v() — see call sites in build_melody(),
# build_chords(), build_bass().
def _gauss_jitter(tick: int, ms: float, bpm: int) -> int:
    """Gaussian timing jitter — clusters near grid, sigma = ms/2, capped at +-1.5x ms."""
    ticks_per_ms = (PPQN * bpm) / 60_000.0
    offset_ms = max(-ms * 1.5, min(ms * 1.5, random.gauss(0, ms * 0.5)))
    return max(0, tick + int(offset_ms * ticks_per_ms))

def _gauss_velocity(base: int, sigma: float = 8.0) -> int:
    return max(1, min(127, round(random.gauss(base, sigma))))

def _lofi_late(tick: int, bpm: int) -> int:
    """Systematic late feel for melody — lands +10-25ms behind the grid."""
    offset_ms = random.gauss(17, 4)
    ticks_per_ms = (PPQN * bpm) / 60_000.0
    return max(0, tick + int(offset_ms * ticks_per_ms))

def abs_to_track(events, channel, program=None, cc_events=None, bank_msb=None,
                  pitch_bend_range=None):
    """
    Convert absolute-tick note events to a MIDI track.
    events:    list of (abs_tick, note, velocity, duration). A note value of
               _PITCHWHEEL_NOTE marks a pitch-bend event instead of a real
               note (velocity field carries the 14-bit pitch value, center
               8192) -- see build_bass()'s glide=True path / _glide_pitchbend_events().
    cc_events: optional list of (abs_tick, control, value) for CC messages (e.g. sustain pedal)
    bank_msb:  if set, send CC0=bank_msb + CC32=0 before program_change (GS drum kit select)
    pitch_bend_range: if set, emit an RPN 0,0 (pitch-bend-range) message at
               track start, +-this many semitones, before any note/pitchwheel
               events -- required once per channel for pitchwheel messages to
               bend by a musically-correct interval instead of the device's
               default (usually +-2 semitones).
    """
    import mido
    track = mido.MidiTrack()
    if bank_msb is not None:
        track.append(mido.Message('control_change', channel=channel, control=0,  value=bank_msb, time=0))
        track.append(mido.Message('control_change', channel=channel, control=32, value=0,        time=0))
    if program is not None:
        track.append(mido.Message('program_change', channel=channel, program=program, time=0))
    if pitch_bend_range is not None:
        # RPN 0,0 = pitch-bend-range; data entry MSB = semitones, LSB = cents
        # (0 here). Null RPN (101/100 = 127) afterward so later CC6/CC38
        # sends on this channel (if any) aren't misinterpreted as RPN data.
        semis = max(0, min(24, int(pitch_bend_range)))
        track.append(mido.Message('control_change', channel=channel, control=101, value=0,   time=0))
        track.append(mido.Message('control_change', channel=channel, control=100, value=0,   time=0))
        track.append(mido.Message('control_change', channel=channel, control=6,   value=semis, time=0))
        track.append(mido.Message('control_change', channel=channel, control=38,  value=0,   time=0))
        track.append(mido.Message('control_change', channel=channel, control=101, value=127, time=0))
        track.append(mido.Message('control_change', channel=channel, control=100, value=127, time=0))
    msgs = []
    for abs_tick, note, velocity, dur in events:
        if note == _PITCHWHEEL_NOTE:
            msgs.append((max(0, int(abs_tick)), 0, 'pitchwheel', velocity))
            continue
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
        elif mtype == 'pitchwheel':
            pitch14 = max(0, min(16383, int(item[3])))
            track.append(mido.Message('pitchwheel', channel=channel,
                                      pitch=pitch14 - 8192, time=t-prev))
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

# Per-voice micro-timing profile for garage/2-step programming (research/
# subgenres/lofi_garage.md: "garage swing lives in the individual hits" --
# per-hit micro-timing offsets per drum voice, not one uniform swing ratio).
# (bias_ms, jitter_ms): bias = mean push-late offset, jitter_ms = std-dev fed
# into _gauss_jitter -- extends that existing humanization call, doesn't
# replace it. Hats get the widest spread + latest push (2-step's off-grid
# hi-hat signature); snare gets a smaller consistent late pull; kick stays
# closest to the grid to keep the four-on-the-floor anchor solid.
_MICRO_SWING_PROFILE = {
    CHH:   (10.0, 12.0),
    OHH:   (8.0,  10.0),
    RIDE:  (8.0,  10.0),
    RIM:   (6.0,  8.0),
    SNARE: (5.0,  5.0),
    KICK:  (0.0,  2.0),
}
_MICRO_SWING_DEFAULT = (4.0, 6.0)


def build_drums(pattern, start_bar, num_bars, swing, bpm, fill_bars=None,
                micro_swing=False, chh_triplet=False, allow_generated=True):
    """
    Build drum events. fill_bars = set of bar numbers that get a fill
    instead of the regular pattern. Every 4 bars gets a hi-hat 16th run.
    Per-bar mutation: 8% chance each step is dropped or added for variation.

    micro_swing=True layers a per-voice micro-timing profile (see
    _MICRO_SWING_PROFILE) on top of the existing _gauss_jitter humanization —
    each drum voice gets its own bias/std-dev instead of every voice sharing
    the same flat +-4ms jitter.

    chh_triplet=True (default False -- every existing genre/call site keeps
    its exact prior behavior unchanged): replaces the CHH voice's normal
    16-step reads with a true 12-step-per-bar (8th-note-triplet) subdivision
    layered against the still-16-step KICK/SNARE/RIM/OHH -- drill's
    hi-hat triplets are a genuinely different subdivision (12 vs 16 per
    bar), not reachable by densifying the 16-step hat pattern
    (research/theory/rhythm-groove.md). See _build_triplet_hat_events().
    """
    events = []
    fill_bars = fill_bars or set()
    fill_template = random.choice(DRUM_FILLS)
    # Euclidean hi-hat: 15% chance of polyrhythmic CHH pattern per section
    # Only for genres that opt in (generated_drums): elsewhere it would
    # overwrite the hats/rim that define the genre's groove.
    eucl_hat = (random.choice(list(_EUCL_HATS.values()))
                if allow_generated and random.random() < 0.15 else None)
    # Independent second Euclidean layer for OHH/RIM (10% chance, own pattern
    # and own target channel, layered on top of whatever CHH is doing).
    eucl_layer2 = (random.choice(list(_EUCL_HATS.values()))
                   if allow_generated and random.random() < 0.10 else None)
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
                if chh_triplet and drum_note == CHH:
                    continue   # CHH comes from _build_triplet_hat_events() below instead
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

                # Patterns may span several bars (32 steps = 2 bars, e.g. a clave).
                n_pat_bars = max(1, len(vels) // 16)
                vel_val = vels[(abs_bar % n_pat_bars) * 16 + step % 16]

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
                    vel_val = max(vel_val, _gauss_velocity(55, 10))

                if vel_val > 0:
                    # Gaussian humanization (matches melody/chords/bass'
                    # _gauss_jitter/_gauss_velocity conventions elsewhere in
                    # this file) instead of the flat/uniform jitter()/v() --
                    # real human timing/velocity variance clusters near the
                    # target rather than spreading uniformly. Only the feel
                    # changes here; which steps/drums fire is untouched.
                    if micro_swing:
                        bias_ms, jit_ms = _MICRO_SWING_PROFILE.get(drum_note, _MICRO_SWING_DEFAULT)
                        ticks_per_ms = (PPQN * bpm) / 60_000.0
                        t = _gauss_jitter(base_t + int(bias_ms * ticks_per_ms), jit_ms, bpm)
                    else:
                        t = _gauss_jitter(base_t, 4, bpm)
                    events.append((t, drum_note, _gauss_velocity(vel_val, 8), 25))

    if chh_triplet:
        events += _build_triplet_hat_events(start_bar, num_bars, bpm)

    return events


_TRIPLET_STEPS_PER_BAR = 12
_TRIPLET_STEP_TICKS = BAR // _TRIPLET_STEPS_PER_BAR   # 160 ticks = one 8th-note-triplet


def _build_triplet_hat_events(start_bar: int, num_bars: int, bpm: int) -> list:
    """
    True 12-step-per-bar (8th-note-triplet) hi-hat subdivision -- a
    genuinely different grid than the 16-step DRUM_PATTERNS format, not a
    denser 16-step pattern (research/theory/rhythm-groove.md). Every 3rd
    triplet step (the "downbeat" of each triplet group, i.e. each real
    beat) gets a stronger accent; the two off-triplet steps in between are
    ghosted, giving the characteristic drill triplet-roll shuffle.
    """
    events = []
    for bar in range(num_bars):
        abs_bar = start_bar + bar
        base_tick = abs_bar * BAR
        for step in range(_TRIPLET_STEPS_PER_BAR):
            if random.random() < 0.08:   # occasional dropped step for variation
                continue
            accent = (step % 3 == 0)
            base_vel = 62 if accent else 40
            t = _gauss_jitter(base_tick + step * _TRIPLET_STEP_TICKS, 4, bpm)
            events.append((t, CHH, _gauss_velocity(base_vel, 8), 25))
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


def _chord_name_at_bar(progression, bar, prog_bars):
    """Return the chord symbol (not just its pitch classes) playing at the
    given absolute bar -- companion to _chord_pcs_at_bar, used by
    build_melody() to detect when the current chord is a secondary-dominant/
    tritone-sub target (see _SEC_DOM_SUB_TARGETS) so it can reach for
    get_altered() instead of the track's main scale for that phrase."""
    bar_in_prog = bar % max(1, prog_bars)
    cursor = 0
    for chord_name, dur in progression:
        if bar_in_prog < cursor + dur:
            return chord_name
        cursor += dur
    return None


# ──────────────────────────────────────────────────────────────────────────────
#  WHOLE-PROGRESSION VOICE LEADING (GA / simulated annealing, species
#  counterpoint) -- ported from generate_music_v2.py's Stage-3 work so v1
#  (the primary/default-weighted engine) gets the same real optimizer v2 has
#  always had, instead of only the greedy nearest-top-note heuristic below.
#  Pure functions, no v2-specific state -- VOICING_OPTIONS is defined right
#  here in v1; v2 only ever imported it from this module.
# ──────────────────────────────────────────────────────────────────────────────

_DISSONANT_INTERVAL_CLASSES = {1, 2, 6}


def _voicing_transition_cost(prev_voicing: list[int], shifted_voicing: list[int]) -> float:
    """
    Species-counterpoint-inspired cost of moving from prev_voicing to
    shifted_voicing (shifted_voicing already has any octave shifts applied).
    Hand-rolled classical voice-leading rules (no neural net, no LLM), all
    scored PER VOICE PAIR independently (every pair of voices is checked on
    its own — not folded into one aggregate adjacent-pairs-only penalty):
      - total semitone displacement from prev_voicing
      - a parallel-fifths/octaves penalty for EVERY pair of voices (not just
        adjacent ones) moving in the same direction and landing on the same
        perfect 5th/octave interval class both before and after — the
        classic part-writing error, same rule Palestrina-style species
        counterpoint forbids between any two voices, not only neighbors
      - a small per-pair bonus for contrary motion between voices
      - a per-pair dissonance/suspension-resolution check: a dissonant
        interval (m2/M2/tritone) present between a voice pair in
        prev_voicing is rewarded if it resolves to a consonant interval by
        STEP (each voice moves <=2 semitones) in shifted_voicing — the
        standard "suspension resolves down/up by step" rule — and penalized
        if it is left hanging (still dissonant) or "resolved" by a leap
      - a spacing penalty for inner-voice gaps outside a natural
        close-position range (~3-12 semitones)
    Shared by _voice_lead_v2 (greedy, per-chord) and _voice_lead_progression_ga
    (whole-progression optimizer) so both apply identical rules — this
    function is a drop-in replacement, no restructuring needed on either
    caller's side.
    """
    n = min(len(shifted_voicing), len(prev_voicing))
    if n == 0:
        return 0.0
    displacement = sum(abs(shifted_voicing[i] - prev_voicing[i]) for i in range(n))
    moves = [shifted_voicing[i] - prev_voicing[i] for i in range(n)]

    parallel_penalty = 0.0
    contrary_bonus = 0.0
    dissonance_cost = 0.0

    for a in range(n):
        for b in range(a + 1, n):
            move_a, move_b = moves[a], moves[b]
            interval_prev = abs(prev_voicing[b] - prev_voicing[a]) % 12
            interval_now = abs(shifted_voicing[b] - shifted_voicing[a]) % 12

            if move_a != 0 and move_b != 0:
                same_direction = (move_a > 0) == (move_b > 0)
                if same_direction and interval_prev in (0, 7) and interval_now in (0, 7):
                    parallel_penalty += 8.0
                if not same_direction:
                    contrary_bonus += 1.0

            if interval_prev in _DISSONANT_INTERVAL_CLASSES:
                resolved_by_step = (
                    interval_now not in _DISSONANT_INTERVAL_CLASSES
                    and abs(move_a) <= 2 and abs(move_b) <= 2
                )
                dissonance_cost += -1.5 if resolved_by_step else 3.0

    spacing_penalty = 0.0
    for a in range(len(shifted_voicing) - 1):
        gap = shifted_voicing[a + 1] - shifted_voicing[a]
        if gap < 3:
            spacing_penalty += (3 - gap) * 1.5
        elif gap > 12:
            spacing_penalty += (gap - 12) * 1.0

    return displacement + parallel_penalty + spacing_penalty + dissonance_cost - contrary_bonus


def _enumerate_shift_options(voicing: list[int]) -> list[list[int]]:
    """All valid (ascending-order-preserving) ±12-semitone octave-shift
    variants of a voicing."""
    n = len(voicing)
    out = []
    for shifts in _iproduct([-12, 0, 12], repeat=n):
        shifted = [voicing[i] + shifts[i] for i in range(n)]
        if shifted == sorted(shifted):
            out.append(shifted)
    return out or [voicing]


def _build_voicing_gene_pools(chord_names: list[str]) -> list[list[list[int]]]:
    """Per-chord list of candidate voicings (every octave-shift variant of
    every curated VOICING_OPTIONS entry for that chord)."""
    gene_pools: list[list[list[int]]] = []
    for chord_name in chord_names:
        options = VOICING_OPTIONS.get(chord_name, [[60, 64, 67]])
        variants: list[list[int]] = []
        for base in options:
            variants.extend(_enumerate_shift_options(base))
        gene_pools.append(variants or [options[0]])
    return gene_pools


def _chromosome_cost(gene_pools: list[list[list[int]]], chromosome: list[int]) -> float:
    """Total _voicing_transition_cost across an entire chromosome's chord sequence."""
    total = 0.0
    prev = None
    for i, gene_idx in enumerate(chromosome):
        voicing = gene_pools[i][gene_idx]
        if prev is not None:
            total += _voicing_transition_cost(prev, voicing)
        prev = voicing
    return total


def _voice_lead_progression_ga(progression: list[tuple[str, int]],
                                pop_size: int = 24, generations: int = 40) -> list[list[int]]:
    """
    Evolve voicing+octave-shift choices for an ENTIRE progression
    simultaneously (unlike a greedy per-chord choice), via a genetic
    algorithm: tournament selection, single-point crossover, mutation,
    elitism. Solves the real limitation of greedy selection, which can get
    locally stuck (like greedy TSP) — global fitness considers every
    transition in the progression at once. Hand-rolled GA, no neural net, no
    LLM. Returns one shifted voicing (list[int]) per chord in `progression`,
    in order.
    """
    chord_names = [c for c, _ in progression]
    gene_pools = _build_voicing_gene_pools(chord_names)

    def _random_chromosome() -> list[int]:
        return [random.randrange(len(pool)) for pool in gene_pools]

    def _fitness(chromosome: list[int]) -> float:
        return _chromosome_cost(gene_pools, chromosome)

    population = [_random_chromosome() for _ in range(pop_size)]
    best = min(population, key=_fitness)
    best_fit = _fitness(best)

    def _tournament(k: int = 3) -> list[int]:
        contenders = random.sample(population, min(k, len(population)))
        return min(contenders, key=_fitness)

    for _ in range(generations):
        next_gen = [best]   # elitism: never lose the best chromosome found so far
        while len(next_gen) < pop_size:
            parent_a, parent_b = _tournament(), _tournament()
            cut = random.randrange(1, len(chord_names)) if len(chord_names) > 1 else 0
            child = parent_a[:cut] + parent_b[cut:]
            if random.random() < 0.15:
                idx = random.randrange(len(child))
                child[idx] = random.randrange(len(gene_pools[idx]))
            next_gen.append(child)
        population = next_gen
        candidate = min(population, key=_fitness)
        candidate_fit = _fitness(candidate)
        if candidate_fit < best_fit:
            best, best_fit = candidate, candidate_fit

    return [gene_pools[i][gene_idx] for i, gene_idx in enumerate(best)]


def _voice_lead_progression_annealing(
    progression: list[tuple[str, int]],
    iterations: int = 600, start_temp: float = 12.0, cooling: float = 0.99,
    seed: int | None = None,
) -> list[list[int]]:
    """
    Simulated-annealing ALTERNATIVE to _voice_lead_progression_ga: same goal
    (minimize total _voicing_transition_cost across the whole chord
    sequence, same gene pools) and same cost function, but a different
    search strategy — a single temperature-scheduled random-restart local
    search instead of a population-based evolutionary search. Standard
    published algorithm (Kirkpatrick et al. 1983): start from a random
    voicing choice per chord, repeatedly propose a random neighbor move
    (re-pick one chord's voicing), accept it unconditionally if it improves
    total cost, or with probability exp(-delta/T) if it doesn't (escapes
    local minima), and geometrically cool T over the run so late iterations
    behave like plain hill-climbing.

    Returns one shifted voicing (list[int]) per chord in `progression`, in
    order — same return shape as _voice_lead_progression_ga.
    """
    chord_names = [c for c, _ in progression]
    gene_pools = _build_voicing_gene_pools(chord_names)
    rng = random.Random(seed) if seed is not None else random

    current = [rng.randrange(len(pool)) for pool in gene_pools]
    current_cost = _chromosome_cost(gene_pools, current)
    best, best_cost = current[:], current_cost

    temp = start_temp
    for _ in range(iterations):
        movable = [i for i, pool in enumerate(gene_pools) if len(pool) > 1]
        if not movable:
            break
        idx = rng.choice(movable)
        neighbor = current[:]
        choices = [g for g in range(len(gene_pools[idx])) if g != current[idx]]
        neighbor[idx] = rng.choice(choices)
        neighbor_cost = _chromosome_cost(gene_pools, neighbor)

        delta = neighbor_cost - current_cost
        accept = delta <= 0 or rng.random() < math.exp(-delta / max(temp, 1e-6))
        if accept:
            current, current_cost = neighbor, neighbor_cost
            if current_cost < best_cost:
                best, best_cost = current[:], current_cost

        temp *= cooling

    return [gene_pools[i][gene_idx] for i, gene_idx in enumerate(best)]


def _voice_lead_progression_best(
    progression: list[tuple[str, int]],
    pop_size: int = 24, generations: int = 40, annealing_iterations: int = 600,
) -> tuple[list[list[int]], str]:
    """
    Run BOTH the genetic-algorithm optimizer and the simulated-annealing
    optimizer on the same progression and keep whichever finds the
    lower (better) total transition cost. Returns (voicings, winner) where
    winner is 'ga' or 'annealing'.
    """
    ga_voicings = _voice_lead_progression_ga(progression, pop_size=pop_size, generations=generations)
    sa_voicings = _voice_lead_progression_annealing(progression, iterations=annealing_iterations)

    def _total_cost(voicings: list[list[int]]) -> float:
        total = 0.0
        prev = None
        for v in voicings:
            if prev is not None:
                total += _voicing_transition_cost(prev, v)
            prev = v
        return total

    ga_cost = _total_cost(ga_voicings)
    sa_cost = _total_cost(sa_voicings)
    if sa_cost < ga_cost:
        return sa_voicings, 'annealing'
    return ga_voicings, 'ga'


def _voice_lead_choice(chord_name, prev_top=None):
    """Pick the voicing whose top note is closest to prev_top (smooth voice leading).
    Falls back to random choice if prev_top is None or chord has no voicings.
    Greedy per-chord fallback -- build_chords() prefers the whole-progression
    _voice_lead_progression_best() above and only falls back to this on
    failure."""
    options = VOICING_OPTIONS.get(chord_name, [[60, 64, 67]])
    if prev_top is None:
        return random.choice(options)
    return min(options, key=lambda vv: abs(vv[-1] - prev_top))


def build_chords(progression, start_bar, num_loops, swing, bpm, tension: float = 0.5):
    """
    Chords with:
    - Voice-leading voicing: the whole resolved progression is optimized at
      once by _voice_lead_progression_best() (GA + simulated annealing,
      species-counterpoint cost function -- see that function and
      _voicing_transition_cost() above), falling back to the greedy
      nearest-top-note heuristic (_voice_lead_choice) if that ever fails.
    - Strum effect (5-12ms spread)
    - Top note louder (melody voice)
    - 50% comp hit on beat 3
    - Occasional secondary dominant substitution
    - Near peak `tension` (>0.75), a chance to escalate a chord to its denser
      9th-family extension (_CHORD_EXTEND_UP) — part of the storytelling arc,
      additive to the existing substitution roll below.
    """
    loops = max(1, num_loops)

    # ── Resolve pass: pin down the actual chord_name played at every
    # (loop, chord_idx) position first. maybe_sub_chord()/the tension
    # escalation roll both draw fresh randomness on every pass through
    # `progression`, so the sequence isn't fixed ahead of time -- the
    # whole-progression voice-leading optimizers below need a concrete,
    # already-resolved chord sequence to work on.
    resolved: list[tuple[str, int]] = []   # (chord_name, dur_bars), flat across all loops
    for _ in range(loops):
        for chord_idx, (chord_name, dur_bars) in enumerate(progression):
            chord_name = maybe_sub_chord(chord_name, chord_idx)
            if tension > 0.75 and chord_name in _CHORD_EXTEND_UP \
                    and random.random() < (tension - 0.75) * 4:
                chord_name = _CHORD_EXTEND_UP[chord_name]
            resolved.append((chord_name, dur_bars))

    # ── Voice-leading pass: optimize the WHOLE resolved sequence at once
    # (this also gives correct voice-leading continuity across loop-pass
    # boundaries, which the old per-chord prev_top carry-over only
    # approximated). Falls back to the original greedy per-chord choice on
    # any failure -- optional-layer pattern used throughout this codebase,
    # must never block a render.
    #
    # _voice_lead_progression_ga/annealing's default params (pop_size=24,
    # generations=40, iterations=600) were tuned against short progressions
    # -- cost scales roughly linearly with len(resolved), and a long-duration
    # render (many num_loops repeats) can flatten out to hundreds of chords.
    # Measured 2026-08-26: an 8-chord progression at num_loops=20
    # (resolved len 160) took ~7.4s at the defaults. Scale params down for
    # longer sequences so total optimizer cost stays roughly bounded instead
    # of growing without limit for long-duration videos -- floors keep
    # quality reasonable even at the low end (v2's own unit tests get good
    # results from pop_size=8/generations=5-10).
    _VOICE_LEAD_BASE_LEN = 40
    _scale = min(1.0, _VOICE_LEAD_BASE_LEN / max(1, len(resolved)))
    _pop_size     = max(8, int(24 * _scale))
    _generations  = max(10, int(40 * _scale))
    _sa_iterations = max(100, int(600 * _scale))
    try:
        voicings, _winner = _voice_lead_progression_best(
            resolved, pop_size=_pop_size, generations=_generations,
            annealing_iterations=_sa_iterations,
        )
        if len(voicings) != len(resolved):
            raise ValueError("voice-leading pass returned a mismatched length")
    except Exception as e:
        print(f"  [chords] whole-progression voice-leading failed ({e}) — using greedy fallback")
        voicings = []
        prev_top = None
        for chord_name, _dur in resolved:
            voicing = _voice_lead_choice(chord_name, prev_top)
            prev_top = voicing[-1]
            voicings.append(voicing)

    events = []
    cursor = start_bar
    for (chord_name, dur_bars), voicing in zip(resolved, voicings):
        base_t   = grid_tick(cursor * 16, swing)
        note_dur = int(dur_bars * BAR * 0.88)

        for i, note in enumerate(voicing):
            strum_t = int(i * random.uniform(5,12) * (PPQN*bpm)/60000)
            t = _gauss_jitter(base_t, 14, bpm) + strum_t
            if i == len(voicing)-1: vel_val = _gauss_velocity(78, 10)   # top note
            elif i == 0:            vel_val = _gauss_velocity(58,  8)   # bottom
            else:                   vel_val = _gauss_velocity(66, 10)   # inner
            events.append((t, note, vel_val, note_dur))

        # Comp hit beat 3 (50%)
        if dur_bars >= 2 and random.random() < 0.5:
            b3_t = grid_tick(cursor*16 + 8, swing)
            for note in voicing[-3:]:
                events.append((_gauss_jitter(b3_t,16,bpm), note, _gauss_velocity(50,10), int(BAR*0.45)))

        # Occasional beat 2 comp hit (25%)
        if dur_bars >= 2 and random.random() < 0.25:
            b2_t = grid_tick(cursor*16 + 4, swing)
            for note in voicing[-2:]:
                events.append((_gauss_jitter(b2_t,16,bpm), note, _gauss_velocity(44,8), int(BAR*0.30)))

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


# Sentinel note value marking a pitchwheel event inside an (abs_tick, note,
# velocity, duration) events tuple, rather than a real note -- lets glide
# events flow through the same list/`+=` accumulation build_midi() already
# uses for bass_ev, with zero changes needed at any build_bass() call site.
# No real MIDI note is ever negative, so this can't collide with a pitch.
_PITCHWHEEL_NOTE = -1

# Pitch-bend range abs_to_track() sets (via RPN 0,0) on the bass channel
# whenever glide=True is used -- wide enough for drill's 808 slides (research:
# "the single most recognizable production element in modern drill") without
# needing to retune per note.
_GLIDE_BEND_RANGE_SEMITONES = 12


def _bend_semitones_to_pitch14(semitones: float, bend_range_semitones: float = _GLIDE_BEND_RANGE_SEMITONES) -> int:
    """Convert a semitone offset to a 14-bit MIDI pitch-bend value (center=8192),
    given the RPN pitch-bend-range abs_to_track() puts on the channel."""
    raw = 8192 + round((semitones / bend_range_semitones) * 8192)
    return max(0, min(16383, raw))


def _glide_pitchbend_events(note_on_tick: int, note_dur: int, bpm: int,
                            ramp_ms=(80, 150), slide_semitones=(2, 5), steps: int = 6) -> list:
    """808 pitch-slide ornament: a ramp of pitchwheel messages sliding the
    bass note's pitch (mostly down, occasionally up) by a few semitones
    during the last ramp_ms of its duration -- the classic drill 808 "glide"
    at a note's tail (research/subgenres/lofi_drill.md) -- then a reset back
    to center exactly at the note's tail so the next note starts in tune.
    Returns a list of (abs_tick, _PITCHWHEEL_NOTE, pitch14, 0) tuples meant to
    be appended into the same events list build_bass() returns; abs_to_track()
    special-cases note == _PITCHWHEEL_NOTE to emit a real 'pitchwheel' message
    instead of a note on/off pair."""
    if note_dur <= 1:
        return []
    ticks_per_ms = (PPQN * bpm) / 60_000.0
    ramp_ticks = max(1, min(int(random.uniform(*ramp_ms) * ticks_per_ms), note_dur - 1))
    direction = -1 if random.random() < 0.80 else 1   # mostly slides DOWN at the tail
    target_semitones = direction * random.uniform(*slide_semitones)

    start_tick = note_on_tick + (note_dur - ramp_ticks)
    end_tick   = note_on_tick + note_dur

    events = []
    for i in range(1, steps + 1):
        frac = i / steps
        tick = start_tick + int(frac * ramp_ticks)
        events.append((tick, _PITCHWHEEL_NOTE,
                        _bend_semitones_to_pitch14(target_semitones * frac), 0))
    # Reset to center right at the note's tail, before the next note begins.
    events.append((end_tick, _PITCHWHEEL_NOTE, 8192, 0))
    return events


# Small dedicated bend range for gamaka (well under 2 semitones per bend) --
# a separate, finer-resolution range from _GLIDE_BEND_RANGE_SEMITONES since
# it lives on a different channel (melody/counter-melody, not bass) and
# never needs the 808 glide's much wider excursion.
_GAMAKA_BEND_RANGE_SEMITONES = 2
_GAMAKA_PROB = 0.45


def _gamaka_pitchbend_events(note_on_tick: int, note_dur: int, bpm: int,
                             bend_semitones=(0.5, 1.5), ramp_ms=(50, 110),
                             steps: int = 5) -> list:
    """
    Gamaka-style grace-note ornament (research/subgenres/lofi_world.md:
    "grace-note bends around a target pitch, per raga convention" -- the
    genre's most distinctive melodic device, the clearest way to
    differentiate it from other dorian-leaning genres). Unlike
    _glide_pitchbend_events (which slides OUT of a note at its TAIL --
    drill's 808 glide), this bends INTO a note at its ONSET: the note
    starts bent off true pitch by a fraction of a semitone (direction
    random) and eases back to center over the first `ramp_ms` of its
    duration -- the classic meend/kampita "approach" ornament. Returns
    (abs_tick, _PITCHWHEEL_NOTE, pitch14, 0) tuples for the same
    events-list convention as _glide_pitchbend_events(); the melody/
    counter-melody channel must be assembled with abs_to_track(...,
    pitch_bend_range=_GAMAKA_BEND_RANGE_SEMITONES).
    """
    if note_dur <= 1:
        return []
    ticks_per_ms = (PPQN * bpm) / 60_000.0
    ramp_ticks = max(1, min(int(random.uniform(*ramp_ms) * ticks_per_ms), note_dur - 1))
    direction = random.choice([-1, 1])
    start_offset = direction * random.uniform(*bend_semitones)

    events = []
    for i in range(steps + 1):   # i=0 -> full offset at note_on; i=steps -> true pitch
        frac = i / steps
        tick = note_on_tick + int(frac * ramp_ticks)
        semis = start_offset * (1.0 - frac)
        events.append((tick, _PITCHWHEEL_NOTE,
                        _bend_semitones_to_pitch14(semis, _GAMAKA_BEND_RANGE_SEMITONES), 0))
    return events


def build_bass(progression, start_bar, num_loops, swing, bpm, walking=False, glide=False):
    """
    Bass line with:
    - Root on beat 1 (always)
    - Fifth on beat 2-and (syncopated, 70%)
    - Occasional passing note on beat 4-and
    - walking=True: occasional 4-note walking line in last bar of progression
    - glide=True: 808 pitch-slide portamento on the beat-1 root hit's tail
      (drill's signature bass technique) -- see _glide_pitchbend_events().
      Requires the bass track to be assembled with abs_to_track(...,
      pitch_bend_range=_GLIDE_BEND_RANGE_SEMITONES) so the pitchwheel events
      this emits bend by a musically-correct interval.
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
                        t = _gauss_jitter(grid_tick(abs_bar*16 + beat*4, swing), 8, bpm)
                        events.append((t, note, _gauss_velocity(72,10), int(PPQN*0.85)))
                else:
                    # Beat 1: root
                    t1 = _gauss_jitter(grid_tick(abs_bar*16, swing), 8, bpm)
                    root_dur = int(BAR*0.82)
                    events.append((t1, root, _gauss_velocity(80,10), root_dur))
                    # 808 glide: pitch-slide the root's tail (75% of hits) —
                    # the loudest structural differentiator drill has over
                    # its nearest sibling (lofi_phonk), per research.
                    if glide and random.random() < 0.75:
                        events += _glide_pitchbend_events(t1, root_dur, bpm)
                    # Beat 2-and: guide tone (3rd when walking, fifth otherwise) 70%
                    if random.random() < 0.70:
                        t2 = _gauss_jitter(grid_tick(abs_bar*16+6, swing), 8, bpm)
                        events.append((t2, beat2_note, _gauss_velocity(68,12), int(BAR*0.35)))
                    # Beat 3: guide tone (7th when walking, root otherwise) 35%
                    if random.random() < 0.35:
                        t3 = _gauss_jitter(grid_tick(abs_bar*16+8, swing), 8, bpm)
                        events.append((t3, beat3_note, _gauss_velocity(72,10), int(BAR*0.40)))
                    # Beat 4-and passing (20%) — chromatic approach to next chord root
                    if random.random() < 0.20:
                        t4 = _gauss_jitter(grid_tick(abs_bar*16+14, swing), 8, bpm)
                        events.append((t4, approach, _gauss_velocity(60,10), int(S16*1.5)))

            cursor += dur_bars
    return events


def _markov_next_pitch_class(markov_nodes: dict, prev_pc: int, scale_pcs: set,
                             root_pc: int = 0) -> int | None:
    """
    Given a Markov transition table (isobar.MarkovLearner-style — either
    {pitch_class: [successor_pcs...]} or {pitch_class: {successor_pc: count}}),
    sample a next pitch class following prev_pc, filtered to the current
    scale so the result stays diatonically sane. Returns None if no usable
    transition exists (caller falls back to the existing chord/phi-point logic).
    """
    if not markov_nodes:
        return None
    # The table is in scale degrees relative to the key's root (see
    # _save_melody_pitch_classes); a table of absolute pitch classes learned
    # from melodies in different keys says nothing about the next note.
    rel = (prev_pc - root_pc) % 12
    node = markov_nodes.get(rel, markov_nodes.get(str(rel)))
    if not node:
        return None
    if isinstance(node, dict):
        candidates, weights = list(node.keys()), list(node.values())
    else:
        candidates, weights = list(node), [1] * len(node)
    filtered = [((int(c) + root_pc) % 12, w) for c, w in zip(candidates, weights)
                if (int(c) + root_pc) % 12 in scale_pcs]
    if not filtered:
        return None
    cands, wts = zip(*filtered)
    return random.choices(cands, weights=wts, k=1)[0]


def build_melody(key_root, start_bar, num_bars, swing, bpm, density='sparse', scale='pent',
                 motif=None, progression=None, prog_bars=None, markov_nodes=None,
                 tension: float = 0.5, gamaka: bool = False):
    """
    Motif-based melody with phi-point (0.618) contour arc + chord-aware phrase starts.
    Develops a 3-5 note motif through retrograde/inversion/transposition variations.
    Climax velocity peaks at ~61.8% through phrase. First note of each phrase snaps to
    the nearest chord tone (60% chance) so melody lands convincingly on the harmony.

    markov_nodes: optional pitch-class transition table (from
    isobar.MarkovLearner) of scale degrees learned from this pipeline's own
    past melodies. When present, blended in as a probabilistic nudge --
    additive to, not a replacement for, the chord-tone/phi-point logic above.

    tension: 0.0-1.0 storytelling-arc scalar (see _tension()). Higher tension
    raises the phrase-trigger probability (denser phrasing) and biases phrase
    contour toward wider melodic leaps — part of threading the track-wide
    arc through the melody, not just drum velocity. density='dense' (used
    for the climax loop) additionally drops the forced rest floor to 0.

    gamaka: when True, each emitted note has a chance (see _GAMAKA_PROB) of
    a raga-convention grace-note pitch-bend ornament layered on top (see
    _gamaka_pitchbend_events()) -- lofi_world's opt-in only. Requires the
    melody channel to be assembled with abs_to_track(..., pitch_bend_range=
    _GAMAKA_BEND_RANGE_SEMITONES) for the bends to read as musically correct.
    """
    notes_scale = _resolve_scale(scale, key_root)
    if not notes_scale:
        return []

    if motif is None:
        # L-system motif generation as an ADDITIONAL source alongside the
        # stepwise-motion generator, not a replacement -- keeps the
        # channel's established melodic character as the majority case
        # while adding real fractal/structural variety some of the time.
        motif_len = random.randint(3, 5)
        if random.random() < 0.28:
            motif = generate_lsystem_motif(notes_scale, length=motif_len)
        else:
            motif = generate_motif(notes_scale, length=motif_len)

    VARIATIONS = ['retrograde', 'transpose_up', 'invert', 'augment', 'fragment', 'default', 'default']
    var_idx = 0
    events = []
    bar = start_bar
    # Bars of rest after each phrase: call-and-response phrasing, a phrase
    # then a breath, not a phrase every eight bars.
    rest_min = 1 if density == 'sparse' else 0
    scale_pcs = {n % 12 for n in notes_scale}
    prev_final_note = None   # tracks the last emitted note, across phrases, for Markov nudging
    phrase_prob = 0.72 + 0.15 * tension

    while bar < start_bar + num_bars:
        if random.random() < phrase_prob:
            phrase_variation = VARIATIONS[var_idx % len(VARIATIONS)]
            phrase_notes = vary_motif(motif, notes_scale, phrase_variation)
            phrase_dur_scale = _VARIATION_DUR_SCALE.get(phrase_variation, 1.0)
            var_idx += 1
            phrase_len   = len(phrase_notes)
            phrase_start = bar * 16 + random.randint(0, 5)
            phrase_last_g = phrase_start
            prev_step = 0   # leap-then-step-reversal lookback, see below

            for i, note in enumerate(phrase_notes):
                g = phrase_start + i * random.randint(2, 5)
                if g >= (start_bar + num_bars) * 16:
                    break
                phrase_last_g = g

                # Phi-point contour: ascending before 0.618, descending after.
                # Step choice is tension-weighted toward the wider leap as
                # tension rises (0.5 = neutral, matching the old flat choice).
                pos = i / max(1, phrase_len - 1)
                if pos < 0.618:
                    step = random.choices([-1, 0, 1, 2],
                                          weights=[2, 2, 3, 1 + 3 * tension], k=1)[0]
                else:
                    step = random.choices([-2, -1, 0],
                                          weights=[1 + 3 * tension, 3, 2], k=1)[0]
                # Leap-then-step-reversal (research/theory/melody-techniques.md):
                # a leap of a 3rd+ should typically be followed by stepwise
                # motion in the OPPOSITE direction to keep the line balanced
                # -- classical melodic-motion convention, previously
                # unenforced (each note's step was chosen independent of the
                # prior note's). Only kicks in after an actual leap; a plain
                # step or repeated note leaves the phi-point weighting alone.
                if abs(prev_step) >= 2:
                    step = (-1 if prev_step > 0 else 1) * random.choice([1, 2])
                prev_step = step
                idx = notes_scale.index(note) if note in notes_scale else len(notes_scale)//2
                idx = max(0, min(len(notes_scale)-1, idx + step))
                note = notes_scale[idx]

                # Chord-aware phrase start: snap first note to nearest chord tone (60%).
                # Ensures each phrase "lands" on a note that fits the active harmony.
                # Interior notes (i > 0) get the same treatment at a lower
                # probability (25%) -- research/theory/melody-techniques.md:
                # chord-tone awareness previously only applied at phrase-start.
                _snap_prob = 0.60 if i == 0 else 0.25
                if progression and prog_bars and random.random() < _snap_prob:
                    chord_scale = None
                    # Altered-scale / tritone-sub pairing: when the chord
                    # sounding at this bar is itself a secondary-dominant or
                    # tritone-sub *target* (e.g. Db7 subbed in for G7), reach
                    # for get_altered() over its root instead of the track's
                    # main scale (50% of the time) -- see _SEC_DOM_SUB_TARGETS.
                    chord_name_here = _chord_name_at_bar(progression, bar, prog_bars)
                    if chord_name_here in _SEC_DOM_SUB_TARGETS and random.random() < 0.5:
                        alt_root = BASS_ROOTS.get(chord_name_here)
                        if alt_root is not None:
                            chord_scale = get_altered(alt_root)
                    if not chord_scale:
                        chord_pcs = _chord_pcs_at_bar(progression, bar, prog_bars)
                        chord_scale = [n for n in notes_scale if n % 12 in chord_pcs]
                    if chord_scale:
                        note = min(chord_scale, key=lambda n: abs(n - note))

                # Markov-influenced nudge (blended, not a replacement): bias
                # toward a pitch class the source melody's own transition
                # statistics favor after the previous note, when available.
                if markov_nodes and prev_final_note is not None and random.random() < 0.35:
                    target_pc = _markov_next_pitch_class(markov_nodes, prev_final_note % 12,
                                                         scale_pcs, root_pc=key_root % 12)
                    if target_pc is not None:
                        same_pc = [n for n in notes_scale
                                   if n % 12 == target_pc and abs(n - note) <= 14]
                        if same_pc:
                            note = min(same_pc, key=lambda n: abs(n - note))

                prev_final_note = note

                # Velocity arc: louder near phi-point climax
                climax_dist = abs(pos - 0.618)
                vel_arc = int(12 * (1.0 - climax_dist))
                beat_pos  = g % 16
                vel_bonus = 8 if beat_pos == 0 else (4 if beat_pos == 8 else 0)

                t   = _lofi_late(_gauss_jitter(grid_tick(g, swing), 22, bpm), bpm)

                # Grace note: acciaccatura — leading-tone approach 1 step below main note
                # 15% chance on first note of each phrase; adds jazz phrasing feel
                if i == 0 and random.random() < 0.15 and len(notes_scale) > 2:
                    n_idx = notes_scale.index(note) if note in notes_scale else len(notes_scale)//2
                    gn_idx = max(0, n_idx - 1)
                    grace_note = notes_scale[gn_idx]
                    grace_t = max(0, t - int(S16 * 0.35))
                    events.append((grace_t, grace_note, _gauss_velocity(38, 6), int(S16 * 0.30)))
                # Chromatic approach-tone grace note: half-step below the
                # main note regardless of scale membership, bypassing
                # notes_scale entirely -- an alternative to the scale-step
                # acciaccatura above (mutually exclusive on any given note,
                # research/theory/melody-techniques.md: idiomatic in
                # bebop-adjacent jazz/lofi melody, previously impossible
                # since grace notes only ever drew from notes_scale).
                elif i == 0 and random.random() < 0.08:
                    grace_note = note - 1
                    grace_t = max(0, t - int(S16 * 0.35))
                    events.append((grace_t, grace_note, _gauss_velocity(38, 6), int(S16 * 0.30)))
                dur = int(BAR * random.uniform(0.22, 0.72) * phrase_dur_scale)
                if random.random() < 0.30:
                    dur = int(dur * 1.5)
                events.append((t, note, _gauss_velocity(70 + vel_bonus + vel_arc, 13), dur))
                if gamaka and random.random() < _GAMAKA_PROB:
                    events += _gamaka_pitchbend_events(t, dur, bpm)

            # Advance by the phrase's real length in bars. (This used to add
            # the phrase's *note count* as bars, leaving ~3 of 4 bars empty.)
            phrase_bars = max(1, -(-(phrase_last_g + 4 - phrase_start) // 16))
            bar += phrase_bars + random.randint(rest_min, rest_min + 1)
        else:
            bar += random.randint(1, 2)

    return events


def build_arpeggio(progression, start_bar, num_loops, swing, bpm, key_root=None,
                    pattern='up', subdivision=16, octave_range=2):
    """
    Continuous arpeggiator -- synthwave's melodic engine (research/subgenres/
    lofi_synthwave.md): "a repeating note sequence built from the chord tones
    of each chord, running continuously as the harmonic backdrop of the
    entire track," typically 16th notes. Structurally different from
    build_melody(): no rests, no phrase/motif development -- every
    subdivision slot gets a note, cycling through the active chord's tones
    for its full duration, looping the tone-cycle as needed to fill the bars.

    Reuses VOICING_OPTIONS for chord-tone lookup (same table build_chords()/
    build_pad() use) instead of re-deriving pitches.

    pattern: 'up' | 'down' | 'up_down' | 'random'
    subdivision: steps per bar (16 = 16th notes, the genre default; should
      evenly divide 16 for exact grid alignment -- 16, 8, 4).
    octave_range: how many octaves the chord-tone cycle is stacked across
      (each extra octave reuses the same chord tones transposed +12, no new
      pitch material introduced).

    key_root is accepted for signature symmetry with build_melody()/
    build_bass() but unused -- the arpeggio's pitch material comes entirely
    from the chord voicings, not the track's scale/key.
    """
    events = []
    cursor = start_bar
    subdivision = max(1, int(subdivision))
    step_ticks = max(1, BAR // subdivision)
    steps_per_16th = 16 / subdivision

    for _ in range(max(1, num_loops)):
        for chord_name, dur_bars in progression:
            voicing = VOICING_OPTIONS.get(chord_name, [[60, 64, 67]])[0]
            tones = sorted(set(voicing))
            full_tones = [t + 12 * oct_i for oct_i in range(max(1, octave_range)) for t in tones]

            if pattern == 'down':
                seq = list(reversed(full_tones))
            elif pattern == 'up_down' and len(full_tones) > 2:
                seq = full_tones + list(reversed(full_tones))[1:-1]
            else:
                seq = full_tones   # 'up' (default) and 'random' (re-rolled per step below)

            base_bar_tick = cursor * 16
            total_steps = dur_bars * subdivision
            for step in range(total_steps):
                grid = base_bar_tick + int(round(step * steps_per_16th))
                note = random.choice(full_tones) if pattern == 'random' else seq[step % len(seq)]
                t = _gauss_jitter(grid_tick(grid, swing), 6, bpm)
                dur = int(step_ticks * 0.92)
                events.append((t, note, _gauss_velocity(62, 8), dur))

            cursor += dur_bars

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


def build_buildup_fill(end_bar: int, num_bars: int, swing: float, bpm: int) -> list:
    """
    Escalating hi-hat-subdivision ramp for the `num_bars` immediately before
    `end_bar` (where a tension-peak / 'B'-section entry begins) — a riser
    substitute needing no synth sample. Subdivision density ramps
    8th -> 8th-and-16th -> full 16ths across num_bars, velocity ramps up bar
    to bar. ADDITIVE: appended on top of whatever the preceding section's own
    drum builder already emitted at those bars, never a replacement.
    """
    events = []
    num_bars  = max(1, num_bars)
    start_bar = end_bar - num_bars
    for bar_i in range(num_bars):
        abs_bar = start_bar + bar_i
        prog = (bar_i + 1) / num_bars   # ramp progress across the fill, 0-1
        if prog < 0.5:
            steps = [0, 4, 8, 12]
        elif prog < 0.85:
            steps = [0, 2, 4, 6, 8, 10, 12, 14]
        else:
            steps = list(range(16))
        base_vel = int(30 + 55 * prog)
        for step in steps:
            t = jitter(grid_tick(abs_bar * 16 + step, swing), 5, bpm)
            events.append((t, CHH, v(base_vel, 8), 20))
    return events


# "Answering" variations for build_counter_melody()'s call-and-response mode
# -- deliberately excludes 'default' (a near-identical nudge) and 'augment'
# (duration stretch would fight the counter-melody's own note-length roll
# below) so the answer reads as a related-but-distinct response rather than
# an echo of the main melody's call.
_COUNTER_MELODY_ANSWER_VARIATIONS = ['invert', 'retrograde', 'fragment']


def build_counter_melody(key_root: int, start_bar: int, num_bars: int,
                         swing: float, bpm: int, scale: str = 'pent',
                         seed_motif: list | None = None,
                         gamaka: bool = False) -> list:
    """
    Answering melody in lower register (root-12). Fills silence between
    main melody phrases. 1-2 short phrases per num_bars section.
    Very sparse — complements without cluttering.

    scale: same scale-name vocabulary as build_melody() (via the shared
    _resolve_scale() dispatch) -- previously this always hardcoded
    get_pentatonic() regardless of the track's actual scale.

    seed_motif: when provided (pass the main melody's own track_motif),
    each phrase is derived from it via vary_motif() using a contrasting
    "answering" variation (invert/retrograde/fragment) instead of an
    independent random walk -- true call-and-response, where the answer is
    recognizably related to the main melody's call rather than merely
    co-located in time. Falls back to the prior independent-random-walk
    behavior when no seed motif is given, so existing call sites that don't
    pass one keep their exact prior behavior.

    gamaka: see build_melody()'s identical parameter -- koto's counter-
    melody line gets the same raga-convention grace-note bend treatment as
    sitar's lead (research/subgenres/lofi_world.md).
    """
    notes_low = _resolve_scale(scale, key_root - 12) or _resolve_scale(scale, key_root)
    if not notes_low:
        notes_low = get_pentatonic(key_root)
    events = []
    bar = start_bar
    while bar < start_bar + num_bars - 1:
        if random.random() < 0.60:
            if seed_motif:
                answer = vary_motif(seed_motif, notes_low,
                                     random.choice(_COUNTER_MELODY_ANSWER_VARIATIONS))
            else:
                answer = None
            phrase_len = len(answer) if answer else random.randint(1, 3)
            # Offset a little further into the bar than a "call" phrase would
            # start, so the answer follows rather than overlaps the main
            # melody's phrase (call-and-response timing).
            phrase_start = bar * 16 + random.randint(2, 8)
            prev_note = random.choice(notes_low)
            for i in range(phrase_len):
                g = phrase_start + i * random.randint(3, 6)
                if g >= (start_bar + num_bars) * 16:
                    break
                if answer:
                    target = answer[i]
                    note = target if target in notes_low else min(
                        notes_low, key=lambda n: abs(n - target))
                else:
                    idx  = notes_low.index(prev_note) if prev_note in notes_low else len(notes_low) // 2
                    step = random.choice([-1, -1, 0, 1, 1])
                    idx  = max(0, min(len(notes_low) - 1, idx + step))
                    note = notes_low[idx]
                t    = jitter(grid_tick(g, swing), 28, bpm)
                dur  = int(BAR * random.uniform(0.65, 1.55))
                events.append((t, note, v(44, 10), dur))
                if gamaka and random.random() < _GAMAKA_PROB:
                    events += _gamaka_pitchbend_events(t, dur, bpm)
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
    'adj_texture':  ('worn', 'amber', 'pale', 'soft', 'warm', 'faded', 'dusty', 'hazy',
                     'muted', 'dim', 'golden', 'quiet', 'slow', 'grainy', 'velvet',
                     'washed-out', 'blue', 'grey', 'mellow', 'low', 'sleepy', 'cloudy',
                     'distant', 'gentle', 'tender', 'still', 'cold', 'silver'),
    'adj_feeling':  ('tired', 'restless', 'unhurried', 'half-awake', 'quiet', 'lonely',
                     'hopeful', 'wistful', 'calm', 'drowsy', 'unfinished',
                     'easy', 'idle', 'thoughtful', 'homesick', 'patient', 'lazy'),
    'noun_sensory': ('light', 'smoke', 'static', 'groove', 'hum', 'echo', 'rain',
                     'silence', 'dust', 'fog', 'shadow', 'breath', 'glow', 'hiss',
                     'crackle', 'drift', 'steam', 'snow', 'tea', 'coffee', 'neon',
                     'streetlight', 'lamplight', 'moonlight', 'haze', 'breeze', 'vinyl'),
    'noun_place':   ('street', 'window', 'hallway', 'staircase', 'rooftop', 'kitchen',
                     'doorway', 'alley', 'library', 'laundromat', 'bus stop', 'balcony',
                     'fire escape', 'train platform', 'bookshop', 'corner cafe', 'porch',
                     'attic', 'garden', 'harbor', 'record store', 'night bus', 'bedroom',
                     'back seat', 'riverbank', 'study desk'),
    # Bare words that can sit before a noun or after an adjective ("dusty
    # sunday", "midnight vinyl"); phrases with their own article only follow
    # "of" or "until" ("until the small hours"). Mixing the two gave titles
    # like "distant a rainy thursday".
    'time_bare':    ('morning', 'evening', 'afternoon', 'tuesday', 'sunday', 'winter',
                     'autumn', 'spring', 'midnight', 'november', 'dusk', 'dawn',
                     'weekend', 'summer'),
    'time_phrase':  ('the small hours', 'a rainy thursday', 'the night before the exam',
                     'last summer', 'closing time', 'the last train home', 'a snow day',
                     'a slow weekend', 'early march', 'late november', '3am', 'sunday morning'),
    'noun_abstract':('weight', 'longing', 'distance', 'stillness', 'quiet', 'memory',
                     'warmth', 'calm', 'nostalgia', 'comfort', 'daydream', 'patience',
                     'solitude', 'drift', 'afterglow', 'slowness', 'hush'),
    'verb_ing':     ('falling', 'echoing', 'waiting', 'breathing', 'floating', 'drifting',
                     'turning', 'humming', 'settling', 'lingering', 'wandering', 'fading',
                     'dreaming', 'resting', 'swaying', 'glowing', 'melting'),
    'until':        ('the small hours', 'closing time', 'the last train home', '3am',
                     'sunday morning', 'dawn', 'the lights go out', 'the rain stops'),
    'place':        ('on the rooftop', 'by the window', 'in the kitchen', 'down the hallway',
                     'on the staircase', 'in the doorway', 'at the library', 'at the laundromat',
                     'at the bus stop', 'on the balcony', 'on the fire escape', 'in the bookshop',
                     'at the corner café', 'on the porch', 'in the attic', 'in the garden',
                     'by the harbor', 'at the record store', 'on the night bus', 'by the river',
                     'on the train platform', 'in the back seat'),
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

# Every pattern reads as a complete phrase for any choice of words.
_MOOD_PATTERNS: tuple[str, ...] = (
    '{adj_texture} {noun_sensory}',
    'the {noun_abstract} of {time_phrase}',
    '{noun_sensory} {place}',
    '{adj_texture} {time_bare}',
    '{adj_feeling} {time_bare}',
    '{verb_ing} {place}',
    'the last {noun_sensory} of {time_phrase}',
    'until {until}',
    'still {verb_ing}',
    '{time_bare} {noun_sensory}',
    '{noun_sensory} and {noun_sensory}',
    '{adj_feeling} {noun_abstract}',
)


def _compose_mood_phrase(sub_genre: str = '') -> str:
    """Generate a unique mood phrase by combining word banks — never repeats fixed strings."""
    import re as _re
    tint = _MOOD_TINTS.get(sub_genre, {})
    pattern = random.choice(_MOOD_PATTERNS)

    def _pick(m: '_re.Match') -> str:  # type: ignore[name-defined]
        pool = tint.get(m.group(1)) or _MOOD_WORDS.get(m.group(1)) or ('',)
        return random.choice(pool)

    for _ in range(4):   # "rain and rain" is not a title
        result = _re.sub(r'\{([^}]+)\}', _pick, pattern)
        words = [w for w in result.split() if w not in _SMALL_WORDS]
        if len(set(words)) == len(words):
            break
    return _song_case(result)


_SMALL_WORDS = {'a', 'an', 'the', 'and', 'of', 'on', 'in', 'at', 'by', 'to', 'until'}


def _song_case(text: str) -> str:
    """Title Case the way song titles are written ("Until the Small Hours")."""
    words = text.split()
    return ' '.join(w if w[0].isdigit() else
                    w.capitalize() if i == 0 or w not in _SMALL_WORDS else w
                    for i, w in enumerate(words))


_PARAMS_HISTORY_FILE = os.path.join(MUSIC_DIR, '.params_history.json')
_HISTORY_MAXLEN = 30  # keep last N genre+key+prog combos to steer away from


def _load_params_history() -> list[dict]:
    try:
        with open(_PARAMS_HISTORY_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


_HISTORY_LOCK = threading.Lock()   # tracks render on worker threads


def _save_params_history(params: dict) -> None:
    from scripts.fileutil import atomic_write_json
    with _HISTORY_LOCK:
        history = _load_params_history()
        history.append({
            'sub_genre':   params.get('sub_genre', ''),
            'key':         params.get('key', ''),
            'progression': params.get('progression', ''),
            'mood':        params.get('mood', ''),
        })
        try:
            atomic_write_json(_PARAMS_HISTORY_FILE, history[-_HISTORY_MAXLEN:], indent=None)
        except OSError:
            pass


# ─── SELF-REFERENTIAL MELODY HISTORY (Markov, learned from own past output) ───

# Scale degrees relative to each track's key. (The old .melody_history.json
# held absolute pitch classes from mixed keys and isn't reused.)
_MELODY_HISTORY_FILE = os.path.join(MUSIC_DIR, '.melody_degrees_history.json')
_MELODY_HISTORY_MAXLEN = 50  # rolling cap: bounds the model and guards against
                              # Markov mode-collapse from unbounded accumulation


def _load_melody_history() -> list[list[int]]:
    try:
        with open(_MELODY_HISTORY_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_melody_pitch_classes(pitch_classes: list[int]) -> None:
    """Append one track's melody pitch-class sequence to the rolling history."""
    if not pitch_classes:
        return
    from scripts.fileutil import atomic_write_json
    with _HISTORY_LOCK:
        history = _load_melody_history()
        history.append(pitch_classes)
        try:
            atomic_write_json(_MELODY_HISTORY_FILE, history[-_MELODY_HISTORY_MAXLEN:], indent=None)
        except OSError:
            pass


def _build_self_markov(history: list[list[int]]) -> dict:
    """
    Build a pitch-class Markov transition table (isobar.MarkovLearner-style:
    {pc: [successor_pcs...]}) from the pipeline's own historically-generated
    melodies, so the system develops an evolving "melodic voice" from its own
    output over time — no external data, no LLM call. Each track's sequence
    is learned independently (learner.last reset between tracks) so
    transitions never falsely bridge across unrelated tracks.
    """
    from isobar import MarkovLearner
    learner = MarkovLearner()
    for track_pcs in history:
        learner.last = None
        for pc in track_pcs:
            learner.register(pc)
    return dict(learner.markov.nodes)


# ─── RECIPE LOG (diagnostic, append-only) ─────────────────────────────────────

_RECIPE_LOG_FILE = os.path.join(MUSIC_DIR, '.recipe_log.jsonl')


def _append_recipe_log(params: dict, quality_score: float | None = None,
                        quality_retries: int | None = None,
                        ga_voicing: bool | None = None,
                        voicing_optimizer_wins: dict | None = None) -> None:
    """
    Append-only JSONL diagnostic log: one line per generated track, recording
    which generative techniques fired and (once the quality gate runs) how it
    scored. Deliberately append-only (no read-modify-write) so it can't
    inherit _save_params_history's latent read-modify-write race under
    generate_tracks()'s ThreadPoolExecutor (up to 3 concurrent pick_params()
    calls). Lets a user debugging "why did today's video sound different"
    weeks into unattended daily runs answer it directly via `tail`, without
    re-deriving anything from the audio/video itself.
    """
    entry = {
        'ts':              round(time.time()),
        'sub_genre':       params.get('sub_genre', ''),
        'key':             params.get('key', ''),
        'bpm':             params.get('bpm', ''),
        'euclid_a':        params.get('drum_pattern_a_source') == 'euclidean',
        'euclid_b':        params.get('drum_pattern_b_source') == 'euclidean',
        'ca_rhythm_a':     params.get('drum_pattern_a_source') == 'ca',
        'ca_rhythm_b':     params.get('drum_pattern_b_source') == 'ca',
        'markov_prog':     'generated_progression' in params,
        'harmony_engine':  'harmony_progression' in params,
        'self_markov':     'markov_melody_nodes' in params,
        'ga_voicing':      bool(ga_voicing),
        # Which whole-progression voicing optimizer (GA vs. simulated
        # annealing — see _voice_lead_progression_best in generate_music_v2.py)
        # won the lower-cost comparison each time it fired this track, e.g.
        # {"ga": 2, "annealing": 1}. None when the optimizer never fired.
        'voicing_optimizer_wins': voicing_optimizer_wins,
        'quality_score':   quality_score,
        'quality_retries': quality_retries,
    }
    try:
        os.makedirs(os.path.dirname(_RECIPE_LOG_FILE), exist_ok=True)
        with open(_RECIPE_LOG_FILE, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except OSError:
        pass


_AUDIO_QUALITY_LOG_FILE = os.path.join(MUSIC_DIR, '.audio_quality_log.jsonl')


def _append_audio_quality_log(wav_path: str, score: float, failures: list[str]) -> None:
    """
    Append-only JSONL diagnostic log for the AUDIO-domain quality gates (see
    scripts/track_quality.score_audio_quality) — separate file from
    _RECIPE_LOG_FILE since this runs at a different pipeline stage (after
    the final WAV exists, not at param-pick time) and a caller debugging
    "was this specific published file clipped/silent/off-loudness" wants to
    grep by filename, not merge into the per-param recipe log. Same
    append-only, best-effort (never raises) design as _append_recipe_log.
    """
    entry = {
        'ts':       round(time.time()),
        'file':     os.path.basename(wav_path),
        'score':    score,
        'failures': failures,
    }
    try:
        os.makedirs(os.path.dirname(_AUDIO_QUALITY_LOG_FILE), exist_ok=True)
        with open(_AUDIO_QUALITY_LOG_FILE, 'a') as f:
            f.write(json.dumps(entry) + '\n')
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

    # Engagement-analytics feedback (Thompson-sampling bandit over watch-
    # ratio/CTR/like/comment-rate — see analytics.sub_genre_weights()):
    # multiply the diversity-driven base weights above by how well each
    # sub-genre has actually performed. Neutral 1.0 for every sub-genre when
    # there's no/insufficient data (cold start), so this is a no-op until
    # enough videos have been synced. try/except-guarded exactly like every
    # other optional layer in pick_params() — a missing/corrupt
    # analytics_log.json or any other failure here must never block a
    # render, just fall back to the base diversity weighting.
    try:
        from scripts.analytics import sub_genre_weights
        engagement_w = sub_genre_weights(all_subs)
        weights = [w * engagement_w.get(s, 1.0) for w, s in zip(weights, all_subs)]
    except Exception as e:
        print(f"  [params] sub_genre engagement weighting failed ({e}) — using base weights")

    return random.choices(all_subs, weights=weights, k=1)[0]


def _pick_progression_avoiding_recent(sub: str, cfg: dict, history: list[dict]) -> int:
    """Pick a progression not recently used for this sub-genre.

    Dedupes on (sub_genre, progression) directly rather than (sub_genre, key) —
    `key` is now derived from whichever progression gets picked here (see
    PROGRESSION_KEY), not picked independently beforehand, so deduping on the
    actual chord content is the more direct check.
    """
    recent: set[int] = set()
    for h in history[-10:]:
        if h.get('sub_genre') == sub:
            raw = h.get('progression', '')
            if str(raw).lstrip('-').isdigit():
                recent.add(int(raw))
    available = [p for p in cfg['progs'] if p not in recent] or list(cfg['progs'])
    return random.choice(available)


def _resolve_genre_hint(hint: str) -> str | None:
    """Map a free-text genre hint to a known sub_genre key, or None."""
    normalized = hint.lower().replace(' ', '_').replace('-', '_')
    # A published genre label ("bossa nova lofi", "jazz hop"). Labels shared
    # by several sub-genres ("lo-fi hip hop") mean "no preference" and fall
    # through to the weighted pick.
    from scripts.generate_seo import _SUBGENRE_TO_GENRE_LABEL as _labels
    owners = [k for k, v in _labels.items() if v == hint.strip().lower()]
    if len(owners) == 1 and owners[0] in _SUBGENRE_CONFIG:
        return owners[0]
    # Exact match
    if normalized in _SUBGENRE_CONFIG:
        return normalized
    # Match ignoring underscores ("lo-fi jazz" → "lofi_jazz")
    norm_bare = normalized.replace('_', '')
    for s in _SUBGENRE_CONFIG:
        if s.replace('_', '') == norm_bare:
            print(f"  [params] genre_hint '{hint}' resolved to '{s}'")
            return s
    # Substring fallback, only when it names exactly one genre: "lofi" used to
    # pick anime_lofi (first in the table) and "jazz" jazz_cafe over lofi_jazz.
    matches = [s for s in _SUBGENRE_CONFIG if normalized in s or s in normalized]
    if len(matches) == 1:
        print(f"  [params] genre_hint '{hint}' resolved to '{matches[0]}'")
        return matches[0]
    if matches:
        print(f"  [params] genre_hint '{hint}' is ambiguous ({', '.join(matches)}); picking by weight")
    return None


def _pick_mood_phrase(concept_hint: str | None = None, sub_genre: str = '',
                      history: list[dict] | None = None) -> str:
    """Poetic mood phrase. Procedural composer is primary (combinatorial word-bank
    generator). Retries a few times to avoid the last 10 phrases used."""
    # A short, explicit mood (run.py --mood "rainy jazz") names the track; a
    # whole video concept ("cottagecore · wildflowers, handwritten recipes,
    # afternoon light...") is not a song title.
    if concept_hint and len(concept_hint.split()) <= 5 and '·' not in concept_hint:
        return _song_case(concept_hint)

    recent = {h['mood'] for h in (history or [])[-10:] if h.get('mood')}
    phrase = _compose_mood_phrase(sub_genre)
    for _ in range(5):
        if phrase not in recent:
            return phrase
        phrase = _compose_mood_phrase(sub_genre)

    return _compose_mood_phrase(sub_genre)


_MAJOR_STEPS = (0, 2, 4, 5, 7, 9, 11)
_MINOR_STEPS = (0, 2, 3, 5, 7, 8, 10, 9, 11)   # natural minor + dorian 6th + leading tone


def _key_pitch_classes(key: str) -> set:
    root = KEY_ROOTS.get(key, 57) % 12
    steps = _MINOR_STEPS if key.endswith('m') else _MAJOR_STEPS
    return {(root + s) % 12 for s in steps}


def progression_fits_key(progression, key: str, max_outside: float = 0.25) -> bool:
    """True if at most `max_outside` of the chords use notes outside `key`.
    Unknown chord symbols count as outside."""
    key_pcs = _key_pitch_classes(key)
    chords = [name for name, _ in progression]
    if not chords:
        return False
    outside = 0
    for name in chords:
        voicings = VOICING_OPTIONS.get(name)
        if not voicings or {n % 12 for v in voicings for n in v} - key_pcs:
            outside += 1
    return outside / len(chords) <= max_outside


def pick_params(concept_hint: str | None = None, genre_hint: str | None = None) -> dict:
    history = _load_params_history()

    sub = (_resolve_genre_hint(genre_hint) if genre_hint else None) or _pick_subgenre_weighted(history)
    cfg  = _SUBGENRE_CONFIG[sub]
    prog = _pick_progression_avoiding_recent(sub, cfg, history)
    # `key` is derived from the chosen progression's real tonal center (see
    # PROGRESSION_KEY) rather than picked independently — previously these were
    # two unrelated random draws, so the melody scale could land in a key with
    # no relation to the chords actually playing underneath it.
    key  = PROGRESSION_KEY[prog]

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
        'melody_density': _MELODY_DENSITY.get(sub) or random.choice(['sparse', 'medium']),
        'melody_scale':   random.choice(cfg['scale']),
        'bass_walking':   _WALKING_BASS.get(sub, random.random() < 0.4),
        'drum_pattern_a': pat_a,
        'drum_pattern_b': pat_b,
        'drum_energy':    drum_energy,
        'sub_genre':      sub,
    }

    # Engagement-analytics soft nudge on BPM (see analytics.bpm_bucket_weights()):
    # re-roll within the subgenre's own bpm range, weighted toward whichever
    # 10-bpm bucket has historically performed best, instead of the plain
    # random.randint() draw above winning outright. A subgenre's bpm range is
    # often narrow (10-20 bpm wide), so this draws a small set of candidate
    # bpms spanning that range (including the original draw) and re-picks
    # among them by bucket weight — a soft bias, not a hard override, and it
    # degrades to the plain random.randint() result whenever there's no
    # engagement data (bpm_bucket_weights() returns {} at cold start, so
    # every candidate gets an equal 1.0 weight). try/except-guarded exactly
    # like every other optional layer in this function — never blocks a render.
    try:
        lo, hi = cfg['bpm']
        if hi > lo:
            from scripts.analytics import bpm_bucket_weights
            bpm_bucket_w = bpm_bucket_weights()
            # Not the endpoints: adding lo and hi as fixed candidates put ~45% of
            # all tracks exactly on the slowest or fastest tempo of their genre.
            candidates = sorted({params['bpm'], *(random.randint(lo, hi) for _ in range(3))})
            cand_weights = [bpm_bucket_w.get((c // 10) * 10, 1.0) for c in candidates]
            params['bpm'] = random.choices(candidates, weights=cand_weights, k=1)[0]
    except Exception as e:
        print(f"  [params] BPM engagement re-roll failed ({e}) — using plain random bpm")

    # ~35% independent chance each for A/B drum sections to use a freshly
    # generated Euclidean pattern instead of the curated table (Phase-A
    # adoption bump; started at 20%). Each call is individually try/except'd
    # so a failure on one side never blocks the other, or the rest of
    # pick_params() — daily unattended runs must never crash over an optional
    # embellishment.
    energy_f = _DRUM_ENERGY_TO_FLOAT.get(drum_energy, 0.55)
    complexity_f = round(random.uniform(0.3, 0.8), 2)
    # 3-against-4 cross-rhythm (see generate_polyrhythm_pattern) -- gated to
    # subgenres a genuine polyrhythmic layer actually suits (research/
    # theory/rhythm-groove.md's new-this-session finding: lofi_world's
    # tala-cycle-inspired percussion identity, and nujabes-style jazzier
    # genres), not offered to every genre the way Euclidean/CA are.
    _polyrhythm_genres = {'lofi_world', 'nujabes'}
    # Euclidean/CA patterns know nothing about genre; they used to replace
    # the curated groove in about half of all sections of every genre.
    # Now only genres that opt in (generated_drums) get them.
    gen_ok = sub in _GENERATED_DRUM_GENRES
    if gen_ok and random.random() < 0.35:
        try:
            params['drum_pattern_a_generated'] = generate_euclidean_drum_pattern(energy_f, complexity_f)
            params['drum_pattern_a_source'] = 'euclidean'
        except Exception as e:
            print(f"  [params] Euclidean drum A generation failed ({e}) — using curated table")
    elif sub in _polyrhythm_genres and random.random() < 0.25:
        try:
            params['drum_pattern_a_generated'] = generate_polyrhythm_pattern(energy_f)
            params['drum_pattern_a_source'] = 'polyrhythm'
        except Exception as e:
            print(f"  [params] Polyrhythm drum A generation failed ({e}) — using curated table")
    elif gen_ok and random.random() < 0.20:
        # Cellular-automaton pattern (see generate_ca_drum_pattern) — a
        # second procedural rhythm source, mutually exclusive with the
        # Euclidean roll above (both write the same override slot) but
        # picked with a comparable ~20% probability, within the same
        # 15-35% range the Euclidean generator itself uses.
        try:
            params['drum_pattern_a_generated'] = generate_ca_drum_pattern(energy_f, complexity_f)
            params['drum_pattern_a_source'] = 'ca'
        except Exception as e:
            print(f"  [params] CA drum A generation failed ({e}) — using curated table")
    if gen_ok and random.random() < 0.35:
        try:
            params['drum_pattern_b_generated'] = generate_euclidean_drum_pattern(energy_f, complexity_f)
            params['drum_pattern_b_source'] = 'euclidean'
        except Exception as e:
            print(f"  [params] Euclidean drum B generation failed ({e}) — using curated table")
    elif sub in _polyrhythm_genres and random.random() < 0.25:
        try:
            params['drum_pattern_b_generated'] = generate_polyrhythm_pattern(energy_f)
            params['drum_pattern_b_source'] = 'polyrhythm'
        except Exception as e:
            print(f"  [params] Polyrhythm drum B generation failed ({e}) — using curated table")
    elif gen_ok and random.random() < 0.20:
        try:
            params['drum_pattern_b_generated'] = generate_ca_drum_pattern(energy_f, complexity_f)
            params['drum_pattern_b_source'] = 'ca'
        except Exception as e:
            print(f"  [params] CA drum B generation failed ({e}) — using curated table")

    # ~30% chance to procedurally generate a fresh progression (Markov walk
    # over the curated table's chord transitions) instead of indexing into the
    # fixed 51-entry table (Phase-A bump; started at 18%) — params['progression']
    # keeps its int index either way (for history/logging); generated_progression,
    # when present, takes priority in build_midi().
    # The walk pools transitions from progressions written in different keys,
    # so it can wander off the melody's key; only keep walks that stay in it.
    if random.random() < 0.30:
        try:
            chord_count = len(PROGRESSIONS[prog]) if PROGRESSIONS[prog] else 4
            for _attempt in range(6):
                walked = generate_progression(
                    length=max(2, min(6, chord_count)),
                    jazziness=round(random.uniform(0.2, 0.8), 2),
                    seed_chord=PROGRESSIONS[prog][0][0],
                )
                if progression_fits_key(walked, key):
                    params['generated_progression'] = walked
                    break
        except Exception as e:
            print(f"  [params] Progression generation failed ({e}) — using curated table")

    # ~20% chance to use the music21-backed functional-harmony engine
    # (Roman-numeral T-S-D walk with secondary-dominant tonicization; see
    # harmony_engine.py) instead of the curated table / bigram Markov walk
    # above. Gated behind HARMONY_ENGINE_ENABLED (default on) so it can be
    # switched off pipeline-wide without touching call sites, and behind a
    # per-track probability roll so existing behavior is not silently
    # changed for every track. params['harmony_progression'], when present,
    # takes top priority in build_midi() (see the `prog = ...` fallback
    # chain there) — mirrors how generated_progression already layers over
    # the fixed table.
    if os.getenv('HARMONY_ENGINE_ENABLED', '1') != '0' and random.random() < 0.20:
        try:
            from scripts.harmony_engine import generate_functional_progression, center_for_key
            chord_count = len(PROGRESSIONS[prog]) if PROGRESSIONS[prog] else 4
            center, hmode = center_for_key(key)
            hp = generate_functional_progression(
                tonal_center=center, mode=hmode,
                length=max(2, min(6, chord_count)),
                secondary_dominant_prob=round(random.uniform(0.2, 0.5), 2),
            )
            params['harmony_progression'] = hp.chords
            params['harmony_roman_numerals'] = hp.roman_numerals
        except Exception as e:
            print(f"  [params] Harmony-engine progression failed ({e}) — using curated table")

    # Self-referential melodic voice: once enough history exists, bias new
    # melodies toward the pipeline's own past output (no external data, no
    # LLM) — see _build_self_markov / build_melody's markov_nodes blending.
    # Capped at 75% (not unconditional) both to bound the blast radius of any
    # latent bug in this newly-wired-up path and to hedge against slow
    # Markov mode-collapse from training on the pipeline's own output daily.
    try:
        _melody_history = _load_melody_history()
        if len(_melody_history) >= 3 and random.random() < 0.75:
            params['markov_melody_nodes'] = _build_self_markov(_melody_history)
    except Exception as e:
        print(f"  [params] Self-referential Markov build failed ({e}) — skipping")

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
# Lofi tracks run roughly two to four minutes. Forms are written in loops
# of the progression, so the real length depends on the progression's bar
# count and the tempo; fit_form_length() adds or removes loops of the main
# sections to land inside this window.
TRACK_MIN_SECS = 120
TRACK_MAX_SECS = 240
_RESIZABLE_SECTIONS = ('A', 'B', 'BR')


def form_seconds(form, prog_bars: int, bpm: float) -> float:
    return sum(n for _, n in form) * prog_bars * 4 * 60.0 / bpm


def fit_form_length(form, prog_bars: int, bpm: float,
                    lo: float = TRACK_MIN_SECS, hi: float = TRACK_MAX_SECS) -> list:
    """Return a copy of `form` with A/B/BR loop counts adjusted so the track
    lasts between `lo` and `hi` seconds (as close as the loop size allows).
    Sections are never dropped; each keeps at least one loop."""
    form = [list(sec) for sec in form]
    loop_secs = prog_bars * 4 * 60.0 / bpm
    for _ in range(64):
        secs = sum(n for _, n in form) * loop_secs
        if secs > hi:
            shrinkable = [sec for sec in form if sec[0] in _RESIZABLE_SECTIONS and sec[1] > 1]
            if not shrinkable:
                break
            max(shrinkable, key=lambda sec: sec[1])[1] -= 1
        elif secs < lo and secs + loop_secs <= hi + loop_secs / 2:
            growable = [sec for sec in form if sec[0] in ('A', 'B')] or \
                       [sec for sec in form if sec[0] in _RESIZABLE_SECTIONS]
            if not growable:
                break
            min(growable, key=lambda sec: sec[1])[1] += 1
        else:
            break
    return [tuple(sec) for sec in form]


_SONG_FORMS = {
    'standard': [('I',1),('A',4),('BR',1),('B',4),('O',1)],   # 1+4+1+4+1 = 11 loops
    'ambient':  [('I',2),('A',6),('BR',2),('B',4),('O',2)],   # longer drift = 16
    'funk':     [('I',2),('A',6),('BR',1),('B',6),('O',1)],   # energy-forward = 16
    'minimal':  [('A',2),('BR',1),('B',2)],                    # tight = 5 loops
    'extended': [('I',1),('A',4),('BR',2),('B',6),('O',2)],   # long nujabes = 15
    # research/theory/arrangement-structure.md #5: canonical 32-bar jazz-
    # standard AABA shape (two A statements, a contrasting bridge, a final
    # A) -- BR doubles as the "B"/bridge section, consistent with how
    # _bridge_progression() already reharmonizes BR. For bossa_lofi/jazz_cafe,
    # which currently fall back to 'standard' despite being the two
    # subgenres most rooted in jazz-standard form.
    'aaba':     [('I',1),('A',2),('A',2),('BR',2),('A',2),('O',1)],  # 10 loops
    # research/theory/arrangement-structure.md #6: approximates phonk/drill's
    # buildup->release cycling using only existing labels -- BR repurposed as
    # a short filtered-buildup section immediately preceding a return to
    # full-energy A, cycled three times, instead of the ambient-style single
    # mid-track breakdown the other forms use. No B section: phonk/drill
    # arrangement is repetition-with-layer-swap, not a long contrasting
    # drop-down section.
    'build':    [('I',1),('A',3),('BR',1),('A',3),('BR',1),('A',3),('O',1)],  # 13 loops
}
_FORM_BY_SUBGENRE = genre_presets.build_form_overrides()

# ─── GENERATIVE SONG-FORM GRAMMAR ──────────────────────────────────────────
# An ADDITIONAL, more varied alternative to the 5 hand-authored _SONG_FORMS
# above, not a replacement — wired into build_midi()/build_midi_v2() with a
# per-track probability roll (see there), same style as the other Stage-3
# optional-generative-layer toggles (harmony engine, CA rhythm, etc.).
#
# Grammar (informal EBNF, matching the existing (label, num_prog_loops) form
# shape build_midi already consumes):
#     form   := 'I' ('A' break? 'B')+ 'O'
#     break  := 'BR' | ε                      (optional, ~45% of the time)
# i.e. intro, then one or more (A section, then one-or-more optional-break+B
# groups), then outro — a direct generative expansion of the same section
# vocabulary the curated forms already use ('I'/'A'/'BR'/'B'/'O'), so it
# drops into the exact same consumption code with zero changes there.
#
# Bounded by construction (not by discard-and-retry) so it always
# terminates and never produces a "wildly long or degenerate" structure:
# loop counts are drawn from small per-label ranges, and the running total
# is hard-capped at _FORM_GRAMMAR_MAX_TOTAL_LOOPS (comparable in scale to
# the existing hand-authored forms' 5-16 loop range) by refusing/clamping
# any addition that would exceed it.
_FORM_GRAMMAR_LOOP_RANGES = {
    'I': (1, 2), 'A': (2, 5), 'BR': (1, 2), 'B': (2, 5), 'O': (1, 2),
}
_FORM_GRAMMAR_MAX_TOTAL_LOOPS = 20
_FORM_GRAMMAR_MAX_TOP_GROUPS = 2
_FORM_GRAMMAR_MAX_B_REPEATS = 2
_FORM_GRAMMAR_BREAK_PROB = 0.45


def generate_song_form(seed: int | None = None) -> list[tuple[str, int]]:
    """
    Generate a song form by seeded random expansion of the
    'I (A (BR? B)+)+ O' grammar above. Returns a list of
    (section_label, num_prog_loops) tuples — the exact same shape as
    _SONG_FORMS entries, so it's a drop-in alternative wherever a form is
    consumed. Deterministic given `seed` (uses a local Random instance so
    it never disturbs the pipeline's global random stream when called with
    an explicit seed); uses the shared global stream when seed is None,
    consistent with how the rest of this module's optional generative
    layers behave when wired into the real per-track pipeline (determinism
    then comes from whatever top-level seed the caller set, not a
    per-feature seed threaded through params).
    """
    rng = random.Random(seed) if seed is not None else random

    def _loops(label: str) -> int:
        lo, hi = _FORM_GRAMMAR_LOOP_RANGES[label]
        return rng.randint(lo, hi)

    intro_loops = _loops('I')
    form: list[tuple[str, int]] = [('I', intro_loops)]
    total = intro_loops

    n_top_groups = rng.randint(1, _FORM_GRAMMAR_MAX_TOP_GROUPS)
    for _ in range(n_top_groups):
        if total >= _FORM_GRAMMAR_MAX_TOTAL_LOOPS:
            break
        a_loops = min(_loops('A'), max(1, _FORM_GRAMMAR_MAX_TOTAL_LOOPS - total))
        form.append(('A', a_loops))
        total += a_loops

        n_b_repeats = rng.randint(1, _FORM_GRAMMAR_MAX_B_REPEATS)
        for _ in range(n_b_repeats):
            if total >= _FORM_GRAMMAR_MAX_TOTAL_LOOPS:
                break
            if rng.random() < _FORM_GRAMMAR_BREAK_PROB:
                br_loops = _loops('BR')
                if total + br_loops <= _FORM_GRAMMAR_MAX_TOTAL_LOOPS:
                    form.append(('BR', br_loops))
                    total += br_loops
            b_loops = min(_loops('B'), max(1, _FORM_GRAMMAR_MAX_TOTAL_LOOPS - total))
            form.append(('B', b_loops))
            total += b_loops

    outro_loops = _loops('O')
    form.append(('O', outro_loops))
    return form


# Section-boundary transition FX (research/theory/arrangement-structure.md
# "Genuine gap #1: section-boundary transition FX are entirely unmodeled" --
# confirmed via grep, zero existing code for this before now). Keyed by
# (from_label, to_label); the 3 values name real DSP effects implemented in
# scripts/lofi_fx.py (_apply_vinyl_stop/_apply_reverse_riser/
# _apply_filter_sweep) -- a well-documented, distinct layer of lofi/hip-hop
# production the form tuples alone don't touch (they only encode section
# duration, never the handoff between sections).
#
# Wired end-to-end: build_midi() calls _compute_section_transitions() (see
# below) and returns its result; generate_track() threads it through
# apply_lofi_fx() into _apply_pedalboard(), which fires the actual FX
# (lofi_fx._apply_vinyl_stop/_apply_reverse_riser/_apply_filter_sweep) on
# the rendered audio.
_SECTION_TRANSITION_FX: dict[tuple[str, str], str] = {
    ('A', 'BR'):  'filter_lowpass_sweep',
    ('BR', 'A'):  'vinyl_stop',
    ('A', 'B'):   'reverse_riser',
    ('B', 'O'):   'filter_lowpass_sweep',
    ('BR', 'B'):  'reverse_riser',
}


def section_transition_fx_for(from_label: str, to_label: str) -> str | None:
    """Look up the transition FX (if any) for a section-boundary hand-off.
    Returns None for boundary pairs with no defined transition (most pairs
    -- this is deliberately sparse, not every hand-off needs an FX)."""
    return _SECTION_TRANSITION_FX.get((from_label, to_label))


def _compute_section_transitions(form: list[tuple[str, int]], prog_bars: int,
                                  bpm: float, sr: int = 44100) -> list[tuple[int, str]]:
    """
    Walk `form`'s section sequence and return (sample_position, fx_name) for
    every section-boundary hand-off that section_transition_fx_for() defines
    an effect for. `sample_position` is where the transition FX's window
    should END (see _apply_vinyl_stop/_apply_reverse_riser/
    _apply_filter_sweep's `at_sample` semantics) -- i.e. the sample offset
    of the boundary itself, computed from bar offset via BAR=1920 ticks
    (4 beats) at the track's actual bpm, matching midi_to_wav's fixed 44.1kHz
    render rate.
    """
    bar_seconds = 240.0 / bpm   # 4 beats/bar * 60s/min / bpm
    transitions: list[tuple[int, str]] = []
    bar = 0
    prev_label = None
    for label, n_loops in form:
        if prev_label is not None:
            fx = section_transition_fx_for(prev_label, label)
            if fx is not None:
                transitions.append((int(bar * bar_seconds * sr), fx))
        bar += prog_bars * n_loops
        prev_label = label
    return transitions


# Sections where the arrangement plays the full beat. The sampled drum break
# layered on after rendering (drum_sampler.layer_drum_break) belongs only
# here; intros, bridges and outros have their own sparser drum parts.
_FULL_BEAT_SECTIONS = ('A', 'B')


def full_beat_span_labels(form: list[tuple[str, int]]) -> list[str]:
    """Section label ('A'/'B') of each span full_beat_spans() returns, in
    order (a merged run takes its first section's label)."""
    labels, prev_full = [], False
    for label, _n in form:
        full = label in _FULL_BEAT_SECTIONS
        if full and not prev_full:
            labels.append(label)
        prev_full = full
    return labels


def full_beat_spans(form: list[tuple[str, int]], prog_bars: int, bpm: float,
                    sr: int = 44100) -> list[tuple[int, int]]:
    """(start_sample, end_sample) for each A/B section, adjacent spans merged."""
    bar_seconds = 240.0 / bpm
    spans: list[tuple[int, int]] = []
    bar = 0
    for label, n_loops in form:
        end_bar = bar + prog_bars * n_loops
        if label in _FULL_BEAT_SECTIONS:
            start, end = int(bar * bar_seconds * sr), int(end_bar * bar_seconds * sr)
            if spans and spans[-1][1] == start:
                spans[-1] = (spans[-1][0], end)
            else:
                spans.append((start, end))
        bar = end_bar
    return spans


# Avoid-note filter. Several chord sources can put a chord under the melody
# that isn't in the melody's key: deliberate borrowed chords in the curated
# table, the Markov progression walk, the functional-harmony engine's
# secondary dominants, and the bridge reharmonization. A melody note one
# semitone above a chord tone (a minor 9th against it) is the classic
# "wrong note" clash, so any sustained melodic note that lands there is
# pulled down onto that chord tone. Short passing notes are left alone.
_CLASH_MIN_DUR = PPQN // 2          # eighth note or longer
_CHORD_GATHER_TICKS = PPQN // 2     # chord notes struck within this window form one chord


def _chord_timeline(piano_ev: list[tuple]) -> tuple[list[int], list[set]]:
    """Group piano note onsets into chords: (sorted onset ticks, pitch-class sets)."""
    notes = sorted((ev[0], ev[1]) for ev in piano_ev if ev[1] != _PITCHWHEEL_NOTE)
    times: list[int] = []
    chords: list[set] = []
    for t, n in notes:
        if times and t - times[-1] <= _CHORD_GATHER_TICKS:
            chords[-1].add(n % 12)
        else:
            times.append(t)
            chords.append({n % 12})
    return times, chords


def fix_melodic_clashes(events: list[tuple], piano_ev: list[tuple]) -> tuple[list[tuple], int]:
    """Move sustained notes that sit a semitone above a chord tone (and aren't
    chord tones themselves) down onto that chord tone. Returns (events, n_fixed)."""
    import bisect
    times, chords = _chord_timeline(piano_ev)
    if not times:
        return events, 0
    out, fixed = [], 0
    for ev in events:
        t, note = ev[0], ev[1]
        if note == _PITCHWHEEL_NOTE or ev[3] < _CLASH_MIN_DUR:
            out.append(ev)
            continue
        i = bisect.bisect_right(times, t + _CHORD_GATHER_TICKS // 2) - 1
        if i < 0:
            out.append(ev)
            continue
        pcs = chords[i]
        pc = note % 12
        if len(pcs) >= 3 and pc not in pcs and (pc - 1) % 12 in pcs:
            ev = (t, note - 1) + tuple(ev[2:])
            fixed += 1
        out.append(ev)
    return out, fixed


# Secondary genre-specific instrument texture layer
# (program, style) — style controls rhythm pattern for that instrument character
_SUBGENRE_TEXTURE = genre_presets.build_subgenre_texture()


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


# Tala-cycle polymetric overlay (research/subgenres/lofi_world.md: "tala
# rhythmic cycles" -- alongside gamaka and drone/modal harmony, one of the
# three techniques the raga/maqam research grounds this genre in; Phase 11's
# "true time-signature support" item). This is genuinely odd-meter -- a
# 7-beat cycle, NOT reachable by subdividing or regrouping the existing 4/4
# BAR/grid_tick()/DRUM_PATTERNS grid every one of the other 28 genres
# depends on -- but implemented as a fully independent overlay with its own
# tick math (multiples of PPQN per beat, nothing derived from BAR or S16),
# LAYERED on top of the existing 4/4 foundation rather than replacing any
# part of it. This is the deliberately-scoped alternative to a full
# variable-time-signature retrofit: parametrizing grid_tick()/BAR/every
# DRUM_PATTERNS entry's step count throughout build_chords/build_bass/
# build_melody/build_drums/etc. would touch code every genre depends on
# (see this function's own research-doc citation above) -- real, but a
# separate, much larger, higher-blast-radius undertaking than fits safely
# in the same change set as everything else in this backlog. This overlay
# achieves the same "genuinely odd-meter, not just cross-rhythm" goal
# (distinct from Phase 5's 3-vs-4 polyrhythm, which stays within one 4/4
# bar) with zero risk to any function outside this one: BAR/grid_tick()/
# DRUM_PATTERNS/build_drums() are never touched or even imported here in a
# meter-aware way.
#
# Rupak Tal (Hindustani classical, 7 beats grouped 3+2+2) -- chosen over an
# arbitrary odd grouping because it's a real, named, idiomatic cycle from
# the same raga/tala tradition gamaka is drawn from, and because its
# defining characteristic (no bass stroke on beat 1 -- a deliberately
# "empty"/de-accented downbeat) gives this overlay an audibly different
# character from the main track's strong-downbeat 4/4 foundation rather
# than just being "4/4 with an extra beat stapled on."
_TALA_BEAT_GROUPS = (3, 2, 2)   # Rupak Tal
_TALA_BEATS_PER_CYCLE = sum(_TALA_BEAT_GROUPS)   # 7


def _tala_cycle_ticks() -> int:
    """Tick-length of one 7-beat tala cycle -- PPQN ticks per quarter-note
    beat (the same beat unit BAR=4*PPQN uses), times 7 instead of 4. Ticks
    are tempo-independent throughout this module (same reason BAR itself
    isn't a function of bpm), which is what makes this a genuinely
    different meter rather than a regrouping of an existing bar."""
    return _TALA_BEATS_PER_CYCLE * PPQN


def build_tala_overlay(key_root: int, scale: str, start_tick: int, duration_ticks: int,
                       bpm: float) -> list:
    """
    One (or more, back-to-back) 7-beat Rupak Tal cycle(s) of sparse notes,
    covering [start_tick, start_tick + duration_ticks). Meant to be appended
    into the SAME texture_ev list build_texture() populates -- shares its
    channel/program downstream, so this reads as an occasional alternate
    rhythmic character from the same instrument voice (kalimba for
    lofi_world), not a whole new track. Returns (abs_tick, note, velocity,
    duration) tuples, empty list if the scale can't be resolved or there's
    no positive duration to fill.
    """
    notes_scale = _resolve_scale(scale, key_root)
    if not notes_scale or duration_ticks <= 0:
        return []
    cycle_ticks = _tala_cycle_ticks()

    events = []
    t = start_tick
    end = start_tick + duration_ticks
    while t < end:
        beat = 0
        for gi, group in enumerate(_TALA_BEAT_GROUPS):
            group_tick = t + beat * PPQN
            if group_tick >= end:
                break
            # Rupak's "empty" downbeat: the first group (beats 1-3) rests
            # more often and, when it does sound, sits quieter than the
            # other two groups -- an audible de-accent on the cycle start.
            is_first_group = (gi == 0)
            rest_prob = 0.55 if is_first_group else 0.25
            if random.random() >= rest_prob:
                note = random.choice(notes_scale)
                # Gaussian humanization (research/theory/rhythm-groove.md:
                # clustered-not-flat deviation reads as idiomatic) -- same
                # _gauss_jitter/_gauss_velocity pair build_melody() uses,
                # not the flat jitter()/v() this module reserves for
                # secondary texture layers.
                t_humanized = _gauss_jitter(group_tick, 15, bpm)
                vel = _gauss_velocity(28 if is_first_group else 48, 6)
                dur = max(1, int(group * PPQN * random.uniform(0.5, 0.9)))
                events.append((t_humanized, note, vel, dur))
            beat += group
        t += cycle_ticks
    return events


# GM/GS drum kit program numbers for percussion channel (ch 9).
# 0=Standard, 8=Room, 16=Power, 24=Electronic, 25=TR-808, 32=Jazz, 40=Brush.
# Non-zero programs are ignored by GM-only soundfonts (falls back to Standard),
# but GS/SF3 soundfonts select a genuinely different drum kit — audible variety.
_SUBGENRE_DRUM_KITS: dict[str, list[int]] = genre_presets.build_subgenre_drum_kits()
_DEFAULT_DRUM_KIT_POOL = [0, 0, 0, 8, 32]  # mostly Standard, occasional variety

# Scale modal lift for break section: shift to relative major 35% of the time
_SCALE_MODAL_LIFT = {
    'pent':   'major_pent',
    'dorian': 'major_pent',
    'phryg':  'pent',         # partial lift — stays somewhat dark
    'major':  'lydian',       # major → Lydian = dreamy lift (raised 4th floats)
    'lydian': 'major',        # Lydian → back to grounded major
}


# ─── BRIDGE (real reharmonization for the 'BR' section) ───────────────────────

def _bridge_progression(key: str, prog: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """
    A harmonically-distinct progression for the 'BR' section: same tonal
    center as `prog`, but genuinely different chords, so the bridge reads as
    a reharmonization instead of the same progression at lower drum volume.

    Primary path: the music21-backed harmony engine (same call pattern
    pick_params() already uses for `harmony_progression`), with a higher
    secondary-dominant probability than the main-progression call so the
    bridge specifically leans into tonicization.

    Fallback (harmony engine unavailable/fails, or happens to return the
    same chord sequence): a relative-major transposition of each chord
    (mirrors the existing _SCALE_MODAL_LIFT +3-semitone convention already
    used for the bridge's counter-melody key) with an unconditional
    secondary-dominant "pickup" chord prepended. The prepend alone
    guarantees the returned sequence differs from `prog` -- even for
    degenerate 1-2-chord vamp progressions where the transposition lookup
    might not find a matching voicing for every slot.
    """
    try:
        from scripts.harmony_engine import generate_functional_progression, center_for_key
        chord_count = len(prog) if prog else 4
        center, hmode = center_for_key(key)
        hp = generate_functional_progression(
            tonal_center=center, mode=hmode,
            length=max(2, min(6, chord_count)),
            secondary_dominant_prob=round(random.uniform(0.5, 0.75), 2),
        )
        if hp.chords and [c for c, _ in hp.chords] != [c for c, _ in prog]:
            return hp.chords
    except Exception as e:
        print(f"  [bridge] Harmony-engine bridge progression failed ({e}) — using reharmonized fallback")

    reharmonized = []
    for chord_name, dur in prog:
        new_name = chord_name
        root    = BASS_ROOTS.get(chord_name)
        quality = _GUIDE_TONES.get(chord_name)
        if root is not None and quality is not None:
            target_root = (root + 3) % 12   # relative-major shift
            for cand in VOICING_OPTIONS:
                cand_root = BASS_ROOTS.get(cand)
                if cand_root is not None and _GUIDE_TONES.get(cand) == quality \
                        and cand_root % 12 == target_root:
                    new_name = cand
                    break
        new_name = maybe_sub_chord(new_name, 1)
        reharmonized.append((new_name, dur))

    pickup_name = _SEC_DOM_SUBS.get(prog[0][0], ('G7', 0))[0] if prog else 'G7'
    return [(pickup_name, 1)] + reharmonized


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
    # Scale-degree Markov table learned from the pipeline's own past melodies
    # (see _build_self_markov), blended into build_melody's note choices.
    markov_nodes = params.get('markov_melody_nodes')

    # A procedurally-generated progression (Markov walk, ~18% of the time —
    # see generate_progression) takes priority over the curated table. The
    # music21-backed functional-harmony engine (see harmony_engine.py,
    # ~20% of the time via pick_params) takes top priority of all three when
    # present — it is the most theoretically-grounded source (real
    # Roman-numeral tonicization/secondary-dominant resolution) but still an
    # alternate source layered on top of, not replacing, the other two.
    prog      = (params.get('harmony_progression') or params.get('generated_progression')
                 or PROGRESSIONS[prog_idx])
    prog_bars = sum(d for _,d in prog)
    key_root  = KEY_ROOTS.get(key, 57)

    # Drum pattern selection
    pat_a_idx = int(params.get('drum_pattern_a', random.randint(0, len(DRUM_PATTERNS)-1)))
    pat_b_idx = int(params.get('drum_pattern_b', random.randint(0, len(DRUM_PATTERNS)-1)))
    # A freshly-generated Euclidean pattern (see generate_euclidean_drum_pattern,
    # set ~20% of the time in pick_params) takes priority over the curated table.
    pat_a = params.get('drum_pattern_a_generated') or DRUM_PATTERNS[pat_a_idx % len(DRUM_PATTERNS)]
    pat_b = params.get('drum_pattern_b_generated') or DRUM_PATTERNS[pat_b_idx % len(DRUM_PATTERNS)]

    # Phonk roll-density lever (see _scale_roll_intensity) -- only affects
    # pattern Q, only for genres with a configured roll_density; every other
    # pattern/genre combination passes through _scale_roll_intensity() as a
    # no-op (identity check against pattern Q's own dict fails).
    _roll_density = _ROLL_DENSITY_BY_GENRE.get(params.get('sub_genre'))
    if _roll_density is not None:
        pat_a = _scale_roll_intensity(pat_a, _roll_density)
        pat_b = _scale_roll_intensity(pat_b, _roll_density)

    # The audio drum-sample layer plays these same patterns (see
    # drum_sampler.pattern_from_midi), instead of a second, unrelated one.
    params['drum_pattern_dicts'] = (pat_a, pat_b)

    # Sub-genre config (piano/melody programs, forced energy)
    _cfg = _SUBGENRE_CONFIG.get(sub_genre, {})
    piano_prog = _cfg.get('piano', GM_RHODES)
    mel_prog   = _cfg.get('melody', 0)
    forced_energy = _cfg.get('energy')
    if forced_energy:
        energy = forced_energy

    # Drum energy modifier
    energy_mult = {'low': 0.78, 'medium': 1.0, 'high': 1.20}.get(energy, 1.0)

    # New engine-feature membership checks (see _GLIDE_808_GENRES/
    # _MICRO_SWING_GENRES/_CONTINUOUS_ARP_GENRES above) — resolved once per
    # track, threaded through every relevant build_*() call site below.
    use_glide_bass  = sub_genre in _GLIDE_808_GENRES
    use_micro_swing = sub_genre in _MICRO_SWING_GENRES
    use_arp_melody  = sub_genre in _CONTINUOUS_ARP_GENRES
    use_chh_triplet = sub_genre in _CHH_TRIPLET_GENRES
    use_gamaka      = sub_genre in _GAMAKA_GENRES
    use_tala_overlay = sub_genre in _TALA_OVERLAY_GENRES

    # ── Song form ───────────────────────────────────────────────
    form_name = _FORM_BY_SUBGENRE.get(sub_genre, 'standard')
    form = _SONG_FORMS[form_name]
    # ~25% of the time, use the generative form-grammar (see
    # generate_song_form) instead of the hand-authored form above — an
    # additional source of structural variety, not a replacement; same
    # try/except-guarded, per-track-probability-gated pattern as this
    # module's other optional generative layers.
    if random.random() < 0.25:
        try:
            form = generate_song_form()
            form_name = 'generative'
        except Exception as e:
            print(f"  [form] Generative form grammar failed ({e}) — using '{form_name}'")
    form = fit_form_length(form, prog_bars, bpm)

    # Total bars and fill bars (last bar before each section transition)
    TOTAL = sum(prog_bars * n for _, n in form)
    fill_bars = set()
    c = 0
    for _sec, _n in form:
        c += prog_bars * _n
        fill_bars.add(c - 1)

    # Section-boundary transition FX (research/theory/arrangement-structure.md
    # gap #1, see _SECTION_TRANSITION_FX/section_transition_fx_for): computed
    # once here from `form`+`bpm` alone (both fixed before the retry loop
    # below rolls per-attempt randomness), so it's already consistent with
    # whichever attempt the quality gate ends up keeping as best_events --
    # no need to fold this into that loop's bookkeeping.
    section_transitions = _compute_section_transitions(form, prog_bars, bpm)
    params['full_beat_spans'] = full_beat_spans(form, prog_bars, bpm)
    params['full_beat_span_labels'] = full_beat_span_labels(form)

    # ── Motif scale (recomputed fresh per retry attempt below) ──
    # Uses the same _resolve_scale() dispatch as build_melody()/
    # build_counter_melody() (previously this was a separate, partial elif
    # chain covering only 5 of the ~15 scale names -- any other scale name
    # silently fell back to pentatonic here even though build_melody() would
    # go on to use the correct scale for the actual notes, which meant the
    # seed motif and the melody built from it could disagree on scale).
    _motif_scale = _resolve_scale(scale, key_root)

    print(f"  BPM={bpm} key={key} prog={prog_idx} swing={int(swing*100)}% "
          f"energy={energy} sub={sub_genre} walk={walking} form={form_name} mood='{mood}' | {TOTAL} bars")

    # ── Build events, with a quality-gate retry loop ─────────────
    # Each attempt gets a fresh motif and break-scale roll (not just a
    # re-run of the same random.* calls) so a retry actually produces a
    # structurally different arrangement, not a near-identical one. Never
    # blocks the daily upload over this — worst case, keeps the
    # highest-scoring attempt even if none clear the threshold.
    try:
        from scripts.track_quality import score_track_quality, MIN_QUALITY_SCORE, MAX_RETRIES
    except Exception:
        score_track_quality, MIN_QUALITY_SCORE, MAX_RETRIES = None, 0.0, 0

    best_events = None
    best_score = -1.0
    best_failures: list = []
    attempts_used = 0

    for attempt in range(1 + MAX_RETRIES):
        attempts_used = attempt + 1

        break_scale    = scale
        break_key_root = key_root
        if random.random() < 0.35 and scale in _SCALE_MODAL_LIFT:
            break_scale    = _SCALE_MODAL_LIFT[scale]
            break_key_root = key_root + 3   # relative major (+3 semitones: Am→C, Dm→F)
        if _motif_scale:
            track_motif = (generate_lsystem_motif(_motif_scale) if random.random() < 0.28
                           else generate_motif(_motif_scale))
        else:
            track_motif = None

        piano_ev    = []
        bass_ev     = []
        drum_ev     = []
        mel_ev      = []
        pad_ev      = []
        cmelo_ev    = []
        texture_ev  = []
        sustain_ev  = []
        active_bars = 0

        cursor = 0
        prev_label    = None
        prev_sec_bars = 0
        for sec_label, n_loops in form:
            sec_start = cursor
            sec_bars  = prog_bars * n_loops
            # Storytelling-arc scalar for this section (see _tension()) —
            # threaded into melody/chord density and texture probability
            # below, not just drum velocity.
            sec_tension = _tension(sec_start + sec_bars // 2, TOTAL)

            if sec_label == 'B' and prev_label in ('BR', 'A'):
                # Escalating build-up fill in the tail of the *previous*
                # section, marking the transition into the tension peak.
                drum_ev += build_buildup_fill(sec_start, min(2, prev_sec_bars), swing, bpm)

            if sec_label == 'I':
                piano_ev   += build_chords(prog, sec_start, n_loops, swing, bpm)
                pad_ev     += build_pad(prog, sec_start, n_loops, swing, bpm)
                sustain_ev += build_sustain_pedal(prog, sec_start, n_loops, swing, bpm)
                # Bass enters a couple of bars in, but stays in sync with the
                # chords: build the whole intro's bass line from the section
                # start and drop the notes before the entry bar. (Starting
                # build_bass() at the entry bar put the bass one chord behind
                # the piano and ran it past the end of the intro.)
                bass_s = sec_start + min(2, prog_bars - 1)
                bass_ev += [e for e in build_bass(prog, sec_start, n_loops, swing, bpm, False,
                                                  glide=use_glide_bass)
                            if bass_s * BAR - S16 <= e[0] < (sec_start + sec_bars) * BAR]
                hat_s = sec_start + min(2, prog_bars - 1)
                hat_b = sec_bars - (hat_s - sec_start)
                if hat_b > 0:
                    drum_ev += build_intro_hats(hat_s, hat_b, swing, bpm)
                cmelo_ev += build_counter_melody(key_root, sec_start, sec_bars, swing, bpm,
                                                 scale=scale, seed_motif=track_motif, gamaka=use_gamaka)

            elif sec_label == 'A':
                piano_ev   += build_chords(prog, sec_start, n_loops, swing, bpm, tension=sec_tension)
                bass_ev    += build_bass(prog, sec_start, n_loops, swing, bpm, walking, glide=use_glide_bass)
                drum_ev    += build_drums(pat_a, sec_start, sec_bars, swing, bpm, fill_bars,
                                          micro_swing=use_micro_swing, chh_triplet=use_chh_triplet,
                                          allow_generated=sub_genre in _GENERATED_DRUM_GENRES)
                pad_ev     += build_pad(prog, sec_start, n_loops, swing, bpm)
                if use_arp_melody:
                    # Synthwave's melodic engine is the arp itself, not
                    # arp-plus-separate-phrase-melody (research/subgenres/
                    # lofi_synthwave.md) -- replaces build_melody() here.
                    mel_ev += build_arpeggio(prog, sec_start, n_loops, swing, bpm, key_root=key_root)
                else:
                    mel_ev += build_melody(key_root, sec_start, sec_bars, swing, bpm,
                                           'sparse', scale, motif=track_motif,
                                           progression=prog, prog_bars=prog_bars,
                                           markov_nodes=markov_nodes, tension=sec_tension,
                                           gamaka=use_gamaka)
                sustain_ev += build_sustain_pedal(prog, sec_start, n_loops, swing, bpm)
                active_bars += sec_bars
                _tex = _SUBGENRE_TEXTURE.get(sub_genre)
                if _tex and random.random() < (0.35 + 0.40 * sec_tension):
                    texture_ev += build_texture(_tex[0], prog, sec_start, sec_bars, swing, bpm, _tex[1])
                # Tala-cycle polymetric overlay (see build_tala_overlay's
                # module comment) -- independent probability roll from the
                # texture layer above, appended into the same texture_ev
                # list/channel/program rather than replacing anything.
                if use_tala_overlay and random.random() < 0.30:
                    texture_ev += build_tala_overlay(key_root, scale, sec_start * BAR,
                                                      sec_bars * BAR, bpm)

            elif sec_label == 'BR':
                bridge_prog      = _bridge_progression(key, prog)
                bridge_prog_bars = sum(d for _, d in bridge_prog) or prog_bars
                bridge_loops     = max(1, sec_bars // bridge_prog_bars)
                piano_ev   += build_chords(bridge_prog, sec_start, bridge_loops, swing, bpm, tension=sec_tension)
                bass_ev    += build_bass(bridge_prog, sec_start, bridge_loops, swing, bpm, walking, glide=use_glide_bass)
                pad_ev     += build_pad(bridge_prog, sec_start, bridge_loops, swing, bpm)
                drum_ev    += build_break_hats(sec_start, sec_bars, swing, bpm)
                cmelo_ev   += build_counter_melody(break_key_root, sec_start, sec_bars, swing, bpm,
                                                   scale=break_scale, seed_motif=track_motif, gamaka=use_gamaka)
                sustain_ev += build_sustain_pedal(bridge_prog, sec_start, bridge_loops, swing, bpm)

            elif sec_label == 'B':
                piano_ev   += build_chords(prog, sec_start, n_loops, swing, bpm, tension=sec_tension)
                bass_ev    += build_bass(prog, sec_start, n_loops, swing, bpm, walking, glide=use_glide_bass)
                drum_ev    += build_drums(pat_b, sec_start, sec_bars, swing, bpm, fill_bars,
                                          micro_swing=use_micro_swing, chh_triplet=use_chh_triplet,
                                          allow_generated=sub_genre in _GENERATED_DRUM_GENRES)
                pad_ev     += build_pad(prog, sec_start, n_loops, swing, bpm)
                sustain_ev += build_sustain_pedal(prog, sec_start, n_loops, swing, bpm)
                active_bars += sec_bars
                _tex = _SUBGENRE_TEXTURE.get(sub_genre)
                if use_tala_overlay and random.random() < 0.30:
                    texture_ev += build_tala_overlay(key_root, scale, sec_start * BAR,
                                                      sec_bars * BAR, bpm)

                # Per-loop climax handling: the loop(s) coinciding with
                # _tension()'s peak plateau get denser melody, a guaranteed
                # texture layer, an extra counter-melody voice, and a
                # stronger fill — distinguishable from an ordinary B-loop
                # repeat instead of every loop in the section being identical.
                for loop_i in range(max(1, n_loops)):
                    loop_start   = sec_start + loop_i * prog_bars
                    loop_tension = _tension(loop_start + prog_bars // 2, TOTAL)
                    is_climax    = loop_tension >= 0.95
                    if use_arp_melody:
                        mel_ev += build_arpeggio(prog, loop_start, 1, swing, bpm, key_root=key_root)
                    else:
                        mel_ev += build_melody(key_root, loop_start, prog_bars, swing, bpm,
                                               'dense' if is_climax else 'medium', scale,
                                               motif=track_motif, progression=prog,
                                               prog_bars=prog_bars, markov_nodes=markov_nodes,
                                               tension=loop_tension, gamaka=use_gamaka)
                    if loop_i >= 1 or is_climax:
                        cmelo_ev += build_counter_melody(key_root, loop_start, prog_bars, swing, bpm,
                                                         scale=scale, seed_motif=track_motif, gamaka=use_gamaka)
                    if is_climax:
                        if _tex:
                            texture_ev += build_texture(_tex[0], prog, loop_start, prog_bars,
                                                        swing, bpm, _tex[1])
                        drum_ev += build_buildup_fill(loop_start + prog_bars,
                                                      min(1, prog_bars), swing, bpm)
                    elif _tex and random.random() < (0.35 + 0.40 * loop_tension):
                        texture_ev += build_texture(_tex[0], prog, loop_start, prog_bars,
                                                    swing, bpm, _tex[1])

            elif sec_label == 'O':
                piano_ev   += build_chords(prog, sec_start, n_loops, swing, bpm)
                bass_ev    += build_bass(prog, sec_start, n_loops, swing, bpm, False, glide=use_glide_bass)
                pad_ev     += build_pad(prog, sec_start, n_loops, swing, bpm)
                cmelo_ev   += build_counter_melody(key_root, sec_start, sec_bars, swing, bpm,
                                                   scale=scale, seed_motif=track_motif, gamaka=use_gamaka)
                sustain_ev += build_sustain_pedal(prog, sec_start, n_loops, swing, bpm)
                od_bars = max(1, sec_bars // 2)
                od_raw  = build_drums(pat_a, sec_start, od_bars, swing, bpm,
                                      micro_swing=use_micro_swing, chh_triplet=use_chh_triplet,
                                          allow_generated=sub_genre in _GENERATED_DRUM_GENRES)
                n_od = len(od_raw)
                od_raw = [(ev[0], ev[1], max(1, int(ev[2] * (1.0 - (i / max(1, n_od)) * 0.75))), ev[3])
                          for i, ev in enumerate(od_raw)]
                drum_ev += od_raw
                if sec_bars - od_bars > 0:
                    drum_ev += build_intro_hats(sec_start + od_bars, sec_bars - od_bars, swing, bpm)

            cursor += sec_bars
            prev_label    = sec_label
            prev_sec_bars = sec_bars

        this_events = (piano_ev, bass_ev, drum_ev, mel_ev, pad_ev, cmelo_ev, texture_ev, sustain_ev)

        if score_track_quality is None:
            best_events, best_score = this_events, 1.0
            break

        try:
            score, failures = score_track_quality(mel_ev, piano_ev, drum_ev, active_bars, sub_genre)
        except Exception as e:
            print(f"  [quality] Scoring failed ({e}) — accepting attempt without gating")
            best_events, best_score, best_failures = this_events, 1.0, []
            break

        if score > best_score:
            best_events, best_score, best_failures = this_events, score, failures
        if score >= MIN_QUALITY_SCORE:
            break

    if best_score < MIN_QUALITY_SCORE and score_track_quality is not None:
        print(f"  [quality] Track scored {best_score:.2f} after {attempts_used} attempt(s) "
              f"(failures: {best_failures}) — using best attempt, not blocking upload")

    piano_ev, bass_ev, drum_ev, mel_ev, pad_ev, cmelo_ev, texture_ev, sustain_ev = best_events

    # ── Avoid-note filter: no sustained melody note a semitone above the chord ──
    mel_ev, _n_mel_fix = fix_melodic_clashes(mel_ev, piano_ev)
    cmelo_ev, _n_cm_fix = fix_melodic_clashes(cmelo_ev, piano_ev)
    texture_ev, _n_tx_fix = fix_melodic_clashes(texture_ev, piano_ev)
    if _n_mel_fix + _n_cm_fix + _n_tx_fix:
        print(f"  [harmony] Moved {_n_mel_fix + _n_cm_fix + _n_tx_fix} clashing note(s) onto chord tones")

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
    # Per-genre bass (config/genres/*.yaml bass_program): upright for jazz
    # and bossa, slap for city pop/funk, synth for house/synthwave, an
    # 808-style sub for drill/phonk.
    bass_prog = _BASS_PROGRAMS.get(sub_genre, GM_BASS)
    # pitch_bend_range only when this subgenre's bass actually uses glide=True
    # (see use_glide_bass above) -- keeps the RPN setup scoped to the one
    # feature that needs it instead of touching every subgenre's bass track.
    mid.tracks.append(abs_to_track(bass_ev, channel=1, program=bass_prog,
                                   pitch_bend_range=_GLIDE_BEND_RANGE_SEMITONES if use_glide_bass else None))
    # Rotate drum kit per track — GS/SF3 soundfonts honor non-zero kits;
    # GM-only soundfonts silently fall back to Standard (program 0).
    if sub_genre in _BEATLESS_GENRES:
        drum_ev = []          # ambient: no beat (config/genres drums: false)
    drum_kit = random.choice(_SUBGENRE_DRUM_KITS.get(sub_genre, _DEFAULT_DRUM_KIT_POOL))
    mid.tracks.append(abs_to_track(drum_ev, channel=9, program=drum_kit,
                                   bank_msb=127 if drum_kit != 0 else None))
    # pitch_bend_range only when this subgenre actually uses gamaka (see
    # use_gamaka above) -- same scoped-RPN-setup pattern as the bass glide.
    _gamaka_bend_range = _GAMAKA_BEND_RANGE_SEMITONES if use_gamaka else None
    if mel_ev:
        mid.tracks.append(abs_to_track(mel_ev,    channel=2, program=mel_prog,
                                       pitch_bend_range=_gamaka_bend_range))
    # Pad: always present — fills air throughout
    mid.tracks.append(abs_to_track(pad_ev,    channel=3,
                                   program=_PAD_PROGRAMS.get(sub_genre, GM_STRINGS)))
    # Counter melody: instrument chosen per sub-genre
    if cmelo_ev:
        cmelo_prog = _cfg.get('cmelo', GM_WARM_PAD)
        mid.tracks.append(abs_to_track(cmelo_ev, channel=4, program=cmelo_prog,
                                       pitch_bend_range=_gamaka_bend_range))
    # Texture layer: secondary genre-specific instrument (guitar/organ/flute/marimba/trumpet)
    if texture_ev:
        tex_prog = _SUBGENRE_TEXTURE[sub_genre][0] if sub_genre in _SUBGENRE_TEXTURE else GM_WARM_PAD
        mid.tracks.append(abs_to_track(texture_ev, channel=5, program=tex_prog))

    # Feed this track's melody into the self-referential history (see
    # _build_self_markov / pick_params) so future tracks can draw on it.
    # Fires once, on the winning attempt only — a discarded low-quality
    # attempt must never pollute the self-referential model with exactly the
    # kind of melody the quality gate exists to filter out.
    _root_pc = KEY_ROOTS.get(key, 57) % 12
    _save_melody_pitch_classes([(note - _root_pc) % 12 for (_t, note, _v, _d) in mel_ev])
    try:
        _append_recipe_log(params, quality_score=best_score,
                            quality_retries=attempts_used - 1, ga_voicing=False)
    except Exception:
        pass

    mid.save(output_path)
    return output_path, section_transitions

# ─── RENDER ───────────────────────────────────────────────────────────────────

_BG_GEN_NICE_LEVEL = 10   # 0 (default) to 19 (lowest); see midi_to_wav's low_priority


def midi_to_wav(midi_path: str, wav_path: str, soundfont: str | None = None,
                 low_priority: bool = False) -> None:
    sf = soundfont or _pick_soundfont()
    # subprocess with capture_output=True — zero ALSA/Jack noise, isolated from parent process.
    # pyfluidsynth was tried here but its start() triggers PortAudio initialisation on this system,
    # which calls C-level abort() on assertion failure — uncatchable by Python exceptions.
    cmd = [
        'fluidsynth', '-ni',
        '-F', wav_path, '-r', '44100', '-T', 'wav', '-O', 's16',
        '-R', '0',           # disable FluidSynth reverb (pedalboard chain handles reverb)
        '-o', 'synth.reverb.active=no',
        '-C', '0',           # disable chorus (adds shimmer — not lo-fi)
        '-g', '3.0',         # raised gain: default 0.85 left signal at ~4% full scale,
                             # causing bitcrusher to quantize to only ~21-46 levels (noise).
                             # 3.0 brings signal to ~15% full scale for clean bit-reduction.
        sf, midi_path,
    ]
    # low_priority: used by stream_live.py's background track generation,
    # which runs concurrently with a real-time ffmpeg encode on the same
    # (often 2-4 thread) box. FluidSynth rendering is the single heaviest
    # CPU step in track generation, so this is the highest-value place to
    # yield scheduling priority to the encode rather than contend with it --
    # nice/ionice lower this process's priority when the CPU/IO is actually
    # contended, they don't cap its throughput when the machine is idle (a
    # systemd CPUQuota would do the latter, which isn't what's wanted for a
    # background job that should still finish promptly when nothing else is
    # running). POSIX-only; on Windows (or if nice/ionice aren't installed)
    # this just runs fluidsynth directly, same as before.
    if low_priority and os.name == 'posix':
        cmd = ['nice', '-n', str(_BG_GEN_NICE_LEVEL), 'ionice', '-c3'] + cmd
    subprocess.run(cmd, check=True, capture_output=True)


# ─── ENTRY ────────────────────────────────────────────────────────────────────

_AUDIO_RETRIES = 2   # re-renders allowed when the audio quality gate fails


def _render_track(index: int, params: dict, low_priority: bool, attempt: int = 0,
                  out_dir: str = MUSIC_DIR):
    """Build MIDI, render, run the FX chain and drum layer. Returns (wav_path, audio_score)."""
    with tempfile.TemporaryDirectory() as tmp:
        midi_path = os.path.join(tmp, 'track.mid')
        raw_wav   = os.path.join(tmp, 'raw.wav')

        print("  [MIDI] Building...")
        _, section_transitions = build_midi(params, midi_path)
        chosen_sf = _pick_soundfont()
        print(f"  [FluidSynth] Rendering ({os.path.basename(chosen_sf)})...")
        midi_to_wav(midi_path, raw_wav, soundfont=chosen_sf, low_priority=low_priority)
        print(f"  [FX] Lo-fi chain ({params.get('sub_genre', '?')})...")
        ts = int(time.time())
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, f'track_{ts}_{index:02d}_{attempt}.wav')
        from scripts.lofi_fx import apply_lofi_fx as _lofi_fx

        _lofi_fx(raw_wav, out,
                 sub_genre=params.get('sub_genre'),
                 bpm=params.get('bpm', 80),
                 energy=params.get('drum_energy', 'medium'),
                 transitions=section_transitions)

        # Layer synthesized drum break — real FM+noise drums on top of the
        # MIDI render so every track has a different acoustic character.
        try:
            from scripts.drum_sampler import layer_drum_break as _layer_drums, pattern_from_midi
            _sub = params.get('sub_genre', 'chillhop')
            if _sub in _BEATLESS_GENRES:
                raise RuntimeError("beatless genre")
            print(f"  [DRUMS] Layering sampled drums on the MIDI pattern ({_sub})...")
            _pats = params.get('drum_pattern_dicts')
            _trip = _sub in _CHH_TRIPLET_GENRES
            _layer_drums(out, out,
                         bpm=params.get('bpm', 80),
                         sub_genre=_sub,
                         volume=0.22,
                         swing=float(params.get('swing', 0.62)),
                         spans=params.get('full_beat_spans'),
                         patterns=(tuple(pattern_from_midi(p, _trip) for p in _pats)
                                   if _pats else None),
                         span_labels=params.get('full_beat_span_labels'))
        except Exception as _de:
            print(f"  [DRUMS] Skipped ({_de})")

        # Audio-domain quality gates (clipping/silence/LUFS/spectral-balance
        # — see track_quality.score_audio_quality) on the FINAL rendered
        # WAV, i.e. after FluidSynth render + the full lofi_fx chain + drum
        # layering above — this is the audio the pipeline is actually about
        # to publish. generate_track() re-renders when the score is below
        # AUDIO_MIN_QUALITY_SCORE.
        try:
            import soundfile as _sf
            from scripts.track_quality import score_audio_quality
            _audio, _sr = _sf.read(out, dtype='float32')
            _audio_score, _audio_failures = score_audio_quality(_audio, _sr)
            print(f"  [audio-quality] score={_audio_score:.2f} failures={_audio_failures}")
            _append_audio_quality_log(out, _audio_score, _audio_failures)
        except Exception as _aqe:
            print(f"  [audio-quality] Scoring skipped ({_aqe})")
            _audio_score = None
    return out, _audio_score


def generate_track(index=0, concept_hint: str = None, genre_hint: str = None, song_dna: dict = None,
                    low_priority: bool = False, out_dir: str = MUSIC_DIR):
    print(f"\n[Track {index+1}] Picking parameters...")
    if song_dna is not None:
        # Pre-computed params (from generate_tracks' per-track diversity pass)
        params = dict(song_dna)
        print(f"  [DNA] bpm={params.get('bpm')} key={params.get('key')} sub={params.get('sub_genre')}")
    else:
        params = pick_params(concept_hint=concept_hint, genre_hint=genre_hint)

    from scripts.track_quality import AUDIO_MIN_QUALITY_SCORE
    best_out, best_score = None, None
    for attempt in range(1 + _AUDIO_RETRIES):
        out, score = _render_track(index, params, low_priority, attempt, out_dir)
        if score is None or score >= AUDIO_MIN_QUALITY_SCORE:
            if best_out and best_out != out:
                os.remove(best_out)
            best_out, best_score = out, score
            break
        print(f"  [audio-quality] {score:.2f} is below {AUDIO_MIN_QUALITY_SCORE:.2f} -- "
              f"re-rendering ({attempt + 1}/{_AUDIO_RETRIES + 1})")
        if best_score is None or score > best_score:
            if best_out:
                os.remove(best_out)
            best_out, best_score = out, score
        else:
            os.remove(out)
    out = best_out

    # Save sidecar metadata for stream now-playing display AND for run.py's
    # concept/meta-alignment step (which stashes sub_genre/bpm/music_engine
    # onto the SEO dict so they reach upload_log.json -> analytics_log.json
    # -> sub_genre_weights()/bpm_bucket_weights()).
    # music_engine is hardcoded "v1" here — this module is the v1 generator;
    # generate_music_v2.py's own generate_track() hardcodes "v2" in its
    # equivalent sidecar write.
    with open(out + ".meta.json", "w", encoding="utf-8") as _mf:
        json.dump({
            "title": params.get("mood", "lofi dreams"),
            "genre": params.get("sub_genre", "lo-fi hip hop"),
            "bpm": params.get("bpm"),
            "music_engine": "v1",
        }, _mf)

    print(f"  ✓ {out} ({os.path.getsize(out)//1024//1024} MB)")
    return out


def _build_diverse_params(count: int, concept_hint=None, genre_hint=None) -> list[dict]:
    """
    Param sets for the N tracks of one video. Every track stays in the
    anchor track's sub-genre (the video is titled, thumbnailed and labelled
    for one genre) and differs in progression, key and tempo. Every set
    comes from pick_params(), which derives the melody key from the chosen
    progression -- building tracks any other way put melodies in a
    different key from the chords underneath them.
    """
    anchor = pick_params(concept_hint=concept_hint, genre_hint=genre_hint)
    param_sets = [anchor]
    sub = anchor.get('sub_genre')
    used_moods = {anchor.get('mood')}
    prog_uses = {anchor.get('progression'): 1}
    for _ in range(1, count):
        # Only the first track carries the video's concept as its title; the
        # others get their own phrase. Of several candidates, take the one
        # whose progression this video has used least (and never the one
        # just played): checking only the previous track let one progression
        # fill a third of a video.
        candidates = [pick_params(concept_hint=None, genre_hint=sub) for _attempt in range(8)]
        fresh = [c for c in candidates
                 if c.get('progression') != param_sets[-1].get('progression')] or candidates
        params = min(fresh, key=lambda c: prog_uses.get(c.get('progression'), 0))
        prog_uses[params.get('progression')] = prog_uses.get(params.get('progression'), 0) + 1
        for _attempt in range(8):
            if params['mood'] not in used_moods:
                break
            params['mood'] = _compose_mood_phrase(sub)
        used_moods.add(params['mood'])
        param_sets.append(params)
    return param_sets


def generate_tracks(count=3, concept_hint: str = None, genre_hint: str = None, song_dna: dict = None):
    import concurrent.futures
    print(f"[MUSIC] Generating {count} track(s)...")

    # Pre-compute one param set per track: same sub-genre for the whole video,
    # a different progression/key/tempo per track (see _build_diverse_params).
    if song_dna is None and count > 1:
        param_sets = _build_diverse_params(count, concept_hint, genre_hint)
        print(f"  [MUSIC] Track plan: {' → '.join(p['sub_genre'] for p in param_sets)}")
    else:
        param_sets = None

    # Parallel generation — FluidSynth and ffmpeg are subprocess calls so
    # threads release the GIL; 3 workers caps CPU.
    workers = min(count, 3)

    def _run(i):
        dna = param_sets[i] if param_sets else song_dna
        chint = None if param_sets else concept_hint
        ghint = None if param_sets else genre_hint
        return generate_track(i, concept_hint=chint, genre_hint=ghint, song_dna=dna)

    if workers <= 1:
        paths = []
        for i in range(count):
            try:
                paths.append(_run(i))
            except Exception as e:
                print(f"  [ERROR] Track {i}: {e}")
    else:
        # Threads complete in whatever order they finish, not submission
        # order -- write into a fixed-size slot per index (not append) so
        # the returned list stays in the planned/submission order
        # (matching the "Track plan: X -> Y -> Z" printed above). Callers
        # (e.g. run.py's SEO-alignment step, which reads paths[0]'s
        # .meta.json as "the" track) depend on slot 0 meaning the first
        # planned track, not whichever thread happened to finish first.
        slots: list[str | None] = [None] * count
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_run, i): i for i in range(count)}
            for fut in concurrent.futures.as_completed(futs):
                i = futs[fut]
                try:
                    slots[i] = fut.result()
                except Exception as e:
                    print(f"  [ERROR] Track {i}: {e}")
        paths = [p for p in slots if p is not None]

    print(f"\n[MUSIC] {len(paths)}/{count} tracks ready.")
    return paths


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    generate_tracks(n)
