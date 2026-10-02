"""
gm_instruments.py — General MIDI program-number constants.

Pure relocation of the GM_* constants that used to live inline near the top
of composer.py. No behavior here — just names to symbolic
integers, imported back into composer.py (and used directly by
config/genres/*.yaml's symbolic-name resolution in scripts/genre_presets.py).
"""

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

# GM "Ethnic" family (spec slots 105/108/109, 0-indexed) — lofi_world's lead/
# counter-melody/texture voices, distinct from every other subgenre's Western
# instrument palette above.
GM_SITAR          = 104  # lofi_world lead melody
GM_KOTO           = 107  # lofi_world counter-melody
GM_KALIMBA        = 108  # lofi_world texture accent
