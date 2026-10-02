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
GM_ORGAN_ROCK     = 17   # neo_soul, lo_fi_funk stabs. NB: GM 17 (0-indexed) is Percussive Organ
GM_MUTED_TRUMPET  = 59   # nujabes, jazz_cafe, lofi_jazz fills
GM_CELLO          = 42   # dark_lofi, piano_lofi, ambient pad voice
GM_FLUTE          = 73   # ambient, morning_lofi, bossa_lofi whisper

# GM "Ethnic" family (spec slots 105/108/109, 0-indexed) — lofi_world's lead/
# counter-melody/texture voices, distinct from every other subgenre's Western
# instrument palette above.
GM_SITAR          = 104  # lofi_world lead melody
GM_KOTO           = 107  # lofi_world counter-melody
GM_KALIMBA        = 108  # lofi_world texture accent

# Added with the genre rework (0-indexed GM 1 program numbers, checked
# against the GM 1 sound set: https://en.wikipedia.org/wiki/General_MIDI).
GM_ACOUSTIC_GRAND = 0    # piano_lofi, lofi_classical, nujabes
GM_DRAWBAR_ORGAN  = 16
GM_GUITAR_CLEAN   = 27   # city_pop / bedroom_pop chorus guitar
GM_ACOUSTIC_BASS  = 32   # upright: jazz, bossa
GM_FINGER_BASS    = 33   # neo_soul, rnb, chillhop
GM_FRETLESS_BASS  = 35
GM_SLAP_BASS      = 36   # city_pop, lo_fi_funk
GM_SYNTH_BASS_1   = 38   # house, synthwave
GM_SYNTH_BASS_2   = 39   # 808-style sub for drill/phonk (with glide)
GM_ALTO_SAX       = 65   # vaporwave smooth-jazz lead
GM_TENOR_SAX      = 66   # nujabes
GM_SQUARE_LEAD    = 80
GM_SAW_LEAD       = 81   # synthwave lead/arp
GM_NEW_AGE_PAD    = 88
GM_POLYSYNTH_PAD  = 90   # synthwave chords
GM_AGOGO          = 113  # pitched bell: phonk's cowbell melody
GM_CLAVI          = 7    # lo_fi_funk stabs
