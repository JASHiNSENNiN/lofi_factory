---
subgenre_key: lofi_garage
status: new_candidate
bpm_range: [66, 76]              # note: source-genre UK garage/2-step/future garage runs 130-140 BPM natively; this value is a half-time lofi-engine equivalent (65-70ish base pulse with the 2-step off-grid hit pattern felt as the "real" groove), analogous to how this codebase already halves drill's 140-BPM native tempo for lofi_drill. Flagged explicitly since it is NOT a literal transcription of source-genre BPM.
swing_range: [0.66, 0.76]
scales: [dorian, natural_minor, pentatonic_minor]
mood_descriptors: [shuffling, nocturnal, moody, syncopated, emotive]
---

## Harmony
Sources describe UK garage harmony as "a mix of minor and major keys, with classic UKG leaning minor for emotional depth," using short rhythmic chord stabs rather than sustained pads — "sus2 and add9 voicings common for that bittersweet UKG harmonic feel." The lofi-crossover variant specifically is cited as featuring "jazzy 7ths and minor 9ths, classic organ riffs, lo-fi pads, and housey piano chords" — i.e., a genuinely distinct harmonic fingerprint from this codebase's existing `lofi_house` key: garage should feel more emotionally minor-leaning and vocal-chop-driven than house's steadier major/dorian groove-first approach, and its chords should be short/percussive stabs rather than held tones.

## Melody
Future garage's atmospheric wing (Burial, FaltyDL, Joy Orbison) is defined by "pitched vocal chops, warm filtered reese basses, dark atmospheres... and vinyl crackle" — since this codebase has no vocal-chop mechanism, the closest instrumental analogue is a melody voice built from short, pitch-bent, stuttering phrase fragments (echoing chopped-vocal rhythm) rather than legato lines. Sources explicitly credit Burial's 2007 album *Untrue* with placing "agile, agitated garage rhythms on top of deep, emotive electronic and sampled soundscapes" — melody should feel fragmentary and emotionally raw against a more skeletal harmonic bed, distinct from the smoother melodic phrasing of `chillhop` or `lofi_house`.

## Rhythm/groove
This is lofi_garage's clearest identity anchor and the strongest reason to treat it as genuinely distinct from the existing roster: "2-step patterns involve removing the kick from every beat and creating a syncopated, groovy rhythm with hits placed slightly off-grid," and — critically — "garage swing lives in the individual hits" (per-hit micro-timing offsets), not a uniform swing-quantize value applied at the end; "sixteenth-note hats are pushed late... without collapsing into full triplets." This groove mechanic is structurally different from every other subgenre in the roster (which apply a single swing ratio uniformly) and would ideally need a new per-hit-offset drum-pattern mechanism rather than reusing the existing swing_range system as-is — flagged as a "needs new rhythm-engine feature" note.

## Arrangement/structure
Warm sub-bass (40-80Hz, monophonic sine-wave-style) is a defining low-end signature distinct from this codebase's existing `GM_BASS` usage elsewhere — garage bass should sit cleaner and more centered than the funkier/syncopated bass patterns used in `lo_fi_funk` or `city_pop`. Arrangement leans on "shuffling drum patterns, soul-inspired vocals, and warm bass," with atmospheric pads filling space around the sparse 2-step kick/snare skeleton — a genuinely different rhythmic silhouette from the boom-bap-descended patterns underlying most of the existing 26 keys.

## Reference repos/algorithms
No dedicated lofi-garage MIDI-generation repos found; the clearest reference lineage is Burial's catalog (specifically *Untrue*, 2007) for the atmospheric/future-garage mood, and general UK garage/2-step production tutorials (Loopmasters, BeatKey, Transmission Samples) for the per-hit swing-timing technique that most distinguishes this genre mechanically from the rest of the roster.

## Provenance
- [Master UK Garage Production: Complete Guide to Filthy Basslines and Swing – The Producer School](https://theproducerschool.com/blogs/featured-blogs/master-uk-garage-production-complete-guide-to-filthy-basslines-and-swing-drums)
- [UK Garage Tutorial: Chord Progressions, Rhythms & Production Tips](https://www.transmissionsamples.com/uk-garage-tutorial)
- [Future garage — Wikipedia](https://en.wikipedia.org/wiki/Future_garage)
- [Future Garage Guide: 5 Characteristics of Future Garage Music - MasterClass](https://www.masterclass.com/articles/future-garage-guide)
- [UK Garage Production Tips 2025 | Big Drum Records](https://www.bigdrumrecords.co.uk/blog/uk-garage-production-tips)
- [How to Make UK Garage Music - 2-Step Production Guide | BeatKey](https://beatkey.app/how-to-make-uk-garage-music)
