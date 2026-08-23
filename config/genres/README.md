# config/genres/ — per-subgenre data

One YAML file per lofi subgenre (26 files, one per `key`). Parsed by
`scripts/genre_presets.py`, which resolves `GM_*` symbolic instrument names
against `scripts/gm_instruments.py`, validates the result, and reconstructs
the exact in-memory shapes the rest of the codebase (`generate_music_gemini.py`,
`lofi_fx.py`, `drum_sampler.py`) used to get from 6 scattered Python literal
dicts/sets. This directory is the single source of truth for per-subgenre
composition, mix, and drum-sampler behavior — nothing here changes what a
track sounds like, it only changes where the numbers live.

## Schema

```yaml
key: <subgenre>                    # must match the filename (without .yaml)
family: <comment-only grouping>    # e.g. hip_hop_beat, jazz_soul, dark_moody,
                                    # cozy_bright, acoustic_classical,
                                    # drill_trap, world_fusion — informational
                                    # only, not read by any consuming code

composition:
  piano_program: GM_SOMETHING          # symbolic GM_* name (scripts/gm_instruments.py)
  melody_program: GM_SOMETHING
  countermelody_program: GM_SOMETHING
  scales: [...]                        # scale-name pool build_melody() picks from
  drum_pattern_indices: [...]          # indices into generate_music_gemini.DRUM_PATTERNS
  bpm_range: [min, max]
  energy: low|medium|high|null         # null = pick_params() rolls a random energy
  progression_indices: [...]           # indices into generate_music_gemini.PROGRESSIONS

swing_range: [min, max]              # omit entirely to fall back to _SWING_DEFAULT
cozy_bias: true|false                # true = 2x weight in the channel-identity picker

bass_style: glide_808                # optional. 'glide_808' = 808 pitch-slide/
                                      # portamento bass (drill's signature
                                      # technique) -- build_bass(..., glide=True)
                                      # membership set: _GLIDE_808_GENRES
micro_swing: true|false              # optional, default false. true = per-voice
                                      # micro-timing drum profile (hats widest
                                      # jitter + latest push, snare a smaller
                                      # consistent late pull, kick near the grid)
                                      # instead of one uniform swing ratio --
                                      # build_drums(..., micro_swing=True)
                                      # membership set: _MICRO_SWING_GENRES
melody_style: continuous_arp         # optional. 'continuous_arp' = replace the
                                      # phrase-based build_melody() lead with a
                                      # continuous chord-tone arpeggiator
                                      # (build_arpeggio()) -- synthwave's
                                      # melodic engine. membership set:
                                      # _CONTINUOUS_ARP_GENRES

texture:                             # omit the whole block if this subgenre has none
  program: GM_SOMETHING
  style: strum|stab|breath|pop|fill

drum_kit_programs: [...]             # omit to fall back to _DEFAULT_DRUM_KIT_POOL
drum_sampler_pattern: standard|boom_bap|808_trap|jazz|dusty|null  # null = random pick

mix:
  lpf_hz: ...
  bitcrush_bits: ...
  reverb_room: ...
  reverb_wet: ...
  tape_wobble_depth: ...
  compress_ratio: ...
  vinyl_crackle: ...
  use_ir_reverb: true|false          # true = eligible for real IR convolution reverb
  sidechain_duck: true|false         # true = kick-triggered sidechain "pump"

song_form: null                      # a _SONG_FORMS key to force a specific structure,
                                      # or null to use the default 'standard' form
```

Every field except `key`, `composition.piano_program`, and
`composition.bpm_range` may be omitted — `scripts/genre_presets.py` treats a
missing/null block as "this subgenre doesn't have an entry in that table,"
exactly matching what the old Python dicts meant when a subgenre key simply
wasn't present in them.

## Worked example — `chillhop.yaml`

```yaml
key: chillhop
family: hip_hop_beat
composition:
  piano_program: GM_RHODES
  melody_program: GM_GUITAR_NYLON
  countermelody_program: GM_WARM_PAD
  scales: [pent, dorian, natural_minor]
  drum_pattern_indices: [0, 1, 2, 13]
  bpm_range: [76, 88]
  energy: null
  progression_indices: [0, 1, 7, 10, 11, 13, 33, 38, 44, 45]
swing_range: [0.59, 0.67]
cozy_bias: true
drum_sampler_pattern: dusty
mix: {lpf_hz: 9500, bitcrush_bits: 11, reverb_room: 0.35, reverb_wet: 0.2, tape_wobble_depth: 0.18,
  compress_ratio: 3.0, vinyl_crackle: 0.12, use_ir_reverb: false, sidechain_duck: true}
song_form: null
```

`chillhop` has no `texture` or `drum_kit_programs` block — it wasn't in the
old `_SUBGENRE_TEXTURE` or `_SUBGENRE_DRUM_KITS` dicts either, so it falls
back to no secondary-texture layer and `_DEFAULT_DRUM_KIT_POOL` respectively,
same as before this refactor.

## Adding a new subgenre

1. Author one new `config/genres/<key>.yaml` here, following the schema
   above (copy a similar existing file as a starting point).
2. Add an SEO label for it in `scripts/generate_seo.py::_SUBGENRE_TO_GENRE_LABEL`.
3. Optionally add a small regression test (see
   `tests/generate_music/test_new_subgenres.py` for the pattern) asserting
   the new key shows up in `_SUBGENRE_CONFIG` and behaves as expected.

No Python changes are needed for the new subgenre to become pickable —
`scripts/genre_presets.py` globs every `*.yaml` in this directory at load
time, so a new file is picked up automatically the next time the process
starts (results are cached per-process — restart anything that already
imported `scripts.genre_presets` to pick up a newly added or edited file).
